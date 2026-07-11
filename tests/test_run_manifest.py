from __future__ import annotations

import os
import unittest
from dataclasses import replace


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.run_manifest import checkpoint_fingerprint, create_run_context  # noqa: E402


class RunManifestTests(unittest.TestCase):
    def test_policy_change_invalidates_checkpoint(self) -> None:
        row = {"姓名": "Example", "教师主页链接": "https://example.edu/faculty/a", "研究方向": "robot"}
        context = create_run_context("final", "school_college")
        changed = replace(context, policy_version="changed")
        first = checkpoint_fingerprint(row, "school", "college", context)
        second = checkpoint_fingerprint(row, "school", "college", changed)
        self.assertNotEqual(first, second)

    def test_direction_change_invalidates_checkpoint(self) -> None:
        context = create_run_context("final", "school_college")
        first = checkpoint_fingerprint(
            {"姓名": "Example", "教师主页链接": "https://example.edu/faculty/a", "研究方向": "robot"},
            "school",
            "college",
            context,
        )
        second = checkpoint_fingerprint(
            {"姓名": "Example", "教师主页链接": "https://example.edu/faculty/a", "研究方向": "nlp"},
            "school",
            "college",
            context,
        )
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
