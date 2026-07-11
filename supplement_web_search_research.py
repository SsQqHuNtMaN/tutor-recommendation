from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    if "--profile" in sys.argv:
        index = sys.argv.index("--profile")
        if index + 1 >= len(sys.argv):
            raise SystemExit("--profile requires a path")
        if "--demo-profile" in sys.argv:
            raise SystemExit("--profile and --demo-profile are mutually exclusive")
        os.environ.pop("TUTOR_ALLOW_TEMPLATE_PROFILE", None)
        os.environ["STUDENT_PROFILE_PATH"] = sys.argv[index + 1]
        del sys.argv[index : index + 2]
    if "--demo-profile" in sys.argv or "--help" in sys.argv or "-h" in sys.argv:
        os.environ.pop("STUDENT_PROFILE_PATH", None)
        os.environ["TUTOR_ALLOW_TEMPLATE_PROFILE"] = "1"
        if "--demo-profile" in sys.argv:
            sys.argv.remove("--demo-profile")
            print(
                "WARNING: using the public demo profile; results are not suitable for real application decisions.",
                file=sys.stderr,
            )
    from tutor_recommendation.supplement_web_search_research import main as package_main

    package_main()


if __name__ == "__main__":
    os.chdir(ROOT)
    main()
