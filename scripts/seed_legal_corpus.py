"""Load the seed EU AI Act legal corpus into the database. Idempotent -- safe to run
against an already-seeded database (no-op).

Run once after `alembic upgrade head` on a fresh database:
    python scripts/seed_legal_corpus.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.legal.ingest import ingest_seed, seed_is_present
from src.persistence.db import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        if seed_is_present(session):
            print("Legal corpus already seeded -- no-op.")
            return
        ingest_seed(session)
    print("Seeded legal corpus: AI Act Article 5, Article 6, Annex III, Articles 9-15; "
          "GDPR Article 22, Article 35.")


if __name__ == "__main__":
    main()
