from __future__ import annotations

import unittest

from app.delivery import build_card


class DeliveryTest(unittest.TestCase):
    def test_unknown_fresh_grad_label_is_hidden_and_change_warning_is_shown(self) -> None:
        payload = build_card([
            {
                "category": "事业单位",
                "region": "省级",
                "fresh_grad_scope": "未知",
                "change_link_status": "未关联原事项",
                "sources": [{
                    "source_name": "河南省人事考试中心",
                    "raw_title": "某事业单位招聘延期公告",
                    "url": "https://www.hnrsks.com/test/article.html",
                    "publish_date": "2026-08-31",
                }],
            }
        ])
        rendered = str(payload)
        self.assertNotIn("应届生：未知", rendered)
        self.assertIn("未关联原事项", rendered)


if __name__ == "__main__":
    unittest.main()
