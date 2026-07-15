from __future__ import annotations

import unittest
import requests

from tutor_recommendation.publication_adapters import OpenAlexAdapter, ZbMathAdapter


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payloads.pop(0))


class PublicationAdapterTests(unittest.TestCase):
    def test_private_rejection_short_circuits_external_sources(self):
        session = FakeSession([])
        row = {"姓名": "Sample Author", "论文身份审核状态": "rejected"}
        zbmath = ZbMathAdapter(session).collect(row, start_year=2022, end_year=2026)
        openalex = OpenAlexAdapter(session, api_key="").collect(row, start_year=2022, end_year=2026)
        self.assertEqual(zbmath.status, "identity_rejected")
        self.assertEqual(openalex.status, "identity_rejected")
        self.assertEqual(session.calls, [])

    def test_openalex_without_key_is_explicit_and_does_not_call_network(self):
        session = FakeSession([])
        result = OpenAlexAdapter(session, api_key="").collect(
            {"姓名": "示例教师"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "not_configured")
        self.assertEqual(session.calls, [])

    def test_zbmath_uses_v1_search_and_title_overlap_for_identity(self):
        session = FakeSession(
            [
                {"result": [{"code": "sample.author", "name": "Sample Author"}]},
                {
                    "result": [{
                        "title": {"title": "A Privacy-Aware Distributed Optimization Method"},
                        "year": 2025,
                        "contributors": {"authors": [{"name": "Sample Author"}]},
                        "links": [],
                        "msc": [{"code": "90C25"}],
                    }]
                },
            ]
        )
        result = ZbMathAdapter(session).collect(
            {
                "姓名": "Sample Author",
                "官方论文列表": "A Privacy-Aware Distributed Optimization Method. 2025.",
                "官方论文来源": "https://faculty.example.edu/sample",
            },
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.works[0].classifications, ("90C25",))
        self.assertTrue(all("/v1/" in url for url, _ in session.calls))
        self.assertEqual(session.calls[0][1]["params"]["search_string"], 'au:"Sample Author"')
        self.assertEqual(session.calls[1][1]["params"]["search_string"], "ia:sample.author py:2022-2026")

    def test_zbmath_name_only_candidate_remains_untrusted(self):
        session = FakeSession(
            [
                {"result": [{"code": "common.name", "name": "Common Name"}]},
                {"result": [{"title": {"title": "Unrelated Algebra Paper"}, "year": 2024}]},
            ]
        )
        result = ZbMathAdapter(session).collect(
            {"姓名": "Common Name"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "identity_uncertain")
        self.assertEqual(result.confidence, "low")

    def test_zbmath_discovery_does_not_fetch_works(self):
        session = FakeSession(
            [{"result": [{"code": "common.name", "name": "Common Name"}]}]
        )
        result = ZbMathAdapter(session).collect(
            {"姓名": "Common Name"},
            start_year=2022,
            end_year=2026,
            discovery_only=True,
        )
        self.assertEqual(result.status, "identity_uncertain")
        self.assertEqual(result.works, ())
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(result.metadata["discovery_only"])

    def test_zbmath_confirmed_id_skips_name_search(self):
        session = FakeSession([{"result": []}])
        result = ZbMathAdapter(session).collect(
            {"姓名": "Sample Author", "zbMATH作者ID": "sample.author"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(len(session.calls), 1)
        self.assertIn("/document/_search", session.calls[0][0])

    def test_zbmath_document_404_is_no_recent_after_schema_confirmed(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: FakeResponse({}, status_code=404)
        adapter = ZbMathAdapter(session)
        adapter.works_schema_confirmed = True
        result = adapter.collect(
            {"姓名": "Sample Author", "zbMATH作者ID": "sample.author"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")
        self.assertEqual(result.confidence, "high")

    def test_zbmath_document_404_uses_schema_probe_before_no_recent(self):
        session = FakeSession([{}, {"result": []}])
        session.responses = [
            FakeResponse({}, status_code=404),
            FakeResponse({"result": []}),
        ]
        session.get = lambda url, **kwargs: session.responses.pop(0)
        result = ZbMathAdapter(session).collect(
            {"姓名": "Sample Author", "zbMATH作者ID": "sample.author"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")

    def test_zbmath_confirmed_author_without_window_works_is_no_recent_record(self):
        session = FakeSession(
            [
                {
                    "result": [{
                        "code": "sample.author",
                        "name": "Sample Author",
                        "external_ids": [{"type": "orcid", "external_id": "0000-0001"}],
                    }]
                },
                {"result": []},
            ]
        )
        result = ZbMathAdapter(session).collect(
            {"英文姓名": "Sample Author", "ORCID": "0000-0001"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.author_id, "sample.author")
        self.assertEqual(result.works, ())

    def test_zbmath_empty_author_search_means_no_candidate(self):
        session = FakeSession([{"result": []}])
        result = ZbMathAdapter(session).collect(
            {"姓名": "未收录姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "no_candidate")
        self.assertIn("不代表作者没有论文", result.reason)

    def test_zbmath_404_author_search_means_schema_changed(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: FakeResponse({}, status_code=404)
        result = ZbMathAdapter(session).collect(
            {"姓名": "未收录姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "schema_changed")

    def test_zbmath_404_is_empty_candidate_after_schema_was_confirmed(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: FakeResponse({}, status_code=404)
        adapter = ZbMathAdapter(session)
        adapter.schema_confirmed = True
        result = adapter.collect(
            {"姓名": "未收录姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "no_candidate")

    def test_zbmath_request_failure_is_not_reported_as_no_record(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("timeout"))
        adapter = ZbMathAdapter(session)
        adapter.http.sleep = lambda _: None
        result = adapter.collect(
            {"姓名": "示例姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "request_failed")

    def test_openalex_empty_author_search_is_no_candidate(self):
        session = FakeSession([{"results": []}])
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {"英文姓名": "Sample Author"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "no_candidate")

    def test_openalex_confirmed_author_without_window_works_is_no_recent_record(self):
        session = FakeSession(
            [
                {
                    "results": [{
                        "id": "https://openalex.org/A123",
                        "display_name": "Sample Author",
                        "orcid": "https://orcid.org/0000-0001",
                        "affiliations": [{"institution": {"display_name": "Renmin University of China"}}],
                    }]
                },
                {"results": []},
            ]
        )
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {"英文姓名": "Sample Author", "ORCID": "0000-0001"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(result.author_id, "A123")
        self.assertEqual(result.works, ())

    def test_openalex_discovery_can_use_name_and_affiliation_without_fetching_works(self):
        session = FakeSession(
            [{
                "results": [{
                    "id": "https://openalex.org/A123",
                    "display_name": "Sample Author",
                    "affiliations": [{"institution": {"display_name": "Renmin University of China"}}],
                }]
            }]
        )
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {
                "英文姓名": "Sample Author",
                "论文身份机构": "Renmin University of China",
            },
            start_year=2022,
            end_year=2026,
            discovery_only=True,
        )
        self.assertEqual(result.status, "identity_probable")
        self.assertEqual(result.confidence, "medium")
        self.assertEqual(result.works, ())
        self.assertEqual(len(session.calls), 1)
        self.assertTrue(result.metadata["discovery_only"])

    def test_openalex_orcid_conflict_rejects_candidate(self):
        session = FakeSession(
            [{
                "results": [{
                    "id": "https://openalex.org/A123",
                    "display_name": "Sample Author",
                    "orcid": "https://orcid.org/0000-CONFLICT",
                    "affiliations": [{"institution": {"display_name": "Renmin University of China"}}],
                }]
            }]
        )
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {
                "英文姓名": "Sample Author",
                "ORCID": "0000-OFFICIAL",
                "论文身份机构": "Renmin University of China",
            },
            start_year=2022,
            end_year=2026,
            discovery_only=True,
        )
        self.assertEqual(result.status, "identity_rejected")
        self.assertIn("ORCID", result.reason)

    def test_openalex_private_candidate_rejection_tries_next_candidate(self):
        session = FakeSession(
            [{
                "results": [
                    {"id": "https://openalex.org/AWRONG", "display_name": "Sample Author"},
                    {
                        "id": "https://openalex.org/ARIGHT",
                        "display_name": "Sample Author",
                        "affiliations": [{"institution": {"display_name": "Example University"}}],
                    },
                ]
            }]
        )
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {
                "英文姓名": "Sample Author",
                "论文身份机构": "Example University",
                "拒绝OpenAlex作者ID": "AWRONG",
            },
            start_year=2022,
            end_year=2026,
            discovery_only=True,
        )
        self.assertEqual(result.author_id, "ARIGHT")
        self.assertEqual(result.status, "identity_probable")
        decisions = {candidate.author_id: candidate.decision for candidate in result.author_candidates}
        self.assertEqual(decisions["AWRONG"], "rejected")
        self.assertEqual(decisions["ARIGHT"], "probable")

    def test_openalex_confirmed_id_skips_name_search(self):
        session = FakeSession([{"results": []}])
        result = OpenAlexAdapter(session, api_key="test-key").collect(
            {"姓名": "Sample Author", "OpenAlex作者ID": "A123"},
            start_year=2022,
            end_year=2026,
        )
        self.assertEqual(result.status, "no_recent_record")
        self.assertEqual(result.confidence, "high")
        self.assertEqual(len(session.calls), 1)
        self.assertIn("/works", session.calls[0][0])

    def test_openalex_works_follow_cursor_pagination(self):
        session = FakeSession(
            [
                {
                    "results": [{"id": "https://openalex.org/W1", "display_name": "Paper One", "publication_year": 2025}],
                    "meta": {"next_cursor": "next-page"},
                },
                {
                    "results": [{"id": "https://openalex.org/W2", "display_name": "Paper Two", "publication_year": 2024}],
                    "meta": {"next_cursor": None},
                },
            ]
        )
        adapter = OpenAlexAdapter(session, api_key="test-key")
        works = adapter._works("A123", 2022, 2026)
        self.assertEqual([work.source_id for work in works], ["W1", "W2"])
        self.assertEqual(session.calls[0][1]["params"]["cursor"], "*")
        self.assertEqual(session.calls[1][1]["params"]["cursor"], "next-page")
        self.assertIn("authorships", session.calls[0][1]["params"]["select"])
        self.assertEqual(adapter.last_work_metadata["pages"], 2)

    def test_openalex_max_pages_is_reported_as_truncated(self):
        session = FakeSession(
            [{
                "results": [{"id": "https://openalex.org/W1", "display_name": "Paper One", "publication_year": 2025}],
                "meta": {"next_cursor": "still-more"},
            }]
        )
        adapter = OpenAlexAdapter(session, api_key="test-key")
        adapter.max_work_pages = 1
        adapter._works("A123", 2022, 2026)
        self.assertTrue(adapter.last_work_metadata["truncated"])

    def test_zbmath_works_follow_page_pagination(self):
        first_page = [
            {"id": f"Z{i}", "title": {"title": f"Paper {i}"}, "year": 2025}
            for i in range(100)
        ]
        session = FakeSession(
            [
                {"result": first_page},
                {"result": [{"id": "Z100", "title": {"title": "Paper 100"}, "year": 2024}]},
            ]
        )
        adapter = ZbMathAdapter(session)
        works = adapter._works("sample.author", 2022, 2026)
        self.assertEqual(len(works), 101)
        self.assertEqual(session.calls[0][1]["params"]["page"], 0)
        self.assertEqual(session.calls[1][1]["params"]["page"], 1)
        self.assertFalse(adapter.last_work_metadata["truncated"])


if __name__ == "__main__":
    unittest.main()
