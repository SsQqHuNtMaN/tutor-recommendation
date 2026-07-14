from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tutor_recommendation import profile_registry
from tutor_recommendation.teacher_match_targets import TargetConfig


class ProfileRegistryTests(unittest.TestCase):
    def test_named_profiles_and_active_selection_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            private_root = root / "user_private"
            profiles_root = private_root / "profiles"
            profile_path = profiles_root / "student-a" / "student_profile.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                json.dumps({"_profile_id": "student-a", "display_name": "学生 A"}, ensure_ascii=False),
                encoding="utf-8",
            )
            with (
                patch.object(profile_registry, "PROJECT_ROOT", root),
                patch.object(profile_registry, "PRIVATE_ROOT", private_root),
                patch.object(profile_registry, "PROFILES_ROOT", profiles_root),
                patch.object(profile_registry, "ACTIVE_PROFILE_PATH", private_root / "active_profile.json"),
                patch.object(profile_registry, "LEGACY_PROFILE_PATHS", (private_root / "missing.json",)),
            ):
                ref = profile_registry.resolve_profile("student-a")
                self.assertEqual(ref.display_name, "学生 A")
                self.assertEqual(ref.output_root, root / "outputs/by_profile/student-a")
                selected = profile_registry.set_active_profile("student-a")
                self.assertEqual(selected.profile_id, "student-a")
                self.assertEqual(profile_registry.active_profile_id(), "student-a")

    def test_target_paths_follow_configured_profile_output_root(self) -> None:
        target = TargetConfig(
            key="example",
            school_slug="school",
            college_slug="math",
            school_name="示例大学",
            college_name="数学学院",
            directory_url="https://example.edu/math",
            affiliation_keywords=("example",),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "outputs/by_profile/student-a"
            with patch.dict(os.environ, {"TUTOR_OUTPUT_ROOT": str(output_root)}, clear=False):
                self.assertEqual(target.output_dir, output_root / "school/math")
                self.assertEqual(target.final_path.parent, output_root / "school/math")

    def test_evidence_path_switches_without_changing_legacy_dblp_targets(self) -> None:
        computer = TargetConfig(
            key="computer", school_slug="school", college_slug="cs",
            school_name="示例大学", college_name="计算机学院",
            directory_url="https://example.edu/cs", affiliation_keywords=("example",),
        )
        mathematics = TargetConfig(
            key="mathematics", school_slug="school", college_slug="math",
            school_name="示例大学", college_name="数学学院",
            directory_url="https://example.edu/math", affiliation_keywords=("example",),
            evidence_profile="mathematics_ai", publication_window_years=5,
        )
        self.assertTrue(computer.evidence_path.name.endswith("_dblp.xlsx"))
        self.assertTrue(mathematics.evidence_path.name.endswith("_publications.xlsx"))


if __name__ == "__main__":
    unittest.main()
