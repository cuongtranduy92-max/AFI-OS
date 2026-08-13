#!/usr/bin/env python3
"""Build the checksum-verified AFI-OS 0.2.107 update package."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]).expanduser().resolve()
VERSION = "0.2.107"
FILES = (
    "README.md",
    "ROLLBACK-AFI-OS-0.2.107.command",
    "SETUP-LLM.command",
    "SETUP-TRAFFIC-DATA.command",
    "apps/web/app.js",
    "apps/web/index.html",
    "apps/web/styles.css",
    "docs/CHANGELOG.md",
    "docs/README-FIRST-0.2.107.txt",
    "docs/RUNBOOK.md",
    "docs/TASKBOARD.md",
    "docs/TEST_REPORT.md",
    "pyproject.toml",
    "migrations/versions/4f7c2a91d5e0_llm_terms_extraction.py",
    "scripts/update_02107_tool.py",
    "src/afi_os/__init__.py",
    "src/afi_os/api/__init__.py",
    "src/afi_os/api/portfolio.py",
    "src/afi_os/api/term_extraction.py",
    "src/afi_os/config.py",
    "src/afi_os/models.py",
    "src/afi_os/schemas.py",
    "src/afi_os/services/appraisal.py",
    "src/afi_os/services/commercial_review.py",
    "src/afi_os/services/llm_extractor.py",
    "src/afi_os/services/llm_keychain.py",
    "src/afi_os/services/llm_terms.py",
    "src/afi_os/services/portfolio.py",
    "src/afi_os/services/programs.py",
    "src/afi_os/services/project_check.py",
    "src/afi_os/services/terms_research.py",
    "tests/test_camp_plan_ui_02104.py",
    "tests/test_exposure_022.py",
    "tests/test_llm_extractor_02107.py",
    "tests/test_llm_terms_02107.py",
    "tests/test_llm_terms_migration_02107.py",
    "tests/test_sprint1.py",
    "tests/test_update_02107.py",
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
        "allowed_from_versions": ["0.2.106"],
        "expected_migration_head": "4f7c2a91d5e0",
        "files": entries,
    }
    manifest_path = OUTPUT / "payload-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(ROOT / "UPDATE-AFI-OS-0.2.107.command", OUTPUT)
    shutil.copy2(ROOT / "scripts/update_02107_tool.py", OUTPUT / "update_02107_tool.py")
    shutil.copy2(ROOT / "docs/README-FIRST-0.2.107.txt", OUTPUT / "README-FIRST.txt")
    checksum_paths = (
        "UPDATE-AFI-OS-0.2.107.command",
        "README-FIRST.txt",
        "payload-manifest.json",
        "update_02107_tool.py",
    )
    checksum_text = "".join(
        f"{sha256(OUTPUT / name)}  {name}\n" for name in checksum_paths
    )
    (OUTPUT / "AFI-OS-update-0.2.107.sha256").write_text(
        checksum_text,
        encoding="utf-8",
    )
    print(f"Built {OUTPUT} with {len(entries)} payload files")


if __name__ == "__main__":
    main()
