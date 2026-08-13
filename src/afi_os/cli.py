import argparse
import os
import subprocess
import sys

from afi_os.config import get_settings
from afi_os.db import Base, engine


def main() -> None:
    parser = argparse.ArgumentParser(prog="afi-os")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create database tables")
    serve = sub.add_parser("serve", help="Run the local web application")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    sub.add_parser("seed-demo", help="Insert deterministic demo data")
    args = parser.parse_args()

    if args.command == "init-db":
        Base.metadata.create_all(bind=engine)
        print("Database initialized")
        return

    if args.command == "seed-demo":
        from afi_os.seed_demo import seed_demo

        seed_demo()
        return

    settings = get_settings()
    host = args.host or settings.host
    port = args.port or settings.port
    os.execvp(
        sys.executable,
        [sys.executable, "-m", "uvicorn", "afi_os.main:app", "--host", host, "--port", str(port)],
    )
