"""Backup or restore local projects; restored jobs remain paused."""

import argparse
from pathlib import Path

from studio.backup import create_backup, restore_backup
from studio.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "restore"])
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "create":
        print(create_backup(Store(args.data), args.archive))
    else:
        if not args.destination:
            parser.error("Restore requires --destination pointing to a new data folder")
        store = restore_backup(args.archive, args.destination)
        print(f"Restored to {store.root}. Review Settings before resuming paused jobs.")


if __name__ == "__main__":
    main()
