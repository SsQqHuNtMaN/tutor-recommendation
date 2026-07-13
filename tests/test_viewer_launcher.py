from __future__ import annotations

import socket
import unittest
from pathlib import Path
from unittest.mock import patch

from tutor_recommendation.viewer_launcher import find_available_port, port_is_available


class ViewerLauncherTests(unittest.TestCase):
    def test_root_batch_file_delegates_to_maintained_launcher(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        launcher = (project_root / "start_viewer.bat").read_text(encoding="utf-8")
        self.assertIn(r"scripts\start_viewer.bat", launcher)

    def test_port_probe_skips_an_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            occupied_port = occupied.getsockname()[1]
            self.assertFalse(port_is_available("127.0.0.1", occupied_port))
        with patch(
            "tutor_recommendation.viewer_launcher.port_is_available",
            side_effect=lambda _host, port: port != 8765,
        ):
            self.assertEqual(find_available_port("127.0.0.1", 8765, search_size=2), 8766)

    def test_port_probe_rejects_invalid_ranges(self) -> None:
        with self.assertRaises(ValueError):
            find_available_port("127.0.0.1", 0)
        with self.assertRaises(ValueError):
            find_available_port("127.0.0.1", 8765, search_size=0)


if __name__ == "__main__":
    unittest.main()
