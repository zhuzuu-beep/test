from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GitHubDeploymentTest(unittest.TestCase):
    def test_daily_workflow_has_required_safety_controls(self) -> None:
        workflow = (ROOT / ".github/workflows/daily-monitor.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("if: always()", workflow)
        self.assertIn("state/recruit_monitor.db", workflow)
        self.assertIn("secrets.FEISHU_WEBHOOK_URL", workflow)
        self.assertNotIn("https://open.feishu.cn/open-apis/bot/v2/hook/", workflow)


if __name__ == "__main__":
    unittest.main()
