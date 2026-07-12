from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tutor_recommendation import viewer_server


class ViewerDataCacheTests(unittest.TestCase):
    def test_summary_records_do_not_embed_evidence_details(self) -> None:
        target_name, target = next(iter(viewer_server.TARGETS.items()))
        raw = {"姓名": "示例教师", "教师主页链接": "https://example.edu/teacher"}
        base = {
            "_targetKey": target_name,
            "schoolSlug": target.school_slug,
            "collegeSlug": target.college_slug,
            "schoolName": target.school_name,
            "collegeName": target.college_name,
            "sourcePath": str(target.final_path),
            "raw": raw,
            "key": "teacher-key",
        }
        with (
            patch.object(viewer_server, "base_records", return_value=[base]),
            patch.object(viewer_server, "load_status_store", return_value={"statuses": {}}),
        ):
            record = viewer_server.build_records()[0]
        self.assertNotIn("dblp", record)
        self.assertNotIn("arxiv", record)
        self.assertNotIn("web", record)
        self.assertNotIn("webSearch", record)

    def test_summary_cache_round_trip_requires_matching_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            cache_path = output_dir / ".viewer_summary_cache.json"
            signature = (("target", "outputs/example.xlsx", 123, 456),)
            records = [{"_targetKey": "target", "key": "teacher", "raw": {"姓名": "示例教师"}}]
            with (
                patch.object(viewer_server, "OUTPUTS_DIR", output_dir),
                patch.object(viewer_server, "SUMMARY_CACHE_PATH", cache_path),
            ):
                viewer_server.save_summary_cache(signature, records)
                self.assertEqual(viewer_server.load_summary_cache(signature), records)
                self.assertIsNone(
                    viewer_server.load_summary_cache((("target", "outputs/example.xlsx", 124, 456),))
                )

    def test_detail_payload_returns_only_requested_teacher(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workbook = Path(temp_dir) / "example.xlsx"
            workbook.write_bytes(b"placeholder")
            raw = {"姓名": "示例教师", "教师主页链接": "https://example.edu/teacher"}
            record = {"key": "teacher-key", "sourcePath": str(workbook), "raw": raw}
            indexes = {
                "dblp": {"示例教师": [{**raw, "题名": "Paper"}]},
                "arxiv": {"示例教师": []},
                "web": {"示例教师": [{**raw, "证据": "Evidence"}]},
                "webSearch": {"示例教师": []},
            }
            with (
                patch.object(viewer_server, "data_payload", return_value={"records": [record]}),
                patch.object(viewer_server, "detail_indexes_for_path", return_value=indexes),
            ):
                payload = viewer_server.detail_payload("teacher-key")
                self.assertIsNone(viewer_server.detail_payload("missing-key"))
            self.assertIsNotNone(payload)
            self.assertEqual(payload["dblp"][0]["题名"], "Paper")
            self.assertEqual(payload["web"][0]["证据"], "Evidence")


if __name__ == "__main__":
    unittest.main()
