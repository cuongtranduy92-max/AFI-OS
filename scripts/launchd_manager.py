#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

SERVER_LABEL = "com.afi-os.server"
MAINTENANCE_LABEL = "com.afi-os.maintenance"


class LaunchdError(RuntimeError):
    pass


def validate_target(target: Path) -> Path:
    target = target.expanduser().resolve()
    if not target.is_dir() or target.is_symlink():
        raise LaunchdError("AFI-OS target is not a normal directory")
    for relative in (".venv/bin/python", "src/afi_os/main.py", "src/afi_os/maintenance.py"):
        path = target / relative
        if not path.exists():
            raise LaunchdError(f"Missing required runtime file: {relative}")
    return target


def build_plists(target: Path) -> dict[str, dict]:
    target = validate_target(target)
    python = str(target / ".venv/bin/python")
    environment = {
        "AFI_OS_ENV": "production",
        "AFI_OS_ALLOW_DEMO_SEED": "false",
        "PYTHONPATH": str(target / "src"),
        "PYTHONUNBUFFERED": "1",
    }
    server = {
        "Label": SERVER_LABEL,
        "ProgramArguments": [
            python,
            "-m",
            "uvicorn",
            "afi_os.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ],
        "WorkingDirectory": str(target),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(target / "logs/launchd-server.log"),
        "StandardErrorPath": str(target / "logs/launchd-server-error.log"),
    }
    maintenance = {
        "Label": MAINTENANCE_LABEL,
        "ProgramArguments": [python, "-m", "afi_os.maintenance"],
        "WorkingDirectory": str(target),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        # Calendar triggers are coalesced by launchd after macOS wakes, while a
        # StartInterval tick can be lost completely during sleep. Two fixed
        # half-hour slots keep the 24/7 heartbeat recoverable on laptops.
        "StartCalendarInterval": [{"Minute": 0}, {"Minute": 30}],
        "LowPriorityIO": True,
        "StandardOutPath": str(target / "logs/maintenance.log"),
        "StandardErrorPath": str(target / "logs/maintenance-error.log"),
    }
    return {SERVER_LABEL: server, MAINTENANCE_LABEL: maintenance}


def launch_agents_root() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist_path(label: str, root: Path | None = None) -> Path:
    return (root or launch_agents_root()) / f"{label}.plist"


def write_plist(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o644)
    temporary.replace(path)


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise LaunchdError(f"{' '.join(args)} failed: {result.stdout.strip()}")
    return result


def service_domain() -> str:
    return f"gui/{os.getuid()}"


def install(target: Path, *, agents_root: Path | None = None) -> dict:
    target = validate_target(target)
    (target / "logs").mkdir(parents=True, exist_ok=True)
    plists = build_plists(target)
    domain = service_domain()
    paths = {label: plist_path(label, agents_root) for label in plists}
    for label, path in paths.items():
        _run(["launchctl", "bootout", domain, str(path)], check=False)
        write_plist(path, plists[label])
        _run(["launchctl", "bootstrap", domain, str(path)])
        _run(["launchctl", "enable", f"{domain}/{label}"])
    _run(["launchctl", "kickstart", "-k", f"{domain}/{SERVER_LABEL}"])
    return {
        "installed": True,
        "server_label": SERVER_LABEL,
        "maintenance_label": MAINTENANCE_LABEL,
        "plists": {label: str(path) for label, path in paths.items()},
    }


def wait_for_health(timeout_seconds: int = 30) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            with urlopen("http://127.0.0.1:8765/api/health", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ok":
                return payload
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise LaunchdError(f"AFI-OS health check timed out: {last_error}")


def status(*, agents_root: Path | None = None) -> dict:
    domain = service_domain()
    services = {}
    for label in (SERVER_LABEL, MAINTENANCE_LABEL):
        result = _run(["launchctl", "print", f"{domain}/{label}"], check=False)
        services[label] = {
            "loaded": result.returncode == 0,
            "plist": str(plist_path(label, agents_root)),
        }
    return {"domain": domain, "services": services}


def uninstall(*, agents_root: Path | None = None) -> dict:
    domain = service_domain()
    removed = []
    for label in (SERVER_LABEL, MAINTENANCE_LABEL):
        path = plist_path(label, agents_root)
        _run(["launchctl", "bootout", domain, str(path)], check=False)
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return {"installed": False, "removed": removed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage AFI-OS macOS 24/7 services")
    sub = parser.add_subparsers(dest="command", required=True)
    install_parser = sub.add_parser("install")
    install_parser.add_argument("--target", required=True)
    sub.add_parser("status")
    sub.add_parser("uninstall")
    args = parser.parse_args()
    if args.command == "install":
        result = install(Path(args.target))
        result["health"] = wait_for_health()
    elif args.command == "status":
        result = status()
    else:
        result = uninstall()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
