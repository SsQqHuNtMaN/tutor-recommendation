from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.contact_status import empty_store, load_status_store, save_status_store  # noqa: E402


class ContactStatusTests(unittest.TestCase):
    def test_missing_store_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = load_status_store(Path(temp_dir) / "missing.json")
        self.assertEqual(store["statuses"], {})
        self.assertEqual(store["version"], 3)

    def test_corrupt_store_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "status.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                load_status_store(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_atomic_save_writes_valid_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "status.json"
            save_status_store(empty_store(), path)
            loaded = load_status_store(path)
        self.assertEqual(loaded["version"], 3)


if __name__ == "__main__":
    unittest.main()
