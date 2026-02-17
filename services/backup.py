from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from db.engine import DATABASE_URL

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except Exception:  # pragma: no cover - handled by callers
    Fernet = None
    PBKDF2HMAC = None
    hashes = None


SNAPSHOT_DIR = Path("snapshots")
BACKUP_DIR = Path("backups")


@dataclass
class BackupResult:
    path: str
    bytes_written: int
    created_at: str


def _db_path() -> Path:
    if DATABASE_URL.startswith("sqlite:///"):
        return Path(DATABASE_URL.replace("sqlite:///", ""))
    raise ValueError("Only sqlite:/// DATABASE_URL is supported for local backup/recovery")


def _derive_fernet(passphrase: str, salt: bytes) -> Fernet:
    if Fernet is None or PBKDF2HMAC is None or hashes is None:
        raise RuntimeError("cryptography is required for encrypted backup/restore")
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key)


def create_db_snapshot(reason: str = "manual", db_path: str | None = None) -> BackupResult:
    source = Path(db_path) if db_path else _db_path()
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = SNAPSHOT_DIR / f"snapshot-{stamp}-{reason}.sqlite3"
    data = source.read_bytes()
    out.write_bytes(data)
    return BackupResult(path=str(out), bytes_written=len(data), created_at=stamp)


def create_encrypted_backup(passphrase: str, label: str = "manual", db_path: str | None = None) -> BackupResult:
    if not passphrase:
        raise ValueError("passphrase is required")

    source = Path(db_path) if db_path else _db_path()
    if not source.exists():
        raise FileNotFoundError(f"Database file not found: {source}")

    raw = source.read_bytes()
    salt = os.urandom(16)
    token = _derive_fernet(passphrase, salt).encrypt(raw)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = BACKUP_DIR / f"flowledger-backup-{stamp}-{label}.enc"
    out.write_bytes(salt + token)
    return BackupResult(path=str(out), bytes_written=len(token) + len(salt), created_at=stamp)


def restore_encrypted_backup(backup_path: str, passphrase: str, db_path: str | None = None, snapshot_before_restore: bool = True):
    if not passphrase:
        raise ValueError("passphrase is required")

    source = Path(backup_path)
    if not source.exists():
        raise FileNotFoundError(f"Backup file not found: {source}")

    target = Path(db_path) if db_path else _db_path()
    payload = source.read_bytes()
    if len(payload) <= 16:
        raise ValueError("Invalid backup payload")
    salt, token = payload[:16], payload[16:]
    plain = _derive_fernet(passphrase, salt).decrypt(token)

    snapshot = None
    if snapshot_before_restore and target.exists():
        snapshot = create_db_snapshot(reason="before_restore", db_path=str(target))

    target.write_bytes(plain)
    return {
        "restored_to": str(target),
        "bytes_restored": len(plain),
        "snapshot": snapshot.path if snapshot else None,
    }


def list_backups(limit: int = 20) -> list[str]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("*.enc"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in files[:limit]]


def latest_backup() -> str | None:
    items = list_backups(limit=1)
    return items[0] if items else None
