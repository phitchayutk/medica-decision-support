from __future__ import annotations

from typing import List, Optional

from .config import GameAssumptions
from .schemas import DailyState, DerivedState
from .utils import clamp, nz, rolling_mean, safe_div


def _diff(current: float, previous: float) -> float:
    return nz(current) - nz(previous)


def _compute_raw_on_order(states: List[DailyState], idx: int, lead_time: int) -> float:
    start = max(0, idx - lead_time + 1)
    pending = sum(nz(states[i].inventory_dispatches) for i in range(start, idx + 1))
    return pending


def _next_stockout_day(on_hand: float, parts_per_day: float, current_day: int) -> Optional[float]:
    if parts_per_day <= 0:
        return None
    coverage = on_hand / parts_per_day
    if coverage < 0:
        coverage = 0
    return current_day + coverage


def build_derived_state(states: List[DailyState], idx: int, assumptions: GameAssumptions) -> DerivedState:
    if not states:
        raise ValueError("No states loaded")

    state = states[idx]
    prev = states[idx - 1] if idx > 0 else state
    last_day = max(s.day for s in states)
    days_remaining = max(0, last_day - state.day)

    expected_std = rolling_mean([s.std_deliveries or s.std_accepted_orders for s in states[max(0, idx - 4): idx + 1]], 5)
    expected_cus = rolling_mean([s.cus_deliveries or s.cus_accepted_orders for s in states[max(0, idx - 4): idx + 1]], 5)
    expected_parts = assumptions.standard_parts_per_unit * expected_std + assumptions.custom_parts_per_unit * expected_cus

    raw_on_hand = nz(state.inventory_level)
    raw_on_order = _compute_raw_on_order(states, idx, assumptions.raw_lead_time_days)
    inventory_position = raw_on_hand + raw_on_order
    raw_coverage = safe_div(inventory_position, expected_parts, 999.0)
    raw_stockout_day = _next_stockout_day(inventory_position, expected_parts, state.day)
    raw_stockout_risk = clamp((assumptions.raw_lead_time_days + 2 - raw_coverage) / (assumptions.raw_lead_time_days + 2), 0, 1)

    std_total_queue = sum([state.std_q1, state.std_q2, state.std_q3, state.std_q4, state.std_q5])
    prev_std_total_queue = sum([prev.std_q1, prev.std_q2, prev.std_q3, prev.std_q4, prev.std_q5])
    std_queue_growth = _diff(std_total_queue, prev_std_total_queue)
    std_demand_gap = nz(state.std_accepted_orders) - nz(state.std_deliveries)
    std_price_gap = nz(state.std_market_price)
    std_s1_capacity_proxy = max(1.0, nz(state.std_s1_output))
    std_resource_pressure_s1 = safe_div(state.std_q1 + state.std_accepted_orders, std_s1_capacity_proxy, 0.0)
    batch_mismatch = (
        abs(state.std_s1_output - state.std_initial_batch_output)
        + abs(state.std_initial_batch_output - state.std_manual_output)
        + abs(state.std_manual_output - state.std_final_batch_output)
        + abs(state.std_final_batch_output - state.std_deliveries)
    )
    std_ordering_pattern_score = clamp(safe_div(abs(std_demand_gap), max(expected_std, 1), 0.0), 0, 3)
    std_wip_pressure = safe_div(std_total_queue, max(expected_std * 5, 1.0), 0.0)

    cus_total_wip = state.cus_q1 + state.cus_q2_first + state.cus_q2_second + state.cus_q3
    prev_cus_total_wip = prev.cus_q1 + prev.cus_q2_first + prev.cus_q2_second + prev.cus_q3
    cus_queue_growth = _diff(cus_total_wip, prev_cus_total_wip)
    cus_wip_ratio = safe_div(cus_total_wip, assumptions.custom_wip_limit, 0.0)
    cus_demand_gap = nz(state.cus_demand) - nz(state.cus_deliveries)
    cus_lt_trend = _diff(state.cus_avg_lead_time, prev.cus_avg_lead_time)
    q2_total = state.cus_q2_first + state.cus_q2_second
    cus_s2_imbalance = safe_div(abs(state.cus_q2_first - state.cus_q2_second), max(q2_total, 1.0), 0.0)
    cus_congestion = clamp(0.45 * cus_wip_ratio + 0.25 * safe_div(max(cus_demand_gap, 0), max(expected_cus, 1), 0) + 0.20 * clamp(cus_lt_trend / 5, 0, 1) + 0.10 * cus_s2_imbalance, 0, 1)
    cus_service_risk = clamp(0.60 * cus_congestion + 0.40 * clamp(state.cus_avg_lead_time / 20, 0, 1), 0, 1)

    total_s1_load = state.std_q1 + state.cus_q1 + state.std_accepted_orders + state.cus_accepted_orders
    total_s1_out = max(1.0, state.std_s1_output + state.cus_s1_output)
    s1_pressure = safe_div(total_s1_load, total_s1_out, 0.0)
    s2_pressure = safe_div(state.cus_q2_first + state.cus_q2_second + state.cus_s2_first_output, max(state.cus_s2_first_output, 1.0), 0.0)
    s3_pressure = safe_div(state.cus_q3 + state.cus_s3_output, max(state.cus_s3_output, 1.0), 0.0)
    manual_capacity_proxy = max(1.0, state.std_manual_output)
    manual_pressure = safe_div(state.std_q3 + state.std_manual_output, manual_capacity_proxy, 0.0)
    effective_workers = state.experts + assumptions.rookie_productivity_ratio * state.rookies
    workforce_capacity_adequacy = safe_div(effective_workers, max(12.0, state.std_manual_output / 12.0), 0.0)

    daily_rev = (state.sales_custom_to_date - prev.sales_custom_to_date) + (state.sales_standard_to_date - prev.sales_standard_to_date)
    daily_holding = (state.raw_holding_costs_to_date - prev.raw_holding_costs_to_date) + (state.custom_queue_holding_costs_to_date - prev.custom_queue_holding_costs_to_date) + (state.standard_queue_holding_costs_to_date - prev.standard_queue_holding_costs_to_date)
    salary_burden = state.salaries_to_date - prev.salaries_to_date
    debt_burden = state.commission_interest_costs_to_date - prev.commission_interest_costs_to_date
    cash_buffer_need = assumptions.min_cash_buffer_days * max(1.0, salary_burden + daily_holding + assumptions.raw_order_fee / assumptions.raw_lead_time_days)
    cash_buffer_adequacy = safe_div(state.cash_on_hand, cash_buffer_need, 0.0)
    loan_urgency = clamp(0.50 * clamp((1.0 - cash_buffer_adequacy), 0, 1) + 0.30 * raw_stockout_risk + 0.20 * cus_service_risk, 0, 1)

    bottleneck_scores = {
        "Raw Inventory": raw_stockout_risk * 1.3,
        "Shared S1": clamp((s1_pressure - 1.0) / 1.5, 0, 1) + 0.2 * clamp(std_resource_pressure_s1 / 3, 0, 1),
        "Initial / Standard Flow": clamp(std_wip_pressure / 2.0, 0, 1) + 0.2 * clamp(batch_mismatch / max(expected_std, 1), 0, 1),
        "Manual Process": clamp((manual_pressure - 1.0) / 1.5, 0, 1),
        "Custom S2": clamp((s2_pressure - 1.0) / 1.5, 0, 1) + 0.3 * cus_s2_imbalance,
        "Custom S3": clamp((s3_pressure - 1.0) / 1.5, 0, 1),
        "Cash": clamp((1.0 - cash_buffer_adequacy), 0, 1) + 0.2 * clamp(state.debt / max(state.cash_on_hand, 1), 0, 1),
    }
    current_bottleneck = max(bottleneck_scores, key=bottleneck_scores.get)

    system_stress = clamp(
        0.25 * raw_stockout_risk
        + 0.25 * cus_congestion
        + 0.15 * clamp(std_queue_growth / max(expected_std, 1), 0, 1)
        + 0.15 * clamp(cus_queue_growth / max(expected_cus, 1), 0, 1)
        + 0.10 * clamp((s1_pressure - 1) / 1.5, 0, 1)
        + 0.10 * clamp((1 - cash_buffer_adequacy), 0, 1),
        0,
        1,
    )

    endgame_robustness = clamp(
        0.35 * clamp(raw_coverage / (assumptions.raw_lead_time_days + 2), 0, 1)
        + 0.25 * (1 - cus_congestion)
        + 0.20 * clamp(cash_buffer_adequacy / 2, 0, 1)
        + 0.20 * (1 - clamp((std_ordering_pattern_score + batch_mismatch / max(expected_std, 1)) / 4, 0, 1)),
        0,
        1,
    )

    if days_remaining <= assumptions.frozen_last_days:
        regime = "Endgame"
    elif raw_coverage < assumptions.raw_lead_time_days or cus_wip_ratio > 0.85 or cash_buffer_adequacy < 0.8 or system_stress > 0.7:
        regime = "Recovery"
    elif system_stress > 0.40:
        regime = "Stabilize"
    else:
        regime = "Harvest"

    warnings = []
    if raw_coverage < assumptions.raw_lead_time_days:
        warnings.append("Raw coverage is below lead time. Stockout protection is required.")
    if cus_wip_ratio > 0.85:
        warnings.append("Custom WIP is approaching the hard limit of 750.")
    if cus_s2_imbalance > 0.30:
        warnings.append("Custom S2 first/second pass queues are imbalanced.")
    if cash_buffer_adequacy < 1.0:
        warnings.append("Cash buffer is below the target operating cushion.")

    return DerivedState(
        day=state.day,
        days_remaining=days_remaining,
        raw_on_hand=raw_on_hand,
        raw_on_order=raw_on_order,
        raw_inventory_position=inventory_position,
        expected_standard_units_per_day=expected_std,
        expected_custom_units_per_day=expected_cus,
        expected_parts_per_day=expected_parts,
        raw_coverage_days=raw_coverage,
        raw_forecast_stockout_day=raw_stockout_day,
        raw_stockout_risk_score=raw_stockout_risk,
        std_total_queue=std_total_queue,
        std_wip_pressure=std_wip_pressure,
        std_demand_delivery_gap=std_demand_gap,
        std_price_market_gap=std_price_gap,
        std_resource_pressure_s1=std_resource_pressure_s1,
        std_batching_mismatch_score=batch_mismatch,
        std_ordering_pattern_score=std_ordering_pattern_score,
        cus_total_wip=cus_total_wip,
        cus_wip_ratio=cus_wip_ratio,
        cus_demand_delivery_gap=cus_demand_gap,
        cus_lead_time_trend=cus_lt_trend,
        cus_s2_imbalance_score=cus_s2_imbalance,
        cus_congestion_score=cus_congestion,
        cus_service_risk_score=cus_service_risk,
        s1_pressure=s1_pressure,
        s2_pressure=s2_pressure,
        s3_pressure=s3_pressure,
        manual_pressure=manual_pressure,
        workforce_capacity_adequacy=workforce_capacity_adequacy,
        daily_revenue_proxy=daily_rev,
        daily_holding_cost_proxy=daily_holding,
        salary_burden=salary_burden,
        debt_burden=debt_burden,
        cash_buffer_adequacy=cash_buffer_adequacy,
        loan_urgency_score=loan_urgency,
        queue_growth_rate_std=std_queue_growth,
        queue_growth_rate_cus=cus_queue_growth,
        system_stress_score=system_stress,
        endgame_robustness_score=endgame_robustness,
        current_bottleneck=current_bottleneck,
        current_regime=regime,
        warnings=warnings,
    )
