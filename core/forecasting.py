from __future__ import annotations

from .config import GameAssumptions
from .schemas import DailyState, DerivedState, ForecastState
from .utils import clamp


def forecast_short_term(state: DailyState, derived: DerivedState, assumptions: GameAssumptions) -> ForecastState:
    horizon = assumptions.forecast_horizon_days
    raw_position = derived.raw_inventory_position
    custom_wip = derived.cus_total_wip
    cash = state.cash_on_hand

    stockout_day = None
    peak_custom_wip = custom_wip
    queue_warning = "Stable"

    std_demand = derived.expected_standard_units_per_day
    cus_demand = derived.expected_custom_units_per_day

    for day in range(1, horizon + 1):
        raw_position -= derived.expected_parts_per_day
        if day % assumptions.raw_lead_time_days == 0:
            raw_position += max(derived.expected_parts_per_day * assumptions.raw_lead_time_days * 0.9, 0)
        if stockout_day is None and raw_position <= 0:
            stockout_day = day

        custom_inflow = max(state.cus_demand, cus_demand)
        custom_outflow = max(1.0, state.cus_deliveries) * (1.0 - 0.20 * derived.cus_congestion_score)
        custom_wip = max(0.0, custom_wip + custom_inflow - custom_outflow)
        peak_custom_wip = max(peak_custom_wip, custom_wip)

        cash += max(derived.daily_revenue_proxy, 0) - max(derived.salary_burden, 0) - max(derived.daily_holding_cost_proxy, 0) - max(derived.debt_burden, 0)
        if raw_position < derived.expected_parts_per_day * assumptions.raw_lead_time_days:
            cash -= assumptions.raw_order_fee

    if peak_custom_wip > assumptions.custom_wip_limit * 0.9:
        queue_warning = "Custom WIP may approach the hard cap within 15 days."
    elif derived.queue_growth_rate_std > 0 or derived.queue_growth_rate_cus > 0:
        queue_warning = "At least one queue is still growing under the current policy."

    lt_text = "Worsening" if derived.cus_lead_time_trend > 0 else "Improving / Stable"

    return ForecastState(
        horizon_days=horizon,
        raw_stockout_day=stockout_day,
        projected_custom_wip_peak=peak_custom_wip,
        projected_cash_min=cash,
        projected_custom_lt_trend=lt_text,
        projected_queue_growth_warning=queue_warning,
    )
