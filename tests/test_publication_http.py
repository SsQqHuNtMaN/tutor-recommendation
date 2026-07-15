from __future__ import annotations

import unittest

import requests

from tutor_recommendation.publication_http import (
    PublicationHttpClient,
    PublicationRequestFailed,
    PublicationSchemaChanged,
    PublicationTermsRequired,
)


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None, text=""):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class PublicationHttpTests(unittest.TestCase):
    def test_429_uses_retry_after_and_then_succeeds(self):
        sleeps = []
        session = FakeSession(
            [
                FakeResponse({}, status_code=429, headers={"Retry-After": "2"}),
                FakeResponse({"results": []}),
            ]
        )
        result = PublicationHttpClient(session, source="openalex", sleep=sleeps.append).get_json(
            "https://example.test/authors", expected_keys=("results",)
        )
        self.assertEqual(result, {"results": []})
        self.assertEqual(sleeps, [2.0])

    def test_timeout_retries_are_bounded(self):
        session = FakeSession([requests.Timeout("slow"), requests.Timeout("slow")])
        client = PublicationHttpClient(session, source="zbmath", max_retries=1, sleep=lambda _: None)
        with self.assertRaises(PublicationRequestFailed):
            client.get_json("https://example.test/documents")
        self.assertEqual(len(session.calls), 2)

    def test_terms_html_is_not_treated_as_empty_json(self):
        session = FakeSession(
            [
                FakeResponse(
                    {},
                    headers={"Content-Type": "text/html"},
                    text="<html><h1>Terms and Conditions</h1></html>",
                )
            ]
        )
        with self.assertRaises(PublicationTermsRequired):
            PublicationHttpClient(session, source="zbmath").get_json("https://example.test")

    def test_non_success_terms_html_keeps_terms_status(self):
        session = FakeSession(
            [
                FakeResponse(
                    {},
                    status_code=403,
                    headers={"Content-Type": "text/html"},
                    text="<html>Please accept the terms</html>",
                )
            ]
        )
        with self.assertRaises(PublicationTermsRequired):
            PublicationHttpClient(session, source="zbmath").get_json("https://example.test")

    def test_500_retries_then_succeeds(self):
        session = FakeSession(
            [FakeResponse({}, status_code=500), FakeResponse({"result": []})]
        )
        result = PublicationHttpClient(session, source="zbmath", sleep=lambda _: None).get_json(
            "https://example.test", expected_keys=("result",)
        )
        self.assertEqual(result, {"result": []})

    def test_missing_expected_schema_is_explicit(self):
        session = FakeSession([FakeResponse({"unexpected": []})])
        with self.assertRaises(PublicationSchemaChanged):
            PublicationHttpClient(session, source="openalex").get_json(
                "https://example.test", expected_keys=("results",)
            )


if __name__ == "__main__":
    unittest.main()
