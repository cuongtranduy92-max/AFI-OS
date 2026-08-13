from __future__ import annotations

import argparse
import json

from afi_os.services.backups import create_backup, list_backups, restore_latest


def main() -> None:
    parser = argparse.ArgumentParser(description="AFI-OS backup utility")
    parser.add_argument("command", choices=["create", "list", "restore-latest"])
    args = parser.parse_args()
    if args.command == "create":
        result = create_backup()
    elif args.command == "list":
        result = list_backups()
    else:
        result = restore_latest()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
