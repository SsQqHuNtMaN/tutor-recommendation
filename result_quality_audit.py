from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow-score existing workbooks and report aggregate quality checks.")
    parser.add_argument("--profile", help="Path to a private student profile JSON file.")
    parser.add_argument("--demo-profile", action="store_true", help="Explicitly use the public example profile.")
    parser.add_argument("--outputs-dir", type=Path, default=ROOT / "outputs")
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    parser.add_argument("--fail-on-violations", action="store_true")
    args = parser.parse_args()
    if args.profile and args.demo_profile:
        parser.error("--profile and --demo-profile are mutually exclusive")
    if args.profile:
        os.environ.pop("TUTOR_ALLOW_TEMPLATE_PROFILE", None)
        os.environ["STUDENT_PROFILE_PATH"] = args.profile
    if args.demo_profile:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"

    from tutor_recommendation.result_quality_audit import main as audit_main

    forwarded = ["--outputs-dir", str(args.outputs_dir)]
    if args.output:
        forwarded.extend(["--output", str(args.output)])
    if args.fail_on_violations:
        forwarded.append("--fail-on-violations")
    audit_main(forwarded)


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
