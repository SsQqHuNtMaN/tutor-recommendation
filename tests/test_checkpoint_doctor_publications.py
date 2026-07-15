from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tutor_recommendation.checkpoint_doctor import audit_publication_workbook


class CheckpointDoctorPublicationTests(unittest.TestCase):
    def test_math_publication_audit_reports_seed_and_trace_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "publications.xlsx"
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                pd.DataFrame([{"教师ID": "teacher_sample", "论文身份种子哈希": "a" * 64}]).to_excel(
                    writer, sheet_name="全量教师名录", index=False
                )
                pd.DataFrame(
                    [{"教师ID": "teacher_sample", "题名": "Paper", "规范论文ID": "doi:10.1/x", "证据URL": "https://example.test"}]
                ).to_excel(writer, sheet_name="数学文献近五年明细", index=False)
                pd.DataFrame([{"教师ID": "teacher_sample", "候选决策": "review", "是否需人工复核": "是"}]).to_excel(
                    writer, sheet_name="学术作者候选", index=False
                )
                pd.DataFrame([{"教师ID": "teacher_sample", "来源": "openalex", "状态": "success"}]).to_excel(
                    writer, sheet_name="论文来源报告", index=False
                )
            report = audit_publication_workbook(path)
        self.assertTrue(report["ok"])
        self.assertEqual(report["identity_seed_coverage"], 1)
        self.assertEqual(report["review_queue"], 1)
        self.assertEqual(report["source_status"], {"openalex|success": 1})


if __name__ == "__main__":
    unittest.main()
