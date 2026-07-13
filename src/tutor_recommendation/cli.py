from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .private_workspace import (
    DRAFT_PROFILE_PATH,
    LEGACY_PROFILE_PATH,
    PROFILE_PATH,
    ensure_private_workspace,
    extract_profile_draft,
    initialize_profile_draft,
)
from .teacher_match_targets import TARGETS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AGENT_WORKFLOW = PROJECT_ROOT / "docs/agent-workflow.md"


def _run_script(script: str, arguments: Sequence[str]) -> int:
    command = [sys.executable, str(PROJECT_ROOT / "scripts/legacy" / script), *arguments]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


def _profile_arguments(args: argparse.Namespace) -> list[str]:
    if getattr(args, "demo_profile", False):
        return ["--demo-profile"]
    profile = getattr(args, "profile", None)
    return ["--profile", str(profile)] if profile else []


def command_setup(_: argparse.Namespace) -> int:
    created = ensure_private_workspace()
    draft = initialize_profile_draft()
    print(f"private_workspace={PROFILE_PATH.parent.parent}")
    print(f"profile_draft={draft}")
    print(f"created={len(created)}")
    print("next=put materials in user_private/source and ask the Coding Agent to extract and confirm the profile")
    return 0


def command_profile_init(args: argparse.Namespace) -> int:
    path = initialize_profile_draft(force=args.force)
    print(path)
    return 0


def command_profile_extract(args: argparse.Namespace) -> int:
    try:
        path, sources = extract_profile_draft(force=args.force)
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError) as exc:
        print(f"profile extraction failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"draft": str(path), "sources": [str(source) for source in sources]}, ensure_ascii=False))
    print("confirmation_required=true")
    return 0


def command_profile_validate(args: argparse.Namespace) -> int:
    default_path = PROFILE_PATH if PROFILE_PATH.is_file() or not LEGACY_PROFILE_PATH.is_file() else LEGACY_PROFILE_PATH
    path = Path(args.path or default_path).expanduser().resolve()
    if not path.is_file():
        print(f"profile not found: {path}", file=sys.stderr)
        return 2
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid profile JSON: {exc}", file=sys.stderr)
        return 2
    if raw.get("_draft_requires_confirmation"):
        print("profile is still a draft and requires user confirmation", file=sys.stderr)
        return 2
    os.environ["STUDENT_PROFILE_PATH"] = str(path)
    try:
        from .student_profile import load_student_profile

        profile = load_student_profile(path)
    except Exception as exc:
        print(f"profile validation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"valid": True, "path": str(profile.source_path), "hash": profile.profile_hash}, ensure_ascii=False))
    return 0


def command_targets(args: argparse.Namespace) -> int:
    if args.check:
        if args.check not in TARGETS:
            print(f"target_missing={args.check}")
            print(f"agent_workflow={AGENT_WORKFLOW}")
            print("next=the Coding Agent must add an official target, collector and regression tests before running")
            return 2
        target = TARGETS[args.check]
        print(json.dumps(target.__dict__, ensure_ascii=False, indent=2))
        return 0
    for target in TARGETS.values():
        print(f"{target.key}\t{target.school_name}\t{target.college_name}\t{target.directory_url}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    missing = [target for target in args.targets if target not in TARGETS]
    if missing:
        print("unsupported targets: " + ", ".join(missing), file=sys.stderr)
        print(f"Coding Agent: follow {AGENT_WORKFLOW} to add official target/collector/tests first", file=sys.stderr)
        return 2
    profile_args = _profile_arguments(args)
    stages = [
        ("build_teacher_match.py", [*args.targets, *profile_args]),
        ("update_teacher_match_with_dblp.py", [*args.targets[:1], *profile_args]),
        ("complete_teacher_research.py", [*args.targets[:1], *profile_args]),
    ]
    if len(args.targets) > 1:
        print("first pass will build all targets together; evidence stages run once per target")
        stages = [("build_teacher_match.py", [*args.targets, *profile_args])]
        for target in args.targets:
            stages.extend(
                [
                    ("update_teacher_match_with_dblp.py", [target, *profile_args]),
                    ("complete_teacher_research.py", [target, *profile_args]),
                ]
            )
    for script, script_args in stages:
        print(f"==> {script} {' '.join(script_args)}")
        code = _run_script(script, script_args)
        if code:
            return code
    return 0


def command_view(args: argparse.Namespace) -> int:
    return _run_script("viewer_server.py", ["--host", args.host, "--port", str(args.port)])


def command_doctor(args: argparse.Namespace) -> int:
    return _run_script("checkpoint_doctor.py", [*args.targets, *_profile_arguments(args)])


def command_audit(args: argparse.Namespace) -> int:
    forwarded = [*_profile_arguments(args)]
    if args.fail_on_violations:
        forwarded.append("--fail-on-violations")
    return _run_script("result_quality_audit.py", forwarded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tutor",
        description="Internal deterministic tools for the Tutor Recommendation Coding Agent workflow.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    setup = commands.add_parser("setup", help="Create the local private workspace and profile draft")
    setup.set_defaults(func=command_setup)

    profile = commands.add_parser("profile", help="Prepare or validate the private student profile")
    profile_commands = profile.add_subparsers(dest="profile_command", required=True)
    profile_init = profile_commands.add_parser("init", help="Create a profile draft from the public template")
    profile_init.add_argument("--force", action="store_true")
    profile_init.set_defaults(func=command_profile_init)
    profile_extract = profile_commands.add_parser("extract", help="Extract local materials into a draft profile")
    profile_extract.add_argument("--force", action="store_true")
    profile_extract.set_defaults(func=command_profile_extract)
    profile_validate = profile_commands.add_parser("validate", help="Validate a user-confirmed formal profile")
    profile_validate.add_argument("path", nargs="?")
    profile_validate.set_defaults(func=command_profile_validate)

    targets = commands.add_parser("targets", help="List registered targets or check one target key")
    targets.add_argument("--check")
    targets.set_defaults(func=command_targets)

    run = commands.add_parser("run", help="Run the existing three-stage workflow")
    run.add_argument("targets", nargs="+")
    run.add_argument("--profile")
    run.add_argument("--demo-profile", action="store_true")
    run.set_defaults(func=command_run)

    view = commands.add_parser("view", help="Start the local Viewer")
    view.add_argument("--host", default="127.0.0.1")
    view.add_argument("--port", type=int, default=8765)
    view.set_defaults(func=command_view)

    doctor = commands.add_parser("doctor", help="Check checkpoint coverage")
    doctor.add_argument("targets", nargs="+")
    doctor.add_argument("--profile")
    doctor.add_argument("--demo-profile", action="store_true")
    doctor.set_defaults(func=command_doctor)

    audit = commands.add_parser("audit", help="Run the result quality audit")
    audit.add_argument("--profile")
    audit.add_argument("--demo-profile", action="store_true")
    audit.add_argument("--fail-on-violations", action="store_true")
    audit.set_defaults(func=command_audit)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "profile", None) and getattr(args, "demo_profile", False):
        parser.error("--profile and --demo-profile are mutually exclusive")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
