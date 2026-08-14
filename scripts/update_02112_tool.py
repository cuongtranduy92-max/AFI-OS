#!/usr/bin/env python3
"""AFI-OS 0.2.112 updater backed by the hardened transactional engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE / "update_02111_tool.py"
if not ENGINE_PATH.is_file():
    ENGINE_PATH = HERE / "payload" / "scripts" / "update_02111_tool.py"
SPEC = importlib.util.spec_from_file_location("afi_os_transactional_updater", ENGINE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Không tải được transactional updater engine")
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)

updater.UPDATE_VERSION = "0.2.112"


if __name__ == "__main__":
    raise SystemExit(updater.main())
