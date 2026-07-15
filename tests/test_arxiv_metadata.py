from __future__ import annotations

import unittest

from tutor_recommendation import teacher_research_completion as completion


class ArxivMetadataTests(unittest.TestCase):
    def test_parser_keeps_stable_ids_doi_and_journal_reference(self):
        year = sorted(completion.RECENT_YEARS)[-1]
        xml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"
              xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
              xmlns:arxiv="http://arxiv.org/schemas/atom">
          <opensearch:totalResults>1</opensearch:totalResults>
          <entry>
            <id>https://arxiv.org/abs/2401.01234v2</id>
            <updated>{year}-02-02T00:00:00Z</updated>
            <published>{year}-01-01T00:00:00Z</published>
            <title>A Robust Learning Method</title>
            <summary>Summary</summary>
            <author><name>Sample Author</name></author>
            <category term="math.OC" />
            <link rel="alternate" href="https://arxiv.org/abs/2401.01234" />
            <arxiv:doi>10.1000/example</arxiv:doi>
            <arxiv:journal_ref>Example Journal</arxiv:journal_ref>
          </entry>
        </feed>'''
        parsed = completion.parse_arxiv_entries(xml, "Sample Author")
        self.assertEqual(len(parsed["entries"]), 1)
        entry = parsed["entries"][0]
        self.assertEqual(entry["arxiv_id"], "2401.01234v2")
        self.assertEqual(entry["doi"], "10.1000/example")
        self.assertEqual(entry["journal_ref"], "Example Journal")

    def test_default_request_interval_is_not_aggressive(self):
        self.assertGreaterEqual(completion.ARXIV_REQUEST_INTERVAL_SECONDS, 1.0)


if __name__ == "__main__":
    unittest.main()
