from __future__ import annotations

import unittest

from tutor_recommendation.viewer_server import (
    is_loopback_host,
    request_host_is_allowed,
    request_origin_is_allowed,
)


class ViewerSecurityTests(unittest.TestCase):
    def test_only_loopback_hosts_are_allowed(self) -> None:
        self.assertTrue(is_loopback_host("127.0.0.1"))
        self.assertTrue(is_loopback_host("localhost"))
        self.assertFalse(is_loopback_host("0.0.0.0"))
        self.assertFalse(is_loopback_host("192.168.1.5"))

    def test_host_header_must_be_loopback(self) -> None:
        self.assertTrue(request_host_is_allowed("127.0.0.1:8765"))
        self.assertFalse(request_host_is_allowed("example.com"))

    def test_cross_origin_request_is_rejected(self) -> None:
        self.assertTrue(request_origin_is_allowed("http://127.0.0.1:8765", "127.0.0.1:8765"))
        self.assertFalse(request_origin_is_allowed("https://example.com", "127.0.0.1:8765"))
        self.assertFalse(request_origin_is_allowed("http://localhost:9999", "localhost:8765"))


if __name__ == "__main__":
    unittest.main()
