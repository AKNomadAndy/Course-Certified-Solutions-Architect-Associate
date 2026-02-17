#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from services.backup import latest_backup, restore_encrypted_backup


def main() -> int:
    parser = argparse.ArgumentParser(description="One-command local disaster recovery for FlowLedger")
    parser.add_argument("--backup", default="latest", help="Path to encrypted backup file, or 'latest'")
    parser.add_argument("--passphrase", required=True, help="Backup passphrase")
    args = parser.parse_args()

    backup_path = latest_backup() if args.backup == "latest" else args.backup
    if not backup_path:
        print("No backup found. Create one in Settings -> Backup & Disaster Recovery first.")
        return 1

    result = restore_encrypted_backup(backup_path=backup_path, passphrase=args.passphrase, snapshot_before_restore=True)
    print(f"Restored database to: {result['restored_to']}")
    if result.get("snapshot"):
        print(f"Pre-restore snapshot: {result['snapshot']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
