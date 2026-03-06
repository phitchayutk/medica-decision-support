from __future__ import annotations

from typing import Iterable


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    try:
        return a / b if b not in (0, 0.0) else default
    except Exception:
        return default


def nz(value: float | None, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if value != value:
            return default
    except Exception:
        return default
    return float(value)


def rolling_mean(values: Iterable[float], window: int) -> float:
    vals = [nz(v) for v in values]
    if not vals:
        return 0.0
    vals = vals[-window:]
    return sum(vals) / len(vals)


def money(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return f"{value:.1%}"
