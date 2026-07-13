from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tutor_recommendation.migrate_contact_status_column import main


if __name__ == "__main__":
    main()
