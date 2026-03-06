from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ============================================================
# Config / Thresholds
# ============================================================

@dataclass
class Thresholds:
    queue_growth_warn: float = 5.0
    queue_growth_critical: float = 15.0
    queue_pressure_warn: float = 0.75
    queue_pressure_critical: float = 1.00

    utilization_warn: float = 0.75
    utilization_bottleneck: float = 0.90
    utilization_overcapacity: float = 0.50

    raw_coverage_warn_days: float = 4.0
    raw_coverage_safe_days: float = 5.0

    custom_wip_limit: float = 750.0
    custom_wip_warn_ratio: float = 0.85

    custom_lt_warn: float = 12.0
    custom_lt_critical: float = 20.0

    stockout_penalty: float = 1.0
    queue_explosion_penalty: float = 1.0
    cash_risk_penalty: float = 1.0


# ============================================================
# Helpers
# ============================================================

def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b not in (0, 0.0) else default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ma(values: List[float], window: int = 3) -> float:
    if not values:
        return 0.0
    vals = values[-window:]
    return sum(vals) / len(vals)


# ============================================================
# Core Data Models
# ============================================================

@dataclass
class InventoryState:
    day: int
    raw_on_hand: float
    raw_dispatch_today: float
    reorder_point: float
    reorder_quantity: float
    raw_on_order_pipeline: Dict[int, float] = field(default_factory=dict)  # arrival_day -> qty


@dataclass
class StandardState:
    day: int
    order_frequency_days: float
    order_size_units: float
    product_price: float
    market_price: float

    s1_allocation_to_standard_pct: float
    s1_machines: int

    initial_batch_size: float
    manual_shifts: float
    final_batch_size: float

    accepted_orders: float
    accumulated_orders: float

    q_before_batch: float
    q_manual: float
    fg_inventory: float

    s1_output: float
    initial_batch_output: float
    manual_output: float
    final_batch_output: float
    deliveries: float


@dataclass
class CustomState:
    day: int
    demand: float
    accepted_orders: float
    accumulated_orders: float

    q1: float
    q2_first: float
    q2_second: float
    q3: float

    s1_output: float
    s2_first_output: float
    s3_output: float
    deliveries: float

    average_lead_time: float
    actual_price: float

    s2_allocation_to_first_pass_pct: float
    s2_machines: int
    s3_machines: int


@dataclass
class WorkforceState:
    day: int
    rookies: int
    experts: int
    desired_employees: int

    rookie_productivity: float = 0.40
    rookie_days_to_expert: int = 15
    rookie_salary: float = 60.0
    expert_salary: float = 100.0
    overtime_multiplier: float = 1.5


@dataclass
class FinancialState:
    day: int
    cash_on_hand: float
    debt: float

    salaries_to_date: float
    standard_ordering_costs_to_date: float
    raw_holding_costs_to_date: float
    custom_queue_holding_costs_to_date: float
    standard_queue_holding_costs_to_date: float
    sales_custom_to_date: float
    sales_standard_to_date: float
    commission_interest_costs_to_date: float
    interest_earned_to_date: float

    get_loan: float = 0.0
    pay_loan: float = 0.0


@dataclass
class PlantState:
    day: int
    inventory: InventoryState
    standard: StandardState
    custom: CustomState
    workforce: WorkforceState
    finance: FinancialState


# ============================================================
# Derived Metrics Models
# ============================================================

@dataclass
class QueueMetric:
    name: str
    level: float
    growth: float
    growth_ma3: float
    pressure: float
    unstable: bool
    severity: str


@dataclass
class UtilizationMetric:
    name: str
    throughput: float
    capacity: float
    utilization: float
    severity: str


@dataclass
class Diagnostics:
    bottleneck: str
    regime: str
    raw_coverage_days: float
    custom_congestion_score: float
    stress_score: float
    endgame_robustness: float
    queue_metrics: Dict[str, QueueMetric]
    utilization_metrics: Dict[str, UtilizationMetric]
    warnings: List[str]


@dataclass
class SimulationDayResult:
    sim_day: int
    raw_on_hand: float
    raw_on_order: float
    raw_coverage_days: float
    custom_wip: float
    custom_wip_ratio: float
    std_total_queue: float
    stockout: bool
    cash_on_hand: float
    queue_explosion: bool


@dataclass
class SimulationResult:
    horizon: int
    daily: List[SimulationDayResult]
    stockout_risk: bool
    queue_explosion_risk: bool
    cash_risk: bool
    survival_score_10d: float
    first_stockout_day: Optional[int]
    first_queue_explosion_day: Optional[int]


# ============================================================
# Queue Engine
# ============================================================

STANDARD_QUEUE_NAMES = [
    "Q_std_before_batch",
    "Q_manual",
    "FG_inventory",
]

CUSTOM_QUEUE_NAMES = [
    "Q1",
    "Q2_first",
    "Q2_second",
    "Q3",
]


def compute_queue_metrics(
    current: PlantState,
    history: List[PlantState],
    thresholds: Thresholds,
) -> Dict[str, QueueMetric]:
    prev = history[-1] if history else None

    def hist_values(extractor) -> List[float]:
        return [extractor(h) for h in history if h.day < current.day]

    metrics: Dict[str, QueueMetric] = {}

    queue_map = {
        "Q_std_before_batch": current.standard.q_before_batch,
        "Q_manual": current.standard.q_manual,
        "FG_inventory": current.standard.fg_inventory,
        "Q1": current.custom.q1,
        "Q2_first": current.custom.q2_first,
        "Q2_second": current.custom.q2_second,
        "Q3": current.custom.q3,
    }

    reference_capacity_map = {
        "Q_std_before_batch": max(current.standard.initial_batch_output, 1.0),
        "Q_manual": max(current.standard.manual_output, 1.0),
        "FG_inventory": max(current.standard.deliveries, 1.0),
        "Q1": max(current.custom.s1_output, 1.0),
        "Q2_first": max(current.custom.s2_first_output, 1.0),
        "Q2_second": max(current.custom.s2_first_output, 1.0),
        "Q3": max(current.custom.s3_output, 1.0),
    }

    prev_map = {}
    if prev:
        prev_map = {
            "Q_std_before_batch": prev.standard.q_before_batch,
            "Q_manual": prev.standard.q_manual,
            "FG_inventory": prev.standard.fg_inventory,
            "Q1": prev.custom.q1,
            "Q2_first": prev.custom.q2_first,
            "Q2_second": prev.custom.q2_second,
            "Q3": prev.custom.q3,
        }

    for q_name, level in queue_map.items():
        prev_level = prev_map.get(q_name, level)
        growth = level - prev_level

        series = hist_values(
            lambda s, name=q_name: {
                "Q_std_before_batch": s.standard.q_before_batch,
                "Q_manual": s.standard.q_manual,
                "FG_inventory": s.standard.fg_inventory,
                "Q1": s.custom.q1,
                "Q2_first": s.custom.q2_first,
                "Q2_second": s.custom.q2_second,
                "Q3": s.custom.q3,
            }[name]
        ) + [level]

        growth_series = []
        for i in range(1, len(series)):
            growth_series.append(series[i] - series[i - 1])
        growth_ma3 = ma(growth_series, 3)

        pressure = safe_div(level, reference_capacity_map[q_name], 0.0)

        unstable = (
            growth_ma3 > thresholds.queue_growth_warn
            or (pressure > thresholds.queue_pressure_warn and growth > 0)
        )

        if pressure >= thresholds.queue_pressure_critical or growth_ma3 >= thresholds.queue_growth_critical:
            severity = "critical"
        elif unstable:
            severity = "warning"
        else:
            severity = "ok"

        metrics[q_name] = QueueMetric(
            name=q_name,
            level=level,
            growth=growth,
            growth_ma3=growth_ma3,
            pressure=pressure,
            unstable=unstable,
            severity=severity,
        )

    return metrics


# ============================================================
# Utilization Engine
# ============================================================

def compute_effective_manual_capacity(workforce: WorkforceState, manual_shifts: float) -> float:
    expert_cap = workforce.experts * 1.0
    rookie_cap = workforce.rookies * workforce.rookie_productivity
    base = expert_cap + rookie_cap
    return base * manual_shifts


def compute_station_capacity(state: PlantState) -> Dict[str, float]:
    s1_total_output = max(state.standard.s1_output + state.custom.s1_output, 1.0)
    current_s1_machines = max(state.standard.s1_machines, 1)
    s1_per_machine = s1_total_output / current_s1_machines

    s2_total_capacity_proxy = max(state.custom.s2_first_output, 1.0)
    s2_per_machine = s2_total_capacity_proxy / max(state.custom.s2_machines, 1)

    s3_total_capacity_proxy = max(state.custom.s3_output, 1.0)
    s3_per_machine = s3_total_capacity_proxy / max(state.custom.s3_machines, 1)

    manual_capacity = compute_effective_manual_capacity(state.workforce, state.standard.manual_shifts)

    return {
        "S1": s1_per_machine * current_s1_machines,
        "S2": s2_per_machine * max(state.custom.s2_machines, 1),
        "S3": s3_per_machine * max(state.custom.s3_machines, 1),
        "Manual": max(manual_capacity, 1.0),
    }


def compute_station_utilization(state: PlantState, thresholds: Thresholds) -> Dict[str, UtilizationMetric]:
    capacities = compute_station_capacity(state)

    throughput_map = {
        "S1": state.standard.s1_output + state.custom.s1_output,
        "S2": state.custom.s2_first_output,
        "S3": state.custom.s3_output,
        "Manual": state.standard.manual_output,
    }

    metrics: Dict[str, UtilizationMetric] = {}

    for name, throughput in throughput_map.items():
        capacity = max(capacities[name], 1.0)
        util = safe_div(throughput, capacity, 0.0)

        if util >= thresholds.utilization_bottleneck:
            severity = "critical"
        elif util >= thresholds.utilization_warn:
            severity = "warning"
        elif util < thresholds.utilization_overcapacity:
            severity = "underused"
        else:
            severity = "ok"

        metrics[name] = UtilizationMetric(
            name=name,
            throughput=throughput,
            capacity=capacity,
            utilization=util,
            severity=severity,
        )

    return metrics


# ============================================================
# Demand / Inventory Helpers
# ============================================================

def expected_standard_units_per_day(state: PlantState) -> float:
    std = state.standard
    return safe_div(std.order_size_units, std.order_frequency_days, std.accepted_orders)


def expected_custom_units_per_day(state: PlantState) -> float:
    return max(state.custom.demand, state.custom.accepted_orders)


def expected_parts_per_day(state: PlantState) -> float:
    return 4.0 * expected_standard_units_per_day(state) + 1.0 * expected_custom_units_per_day(state)


def raw_on_order_total(inv: InventoryState, current_day: int) -> float:
    return sum(qty for day, qty in inv.raw_on_order_pipeline.items() if day >= current_day)


def raw_coverage_days(state: PlantState) -> float:
    return safe_div(state.inventory.raw_on_hand, expected_parts_per_day(state), 0.0)


def custom_total_wip(state: PlantState) -> float:
    c = state.custom
    return c.q1 + c.q2_first + c.q2_second + c.q3


def standard_total_queue(state: PlantState) -> float:
    s = state.standard
    return s.q_before_batch + s.q_manual + s.fg_inventory


def custom_congestion_score(state: PlantState, thresholds: Thresholds) -> float:
    c = state.custom
    wip_ratio = safe_div(custom_total_wip(state), thresholds.custom_wip_limit, 0.0)
    lt_score = clamp(safe_div(c.average_lead_time, thresholds.custom_lt_warn, 0.0), 0.0, 2.0)
    gap_score = clamp(safe_div(max(c.demand - c.deliveries, 0.0), max(c.demand, 1.0), 0.0), 0.0, 1.0)
    return clamp(0.4 * wip_ratio + 0.35 * lt_score + 0.25 * gap_score, 0.0, 1.0)


# ============================================================
# Regime / Bottleneck / Diagnostics
# ============================================================

def detect_bottleneck(
    queue_metrics: Dict[str, QueueMetric],
    util_metrics: Dict[str, UtilizationMetric],
) -> str:
    candidates: List[Tuple[float, str]] = []

    for q in queue_metrics.values():
        score = q.pressure + max(q.growth_ma3, 0.0) * 0.05
        if q.name in {"Q1", "Q2_first", "Q2_second", "Q3"}:
            score += 0.25
        candidates.append((score, q.name))

    for u in util_metrics.values():
        score = u.utilization
        station_name = f"Station_{u.name}"
        candidates.append((score, station_name))

    best = max(candidates, key=lambda x: x[0])[1]

    if best in {"Q1", "Q2_first", "Q2_second", "Q3", "Station_S2", "Station_S3"}:
        return best
    if best in {"Q_std_before_batch", "Q_manual", "FG_inventory", "Station_Manual"}:
        return best
    return "Shared S1"


def detect_regime(state: PlantState, thresholds: Thresholds, custom_score: float) -> str:
    coverage = raw_coverage_days(state)
    c = state.custom

    if (
        coverage < thresholds.raw_coverage_warn_days
        or custom_score > 0.80
        or c.average_lead_time > thresholds.custom_lt_critical
    ):
        return "Recovery"

    if custom_score > 0.45 or c.average_lead_time > thresholds.custom_lt_warn:
        return "Stabilize"

    if state.finance.cash_on_hand > 0 and state.finance.debt <= 0:
        return "Harvest"

    return "Endgame"


def build_diagnostics(
    current: PlantState,
    history: List[PlantState],
    thresholds: Thresholds,
    remaining_days: int = 50,
) -> Diagnostics:
    q_metrics = compute_queue_metrics(current, history, thresholds)
    u_metrics = compute_station_utilization(current, thresholds)
    coverage = raw_coverage_days(current)
    custom_score = custom_congestion_score(current, thresholds)

    stress_components = [
        clamp((thresholds.raw_coverage_warn_days - coverage) / thresholds.raw_coverage_warn_days, 0.0, 1.0),
        custom_score,
        max((max(u.utilization for u in u_metrics.values()) - thresholds.utilization_warn), 0.0),
    ]
    stress_score = clamp(sum(stress_components) / 3.0, 0.0, 1.0)

    regime = detect_regime(current, thresholds, custom_score)
    bottleneck = detect_bottleneck(q_metrics, u_metrics)

    endgame_robustness = clamp(
        0.45 * clamp(coverage / thresholds.raw_coverage_safe_days, 0.0, 1.0)
        + 0.35 * (1.0 - custom_score)
        + 0.20 * (1.0 - stress_score),
        0.0,
        1.0,
    )

    warnings: List[str] = []

    if coverage < thresholds.raw_coverage_warn_days:
        warnings.append(f"Raw coverage below safe lead-time cover: {coverage:.2f} days")

    if custom_total_wip(current) / thresholds.custom_wip_limit > thresholds.custom_wip_warn_ratio:
        warnings.append("Custom WIP near limit")

    if current.custom.average_lead_time > thresholds.custom_lt_warn:
        warnings.append(f"Custom lead time elevated: {current.custom.average_lead_time:.2f}")

    for q in q_metrics.values():
        if q.severity in {"warning", "critical"}:
            warnings.append(
                f"{q.name} unstable (level={q.level:.2f}, growth_ma3={q.growth_ma3:.2f}, pressure={q.pressure:.2f})"
            )

    return Diagnostics(
        bottleneck=bottleneck,
        regime=regime,
        raw_coverage_days=coverage,
        custom_congestion_score=custom_score,
        stress_score=stress_score,
        endgame_robustness=endgame_robustness,
        queue_metrics=q_metrics,
        utilization_metrics=u_metrics,
        warnings=warnings,
    )


# ============================================================
# Simulator
# ============================================================

@dataclass
class Policy:
    std_order_frequency: float
    std_order_size: float
    std_s1_alloc_pct: float
    s2_first_pass_pct: float
    inventory_rop: float
    inventory_roq: float
    std_price: float
    desired_s1_machines: int
    desired_s2_machines: int
    desired_s3_machines: int
    desired_employees: int
    manual_shifts: float


def build_default_policy_from_state(state: PlantState) -> Policy:
    return Policy(
        std_order_frequency=state.standard.order_frequency_days,
        std_order_size=state.standard.order_size_units,
        std_s1_alloc_pct=state.standard.s1_allocation_to_standard_pct,
        s2_first_pass_pct=state.custom.s2_allocation_to_first_pass_pct,
        inventory_rop=state.inventory.reorder_point,
        inventory_roq=state.inventory.reorder_quantity,
        std_price=state.standard.product_price,
        desired_s1_machines=state.standard.s1_machines,
        desired_s2_machines=state.custom.s2_machines,
        desired_s3_machines=state.custom.s3_machines,
        desired_employees=state.workforce.desired_employees,
        manual_shifts=state.standard.manual_shifts,
    )


def simulate_days(
    state: PlantState,
    policy: Policy,
    thresholds: Thresholds,
    horizon: int = 10,
) -> SimulationResult:
    sim_daily: List[SimulationDayResult] = []

    raw_on_hand = state.inventory.raw_on_hand
    pipeline = dict(state.inventory.raw_on_order_pipeline)
    cash = state.finance.cash_on_hand

    std_queue = standard_total_queue(state)
    cus_wip = custom_total_wip(state)

    s1_machines = policy.desired_s1_machines
    s2_machines = policy.desired_s2_machines
    s3_machines = policy.desired_s3_machines

    stockout_risk = False
    queue_explosion_risk = False
    cash_risk = False
    first_stockout_day = None
    first_queue_explosion_day = None

    # simple capacity proxies from current state
    current_caps = compute_station_capacity(state)
    s1_per_machine = safe_div(current_caps["S1"], max(state.standard.s1_machines, 1), 0.0)
    s2_per_machine = safe_div(current_caps["S2"], max(state.custom.s2_machines, 1), 0.0)
    s3_per_machine = safe_div(current_caps["S3"], max(state.custom.s3_machines, 1), 0.0)

    for step in range(1, horizon + 1):
        sim_day = state.day + step

        arrivals_today = pipeline.pop(sim_day, 0.0)
        raw_on_hand += arrivals_today

        std_demand = safe_div(policy.std_order_size, policy.std_order_frequency, 0.0)
        cus_demand = state.custom.demand  # keep exogenous demand flat in short horizon

        required_parts = 4.0 * std_demand + 1.0 * cus_demand

        # reorder logic on inventory position
        raw_on_order = sum(pipeline.values())
        inventory_position = raw_on_hand + raw_on_order

        if inventory_position <= policy.inventory_rop:
            arrival_day = sim_day + 4
            pipeline[arrival_day] = pipeline.get(arrival_day, 0.0) + policy.inventory_roq

        # simplified station capacities
        s1_total_cap = s1_per_machine * max(s1_machines, 1)
        s1_std_cap = s1_total_cap * (policy.std_s1_alloc_pct / 100.0)
        s1_cus_cap = s1_total_cap - s1_std_cap

        s2_total_cap = s2_per_machine * max(s2_machines, 1)
        s2_first_cap = s2_total_cap * (policy.s2_first_pass_pct / 100.0)
        s2_second_cap = s2_total_cap - s2_first_cap

        s3_total_cap = s3_per_machine * max(s3_machines, 1)
        manual_cap = compute_effective_manual_capacity(
            WorkforceState(
                day=sim_day,
                rookies=state.workforce.rookies,
                experts=max(policy.desired_employees, 0),
                desired_employees=policy.desired_employees,
            ),
            policy.manual_shifts,
        )

        # raw availability
        parts_used = min(raw_on_hand, required_parts)
        raw_on_hand -= parts_used

        stockout = parts_used + 1e-9 < required_parts
        if stockout and not stockout_risk:
            stockout_risk = True
            first_stockout_day = sim_day

        # simplified queue evolution
        std_in = std_demand
        cus_in = cus_demand

        std_service = min(std_in + std_queue, s1_std_cap, manual_cap)
        cus_service = min(cus_in + cus_wip, s1_cus_cap, s2_first_cap, s2_second_cap + s3_total_cap)

        std_queue = max(0.0, std_queue + std_in - std_service)
        cus_wip = max(0.0, cus_wip + cus_in - cus_service)

        custom_wip_ratio = safe_div(cus_wip, thresholds.custom_wip_limit, 0.0)

        queue_explosion = (
            custom_wip_ratio >= thresholds.custom_wip_warn_ratio
            or std_queue > 2.0 * max(std_service, 1.0)
        )

        if queue_explosion and not queue_explosion_risk:
            queue_explosion_risk = True
            first_queue_explosion_day = sim_day

        # simple cash model
        std_sales = std_service * policy.std_price
        cus_sales = cus_service * state.custom.actual_price

        holding_costs = raw_on_hand + std_queue + cus_wip
        daily_salary = (
            state.workforce.rookies * state.workforce.rookie_salary
            + max(policy.desired_employees, 0) * state.workforce.expert_salary
        )

        cash = cash + std_sales + cus_sales - holding_costs - daily_salary
        if cash < 0:
            cash_risk = True

        coverage = safe_div(raw_on_hand, max(required_parts, 1e-9), 0.0)

        sim_daily.append(
            SimulationDayResult(
                sim_day=sim_day,
                raw_on_hand=raw_on_hand,
                raw_on_order=sum(pipeline.values()),
                raw_coverage_days=coverage,
                custom_wip=cus_wip,
                custom_wip_ratio=custom_wip_ratio,
                std_total_queue=std_queue,
                stockout=stockout,
                cash_on_hand=cash,
                queue_explosion=queue_explosion,
            )
        )

    penalties = 0.0
    if stockout_risk:
        penalties += thresholds.stockout_penalty
    if queue_explosion_risk:
        penalties += thresholds.queue_explosion_penalty
    if cash_risk:
        penalties += thresholds.cash_risk_penalty

    survival_score = clamp(1.0 - penalties / 3.0, 0.0, 1.0)

    return SimulationResult(
        horizon=horizon,
        daily=sim_daily,
        stockout_risk=stockout_risk,
        queue_explosion_risk=queue_explosion_risk,
        cash_risk=cash_risk,
        survival_score_10d=survival_score,
        first_stockout_day=first_stockout_day,
        first_queue_explosion_day=first_queue_explosion_day,
    )


# ============================================================
# ROI / Forecast / Trend Helpers
# ============================================================

def machine_payback_days(machine_cost: float, queue_cost_saved_per_day: float) -> float:
    return safe_div(machine_cost, queue_cost_saved_per_day, float("inf"))


def workforce_manual_load_forecast(state: PlantState) -> float:
    return safe_div(state.standard.q_manual, max(state.standard.manual_output, 1.0), 0.0)


def standard_demand_std(history: List[PlantState]) -> float:
    if len(history) < 2:
        return 0.0
    values = [expected_standard_units_per_day(h) for h in history]
    return pd.Series(values).std(ddof=0) if len(values) > 1 else 0.0


def custom_lt_slope(current: PlantState, history: List[PlantState]) -> float:
    if not history:
        return 0.0
    prev = history[-1]
    return current.custom.average_lead_time - prev.custom.average_lead_time


# ============================================================
# Example Usage
# ============================================================

def example() -> None:
    thresholds = Thresholds()

    state = PlantState(
        day=50,
        inventory=InventoryState(
            day=50,
            raw_on_hand=266.0,
            raw_dispatch_today=0.0,
            reorder_point=266.0,
            reorder_quantity=450.0,
            raw_on_order_pipeline={54: 450.0},
        ),
        standard=StandardState(
            day=50,
            order_frequency_days=2.0,
            order_size_units=16.0,
            product_price=412.61,
            market_price=395.0,
            s1_allocation_to_standard_pct=40.0,
            s1_machines=3,
            initial_batch_size=20.0,
            manual_shifts=2.0,
            final_batch_size=20.0,
            accepted_orders=8.0,
            accumulated_orders=40.0,
            q_before_batch=35.0,
            q_manual=20.0,
            fg_inventory=10.0,
            s1_output=12.0,
            initial_batch_output=10.0,
            manual_output=10.0,
            final_batch_output=10.0,
            deliveries=10.0,
        ),
        custom=CustomState(
            day=50,
            demand=28.0,
            accepted_orders=28.0,
            accumulated_orders=220.0,
            q1=45.0,
            q2_first=80.0,
            q2_second=95.0,
            q3=60.0,
            s1_output=18.0,
            s2_first_output=16.0,
            s3_output=17.0,
            deliveries=15.0,
            average_lead_time=14.0,
            actual_price=145.0,
            s2_allocation_to_first_pass_pct=85.0,
            s2_machines=2,
            s3_machines=3,
        ),
        workforce=WorkforceState(
            day=50,
            rookies=0,
            experts=12,
            desired_employees=12,
        ),
        finance=FinancialState(
            day=50,
            cash_on_hand=334_000.0,
            debt=0.0,
            salaries_to_date=60_000.0,
            standard_ordering_costs_to_date=1_000.0,
            raw_holding_costs_to_date=2_700.0,
            custom_queue_holding_costs_to_date=2_900.0,
            standard_queue_holding_costs_to_date=5_600.0,
            sales_custom_to_date=40_000.0,
            sales_standard_to_date=153_600.0,
            commission_interest_costs_to_date=0.0,
            interest_earned_to_date=8_500.0,
        ),
    )

    # very small history example
    history = [
        PlantState(
            day=49,
            inventory=InventoryState(
                day=49,
                raw_on_hand=220.0,
                raw_dispatch_today=450.0,
                reorder_point=260.0,
                reorder_quantity=450.0,
                raw_on_order_pipeline={53: 450.0},
            ),
            standard=StandardState(
                day=49,
                order_frequency_days=2.0,
                order_size_units=16.0,
                product_price=410.0,
                market_price=394.0,
                s1_allocation_to_standard_pct=42.0,
                s1_machines=3,
                initial_batch_size=20.0,
                manual_shifts=2.0,
                final_batch_size=20.0,
                accepted_orders=8.0,
                accumulated_orders=42.0,
                q_before_batch=30.0,
                q_manual=18.0,
                fg_inventory=11.0,
                s1_output=11.0,
                initial_batch_output=9.0,
                manual_output=9.0,
                final_batch_output=9.0,
                deliveries=9.0,
            ),
            custom=CustomState(
                day=49,
                demand=28.0,
                accepted_orders=28.0,
                accumulated_orders=210.0,
                q1=40.0,
                q2_first=72.0,
                q2_second=88.0,
                q3=55.0,
                s1_output=17.0,
                s2_first_output=15.0,
                s3_output=16.0,
                deliveries=14.0,
                average_lead_time=13.2,
                actual_price=146.0,
                s2_allocation_to_first_pass_pct=82.0,
                s2_machines=2,
                s3_machines=3,
            ),
            workforce=WorkforceState(
                day=49,
                rookies=0,
                experts=12,
                desired_employees=12,
            ),
            finance=FinancialState(
                day=49,
                cash_on_hand=333_500.0,
                debt=0.0,
                salaries_to_date=58_800.0,
                standard_ordering_costs_to_date=1_000.0,
                raw_holding_costs_to_date=2_650.0,
                custom_queue_holding_costs_to_date=2_850.0,
                standard_queue_holding_costs_to_date=5_500.0,
                sales_custom_to_date=39_500.0,
                sales_standard_to_date=150_000.0,
                commission_interest_costs_to_date=0.0,
                interest_earned_to_date=8_300.0,
            ),
        )
    ]

    diagnostics = build_diagnostics(state, history, thresholds, remaining_days=50)
    policy = build_default_policy_from_state(state)
    sim = simulate_days(state, policy, thresholds, horizon=10)

    print("\n=== EXECUTIVE SUMMARY ===")
    print(f"Bottleneck: {diagnostics.bottleneck}")
    print(f"Regime: {diagnostics.regime}")
    print(f"Raw Coverage Days: {diagnostics.raw_coverage_days:.2f}")
    print(f"Custom Congestion Score: {diagnostics.custom_congestion_score:.2f}")
    print(f"Stress Score: {diagnostics.stress_score:.2f}")
    print(f"Endgame Robustness: {diagnostics.endgame_robustness:.2f}")

    print("\n=== WARNINGS ===")
    for w in diagnostics.warnings:
        print("-", w)

    print("\n=== UTILIZATION ===")
    for u in diagnostics.utilization_metrics.values():
        print(f"{u.name}: util={u.utilization:.2f}, severity={u.severity}")

    print("\n=== QUEUES ===")
    for q in diagnostics.queue_metrics.values():
        print(
            f"{q.name}: level={q.level:.2f}, growth={q.growth:.2f}, "
            f"growth_ma3={q.growth_ma3:.2f}, pressure={q.pressure:.2f}, severity={q.severity}"
        )

    print("\n=== 10-DAY SIMULATION SUMMARY ===")
    print(f"Stockout Risk: {sim.stockout_risk} (day={sim.first_stockout_day})")
    print(f"Queue Explosion Risk: {sim.queue_explosion_risk} (day={sim.first_queue_explosion_day})")
    print(f"Cash Risk: {sim.cash_risk}")
    print(f"Survival Score 10D: {sim.survival_score_10d:.2f}")

    print("\n=== EXTRA METRICS ===")
    print(f"Manual Load Forecast: {workforce_manual_load_forecast(state):.2f}")
    print(f"Std Demand Std: {standard_demand_std(history + [state]):.2f}")
    print(f"Custom LT Slope: {custom_lt_slope(state, history):.2f}")
    print(f"Example S2 Payback Days: {machine_payback_days(9000.0, 250.0):.2f}")


if __name__ == "__main__":
    example()
