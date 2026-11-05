"""Benchmark kecil model Groq untuk kebutuhan TalentSync AI (M8: CV Optimization).

Benchmark 3 tugas per model:
  T1  Ekstraksi terstruktur  : CV teks -> JSON payload (json_schema strict=false,
      fallback json_object bila model tidak mendukung structured outputs).
  T2  Rewrite ter-grounding  : 2 bullet CV ditulis ulang utk job description;
      dicek fabrikasi (entitas/keterampilan yang TIDAK ada di CV asli).
  T3  Latensi                : waktu total + token usage per panggilan.

Cara pakai:
  1. Isi GROQ_API_KEY di backend/.env (atau export di shell).
  2. cd backend && .venv/Scripts/python scripts/benchmark_groq_models.py

Catatan:
- Tidak menampilkan API key; output hanya hasil evaluasi.
- Konsumsi kuota kecil: ~3 model x 3 panggilan (aman utk free tier 30 RPM/1K RPD).
- Hasil mentah ditulis ke scripts/benchmark_results.json (tanpa secret).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

GROQ_BASE = "https://api.groq.com/openai/v1"
CANDIDATES = [
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-20b",
    "allam-2-7b",
]

CV_TEXT = """Budi Santoso — Data Analyst
Email: budi.santoso@example.dev | Telepon: +62 812-3456-7890 | Jakarta
RINGKASAN
Analis data dengan 2 tahun pengalaman mengolah data penjualan dan operasional
menggunakan SQL dan Excel, menyusun dashboard rutin untuk tim marketing.
PENGALAMAN
Data Analyst — PT Nusantara Retail (2023-01 - sekarang)
- Membuat laporan performa penjualan mingguan untuk 12 cabang menggunakan SQL
  dan Excel pivot.
- Mengotomatiskan rekap data harian dengan Python pandas, menghemat 5 jam kerja
  manual per minggu.
- Menganalisis pola retensi pelanggan dari 200 ribu baris transaksi.
Junior Data Analyst — CV Maju Bersama (2021-07 - 2022-12)
- Membersihkan dan memvalidasi data survei pelanggan (±15 ribu respons per bulan).
PENDIDIKAN
S1 Statistika, Universitas Airlangga (2017-2021), IPK 3.42
KEAHLIAN
SQL (lanjut), Excel lanjutan, Python pandas, visualisasi data matplotlib, Google Sheets
SERTIFIKASI
Google Data Analytics Professional Certificate (2022)"""

JOB_TEXT = """Lowongan: Data Analyst (Senior) — PT Teknologi Cerdas
Kualifikasi: minimal 4 tahun pengalaman analisis data; menguasai SQL lanjutan,
Python, dan dashboarding dengan Power BI atau Tableau; membangun pipeline data;
terbiasa mempresentasikan insight ke manajemen. Skill pengalaman: data analyst."""

EXTRACT_SCHEMA = {
    "name": "cv_payload",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "nama": {"type": "string"},
            "email": {"type": "string"},
            "telepon": {"type": "string"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "pengalaman": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "judul": {"type": "string"},
                        "perusahaan": {"type": "string"},
                        "periode": {"type": "string"},
                    },
                },
            },
            "pendidikan": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "jenjang": {"type": "string"},
                        "institusi": {"type": "string"},
                        "tahun": {"type": "string"},
                    },
                },
            },
        },
    },
}


def load_api_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    # anchor ke lokasi skrip: scripts/ -> backend/ -> root/ (robust terhadap CWD)
    here = Path(__file__).resolve()
    for loc in (here.parents[1] / ".env", here.parents[2] / ".env"):
        if loc.exists():
            m = re.search(r"^GROQ_API_KEY\s*=\s*(.+?)\s*$", loc.read_text(encoding="utf-8"), re.M)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def call_model(
    client: httpx.Client, model: str, messages: list, response_format: dict | None
) -> dict:
    body: dict = {"model": model, "messages": messages, "temperature": 0.2}
    if response_format:
        body["response_format"] = response_format
    t0 = time.perf_counter()
    r = client.post(f"{GROQ_BASE}/chat/completions", json=body, timeout=90)
    elapsed = time.perf_counter() - t0
    if r.status_code == 400:
        err = r.json().get("error", {}).get("message", "")[:160]
        return {"error": f"400: {err}", "elapsed": elapsed}
    if r.status_code == 429:
        return {"error": "429 rate limit", "elapsed": elapsed}
    r.raise_for_status()
    data = r.json()
    return {
        "content": data["choices"][0]["message"]["content"],
        "usage": data.get("usage", {}),
        "elapsed": round(elapsed, 2),
    }


def t1_extract(client: httpx.Client, model: str) -> dict:
    msgs = [
        {"role": "system", "content": "Ekstrak data CV ke JSON sesuai skema. Jawab JSON saja."},
        {"role": "user", "content": CV_TEXT},
    ]
    out = call_model(client, model, msgs, {"type": "json_schema", "json_schema": EXTRACT_SCHEMA})
    if "error" in out and "400" in out["error"]:
        # fallback: JSON object mode
        fallback = call_model(client, model, msgs, {"type": "json_object"})
        fallback["fallback_json_object"] = True
        out = fallback
    if "error" not in out:
        try:
            payload = json.loads(out["content"])
            out["json_valid"] = True
            out["nama_ok"] = "Budi Santoso" in str(payload.get("nama", ""))
            out["skills_count"] = len(payload.get("skills", []))
            out["pengalaman_count"] = len(payload.get("pengalaman", []))
        except json.JSONDecodeError:
            out["json_valid"] = False
        out.pop("content", None)
    return out


def t2_grounding(client: httpx.Client, model: str) -> dict:
    msgs = [
        {
            "role": "system",
            "content": (
                "Kamu editor CV. Tulis ulang bullet pengalaman agar lebih kuat untuk lowongan "
                "yang diberikan. ATURAN KETAT: (1) jangan menambah keterampilan, alat, "
                "perusahaan, atau angka yang tidak ada di CV asli; (2) jangan mengubah fakta "
                "(tanggal, perusahaan, jabatan); (3) balas JSON dengan format "
                '{"edits":[{"source_ref":"<nomor bullet asli>",'
                '"original_text":"...","suggested_text":"...","rationale":"..."}]}.'
            ),
        },
        {
            "role": "user",
            "content": (
                f"CV:\n{CV_TEXT}\n\nLOWONGAN:\n{JOB_TEXT}\n\n"
                "Tulis ulang bullet 1 dan bullet 3 bagian PENGALAMAN Data Analyst."
            ),
        },
    ]
    out = call_model(client, model, msgs, {"type": "json_object"})
    if "error" not in out:
        try:
            payload = json.loads(out["content"])
            edits = payload.get("edits", [])
            cv_lower = CV_TEXT.lower()
            fabricated = []
            for e in edits:
                # kata kunci yang HARUSNYA tidak muncul karena tidak ada di CV asli
                for trap in ("power bi", "tableau", "pipeline data"):
                    if trap in str(e.get("suggested_text", "")).lower() and trap not in cv_lower:
                        fabricated.append(f"{e.get('source_ref')} menambah '{trap}'")
            out["edits_count"] = len(edits)
            out["fabrications"] = fabricated or "tidak ada"
            out["json_valid"] = True
        except json.JSONDecodeError:
            out["json_valid"] = False
        out.pop("content", None)
    return out


def main() -> None:
    key = load_api_key()
    if not key:
        print(
            "GROQ_API_KEY tidak ditemukan di shell / backend/.env / root .env "
            "— benchmark tidak bisa dijalankan."
        )
        print("Tambahkan kunci ke backend/.env lalu jalankan ulang skrip ini.")
        sys.exit(1)

    with httpx.Client(headers={"Authorization": f"Bearer {key}"}) as client:
        models = client.get(f"{GROQ_BASE}/models", timeout=30).json()
        available = {m["id"] for m in models.get("data", [])}
        print(
            f"Model tersedia utk akun ini: {len(available)} — kandidat diuji:",
            [m for m in CANDIDATES if m in available] or "(tidak ada kandidat aktif)",
        )

        results = {}
        for model in CANDIDATES:
            if model not in available:
                results[model] = {"status": "tidak tersedia utk akun ini"}
                continue
            print(f"\n== {model} ==")
            r1 = t1_extract(client, model)
            print(" T1 ekstraksi :", json.dumps(r1, ensure_ascii=False))
            time.sleep(2)  # jaga RPM
            r2 = t2_grounding(client, model)
            print(" T2 grounding :", json.dumps(r2, ensure_ascii=False))
            time.sleep(2)
            results[model] = {"T1": r1, "T2": r2}

        out_path = Path(__file__).parent / "benchmark_results.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nHasil lengkap: {out_path}")


if __name__ == "__main__":
    main()
