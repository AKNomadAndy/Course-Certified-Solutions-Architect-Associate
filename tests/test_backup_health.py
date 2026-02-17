from datetime import datetime, timedelta
from pathlib import Path

import pytest

from db import models
from services.backup import create_db_snapshot, create_encrypted_backup, restore_encrypted_backup
from services.health import build_health_report, upsert_health_status


def test_encrypted_backup_and_restore_roundtrip(tmp_path):
    pytest.importorskip("cryptography")

    db_file = tmp_path / "sample.sqlite3"
    db_file.write_bytes(b"hello-flowledger")

    out = create_encrypted_backup(passphrase="secret", label="test", db_path=str(db_file))
    assert Path(out.path).exists()

    db_file.write_bytes(b"mutated")
    restore_encrypted_backup(out.path, passphrase="secret", db_path=str(db_file), snapshot_before_restore=False)

    assert db_file.read_bytes() == b"hello-flowledger"


def test_create_snapshot(tmp_path):
    db_file = tmp_path / "sample.sqlite3"
    db_file.write_bytes(b"db-content")

    snap = create_db_snapshot(reason="unit", db_path=str(db_file))
    assert Path(snap.path).exists()


def test_health_report_with_heartbeat(session):
    now = datetime.utcnow()
    upsert_health_status(session, "scheduler_heartbeat", {"status": "ok"})
    row = session.query(models.SystemHealthStatus).filter(models.SystemHealthStatus.key == "scheduler_heartbeat").one()
    row.updated_at = now - timedelta(minutes=20)

    session.add(models.ImportRun(file_name="recent.csv", quality_score=90.0, summary={}))
    session.commit()

    report = build_health_report(session)
    assert report["scheduler"]["state"] == "healthy"
    assert isinstance(report["warnings"], list)
