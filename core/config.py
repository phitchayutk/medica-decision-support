from dataclasses import dataclass


@dataclass(frozen=True)
class GameAssumptions:
    raw_lead_time_days: int = 4
    standard_parts_per_unit: int = 4
    custom_parts_per_unit: int = 1
    custom_wip_limit: int = 750

    initial_batch_setup_days: int = 4
    final_batch_setup_days: int = 1

    rookie_to_expert_days: int = 15
    rookie_productivity_ratio: float = 0.40

    expert_salary_per_day: float = 100.0
    rookie_salary_per_day: float = 60.0
    extra_time_cost_multiplier: float = 1.50

    debt_interest_annual: float = 0.365
    debt_commission_rate: float = 0.02
    salary_debt_commission_rate: float = 0.05
    cash_interest_daily: float = 0.0005

    standard_order_fee: float = 100.0
    raw_order_fee: float = 2000.0
    raw_holding_cost_per_part_per_day: float = 1.0
    standard_queue_holding_cost_per_unit_per_day: float = 1.0
    custom_queue_holding_cost_per_unit_per_day: float = 1.0

    machine_buy_cost_s1: float = 15000.0
    machine_sell_value_s1: float = 7000.0
    machine_buy_cost_s2: float = 9000.0
    machine_sell_value_s2: float = 5000.0
    machine_buy_cost_s3: float = 7000.0
    machine_sell_value_s3: float = 4000.0

    frozen_last_days: int = 50
    total_game_days: int = 400
    player_control_last_day: int = 350
    forecast_horizon_days: int = 15

    min_cash_buffer_days: int = 7
