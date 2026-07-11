from __future__ import annotations

import os
import unittest


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.first_pass_research import (  # noqa: E402
    deduplicate_targets_rows,
    seu_affiliations_for_detail,
)
from tutor_recommendation.teacher_match_targets import TARGETS  # noqa: E402


class SeuAffiliationTests(unittest.TestCase):
    def test_department_and_profile_can_create_multiple_college_affiliations(self) -> None:
        detail = {
            "姓名": "示例教师",
            "教师主页链接": "https://cs.seu.edu.cn/example/main.htm",
            "官方系别": "计算机科学系",
            "_seu_profile_text": "我正在招收如下学院的硕士生：计算机科学与工程学院、软件学院。",
        }

        affiliations = seu_affiliations_for_detail(detail, [])

        self.assertEqual(set(affiliations), {"seu_cse", "seu_software"})
        self.assertEqual(affiliations["seu_cse"]["status"], "官方确认")
        self.assertEqual(affiliations["seu_software"]["method"], "导师主页明确表述")

    def test_unresolved_shared_directory_entry_is_marked_for_review(self) -> None:
        detail = {
            "姓名": "示例教师",
            "教师主页链接": "https://cs.seu.edu.cn/example/main.htm",
            "官方系别": "",
            "_seu_profile_text": "研究方向为分布式系统。",
        }

        affiliations = seu_affiliations_for_detail(detail, [])

        self.assertEqual(set(affiliations), {"seu_cse"})
        self.assertEqual(affiliations["seu_cse"]["status"], "待复核")

    def test_education_history_does_not_create_current_college_affiliation(self) -> None:
        detail = {
            "姓名": "示例教师",
            "教师主页链接": "https://cs.seu.edu.cn/example/main.htm",
            "官方系别": "计算机工程系",
            "_seu_profile_text": "曾在东南大学软件学院取得学士和硕士学位，现为计算机科学与工程学院副教授。",
        }

        affiliations = seu_affiliations_for_detail(detail, [])

        self.assertEqual(set(affiliations), {"seu_cse"})

    def test_private_override_can_add_cross_college_membership(self) -> None:
        detail = {
            "姓名": "示例教师",
            "教师主页链接": "https://cs.seu.edu.cn/example/main.htm",
            "官方系别": "计算机工程系",
            "_seu_profile_text": "",
        }
        overrides = [
            {
                "name": "示例教师",
                "teacher_url": "https://cs.seu.edu.cn/example/main.htm",
                "targets": ["seu_ai"],
                "evidence": "人工核对招生系统",
                "sources": ["https://example.edu/source"],
            }
        ]

        affiliations = seu_affiliations_for_detail(detail, overrides)

        self.assertEqual(set(affiliations), {"seu_cse", "seu_ai"})
        self.assertEqual(affiliations["seu_ai"]["status"], "人工确认")

    def test_cross_college_identity_is_preserved_for_overlap_group(self) -> None:
        row = {
            "姓名": "示例教师",
            "教师主页链接": "https://cs.seu.edu.cn/example/main.htm",
        }
        configs = [TARGETS["seu_cse"], TARGETS["seu_software"]]

        result = deduplicate_targets_rows(
            {"seu_cse": [dict(row)], "seu_software": [dict(row)]},
            configs,
        )

        self.assertEqual(len(result["seu_cse"]), 1)
        self.assertEqual(len(result["seu_software"]), 1)
        self.assertIn("跨目标多学院归属保留", result["seu_cse"][0]["去重备注"])


if __name__ == "__main__":
    unittest.main()
