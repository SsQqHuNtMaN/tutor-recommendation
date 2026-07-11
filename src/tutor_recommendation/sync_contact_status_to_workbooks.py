from __future__ import annotations

import argparse

from .contact_status import CONTACT_STATUS_PATH, empty_store, load_status_store, save_status_store
from .migrate_contact_status_column import iter_current_workbooks, migrate_workbook


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync outputs/contact_status.json back into current Excel workbooks.")
    parser.add_argument(
        "--preserve-untracked",
        action="store_true",
        help="Keep existing Excel contact records for rows that are not present in contact_status.json.",
    )
    args = parser.parse_args()

    if CONTACT_STATUS_PATH.exists():
        store = load_status_store(CONTACT_STATUS_PATH)
        save_status_store(store, CONTACT_STATUS_PATH)
    else:
        store = empty_store()
        save_status_store(store, CONTACT_STATUS_PATH)

    paths = iter_current_workbooks()
    for path in paths:
        migrate_workbook(path, store, authoritative=not args.preserve_untracked)
        print(f"synced {path}")
    print(f"workbooks={len(paths)}")
    print(f"status_store={CONTACT_STATUS_PATH}")


if __name__ == "__main__":
    main()
