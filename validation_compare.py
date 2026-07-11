from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


if __name__ == "__main__":
    os.chdir(ROOT)
    from tutor_recommendation.validation_compare import main

    main()
