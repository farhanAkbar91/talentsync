"""Test M8 — optimasi CV by LLM (Groq): klien LLM (MockTransport, tanpa jaringan),
prompt grounding, validator R1-R4, perender PDF, service generasi/penerapan, dan
API (cache kuota, failed, RBAC, apply → CV versi baru + PDF + auto-confirm).

Semua panggilan Groq memakai httpx.MockTransport lewat patch
optimization_service.build_client — TIDAK ADA panggilan jaringan nyata.
Kunci API palsu ("test-groq-key-fake") tidak pernah boleh muncul di pesan error.
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.ai.optimization.grounding_validator import ensure_suggestion_ids, validate_edits
from app.ai.optimization.llm_client import GroqClient, LLMError, build_client
from app.ai.optimization.pdf_renderer import render_cv_pdf
from app.ai.optimization.prompts import PROMPT_VERSION, build_messages
from app.core.config import Settings
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.models.ai import CvOptimization
from app.models.cv import CV
from app.models.job import Job
from app.models.user import User
from app.services import optimization_service
from tests.helpers import create_job, make_candidate, make_hr_with_company
from tests.test_extraction_api import CV_LINES, get_extraction, make_multiline_pdf, upload_cv

FAKE_KEY = "test-groq-key-fake"
PRIMARY_MODEL = "test-model-utama"
FALLBACK_MODEL = "test-model-cadangan"


def _opt_settings(**overrides) -> Settings:
    """Settings test ala conftest._make_settings + kunci/model Groq palsu
    (dibangun di sini — conftest tidak boleh diedit)."""
    base = dict(
        app_env="test",
        log_level="WARNING",
        cors_origins=["http://test"],
        secret_key="test-secret-key-not-for-production-0123456789abcdef",
        uploads_dir=f"test_uploads_opt_{uuid.uuid4().hex[:8]}",
        embeddings_enabled=False,
        groq_api_key=FAKE_KEY,
        groq_model=PRIMARY_MODEL,
        groq_model_fallback=FALLBACK_MODEL,
    )
    base.update(overrides)
    return Settings(**base)


def _opt_client(
    db_engine, monkeypatch, *, patch_llm: bool = True, **overrides
) -> tuple[TestClient, list, dict, Settings, sessionmaker]:
    """App test + transport Groq palsu. Mengembalikan (client, calls, holder,
    settings, factory). Handler aktif diatur test lewat holder["handler"] = fn."""
    calls: list[httpx.Request] = []
    holder: dict[str, Callable[[httpx.Request], httpx.Response]] = {}

    def recording_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return holder["handler"](request)

    transport = httpx.MockTransport(recording_handler)

    def factory(settings: Settings) -> GroqClient | None:
        if not settings.groq_api_key:
            return None
        return GroqClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            fallback_model=settings.groq_model_fallback,
            transport=transport,
        )

    settings = _opt_settings(**overrides)
    app = create_app(settings)
    factory_db: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        db = factory_db()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory_db
    if patch_llm:
        monkeypatch.setattr(optimization_service, "build_client", factory)
    return TestClient(app), calls, holder, settings, factory_db


def _confirmed_cv_and_job(client: TestClient) -> tuple[dict, dict, dict, dict, dict]:
    """Kandidat + CV terkonfirmasi + lowongan aktif (terpublish)."""
    reg, cand_headers = make_candidate(client)
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
    return cand_headers, hr_headers, cv, job, reg


# --- Handler transport palsu ---


def _llm_ok(edits: list[dict]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        assert body["response_format"]["type"] == "json_schema"
        assert body["temperature"] == 0.2
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"edits": edits})}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    return handler


def _llm_server_error(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": {"message": "internal"}})


def _edits_from_payload(payload: dict) -> list[dict]:
    """Edit valid yang merujuk bullet NYATA dari payload heuristik CV_LINES."""
    bullet = payload["experiences"][0]["bullets"][0]
    base = bullet.rstrip(".")
    return [
        {
            "suggestion_id": "edit-1",
            "source_ref": bullet,
            "section": "pengalaman",
            "original_text": bullet,
            "suggested_text": base + " dengan gaya kerja yang lebih terstruktur.",
            "rationale": "Menegaskan gaya kerja terstruktur.",
            "change_type": "emphasize",
        }
    ]


# --- Payload CV-001-like untuk test unit validator/prompt/renderer ---

BULLET_1 = "Menangani pekerjaan analis data menggunakan SQL dan Python."
BULLET_2 = "Berkolaborasi dengan tim lintas fungsi untuk menghasilkan laporan mingguan."

CV_PAYLOAD: dict = {
    "contact": {
        "name": "Budi Santoso",
        "email": "budi.santoso@example.dev",
        "phone": "+62 8121-3188-4851",
        "location": "Jakarta",
        "links": [],
    },
    "summary": (
        "Data Analyst dengan 1 tahun pengalaman pada bidang analis data, terbiasa "
        "bekerja dengan SQL/Python/pandas dan berkolaborasi dalam tim produk."
    ),
    "experiences": [
        {
            "title": "Data Analyst Junior",
            "company": "PT Teknologi Cerdas",
            "period": "2025-01 - sekarang",
            "current": True,
            "bullets": [BULLET_1, BULLET_2],
        }
    ],
    "education": [
        {
            "degree": "S1",
            "field": "Data Analyst",
            "institution": "Universitas Airlangga",
            "years": "2021-2025",
            "gpa": 3.01,
        }
    ],
    "skills": [
        {"name": "SQL"},
        {"name": "Python"},
        {"name": "pandas"},
        {"name": "Excel"},
        {"name": "Power BI"},
    ],
    "certifications": [
        {"name": "Sertifikasi Profesional Data Analyst", "issuer": "BNSP", "year": 2025}
    ],
    "languages": [
        {"language": "Indonesia", "level": "Native"},
        {"language": "English", "level": "Pasif"},
    ],
}


# =====================================================================
# 1. Klien LLM Groq (httpx.MockTransport — tanpa jaringan)
# =====================================================================


def _unit_client(handler, sleeps: list[float] | None = None) -> tuple[GroqClient, list]:
    requests: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    kwargs: dict = {}
    if sleeps is not None:
        kwargs["sleep_fn"] = sleeps.append
    client = GroqClient(
        api_key=FAKE_KEY,
        model=PRIMARY_MODEL,
        fallback_model=FALLBACK_MODEL,
        transport=httpx.MockTransport(recording),
        **kwargs,
    )
    return client, requests


class TestGroqClient:
    def test_generate_success_strict_json_schema(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            assert body["model"] == PRIMARY_MODEL
            assert body["response_format"]["type"] == "json_schema"
            assert body["response_format"]["json_schema"]["strict"] is True
            assert body["temperature"] == 0.2
            assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps({"edits": []})}}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
                },
            )

        client, requests = _unit_client(handler)
        result = client.generate_optimizations("system", "user")
        assert result == {"edits": []}
        assert client.last_model == PRIMARY_MODEL
        assert client.last_usage["total_tokens"] == 42
        assert client.last_meta == {
            "model": PRIMARY_MODEL,
            "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
        }
        assert len(requests) == 1

    def test_400_on_schema_retries_with_json_object(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            if body["response_format"]["type"] == "json_schema":
                return httpx.Response(400, json={"error": {"message": "schema rejected"}})
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps({"edits": [1]})}}]}
            )

        client, requests = _unit_client(handler)
        result = client.generate_optimizations("system", "user")
        assert result == {"edits": [1]}
        assert client.last_model == PRIMARY_MODEL
        assert len(requests) == 2
        assert json.loads(requests[1].read())["response_format"] == {"type": "json_object"}

    def test_429_retries_once_then_falls_back_to_fallback_model(self):
        sleeps: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read())
            if body["model"] == PRIMARY_MODEL:
                return httpx.Response(429, headers={"Retry-After": "3"})
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps({"edits": []})}}]}
            )

        client, requests = _unit_client(handler, sleeps)
        result = client.generate_optimizations("system", "user")
        assert result == {"edits": []}
        assert client.last_model == FALLBACK_MODEL
        # utama → retry utama (setelah tunggu 3s) → cadangan sukses.
        assert len(requests) == 3
        assert sleeps == [3.0]

    def test_retry_after_is_capped_at_10_seconds(self):
        sleeps: list[float] = []
        client, requests = _unit_client(_llm_server_error, sleeps)
        with pytest.raises(LLMError):
            client.generate_optimizations("system", "user")
        # 500 tanpa header Retry-After → tanpa tunggu; 4 panggilan (2 model x 2).
        assert sleeps == []
        assert len(requests) == 4

        # Header Retry-After "120" dibatasi 10 detik, untuk kedua model.
        sleeps_capped: list[float] = []
        client2 = GroqClient(
            api_key=FAKE_KEY,
            model=PRIMARY_MODEL,
            fallback_model=FALLBACK_MODEL,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(429, headers={"Retry-After": "120"})
            ),
            sleep_fn=sleeps_capped.append,
        )
        with pytest.raises(LLMError):
            client2.generate_optimizations("system", "user")
        assert sleeps_capped == [10.0, 10.0]

    def test_both_models_fail_raises_llm_error_without_leaking_key(self):
        client, requests = _unit_client(_llm_server_error)
        with pytest.raises(LLMError) as excinfo:
            client.generate_optimizations("system", "user")
        assert "coba lagi" in excinfo.value.message
        assert FAKE_KEY not in excinfo.value.message
        assert excinfo.value.status_code == 503
        assert excinfo.value.code == "LLM_UNAVAILABLE"
        assert len(requests) == 4

    def test_invalid_json_content_raises_llm_error(self):
        client, _requests = _unit_client(_llm_server_error)
        with pytest.raises(LLMError) as excinfo:
            client._parse("bukan json sama sekali", PRIMARY_MODEL)
        assert "JSON" in excinfo.value.message
        assert client.last_model is None  # model tak tercatat bila parse gagal

        # Konten JSON valid tapi bukan objek → error terpisah.
        with pytest.raises(LLMError):
            client._parse(json.dumps(["bukan", "objek"]), PRIMARY_MODEL)

    def test_connection_error_maps_to_llm_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("koneksi gagal")

        client, _requests = _unit_client(handler)
        with pytest.raises(LLMError) as excinfo:
            client._post({"model": PRIMARY_MODEL})
        assert "dihubungi" in excinfo.value.message
        assert FAKE_KEY not in excinfo.value.message

    def test_build_client_and_from_settings_feature_gate(self):
        client = build_client(_opt_settings())
        assert isinstance(client, GroqClient)
        client.close()
        disabled = _opt_settings(groq_api_key="")
        assert build_client(disabled) is None
        assert GroqClient.from_settings(disabled) is None
        assert isinstance(GroqClient.from_settings(_opt_settings()), GroqClient)


# =====================================================================
# 2. Prompt
# =====================================================================


class TestPrompts:
    def test_prompt_version_frozen(self):
        assert PROMPT_VERSION == "v1"

    def test_system_embeds_grounding_rules_and_json_schema(self):
        system, _user = build_messages(CV_PAYLOAD, {"title": "Data Analyst Senior"}, None)
        assert "DILARANG" in system
        assert "reword, reorder, emphasize, quantify" in system
        assert "Maksimal 8 edit" in system
        # Skema JSON eksplisit di system.
        assert '"suggestion_id"' in system
        assert '"change_type"' in system
        assert '"source_ref"' in system

    def test_user_carries_cv_text_job_and_optional_gap(self):
        job = {
            "title": "Data Analyst Senior",
            "skills": [{"name": "SQL", "required": True}, {"name": "Tableau"}],
            "description": "Menganalisa data penjualan.",
            "requirements": "Mahir SQL.",
            "responsibilities": None,
        }
        _system, user = build_messages(CV_PAYLOAD, job, None)
        assert "NAMA: Budi Santoso" in user
        assert BULLET_1 in user
        assert "POSISI" in user and "Data Analyst Senior" in user
        assert "GAP SKILL" not in user  # gap None → blok gap absen

        _system, user_gap = build_messages(CV_PAYLOAD, job, {"items": [{"display": "Tableau"}]})
        assert "GAP SKILL" in user_gap
        assert "Tableau" in user_gap


# =====================================================================
# 3. Validator grounding (R1-R4)
# =====================================================================


def _edit(**overrides) -> dict:
    base = {
        "suggestion_id": "edit-1",
        "source_ref": BULLET_1,
        "section": "pengalaman",
        "original_text": BULLET_1,
        "suggested_text": BULLET_1 + " secara lebih terstruktur.",
        "rationale": "Penekanan gaya kerja.",
        "change_type": "reword",
    }
    base.update(overrides)
    return base


class TestGroundingValidator:
    def test_r1_source_not_found(self):
        report = validate_edits(
            [_edit(source_ref="Kalimat yang sama sekali tidak ada di CV.")],
            CV_PAYLOAD,
            "Data Analyst Senior",
        )
        assert report["passed"] is False
        assert report["checked"] == 1
        rules = [v["rule"] for v in report["violations"]]
        assert rules == ["source_not_found"]
        assert report["violations"][0]["suggestion_id"] == "edit-1"

    def test_r2_change_type_invalid(self):
        report = validate_edits([_edit(change_type="parafrase")], CV_PAYLOAD, "Data Analyst Senior")
        assert [v["rule"] for v in report["violations"]] == ["change_type_invalid"]

    def test_r3_fabricated_entity_phrase_and_single_token(self):
        # Frasa kapital multi-kata yang tidak ada di CV/judul.
        phrase_edit = _edit(suggested_text="Memimpin transformasi data di PT Maju Jaya Sentosa.")
        report = validate_edits([phrase_edit], CV_PAYLOAD, "Data Analyst Senior")
        assert [v["rule"] for v in report["violations"]] == ["fabricated_entity"]
        assert "PT Maju Jaya Sentosa" in report["violations"][0]["detail"]

        # Kata kapital tunggal di tengah kalimat (bukan skill CV / judul lowongan).
        single_edit = _edit(
            suggested_text="Terbiasa menyusun dashboard interaktif menggunakan Tableau."
        )
        report = validate_edits([single_edit], CV_PAYLOAD, "Data Analyst Senior")
        assert [v["rule"] for v in report["violations"]] == ["fabricated_entity"]

        # Kata dari judul lowongan diizinkan.
        title_edit = _edit(
            suggested_text="Siap berkembang sebagai Data Analyst Senior yang terstruktur."
        )
        report = validate_edits([title_edit], CV_PAYLOAD, "Data Analyst Senior")
        assert report["passed"] is True

    def test_r3_fabricated_number_on_quantify(self):
        suggested = "Berkolaborasi dengan tim lintas fungsi untuk menghasilkan 25 laporan mingguan."
        quantify_edit = _edit(
            change_type="quantify",
            original_text=BULLET_2,
            source_ref=BULLET_2,
            suggested_text=suggested,
        )
        report = validate_edits([quantify_edit], CV_PAYLOAD, "Data Analyst Senior")
        assert [v["rule"] for v in report["violations"]] == ["fabricated_number"]
        assert "25" in report["violations"][0]["detail"]

    def test_r4_date_modified(self):
        dated_edit = _edit(
            suggested_text="Sejak 2019, menangani pekerjaan analis data menggunakan SQL dan Python."
        )
        report = validate_edits([dated_edit], CV_PAYLOAD, "Data Analyst Senior")
        rules = {v["rule"] for v in report["violations"]}
        assert "date_modified" in rules
        # Angka baru juga tertangkap R3 (aturan beku: tanpa angka baru).
        assert "fabricated_number" in rules

    def test_valid_edits_pass(self):
        edits = [
            _edit(suggestion_id="edit-1"),
            _edit(
                suggestion_id="edit-2",
                source_ref=BULLET_2,
                original_text=BULLET_2,
                suggested_text=BULLET_2 + " yang terukur.",
                change_type="emphasize",
            ),
        ]
        report = validate_edits(edits, CV_PAYLOAD, "Data Analyst Senior")
        assert report == {"passed": True, "violations": [], "checked": 2}

    def test_empty_edits_pass(self):
        assert validate_edits([], CV_PAYLOAD, "Data Analyst Senior") == {
            "passed": True,
            "violations": [],
            "checked": 0,
        }

    def test_ensure_suggestion_ids_assigns_and_dedupes(self):
        edits = [
            {"original_text": "a"},
            {"suggestion_id": "edit-1", "original_text": "b"},
            {"suggestion_id": "edit-1", "original_text": "c"},
            {"original_text": "d"},
        ]
        normalized = ensure_suggestion_ids(edits)
        assert [edit["suggestion_id"] for edit in normalized] == [
            "edit-0",
            "edit-1",
            "edit-2",
            "edit-3",
        ]


# =====================================================================
# 4. Perender PDF
# =====================================================================


class TestPdfRenderer:
    def test_render_cv_pdf_produces_pdf_bytes(self):
        data = render_cv_pdf(CV_PAYLOAD)
        assert data.startswith(b"%PDF")
        assert len(data) > 500

    def test_render_cv_pdf_total_on_empty_payload(self):
        data = render_cv_pdf({})
        assert data.startswith(b"%PDF")


# =====================================================================
# 5. API + service: generasi
# =====================================================================


class TestGenerationAPI:
    def test_generation_success_completes_row(self, db_engine, monkeypatch):
        client, calls, holder, settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        holder["handler"] = _llm_ok(_edits_from_payload(payload))

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        )
        assert resp.status_code == 201, resp.text
        start = resp.json()
        assert start["status"] == "generating"
        assert start["cached"] is False
        assert start["model_version"] is None

        detail = client.get(
            f"/api/v1/cvs/{cv['id']}/optimizations/{start['id']}", headers=cand_headers
        ).json()
        assert detail["status"] == "completed"
        assert detail["llm_provider"] == "groq"
        assert detail["llm_model"] == PRIMARY_MODEL
        assert detail["prompt_version"] == PROMPT_VERSION
        assert detail["suggestions"][0]["suggestion_id"] == "edit-1"
        assert detail["grounding_report"]["passed"] is True
        assert detail["grounding_report"]["checked"] == 1
        assert detail["grounding_report"]["meta"]["usage"]["total_tokens"] == 15
        assert detail["error_message"] is None

    def test_cached_generation_returns_same_row_without_llm_call(self, db_engine, monkeypatch):
        client, calls, holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        holder["handler"] = _llm_ok(_edits_from_payload(payload))

        first = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        ).json()
        assert first["cached"] is False
        calls_after_first = len(calls)
        assert calls_after_first >= 1

        second = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        ).json()
        assert second["cached"] is True
        assert second["id"] == first["id"]
        assert second["status"] == "completed"
        assert second["model_version"] == PRIMARY_MODEL
        assert len(calls) == calls_after_first  # cache kuota: nol panggilan LLM

    def test_regenerate_creates_new_generation(self, db_engine, monkeypatch):
        client, calls, holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        holder["handler"] = _llm_ok(_edits_from_payload(payload))

        first = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        ).json()
        calls_after_first = len(calls)

        again = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"], "regenerate": True},
            headers=cand_headers,
        ).json()
        assert again["cached"] is False
        assert again["id"] != first["id"]
        detail = client.get(
            f"/api/v1/cvs/{cv['id']}/optimizations/{again['id']}", headers=cand_headers
        ).json()
        assert detail["status"] == "completed"
        assert len(calls) == calls_after_first + 1

    def test_llm_failure_marks_row_failed_with_safe_message(self, db_engine, monkeypatch):
        client, calls, holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        holder["handler"] = _llm_server_error

        start = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        ).json()
        assert start["status"] == "generating"

        detail = client.get(
            f"/api/v1/cvs/{cv['id']}/optimizations/{start['id']}", headers=cand_headers
        ).json()
        assert detail["status"] == "failed"
        assert detail["error_message"]
        assert detail["suggestions"] is None
        assert FAKE_KEY not in detail["error_message"]
        # Tangga gagal: utama → retry utama → cadangan → retry cadangan = 4 panggilan.
        assert len(calls) == 4

    def test_start_requires_confirmed_extraction(self, db_engine, monkeypatch):
        client, calls, _holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        _reg, cand_headers = make_candidate(client)
        _hr_reg, hr_headers, _company = make_hr_with_company(client)
        cv = upload_cv(client, cand_headers, make_multiline_pdf(CV_LINES))
        job = create_job(client, hr_headers)
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
        assert resp.status_code == 200

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "MATCH_UNAVAILABLE"
        assert calls == []

    def test_start_job_must_be_active(self, db_engine, monkeypatch):
        client, _calls, _holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, hr_headers, cv, job, _reg = _confirmed_cv_and_job(client)
        # Lowongan draft kedua (belum terpublish → bukan katalog aktif kandidat).
        draft = create_job(client, hr_headers, title="Data Analyst Intern")
        assert draft["id"] != job["id"]
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": draft["id"]},
            headers=cand_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_start_feature_disabled_clear_error(self, db_engine, monkeypatch):
        client, calls, _holder, _settings, _factory = _opt_client(
            db_engine, monkeypatch, patch_llm=False, groq_api_key=""
        )
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        )
        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["code"] == "LLM_UNAVAILABLE"
        assert "optimasi" in error["message"].lower()
        assert calls == []

    def test_optimization_rbac_and_ownership(self, db_engine, monkeypatch):
        client, calls, _holder, _settings, _factory = _opt_client(
            db_engine, monkeypatch, patch_llm=False, groq_api_key=""
        )
        cand_headers, hr_headers, cv, job, _reg = _confirmed_cv_and_job(client)
        _, headers_other = make_candidate(client)

        # Anonim → 401.
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/optimizations", json={"job_id": job["id"]}
            ).status_code
            == 401
        )
        # HR bukan kandidat → 403.
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/optimizations",
                json={"job_id": job["id"]},
                headers=hr_headers,
            ).status_code
            == 403
        )
        # Kandidat lain → 404 (jangan bocorkan keberadaan resource).
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/optimizations",
                json={"job_id": job["id"]},
                headers=headers_other,
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/v1/cvs/{cv['id']}/optimizations", headers=headers_other).status_code
            == 404
        )
        # Pemilik: detail/apply dengan id acak → 404.
        random_id = uuid.uuid4()
        assert (
            client.get(
                f"/api/v1/cvs/{cv['id']}/optimizations/{random_id}", headers=cand_headers
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/optimizations/{random_id}/apply",
                json={"decisions": {}},
                headers=cand_headers,
            ).status_code
            == 404
        )
        # Pemilik → lolos prasyarat, fitur nonaktif → 503 jelas (tanpa panggilan).
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        )
        assert resp.status_code == 503
        assert calls == []

    def test_list_optimizations_newest_first(self, db_engine, monkeypatch):
        client, _calls, _holder, _settings, factory = _opt_client(
            db_engine, monkeypatch, groq_api_key=""
        )
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        with factory() as db:
            older = CvOptimization(
                cv_id=db.get(CV, uuid.UUID(cv["id"])).id,
                job_id=db.get(Job, uuid.UUID(job["id"])).id,
                status="failed",
                error_message="lama",
            )
            newer = CvOptimization(
                cv_id=db.get(CV, uuid.UUID(cv["id"])).id,
                job_id=db.get(Job, uuid.UUID(job["id"])).id,
                status="completed",
            )
            db.add_all([older, newer])
            db.commit()
            # Presisi created_at SQLite per detik → paksa urutan eksplisit.
            older.created_at = datetime.now(UTC) - timedelta(seconds=30)
            newer.created_at = datetime.now(UTC)
            db.commit()
            older_id, newer_id = str(older.id), str(newer.id)

        resp = client.get(f"/api/v1/cvs/{cv['id']}/optimizations", headers=cand_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert [item["id"] for item in body["items"]] == [newer_id, older_id]


# =====================================================================
# 6. API + service: penerapan (apply)
# =====================================================================


class TestApplyAPI:
    def _generate(self, client, calls, holder, cand_headers, cv, job) -> str:
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        holder["handler"] = _llm_ok(_edits_from_payload(payload))
        start = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations",
            json={"job_id": job["id"]},
            headers=cand_headers,
        ).json()
        detail = client.get(
            f"/api/v1/cvs/{cv['id']}/optimizations/{start['id']}", headers=cand_headers
        ).json()
        assert detail["status"] == "completed"
        return start["id"]

    def test_apply_creates_new_version_with_pdf_and_auto_confirm(self, db_engine, monkeypatch):
        client, _calls, holder, _settings, factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, reg = _confirmed_cv_and_job(client)
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        edits = _edits_from_payload(payload)
        opt_id = self._generate(client, _calls, holder, cand_headers, cv, job)

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}/apply",
            json={"decisions": {"edit-1": True}},
            headers=cand_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["applied"] == 1

        listing = client.get("/api/v1/cvs", headers=cand_headers).json()
        new_cv = next(item for item in listing if item["id"] == body["new_cv_id"])
        parent = next(item for item in listing if item["id"] == cv["id"])
        assert new_cv["version"] == cv["version"] + 1
        assert new_cv["is_primary"] is True
        assert parent["is_primary"] is False
        assert new_cv["extraction_confirmed"] is True

        # PDF ReportLab benar-benar tersimpan & terkirim (magic %PDF).
        file_resp = client.get(f"/api/v1/cvs/{body['new_cv_id']}/file", headers=cand_headers)
        assert file_resp.status_code == 200
        assert file_resp.content.startswith(b"%PDF")

        # Ekstraksi auto-confirm dengan payload yang sudah disunting.
        extraction = client.get(
            f"/api/v1/cvs/{body['new_cv_id']}/extraction", headers=cand_headers
        ).json()
        assert extraction["status"] == "done"
        assert extraction["parser_version"] == "optimized-v1"
        assert extraction["confirmed_by"] == reg["user"]["id"]
        bullets = extraction["payload"]["experiences"][0]["bullets"]
        assert edits[0]["suggested_text"] in bullets
        assert edits[0]["original_text"] not in bullets

        with factory() as db:
            row = db.get(CV, uuid.UUID(body["new_cv_id"]))
            assert row.parent_cv_id == uuid.UUID(cv["id"])

        detail = client.get(
            f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}", headers=cand_headers
        ).json()
        assert detail["status"] == "applied"
        assert detail["applied_cv_id"] == body["new_cv_id"]
        assert detail["decisions"]["edit-1"] == {"accepted": True}

    def test_apply_zero_accepted_returns_400(self, db_engine, monkeypatch):
        client, _calls, holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        opt_id = self._generate(client, _calls, holder, cand_headers, cv, job)

        for decisions in ({}, {"edit-1": False}):
            resp = client.post(
                f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}/apply",
                json={"decisions": decisions},
                headers=cand_headers,
            )
            assert resp.status_code == 400

    def test_apply_twice_returns_409(self, db_engine, monkeypatch):
        client, _calls, holder, _settings, _factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        opt_id = self._generate(client, _calls, holder, cand_headers, cv, job)

        first = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}/apply",
            json={"decisions": {"edit-1": True}},
            headers=cand_headers,
        )
        assert first.status_code == 200

        second = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}/apply",
            json={"decisions": {"edit-1": True}},
            headers=cand_headers,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    def test_apply_grounding_gate_blocks_fabricated_edits(self, db_engine, monkeypatch):
        client, _calls, _holder, _settings, factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, _reg = _confirmed_cv_and_job(client)
        payload = get_extraction(client, cand_headers, cv["id"])["payload"]
        bullet = payload["experiences"][0]["bullets"][0]

        # Baris completed "palsu" (lolos di generasi) berisi entitas fabrikasi —
        # gerbang apply (defense in depth) wajib menolaknya.
        with factory() as db:
            opt = CvOptimization(
                cv_id=db.get(CV, uuid.UUID(cv["id"])).id,
                job_id=db.get(Job, uuid.UUID(job["id"])).id,
                status="completed",
                suggestions=[
                    {
                        "suggestion_id": "edit-1",
                        "source_ref": bullet,
                        "section": "pengalaman",
                        "original_text": bullet,
                        "suggested_text": "Memimpin transformasi data di PT Maju Jaya Sentosa.",
                        "rationale": "Penekanan kepemimpinan.",
                        "change_type": "reword",
                    }
                ],
                grounding_report={"passed": True, "violations": [], "checked": 1},
                llm_provider="groq",
                llm_model=PRIMARY_MODEL,
                prompt_version=PROMPT_VERSION,
            )
            db.add(opt)
            db.commit()
            opt_id = str(opt.id)

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/optimizations/{opt_id}/apply",
            json={"decisions": {"edit-1": True}},
            headers=cand_headers,
        )
        assert resp.status_code == 400
        details = resp.json()["error"]["details"]
        assert any(item["rule"] == "fabricated_entity" for item in details)

    def test_apply_fallback_appends_unmatched_bullet(self, db_engine, monkeypatch):
        """Pemetaan pragmatis: original_text yang hanya hidup di baris teks CV
        (bukan field payload) → bullet hasil edit ditambahkan ke pengalaman."""
        client, _calls, _holder, settings, factory = _opt_client(db_engine, monkeypatch)
        cand_headers, _hr, cv, job, reg = _confirmed_cv_and_job(client)

        with factory() as db:
            user = db.get(User, uuid.UUID(reg["user"]["id"]))
            cv_row = db.get(CV, uuid.UUID(cv["id"]))
            job_row = db.get(Job, uuid.UUID(job["id"]))
            opt = CvOptimization(
                cv_id=cv_row.id,
                job_id=job_row.id,
                status="completed",
                suggestions=[
                    {
                        "suggestion_id": "edit-7",
                        "source_ref": "PENGALAMAN",
                        "section": "pengalaman",
                        "original_text": "PENGALAMAN",
                        "suggested_text": "Ruang lingkup pekerjaan analis data diperluas.",
                        "rationale": "Penataan ulang cakupan peran.",
                        "change_type": "reword",
                    }
                ],
                grounding_report={"passed": True, "violations": [], "checked": 1},
                llm_provider="groq",
                llm_model=PRIMARY_MODEL,
                prompt_version=PROMPT_VERSION,
            )
            db.add(opt)
            db.commit()

            new_cv = optimization_service.apply_optimization(
                db, user, cv_row.id, opt.id, {"edit-7": True}, settings
            )

        bullets = new_cv.extraction.payload["experiences"][0]["bullets"]
        assert "Ruang lingkup pekerjaan analis data diperluas." in bullets
        assert new_cv.version == cv_row.version + 1
        assert new_cv.parent_cv_id == cv_row.id
        assert new_cv.is_primary is True
