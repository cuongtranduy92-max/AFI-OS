#!/usr/bin/env python3
"""Build the checksum-verified AFI-OS 0.2.112 update package."""

from __future__ import annotations

import build_release_02111 as builder

builder.VERSION = "0.2.112"
builder.FILES = tuple(
    dict.fromkeys(
        (
            *builder.FILES,
            "ROLLBACK-AFI-OS-0.2.112.command",
            "docs/README-FIRST-0.2.112.txt",
            "scripts/update_02112_tool.py",
            "src/afi_os/api/finance.py",
            "src/afi_os/services/llm_extractor.py",
            "src/afi_os/services/true_profit.py",
            "tests/test_true_profit_02112.py",
        )
    )
)


if __name__ == "__main__":
    builder.main()
