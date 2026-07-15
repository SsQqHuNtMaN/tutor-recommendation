from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from tutor_recommendation.collectors.ruc_isbd import (
    discover_directory_pages,
    parse_directory_cards,
    parse_teacher_detail,
)


DIRECTORY_HTML = """
<html><body>
  <div class="sztuanduia">
    <a href="teacher-a.htm"><img src="a.png"></a>
    <h1>姓名：<a href="teacher-a.htm">示例甲</a></h1>
    <p>职称：副教授、博士生导师（示例研究院）</p>
    <p>研究方向：分布式学习、随机优化</p>
    <p>联系方式：teacher.a@example.edu.cn</p>
  </div>
  <a href="index.htm">第一页</a>
  <a href="index1.htm">下一页</a>
  <a href="index2.htm">最后页</a>
  <a href="../news/index.htm">新闻</a>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <div class="muyslia">
    <h1>示例甲</h1>
    <p>职称：副教授、博士生导师（示例研究院）</p>
    <p>研究方向：联邦学习、差分隐私</p>
    <p>联系方式：teacher.a@example.edu.cn</p>
  </div>
  <div class="wuyshux">
    <p>主要研究联邦学习中的隐私保护优化。</p>
    <p><a href="https://faculty.example.org/a">个人主页</a></p>
    <p><strong>Selected Publications</strong></p>
    <p>Example A. Privacy-aware distributed optimization. Journal of Examples, 2025. doi:10.1234/example.1</p>
  </div>
</body></html>
"""

SECTIONED_DETAIL_HTML = """
<html><body>
  <div class="muyslia"><h1>示例乙</h1></div>
  <div class="wuyshux">
    <h3>工作经历</h3>
    <p>2023-08至2025-08，示例大学，准聘副教授</p>
    <p><strong>Selected Publications</strong></p>
    <p>Example B. A distributed optimization method. Journal of Examples, 2025.</p>
    <p>1. Example C. A statistical learning method. Annals of Examples, 2024. 2. Example D. A privacy method. arXiv:2501.01234.</p>
    <h3>奖励与荣誉</h3>
    <p>示例大学优秀科研成果奖（一等奖），2024</p>
    <h3>科研项目</h3>
    <p>隐私保护优化研究，2024-2026，示例基金项目，主持。</p>
  </div>
</body></html>
"""

NO_PUBLICATION_SECTION_HTML = """
<html><body>
  <div class="muyslia"><h1>示例丙</h1></div>
  <div class="wuyshux">
    <p>2022 年毕业于示例大学，2024 年加入示例研究院。</p>
    <p>2025 年担任副主任并主持重点项目。</p>
  </div>
</body></html>
"""

MULTILINE_TABLE_DETAIL_HTML = """
<html><head><meta name="citation_author" content="Qiong Zhang"></head><body>
  <div class="muyslia"><h1>张琼 Qiong Zhang</h1></div>
  <div class="wuyshux">
    <h3>Selected Publications</h3>
    <p>Qiong Zhang, Example Coauthor.<br>A multiline optimization paper.<br>Journal of Examples, 2025.</p>
    <table>
      <tr><th>Authors</th><th>Title</th><th>Venue</th><th>Year</th></tr>
      <tr><td>Qiong Zhang</td><td>A tabular statistical learning paper</td><td>Annals of Examples</td><td>2024</td></tr>
    </table>
  </div>
</body></html>
"""


class RucIsbdCollectorTests(unittest.TestCase):
    def test_discovers_only_same_directory_pages(self) -> None:
        soup = BeautifulSoup(DIRECTORY_HTML, "html.parser")
        pages = discover_directory_pages(soup, "http://example.edu/sztd/index.htm")
        self.assertEqual(
            pages,
            [
                "http://example.edu/sztd/index.htm",
                "http://example.edu/sztd/index1.htm",
                "http://example.edu/sztd/index2.htm",
            ],
        )

    def test_parses_card_and_detail_without_navigation_text(self) -> None:
        rows = parse_directory_cards(BeautifulSoup(DIRECTORY_HTML, "html.parser"), "http://example.edu/sztd/index.htm")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["姓名"], "示例甲")
        self.assertEqual(rows[0]["名录研究所"], "示例研究院")
        detail = parse_teacher_detail(BeautifulSoup(DETAIL_HTML, "html.parser"), rows[0])
        self.assertEqual(detail["研究方向"], "联邦学习、差分隐私")
        self.assertEqual(detail["个人主页"], "https://faculty.example.org/a")
        self.assertIn("2025", detail["官方论文列表"])
        self.assertNotIn("2025", detail["个人简介摘要"])
        self.assertNotIn("新闻", detail["个人简介摘要"])

    def test_publication_section_excludes_career_awards_and_projects(self) -> None:
        row = {
            "姓名": "示例乙",
            "教师主页链接": "http://example.edu/sztd/teacher-b.htm",
            "研究方向": "",
            "职称": "",
            "邮箱": "",
            "名录研究所": "",
        }
        detail = parse_teacher_detail(BeautifulSoup(SECTIONED_DETAIL_HTML, "html.parser"), row)
        publications = detail["官方论文列表"].splitlines()
        self.assertEqual(len(publications), 3)
        self.assertTrue(any("2025" in item for item in publications))
        self.assertTrue(any("2501.01234" in item for item in publications))
        self.assertFalse(any("副教授" in item or "成果奖" in item or "基金项目" in item for item in publications))

    def test_years_without_publication_section_fail_closed(self) -> None:
        row = {
            "姓名": "示例丙",
            "教师主页链接": "http://example.edu/sztd/teacher-c.htm",
            "研究方向": "",
            "职称": "",
            "邮箱": "",
            "名录研究所": "",
        }
        detail = parse_teacher_detail(BeautifulSoup(NO_PUBLICATION_SECTION_HTML, "html.parser"), row)
        self.assertEqual(detail["官方论文列表"], "")
        self.assertEqual(detail["官方论文来源"], "")

    def test_multiline_and_table_publications_are_reconstructed(self) -> None:
        row = {
            "姓名": "张琼",
            "教师主页链接": "http://example.edu/sztd/qiong-zhang.htm",
            "研究方向": "",
            "职称": "",
            "邮箱": "",
            "名录研究所": "",
        }
        detail = parse_teacher_detail(BeautifulSoup(MULTILINE_TABLE_DETAIL_HTML, "html.parser"), row)
        publications = detail["官方论文列表"].splitlines()
        self.assertEqual(len(publications), 2)
        self.assertIn("Qiong Zhang", publications[0])
        self.assertTrue(any("tabular statistical learning" in item for item in publications))
        self.assertEqual(detail["英文姓名"], "Qiong Zhang")
        self.assertIn(detail["英文姓名来源"], {"official_meta", "official_heading"})

    def test_non_heading_text_is_not_truncated_by_absent_section_marker(self) -> None:
        row = {
            "姓名": "示例丁",
            "教师主页链接": "http://example.edu/sztd/teacher-d.htm",
            "研究方向": "",
            "职称": "",
            "邮箱": "",
            "名录研究所": "",
        }
        detail = parse_teacher_detail(BeautifulSoup(MULTILINE_TABLE_DETAIL_HTML, "html.parser"), row)
        self.assertTrue(detail["官方论文列表"].startswith("Qiong Zhang, Example Coauthor."))


if __name__ == "__main__":
    unittest.main()
