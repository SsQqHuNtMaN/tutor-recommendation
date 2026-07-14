from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.teacher_match_targets import TARGETS, get_target


def configure_target(target_key: str) -> None:
    target = get_target(target_key)
    os.environ["SCHOOL_SLUG"] = target.school_slug
    os.environ["COLLEGE_SLUG"] = target.college_slug
    os.environ["FACULTY_SOURCE_URL"] = target.directory_url
    os.environ["TARGET_KEY"] = target.key
    os.environ["EVIDENCE_PROFILE"] = target.evidence_profile
    os.environ["PUBLICATION_WINDOW_YEARS"] = str(target.publication_window_years)
    if target_key == "zju_cs":
        os.environ["FACULTY_PDF_SOURCE_URL"] = "http://www.cs.zju.edu.cn/csen/2021/0525/c27006a2377953/page.htm"


def main() -> None:
    parser = argparse.ArgumentParser(description="Add arXiv and web evidence to a teacher matching workbook.")
    parser.add_argument("target_arg", nargs="?", help="Target key, e.g. nju_cs.")
    parser.add_argument("--target", dest="target", help=f"Target key. Available: {', '.join(TARGETS)}")
    parser.add_argument("--finalize-only", action="store_true", help="Rebuild final Excel from checkpoint only.")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow finalize-only to produce a workbook when valid checkpoint coverage is incomplete.",
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
        from tutor_recommendation.profile_registry import configure_profile_environment

        configure_profile_environment(args.profile)
    elif not args.demo_profile:
        from tutor_recommendation.profile_registry import configure_profile_environment

        configure_profile_environment()
    if args.demo_profile:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"
        print("WARNING: using the public demo profile; results are not suitable for real application decisions.", file=sys.stderr)

    target_key = args.target or args.target_arg
    if target_key:
        configure_target(target_key)
    if args.finalize_only:
        os.environ["FINALIZE_ONLY"] = "1"
    if args.allow_partial:
        os.environ["ALLOW_PARTIAL_FINALIZE"] = "1"

    from tutor_recommendation import teacher_research_completion

    teacher_research_completion.main()


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
