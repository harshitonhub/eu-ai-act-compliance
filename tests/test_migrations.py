import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str, db_url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_migration_upgrade_and_downgrade_round_trip(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migration_test.db'}"

    up = _run_alembic("upgrade", "head", db_url=db_url)
    assert up.returncode == 0, up.stderr

    down = _run_alembic("downgrade", "base", db_url=db_url)
    assert down.returncode == 0, down.stderr
