from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ViewerLayoutTests(unittest.TestCase):
    def test_four_week_strip_contract_is_present(self) -> None:
        html = (PROJECT_ROOT / "viewer" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "viewer" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="calendarLegend"', html)
        self.assertIn('class="calendar-weekdays"', html)
        self.assertIn('id="calendarSelectedTeachers"', html)
        self.assertIn('id="calendarToggle"', html)
        self.assertNotIn('class="actions"', html)
        self.assertIn("Array.from({ length: 28 }", script)
        self.assertIn("renderSelectedCalendarDay", script)
        self.assertIn("calendar-interview-marker", script)

    def test_contact_frequency_warnings_are_removed(self) -> None:
        source = "\n".join(
            (PROJECT_ROOT / path).read_text(encoding="utf-8")
            for path in ("viewer/index.html", "viewer/assets/app.js", "viewer/assets/app.css")
        )
        self.assertNotIn("calendarWarnings", source)
        self.assertNotIn("calendarDensityWarnings", source)
        self.assertNotIn("calendar-warning", source)

    def test_removed_toolbar_features_have_no_api_routes(self) -> None:
        html = (PROJECT_ROOT / "viewer" / "index.html").read_text(encoding="utf-8")
        script = (PROJECT_ROOT / "viewer" / "assets" / "app.js").read_text(encoding="utf-8")
        server = (PROJECT_ROOT / "src" / "tutor_recommendation" / "viewer_server.py").read_text(encoding="utf-8")
        self.assertNotIn('class="actions"', html)
        self.assertNotIn("saveStatus", script)
        self.assertNotIn("syncExcel", script)
        self.assertNotIn("/api/status-store", server)
        self.assertNotIn("/api/sync-excel", server)


if __name__ == "__main__":
    unittest.main()
