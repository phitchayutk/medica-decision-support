from dataclasses import dataclass


@dataclass
class GameAssumptions:
    raw_lead_time_days: int = 4
    raw_cost_per_part: float = 50.0
    raw_order_fee: float = 2000.0
    raw_holding_cost_per_unit_day: float = 1.0

    standard_parts_per_unit: float = 4.0
    custom_parts_per_unit: float = 1.0

    custom_wip_limit: float = 750.0
    custom_queue_holding_cost_per_unit_day: float = 1.0
    standard_queue_holding_cost_per_unit_day: float = 1.0

    standard_order_fee: float = 100.0
    initial_batch_setup_days: float = 4.0
    final_batch_setup_days: float = 1.0

    rookie_days_to_expert: int = 15
    rookie_productivity: float = 0.40
    rookie_salary_per_day: float = 60.0
    expert_salary_per_day: float = 100.0
    overtime_multiplier: float = 1.50

    s1_buy_price: float = 15000.0
    s2_buy_price: float = 9000.0
    s3_buy_price: float = 7000.0

    s1_sell_price: float = 7000.0
    s2_sell_price: float = 5000.0
    s3_sell_price: float = 4000.0

    normal_debt_daily_rate: float = 0.365 / 365.0
    normal_debt_commission: float = 0.02
    salary_debt_commission: float = 0.05
    cash_daily_interest: float = 0.0005

    endgame_days_uncontrolled: int = 50


ASSUMPTIONS = GameAssumptions()