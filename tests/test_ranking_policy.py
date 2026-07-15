from __future__ import annotations

import os
import unittest
from pathlib import Path


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.ranking_policy import direction_groups_for_keywords, evaluate_teacher, score_text  # noqa: E402
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

EXPANDED_MATH_AI_PROFILE = StudentProfile(
    resume_match_context="math, statistics, and AI exploration",
    keyword_weights=[
        ("machine learning", 26),
        ("causal inference", 26),
        ("high-dimensional data analysis", 26),
        ("Bayesian statistics", 26),
        ("applied statistics", 16),
    ],
    institute_bonus=[],
    high_signal_terms={
        "machine learning",
        "causal inference",
        "high-dimensional data analysis",
        "bayesian statistics",
        "applied statistics",
    },
    source_path=Path("expanded-math-ai.json"),
    profile_hash="expanded-math-ai",
    is_demo=False,
    direction_term_groups={
        "statistics_methods": frozenset({"high-dimensional data analysis", "bayesian statistics", "applied statistics"}),
        "ai_methods": frozenset({"machine learning"}),
        "math_ai_bridges": frozenset({"causal inference"}),
    },
)

SINGLE_GROUP_PROFILE = StudentProfile(
    resume_match_context="statistics exploration",
    keyword_weights=[("Bayesian statistics", 26), ("high-dimensional data analysis", 26)],
    institute_bonus=[],
    high_signal_terms={"bayesian statistics", "high-dimensional data analysis"},
    source_path=Path("single-group.json"),
    profile_hash="single-group",
    is_demo=False,
    direction_term_groups={
        "statistics_methods": frozenset({"bayesian statistics", "high-dimensional data analysis"}),
    },
)


class RankingPolicyTests(unittest.TestCase):
    def test_expanded_math_ai_directions_create_auditable_exploration_anchors(self) -> None:
        cases = (
            ("machine learning", "ai_methods"),
            ("causal inference", "math_ai_bridges"),
            ("high-dimensional data analysis", "statistics_methods"),
            ("Bayesian statistics", "statistics_methods"),
        )
        for direction, expected_group in cases:
            with self.subTest(direction=direction):
                decision = evaluate_teacher({"研究方向": direction}, profile=EXPANDED_MATH_AI_PROFILE)
                self.assertTrue(decision.explicit_anchor)
                self.assertEqual(decision.level, "可以考虑")
                self.assertIn(expected_group, decision.matched_direction_groups)

    def test_multiple_independent_expanded_directions_can_be_strong(self) -> None:
        decision = evaluate_teacher(
            {"研究方向": "causal inference and high-dimensional data analysis"},
            profile=EXPANDED_MATH_AI_PROFILE,
        )
        self.assertEqual(decision.level, "强烈建议")
        self.assertEqual(set(decision.matched_direction_groups), {"statistics_methods", "math_ai_bridges"})

    def test_single_direction_group_without_auxiliary_evidence_is_capped_at_consider(self) -> None:
        decision = evaluate_teacher(
            {"研究方向": "Bayesian statistics and high-dimensional data analysis"},
            profile=SINGLE_GROUP_PROFILE,
        )
        self.assertEqual(decision.score, 52)
        self.assertEqual(decision.level, "可以考虑")
        self.assertTrue(any("单一画像方向组" in reason for reason in decision.reasons))

    def test_single_direction_group_can_be_strong_with_confirmed_publications(self) -> None:
        decision = evaluate_teacher(
            {"研究方向": "Bayesian statistics and high-dimensional data analysis"},
            profile=SINGLE_GROUP_PROFILE,
            publication={
                "status": "official:success/high",
                "confidence": "high",
                "keywords": "Bayesian statistics",
                "titles": "Bayesian statistics for complex data",
            },
        )
        self.assertEqual(decision.level, "强烈建议")
        self.assertGreater(decision.breakdown["publication"], 0)

    def test_broad_applied_statistics_or_big_data_alone_is_not_prioritized(self) -> None:
        broad = evaluate_teacher({"研究方向": "applied statistics"}, profile=EXPANDED_MATH_AI_PROFILE)
        generic = evaluate_teacher({"研究方向": "big data applications"}, profile=EXPANDED_MATH_AI_PROFILE)
        self.assertEqual(broad.level, "暂不优先")
        self.assertTrue(broad.explicit_anchor)
        self.assertEqual(generic.score, 0)
        self.assertFalse(generic.explicit_anchor)

    def test_direction_group_mapping_is_profile_driven(self) -> None:
        self.assertEqual(
            direction_groups_for_keywords(["machine learning", "causal inference"], EXPANDED_MATH_AI_PROFILE),
            ("ai_methods", "math_ai_bridges"),
        )

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

    def test_negative_publication_states_never_score(self) -> None:
        row = {"研究方向": "robot manipulation"}
        base = evaluate_teacher(row, profile=PROFILE)
        for status in (
            "official:no_record",
            "official:no_recent_record/high",
            "zbmath:no_candidate/high",
            "zbmath:identity_uncertain/high",
            "zbmath:review/high",
            "zbmath:rejected/high",
            "zbmath:unsuccessful/high",
        ):
            with self.subTest(status=status):
                decision = evaluate_teacher(
                    row,
                    profile=PROFILE,
                    publication={
                        "status": status,
                        "confidence": "high",
                        "keywords": "robot manipulation",
                        "titles": "Reliable Robot Manipulation",
                    },
                )
                self.assertEqual(decision.score, base.score)
                self.assertEqual(decision.breakdown["publication"], 0)


if __name__ == "__main__":
    unittest.main()
