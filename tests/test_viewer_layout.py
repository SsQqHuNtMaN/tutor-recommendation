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
        self.assertIn('id="calendarSelectedDay"', html)
        self.assertIn('id="calendarToggle"', html)
        self.assertIn('class="calendar-pane-header"', html)
        self.assertIn('class="calendar-toggle-icon"', html)
        self.assertIn('class="detail-rail"', html)
        self.assertIn('class="detail-toggle-icon"', html)
        self.assertIn('id="calendarFilterReset"', html)
        self.assertIn('id="listFilterReset"', html)
        self.assertIn('id="calendarProgressOverview"', html)
        self.assertIn('id="calendarProgressBody"', html)
        self.assertIn('id="profileSelector"', html)
        self.assertIn('class="profile-switcher"', html)
        self.assertIn('class="calendar-dashboard"', html)
        self.assertIn('class="calendar-main"', html)
        self.assertIn('class="calendar-side"', html)
        self.assertIn('查看学校 / 学院进度', html)
        self.assertNotIn('class="actions"', html)
        self.assertIn("Array.from({ length: 28 }", script)
        self.assertIn("renderSelectedCalendarDay", script)
        self.assertIn("calendarDateInteracted", script)
        self.assertIn("calendar-interview-marker", script)
        self.assertIn('responses.className = "calendar-event-responses"', script)
        stylesheet = (PROJECT_ROOT / "viewer" / "assets" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".calendar-selected-teachers .calendar-event-responses", stylesheet)
        self.assertIn("flex-direction: column", stylesheet)
        self.assertIn("overflow-x: hidden", stylesheet)
        self.assertIn("max-width: 100%", stylesheet)
        self.assertIn(".calendar-pane.is-collapsed .calendar-toggle-icon", stylesheet)
        self.assertIn("border-bottom: 6px solid currentColor", stylesheet)
        self.assertIn("grid-template-columns: minmax(600px, 1fr) 32px", stylesheet)
        self.assertIn(".workbench.sidebar-collapsed .detail-toggle-icon", stylesheet)
        self.assertNotIn('detailToggle.textContent = collapsed', script)
        self.assertIn("function resetCalendarFilters()", script)
        self.assertIn("function resetListFilters()", script)
        self.assertIn("function renderCalendarProgressOverview()", script)
        self.assertIn("grid-template-rows: repeat(4, minmax(30px, 1fr))", stylesheet)
        self.assertIn("overflow-y: hidden", stylesheet)
        self.assertIn("function selectAdjacentTeacher(offset)", script)
        self.assertIn("function bindDetailToolbar()", script)
        self.assertIn('id="detailJumpSelect"', script)
        self.assertIn('event.key === "ArrowUp"', script)
        self.assertIn('FILTER_PREFERENCES_STORAGE_KEY', script)
        self.assertIn('function restoreFilterPreferences()', script)
        self.assertIn('function writeFilterPreferences()', script)
        self.assertIn('async function switchProfile(profileId)', script)
        self.assertIn('/api/profile-selection', script)
        self.assertIn('profileId, key: record.key', script)
        self.assertNotIn('search: els.searchInput.value', script)
        self.assertIn('tr.setAttribute("aria-selected"', script)
        self.assertIn('tr.addEventListener("keydown"', script)

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

    def test_math_publication_evidence_contract_is_present(self) -> None:
        script = (PROJECT_ROOT / "viewer" / "assets" / "app.js").read_text(encoding="utf-8")
        server = (PROJECT_ROOT / "src" / "tutor_recommendation" / "viewer_server.py").read_text(encoding="utf-8")
        self.assertIn("数学文献近五年", script)
        self.assertIn('["数学论文", "论文证据分"', script)
        self.assertIn("record.publication", script)
        self.assertIn('"publication": ["数学文献近五年明细"]', server)


if __name__ == "__main__":
    unittest.main()
