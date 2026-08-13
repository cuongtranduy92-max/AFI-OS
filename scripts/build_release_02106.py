#!/usr/bin/env python3
"""Build the checksum-verified AFI-OS 0.2.106 update package."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]).expanduser().resolve()
VERSION = "0.2.106"
FILES = (
    "README.md",
    "ROLLBACK-AFI-OS-0.2.106.command",
    "SETUP-TRAFFIC-DATA.command",
    "apps/web/app.js",
    "apps/web/index.html",
    "apps/web/styles.css",
    "docs/CHANGELOG.md",
    "docs/README-FIRST-0.2.106.txt",
    "docs/RUNBOOK.md",
    "docs/TASKBOARD.md",
    "docs/TEST_REPORT.md",
    "pyproject.toml",
    "migrations/versions/e91f4d7a2c18_resource_management.py",
    "scripts/update_02106_tool.py",
    "src/afi_os/__init__.py",
    "src/afi_os/api/__init__.py",
    "src/afi_os/api/camp_plans.py",
    "src/afi_os/api/resources.py",
    "src/afi_os/enums.py",
    "src/afi_os/models.py",
    "src/afi_os/schemas.py",
    "src/afi_os/services/resource_rules.py",
    "src/afi_os/services/resources.py",
    "tests/test_camp_plans_02104.py",
    "tests/test_camp_plan_ui_02104.py",
    "tests/test_exposure_022.py",
    "tests/test_resource_migration_02106.py",
    "tests/test_resources_02106.py",
    "tests/test_update_02106.py",
    "uv.lock",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    payload = OUTPUT / "payload"
    payload.mkdir(parents=True)
    entries = []
    for relative in FILES:
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            raise SystemExit(f"Missing regular release file: {relative}")
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        mode = stat.S_IMODE(destination.stat().st_mode)
        entries.append(
            {
                "path": relative,
                "sha256": sha256(destination),
                "size_bytes": destination.stat().st_size,
                "mode": format(mode, "o"),
            }
        )

    manifest = {
        "format_version": 1,
        "update_version": VERSION,
        "allowed_from_versions": ["0.2.105"],
        "expected_migration_head": "e91f4d7a2c18",
        "files": entries,
    }
    manifest_path = OUTPUT / "payload-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(ROOT / "UPDATE-AFI-OS-0.2.106.command", OUTPUT)
    shutil.copy2(ROOT / "scripts/update_02106_tool.py", OUTPUT / "update_02106_tool.py")
    shutil.copy2(ROOT / "docs/README-FIRST-0.2.106.txt", OUTPUT / "README-FIRST.txt")
    checksum_paths = (
        "UPDATE-AFI-OS-0.2.106.command",
        "README-FIRST.txt",
        "payload-manifest.json",
        "update_02106_tool.py",
    )
    checksum_text = "".join(
        f"{sha256(OUTPUT / name)}  {name}\n" for name in checksum_paths
    )
    (OUTPUT / "AFI-OS-update-0.2.106.sha256").write_text(
        checksum_text,
        encoding="utf-8",
    )
    print(f"Built {OUTPUT} with {len(entries)} payload files")


if __name__ == "__main__":
    main()
