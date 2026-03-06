from __future__ import annotations

from .schemas import DerivedState, RecommendationPackage


def executive_summary(derived: DerivedState, recommendation: RecommendationPackage) -> str:
    return (
        f"Current regime is {derived.current_regime}. The main bottleneck is {derived.current_bottleneck}. "
        f"Raw coverage is {derived.raw_coverage_days:.2f} days and custom congestion score is {derived.cus_congestion_score:.2f}. "
        f"The recommendation package prioritizes raw protection, custom service continuity, queue stability, and cash survivability."
    )
