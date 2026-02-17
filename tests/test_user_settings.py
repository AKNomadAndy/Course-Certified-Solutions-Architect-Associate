from services.user_settings import AUTOPILOT_MODES, get_or_create_user_settings, save_user_settings


def test_get_or_create_user_settings_is_idempotent(session):
    first = get_or_create_user_settings(session)
    second = get_or_create_user_settings(session)

    assert first.id == second.id
    assert second.user_name == "Personal User"
    assert second.base_currency == "USD"


def test_save_user_settings_normalizes_values(session):
    updated = save_user_settings(
        session,
        user_name="  Alex  ",
        base_currency=" usd ",
        autopilot_mode="auto_create_tasks",
        guardrail_min_checking_floor=125.0,
        guardrail_max_category_daily=200.0,
        guardrail_risk_pause_threshold=0.7,
        risk_tolerance="conservative",
        adaptive_thresholds_enabled=False,
    )

    assert updated.user_name == "Alex"
    assert updated.base_currency == "USD"
    assert updated.autopilot_mode == "auto_create_tasks"
    assert updated.guardrail_min_checking_floor == 125.0
    assert updated.guardrail_max_category_daily == 200.0
    assert updated.guardrail_risk_pause_threshold == 0.7
    assert updated.risk_tolerance == "conservative"
    assert updated.adaptive_thresholds_enabled is False


def test_invalid_autopilot_mode_falls_back(session):
    updated = save_user_settings(session, user_name="A", base_currency="USD", autopilot_mode="weird")
    assert updated.autopilot_mode in AUTOPILOT_MODES
    assert updated.autopilot_mode == "suggest_only"
