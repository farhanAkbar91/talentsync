"""Seed taksonomi skill dari app/ai/extraction/taxonomy/skills_v1.json (idempoten).

Pemakaian ( DATABASE_URL mengikuti .env atau env var):
    cd backend
    ./.venv/Scripts/python.exe scripts/seed_taxonomy.py
    ./.venv/Scripts/python.exe scripts/seed_taxonomy.py --json path/ke/skills.json

Hanya mencetak jumlah baris & versi taksonomi — tanpa kredensial/rahasia.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.services.taxonomy_service import DEFAULT_TAXONOMY_JSON, seed_from_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed taksonomi skill TalentSync AI")
    parser.add_argument(
        "--json",
        default=str(DEFAULT_TAXONOMY_JSON),
        help="Path berkas JSON taksonomi (default: skills_v1.json bawaan)",
    )
    args = parser.parse_args()

    json_path = Path(args.json)
    if not json_path.is_file():
        print(f"ERROR: berkas taksonomi tidak ditemukan: {json_path}")
        return 1

    db = SessionLocal()
    try:
        summary = seed_from_json(db, json_path)
    except Exception as exc:  # noqa: BLE001 — skrip CLI: lapangkan pesan error
        db.rollback()
        print(f"ERROR: seed gagal: {exc}")
        return 1
    finally:
        db.close()

    print(
        "Seed taksonomi selesai: "
        f"{summary['canonical']} skill kanon, {summary['aliases']} alias, "
        f"versi {summary['version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
