import os
from pathlib import Path

TEST_DB = Path("/tmp/afi_os_test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["AFI_OS_DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["AFI_OS_ALLOW_DEMO_SEED"] = "false"
