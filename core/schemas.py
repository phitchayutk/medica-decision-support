from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class DailyState:
    day: int

    std_accepted_orders: float = 0.0
    std_accumulated_orders: float = 0.0
    std_q1: float = 0.0
    std_s1_output: float = 0.0
    std_q2: float = 0.0
    std_initial_batch_output: float = 0.0
    std_q3: float = 0.0
    std_manual_output: float = 0.0
    std_q4: float = 0.0
    std_final_batch_output: float = 0.0
    std_q5: float = 0.0
    std_deliveries: float = 0.0
    std_s1_machines: float = 0.0
    std_manual_workload_pct: float = 0.0
    std_market_price: float = 0.0

    cus_accepted_orders: float = 0.0
    cus_accumulated_orders: float = 0.0
    cus_q1: float = 0.0
    cus_s1_output: float = 0.0
    cus_q2_first: float = 0.0
    cus_s2_first_output: float = 0.0
    cus_q3: float = 0.0
    cus_s3_output: float = 0.0
    cus_q2_second: float = 0.0
    cus_deliveries: float = 0.0
    cus_demand: float = 0.0
    cus_s2_machines: float = 0.0
    cus_s3_machines: float = 0.0
    cus_actual_price: float = 0.0
    cus_avg_lead_time: float = 0.0

    inventory_dispatches: float = 0.0
    inventory_level: float = 0.0

    cash_on_hand: float = 0.0
    debt: float = 0.0
    inventory_costs_to_date: float = 0.0
    commission_interest_costs_to_date: float = 0.0
    machines_bought_to_date: float = 0.0
    salaries_to_date: float = 0.0
    std_ordering_costs_to_date: float = 0.0
    interest_earned_to_date: float = 0.0
    sales_custom_to_date: float = 0.0
    sales_standard_to_date: float = 0.0
    machines_sold_to_date: float = 0.0
    raw_holding_costs_to_date: float = 0.0
    custom_queue_holding_costs_to_date: float = 0.0
    standard_queue_holding_costs_to_date: float = 0.0

    rookies: float = 0.0
    experts: float = 0.0


@dataclass
class DerivedState:
    day: int
    days_remaining: int
    raw_on_hand: float
    raw_on_order: float
    raw_inventory_position: float
    expected_standard_units_per_day: float
    expected_custom_units_per_day: float
    expected_parts_per_day: float
    raw_coverage_days: float
    raw_forecast_stockout_day: Optional[float]
    raw_stockout_risk_score: float

    std_total_queue: float
    std_wip_pressure: float
    std_demand_delivery_gap: float
    std_price_market_gap: float
    std_resource_pressure_s1: float
    std_batching_mismatch_score: float
    std_ordering_pattern_score: float

    cus_total_wip: float
    cus_wip_ratio: float
    cus_demand_delivery_gap: float
    cus_lead_time_trend: float
    cus_s2_imbalance_score: float
    cus_congestion_score: float
    cus_service_risk_score: float

    s1_pressure: float
    s2_pressure: float
    s3_pressure: float
    manual_pressure: float
    workforce_capacity_adequacy: float

    daily_revenue_proxy: float
    daily_holding_cost_proxy: float
    salary_burden: float
    debt_burden: float
    cash_buffer_adequacy: float
    loan_urgency_score: float

    queue_growth_rate_std: float
    queue_growth_rate_cus: float
    system_stress_score: float
    endgame_robustness_score: float
    current_bottleneck: str
    current_regime: str
    warnings: List[str] = field(default_factory=list)


@dataclass
class ForecastState:
    horizon_days: int
    raw_stockout_day: Optional[int]
    projected_custom_wip_peak: float
    projected_cash_min: float
    projected_custom_lt_trend: str
    projected_queue_growth_warning: str


@dataclass
class RecommendationPackage:
    day: int
    current_bottleneck: str
    current_regime: str
    raw_coverage_days: float
    custom_congestion_score: float
    queue_imbalance_warning: str
    cash_risk_warning: str

    standard_order_frequency: int
    standard_order_size: int
    standard_s1_allocation_pct: float
    desired_s1_machines: int
    initial_batch_size: int
    manual_workday_length_in_shifts: float
    final_batch_size: int
    standard_product_price: float

    s2_allocation_to_first_pass_pct: float
    desired_s2_machines: int
    desired_s3_machines: int

    inventory_rop: int
    inventory_roq: int
    get_loan: float
    pay_loan: float
    desired_employees: int

    rationale: Dict[str, str]
    scores: Dict[str, float] = field(default_factory=dict)
    assumptions_used: Dict[str, float] = field(default_factory=dict)
