"""Re-embed massal: seluruh CV terkonfirmasi + lowongan aktif/paused (M3).

Dipakai setelah swap EMBEDDING_MODEL atau refresh vektor. Baris embedding
model lama tidak pernah dihapus (retensi multi-versi); upsert hanya untuk
(model aktif, text_kind aktif).

Pemakaian (dari backend/):
    ./.venv/Scripts/python.exe scripts/reembed_embeddings.py
    # --force: paksa walau embeddings_enabled=False
    ./.venv/Scripts/python.exe scripts/reembed_embeddings.py --force
    # --yes: izinkan DB non-sqlite (postgres/Supabase)
    ./.venv/Scripts/python.exe scripts/reembed_embeddings.py --yes

Tanpa --yes, skrip MENOLAK database non-sqlite — pengaman agar pengembangan
lokal tidak menulis massal ke Supabase secara tidak sengaja.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.embedding_service import reembed_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-embed CV & lowongan TalentSync AI (M3)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Paksa embedding walau settings.embeddings_enabled=False",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Konfirmasi eksplisit untuk menjalankan pada database non-sqlite "
        "(postgres/Supabase) — cegah tulis massal tak sengaja saat dev",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.database_url.startswith("sqlite") and not args.yes:
        print(
            "DITOLAK: DATABASE_URL bukan sqlite "
            "(pengaman tulis massal ke postgres/Supabase saat dev). "
            "Jalankan ulang dengan --yes bila memang disengaja."
        )
        return 1

    if not settings.embeddings_enabled and not args.force:
        print(
            "DILEWATI: embeddings_enabled=False. "
            "Gunakan --force untuk menjalankan tetap (re-embed massal offline)."
        )
        return 0

    summary = reembed_all(SessionLocal, settings, force=args.force)
    print(
        "Re-embed selesai "
        f"(model={settings.embedding_model}): "
        f"CV {summary['cvs_embedded']}/{summary['cvs_eligible']}, "
        f"lowongan {summary['jobs_embedded']}/{summary['jobs_eligible']}, "
        f"error={summary['errors']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
