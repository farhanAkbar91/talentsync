"""CLI ingestion lowongan eksternal (RemoteOK / Remotive / Arbeitnow).

Pemakaian (dari backend/):
    .venv/Scripts/python -m scripts.ingest_jobs --source all --limit 50
    .venv/Scripts/python -m scripts.ingest_jobs --source remoteok --limit 10 --dry-run
    .venv/Scripts/python -m scripts.ingest_jobs --sweep-expired   # arsipkan lowongan lewat batas

Catatan:
- Hanya API publik (tanpa kunci, tanpa scraping); koneksi jaringan HANYA terjadi
  saat skrip benar-benar dijalankan — bukan saat import.
- --source all menjalankan tiga sumber BERURUTAN dengan jeda sopan 2 detik
  (ToS Arbeitnow melarang abuse; docs/03 §3).
- --limit berlaku per sumber (Remotive via param API; RemoteOK/Arbeitnow dipotong
  lokal).
- Tidak ada secret yang dipakai/dicetak (semua sumber publik tanpa autentikasi).
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.ingestion import ingest_service, sources  # noqa: E402

FETCHERS = {
    "remoteok": sources.fetch_remoteok,
    "remotive": sources.fetch_remotive,
    "arbeitnow": sources.fetch_arbeitnow,
}

# Jeda antar sumber pada mode --source all (sopan terhadap API publik).
POLITE_DELAY_SECONDS = 2.0


def _run_source(db: Session, source: str, limit: int, dry_run: bool) -> dict:
    """Fetch satu sumber lalu ingest; konektor tidak pernah raise (→ [])."""
    items = FETCHERS[source](limit=limit)
    return ingest_service.ingest(
        db, get_settings(), source_type=source, items=items, dry_run=dry_run
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest lowongan eksternal TalentSync AI")
    parser.add_argument(
        "--source",
        choices=[*FETCHERS, "all"],
        default="all",
        help="sumber tunggal atau semua (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="batas jumlah item per sumber (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="hitung saja, tanpa menulis ke database",
    )
    parser.add_argument(
        "--sweep-expired",
        action="store_true",
        help="arsipkan lowongan aktif yang closing_at-nya sudah lewat (status expired)",
    )
    args = parser.parse_args()

    chosen = (
        []
        if args.sweep_expired and "--source" not in sys.argv
        else (list(FETCHERS) if args.source == "all" else [args.source])
    )
    # --source all (default) tanpa --sweep-expired tetap masuk akal untuk tarik
    # data saja; sweep hanya jalan bila flag diminta.
    if (
        args.source == "all"
        and not args.sweep_expired
        and not any(a == "--source" for a in __import__("sys").argv)
    ):
        pass  # default all + tanpa sweep: perilaku lama dipertahankan
    db = SessionLocal()
    try:
        for index, source in enumerate(chosen):
            if index > 0:
                time.sleep(POLITE_DELAY_SECONDS)
            result = _run_source(db, source, args.limit, args.dry_run)
            mode = " (dry-run)" if args.dry_run else ""
            print(
                f"[{source}{mode}] inserted={result['inserted']} "
                f"skipped={result['skipped']} seen={result['seen']}"
            )
        if args.sweep_expired:
            sweep = ingest_service.sweep_expired_jobs(db)
            mode = " (dry-run)" if args.dry_run else ""
            print(f"[sweep{mode}] expired={sweep['expired']}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
