#!/usr/bin/env python3
"""Build the checksum-verified AFI-OS 0.2.111 update package."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[1]).expanduser().resolve()
VERSION = "0.2.111"
FILES = (
    "README.md",
    "ROLLBACK-AFI-OS-0.2.111.command",
    "SETUP-ADVERTISER.command",
    "SETUP-LLM.command",
    "SETUP-TRAFFIC-DATA.command",
    "apps/web/app.js",
    "apps/web/index.html",
    "apps/web/styles.css",
    "docs/CHANGELOG.md",
    "docs/MASTER_SPEC.md",
    "docs/README-FIRST-0.2.111.txt",
    "docs/RUNBOOK.md",
    "docs/TASKBOARD.md",
    "docs/TEST_REPORT.md",
    "pyproject.toml",
    "uv.lock",
    "migrations/versions/93d7e5a2b1c4_advertiser_provider.py",
    "scripts/update_02111_tool.py",
    "src/afi_os/__init__.py",
    "src/afi_os/api/appraisal.py",
    "src/afi_os/api/ad_intelligence.py",
    "src/afi_os/api/portfolio.py",
    "src/afi_os/api/term_extraction.py",
    "src/afi_os/enums.py",
    "src/afi_os/main.py",
    "src/afi_os/models.py",
    "src/afi_os/schemas.py",
    "src/afi_os/services/appraisal.py",
    "src/afi_os/services/appraisal_jobs.py",
    "src/afi_os/services/advertiser_keychain.py",
    "src/afi_os/services/advertiser_provider.py",
    "src/afi_os/services/campaign_diagnosis.py",
    "src/afi_os/config.py",
    "src/afi_os/services/google_ads_keyword_check.py",
    "src/afi_os/services/llm_terms.py",
    "src/afi_os/services/resource_rules.py",
    "src/afi_os/services/portfolio.py",
    "src/afi_os/services/project_check.py",
    "src/afi_os/services/terms_research.py",
    "src/afi_os/services/traffic_provider.py",
    "tests/test_apify_traffic_02105.py",
    "tests/test_advertiser_provider_02111.py",
    "tests/test_appraisal_contract_02101.py",
    "tests/test_camp_plan_ui_02104.py",
    "tests/test_campaign_diagnosis_02108.py",
    "tests/test_exposure_022.py",
    "tests/test_llm_terms_02107.py",
    "tests/test_progressive_appraisal_02109.py",
    "tests/test_progressive_appraisal_migration_02109.py",
    "tests/test_terms_no_blind_retry_02109.py",
    "tests/test_update_02111.py",
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
        "allowed_from_versions": ["0.2.110", "0.2.111"],
        "expected_migration_head": "93d7e5a2b1c4",
        "files": entries,
    }
    manifest_path = OUTPUT / "payload-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release_code = VERSION.replace(".", "")
    update_command = f"UPDATE-AFI-OS-{VERSION}.command"
    update_tool = f"update_{release_code}_tool.py"
    readme = f"docs/README-FIRST-{VERSION}.txt"
    shutil.copy2(ROOT / update_command, OUTPUT)
    shutil.copy2(ROOT / f"scripts/{update_tool}", OUTPUT)
    shutil.copy2(ROOT / readme, OUTPUT / "README-FIRST.txt")
    checksum_paths = (
        update_command,
        "README-FIRST.txt",
        "payload-manifest.json",
        update_tool,
    )
    checksum_text = "".join(
        f"{sha256(OUTPUT / name)}  {name}\n" for name in checksum_paths
    )
    (OUTPUT / f"AFI-OS-update-{VERSION}.sha256").write_text(
        checksum_text,
        encoding="utf-8",
    )
    print(f"Built {OUTPUT} with {len(entries)} payload files")


if __name__ == "__main__":
    main()
