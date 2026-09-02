from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.database import Database
from app.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[1]


class PipelineTest(unittest.TestCase):
    def test_run_enabled_feeds_only_runs_enabled_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "monitor.db"
            pipeline = Pipeline(ROOT / "config", db_path, aggregation_window_min=0)
            summaries = pipeline.run_enabled_feeds(
                {"hnrsks_home": ROOT / "tests/fixtures/hnrsks_home.html"}
            )
            self.assertEqual([item.feed_id for item in summaries], ["hnrsks_home"])
            self.assertEqual(summaries[0].status, "success")
            self.assertEqual(len(Database(db_path).checkpoint()), 3)

    def test_cold_start_then_new_item_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "monitor.db"
            pipeline = Pipeline(ROOT / "config", db_path, aggregation_window_min=0)
            baseline = pipeline.run_feed("hnrsks_home", ROOT / "tests/fixtures/hnrsks_home.html")
            self.assertEqual(baseline.status, "success")
            self.assertFalse(baseline.initialized_before)
            self.assertEqual(baseline.deliveries_created, 0)

            new_fixture = Path(tmp) / "new.html"
            new_fixture.write_text(
                '<meta charset="utf-8"><a href="/test/article-new.html">河南省2027年度统一考试录用公务员公告</a><span>2026-08-31</span>',
                encoding="utf-8",
            )
            second = pipeline.run_feed("hnrsks_home", new_fixture)
            self.assertTrue(second.initialized_before)
            self.assertEqual(second.deliveries_created, 1)
            third = pipeline.run_feed("hnrsks_home", new_fixture)
            self.assertEqual(third.deliveries_created, 0)

            pending = Database(db_path).pending_deliveries()
            self.assertEqual(len(pending), 1)


if __name__ == "__main__":
    unittest.main()
