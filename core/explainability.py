def executive_summary(state, derived, recommendation):
    summary_text = (
        f"Current regime is {derived.current_regime}. "
        f"The main bottleneck is {derived.bottleneck}. "
        f"Raw coverage is {derived.raw_coverage_days:.2f} days and "
        f"custom congestion score is {derived.custom_congestion_score:.2f}. "
        f"The recommendation package prioritizes raw protection, custom service continuity, "
        f"queue stability, and cash survivability."
    )

    why_lines = [
        (
            f"**Inventory:** ROP covers lead-time demand plus an operational stress buffer. "
            f"ROQ uses EOQ logic and is bounded to avoid overstocking."
        ),
        (
            f"**Standard Controls:** Product price is the main throttle. "
            f"Order size/frequency are chosen to reduce burstiness while keeping useful throughput."
        ),
        (
            f"**Custom Flow:** S2 first-pass allocation is shifted toward the queue that needs relief most, "
            f"because S2 is a double-pass station and balance matters more than raw first-pass throughput."
        ),
        (
            f"**Capacity:** Machine additions are only recommended when bottleneck evidence is strong "
            f"and the system is under material or service stress."
        ),
        (
            f"**Workforce:** Desired employees are treated as a long-lead decision. "
            f"Hiring only increases when manual pressure is elevated."
        ),
        (
            f"**Finance:** Loans are used only to prevent operational disruption. "
            f"Debt repayment is recommended only when cash remains comfortably above the operating buffer."
        ),
    ]

    return {
        "summary_text": summary_text,
        "why_lines": why_lines,
    }