from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db import models


def upsert_health_status(session, key: str, value: dict):
    row = session.scalar(select(models.SystemHealthStatus).where(models.SystemHealthStatus.key == key))
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        row = models.SystemHealthStatus(key=key, value=value)
        session.add(row)
    session.commit()
    return row


def get_health_status(session, key: str) -> dict | None:
    row = session.scalar(select(models.SystemHealthStatus).where(models.SystemHealthStatus.key == key))
    return row.value if row else None


def build_health_report(session) -> dict:
    now = datetime.now(timezone.utc)
    heartbeat_row = session.scalar(select(models.SystemHealthStatus).where(models.SystemHealthStatus.key == "scheduler_heartbeat"))
    scheduler_state = "unknown"
    stale_warning = None

    if heartbeat_row:
        heartbeat_at = heartbeat_row.updated_at.replace(tzinfo=timezone.utc)
        age_min = (now - heartbeat_at).total_seconds() / 60.0
        scheduler_state = "healthy" if age_min <= 90 else "stale"
        if age_min > 90:
            stale_warning = f"Scheduler heartbeat is stale ({age_min:.0f} minutes old)."

    last_schedule_run = session.scalar(
        select(models.Run).where(models.Run.event_key.like("schedule:%")).order_by(models.Run.created_at.desc())
    )

    last_import = session.scalar(select(models.ImportRun).order_by(models.ImportRun.created_at.desc()))
    import_warning = None
    if last_import:
        import_age_days = (now - last_import.created_at.replace(tzinfo=timezone.utc)).days
        if import_age_days >= 30:
            import_warning = f"No import in {import_age_days} days. Data may be stale."

    open_tasks = session.query(models.Task).filter(models.Task.status == "open").count()

    warnings = [w for w in [stale_warning, import_warning] if w]

    return {
        "generated_at": now.isoformat(),
        "scheduler": {
            "state": scheduler_state,
            "heartbeat_at": heartbeat_row.updated_at.isoformat() if heartbeat_row else None,
        },
        "last_schedule_run": {
            "status": last_schedule_run.status if last_schedule_run else None,
            "created_at": last_schedule_run.created_at.isoformat() if last_schedule_run else None,
        },
        "last_import": {
            "file_name": last_import.file_name if last_import else None,
            "created_at": last_import.created_at.isoformat() if last_import else None,
            "quality_score": float(last_import.quality_score) if last_import else None,
        },
        "open_tasks": int(open_tasks),
        "warnings": warnings,
    }
