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

    def test_zbmath_404_author_search_means_no_record(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: FakeResponse({}, status_code=404)
        result = ZbMathAdapter(session).collect(
            {"姓名": "未收录姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "no_record")

    def test_zbmath_request_failure_is_not_reported_as_no_record(self):
        session = FakeSession([])
        session.get = lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout("timeout"))
        result = ZbMathAdapter(session).collect(
            {"姓名": "示例姓名"}, start_year=2022, end_year=2026
        )
        self.assertEqual(result.status, "request_failed")


if __name__ == "__main__":
    unittest.main()
