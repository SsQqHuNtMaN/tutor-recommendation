from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.teacher_match_targets import TARGETS, get_target


def configure_target(target_key: str) -> None:
    target = get_target(target_key)
    os.environ["SCHOOL_SLUG"] = target.school_slug
    os.environ["COLLEGE_SLUG"] = target.college_slug
    os.environ["AFFILIATION_KEYWORDS"] = target.affiliation_env


def main() -> None:
    parser = argparse.ArgumentParser(description="Add DBLP evidence to a teacher matching workbook.")
    parser.add_argument("target_arg", nargs="?", help="Target key, e.g. nju_cs.")
    parser.add_argument("--target", dest="target", help=f"Target key. Available: {', '.join(TARGETS)}")
    parser.add_argument(
        "--recommendation-levels",
        help="Optional comma-separated recommendation levels to query, e.g. 强烈建议.",
    )
    parser.add_argument(
        "--names",
        help="Optional comma-separated teacher names to query. Existing DBLP rows for other teachers are preserved.",
    )
    parser.add_argument(
        "--demo-profile",
        action="store_true",
        help="Explicitly use the public example profile when no private profile exists.",
    )
    parser.add_argument("--profile", help="Path to a private student profile JSON file.")
    args = parser.parse_args()

    if args.demo_profile and args.profile:
        parser.error("--profile and --demo-profile are mutually exclusive")
    if args.profile:
        os.environ.pop("TUTOR_ALLOW_TEMPLATE_PROFILE", None)
        os.environ["STUDENT_PROFILE_PATH"] = args.profile
    if args.demo_profile:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"
        print("WARNING: using the public demo profile; results are not suitable for real application decisions.", file=sys.stderr)

    target_key = args.target or args.target_arg
    if target_key:
        configure_target(target_key)
    if args.recommendation_levels is not None:
        os.environ["DBLP_RECOMMENDATION_LEVELS"] = args.recommendation_levels
    if args.names is not None:
        os.environ["DBLP_TARGET_NAMES"] = args.names

    from tutor_recommendation import dblp_research

    dblp_research.main()


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
