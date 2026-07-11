from __future__ import annotations

import os
import tempfile
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd


os.environ.setdefault("TUTOR_ALLOW_TEMPLATE_PROFILE", "1")

from tutor_recommendation import teacher_research_completion as completion  # noqa: E402
from tutor_recommendation.teacher_research_completion import (  # noqa: E402
    prepare_web_search_columns_for_restore,
    require_complete_checkpoint_coverage,
)


class CompletionCheckpointTests(unittest.TestCase):
    def test_finalize_only_requires_complete_coverage(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "100% valid checkpoint coverage"):
            require_complete_checkpoint_coverage(9, 10, allow_partial=False)

    def test_allow_partial_is_explicit_escape_hatch(self) -> None:
        require_complete_checkpoint_coverage(9, 10, allow_partial=True)

    def test_curl_fallback_replaces_invalid_output_bytes(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="<html>ok</html>", stderr="")
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.object(completion.requests.Session, "get", side_effect=RuntimeError("offline")):
                with mock.patch.object(completion.subprocess, "run", return_value=completed) as run:
                    result = completion.fetch_with_curl(
                        "https://example.test/profile",
                        Path(tmp_dir),
                        ".html",
                    )
        self.assertEqual(result, completed.stdout)
        self.assertEqual(run.call_args.kwargs["errors"], "replace")

    def test_web_search_text_columns_accept_restored_strings(self) -> None:
        frame = pd.DataFrame({column: [float("nan")] for column in completion.WEB_SEARCH_COLUMNS})
        frame = prepare_web_search_columns_for_restore(frame)
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            frame.at[0, "WebSearch置信度"] = "高"
            frame.at[0, "WebSearch关键词"] = "robotics"
        self.assertEqual(frame.at[0, "WebSearch置信度"], "高")
        self.assertEqual(frame.at[0, "WebSearch关键词"], "robotics")


if __name__ == "__main__":
    unittest.main()
