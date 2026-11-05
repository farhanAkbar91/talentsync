"""Siapkan database SQLite bersih khusus E2E browser.

CATATAN JUJUR: ini BUKAN pengganti verifikasi PostgreSQL — kompatibilitas
PostgreSQL 16 + pgvector tetap diverifikasi di CI (alembic + pytest dengan
DATABASE_URL_TEST). Jalur ini hanya agar alur E2E via browser dapat dijalankan
di mesin tanpa Docker/PostgreSQL.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402


def main() -> int:
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        print("bootstrap_e2e hanya untuk sqlite; DATABASE_URL saat ini:", url)
        return 1
    db_path = Path(url.replace("sqlite:///", ""))
    if db_path.exists():
        db_path.unlink()
    import app.models  # noqa: F401 — daftarkan seluruh model

    engine = create_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    print("E2E database siap:", db_path.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
