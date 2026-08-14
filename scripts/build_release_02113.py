#!/usr/bin/env python3
"""Build the checksum-verified AFI-OS 0.2.113 update package."""

from __future__ import annotations

import build_release_02112 as release_02112

builder = release_02112.builder
builder.VERSION = "0.2.113"
builder.ALLOWED_FROM_VERSIONS = ["0.2.111", "0.2.112"]
builder.FILES = tuple(
    dict.fromkeys(
        (
            *builder.FILES,
            "ROLLBACK-AFI-OS-0.2.113.command",
            "docs/README-FIRST-0.2.113.txt",
            "scripts/update_02113_tool.py",
            "tests/test_project_check_ui_02113.py",
            "tests/test_update_02113.py",
        )
    )
)


if __name__ == "__main__":
    builder.main()
