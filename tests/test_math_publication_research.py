from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from tutor_recommendation.math_publication_research import (
    _collect_cached,
    _discovery_allows_deep_query,
    _row_with_discovered_source_id,
    _write_json,
    _write_jsonl,
    publication_profile_keywords,
    publication_relevance_labels,
    resolve_stage_output_dir,
)
from tutor_recommendation.publication_evidence import PublicationEvidenceResult


class MathPublicationResearchTests(unittest.TestCase):
    def test_transport_errors_are_not_written_to_semantic_cache(self):
        class FakeAdapter:
            source = "sample"
            cache_version = "sample-v1"

            def collect(self, row, **kwargs):
                return PublicationEvidenceResult("sample", "request_failed", reason="timeout")

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tutor_recommendation.math_publication_research.CACHE_DIR", Path(temp_dir)
        ):
            result = _collect_cached(FakeAdapter(), {"教师ID": "teacher_sample", "姓名": "Sample"})
            self.assertEqual(result["status"], "request_failed")
            self.assertEqual(list(Path(temp_dir).rglob("*.json")), [])

    def test_successful_results_are_reused_from_cache(self):
        class FakeAdapter:
            source = "sample"
            cache_version = "sample-v1"

            def __init__(self):
                self.calls = 0

            def collect(self, row, **kwargs):
                self.calls += 1
                return PublicationEvidenceResult("sample", "no_candidate", reason="none")

        adapter = FakeAdapter()
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "tutor_recommendation.math_publication_research.CACHE_DIR", Path(temp_dir)
        ):
            first = _collect_cached(adapter, {"教师ID": "teacher_sample", "姓名": "Sample"})
            second = _collect_cached(adapter, {"教师ID": "teacher_sample", "姓名": "Sample"})
        self.assertEqual(first, second)
        self.assertEqual(adapter.calls, 1)

    def test_valid_shadow_cache_can_seed_formal_cache(self):
        class FakeAdapter:
            source = "sample"
            cache_version = "sample-v1"

            def __init__(self):
                self.calls = 0

            def collect(self, row, **kwargs):
                self.calls += 1
                return PublicationEvidenceResult("sample", "request_failed", reason="should not run")

        adapter = FakeAdapter()
        row = {"教师ID": "teacher_sample", "姓名": "Sample"}
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            shadow = root / "_shadow" / "cache"
            formal = root / "formal"
            with patch("tutor_recommendation.math_publication_research.CACHE_DIR", shadow), patch(
                "tutor_recommendation.math_publication_research.SHADOW_CACHE_READ_DIR", None
            ):
                cached = _collect_cached(
                    type(
                        "SuccessAdapter",
                        (),
                        {
                            "source": "sample",
                            "cache_version": "sample-v1",
                            "collect": lambda self, row, **kwargs: PublicationEvidenceResult(
                                "sample", "no_candidate", reason="cached"
                            ),
                        },
                    )(),
                    row,
                )
            self.assertEqual(cached["status"], "no_candidate")
            with patch("tutor_recommendation.math_publication_research.CACHE_DIR", formal), patch(
                "tutor_recommendation.math_publication_research.SHADOW_CACHE_READ_DIR", shadow
            ):
                result = _collect_cached(adapter, row)
            self.assertEqual(result["status"], "no_candidate")
            self.assertEqual(adapter.calls, 0)
            self.assertEqual(len(list(formal.rglob("*.json"))), 1)

    def test_shadow_output_requires_explicit_shadow_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            formal = Path(temp_dir) / "formal" / "ruc" / "isbd"
            shadow = Path(temp_dir) / "_shadow" / "run-1"
            resolved = resolve_stage_output_dir(formal, str(shadow))
            self.assertEqual(resolved, shadow.resolve() / "ruc" / "isbd")
            with self.assertRaisesRegex(RuntimeError, "_shadow"):
                resolve_stage_output_dir(formal, str(Path(temp_dir) / "unsafe"))

    def test_only_medium_or_high_confirmed_discovery_allows_work_fetch(self):
        self.assertTrue(
            _discovery_allows_deep_query(
                {"status": "identity_probable", "confidence": "medium"}
            )
        )
        self.assertFalse(
            _discovery_allows_deep_query(
                {"status": "identity_uncertain", "confidence": "low"}
            )
        )
        self.assertFalse(
            _discovery_allows_deep_query(
                {"status": "no_candidate", "confidence": ""}
            )
        )

    def test_discovered_author_id_is_scoped_to_its_source(self):
        original = {"姓名": "示例教师"}
        updated = _row_with_discovered_source_id(
            original,
            {"source": "openalex", "author_id": "A123"},
        )
        self.assertNotIn("OpenAlex作者ID", original)
        self.assertEqual(updated["OpenAlex作者ID"], "A123")
        self.assertNotIn("zbMATH作者ID", updated)

    def test_relevance_labels_are_descriptive_and_profile_matches_use_title_only(self):
        profile = SimpleNamespace(
            keyword_weights=[("federated learning", 26), ("stochastic optimization", 10)],
            concept_alias_groups=(),
        )
        work = {
            "title": "Federated learning with stochastic optimization",
            "classifications": ["Machine learning"],
            "topics": ["Differential privacy"],
        }
        labels = publication_relevance_labels(work, profile=profile)
        self.assertIn("privacy_preserving_learning", labels)
        self.assertIn("distributed_learning", labels)
        self.assertIn("optimization_for_ai", labels)
        self.assertIn("federated learning", publication_profile_keywords(work, profile=profile))

        auxiliary_only = {
            "title": "A generic mathematical result",
            "topics": ["Federated learning"],
        }
        self.assertEqual(publication_profile_keywords(auxiliary_only, profile=profile), ())
        self.assertIn("uncertain", publication_relevance_labels(auxiliary_only, profile=profile))

    def test_private_audit_artifacts_are_atomic_json_and_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "report.json", [{"value": float("nan")}])
            _write_jsonl(root / "queue.jsonl", [{"teacher": "示例", "value": None}])
            self.assertEqual((root / "report.json").read_text(encoding="utf-8").strip(), '[\n  {\n    "value": null\n  }\n]')
            self.assertEqual(
                (root / "queue.jsonl").read_text(encoding="utf-8").strip(),
                '{"teacher": "示例", "value": null}',
            )
            self.assertEqual(list(root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
