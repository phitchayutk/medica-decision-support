from __future__ import annotations

import math
from copy import deepcopy
from typing import Dict, List, Tuple

from .config import GameAssumptions
from .forecasting import forecast_short_term
from .schemas import DailyState, DerivedState, ForecastState, RecommendationPackage
from .utils import clamp, safe_div


def _stress_buffer_days(derived: DerivedState) -> float:
    if derived.current_regime == "Endgame":
        return 1.5
    if derived.current_regime == "Recovery":
        return 1.25
    if derived.current_regime == "Stabilize":
        return 0.75
    return 0.30


def recommend_inventory(state: DailyState, derived: DerivedState, assumptions: GameAssumptions) -> Tuple[int, int, str]:
    base_rop = derived.expected_parts_per_day * assumptions.raw_lead_time_days
    buffer_days = _stress_buffer_days(derived)
    stress_buffer = derived.expected_parts_per_day * buffer_days
    rop = max(1, round(base_rop + stress_buffer))

    annual_demand_proxy = max(derived.expected_parts_per_day * 365, 1)
    annual_holding = assumptions.raw_holding_cost_per_part_per_day * 365
    eoq = math.sqrt((2 * annual_demand_proxy * assumptions.raw_order_fee) / max(annual_holding, 1))
    cash_factor = 0.70 if derived.cash_buffer_adequacy < 1 else 1.0
    stable_factor = 1.15 if derived.current_regime == "Harvest" else 1.0
    roq = max(50, round(eoq * cash_factor * stable_factor))

    rationale = "ROP covers lead time demand plus an operational stress buffer. ROQ uses EOQ logic, reduced when cash is tight and lifted slightly when the system is stable."
    return rop, roq, rationale


def recommend_standard_controls(state: DailyState, derived: DerivedState, assumptions: GameAssumptions) -> Dict[str, float | int | str]:
    target_std = derived.expected_standard_units_per_day

    throttle = 0.0
    if derived.cus_congestion_score > 0.55:
        throttle += 0.20
    if derived.raw_coverage_days < assumptions.raw_lead_time_days + 1:
        throttle += 0.20
    if derived.s1_pressure > 1.15:
        throttle += 0.10
    if derived.current_regime == "Endgame":
        throttle += 0.10
    if derived.current_regime == "Harvest" and derived.cus_congestion_score < 0.30 and derived.raw_coverage_days > assumptions.raw_lead_time_days + 2:
        throttle -= 0.05

    target_std = max(8.0, target_std * (1 - throttle))

    candidate_patterns = []
    for freq in [1, 2, 3, 4, 5]:
        size = max(10, round(target_std * freq))
        burst_penalty = size / 250
        mismatch_penalty = abs((size / freq) - target_std)
        score = mismatch_penalty + burst_penalty
        candidate_patterns.append((score, freq, size))
    _, order_frequency, order_size = min(candidate_patterns, key=lambda x: x[0])

    price = state.std_market_price
    if derived.cus_congestion_score > 0.55 or derived.raw_coverage_days < assumptions.raw_lead_time_days:
        price += 15
    elif derived.s1_pressure > 1.10:
        price += 10
    elif derived.current_regime == "Harvest" and derived.cus_congestion_score < 0.25 and derived.raw_coverage_days > assumptions.raw_lead_time_days + 3:
        price -= 5
    price = max(50.0, round(price, 2))

    s1_alloc = 50.0
    if derived.cus_service_risk_score > 0.60:
        s1_alloc -= 10
    elif derived.cus_service_risk_score > 0.45:
        s1_alloc -= 5
    elif derived.current_regime == "Harvest" and derived.std_demand_delivery_gap > 0:
        s1_alloc += 5
    s1_alloc = clamp(s1_alloc, 25, 75)

    initial_batch = max(25, round(max(order_size, target_std * 2) / 5) * 5)
    if derived.raw_coverage_days < assumptions.raw_lead_time_days + 1 or derived.std_q2 > state.std_initial_batch_output:
        initial_batch = max(20, initial_batch - 10)
    if derived.current_regime == "Harvest" and derived.std_batching_mismatch_score < target_std:
        initial_batch = min(initial_batch + 10, 250)

    final_batch = max(20, round(max(target_std * 1.5, 20) / 5) * 5)
    if state.std_q5 > state.std_deliveries * 2:
        final_batch -= 5
    final_batch = int(clamp(final_batch, 20, 200))

    shifts = 2.0
    if derived.manual_pressure > 1.15:
        shifts = 3.0
    elif derived.current_regime == "Harvest" and derived.manual_pressure < 0.90:
        shifts = 2.0

    rationale = (
        "Standard settings use product price as the main throttle. Price is increased when custom congestion, raw stress, or S1 pressure are high. "
        "Order size/frequency are chosen to hit the target average demand with limited burstiness. S1 allocation is reduced when custom service needs protection."
    )

    return {
        "standard_order_frequency": int(order_frequency),
        "standard_order_size": int(order_size),
        "standard_s1_allocation_pct": round(s1_alloc, 1),
        "initial_batch_size": int(initial_batch),
        "manual_workday_length_in_shifts": float(shifts),
        "final_batch_size": int(final_batch),
        "standard_product_price": float(price),
        "rationale": rationale,
    }


def recommend_custom_flow(state: DailyState, derived: DerivedState) -> Tuple[float, str]:
    first_pass_alloc = 75.0
    if state.cus_q2_second > state.cus_q2_first * 1.15:
        first_pass_alloc -= 10
    elif state.cus_q2_first > state.cus_q2_second * 1.15:
        first_pass_alloc += 10
    elif derived.cus_s2_imbalance_score > 0.20:
        first_pass_alloc += -5 if state.cus_q2_second > state.cus_q2_first else 5
    first_pass_alloc = clamp(first_pass_alloc, 45, 85)
    rationale = "S2 first-pass allocation is shifted toward the queue that needs relief, because S2 is a double-pass station and balance matters more than raw first-pass throughput."
    return round(first_pass_alloc, 1), rationale


def recommend_capacity(state: DailyState, derived: DerivedState, forecast: ForecastState, assumptions: GameAssumptions) -> Tuple[int, int, int, str]:
    desired_s1 = int(state.std_s1_machines)
    desired_s2 = int(state.cus_s2_machines)
    desired_s3 = int(state.cus_s3_machines)

    if derived.current_regime != "Endgame":
        if derived.current_bottleneck == "Shared S1" and derived.s1_pressure > 1.20 and derived.cash_buffer_adequacy > 0.8:
            desired_s1 += 1
        if derived.current_bottleneck == "Custom S2" and derived.s2_pressure > 1.15 and derived.cash_buffer_adequacy > 0.8:
            desired_s2 += 1
        if derived.current_bottleneck == "Custom S3" and derived.s3_pressure > 1.15 and derived.cash_buffer_adequacy > 0.8:
            desired_s3 += 1
        if forecast.projected_custom_wip_peak > assumptions.custom_wip_limit * 0.85 and derived.cash_buffer_adequacy > 1.0:
            desired_s2 = max(desired_s2, int(state.cus_s2_machines) + 1)
    rationale = "Machine additions are only recommended when bottleneck evidence is strong and cash can still protect inventory and payroll. Endgame suppresses late capacity expansion unless the case is exceptional."
    return desired_s1, desired_s2, desired_s3, rationale


def recommend_workforce(state: DailyState, derived: DerivedState, assumptions: GameAssumptions) -> Tuple[int, str]:
    effective_workers = state.experts + assumptions.rookie_productivity_ratio * state.rookies
    desired = int(round(state.experts + state.rookies))
    if derived.manual_pressure > 1.10 and derived.days_remaining > assumptions.rookie_to_expert_days:
        desired += 2
    elif derived.manual_pressure > 1.0 and derived.days_remaining > assumptions.rookie_to_expert_days:
        desired += 1
    rationale = "Desired employees is treated as a long-lead decision. Hiring only increases when manual pressure is elevated and there is enough time for rookies to become productive before the run ends."
    return desired, rationale


def recommend_finance(state: DailyState, derived: DerivedState, assumptions: GameAssumptions, capex_cost: float) -> Tuple[float, float, str]:
    get_loan = 0.0
    pay_loan = 0.0

    target_buffer = assumptions.min_cash_buffer_days * max(1.0, derived.salary_burden + derived.daily_holding_cost_proxy + assumptions.raw_order_fee / assumptions.raw_lead_time_days)
    needed = max(0.0, target_buffer + capex_cost - state.cash_on_hand)

    if needed > 0 and derived.loan_urgency_score > 0.35:
        get_loan = round(needed * 1.15, 2)
    elif state.debt > 0 and state.cash_on_hand > target_buffer * 1.8 and derived.current_regime in {"Harvest", "Endgame"}:
        pay_loan = round(min(state.debt, (state.cash_on_hand - target_buffer * 1.5)), 2)

    rationale = "Loans are used to prevent operational disruption or fund high-value bottleneck relief. Debt repayment is recommended only when cash remains comfortably above the operating buffer."
    return get_loan, pay_loan, rationale


def _candidate_score(derived: DerivedState, rec: RecommendationPackage, forecast: ForecastState, assumptions: GameAssumptions) -> Dict[str, float]:
    raw_safety = clamp(rec.inventory_rop / max(derived.expected_parts_per_day * assumptions.raw_lead_time_days, 1), 0, 2) / 2
    custom_protection = clamp(1 - derived.cus_service_risk_score + (0.1 if rec.s2_allocation_to_first_pass_pct < 75 and derived.cus_q2_second > derived.cus_q2_first else 0), 0, 1)
    queue_stability = clamp(1 - derived.system_stress_score + 0.1 * (1 if rec.standard_order_frequency >= 2 else 0), 0, 1)
    cash_safety = clamp(min(forecast.projected_cash_min, rec.get_loan + forecast.projected_cash_min + 1) / max(state_like_cash_floor := 10000.0, 1), 0, 1)
    efficiency = clamp(1 - min(rec.manual_workday_length_in_shifts - 2.0, 1.0) * 0.20 - (1 if rec.get_loan > 0 else 0) * 0.10, 0, 1)
    endgame = derived.endgame_robustness_score
    total = 0.30 * raw_safety + 0.25 * custom_protection + 0.20 * queue_stability + 0.15 * cash_safety + 0.05 * efficiency + 0.05 * endgame
    return {
        "raw_safety": round(raw_safety, 3),
        "custom_protection": round(custom_protection, 3),
        "queue_stability": round(queue_stability, 3),
        "cash_safety": round(cash_safety, 3),
        "efficiency": round(efficiency, 3),
        "endgame_robustness": round(endgame, 3),
        "total": round(total, 3),
    }


def build_recommendation(state: DailyState, derived: DerivedState, assumptions: GameAssumptions) -> RecommendationPackage:
    forecast = forecast_short_term(state, derived, assumptions)
    rop, roq, inv_reason = recommend_inventory(state, derived, assumptions)
    std = recommend_standard_controls(state, derived, assumptions)
    s2_alloc, s2_reason = recommend_custom_flow(state, derived)
    desired_s1, desired_s2, desired_s3, cap_reason = recommend_capacity(state, derived, forecast, assumptions)
    desired_employees, wf_reason = recommend_workforce(state, derived, assumptions)

    capex_cost = max(0, desired_s1 - int(state.std_s1_machines)) * assumptions.machine_buy_cost_s1 + max(0, desired_s2 - int(state.cus_s2_machines)) * assumptions.machine_buy_cost_s2 + max(0, desired_s3 - int(state.cus_s3_machines)) * assumptions.machine_buy_cost_s3
    get_loan, pay_loan, fin_reason = recommend_finance(state, derived, assumptions, capex_cost)

    queue_warning = forecast.projected_queue_growth_warning
    cash_warning = "Cash buffer is thin under the current policy." if derived.cash_buffer_adequacy < 1.0 else "Cash buffer is acceptable."

    package = RecommendationPackage(
        day=state.day,
        current_bottleneck=derived.current_bottleneck,
        current_regime=derived.current_regime,
        raw_coverage_days=round(derived.raw_coverage_days, 2),
        custom_congestion_score=round(derived.cus_congestion_score, 3),
        queue_imbalance_warning=queue_warning,
        cash_risk_warning=cash_warning,
        standard_order_frequency=int(std["standard_order_frequency"]),
        standard_order_size=int(std["standard_order_size"]),
        standard_s1_allocation_pct=float(std["standard_s1_allocation_pct"]),
        desired_s1_machines=int(desired_s1),
        initial_batch_size=int(std["initial_batch_size"]),
        manual_workday_length_in_shifts=float(std["manual_workday_length_in_shifts"]),
        final_batch_size=int(std["final_batch_size"]),
        standard_product_price=float(std["standard_product_price"]),
        s2_allocation_to_first_pass_pct=float(s2_alloc),
        desired_s2_machines=int(desired_s2),
        desired_s3_machines=int(desired_s3),
        inventory_rop=int(rop),
        inventory_roq=int(roq),
        get_loan=float(get_loan),
        pay_loan=float(pay_loan),
        desired_employees=int(desired_employees),
        rationale={
            "inventory": inv_reason,
            "standard_controls": str(std["rationale"]),
            "custom_flow": s2_reason,
            "capacity": cap_reason,
            "workforce": wf_reason,
            "finance": fin_reason,
        },
        assumptions_used={
            "raw_lead_time_days": assumptions.raw_lead_time_days,
            "custom_wip_limit": assumptions.custom_wip_limit,
            "rookie_to_expert_days": assumptions.rookie_to_expert_days,
        },
    )
    package.scores = _candidate_score(derived, package, forecast, assumptions)
    return package
