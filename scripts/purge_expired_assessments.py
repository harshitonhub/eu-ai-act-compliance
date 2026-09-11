"""Delete AssessmentRecord rows older than the retention window.

Run periodically (e.g. via cron) against the production database:
    python scripts/purge_expired_assessments.py [--retention-days N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.observability.retention import DEFAULT_RETENTION_DAYS, purge_expired_assessments
from src.persistence.db import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retention-days", type=int, default=DEFAULT_RETENTION_DAYS)
    args = parser.parse_args()

    with SessionLocal() as session:
        count = purge_expired_assessments(session, retention_days=args.retention_days)

    print(f"Purged {count} assessment record(s) older than {args.retention_days} days.")


if __name__ == "__main__":
    main()
