from __future__ import annotations

import os
import re
import unittest

os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.publication_adapters import OfficialPublicationAdapter
from tutor_recommendation.publication_evidence import (
    PublicationRecord,
    canonicalize_publications,
    looks_like_publication_record,
    normalize_arxiv_id,
    normalize_doi,
    norm_text,
    official_publications,
    split_publication_entries,
)
from tutor_recommendation.math_publication_research import _evidence_columns


class PublicationEvidenceTests(unittest.TestCase):
    def test_identifiers_and_latex_titles_are_normalized(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.1000/ABC.1"), "10.1000/abc.1")
        self.assertEqual(normalize_arxiv_id("arXiv:2401.01234v2"), "2401.01234")
        record = PublicationRecord("arxiv", r"A $\mathbf{Robust}$ Method", arxiv_id="2401.01234v2")
        self.assertEqual(record.to_dict()["normalized_title"], "arobustmethod")

    def test_canonicalization_merges_preprint_and_formal_version(self) -> None:
        records = [
            PublicationRecord(
                "arxiv",
                "A Robust Optimization Method for Learning",
                2024,
                authors=("Sample Author",),
                arxiv_id="2401.01234v2",
                is_preprint=True,
                source_id="2401.01234",
            ),
            PublicationRecord(
                "openalex",
                "A Robust Optimization Method for Learning",
                2025,
                doi="https://doi.org/10.1000/ROBUST.1",
                authors=("Sample Author", "Coauthor"),
                venue="Example Journal",
                source_id="W123",
            ),
        ]
        works = canonicalize_publications(records)
        self.assertEqual(len(works), 1)
        self.assertEqual(works[0].canonical_id, "doi:10.1000/robust.1")
        self.assertEqual(works[0].arxiv_id, "2401.01234")
        self.assertFalse(works[0].is_preprint)
        self.assertEqual(set(works[0].sources), {"arxiv", "openalex"})

    def test_fuzzy_title_does_not_merge_without_author_overlap(self) -> None:
        records = [
            PublicationRecord("zbmath", "A Statistical Learning Method for Networks", 2024, authors=("A",)),
            PublicationRecord("openalex", "A Statistical Learning Method for Network", 2024, authors=("B",)),
        ]
        self.assertEqual(len(canonicalize_publications(records)), 2)

    def test_missing_spreadsheet_values_do_not_become_publications(self) -> None:
        for value in (None, "", "  ", "nan", "NaT", "<NA>", float("nan")):
            with self.subTest(value=repr(value)):
                self.assertEqual(norm_text(value), "")
                self.assertEqual(split_publication_entries(value), ())
                self.assertEqual(official_publications({"官方论文列表": value}), ())

    def test_record_gate_rejects_career_awards_and_projects(self) -> None:
        row = {
            "官方论文来源": "https://faculty.example.edu/sample",
            "官方论文列表": "\n".join(
                [
                    "Sample A. A privacy-aware optimization method. Journal of Examples, 2025.",
                    "2024-08至今，示例大学，副主任",
                    "示例大学优秀科研成果奖（一等奖），2023",
                    "隐私保护优化研究，2022-2025，示例基金项目，主持。",
                    "Sample B. A second method. arXiv:2501.01234.",
                ]
            ),
        }
        records = official_publications(row)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].year, 2025)
        self.assertEqual(records[1].year, None)
        self.assertTrue(all(record.url == row["官方论文来源"] for record in records))

    def test_numbered_publications_are_split_without_splitting_doi(self) -> None:
        text = (
            "1. First paper. Journal A, 2024. "
            "2. Second paper. Journal B, 2025. doi:10.1234/example.2"
        )
        entries = split_publication_entries(text)
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(looks_like_publication_record(entry) for entry in entries))
        records = official_publications({"官方论文列表": text})
        self.assertEqual([record.year for record in records], [2024, 2025])
        self.assertEqual(records[1].doi, "10.1234/example.2")

    def test_chinese_year_followed_by_issue_marker_is_recognized(self) -> None:
        for text in (
            "赵某，数字化统计研究，统计研究，2020年第5期。",
            "赵某，空间统计应用研究，统计研究2017年5期。",
        ):
            with self.subTest(text=text):
                records = official_publications({"官方论文列表": text})
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0].year, int(re.search(r"20\d{2}", text).group(0)))

    def test_official_adapter_distinguishes_recent_old_and_invalid_records(self) -> None:
        adapter = OfficialPublicationAdapter()
        recent = adapter.collect(
            {"官方论文列表": "Sample A. A recent method. Journal A, 2025."},
            start_year=2022,
            end_year=2026,
        )
        old = adapter.collect(
            {"官方论文列表": "Sample A. An older method. Journal A, 2019."},
            start_year=2022,
            end_year=2026,
        )
        unknown_year = adapter.collect(
            {"官方论文列表": "Sample A. A preprint. arXiv:2501.01234."},
            start_year=2022,
            end_year=2026,
        )
        invalid = adapter.collect(
            {"官方论文列表": "2024-08至今，示例大学，副主任"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(recent.status, "success")
        self.assertEqual(len(recent.works), 1)
        self.assertEqual(old.status, "no_recent_record")
        self.assertEqual(old.works, ())
        self.assertEqual(old.metadata["available_records"], 1)
        self.assertEqual(unknown_year.status, "no_recent_record")
        self.assertEqual(invalid.status, "no_record")

    def test_no_recent_external_identity_is_preserved_without_publication_count(self) -> None:
        columns = _evidence_columns(
            [
                {"source": "official", "status": "no_record", "works": []},
                {
                    "source": "zbmath",
                    "status": "no_recent_record",
                    "confidence": "high",
                    "author_id": "sample.author",
                    "author_url": "https://zbmath.org/authors/?q=ai:sample.author",
                    "orcid": "0000-0001",
                    "works": [],
                },
            ]
        )
        self.assertEqual(columns["学术作者匹配置信度"], "high")
        self.assertEqual(columns["学术作者ID"], "sample.author")
        self.assertEqual(columns["ORCID"], "0000-0001")
        self.assertEqual(columns["近五年论文数"], 0)
        self.assertEqual(columns["论文证据来源"], "")


if __name__ == "__main__":
    unittest.main()
