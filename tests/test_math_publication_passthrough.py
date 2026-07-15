from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import tutor_recommendation.teacher_research_completion as completion


class MathPublicationPassthroughTests(unittest.TestCase):
    def test_math_detail_dedup_uses_canonical_id(self):
        frame = pd.DataFrame(
            columns=["教师ID", "规范论文ID", "年份", "题名", "DOI"]
        )
        self.assertEqual(
            completion.publication_detail_dedup_columns(frame, is_math=True),
            ["教师ID", "规范论文ID"],
        )

    def test_additive_diagnostic_sheets_are_loaded_when_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "stage2.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame([{"教师ID": "teacher_sample", "候选状态": "identity_uncertain"}]).to_excel(
                    writer, sheet_name="学术作者候选", index=False
                )
                pd.DataFrame([{"教师ID": "teacher_sample", "状态": "success"}]).to_excel(
                    writer, sheet_name="论文来源报告", index=False
                )
            with patch.object(completion, "INPUT_PATH", path), patch.object(
                completion, "IS_MATH_EVIDENCE", True
            ):
                sheets = completion.load_math_diagnostic_sheets()
        self.assertEqual(sheets["学术作者候选"].iloc[0]["候选状态"], "identity_uncertain")
        self.assertEqual(sheets["论文来源报告"].iloc[0]["状态"], "success")

    def test_old_stage2_without_diagnostic_sheets_returns_empty_frames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "stage2.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame([{"教师ID": "teacher_sample"}]).to_excel(
                    writer, sheet_name="数学文献近五年明细", index=False
                )
            with patch.object(completion, "INPUT_PATH", path), patch.object(
                completion, "IS_MATH_EVIDENCE", True
            ):
                sheets = completion.load_math_diagnostic_sheets()
        self.assertTrue(all(frame.empty for frame in sheets.values()))


if __name__ == "__main__":
    unittest.main()
