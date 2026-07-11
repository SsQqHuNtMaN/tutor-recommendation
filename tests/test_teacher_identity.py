from __future__ import annotations

import os
import unittest


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation.teacher_identity import teacher_id_for_row  # noqa: E402


class TeacherIdentityTests(unittest.TestCase):
    def test_same_school_strong_url_has_same_teacher_id(self) -> None:
        row = {"姓名": "Example", "教师主页链接": "https://example.edu/faculty/a"}
        first = teacher_id_for_row("school", "college_a", row)
        second = teacher_id_for_row("school", "college_b", row)
        self.assertEqual(first, second)

    def test_same_name_without_identity_is_target_local(self) -> None:
        row = {"姓名": "Example", "职称": "教授", "名录序号": 1}
        first = teacher_id_for_row("school", "college_a", row)
        second = teacher_id_for_row("school", "college_b", row)
        self.assertNotEqual(first, second)

    def test_tracking_parameters_do_not_change_identity(self) -> None:
        first = teacher_id_for_row(
            "school",
            "college",
            {"姓名": "Example", "教师主页链接": "https://example.edu/a?utm_source=x&id=1"},
        )
        second = teacher_id_for_row(
            "school",
            "college",
            {"姓名": "Example", "教师主页链接": "https://example.edu/a?id=1"},
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
