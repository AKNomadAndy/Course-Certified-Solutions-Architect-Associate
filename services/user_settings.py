from __future__ import annotations

from sqlalchemy import select

from db import models


def get_or_create_user_settings(session):
    settings = session.scalar(select(models.UserSettings).order_by(models.UserSettings.id))
    if settings:
        return settings

    settings = models.UserSettings(user_name="Personal User", base_currency="USD")
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


def save_user_settings(session, user_name: str, base_currency: str):
    settings = get_or_create_user_settings(session)
    settings.user_name = (user_name or "Personal User").strip() or "Personal User"
    settings.base_currency = (base_currency or "USD").strip().upper() or "USD"
    session.commit()
    session.refresh(settings)
    return settings
