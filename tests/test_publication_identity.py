from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tutor_recommendation.publication_identity import (
    build_publication_identity_seed,
    generated_name_aliases,
    identity_query_names,
    load_publication_identity_overrides,
    official_publication_name_candidates,
)


class PublicationIdentityTests(unittest.TestCase):
    def test_public_example_override_schema_is_valid(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "templates"
            / "publication_identity_overrides.example.json"
        )
        overrides = load_publication_identity_overrides(path)
        self.assertIn("teacher_example123", overrides)

    def test_generated_chinese_name_aliases_are_recall_only_variants(self) -> None:
        aliases = generated_name_aliases("张琼")
        self.assertIn("qiong zhang", aliases)
        self.assertIn("zhang qiong", aliases)

    def test_external_identity_queries_are_bounded(self) -> None:
        names = identity_query_names(
            {
                "英文姓名": "Qiong Zhang",
                "英文姓名别名": "Zhang Qiong; Q. Zhang; Zhang, Qiong",
                "姓名": "张琼",
            }
        )
        self.assertEqual(names, ("Qiong Zhang", "Zhang Qiong"))

    def test_official_publication_author_string_adds_a_recall_candidate(self) -> None:
        candidates = official_publication_name_candidates(
            "张琼",
            "Qiong Zhang, Known Coauthor. A privacy-aware method. Journal of Examples, 2025.",
        )
        self.assertEqual(candidates, ("Qiong Zhang",))

    def test_unrelated_latin_name_is_not_claimed_from_publication_text(self) -> None:
        candidates = official_publication_name_candidates(
            "张琼",
            "John Smith. A privacy-aware method. Journal of Examples, 2025.",
        )
        self.assertEqual(candidates, ())

    def test_override_requires_stable_teacher_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "overrides.json"
            path.write_text(json.dumps({"targets": [{"name": "示例教师"}]}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "requires teacher_id"):
                load_publication_identity_overrides(path)

    def test_confirmed_override_requires_reviewable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "overrides.json"
            path.write_text(
                json.dumps({"targets": [{"teacher_id": "teacher_sample", "review_status": "confirmed"}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "requires evidence"):
                load_publication_identity_overrides(path)

    def test_override_builds_auditable_identity_seed_and_query_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "overrides.json"
            path.write_text(
                json.dumps(
                    {
                        "targets": [
                            {
                                "teacher_id": "teacher_sample",
                                "canonical_english_name": "Qiong Zhang",
                                "aliases": ["Zhang Qiong"],
                                "affiliations": ["Renmin University of China"],
                                "orcid": "https://orcid.org/0000-0001",
                                "source_ids": {
                                    "openalex": "A123",
                                    "zbmath": "zhang.qiong",
                                    "dblp": "12/3456"
                                },
                                "rejected_source_ids": {
                                    "openalex": ["A999"],
                                    "zbmath": ["wrong.author"]
                                },
                                "known_titles": ["A Known Paper"],
                                "known_coauthors": ["Known Coauthor"],
                                "review_status": "confirmed",
                                "evidence": ["https://faculty.example.edu/qiong-zhang"]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            overrides = load_publication_identity_overrides(path)
        seed = build_publication_identity_seed(
            {
                "教师ID": "teacher_sample",
                "姓名": "张琼",
                "教师主页链接": "https://faculty.example.edu/qiong-zhang",
                "官方论文列表": "Qiong Zhang. A Known Paper. Journal A, 2025.",
            },
            school_slug="ruc",
            college_slug="isbd",
            overrides=overrides,
        )
        self.assertEqual(seed.canonical_english_name, "Qiong Zhang")
        self.assertEqual(seed.orcid, "0000-0001")
        self.assertEqual(seed.openalex_id, "A123")
        self.assertEqual(seed.rejected_openalex_ids, ("A999",))
        self.assertEqual(seed.rejected_zbmath_author_ids, ("wrong.author",))
        self.assertEqual(seed.review_status, "confirmed")
        self.assertIn("Zhang Qiong", seed.aliases)
        self.assertIn("A Known Paper", seed.known_titles)
        fields = seed.query_fields()
        self.assertEqual(fields["英文姓名"], "Qiong Zhang")
        self.assertEqual(len(fields["论文身份种子哈希"]), 64)
        self.assertEqual(identity_query_names(fields)[0], "Qiong Zhang")


if __name__ == "__main__":
    unittest.main()
