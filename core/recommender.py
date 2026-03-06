from dataclasses import dataclass


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b not in (0, 0.0) else default


@dataclass
class Recommendation:
    standard_order_frequency: int
    standard_order_size: int
    standard_s1_allocation_pct: int
    desired_s1_machines: int
    initial_batch_size: int
    manual_workday_length_shifts: int
    final_batch_size: int
    standard_product_price: float
    s2_allocation_first_pass_pct: int
    desired_s2_machines: int
    desired_s3_machines: int
    inventory_rop: int
    inventory_roq: int
    get_loan: int
    pay_loan: int
    desired_employees: int


def _recommend_standard_controls(state, derived, assumptions):
    target_std = max(8.0, derived.std_avg_demand_per_day)

    if derived.custom_congestion_score > 0.75 or derived.raw_coverage_days < assumptions.raw_lead_time_days:
        target_std *= 0.70
    elif derived.stress_score > 0.50:
        target_std *= 0.85
    elif derived.current_regime == "Harvest":
        target_std *= 1.10

    order_frequency = 2
    order_size = int(round(target_std * order_frequency))

    std_price = state.standard.market_price
    if std_price <= 0:
        std_price = 400.0

    if derived.custom_congestion_score > 0.80:
        std_price *= 1.05
    elif derived.stress_score > 0.55:
        std_price *= 1.03
    elif derived.current_regime == "Harvest":
        std_price *= 0.995

    s1_alloc = 50
    if derived.custom_congestion_score > 0.80:
        s1_alloc = 40
    elif derived.custom_congestion_score > 0.60:
        s1_alloc = 45
    elif derived.current_regime == "Harvest":
        s1_alloc = 55
    s1_alloc = int(clamp(s1_alloc, 25, 75))

    initial_batch = max(25, round(max(order_size, target_std * 2) / 5) * 5)
    if (
        derived.raw_coverage_days < assumptions.raw_lead_time_days + 1
        or state.standard.q_before_batch > state.standard.initial_batch_output
    ):
        initial_batch = max(20, initial_batch - 10)

    if derived.current_regime == "Harvest" and derived.std_batching_mismatch_score < target_std:
        initial_batch = min(initial_batch + 10, 250)

    final_batch = max(20, round(max(target_std * 1.5, 20) / 5) * 5)
    if state.standard.fg_inventory > state.standard.deliveries * 2:
        final_batch -= 5
    final_batch = int(clamp(final_batch, 20, 200))

    manual_shifts = 2
    if derived.manual_utilization > 0.90 or state.standard.q_manual > state.standard.manual_output * 2:
        manual_shifts = 3
    elif derived.current_regime == "Harvest":
        manual_shifts = 2

    return {
        "order_frequency": int(order_frequency),
        "order_size": int(max(5, order_size)),
        "s1_alloc": int(s1_alloc),
        "initial_batch": int(initial_batch),
        "manual_shifts": int(manual_shifts),
        "final_batch": int(final_batch),
        "std_price": round(std_price, 2),
    }


def _recommend_custom_controls(state, derived, assumptions):
    s2_first = 50

    if state.custom.q2_second > state.custom.q2_first * 1.10:
        s2_first = 40
    elif state.custom.q2_first > state.custom.q2_second * 1.10:
        s2_first = 60
    elif derived.current_regime == "Recovery":
        s2_first = 55

    s2_first = int(clamp(s2_first, 15, 85))

    desired_s2 = state.custom.s2_machines
    desired_s3 = state.custom.s3_machines
    desired_s1 = state.standard.s1_machines

    if derived.bottleneck == "Shared S1" and derived.stress_score > 0.55:
        desired_s1 += 1

    if derived.bottleneck in ("Custom S2 First Pass", "Custom S2 Second Pass") and derived.custom_congestion_score > 0.60:
        desired_s2 += 1

    if derived.bottleneck == "Custom S3" and derived.custom_congestion_score > 0.60:
        desired_s3 += 1

    return {
        "s2_first": desired_s2 if False else s2_first,
        "desired_s1": int(desired_s1),
        "desired_s2": int(desired_s2),
        "desired_s3": int(desired_s3),
    }


def _recommend_inventory(state, derived, assumptions):
    base_rop = derived.expected_parts_per_day * assumptions.raw_lead_time_days

    if derived.custom_congestion_score > 0.75:
        base_rop *= 1.15
    elif derived.stress_score > 0.50:
        base_rop *= 1.08

    inventory_rop = int(round(base_rop))

    d = max(derived.expected_parts_per_day, 1.0)
    s = assumptions.raw_order_fee
    h = assumptions.raw_holding_cost_per_unit_day
    eoq = (2 * d * s / h) ** 0.5

    inventory_roq = int(round(eoq))
    inventory_roq = max(100, min(inventory_roq, 1000))

    return inventory_rop, inventory_roq


def _recommend_finance(state, derived, assumptions, rec):
    get_loan = 0
    pay_loan = 0

    operating_buffer = (
        assumptions.raw_order_fee
        + max(rec.inventory_roq * assumptions.raw_cost_per_part * 0.25, 0)
        + (state.workforce.experts * assumptions.expert_salary_per_day)
        + (state.workforce.rookies * assumptions.rookie_salary_per_day)
    )

    if state.finance.cash_on_hand < operating_buffer and state.finance.debt <= 0:
        get_loan = int(max(0, round(operating_buffer - state.finance.cash_on_hand, -2)))

    if state.finance.debt > 0 and state.finance.cash_on_hand > operating_buffer * 1.5:
        pay_loan = int(min(state.finance.debt, round((state.finance.cash_on_hand - operating_buffer), -2)))

    return get_loan, pay_loan


def _recommend_workforce(state, derived, assumptions):
    desired = state.workforce.experts + state.workforce.rookies

    if derived.manual_utilization > 0.90 and derived.current_regime in ("Recovery", "Stabilize"):
        desired += 1

    if derived.current_regime == "Harvest" and derived.manual_utilization < 0.65:
        desired = max(12, desired)

    return int(desired)


def build_recommendation(state, derived, assumptions) -> Recommendation:
    std = _recommend_standard_controls(state, derived, assumptions)
    cus = _recommend_custom_controls(state, derived, assumptions)
    inventory_rop, inventory_roq = _recommend_inventory(state, derived, assumptions)

    rec = Recommendation(
        standard_order_frequency=std["order_frequency"],
        standard_order_size=std["order_size"],
        standard_s1_allocation_pct=std["s1_alloc"],
        desired_s1_machines=cus["desired_s1"],
        initial_batch_size=std["initial_batch"],
        manual_workday_length_shifts=std["manual_shifts"],
        final_batch_size=std["final_batch"],
        standard_product_price=std["std_price"],
        s2_allocation_first_pass_pct=cus["s2_first"],
        desired_s2_machines=cus["desired_s2"],
        desired_s3_machines=cus["desired_s3"],
        inventory_rop=inventory_rop,
        inventory_roq=inventory_roq,
        get_loan=0,
        pay_loan=0,
        desired_employees=_recommend_workforce(state, derived, assumptions),
    )

    get_loan, pay_loan = _recommend_finance(state, derived, assumptions, rec)
    rec.get_loan = get_loan
    rec.pay_loan = pay_loan

    return rec