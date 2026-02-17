from services.explainability import (
    build_what_if_skip,
    build_why_recommendation,
    confidence_badge_for_forecast,
    confidence_badge_for_rule,
)


def test_rule_confidence_badges():
    assert confidence_badge_for_rule("completed", risk_spike_score=0.1) == "high"
    assert confidence_badge_for_rule("condition_failed", risk_spike_score=0.2) == "medium"


def test_forecast_confidence_badges():
    assert confidence_badge_for_forecast(0.1, 200) == "high"
    assert confidence_badge_for_forecast(0.35, 700) == "medium"
    assert confidence_badge_for_forecast(0.7, 1200) == "low"


def test_why_and_skip_messages():
    why = build_why_recommendation(True, 2, 1, "suggest_only")
    assert "trigger matched" in why

    skip = build_what_if_skip([{"allocated": 40}, {"task_title": "Pay"}])
    assert "unallocated" in skip
    assert "task" in skip
