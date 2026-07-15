from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.student_profile import (  # noqa: E402
    ProfileConfigurationError,
    load_student_profile,
)


class StudentProfileTests(unittest.TestCase):
    def test_missing_formal_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with self.assertRaises(ProfileConfigurationError):
                load_student_profile(missing, allow_template=False)

    def test_demo_profile_requires_explicit_opt_in(self) -> None:
        profile = load_student_profile(allow_template=True)
        self.assertTrue(profile.is_demo)
        self.assertTrue(profile.keyword_weights)

    def test_explicit_missing_profile_never_falls_back_to_demo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with self.assertRaises(ProfileConfigurationError):
                load_student_profile(missing, allow_template=True)

    def test_invalid_profile_does_not_merge_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(json.dumps({"resume_match_context": "x"}), encoding="utf-8")
            with self.assertRaises(ProfileConfigurationError):
                load_student_profile(path, allow_template=False)

    def test_core_terms_must_have_positive_weight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "resume_match_context": "test",
                        "keyword_weights": [["robot", 0]],
                        "institute_bonus": [],
                        "high_signal_terms": ["robot"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ProfileConfigurationError):
                load_student_profile(path, allow_template=False)

    def test_unconfirmed_draft_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "_draft_requires_confirmation": True,
                        "resume_match_context": "test",
                        "keyword_weights": [["robot", 10]],
                        "institute_bonus": [],
                        "high_signal_terms": ["robot"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ProfileConfigurationError):
                load_student_profile(path, allow_template=False)

    def test_direction_term_groups_load_only_known_positive_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "resume_match_context": "test",
                        "keyword_weights": [["causal inference", 26]],
                        "institute_bonus": [],
                        "high_signal_terms": ["causal inference"],
                        "direction_term_groups": {"math_ai_bridges": ["causal inference"]},
                    }
                ),
                encoding="utf-8",
            )
            profile = load_student_profile(path, allow_template=False)
            self.assertEqual(profile.direction_term_groups["math_ai_bridges"], frozenset({"causal inference"}))

    def test_direction_term_groups_reject_unknown_or_duplicate_terms(self) -> None:
        for groups in (
            {"ai_methods": ["unknown"]},
            {"ai_methods": ["machine learning"], "math_ai_bridges": ["machine learning"]},
        ):
            with self.subTest(groups=groups), tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "profile.json"
                path.write_text(
                    json.dumps(
                        {
                            "resume_match_context": "test",
                            "keyword_weights": [["machine learning", 26]],
                            "institute_bonus": [],
                            "high_signal_terms": ["machine learning"],
                            "direction_term_groups": groups,
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(ProfileConfigurationError):
                    load_student_profile(path, allow_template=False)


if __name__ == "__main__":
    unittest.main()
