"""Generator golden set sintetis untuk evaluasi P3 (docs/03 §4.4).

Menghasilkan di <repo>/eval/golden/:
  - cvs/CV-XXX.json   : 12 profil CV sintetis (terstruktur, dwibahasa ID/EN)
  - jobs/JOB-XXX.json : 30 lowongan sintetis (10 peran × 3 level)
  - pairs_labels.csv  : ±84 pasangan CV-job berlabel rubrik 0-3 (docs/03 §4.5)
  - manifest.json     : provenance dataset

Dataset ini "jelas sintetis & berlabel" (12 CV sintetis pertama dari komposisi
golden set); CV volunteer menyusul terpisah. Tanpa PII — semua nama fiktif,
email @example.dev. Deterministik (seed tetap).

Jalankan dari backend/: .venv/Scripts/python scripts/generate_golden_synthetic.py
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

SEED = 20261106
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "eval" / "golden"

ROLES: dict[str, dict] = {
    "data-analyst": {
        "id": "analis data",
        "en": "Data Analyst",
        "hard": ["SQL", "Python", "pandas", "Excel", "visualisasi data", "statistika"],
        "pref": ["Power BI", "Tableau", "A/B testing"],
        "adjacent": "business-analyst",
    },
    "business-analyst": {
        "id": "analis bisnis",
        "en": "Business Analyst",
        "hard": ["analisis bisnis", "SQL", "Excel", "documentasi proses", "requirements gathering"],
        "pref": ["BPMN", "Tableau"],
        "adjacent": "data-analyst",
    },
    "frontend-developer": {
        "id": "pengembang frontend",
        "en": "Frontend Developer",
        "hard": ["JavaScript", "React", "TypeScript", "HTML", "CSS"],
        "pref": ["Next.js", "Tailwind CSS", "testing"],
        "adjacent": "fullstack-developer",
    },
    "backend-developer": {
        "id": "pengembang backend",
        "en": "Backend Developer",
        "hard": ["Python", "FastAPI", "PostgreSQL", "REST API", "Docker"],
        "pref": ["Redis", "SQLAlchemy", "Kubernetes"],
        "adjacent": "fullstack-developer",
    },
    "fullstack-developer": {
        "id": "pengembang fullstack",
        "en": "Fullstack Developer",
        "hard": ["JavaScript", "React", "Node.js", "PostgreSQL", "REST API"],
        "pref": ["TypeScript", "Docker"],
        "adjacent": "backend-developer",
    },
    "qa-engineer": {
        "id": "insinyur QA",
        "en": "QA Engineer",
        "hard": ["manual testing", "Playwright", "API testing", "Postman", "manajemen bug"],
        "pref": ["Selenium", "Python"],
        "adjacent": "backend-developer",
    },
    "ui-ux-designer": {
        "id": "desainer UI/UX",
        "en": "UI/UX Designer",
        "hard": ["Figma", "prototyping", "design system", "user research", "wireframe"],
        "pref": ["usability testing", "HTML"],
        "adjacent": "frontend-developer",
    },
    "devops-engineer": {
        "id": "insinyur DevOps",
        "en": "DevOps Engineer",
        "hard": ["Docker", "CI/CD", "GitHub Actions", "Linux", "Terraform"],
        "pref": ["Kubernetes", "AWS"],
        "adjacent": "backend-developer",
    },
    "mobile-developer": {
        "id": "pengembang mobile",
        "en": "Mobile Developer",
        "hard": ["Flutter", "Dart", "REST API", "SQLite"],
        "pref": ["Kotlin", "Firebase"],
        "adjacent": "fullstack-developer",
    },
    "product-manager": {
        "id": "manajer produk",
        "en": "Product Manager",
        "hard": ["product roadmap", "agile", "analisis bisnis", "stakeholder management"],
        "pref": ["Figma", "SQL"],
        "adjacent": "business-analyst",
    },
}

LEVELS = {
    "junior": {"years": 1, "edu": "S1", "id": "junior"},
    "mid": {"years": 3, "edu": "S1", "id": "menengah"},
    "senior": {"years": 6, "edu": "S2", "id": "senior"},
}

NAMA = [
    "Budi Santoso",
    "Siti Rahmawati",
    "Andi Pratama",
    "Dewi Lestari",
    "Rizky Hidayat",
    "Maya Kusuma",
    "Fajar Nugroho",
    "Intan Permata",
    "Agus Wibowo",
    "Lina Marlina",
    "Bagas Setiawan",
    "Nadia Safitri",
]
PERUSAHAAN = [
    "PT Nusantara Digital",
    "PT Teknologi Cerdas",
    "CV Maju Bersama",
    "PT Solusi Data Indonesia",
    "PT Kreasi Aplikasi",
    "PT Sistem Andalan",
]
KOTA = ["Jakarta", "Surabaya", "Bandung", "Yogyakarta", "Remote"]


def _cv_text(cv: dict) -> str:
    """Render CV terstruktur ke teks (seperti hasil ekstraksi PDF)."""
    lines = [
        f"{cv['nama']} — {cv['headline']}",
        f"{cv['email']} | {cv['telepon']} | {cv['lokasi']}",
        "RINGKASAN",
        cv["ringkasan"],
        "PENGALAMAN",
    ]
    for exp in cv["pengalaman"]:
        lines.append(f"{exp['judul']} — {exp['perusahaan']} ({exp['periode']})")
        lines.extend(f"- {b}" for b in exp["bullet"])
    lines.append("PENDIDIKAN")
    for edu in cv["pendidikan"]:
        lines.append(
            f"{edu['jenjang']} {edu['jurusan']}, {edu['institusi']} "
            f"({edu['tahun']}), IPK {edu['ipk']}"
        )
    lines.append("KEAHLIAN")
    lines.append(", ".join(cv["skills"]))
    if cv["sertifikasi"]:
        lines.append("SERTIFIKASI")
        lines.extend(f"- {c}" for c in cv["sertifikasi"])
    return "\n".join(lines)


def _job_text(job: dict) -> str:
    lines = [
        f"POSISI: {job['title']} — {job['perusahaan']} ({job['lokasi']})",
        job["deskripsi"],
        "KUALIFIKASI",
    ]
    lines.extend(f"- {k}" for k in job["requirements"])
    lines.append("KEAHLIAN WAJIB: " + ", ".join(s["name"] for s in job["skills"]))
    if job["responsibilities"]:
        lines.append("TANGGUNG JAWAB")
        lines.extend(f"- {r}" for r in job["responsibilities"])
    return "\n".join(lines)


def main() -> None:
    rng = random.Random(SEED)
    cvs, jobs = [], []

    # --- 12 CV: tiap peran level bervariasi ---
    plan = [
        ("data-analyst", "junior"),
        ("data-analyst", "mid"),
        ("frontend-developer", "junior"),
        ("frontend-developer", "senior"),
        ("backend-developer", "mid"),
        ("backend-developer", "senior"),
        ("business-analyst", "mid"),
        ("fullstack-developer", "mid"),
        ("qa-engineer", "junior"),
        ("ui-ux-designer", "mid"),
        ("devops-engineer", "senior"),
        ("product-manager", "mid"),
    ]
    for i, (role_key, level_key) in enumerate(plan, start=1):
        role, level = ROLES[role_key], LEVELS[level_key]
        nama = NAMA[i - 1]
        skills = (
            role["hard"][: 3 + min(level["years"], 3)]
            + role["pref"][: 1 if level_key == "junior" else 2]
        )
        yrs = level["years"]
        cvs.append(
            {
                "id": f"CV-{i:03d}",
                "synthetic": True,
                "role": role_key,
                "level": level_key,
                "nama": nama,
                "headline": f"{role['id']} {level['id']}".strip(),
                "email": f"{nama.split()[0].lower()}.{nama.split()[1].lower()}@example.dev",
                "lokasi": rng.choice(KOTA),
                "telepon": (
                    f"+62 81{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
                    f"-{rng.randint(1000, 9999)}"
                ),
                "ringkasan": (
                    f"{role['en']} dengan {yrs} tahun pengalaman pada bidang {role['id']}, "
                    f"terbiasa bekerja dengan {'/'.join(role['hard'][:3])} "
                    "dan berkolaborasi dalam tim produk."
                ),
                "skills": skills,
                "pengalaman": [
                    {
                        "judul": f"{role['en']} "
                        f"{'Junior' if level_key == 'junior' else ''}".strip(),
                        "perusahaan": PERUSAHAAN[i % len(PERUSAHAAN)],
                        "periode": f"{2026 - yrs}-01 - sekarang"
                        if yrs > 0
                        else "2026-01 - sekarang",
                        "bullet": [
                            f"Menangani pekerjaan {role['id']} menggunakan "
                            f"{role['hard'][0]} dan {role['hard'][1]}.",
                            f"Berkolaborasi dengan tim lintas fungsi untuk menghasilkan "
                            f"{role['hard'][2] if len(role['hard']) > 2 else role['hard'][0]} "
                            "yang terukur.",
                        ],
                    }
                ],
                "pendidikan": [
                    {
                        "jenjang": level["edu"],
                        "jurusan": role["en"],
                        "institusi": "Universitas Airlangga",
                        "tahun": f"{2026 - yrs - 4}-{2026 - yrs}",
                        "ipk": round(rng.uniform(3.0, 3.9), 2),
                    }
                ],
                "sertifikasi": [f"Sertifikasi Profesional {role['en']} ({2026 - yrs})"],
            }
        )

    # --- 30 jobs: 10 peran × 3 level (1 job per kombinasi) ---
    j = 0
    for role_key, role in ROLES.items():
        for level_key in ("junior", "mid", "senior"):
            j += 1
            level = LEVELS[level_key]
            jobs.append(
                {
                    "id": f"JOB-{j:03d}",
                    "synthetic": True,
                    "role": role_key,
                    "level": level_key,
                    "title": f"{role['en']} ({level['id'].capitalize()})",
                    "perusahaan": PERUSAHAAN[j % len(PERUSAHAAN)],
                    "lokasi": KOTA[j % len(KOTA)],
                    "deskripsi": (
                        f"Kami mencari {role['en']} level {level['id']} "
                        f"dengan pengalaman ±{level['years']} tahun "
                        "untuk bergabung dengan tim produk kami."
                    ),
                    "requirements": [
                        f"Pengalaman {level['years']}+ tahun pada bidang {role['id']}",
                        f"Menguasai {', '.join(role['hard'][:3])}",
                    ],
                    "skills": [{"name": s, "required": True} for s in role["hard"][:4]]
                    + [{"name": s, "required": False} for s in role["pref"]],
                    "responsibilities": [
                        f"Melaksanakan pekerjaan {role['id']} sehari-hari",
                        "Berkolaborasi dengan tim produk dan menyampaikan hasil secara terukur",
                    ],
                }
            )

    # --- pasangan berlabel (rubrik 0-3, docs/03 §4.5) ---
    jobs_by_role: dict[str, list[dict]] = {}
    for job in jobs:
        jobs_by_role.setdefault(job["role"], []).append(job)
    pairs = []
    for cv in cvs:
        role = ROLES[cv["role"]]
        same = jobs_by_role[cv["role"]]
        adj = jobs_by_role[role["adjacent"]]
        others = [jb for jb in jobs if jb["role"] not in (cv["role"], role["adjacent"])]
        # 1× label 3 (peran sama, level sama) · 2× label 2 (peran sama, level beda)
        for jb in [x for x in same if x["level"] == cv["level"]][:1]:
            pairs.append((cv["id"], jb["id"], 3))
        for jb in [x for x in same if x["level"] != cv["level"]][:2]:
            pairs.append((cv["id"], jb["id"], 2))
        # 1× label 1 (peran berdekatan)
        if adj:
            pairs.append((cv["id"], rng.choice(adj)["id"], 1))
        # 3× label 0 (peran tak terkait)
        for jb in rng.sample(others, min(3, len(others))):
            pairs.append((cv["id"], jb["id"], 0))

    # --- tulis file ---
    for folder, items, render in (("cvs", cvs, _cv_text), ("jobs", jobs, _job_text)):
        d = OUT / folder
        d.mkdir(parents=True, exist_ok=True)
        for item in items:
            item["_text"] = render(item)
            (d / f"{item['id']}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    with (OUT / "pairs_labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["cv_id", "job_id", "label", "rubrik"])
        rubrik = {
            3: "akan masuk shortlist",
            2: "relevan, layak dipertimbangkan",
            1: "relevan lemah/sebagian",
            0: "tidak relevan",
        }
        for cv_id, job_id, label in pairs:
            w.writerow([cv_id, job_id, label, rubrik[label]])

    label_dist = {k: 0 for k in (0, 1, 2, 3)}
    for *_, lab in pairs:
        label_dist[lab] += 1
    manifest = {
        "generated_by": "scripts/generate_golden_synthetic.py",
        "seed": SEED,
        "date": "2026-11-06",
        "synthetic": True,
        "n_cvs": len(cvs),
        "n_jobs": len(jobs),
        "n_pairs": len(pairs),
        "label_distribution": {str(k): v for k, v in label_dist.items()},
        "catatan": (
            "CV sintetis berlabel (12 pertama dari komposisi docs/03 §4.4); "
            "tanpa PII; label dari konstruksi."
        ),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"eval/golden: {len(cvs)} CV, {len(jobs)} jobs, {len(pairs)} pasangan berlabel")
    print("distribusi label:", manifest["label_distribution"])


if __name__ == "__main__":
    main()
