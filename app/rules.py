from __future__ import annotations

from typing import Any

from .models import Candidate, Classification


IMMEDIATE = "即时"
DAILY = "仅日报"
DISCARD = "丢弃"


class RuleEngine:
    def __init__(self, rules: dict[str, Any]):
        self.rules = rules

    @staticmethod
    def _hits(text: str, terms: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        return tuple(term for term in terms if term and term in text)

    def has_major_change_term(self, title: str) -> bool:
        return bool(self._hits(title, self.rules["major_change_terms"]))

    def _hard_exclusion(self, title: str) -> tuple[bool, str, str]:
        selection_hits = self._hits(title, self.rules["selection_exclude"])
        if selection_hits:
            return True, "命中选调生或公开遴选排除项", "否"

        volunteer_hits = self._hits(title, self.rules.get("other_exclude", []))
        if volunteer_hits:
            return True, "命中其他排除项", "否"

        has_education = "教师" in title or "教育岗位" in title
        comprehensive = any(term in title for term in self.rules.get("mixed_recruitment_markers", []))
        teacher_hits = self._hits(title, self.rules["teacher_exclude"])
        if teacher_hits and not comprehensive:
            return True, "命中教师专项招聘排除项", "是"
        return False, "", "是" if has_education else "否"

    def classify(self, candidate: Candidate, related_to_existing: bool = False) -> Classification:
        title = candidate.title
        excluded, reason, contains_education = self._hard_exclusion(title)
        if excluded:
            return Classification(
                accepted=False,
                event_type="无关信息",
                category="其他",
                region=candidate.region,
                fresh_grad_scope=self._fresh_grad_scope(title),
                contains_education_posts=contains_education,
                push_policy=DISCARD,
                reason=reason,
            )

        whitelist_hits = self._hits(title, self.rules["whitelist"])
        major_hits = self._hits(title, self.rules["major_change_terms"])
        process_hits = self._hits(title, self.rules["process_terms"])
        category = self._category(title)
        fresh_scope = self._fresh_grad_scope(title)

        if fresh_scope == "不面向":
            return Classification(
                accepted=False,
                event_type="无关信息",
                category=category,
                region=candidate.region,
                fresh_grad_scope=fresh_scope,
                contains_education_posts=contains_education,
                push_policy=DISCARD,
                reason="标题明确排除应届生",
            )

        if major_hits:
            recruitment_signal = related_to_existing or candidate.recruitment_context or bool(whitelist_hits)
            if recruitment_signal:
                return Classification(
                    accepted=True,
                    event_type="重大变更",
                    category=category,
                    region=candidate.region,
                    fresh_grad_scope=fresh_scope,
                    contains_education_posts=contains_education,
                    push_policy=IMMEDIATE,
                    change_link_status="已关联" if related_to_existing else "未关联原事项",
                    reason="重大变更命中，按招聘语境兜底推送",
                    matched_terms=major_hits,
                )
            return Classification(
                accepted=False,
                event_type="无关信息",
                category=category,
                region=candidate.region,
                fresh_grad_scope=fresh_scope,
                contains_education_posts=contains_education,
                push_policy=DISCARD,
                reason="重大变更词缺少招聘语境",
                matched_terms=major_hits,
            )

        if process_hits and (candidate.recruitment_context or bool(whitelist_hits)):
            return Classification(
                accepted=True,
                event_type="一般流程",
                category=category,
                region=candidate.region,
                fresh_grad_scope=fresh_scope,
                contains_education_posts=contains_education,
                push_policy=DAILY,
                reason="招聘专栏中的一般流程公告",
                matched_terms=process_hits,
            )

        if whitelist_hits:
            return Classification(
                accepted=True,
                event_type="首次机会",
                category=category,
                region=candidate.region,
                fresh_grad_scope=fresh_scope,
                contains_education_posts=contains_education,
                push_policy=IMMEDIATE,
                reason="命中招聘白名单",
                matched_terms=whitelist_hits,
            )

        return Classification(
            accepted=False,
            event_type="无关信息",
            category=category,
            region=candidate.region,
            fresh_grad_scope=fresh_scope,
            contains_education_posts=contains_education,
            push_policy=DISCARD,
            reason="未命中招聘白名单",
        )

    def _category(self, title: str) -> str:
        categories: list[tuple[str, list[str]]] = self.rules.get("category_terms", [])
        for category, terms in categories:
            if self._hits(title, terms):
                return category
        return "其他"

    def _fresh_grad_scope(self, title: str) -> str:
        if self._hits(title, self.rules.get("fresh_grad_exclude_terms", [])):
            return "不面向"
        if self._hits(title, self.rules.get("fresh_grad_explicit_terms", [])):
            return "明确面向"
        if self._hits(title, self.rules.get("fresh_grad_partial_terms", [])):
            return "部分包含"
        return "未知"
