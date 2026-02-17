from __future__ import annotations

from sqlalchemy import select

from db import models

AUTOPILOT_MODES = ("suggest_only", "auto_create_tasks", "auto_apply_internal_allocations")
RISK_TOLERANCES = ("conservative", "balanced", "aggressive")


def get_or_create_user_settings(session):
    settings = session.scalar(select(models.UserSettings).order_by(models.UserSettings.id))
    if settings:
        return settings

    settings = models.UserSettings(user_name="Personal User", base_currency="USD")
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def save_user_settings(
    session,
    user_name: str,
    base_currency: str,
    autopilot_mode: str | None = None,
    guardrail_min_checking_floor: float | None = None,
    guardrail_max_category_daily: float | None = None,
    guardrail_risk_pause_threshold: float | None = None,
    risk_tolerance: str | None = None,
    adaptive_thresholds_enabled: bool | None = None,
):
    settings = get_or_create_user_settings(session)
    settings.user_name = (user_name or "Personal User").strip() or "Personal User"
    settings.base_currency = (base_currency or "USD").strip().upper() or "USD"

    if autopilot_mode is not None:
        mode = (autopilot_mode or "suggest_only").strip()
        settings.autopilot_mode = mode if mode in AUTOPILOT_MODES else "suggest_only"

    if guardrail_min_checking_floor is not None:
        settings.guardrail_min_checking_floor = float(max(0.0, guardrail_min_checking_floor))

    if guardrail_max_category_daily is not None:
        settings.guardrail_max_category_daily = (
            float(guardrail_max_category_daily) if guardrail_max_category_daily > 0 else None
        )

    if guardrail_risk_pause_threshold is not None:
        threshold = float(guardrail_risk_pause_threshold)
        settings.guardrail_risk_pause_threshold = min(1.0, max(0.0, threshold))

    if risk_tolerance is not None:
        rt = (risk_tolerance or "balanced").strip().lower()
        settings.risk_tolerance = rt if rt in RISK_TOLERANCES else "balanced"

    if adaptive_thresholds_enabled is not None:
        settings.adaptive_thresholds_enabled = bool(adaptive_thresholds_enabled)

    session.commit()
    session.refresh(settings)
    return settings
