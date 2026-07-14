from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    configured_profile = False
    if "--profile" in sys.argv and "--demo-profile" in sys.argv:
        raise SystemExit("--profile and --demo-profile are mutually exclusive")
    if "--profile" in sys.argv:
        index = sys.argv.index("--profile")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--profile requires a path")
        from tutor_recommendation.profile_registry import configure_profile_environment

        configure_profile_environment(sys.argv[index + 1])
        configured_profile = True
        del sys.argv[index : index + 2]
    if "--demo-profile" in sys.argv:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"
        sys.argv.remove("--demo-profile")
    elif not configured_profile and "--help" not in sys.argv and "-h" not in sys.argv:
        from tutor_recommendation.profile_registry import configure_profile_environment

        configure_profile_environment()
    if "--help" in sys.argv or "-h" in sys.argv:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"
    from tutor_recommendation.checkpoint_doctor import main as package_main

    package_main()


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
