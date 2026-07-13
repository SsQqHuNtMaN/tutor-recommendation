from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tutor_recommendation.cli import main


class AgentCliTests(unittest.TestCase):
    def test_registered_target_check_succeeds(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["targets", "--check", "sjtu_cs"])
        self.assertEqual(code, 0)
        self.assertIn('"key": "sjtu_cs"', output.getvalue())

    def test_missing_target_routes_agent_to_workflow(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["targets", "--check", "missing_college"])
        self.assertEqual(code, 2)
        self.assertIn("target_missing=missing_college", output.getvalue())
        self.assertIn("agent_workflow=", output.getvalue())

    def test_legacy_wrappers_live_outside_repository_root(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "tutor.py").is_file())
        self.assertTrue((root / "scripts/legacy/build_teacher_match.py").is_file())
        self.assertFalse((root / "build_teacher_match.py").exists())


if __name__ == "__main__":
    unittest.main()
