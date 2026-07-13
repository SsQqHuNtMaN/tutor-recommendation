from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.first_pass_collectors import build_targets
from tutor_recommendation.teacher_match_targets import TARGETS, get_target


def main() -> None:
    parser = argparse.ArgumentParser(description="Build first-pass teacher matching workbooks.")
    parser.add_argument(
        "targets",
        nargs="*",
        help=f"Targets to build. Available: {', '.join(TARGETS)}",
    )
    parser.add_argument("--all", action="store_true", help="Build every configured target.")
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

    target_keys = list(TARGETS) if args.all else args.targets
    if not target_keys:
        parser.error("provide at least one target or use --all")

    for target_key in target_keys:
        get_target(target_key)
    build_targets(target_keys)


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
