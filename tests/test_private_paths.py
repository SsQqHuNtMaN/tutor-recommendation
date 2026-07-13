from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tutor_recommendation import private_paths


class PrivatePathTests(unittest.TestCase):
    def test_prefers_new_private_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            preferred = root / "user_private/overrides/example.json"
            legacy = root / "data/private/example.json"
            preferred.parent.mkdir(parents=True)
            legacy.parent.mkdir(parents=True)
            preferred.write_text("{}", encoding="utf-8")
            legacy.write_text("{}", encoding="utf-8")
            with patch.object(private_paths, "PROJECT_ROOT", root):
                self.assertEqual(private_paths.private_file("example.json"), preferred)

    def test_falls_back_to_legacy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "data/private/example.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text("{}", encoding="utf-8")
            with patch.object(private_paths, "PROJECT_ROOT", root):
                self.assertEqual(private_paths.private_file("example.json"), legacy)


if __name__ == "__main__":
    unittest.main()
