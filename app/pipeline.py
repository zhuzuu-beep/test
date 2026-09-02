from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

from .config import AppConfig, load_config
from .database import Database, now_cn
from .fetcher import FetchError, fetch
from .models import RunSummary
from .parser import decode_html, parse_candidates
from .rules import RuleEngine


LOGGER = logging.getLogger(__name__)


class Pipeline:
    def __init__(
        self,
        config_dir: str | Path,
        db_path: str | Path,
        aggregation_window_min: int = 0,
    ):
        self.config: AppConfig = load_config(config_dir)
        self.db = Database(db_path)
        self.db.migrate()
        self.db.sync_config(self.config)
        self.engine = RuleEngine(self.config.rules)
        self.aggregation_window_min = max(0, aggregation_window_min)

    def run_enabled_feeds(
        self,
        fixture_paths: Mapping[str, str | Path] | None = None,
    ) -> list[RunSummary]:
        """依次运行所有已启用栏目，单个栏目失败不阻断其余栏目。"""
        fixtures = fixture_paths or {}
        return [
            self.run_feed(feed.id, fixtures.get(feed.id))
            for feed in self.config.enabled_feeds()
        ]

    def run_feed(self, feed_id: str, fixture_path: str | Path | None = None) -> RunSummary:
        feed = self.config.feed(feed_id)
        started_at = now_cn()
        initialized_before = self.db.is_initialized(feed_id)
        summary = RunSummary(
            feed_id=feed_id,
            status="running",
            initialized_before=initialized_before,
            initialized_after=initialized_before,
        )
        http_status: int | None = None
        try:
            if fixture_path:
                body = Path(fixture_path).read_bytes()
                content_type = "text/html; charset=utf-8"
                http_status = 200
            else:
                fetched = fetch(feed)
                body = fetched.body
                content_type = fetched.content_type
                http_status = fetched.status
            html = decode_html(body, content_type, feed.encoding)
            candidates = parse_candidates(html, feed)
            summary.parsed = len(candidates)
            if len(candidates) < feed.min_items:
                raise ValueError(f"解析条目数{len(candidates)}低于健康阈值{feed.min_items}")

            for candidate in candidates:
                related = self.db.find_related(candidate.title) if self.engine.has_major_change_term(candidate.title) else False
                classification = self.engine.classify(candidate, related_to_existing=related)
                if classification.accepted:
                    summary.accepted += 1
                else:
                    summary.discarded += 1
                ingested = self.db.ingest(
                    candidate,
                    classification,
                    create_delivery=initialized_before,
                    aggregation_window_min=self.aggregation_window_min,
                )
                summary.new_announcements += int(ingested.created_announcement)
                summary.new_sources += int(ingested.created_source)
                summary.deliveries_created += int(ingested.created_delivery)

            if not initialized_before:
                self.db.mark_initialized(feed_id)
            summary.initialized_after = True
            summary.status = "success"
            self.db.record_run(
                feed_id,
                started_at,
                "success",
                summary.parsed,
                summary.accepted,
                summary.new_announcements,
                http_status=http_status,
            )
            LOGGER.info("feed_run_success %s", summary.as_dict())
            return summary
        except (FetchError, OSError, ValueError) as exc:
            error_type = type(exc).__name__
            summary.status = "failed"
            summary.error_type = error_type
            summary.error_message = str(exc)
            summary.failure_count = self.db.record_run(
                feed_id,
                started_at,
                "failed",
                summary.parsed,
                summary.accepted,
                summary.new_announcements,
                http_status=http_status,
                error_type=error_type,
                error_message=str(exc),
            )
            LOGGER.error("feed_run_failed %s", summary.as_dict())
            return summary
