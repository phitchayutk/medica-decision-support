from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import pandas as pd

from core.data_loader import load_game_data


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b not in (0, 0.0) else default


def to_float(x, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def pick_col(df: pd.DataFrame, aliases):
    if df is None or df.empty:
        return None
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        if a in df.columns:
            return a
    for a in aliases:
        key = str(a).strip().lower()
        if key in lower_map:
            return lower_map[key]
    return None


def get_val(row: pd.Series, df: pd.DataFrame, aliases, default: float = 0.0) -> float:
    c = pick_col(df, aliases)
    if c is None:
        return default
    return to_float(row.get(c, default), default)


@dataclass
class InventoryState:
    inventory_level: float
    dispatches: float


@dataclass
class StandardState:
    accepted_orders: float
    accumulated_orders: float
    q1: float
    s1_output: float
    q_before_batch: float
    initial_batch_output: float
    q3: float
    manual_output: float
    q_manual: float
    final_batch_output: float
    fg_inventory: float
    deliveries: float
    market_price: float
    s1_machines: int


@dataclass
class CustomState:
    accepted_orders: float
    accumulated_orders: float
    q1: float
    s1_output: float
    q2_first: float
    s2_first_output: float
    q3: float
    s3_output: float
    q2_second: float
    deliveries: float
    demand: float
    s2_machines: int
    s3_machines: int
    actual_price: float
    average_lead_time: float


@dataclass
class WorkforceState:
    rookies: int
    experts: int


@dataclass
class FinancialState:
    cash_on_hand: float
    debt: float
    inventory_costs_to_date: float
    commission_interest_costs_to_date: float
    machines_bought_to_date: float
    salaries_to_date: float
    standard_ordering_costs_to_date: float
    interest_earned_to_date: float
    sales_custom_to_date: float
    sales_standard_to_date: float
    machines_sold_to_date: float
    raw_holding_costs_to_date: float
    custom_queue_holding_costs_to_date: float
    standard_queue_holding_costs_to_date: float


@dataclass
class PlantState:
    day: int
    inventory: InventoryState
    standard: StandardState
    custom: CustomState
    workforce: WorkforceState
    finance: FinancialState


@dataclass
class DerivedState:
    raw_coverage_days: float
    expected_parts_per_day: float
    std_avg_demand_per_day: float
    custom_avg_demand_per_day: float

    s1_utilization: float
    s2_utilization: float
    s3_utilization: float
    manual_utilization: float

    std_batching_mismatch_score: float
    custom_congestion_score: float
    stress_score: float
    endgame_robustness: float

    bottleneck: str
    current_regime: str

    std_q2: float
    custom_total_wip: float


def _latest_row(df: pd.DataFrame):
    if df is None or df.empty:
        return pd.Series(dtype=object)
    return df.sort_values("Day").iloc[-1]


def build_derived_state(file_obj, assumptions) -> Tuple[PlantState, DerivedState, Dict[str, pd.DataFrame]]:
    raw = load_game_data(file_obj)

    std_df = raw["Standard"]
    cus_df = raw["Custom"]
    inv_df = raw["Inventory"]
    fin_df = raw["Financial"]
    wf_df = raw["WorkForce"]

    std = _latest_row(std_df)
    cus = _latest_row(cus_df)
    inv = _latest_row(inv_df)
    fin = _latest_row(fin_df)
    wf = _latest_row(wf_df)

    day = int(
        max(
            to_float(std.get("Day", 0)),
            to_float(cus.get("Day", 0)),
            to_float(inv.get("Day", 0)),
            to_float(fin.get("Day", 0)),
            to_float(wf.get("Day", 0)),
        )
    )

    state = PlantState(
        day=day,
        inventory=InventoryState(
            inventory_level=get_val(inv, inv_df, ["Inventory-Level"], 0.0),
            dispatches=get_val(inv, inv_df, ["Inventory-Dispatches"], 0.0),
        ),
        standard=StandardState(
            accepted_orders=get_val(std, std_df, ["Standard Orders-Accepted Orders"], 0.0),
            accumulated_orders=get_val(std, std_df, ["Standard Orders-Accumulated Orders"], 0.0),
            q1=get_val(std, std_df, ["Standard Queue 1-Level"], 0.0),
            s1_output=get_val(std, std_df, ["Standard Station 1-Output"], 0.0),
            q_before_batch=get_val(std, std_df, ["Standard Queue 2-Level"], 0.0),
            initial_batch_output=get_val(std, std_df, ["Standard Initial Batching-Output"], 0.0),
            q3=get_val(std, std_df, ["Standard Queue 3-Level"], 0.0),
            manual_output=get_val(std, std_df, ["Standard Manual Processing-Output"], 0.0),
            q_manual=get_val(std, std_df, ["Standard Queue 4-Level"], 0.0),
            final_batch_output=get_val(std, std_df, ["Standard Final Batching-Output"], 0.0),
            fg_inventory=get_val(std, std_df, ["Standard Queue 5-Level"], 0.0),
            deliveries=get_val(std, std_df, ["Standard Deliveries-Deliveries"], 0.0),
            market_price=get_val(std, std_df, ["Standard Deliveries-Market Price"], 0.0),
            s1_machines=int(get_val(std, std_df, ["Standard Station 1-Number of Machines"], 1.0)),
        ),
        custom=CustomState(
            accepted_orders=get_val(cus, cus_df, ["Custom Orders-Accepted Orders"], 0.0),
            accumulated_orders=get_val(cus, cus_df, ["Custom Orders-Accumulated Orders"], 0.0),
            q1=get_val(cus, cus_df, ["Custom Queue 1-Level"], 0.0),
            s1_output=get_val(cus, cus_df, ["Custom Station 1-Output"], 0.0),
            q2_first=get_val(cus, cus_df, ["Custom Queue 2-Level First Pass"], 0.0),
            s2_first_output=get_val(cus, cus_df, ["Custom Station 2-Output First Pass"], 0.0),
            q3=get_val(cus, cus_df, ["Custom Queue 3-Level"], 0.0),
            s3_output=get_val(cus, cus_df, ["Custom Station 3-Output"], 0.0),
            q2_second=get_val(cus, cus_df, ["Custom Queue 2-Level Second Pass"], 0.0),
            deliveries=get_val(cus, cus_df, ["Custom Deliveries-Deliveries"], 0.0),
            demand=get_val(cus, cus_df, ["Custom Orders-Demand"], 0.0),
            s2_machines=int(get_val(cus, cus_df, ["Custom Station 2-Number of Machines"], 1.0)),
            s3_machines=int(get_val(cus, cus_df, ["Custom Station 3-Number of Machines"], 1.0)),
            actual_price=get_val(cus, cus_df, ["Custom Deliveries-Actual Price"], 0.0),
            average_lead_time=get_val(cus, cus_df, ["Custom Deliveries-Average Lead Time"], 0.0),
        ),
        workforce=WorkforceState(
            rookies=int(get_val(wf, wf_df, ["WorkForce-Rookies"], 0.0)),
            experts=int(get_val(wf, wf_df, ["WorkForce-Experts"], 12.0)),
        ),
        finance=FinancialState(
            cash_on_hand=get_val(fin, fin_df, ["Finance-Cash On Hand"], 0.0),
            debt=get_val(fin, fin_df, ["Finance-Debt"], 0.0),
            inventory_costs_to_date=get_val(fin, fin_df, ["Finance-Inventory Costs *To Date"], 0.0),
            commission_interest_costs_to_date=get_val(fin, fin_df, ["Finance-Commission + Interest Costs *To Date"], 0.0),
            machines_bought_to_date=get_val(fin, fin_df, ["Finance-Machines Bought *To Date"], 0.0),
            salaries_to_date=get_val(fin, fin_df, ["Finance-Salaries *To Date"], 0.0),
            standard_ordering_costs_to_date=get_val(fin, fin_df, ["Finance-Standard Ordering Costs *To Date"], 0.0),
            interest_earned_to_date=get_val(fin, fin_df, ["Finance-Interest Earned *To Date"], 0.0),
            sales_custom_to_date=get_val(fin, fin_df, ["Finance-Sales Custom *To Date"], 0.0),
            sales_standard_to_date=get_val(fin, fin_df, ["Finance-Sales Standard *To Date"], 0.0),
            machines_sold_to_date=get_val(fin, fin_df, ["Finance-Machines Sold *To Date"], 0.0),
            raw_holding_costs_to_date=get_val(fin, fin_df, ["Finance-Raw Inventory Holding Costs *To Date"], 0.0),
            custom_queue_holding_costs_to_date=get_val(fin, fin_df, ["Finance-Custom Queues Holding Costs *To Date"], 0.0),
            standard_queue_holding_costs_to_date=get_val(fin, fin_df, ["Finance-Standard Queues Holding Costs *To Date"], 0.0),
        ),
    )

    std_avg_demand_per_day = max(state.standard.accepted_orders, 1.0)
    custom_avg_demand_per_day = max(state.custom.demand, 1.0)
    expected_parts_per_day = (
        std_avg_demand_per_day * assumptions.standard_parts_per_unit
        + custom_avg_demand_per_day * assumptions.custom_parts_per_unit
    )
    raw_coverage_days = safe_div(state.inventory.inventory_level, expected_parts_per_day, 0.0)

    s1_total_output = state.standard.s1_output + state.custom.s1_output
    s1_capacity = max(s1_total_output, 1.0)
    s1_utilization = safe_div(s1_total_output, s1_capacity, 0.0)

    s2_capacity = max(state.custom.s2_first_output, 1.0)
    s2_utilization = safe_div(state.custom.s2_first_output, s2_capacity, 0.0)

    s3_capacity = max(state.custom.s3_output, 1.0)
    s3_utilization = safe_div(state.custom.s3_output, s3_capacity, 0.0)

    effective_manual_capacity = max(
        state.workforce.experts + state.workforce.rookies * assumptions.rookie_productivity,
        1.0,
    )
    manual_utilization = safe_div(state.standard.manual_output, effective_manual_capacity, 0.0)

    std_batching_mismatch_score = abs(state.standard.q_before_batch - state.standard.initial_batch_output)

    custom_total_wip = state.custom.q1 + state.custom.q2_first + state.custom.q2_second + state.custom.q3
    custom_congestion_score = min(
        1.0,
        0.45 * safe_div(custom_total_wip, assumptions.custom_wip_limit, 0.0)
        + 0.35 * safe_div(state.custom.average_lead_time, 20.0, 0.0)
        + 0.20 * safe_div(max(state.custom.demand - state.custom.deliveries, 0.0), max(state.custom.demand, 1.0), 0.0),
    )

    stress_score = min(
        1.0,
        (
            min(1.0, max(0.0, (assumptions.raw_lead_time_days + 1 - raw_coverage_days) / 5.0))
            + custom_congestion_score
            + min(1.0, max(s1_utilization, s2_utilization, s3_utilization, manual_utilization))
        )
        / 3.0,
    )

    if custom_congestion_score > 0.80 or raw_coverage_days < assumptions.raw_lead_time_days:
        regime = "Recovery"
    elif stress_score > 0.50:
        regime = "Stabilize"
    elif stress_score < 0.30 and custom_congestion_score < 0.40:
        regime = "Harvest"
    else:
        regime = "Endgame"

    if state.custom.q2_second > state.custom.q2_first * 1.10:
        bottleneck = "Custom S2 Second Pass"
    elif state.custom.q2_first > state.custom.q1 * 1.10:
        bottleneck = "Custom S2 First Pass"
    elif state.custom.q3 > max(state.custom.s3_output, 1.0) * 2:
        bottleneck = "Custom S3"
    elif state.standard.q_before_batch > max(state.standard.initial_batch_output, 1.0) * 2:
        bottleneck = "Standard Initial Batching"
    elif state.standard.q_manual > max(state.standard.manual_output, 1.0) * 2:
        bottleneck = "Standard Manual"
    else:
        bottleneck = "Shared S1"

    endgame_robustness = max(
        0.0,
        min(
            1.0,
            0.40 * min(1.0, raw_coverage_days / 5.0)
            + 0.35 * (1.0 - custom_congestion_score)
            + 0.25 * (1.0 - stress_score),
        ),
    )

    derived = DerivedState(
        raw_coverage_days=raw_coverage_days,
        expected_parts_per_day=expected_parts_per_day,
        std_avg_demand_per_day=std_avg_demand_per_day,
        custom_avg_demand_per_day=custom_avg_demand_per_day,
        s1_utilization=s1_utilization,
        s2_utilization=s2_utilization,
        s3_utilization=s3_utilization,
        manual_utilization=manual_utilization,
        std_batching_mismatch_score=std_batching_mismatch_score,
        custom_congestion_score=custom_congestion_score,
        stress_score=stress_score,
        endgame_robustness=endgame_robustness,
        bottleneck=bottleneck,
        current_regime=regime,
        std_q2=state.standard.q_before_batch,
        custom_total_wip=custom_total_wip,
    )

    return state, derived, raw