"""Back up, rehearse, and apply the idempotent v0.5 private DB migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from yuanjian_app.cognition import CognitionService
from yuanjian_app.database import Database


PRESERVED_TABLES = (
    "forecasts",
    "forecast_versions",
    "signals",
    "knowledge_documents",
    "external_items",
)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def counts(path):
    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if table in tables
            else 0
            for table in PRESERVED_TABLES
        }


def integrity(path):
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]


def online_backup(source, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"yuanjian-pre-v0.5-{stamp}.db"
    with closing(sqlite3.connect(source)) as original, closing(
        sqlite3.connect(target)
    ) as destination:
        original.backup(destination)
    return target


def migration_stats(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        levels = {
            row["evidence_level"]: row["amount"]
            for row in connection.execute(
                "SELECT evidence_level,COUNT(*) AS amount FROM event_clusters GROUP BY evidence_level"
            )
        }
        return {
            "clusters": connection.execute(
                "SELECT COUNT(*) FROM event_clusters"
            ).fetchone()[0],
            "relations": connection.execute(
                "SELECT COUNT(*) FROM event_cluster_items"
            ).fetchone()[0],
            "independent_domains_max": connection.execute(
                "SELECT COALESCE(MAX(independent_domains),0) FROM event_clusters"
            ).fetchone()[0],
            "evidence_levels": levels,
            "needs_judgment": connection.execute(
                "SELECT COUNT(*) FROM event_clusters WHERE needs_judgment=1"
            ).fetchone()[0],
            "personal_impacts": connection.execute(
                "SELECT COUNT(*) FROM personal_impacts"
            ).fetchone()[0],
        }


def rehearse(backup):
    with tempfile.TemporaryDirectory() as temporary:
        rehearsal = Path(temporary) / "yuanjian-rehearsal.db"
        shutil.copy2(backup, rehearsal)
        before = counts(rehearsal)
        database = Database(rehearsal)
        database.initialize()
        cognition = CognitionService(database)
        first = cognition.backfill_unclustered(limit=10_000)
        first_stats = migration_stats(rehearsal)
        second = cognition.backfill_unclustered(limit=10_000)
        second_stats = migration_stats(rehearsal)
        after = counts(rehearsal)
        if before != after:
            raise RuntimeError("rehearsal_preserved_counts_changed")
        if first_stats != second_stats or second["processed"] != 0:
            raise RuntimeError("rehearsal_backfill_not_idempotent")
        return {
            "preserved_before": before,
            "preserved_after": after,
            "first_backfill": first,
            "second_backfill": second,
            "stats": second_stats,
            "integrity": integrity(rehearsal),
        }


def apply_migration(source):
    before = counts(source)
    database = Database(source)
    database.initialize()
    cognition = CognitionService(database)
    first = cognition.backfill_unclustered(limit=10_000)
    stats = migration_stats(source)
    second = cognition.backfill_unclustered(limit=10_000)
    after = counts(source)
    if before != after:
        raise RuntimeError("private_preserved_counts_changed")
    if second["processed"] != 0:
        raise RuntimeError("private_backfill_not_idempotent")
    return {
        "preserved_before": before,
        "preserved_after": after,
        "first_backfill": first,
        "second_backfill": second,
        "stats": stats,
        "integrity": integrity(source),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if args.apply:
        report = {"mode": "apply", "source": str(source), **apply_migration(source)}
    else:
        if args.backup_dir is None:
            parser.error("--backup-dir is required unless --apply is used")
        backup = online_backup(source, args.backup_dir.resolve())
        report = {
            "mode": "backup_and_rehearsal",
            "backup": str(backup),
            "backup_sha256": sha256(backup),
            "backup_integrity": integrity(backup),
            "rehearsal": rehearse(backup),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
