from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.sync_contact_status_to_workbooks import main


if __name__ == "__main__":
    main()
