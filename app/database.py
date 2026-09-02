from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from .config import AppConfig
from .models import Candidate, Classification, IngestResult
from .normalize import core_title, dedupe_key, normalize_title, url_hash


CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> str:
    return datetime.now(CN_TZ).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str | Path, migrations_dir: str | Path | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = Path(migrations_dir) if migrations_dir else Path(__file__).resolve().parents[1] / "migrations"

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        migration = self.migrations_dir / "001_initial.sql"
        with self.connect() as conn:
            conn.executescript(migration.read_text(encoding="utf-8"))
            version = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
            if version is None or int(version["version"]) != 1:
                raise RuntimeError("不支持的数据库schema版本")

    def checkpoint(self) -> tuple[int, int, int]:
        """将WAL内容合并回主数据库，便于Git提交单个SQLite文件。"""
        if not self.path.exists():
            self.migrate()
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            row = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            return tuple(int(value) for value in row)
        finally:
            conn.close()

    def sync_config(self, config: AppConfig) -> None:
        current = now_cn()
        sources: dict[str, tuple[str, str, bool]] = {}
        for feed in config.feeds:
            sources[feed.source_id] = (feed.source_name, feed.region, True)
        with self.connect() as conn:
            for source_id, (name, region, enabled) in sources.items():
                conn.execute(
                    """
                    INSERT INTO sources(id, name, region, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name=excluded.name, region=excluded.region,
                        enabled=excluded.enabled, updated_at=excluded.updated_at
                    """,
                    (source_id, name, region, int(enabled), current, current),
                )
            for feed in config.feeds:
                conn.execute(
                    """
                    INSERT INTO feeds(id, source_id, list_url, parser_type, interval_min, enabled, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_id=excluded.source_id, list_url=excluded.list_url,
                        parser_type=excluded.parser_type, interval_min=excluded.interval_min,
                        enabled=excluded.enabled, updated_at=excluded.updated_at
                    """,
                    (feed.id, feed.source_id, feed.list_url, feed.parser_type, feed.interval_min, int(feed.enabled), current),
                )

    def is_initialized(self, feed_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT initialized_at FROM feeds WHERE id=?", (feed_id,)).fetchone()
            if row is None:
                raise KeyError(feed_id)
            return bool(row["initialized_at"])

    def mark_initialized(self, feed_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE feeds SET initialized_at=COALESCE(initialized_at, ?), updated_at=? WHERE id=?",
                (now_cn(), now_cn(), feed_id),
            )

    def find_related(self, title: str, threshold: float = 0.82) -> bool:
        target = core_title(title)
        if len(target) < 6:
            return False
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT canonical_title FROM announcements WHERE event_type IN ('首次机会', '重大变更') ORDER BY id DESC LIMIT 500"
            ).fetchall()
        for row in rows:
            known = core_title(str(row["canonical_title"]))
            if not known:
                continue
            if target == known or target in known or known in target:
                return True
            if SequenceMatcher(None, target, known).ratio() >= threshold:
                return True
        return False

    def ingest(
        self,
        candidate: Candidate,
        classification: Classification,
        create_delivery: bool,
        aggregation_window_min: int,
    ) -> IngestResult:
        current = now_cn()
        source_url_hash = url_hash(candidate.url)
        key = dedupe_key(candidate.title, classification.event_type, candidate.publish_date, candidate.source_name)
        with self.connect() as conn:
            existing_source = conn.execute(
                "SELECT announcement_id FROM announcement_sources WHERE source_id=? AND feed_id=? AND url_hash=?",
                (candidate.source_id, candidate.feed_id, source_url_hash),
            ).fetchone()
            if existing_source:
                announcement_id = int(existing_source["announcement_id"])
                conn.execute(
                    "UPDATE announcement_sources SET last_seen_at=? WHERE source_id=? AND feed_id=? AND url_hash=?",
                    (current, candidate.source_id, candidate.feed_id, source_url_hash),
                )
                conn.execute("UPDATE announcements SET last_seen_at=? WHERE id=?", (current, announcement_id))
                return IngestResult(announcement_id, False, False, False)

            row = conn.execute("SELECT id FROM announcements WHERE dedupe_key=?", (key,)).fetchone()
            created_announcement = row is None
            if row is None:
                cursor = conn.execute(
                    """
                    INSERT INTO announcements(
                        dedupe_key, canonical_title, category, region, event_type,
                        fresh_grad_scope, contains_education_posts, push_policy,
                        change_link_status, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        normalize_title(candidate.title),
                        classification.category,
                        classification.region,
                        classification.event_type,
                        classification.fresh_grad_scope,
                        classification.contains_education_posts,
                        classification.push_policy,
                        classification.change_link_status,
                        current,
                        current,
                    ),
                )
                announcement_id = int(cursor.lastrowid)
            else:
                announcement_id = int(row["id"])
                conn.execute("UPDATE announcements SET last_seen_at=? WHERE id=?", (current, announcement_id))

            conn.execute(
                """
                INSERT INTO announcement_sources(
                    announcement_id, source_id, feed_id, source_name, raw_title,
                    url, url_hash, publish_date, discovered_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    announcement_id,
                    candidate.source_id,
                    candidate.feed_id,
                    candidate.source_name,
                    candidate.title,
                    candidate.url,
                    source_url_hash,
                    candidate.publish_date,
                    current,
                    current,
                ),
            )

            created_delivery = False
            if create_delivery and created_announcement and classification.push_policy == "即时":
                available = (datetime.now(CN_TZ) + timedelta(minutes=max(0, aggregation_window_min))).isoformat(timespec="seconds")
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO deliveries(
                        announcement_id, destination, delivery_type, status,
                        available_at, created_at, updated_at
                    ) VALUES (?, 'feishu', 'immediate', 'pending', ?, ?, ?)
                    """,
                    (announcement_id, available, current, current),
                )
                created_delivery = cursor.rowcount == 1
            return IngestResult(announcement_id, created_announcement, True, created_delivery)

    def record_run(
        self,
        feed_id: str,
        started_at: str,
        status: str,
        item_count: int,
        accepted_count: int,
        new_count: int,
        http_status: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> int:
        current = now_cn()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO source_runs(
                    feed_id, started_at, finished_at, http_status, item_count,
                    accepted_count, new_count, status, error_type, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (feed_id, started_at, current, http_status, item_count, accepted_count, new_count, status, error_type, error_message),
            )
            if status == "success":
                conn.execute(
                    "UPDATE feeds SET consecutive_failures=0, last_success_at=?, last_error_type=NULL, updated_at=? WHERE id=?",
                    (current, current, feed_id),
                )
                return 0
            conn.execute(
                "UPDATE feeds SET consecutive_failures=consecutive_failures+1, last_error_type=?, updated_at=? WHERE id=?",
                (error_type, current, feed_id),
            )
            row = conn.execute("SELECT consecutive_failures FROM feeds WHERE id=?", (feed_id,)).fetchone()
            return int(row["consecutive_failures"]) if row else 0

    def pending_deliveries(self, limit: int = 10) -> list[dict[str, object]]:
        current = now_cn()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id AS delivery_id, d.attempt_count, a.*
                FROM deliveries d
                JOIN announcements a ON a.id=d.announcement_id
                WHERE d.status IN ('pending', 'retry') AND d.available_at<=?
                ORDER BY d.id LIMIT ?
                """,
                (current, limit),
            ).fetchall()
            result: list[dict[str, object]] = []
            for row in rows:
                item = dict(row)
                source_rows = conn.execute(
                    """
                    SELECT source_name, raw_title, url, publish_date
                    FROM announcement_sources WHERE announcement_id=? ORDER BY id
                    """,
                    (row["id"],),
                ).fetchall()
                item["sources"] = [dict(source) for source in source_rows]
                result.append(item)
            return result

    def mark_deliveries_sent(self, delivery_ids: list[int]) -> None:
        if not delivery_ids:
            return
        current = now_cn()
        placeholders = ",".join("?" for _ in delivery_ids)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE deliveries SET status='sent', sent_at=?, updated_at=? WHERE id IN ({placeholders})",
                (current, current, *delivery_ids),
            )

    def mark_deliveries_failed(self, delivery_ids: list[int], error: str) -> None:
        current = now_cn()
        with self.connect() as conn:
            for delivery_id in delivery_ids:
                row = conn.execute("SELECT attempt_count FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
                attempts = (int(row["attempt_count"]) if row else 0) + 1
                status = "failed" if attempts >= 3 else "retry"
                available = (datetime.now(CN_TZ) + timedelta(minutes=min(30, 2**attempts))).isoformat(timespec="seconds")
                conn.execute(
                    """
                    UPDATE deliveries SET status=?, attempt_count=?, available_at=?,
                        last_error=?, updated_at=? WHERE id=?
                    """,
                    (status, attempts, available, error[:500], current, delivery_id),
                )

    def health_snapshot(self) -> dict[str, int]:
        with self.connect() as conn:
            enabled = int(conn.execute("SELECT COUNT(*) FROM feeds WHERE enabled=1").fetchone()[0])
            failed = int(conn.execute("SELECT COUNT(*) FROM feeds WHERE enabled=1 AND consecutive_failures>0").fetchone()[0])
            today = datetime.now(CN_TZ).date().isoformat()
            new_count = int(
                conn.execute("SELECT COUNT(*) FROM announcements WHERE substr(first_seen_at,1,10)=?", (today,)).fetchone()[0]
            )
        return {"enabled_feeds": enabled, "successful_feeds": enabled - failed, "failed_feeds": failed, "new_announcements": new_count}
