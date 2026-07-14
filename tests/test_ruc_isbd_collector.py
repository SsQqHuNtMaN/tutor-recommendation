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


if __name__ == "__main__":
    unittest.main()
