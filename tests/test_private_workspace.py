from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tutor_recommendation import private_workspace


class PrivateWorkspaceTests(unittest.TestCase):
    def workspace(self, root: Path):
        private_root = root / "user_private"
        template = root / "student_profile.example.json"
        template.write_text(
            json.dumps(
                {
                    "resume_match_context": "demo",
                    "keyword_weights": [["robotics", 10]],
                    "institute_bonus": [],
                    "high_signal_terms": ["robotics"],
                }
            ),
            encoding="utf-8",
        )
        return patch.multiple(
            private_workspace,
            PRIVATE_ROOT=private_root,
            SOURCE_DIR=private_root / "source",
            PROFILE_DIR=private_root / "profile",
            OVERRIDES_DIR=private_root / "overrides",
            PROFILE_PATH=private_root / "profile/student_profile.json",
            DRAFT_PROFILE_PATH=private_root / "profile/student_profile.draft.json",
            REQUEST_PATH=private_root / "request.md",
            REQUEST_EXAMPLE_PATH=root / "request.example.md",
            PROFILE_TEMPLATE_PATH=template,
        )

    def test_profile_init_creates_blocked_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.workspace(root):
                draft = private_workspace.initialize_profile_draft()
                payload = json.loads(draft.read_text(encoding="utf-8"))
                self.assertTrue(payload["_draft_requires_confirmation"])
                self.assertTrue((root / "user_private/source").is_dir())

    def test_text_material_is_extracted_to_local_draft(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.workspace(root):
                private_workspace.ensure_private_workspace()
                source = root / "user_private/source/resume.txt"
                source.write_text("robot learning and control", encoding="utf-8")
                draft, sources = private_workspace.extract_profile_draft()
                payload = json.loads(draft.read_text(encoding="utf-8"))
                self.assertEqual(sources, [source])
                self.assertIn("robot learning and control", payload["resume_match_context"])
                self.assertTrue(payload["_draft_requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
