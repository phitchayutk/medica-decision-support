from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Tuple

import pandas as pd

from .schemas import DailyState
from .utils import nz


STANDARD_COLUMN_MAP = {
    "Day": "day",
    "Standard Orders-Accepted Orders": "std_accepted_orders",
    "Standard Orders-Accumulated Orders": "std_accumulated_orders",
    "Standard Queue 1-Level": "std_q1",
    "Standard Station 1-Output": "std_s1_output",
    "Standard Queue 2-Level": "std_q2",
    "Standard Initial Batching-Output": "std_initial_batch_output",
    "Standard Queue 3-Level": "std_q3",
    "Standard Manual Processing-Output": "std_manual_output",
    "Standard Queue 4-Level": "std_q4",
    "Standard Final Batching-Output": "std_final_batch_output",
    "Standard Queue 5-Level": "std_q5",
    "Standard Deliveries-Deliveries": "std_deliveries",
    "Standard Station 1-Number of Machines": "std_s1_machines",
    "Standard Manual Processing-Effective Work Load (%)": "std_manual_workload_pct",
    "Standard Deliveries-Market Price": "std_market_price",
}

CUSTOM_COLUMN_MAP = {
    "Day": "day",
    "Custom Orders-Accepted Orders": "cus_accepted_orders",
    "Custom Orders-Accumulated Orders": "cus_accumulated_orders",
    "Custom Queue 1-Level": "cus_q1",
    "Custom Station 1-Output": "cus_s1_output",
    "Custom Queue 2-Level First Pass": "cus_q2_first",
    "Custom Station 2-Output First Pass": "cus_s2_first_output",
    "Custom Queue 3-Level": "cus_q3",
    "Custom Station 3-Output": "cus_s3_output",
    "Custom Queue 2-Level Second Pass": "cus_q2_second",
    "Custom Deliveries-Deliveries": "cus_deliveries",
    "Custom Orders-Demand": "cus_demand",
    "Custom Station 2-Number of Machines": "cus_s2_machines",
    "Custom Station 3-Number of Machines": "cus_s3_machines",
    "Custom Deliveries-Actual Price": "cus_actual_price",
    "Custom Deliveries-Average Lead Time": "cus_avg_lead_time",
}

INVENTORY_COLUMN_MAP = {
    "Day": "day",
    "Inventory-Dispatches": "inventory_dispatches",
    "Inventory-Level": "inventory_level",
}

FINANCIAL_COLUMN_MAP = {
    "Day": "day",
    "Finance-Cash On Hand": "cash_on_hand",
    "Finance-Debt": "debt",
    "Finance-Inventory Costs *To Date": "inventory_costs_to_date",
    "Finance-Commission + Interest Costs *To Date": "commission_interest_costs_to_date",
    "Finance-Machines Bought *To Date": "machines_bought_to_date",
    "Finance-Salaries *To Date": "salaries_to_date",
    "Finance-Standard Ordering Costs *To Date": "std_ordering_costs_to_date",
    "Finance-Interest Earned *To Date": "interest_earned_to_date",
    "Finance-Sales Custom *To Date": "sales_custom_to_date",
    "Finance-Sales Standard *To Date": "sales_standard_to_date",
    "Finance-Machines Sold *To Date": "machines_sold_to_date",
    "Finance-Raw Inventory Holding Costs *To Date": "raw_holding_costs_to_date",
    "Finance-Custom Queues Holding Costs *To Date": "custom_queue_holding_costs_to_date",
    "Finance-Standard Queues Holding Costs *To Date": "standard_queue_holding_costs_to_date",
}

WORKFORCE_COLUMN_MAP = {
    "Day": "day",
    "WorkForce-Rookies": "rookies",
    "WorkForce-Experts": "experts",
}

REQUIRED_SHEETS = ["Standard", "Custom", "Inventory", "Financial", "WorkForce"]


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed:")]
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _select_and_rename(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    missing = [col for col in mapping if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    out = df[list(mapping.keys())].rename(columns=mapping)
    return out


def load_game_data(file) -> Tuple[List[DailyState], Dict[str, pd.DataFrame], List[str]]:
    xls = pd.ExcelFile(file)
    warnings: List[str] = []
    missing_sheets = [s for s in REQUIRED_SHEETS if s not in xls.sheet_names]
    if missing_sheets:
        raise ValueError(f"Missing required sheets: {missing_sheets}")

    raw_tables: Dict[str, pd.DataFrame] = {}
    normalized: Dict[str, pd.DataFrame] = {}

    for sheet, mapping in [
        ("Standard", STANDARD_COLUMN_MAP),
        ("Custom", CUSTOM_COLUMN_MAP),
        ("Inventory", INVENTORY_COLUMN_MAP),
        ("Financial", FINANCIAL_COLUMN_MAP),
        ("WorkForce", WORKFORCE_COLUMN_MAP),
    ]:
        df = pd.read_excel(file, sheet_name=sheet)
        raw_tables[sheet] = df.copy()
        df = _clean_columns(df)
        normalized[sheet] = _select_and_rename(df, mapping)

    merged = normalized["Standard"]
    for key in ["Custom", "Inventory", "Financial", "WorkForce"]:
        merged = merged.merge(normalized[key], on="day", how="outer", suffixes=(None, None))

    merged = merged.sort_values("day").reset_index(drop=True)
    merged = merged.fillna(0)

    states: List[DailyState] = []
    for row in merged.to_dict(orient="records"):
        safe_row = {k: nz(v) for k, v in row.items()}
        safe_row["day"] = int(safe_row["day"])
        states.append(DailyState(**safe_row))

    return states, raw_tables, warnings
