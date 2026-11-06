"""Test M4/M5 — kalibrasi, scorer (rumus beku), explainer, gap, match_service, API.

Semua test memakai embedder PALSU deterministik (bag-of-words hash dari
tests.test_embedding) — TIDAK memuat model sungguhan. Encoder judul pengalaman
di-inject via scorer.set_title_encoder agar jalur F_experience tetap teruji.
"""

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.matching import calibration as calibration_module
from app.ai.matching import scorer
from app.ai.matching.calibration import load_calibration, map_cosine, reset_calibration_cache
from app.ai.matching.explainer import build_explanation, label_for
from app.ai.matching.gap import build_gap, load_learning_resources
from app.ai.matching.scorer import (
    compute_required_education,
    compute_years_have,
    compute_years_required,
    normalize_weights,
    score_pair,
)
from app.ai.matching.similarity import cosine
from app.core.exceptions import NotFoundError
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.models.ai import CvEmbedding, JobEmbedding, MatchResult
from app.models.cv import CV, CvExtraction
from app.models.job import Job
from app.schemas.job import JobIn
from app.services import embedding_service, extraction_service, job_service, match_service
from tests.helpers import create_job, make_candidate, make_hr_with_company
from tests.test_embedding import (
    MODEL_NAME,
    FakeTextEmbedder,
    _fake_factory,
    _seed_company,
    _seed_user,
    _svc_settings,
)
from tests.test_extraction_api import CV_LINES, get_extraction, make_multiline_pdf, upload_cv


def _vec(text: str) -> list[float]:
    """Vektor palsu deterministik (bag-of-words hash, L2-normalized)."""
    return FakeTextEmbedder(MODEL_NAME).encode([text])[0]


def _axis(index: int) -> list[float]:
    """Vektor basis ortogonal dim-384 — untuk kasus cosine 0/1 yang pasti."""
    vec = [0.0] * 384
    vec[index] = 1.0
    return vec


@pytest.fixture(autouse=True)
def _reset_matching_caches():
    """Cache kalibrasi & taksonomi bersih antar test (berkas dibaca ulang)."""
    reset_calibration_cache()
    match_service.reset_taxonomy_related_cache()
    yield
    reset_calibration_cache()
    match_service.reset_taxonomy_related_cache()


@pytest.fixture()
def fake_title_encoder():
    """Encoder judul pengalaman palsu (bag-of-words) — reset setelah test."""
    scorer.set_title_encoder(lambda texts: FakeTextEmbedder(MODEL_NAME).encode(list(texts)))
    yield
    scorer.set_title_encoder(None)


# =====================================================================
# 1. Kalibrasi
# =====================================================================


class TestCalibration:
    def test_load_calibration_reads_frozen_file(self):
        data = load_calibration()
        assert data["version"] == "v1.1"
        assert data["anchors"] == [
            {"cos": 0.4509, "score": 30},
            {"cos": 0.7327, "score": 85},
        ]

    def test_load_calibration_fallback_when_missing_or_corrupt(self, monkeypatch, tmp_path):
        monkeypatch.setattr(calibration_module, "_CALIBRATION_PATH", tmp_path / "hilang.json")
        reset_calibration_cache()
        assert load_calibration() == calibration_module.DEFAULT_CALIBRATION

        corrupt = tmp_path / "korup.json"
        corrupt.write_text('{"version": "v1", "anchors": [{"cos": "x"}]', encoding="utf-8")
        monkeypatch.setattr(calibration_module, "_CALIBRATION_PATH", corrupt)
        reset_calibration_cache()
        assert load_calibration()["anchors"] == calibration_module.DEFAULT_CALIBRATION["anchors"]

    def test_load_calibration_cached_per_process(self, monkeypatch, tmp_path):
        reset_calibration_cache()
        first = load_calibration()
        # Setelah pembacaan pertama, berkas diganti → hasil tetap dari cache.
        replacement = tmp_path / "baru.json"
        replacement.write_text(
            '{"version": "v9", "anchors": [{"cos": 0.1, "score": 10}]}', encoding="utf-8"
        )
        monkeypatch.setattr(calibration_module, "_CALIBRATION_PATH", replacement)
        assert load_calibration() == first

    def test_map_cosine_piecewise_linear_and_clamped(self):
        # Titik anchor & tengah segmen (0.4509→30, 0.7327→85; tengah 0.5918 → 57.5).
        assert map_cosine(0.4509) == pytest.approx(30.0)
        assert map_cosine(0.7327) == pytest.approx(85.0)
        assert map_cosine(0.5918) == pytest.approx(57.5)
        # Clamp di luar anchor terluar — tanpa ekstrapolasi.
        assert map_cosine(0.10) == pytest.approx(30.0)
        assert map_cosine(0.95) == pytest.approx(85.0)  # clamp atas
        assert 0.0 <= map_cosine(0.0) <= 100.0

    def test_map_cosine_custom_anchors(self):
        anchors = [
            {"cos": 0.0, "score": 0},
            {"cos": 0.5, "score": 50},
            {"cos": 1.0, "score": 100},
        ]
        assert map_cosine(0.25, anchors) == pytest.approx(25.0)
        assert map_cosine(0.75, anchors) == pytest.approx(75.0)
        assert map_cosine(1.5, anchors) == pytest.approx(100.0)
        assert map_cosine(-0.2, anchors) == pytest.approx(0.0)

    def test_map_cosine_robust_edge_cases(self):
        assert map_cosine(0.5, []) == 0.0
        assert map_cosine(float("nan")) == 0.0
        assert map_cosine(0.4, [{"cos": 0.5, "score": 70}]) == pytest.approx(70.0)
        assert map_cosine(0.6, [{"cos": 0.5, "score": 70}]) == pytest.approx(70.0)


# =====================================================================
# 2. Scorer — rumus beku
# =====================================================================


def _job(**overrides) -> dict:
    base = {
        "title": "Data Analyst",
        "description": "Menganalisa data penjualan. Pengalaman 2+ tahun.",
        "requirements": "Mahir SQL dan Python.",
        "responsibilities": None,
        "seniority": None,
        "skills": [
            {"name": "SQL", "slug": "sql", "display": "SQL", "required": True},
            {"name": "Python", "slug": "python", "display": "Python", "required": True},
            {"name": "Tableau", "slug": "tableau", "display": "Tableau", "required": False},
        ],
    }
    base.update(overrides)
    return base


def _payload(**overrides) -> dict:
    base = {
        "experiences": [
            {
                "title": "Data Analyst Junior",
                "company": "PT Cerdas",
                "period": "2025-01 - sekarang",
                "start": "2025-01",
                "end": None,
                "current": True,
                "bullets": [],
            }
        ],
        "education": [{"degree": "S1", "field": "Statistik", "institution": "Universitas A"}],
        "skills": [{"name": "SQL", "evidence": "SQL", "confidence": 1.0}],
    }
    base.update(overrides)
    return base


RELATED = {"tableau": {"power-bi", "data-visualization"}}


class TestScorePair:
    def test_semantic_factor_from_calibration(self, fake_title_encoder):
        result = score_pair(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),  # identik → cos 1.0 → clamp ke 85
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        assert result["factors"]["semantic"] == pytest.approx(85.0)

        orthogonal = score_pair(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(1),  # ortogonal → cos 0 → skor anchor bawah
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        assert orthogonal["factors"]["semantic"] == pytest.approx(30.0)

    def test_skill_exact_alias_and_preferred_missing(self, fake_title_encoder):
        result = score_pair(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql", "python"},
            explicit_slugs={"sql"},  # python lewat jalur inferred → alias
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        by_name = {item["name"]: item for item in result["matched"]}
        assert by_name["sql"]["match_type"] == "exact"
        assert by_name["sql"]["required"] is True
        assert by_name["sql"]["evidence"] == "SQL"
        assert by_name["python"]["match_type"] == "alias"
        assert by_name["python"]["evidence"] is None

        # F_skill = 100·(0.6·1.0 + 0.4·0)/0.6 = 60 (preferred Tableau kosong).
        assert result["factors"]["skill_coverage"] == pytest.approx(60.0)
        missing = {item["name"]: item for item in result["missing"]}
        assert set(missing) == {"tableau"}
        assert missing["tableau"]["severity"] == "minor"  # preferred → minor

    def test_skill_related_credit_and_severity(self, fake_title_encoder):
        job = _job(
            skills=[{"name": "Tableau", "slug": "tableau", "display": "Tableau", "required": True}]
        )
        common = dict(
            cv_payload=_payload(),
            job=job,
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        # Kandidat punya power-bi (terkait tableau) → kredit 0.5, missing menengah.
        result = score_pair(candidate_slugs={"power-bi"}, explicit_slugs={"power-bi"}, **common)
        assert result["factors"]["skill_coverage"] == pytest.approx(50.0)
        assert result["matched"] == []
        assert result["missing"][0]["severity"] == "menengah"

        # Tanpa kredit related → kritis.
        result_kritis = score_pair(candidate_slugs={"excel"}, explicit_slugs={"excel"}, **common)
        assert result_kritis["factors"]["skill_coverage"] == 0.0
        assert result_kritis["missing"][0]["severity"] == "kritis"

    def test_skill_empty_preferred_is_neutral(self, fake_title_encoder):
        job = _job(skills=[{"name": "SQL", "slug": "sql", "display": "SQL", "required": True}])
        result = score_pair(
            cv_payload=_payload(),
            job=job,
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        # Tanpa kelas preferred → F_skill = 100·Cov_req (bukan 60·Cov_req).
        assert result["factors"]["skill_coverage"] == pytest.approx(100.0)

        # Kebalikannya: hanya preferred yang ada → bobot penuh ke preferred.
        job_pref = _job(
            description="Tanpa syarat khusus pada deskripsi ini.",
            skills=[
                {"name": "Tableau", "slug": "tableau", "display": "Tableau", "required": False}
            ],
        )
        result_pref = score_pair(
            cv_payload=_payload(),
            job=job_pref,
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"tableau"},
            explicit_slugs={"tableau"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        assert result_pref["factors"]["skill_coverage"] == pytest.approx(100.0)

    def test_skill_slug_none_excluded(self, fake_title_encoder):
        job = _job(
            skills=[
                {
                    "name": "Misterius XYZ",
                    "slug": None,
                    "display": "Misterius XYZ",
                    "required": True,
                }
            ]
        )
        result = score_pair(
            cv_payload=_payload(),
            job=job,
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs=set(),
            explicit_slugs=set(),
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        assert result["matched"] == []
        assert result["missing"] == []  # tanpa identitas kanon → tidak dilaporkan
        assert result["factors"]["skill_coverage"] == 0.0

    def test_years_required_regex_seniority_and_default(self):
        assert (
            compute_years_required(
                {"description": "Pengalaman 3+ tahun.", "requirements": None, "seniority": "senior"}
            )
            == 3
        )  # regex menang atas seniority
        assert (
            compute_years_required(
                {"description": "5 tahun", "requirements": "2 years min", "seniority": None}
            )
            == 5
        )
        assert (
            compute_years_required(
                {"description": "ok", "requirements": None, "seniority": "senior"}
            )
            == 5
        )
        assert (
            compute_years_required(
                {"description": "ok", "requirements": None, "seniority": "manager"}
            )
            == 6
        )
        assert (
            compute_years_required(
                {"description": "ok", "requirements": None, "seniority": "intern"}
            )
            == 0
        )
        assert (
            compute_years_required({"description": "ok", "requirements": None, "seniority": "aneh"})
            == 3
        )
        assert (
            compute_years_required({"description": "ok", "requirements": None, "seniority": None})
            == 3
        )

    def test_years_have_spans_ongoing_and_overlap(self):
        today = datetime.now(UTC)
        ongoing_months = (today.year - 2025) * 12 + (today.month - 1)
        payload = {
            "experiences": [
                {"period": "2025-01 - sekarang"},  # berjalan → s.d. bulan berjalan
                {"period": "2023-01 - 2023-12"},  # 11 bulan
            ]
        }
        assert compute_years_have(payload) == pytest.approx((ongoing_months + 11) / 12.0)

        # Tumpang-tindih dijumlahkan apa adanya: 11 bulan + 10 bulan.
        overlap = {
            "experiences": [
                {"period": "2023-01 - 2023-12"},
                {"period": "2023-06 - 2024-04"},
            ]
        }
        assert compute_years_have(overlap) == pytest.approx((11 + 10) / 12.0)

        # Fallback field terstruktur & entri tanpa tanggal → 0.
        structured = {"experiences": [{"start": "2022-01", "end": "2022-07", "current": False}]}
        assert compute_years_have(structured) == pytest.approx(6 / 12.0)
        assert compute_years_have({"experiences": [{"title": "tanpa tanggal"}]}) == 0.0
        assert compute_years_have({}) == 0.0

    def test_experience_factor_and_top_experiences(self, fake_title_encoder):
        payload = {
            "experiences": [
                {
                    "title": "Data Analyst Junior",
                    "company": "PT A",
                    "period": "2025-01 - sekarang",
                },
                {"title": "Barista", "company": "Kafe B", "period": "2023-01 - 2023-12"},
                {"title": "Data Intern", "company": "PT C", "period": "2024-01 - 2024-06"},
                {"title": "Kasir", "company": "Toko D", "period": "2022-01 - 2022-03"},
                {"title": "Pramugara", "company": "E", "period": "2021-01 - 2021-02"},
            ]
        }
        title_vec = _vec("data analyst")
        common = dict(
            cv_payload=payload,
            job=_job(),  # years_req = 2 (regex)
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=title_vec,
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            taxonomy_related=RELATED,
        )
        result = score_pair(weights=(0.4, 0.3, 0.2, 0.1), **common)

        years_have = compute_years_have(payload)
        ratio = min(years_have, 2.0) / 2.0
        sim = max(0.0, cosine(_vec("Data Analyst Junior"), title_vec))
        expected = 100.0 * (0.6 * ratio + 0.4 * sim)
        assert result["factors"]["experience"] == pytest.approx(expected, abs=1e-3)

        tops = result["top_experiences"]
        assert len(tops) == 3  # dipangkas ke 3 teratas
        assert tops[0]["title"] == "Data Analyst Junior"
        assert tops[0]["relevance"] == pytest.approx(sim, abs=1e-4)
        relevances = [item["relevance"] for item in tops]
        assert relevances == sorted(relevances, reverse=True)
        assert set(tops[0]) == {"title", "company", "period", "relevance"}

        # Tanpa pengalaman → title_similarity 0.
        empty = score_pair(
            cv_payload={"experiences": []},
            weights=(0.4, 0.3, 0.2, 0.1),
            **{key: value for key, value in common.items() if key != "cv_payload"},
        )
        assert empty["factors"]["experience"] == 0.0
        assert empty["top_experiences"] == []

    def test_experience_cv_title_vecs_matches_fallback(self, fake_title_encoder):
        """Amandemen M4: cv_title_vecs tersuntik → hasil identik dgn fallback."""
        payload = {
            "experiences": [
                {
                    "title": "Data Analyst Junior",
                    "company": "PT A",
                    "period": "2025-01 - sekarang",
                },
                {"title": "Barista", "company": "Kafe B", "period": "2023-01 - 2023-12"},
            ]
        }
        base = dict(
            cv_payload=payload,
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        fallback = score_pair(**base)
        with_vecs = score_pair(cv_title_vecs=[_vec("Data Analyst Junior"), _vec("Barista")], **base)
        assert with_vecs["factors"] == fallback["factors"]  # identik (determinisme)
        assert with_vecs["top_experiences"] == fallback["top_experiences"]

        # Panjang tak cocok → fallback encode, hasil tetap identik (robust).
        mismatched = score_pair(cv_title_vecs=[_vec("Data Analyst Junior")], **base)
        assert mismatched["factors"] == fallback["factors"]
        assert mismatched["top_experiences"] == fallback["top_experiences"]

    def test_education_ordinal_levels(self):
        # Kandidat = S1 (2) vs job tanpa jenjang (default 2) → 90.
        assert scorer.evaluate_education(_payload(), _job()) == pytest.approx(90.0)
        assert compute_required_education({"description": "Minimal S1", "requirements": None}) == 2
        assert (
            compute_required_education({"description": "S2 diutamakan", "requirements": None}) == 3
        )
        assert (
            compute_required_education({"description": "D3/D4 diploma", "requirements": None}) == 1
        )
        assert (
            compute_required_education({"description": "bachelor degree", "requirements": None})
            == 2
        )
        assert (
            compute_required_education({"description": "tidak disebut", "requirements": None}) == 2
        )

        def _edu(degree):
            return {"education": [{"degree": degree}]}

        def _req_edu(text):
            return {"description": text}

        assert scorer.evaluate_education(_edu("S3"), _req_edu("S1")) == pytest.approx(100.0)
        assert scorer.evaluate_education(_edu("S1"), _req_edu("S1")) == pytest.approx(90.0)
        assert scorer.evaluate_education(_edu("SMA"), _req_edu("S1")) == pytest.approx(55.0)
        assert scorer.evaluate_education(_edu("SMA"), _req_edu("S2")) == pytest.approx(25.0)
        assert scorer.evaluate_education({"education": []}, _req_edu("S1")) == pytest.approx(25.0)
        # Sinonim jenjang kandidat.
        assert scorer.evaluate_education(_edu("Bachelor"), _req_edu("S1")) == pytest.approx(90.0)
        assert scorer.evaluate_education(_edu("Magister"), _req_edu("S2")) == pytest.approx(90.0)

    def test_weights_normalization_and_overall(self, fake_title_encoder):
        result = score_pair(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(2.0, 1.0, 1.0, 0.0),  # jumlah 4 → dinormalisasi (0.5, 0.25, 0.25, 0)
            taxonomy_related=RELATED,
        )
        factors = result["factors"]
        expected = (
            0.5 * factors["semantic"]
            + 0.25 * factors["skill_coverage"]
            + 0.25 * factors["experience"]
            + 0.0 * factors["education"]
        )
        assert result["overall"] == pytest.approx(expected, abs=1e-3)

        # Total bobot 0 → guard: rata 0.25 masing-masing (tidak pernah crash).
        result_zero = score_pair(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.0, 0.0, 0.0, 0.0),
            taxonomy_related=RELATED,
        )
        expected_zero = 0.25 * sum(result_zero["factors"].values())
        assert result_zero["overall"] == pytest.approx(expected_zero, abs=1e-3)

        assert normalize_weights((0.4, 0.3, 0.2, 0.1)) == pytest.approx((0.4, 0.3, 0.2, 0.1))
        assert sum(normalize_weights((2.0, 1.0, 1.0, 0.0))) == pytest.approx(1.0)
        assert sum(normalize_weights((0.0, 0.0, 0.0, 0.0))) == pytest.approx(1.0)

    def test_calibration_version_is_traceability_only(self, fake_title_encoder):
        kwargs = dict(
            cv_payload=_payload(),
            job=_job(),
            cv_vec=_axis(0),
            job_vec=_axis(0),
            job_title_vec=_vec("data analyst"),
            candidate_slugs={"sql"},
            explicit_slugs={"sql"},
            weights=(0.4, 0.3, 0.2, 0.1),
            taxonomy_related=RELATED,
        )
        assert score_pair(**kwargs, calibration_version="v1") == score_pair(
            **kwargs, calibration_version="v9"
        )


# =====================================================================
# 3. Explainer
# =====================================================================


FACTORS_SAMPLE = {
    "semantic": 72.0,
    "skill_coverage": 85.5,
    "experience": 40.0,
    "education": 90.0,
}


class TestExplainer:
    def test_label_bands(self):
        assert label_for(100.0) == "Sangat Cocok"
        assert label_for(85.0) == "Sangat Cocok"
        assert label_for(84.99) == "Cocok"
        assert label_for(70.0) == "Cocok"
        assert label_for(69.99) == "Cukup"
        assert label_for(55.0) == "Cukup"
        assert label_for(54.99) == "Kurang"
        assert label_for(0.0) == "Kurang"

    def test_deterministic_and_mentions_required_facts(self):
        kwargs = dict(
            overall=72.5,
            factors=FACTORS_SAMPLE,
            matched=[{"name": "sql", "display": "SQL", "required": True}],
            missing=[
                {"name": "python", "display": "Python", "required": True},
                {"name": "tableau", "display": "Tableau", "required": False},
            ],
            job_title="Data Analyst",
            years_have=1.8,
            years_req=2,
        )
        first, second = build_explanation(**kwargs), build_explanation(**kwargs)
        assert first == second  # deterministik — tanpa LLM
        assert "72.5" in first and "Cocok" in first
        assert 'lowongan "Data Analyst"' in first
        assert "pendidikan (90.0)" in first  # faktor terkuat
        assert "pengalaman (40.0)" in first  # faktor terlemah
        assert "1 dari 2 skill wajib terpenuhi" in first
        assert "1.8 tahun dari 2 tahun" in first  # years_have vs years_req
        sentences = [part for part in first.split(". ") if part.strip()]
        assert 2 <= len(sentences) <= 4  # narasi 2-4 kalimat

    def test_years_fulfilled_and_no_required_skills(self):
        text = build_explanation(
            overall=90.0,
            factors=FACTORS_SAMPLE,
            matched=[{"name": "sql", "display": "SQL", "required": True}],
            missing=[],
            job_title="Analis Data",
            years_have=5.0,
            years_req=3,
        )
        assert "sudah memenuhi kebutuhan 3 tahun" in text

        text_none = build_explanation(
            overall=50.0,
            factors=FACTORS_SAMPLE,
            matched=[],
            missing=[],
            job_title="Analis",
            years_have=0.0,
            years_req=0,
        )
        assert "tidak mencantumkan skill wajib" in text_none


# =====================================================================
# 4. Gap (M5)
# =====================================================================


class TestGap:
    def test_load_learning_resources_shape(self):
        resources = load_learning_resources()
        assert len(resources) >= 8  # ~8 kategori utama
        for category, items in resources.items():
            assert category and 2 <= len(items) <= 3
            for item in items:
                assert set(item) == {"title", "provider", "url"}
                assert item["url"].startswith("http")
                assert item["title"] and item["provider"]

    def test_build_gap_matrix_statuses_and_suggestions(self):
        match = {
            "missing": [
                {
                    "name": "postgresql",
                    "display": "PostgreSQL",
                    "required": True,
                    "severity": "kritis",
                },
                {"name": "tableau", "display": "Tableau", "required": False, "severity": "minor"},
            ]
        }
        taxonomy_categories = ["Data Analytics", "Database Management", "Cloud Computing"]
        candidate = {"Data Analytics": ["sql", "python"], "Cloud Computing": ["aws"]}
        job = {"Data Analytics": ["sql"], "Database Management": ["postgresql"]}

        result = build_gap(match, taxonomy_categories, candidate, job)
        assert set(result) == {"matrix", "items", "learning_suggestions"}

        rows = {row["category"]: row for row in result["matrix"]}
        assert rows["Data Analytics"] == {
            "category": "Data Analytics",
            "target": 100,
            "candidate": 100,  # 2 slug kandidat / 1 slug lowongan → min(100, 200)
            "status": "met",
        }
        assert rows["Database Management"]["candidate"] == 0
        assert rows["Database Management"]["status"] == "gap"
        assert rows["Cloud Computing"] == {
            "category": "Cloud Computing",
            "target": 0,
            "candidate": 100,
            "status": "surplus",
        }

        items = {item["name"]: item for item in result["items"]}
        assert items["postgresql"]["reason"]  # alasan turunan severity
        assert "wajib" in items["postgresql"]["reason"]
        assert items["tableau"]["severity"] == "minor"

        # Kategori gap = kategori lowongan yang memuat slug missing (postgresql).
        categories = {s["category"] for s in result["learning_suggestions"]}
        assert categories == {"Database Management"}
        for suggestion in result["learning_suggestions"]:
            assert set(suggestion) == {"category", "title", "provider", "url"}

    def test_build_gap_partial_candidate_counts(self):
        result = build_gap(
            {"missing": []},
            ["Data Analytics"],
            {"Data Analytics": ["sql"]},
            {"Data Analytics": ["sql", "python"]},
        )
        assert result["matrix"][0]["candidate"] == 50  # 1/2
        assert result["matrix"][0]["status"] == "gap"

    def test_build_gap_empty_inputs(self):
        result = build_gap({}, [], {}, {})
        assert result == {"matrix": [], "items": [], "learning_suggestions": []}


# =====================================================================
# 5. match_service (level service, embedder palsu)
# =====================================================================


PAYLOAD_M4 = {
    "contact": {
        "name": "Budi Santoso",
        "email": "budi@example.dev",
        "phone": "+62 8121-3188-4851",
        "location": "Jakarta",
        "links": [],
    },
    "summary": "Analis data dengan SQL, Python, dan pandas.",
    "experiences": [
        {
            "title": "Data Analyst Junior",
            "company": "PT Cerdas",
            "period": "2025-01 - sekarang",
            "start": "2025-01",
            "end": None,
            "current": True,
            "bullets": ["Membuat dashboard Power BI dan otomasi Excel dengan Python."],
            "evidence": "Data Analyst Junior - PT Cerdas",
            "confidence": 0.9,
        }
    ],
    "education": [
        {
            "degree": "S1",
            "field": "Statistik",
            "institution": "Universitas A",
            "years": "2021-2025",
            "gpa": 3.2,
        }
    ],
    "skills": [
        {"name": "SQL", "evidence": "SQL", "confidence": 1.0},
        {"name": "Python", "evidence": "Python", "confidence": 1.0},
    ],
    "certifications": [],
    "languages": [{"language": "Indonesia", "level": "Native"}],
    "projects": [],
    "awards": [],
}


def _seed_cv_primary(db: Session, user, *, confirmed=True, payload=PAYLOAD_M4, deleted=False) -> CV:
    cv = CV(
        candidate_user_id=user.id,
        status="ready",
        file_path="uploads/cvs/uji.pdf",
        original_filename="cv.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=uuid.uuid4().hex,
        is_primary=True,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(cv)
    db.flush()
    db.add(
        CvExtraction(
            cv_id=cv.id,
            status="done",
            parser_version="pymupdf-heuristic-v1",
            payload=payload,
            confirmed_at=datetime.now(UTC) if confirmed else None,
        )
    )
    db.commit()
    return cv


def _persist_skills(db: Session, user, cv: CV) -> None:
    """Persist skill kandidat dari payload (mirror jalur confirm_extraction)."""
    from app.services import skill_service  # noqa: PLC0415

    skill_service.persist_cv_skills(db, user, cv.id, cv.extraction)
    db.commit()


def _seed_match_job(db: Session, hr, company, *, status="active", deleted=False) -> Job:
    """Lowongan analis data: SQL+Python wajib, Tableau diutamakan, 2+ tahun."""
    job = Job(
        company_id=company.id,
        posted_by_user_id=hr.id,
        source_type="hr",
        status=status,
        title="Data Analyst Senior",
        description="Menganalisa data penjualan dan membangun dashboard. Pengalaman 2+ tahun.",
        requirements="Mahir SQL dan Python.",
        responsibilities="Laporan mingguan.",
        skills=[
            {"name": "SQL", "required": True},
            {"name": "Python", "required": True},
            {"name": "Tableau", "required": False},
        ],
        employment_type="full_time",
        work_mode="hybrid",
        seniority="junior",
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(job)
    db.commit()
    return job


class TestMatchService:
    def _setup(self, db_session, seeded_taxonomy, monkeypatch):
        monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
        user = _seed_user(db_session, "match-flow@example.dev")
        hr = _seed_user(db_session, "match-hr@example.dev", role="hr")
        company = _seed_company(db_session, hr)
        cv = _seed_cv_primary(db_session, user)
        _persist_skills(db_session, user, cv)
        job = _seed_match_job(db_session, hr, company)
        return user, hr, cv, job

    def test_compute_match_full_flow_and_persistence(
        self, db_session, seeded_taxonomy, monkeypatch, fake_title_encoder
    ):
        user, _hr, cv, job = self._setup(db_session, seeded_taxonomy, monkeypatch)
        settings = _svc_settings()

        result = match_service.compute_match(db_session, user, job.id, settings)

        assert set(result) == {
            "job_id",
            "cv_id",
            "model_version",
            "overall",
            "label",
            "factors",
            "weights",
            "matched_skills",
            "missing_skills",
            "top_experiences",
            "explanation",
            "computed_at",
            "gap",
        }
        assert result["model_version"] == "m4v1|emb:fake-model-untuk-tes|w:40-30-20-10|cal:v1.1"
        assert result["job_id"] == job.id and result["cv_id"] == cv.id
        assert result["weights"] == {
            "semantic": 0.4,
            "skill_coverage": 0.3,
            "experience": 0.2,
            "education": 0.1,
        }
        assert result["label"] == label_for(result["overall"])
        # SQL & Python eksplisit di payload → matched exact.
        matched_names = {item["name"] for item in result["matched_skills"]}
        assert {"sql", "python"} <= matched_names
        assert all(item["match_type"] in ("exact", "alias") for item in result["matched_skills"])
        assert any(
            item["name"] == "tableau" and item["severity"] == "minor"
            for item in result["missing_skills"]
        )
        assert 0.0 <= result["overall"] <= 100.0
        assert set(result["gap"]) == {"matrix", "items", "learning_suggestions"}

        # Persist: satu baris match_results + vektor dibuat on the fly.
        rows = db_session.scalars(select(MatchResult)).all()
        assert len(rows) == 1
        assert rows[0].cv_id == cv.id and rows[0].job_id == job.id
        assert rows[0].model_version == result["model_version"]
        assert rows[0].explanation == result["explanation"]
        assert len(db_session.scalars(select(CvEmbedding)).all()) == 1
        assert len(db_session.scalars(select(JobEmbedding)).all()) == 1

        # Recompute → replace (tetap satu baris, model_version sama).
        match_service.compute_match(db_session, user, job.id, settings)
        assert len(db_session.scalars(select(MatchResult)).all()) == 1

    def test_title_vectors_encoded_once_per_compute_match(
        self, db_session, seeded_taxonomy, monkeypatch, fake_title_encoder
    ):
        """Amandemen M4: judul di-encode SEKALI per compute_match (satu batch)."""
        user, _hr, _cv, job = self._setup(db_session, seeded_taxonomy, monkeypatch)
        settings = _svc_settings()
        match_service.compute_match(db_session, user, job.id, settings)  # warm: vektor tersimpan

        counting: dict = {"calls": []}
        inner = FakeTextEmbedder(MODEL_NAME)

        class _CountingEmbedder:
            def encode(self, texts):
                counting["calls"].append(list(texts))
                return inner.encode(texts)

        monkeypatch.setattr(embedding_service, "get_embedder", lambda _model: _CountingEmbedder())
        result = match_service.compute_match(db_session, user, job.id, settings)

        # Satu-satunya panggilan encode = batch judul (judul lowongan + judul CV).
        assert len(counting["calls"]) == 1
        batch = counting["calls"][0]
        assert batch[0] == job.title
        expected_titles = [
            str(exp.get("title") or "") for exp in PAYLOAD_M4.get("experiences") or []
        ]
        assert batch[1:] == expected_titles
        assert result["factors"]["experience"] > 0  # skor tetap terhitung dari vecs cache

    def test_compute_match_overall_consistent_with_factors(
        self, db_session, seeded_taxonomy, monkeypatch, fake_title_encoder
    ):
        user, _hr, _cv, job = self._setup(db_session, seeded_taxonomy, monkeypatch)
        result = match_service.compute_match(db_session, user, job.id, _svc_settings())
        weights = normalize_weights(tuple(_svc_settings().match_weights))
        expected = sum(
            weight * result["factors"][key]
            for weight, key in zip(
                weights, ("semantic", "skill_coverage", "experience", "education"), strict=True
            )
        )
        assert result["overall"] == pytest.approx(expected, abs=1e-3)

    def test_match_unavailable_without_or_unconfirmed_cv(
        self, db_session, seeded_taxonomy, monkeypatch
    ):
        monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
        user = _seed_user(db_session, "match-none@example.dev")
        hr = _seed_user(db_session, "match-hr2@example.dev", role="hr")
        company = _seed_company(db_session, hr)
        job = _seed_match_job(db_session, hr, company)
        settings = _svc_settings()

        with pytest.raises(match_service.MatchUnavailableError) as exc_no_cv:
            match_service.compute_match(db_session, user, job.id, settings)
        assert exc_no_cv.value.code == "MATCH_UNAVAILABLE"

        # CV ada tapi ekstraksi belum dikonfirmasi → kode sama.
        _seed_cv_primary(db_session, user, confirmed=False)
        with pytest.raises(match_service.MatchUnavailableError) as exc_unconf:
            match_service.compute_match(db_session, user, job.id, settings)
        assert exc_unconf.value.code == "MATCH_UNAVAILABLE"

    def test_404_for_non_active_or_deleted_job(self, db_session, seeded_taxonomy, monkeypatch):
        monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
        user = _seed_user(db_session, "match-404@example.dev")
        hr = _seed_user(db_session, "match-hr3@example.dev", role="hr")
        company = _seed_company(db_session, hr)

        # Cek job lebih dulu daripada CV → semua status non-aktif → 404.
        for status in ("draft", "paused", "closed"):
            job = _seed_match_job(db_session, hr, company, status=status)
            with pytest.raises(NotFoundError):
                match_service.compute_match(db_session, user, job.id, _svc_settings())

        job_deleted = _seed_match_job(db_session, hr, company, status="active", deleted=True)
        with pytest.raises(NotFoundError):
            match_service.compute_match(db_session, user, job_deleted.id, _svc_settings())

    def test_invalidation_hooks_confirm_and_update(
        self, db_session, seeded_taxonomy, monkeypatch, fake_title_encoder
    ):
        user, hr, cv, job = self._setup(db_session, seeded_taxonomy, monkeypatch)
        settings = _svc_settings()
        match_service.compute_match(db_session, user, job.id, settings)
        assert len(db_session.scalars(select(MatchResult)).all()) == 1

        # Hook confirm_extraction (konfirmasi ulang) → baris match milik CV hilang.
        extraction_service.confirm_extraction(db_session, user, cv.id)
        assert db_session.scalars(select(MatchResult)).all() == []

        match_service.compute_match(db_session, user, job.id, settings)
        assert len(db_session.scalars(select(MatchResult)).all()) == 1

        # Hook update_job → baris match lowongan hilang.
        job_in = JobIn(
            title="Data Analyst Senior",
            description="Memimpin analisa data dan dashboard eksekutif perusahaan.",
            skills=[{"name": "SQL", "required": True}],
            employment_type="full_time",
            work_mode="onsite",
        )
        job_service.update_job(db_session, hr, job.id, job_in, settings=settings)
        assert db_session.scalars(select(MatchResult)).all() == []


# =====================================================================
# 6. API — /jobs/{id}/compatibility & /jobs/{id}/gap
# =====================================================================


def _make_match_client(db_engine, monkeypatch) -> TestClient:
    """Client ala conftest.client, tapi embedding aktif + embedder palsu."""
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    settings = _svc_settings(uploads_dir=f"test_uploads_match_{uuid.uuid4().hex[:8]}")
    app = create_app(settings)
    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    return TestClient(app)


@contextmanager
def _prepared_client(db_engine, seeded_taxonomy, monkeypatch):
    """Kandidat dgn CV terkonfirmasi + lowongan analis data aktif (terpublish)."""
    with _make_match_client(db_engine, monkeypatch) as client:
        _reg, cand_headers = make_candidate(client)
        _hr_reg, hr_headers, _company = make_hr_with_company(client)

        cv = upload_cv(client, cand_headers, make_multiline_pdf(CV_LINES))
        get_extraction(client, cand_headers, cv["id"])
        resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=cand_headers)
        assert resp.status_code == 200, resp.text

        job = create_job(
            client,
            hr_headers,
            title="Data Analyst Senior",
            description="Menganalisa data penjualan bersama tim produk.",
            requirements="Pengalaman 2+ tahun. Mahir SQL dan Python.",
            skills=[
                {"name": "SQL", "required": True},
                {"name": "Python", "required": True},
                {"name": "Tableau", "required": False},
            ],
        )
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
        assert resp.status_code == 200, resp.text
        yield client, cand_headers, hr_headers, job


class TestMatchAPI:
    def test_compatibility_and_gap_200(self, db_engine, seeded_taxonomy, monkeypatch):
        with _prepared_client(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            cand_headers,
            _hr_headers,
            job,
        ):
            resp = client.get(f"/api/v1/jobs/{job['id']}/compatibility", headers=cand_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body) == {
                "job_id",
                "cv_id",
                "model_version",
                "overall",
                "label",
                "factors",
                "weights",
                "matched_skills",
                "missing_skills",
                "top_experiences",
                "explanation",
                "computed_at",
            }
            assert body["model_version"].startswith(
                "m4v1|emb:fake-model-untuk-tes|w:40-30-20-10|cal:v1.1"
            )
            assert body["job_id"] == job["id"]
            assert body["label"] in ("Sangat Cocok", "Cocok", "Cukup", "Kurang")
            assert set(body["factors"]) == {
                "semantic",
                "skill_coverage",
                "experience",
                "education",
            }
            assert body["explanation"]  # narasi non-kosong

            # /gap reuse compute_match — kontrak lengkap.
            resp_gap = client.get(f"/api/v1/jobs/{job['id']}/gap", headers=cand_headers)
            assert resp_gap.status_code == 200, resp_gap.text
            gap_body = resp_gap.json()
            assert set(gap_body) == {
                "job_id",
                "model_version",
                "overall",
                "matrix",
                "items",
                "learning_suggestions",
                "explanation",
            }
            assert gap_body["matrix"], "skill lowongan pasti menghasilkan >=1 baris matriks"
            for row in gap_body["matrix"]:
                assert set(row) == {"category", "target", "candidate", "status"}
                assert row["status"] in ("met", "gap", "surplus")
            for item in gap_body["items"]:
                assert set(item) == {"name", "display", "required", "severity", "reason"}

    def test_404_draft_job_400_unavailable_and_rbac(self, db_engine, seeded_taxonomy, monkeypatch):
        with _make_match_client(db_engine, monkeypatch) as client:
            _reg, cand_headers = make_candidate(client)
            _hr_reg, hr_headers, _company = make_hr_with_company(client)
            job = create_job(client, hr_headers)  # draft → tidak terlihat kandidat

            resp = client.get(f"/api/v1/jobs/{job['id']}/compatibility", headers=cand_headers)
            assert resp.status_code == 404
            assert resp.json()["error"]["code"] == "NOT_FOUND"

            resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
            assert resp.status_code == 200

            # Lowongan aktif, tapi kandidat belum punya CV → MATCH_UNAVAILABLE.
            resp = client.get(f"/api/v1/jobs/{job['id']}/compatibility", headers=cand_headers)
            assert resp.status_code == 400
            assert resp.json()["error"]["code"] == "MATCH_UNAVAILABLE"

            resp = client.get(f"/api/v1/jobs/{job['id']}/gap", headers=cand_headers)
            assert resp.status_code == 400
            assert resp.json()["error"]["code"] == "MATCH_UNAVAILABLE"

            # RBAC: HR bukan kandidat → 403; tanpa token → 401.
            resp = client.get(f"/api/v1/jobs/{job['id']}/compatibility", headers=hr_headers)
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "FORBIDDEN"
            resp = client.get(f"/api/v1/jobs/{job['id']}/gap", headers=hr_headers)
            assert resp.status_code == 403
            resp = client.get(f"/api/v1/jobs/{job['id']}/compatibility")
            assert resp.status_code == 401
