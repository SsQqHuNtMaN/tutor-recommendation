from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.teacher_match_targets import TARGETS, get_target


def main() -> None:
    parser = argparse.ArgumentParser(description="Add math publication evidence to a teacher matching workbook.")
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--profile", help="Named profile ID or private profile JSON path")
    args = parser.parse_args()
    from tutor_recommendation.profile_registry import configure_profile_environment

    configure_profile_environment(args.profile)
    target = get_target(args.target)
    if target.evidence_profile not in {"mathematics", "mathematics_ai"}:
        parser.error(f"target {target.key} does not use the mathematics publication profile")
    os.environ["TARGET_KEY"] = target.key
    os.environ["SCHOOL_SLUG"] = target.school_slug
    os.environ["COLLEGE_SLUG"] = target.college_slug
    os.environ["AFFILIATION_KEYWORDS"] = target.affiliation_env
    os.environ["EVIDENCE_PROFILE"] = target.evidence_profile
    os.environ["PUBLICATION_WINDOW_YEARS"] = str(target.publication_window_years)
    from tutor_recommendation.math_publication_research import main as research_main

    research_main()


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
