from __future__ import annotations

import unittest
from pathlib import Path

from app.config import load_config
from app.models import Candidate
from app.rules import RuleEngine


ROOT = Path(__file__).resolve().parents[1]


def candidate(title: str, recruitment_context: bool = True) -> Candidate:
    return Candidate(
        source_id="hnrsks",
        source_name="河南省人事考试中心",
        feed_id="hnrsks_home",
        region="省级",
        title=title,
        url="https://www.hnrsks.com/test/article.html",
        publish_date="2026-08-31",
        recruitment_context=recruitment_context,
    )


class RuleEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = RuleEngine(load_config(ROOT / "config").rules)

    def test_exam_admission_is_not_missed(self) -> None:
        result = self.engine.classify(candidate("河南省2026年度统一考试录用公务员公告"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.category, "公务员")
        self.assertEqual(result.event_type, "首次机会")

    def test_xuanpin_is_whitelisted(self) -> None:
        result = self.engine.classify(candidate("某事业单位2026年公开选聘工作人员公告"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.category, "事业单位")

    def test_selection_and_teacher_special_are_excluded(self) -> None:
        self.assertFalse(self.engine.classify(candidate("河南省2026年定向选调生公告")).accepted)
        self.assertFalse(self.engine.classify(candidate("某学校2026年公开招聘教师公告")).accepted)

    def test_mixed_recruitment_is_retained(self) -> None:
        result = self.engine.classify(candidate("河南省2026年事业单位公开招聘联考公告（含教育岗位）"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.contains_education_posts, "是")

    def test_major_change_fail_open_in_recruitment_feed(self) -> None:
        result = self.engine.classify(candidate("关于某事业单位报名延期的公告"), related_to_existing=False)
        self.assertTrue(result.accepted)
        self.assertEqual(result.event_type, "重大变更")
        self.assertEqual(result.change_link_status, "未关联原事项")

    def test_major_change_without_recruitment_context_is_not_pushed(self) -> None:
        result = self.engine.classify(candidate("关于会议延期的公告", recruitment_context=False), related_to_existing=False)
        self.assertFalse(result.accepted)

    def test_process_notice_is_daily_only(self) -> None:
        result = self.engine.classify(candidate("某事业单位公开招聘面试人员公示"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.event_type, "一般流程")
        self.assertEqual(result.push_policy, "仅日报")


if __name__ == "__main__":
    unittest.main()
