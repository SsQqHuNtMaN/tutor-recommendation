from __future__ import annotations

import os
import unittest
from pathlib import Path


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.ranking_policy import evaluate_teacher, score_text  # noqa: E402
from tutor_recommendation.student_profile import StudentProfile  # noqa: E402


PROFILE = StudentProfile(
    resume_match_context="test",
    keyword_weights=[("robot manipulation", 30), ("robot", 24), ("llm", 0), ("vision", 5)],
    institute_bonus=[],
    high_signal_terms={"robot manipulation", "robot"},
    source_path=Path("test.json"),
    profile_hash="test-profile",
    is_demo=False,
    concept_alias_groups=(("robot", "robotic"),),
)

ALIAS_PROFILE = StudentProfile(
    resume_match_context="test",
    keyword_weights=[("robot", 24), ("robotic", 24)],
    institute_bonus=[],
    high_signal_terms={"robot", "robotic"},
    source_path=Path("test.json"),
    profile_hash="test-alias-profile",
    is_demo=False,
    concept_alias_groups=(("robot", "robotic"),),
)


class RankingPolicyTests(unittest.TestCase):
    def test_profile_excluded_direction_is_reported_and_not_prioritized(self) -> None:
        profile = StudentProfile(
            resume_match_context="optimization for learning",
            keyword_weights=[("convex optimization", 10)],
            institute_bonus=[],
            high_signal_terms={"convex optimization"},
            source_path=Path("excluded-profile.json"),
            profile_hash="excluded-profile",
            is_demo=False,
            excluded_terms=frozenset({"functional analysis"}),
        )
        decision = evaluate_teacher({"研究方向": "functional analysis"}, profile=profile)
        self.assertEqual(decision.level, "暂不优先")
        self.assertTrue(any("排除方向" in warning for warning in decision.warnings))

    def test_zero_weight_never_scores(self) -> None:
        score, keywords = score_text("LLM and large models", profile=PROFILE)
        self.assertEqual(score, 0)
        self.assertEqual(keywords, [])

    def test_concept_alias_group_scores_only_once(self) -> None:
        score, keywords = score_text("robot and robotic systems", profile=ALIAS_PROFILE)
        self.assertEqual(score, 24)
        self.assertEqual(keywords, ["robotic"])

    def test_external_evidence_cannot_create_priority_without_anchor(self) -> None:
        row = {"研究方向": "machine learning"}
        decision = evaluate_teacher(
            row,
            profile=PROFILE,
            dblp={"confidence": "高", "keywords": "robot manipulation", "titles": "robot manipulation"},
            arxiv={"置信度": "中-DBLP交叉确认", "关键词": "robot"},
            web_search={
                "WebSearch状态": "人工确认-本地证据",
                "WebSearch置信度": "高",
                "WebSearch关键词": "robot manipulation",
                "人工确认": True,
            },
        )
        self.assertEqual(decision.level, "暂不优先")
        self.assertEqual(decision.can_contact, "否")
        self.assertFalse(decision.explicit_anchor)

    def test_official_anchor_can_enter_priority(self) -> None:
        decision = evaluate_teacher({"研究方向": "robot manipulation"}, profile=PROFILE)
        self.assertEqual(decision.level, "可以考虑")
        self.assertTrue(decision.explicit_anchor)
        self.assertTrue(decision.reasons)

    def test_explicit_direction_sentence_in_official_biography_is_an_anchor(self) -> None:
        decision = evaluate_teacher(
            {"个人简介摘要": "当前主要研究方向包括 robot manipulation、computer vision。曾在企业工作。"},
            profile=PROFILE,
        )
        self.assertTrue(decision.explicit_anchor)
        self.assertEqual(decision.level, "可以考虑")

    def test_automatic_web_search_does_not_change_score(self) -> None:
        row = {"研究方向": "robot manipulation"}
        base = evaluate_teacher(row, profile=PROFILE)
        searched = evaluate_teacher(
            row,
            profile=PROFILE,
            web_search={
                "WebSearch状态": "已搜索",
                "WebSearch置信度": "高",
                "WebSearch关键词": "robot manipulation",
            },
        )
        self.assertEqual(base.score, searched.score)
        self.assertEqual(base.level, searched.level)

    def test_medium_dblp_does_not_affect_rank(self) -> None:
        row = {"研究方向": "robot manipulation"}
        base = evaluate_teacher(row, profile=PROFILE)
        medium = evaluate_teacher(
            row,
            profile=PROFILE,
            dblp={"confidence": "中", "keywords": "robot manipulation"},
        )
        self.assertEqual(base.score, medium.score)

    def test_confirmed_math_publications_only_enhance_an_official_anchor(self) -> None:
        evidence = {
            "status": "official:success; zbmath:success/medium",
            "confidence": "medium",
            "keywords": "robot manipulation",
            "titles": "Reliable Robot Manipulation",
            "classifications": "90C25",
        }
        anchored = {"研究方向": "robot manipulation"}
        base = evaluate_teacher(anchored, profile=PROFILE)
        enhanced = evaluate_teacher(anchored, profile=PROFILE, publication=evidence)
        self.assertGreater(enhanced.score, base.score)
        self.assertGreater(enhanced.breakdown["publication"], 0)

        unanchored = {"研究方向": "computer science"}
        decision = evaluate_teacher(unanchored, profile=PROFILE, publication=evidence)
        self.assertEqual(decision.breakdown["publication"], 0)
        self.assertEqual(decision.can_contact, "否")


if __name__ == "__main__":
    unittest.main()
