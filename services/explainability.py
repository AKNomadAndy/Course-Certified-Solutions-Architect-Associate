from __future__ import annotations


def confidence_badge_for_rule(status: str, risk_spike_score: float | None = None) -> str:
    if status in {"completed", "skipped"} and (risk_spike_score or 0.0) < 0.3:
        return "high"
    if status in {"guardrail_blocked", "action_failed", "condition_failed"}:
        return "medium"
    return "low"


def confidence_badge_for_forecast(prob_negative: float, band_width: float) -> str:
    if prob_negative <= 0.2 and band_width <= 400:
        return "high"
    if prob_negative <= 0.45 and band_width <= 900:
        return "medium"
    return "low"


def build_why_recommendation(trigger_hit: bool, condition_count: int, action_count: int, execution_mode: str) -> str:
    if not trigger_hit:
        return "No recommendation because the trigger did not match this event."
    return (
        f"Recommendation produced because trigger matched, {condition_count} condition(s) were evaluated, "
        f"and {action_count} action(s) were attempted in {execution_mode} mode."
    )


def build_what_if_skip(action_payloads: list[dict]) -> str:
    allocated = round(sum(float(p.get("allocated", 0) or 0) for p in action_payloads), 2)
    tasks = sum(1 for p in action_payloads if p.get("task_title"))
    if allocated <= 0 and tasks == 0:
        return "Skipping this recommendation likely has minimal immediate impact based on this run."
    parts = []
    if allocated > 0:
        parts.append(f"{allocated:.2f} would remain unallocated")
    if tasks > 0:
        parts.append(f"{tasks} manual payment task(s) would not be generated")
    return "If you skip this: " + " and ".join(parts) + "."
