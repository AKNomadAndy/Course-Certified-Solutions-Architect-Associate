from services.user_settings import get_or_create_user_settings, save_user_settings


def test_get_or_create_user_settings_is_idempotent(session):
    first = get_or_create_user_settings(session)
    second = get_or_create_user_settings(session)

    assert first.id == second.id
    assert second.user_name == "Personal User"
    assert second.base_currency == "USD"


def test_save_user_settings_normalizes_values(session):
    updated = save_user_settings(session, user_name="  Alex  ", base_currency=" usd ")

    assert updated.user_name == "Alex"
    assert updated.base_currency == "USD"
