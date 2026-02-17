from services.scheduler import build_scheduler


class DummySession:
    def close(self):
        pass


def _factory():
    return DummySession()


def test_build_scheduler_registers_tick_job():
    scheduler = build_scheduler(_factory)
    jobs = scheduler.get_jobs()

    assert len(jobs) == 1
    assert jobs[0].id == "rule_scheduler_tick"
