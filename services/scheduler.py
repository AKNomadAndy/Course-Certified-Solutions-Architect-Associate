from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from services.health import upsert_health_status
from services.rules_engine import scheduler_tick


@dataclass
class _Job:
    id: str


class _FallbackScheduler:
    def __init__(self):
        self._jobs: list[_Job] = []
        self.running = False

    def add_job(self, func, trigger, minutes, id, replace_existing, coalesce, max_instances, args):  # noqa: A002
        if replace_existing:
            self._jobs = [j for j in self._jobs if j.id != id]
        self._jobs.append(_Job(id=id))

    def get_jobs(self):
        return list(self._jobs)

    def start(self):
        self.running = True


try:
    from apscheduler.schedulers.background import BackgroundScheduler as _RealScheduler
except Exception:
    _RealScheduler = None


def run_scheduled_tick(session_factory):
    session = session_factory()
    try:
        runs = scheduler_tick(session)
        upsert_health_status(
            session,
            "scheduler_heartbeat",
            {
                "last_tick_at": datetime.utcnow().isoformat(),
                "status": "ok",
                "run_count": len(runs),
            },
        )
    except Exception as exc:
        upsert_health_status(
            session,
            "scheduler_heartbeat",
            {
                "last_tick_at": datetime.utcnow().isoformat(),
                "status": "error",
                "error": str(exc),
            },
        )
        raise
    finally:
        session.close()


def _new_scheduler():
    if _RealScheduler is None:
        return _FallbackScheduler()
    return _RealScheduler(timezone="UTC")


def build_scheduler(session_factory):
    scheduler = _new_scheduler()
    scheduler.add_job(
        run_scheduled_tick,
        "interval",
        minutes=60,
        id="rule_scheduler_tick",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        args=[session_factory],
    )
    return scheduler


def start_local_scheduler(session_factory):
    scheduler = build_scheduler(session_factory)
    scheduler.start()
    return scheduler
