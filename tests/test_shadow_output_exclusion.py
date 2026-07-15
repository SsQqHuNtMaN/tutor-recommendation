from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tutor_recommendation.migrate_contact_status_column import iter_current_workbooks


class ShadowOutputExclusionTests(unittest.TestCase):
    def test_contact_migration_does_not_scan_shadow_workbooks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            formal = root / "outputs" / "ruc" / "isbd" / "formal.xlsx"
            shadow = root / "outputs" / "by_profile" / "sample" / "_shadow" / "run" / "shadow.xlsx"
            formal.parent.mkdir(parents=True)
            shadow.parent.mkdir(parents=True)
            formal.touch()
            shadow.touch()
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                paths = iter_current_workbooks()
            finally:
                os.chdir(old_cwd)
        self.assertEqual(paths, [Path("outputs/ruc/isbd/formal.xlsx")])


if __name__ == "__main__":
    unittest.main()
