"""Uji API taksonomi skill: auth, RBAC, autocomplete, detail, envelope 404.
Plus skill kandidat (M2 Wave 2B): GET /cvs/{id}/skills, apply, /me/candidate-skills,
serta normalisasi skill lowongan (skills_normalized pada detail HR)."""

from uuid import uuid4

from tests.helpers import (
    auth_headers,
    create_job,
    make_candidate,
    make_hr_with_company,
    make_job_payload,
    register,
)
from tests.test_extraction_api import CV_LINES, make_multiline_pdf, upload_cv


def _candidate(client):
    reg = register(client, role="candidate")
    return auth_headers(reg)


def _hr(client):
    reg = register(client, role="hr")
    return auth_headers(reg)


class TestTaxonomyEndpoint:
    def test_401_without_token(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/taxonomy")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_candidate_gets_summary(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/taxonomy", headers=_candidate(client))
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "1.1.0"
        assert body["total"] >= 300
        names = {c["name"] for c in body["categories"]}
        assert "Programming Languages" in names and "Leadership" in names
        total_by_cat = sum(c["count"] for c in body["categories"])
        assert total_by_cat == body["total"]

    def test_hr_also_allowed(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/taxonomy", headers=_hr(client))
        assert resp.status_code == 200
        assert resp.json()["total"] >= 300


class TestAutocompleteEndpoint:
    def test_401_without_token(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/autocomplete?q=pyt")
        assert resp.status_code == 401

    def test_prefix_query_finds_python(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/autocomplete?q=pyt", headers=_candidate(client))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items, "pyt harus menemukan minimal Python"
        assert items[0]["slug"] == "python"
        for item in items:
            assert set(item) == {"id", "slug", "name", "category", "skill_type"}

    def test_short_query_returns_empty_200(self, client, seeded_taxonomy):
        # Kontrak dipilih: q < 2 karakter -> 200 + items kosong (bukan 422).
        resp = client.get("/api/v1/skills/autocomplete?q=p", headers=_candidate(client))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

        resp = client.get("/api/v1/skills/autocomplete", headers=_candidate(client))
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_alias_matches(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/autocomplete?q=k8s", headers=_candidate(client))
        assert resp.status_code == 200
        slugs = [item["slug"] for item in resp.json()["items"]]
        assert "kubernetes" in slugs

    def test_limit_is_respected(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/autocomplete?q=co&limit=3", headers=_candidate(client))
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 3

    def test_single_character_still_empty_for_two_char_rule(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/autocomplete?q=java", headers=_candidate(client))
        slugs = [item["slug"] for item in resp.json()["items"]]
        assert "java" in slugs and "javascript" in slugs
        assert slugs.index("java") < slugs.index("javascript")


class TestSkillDetailEndpoint:
    def test_401_without_token(self, client, seeded_taxonomy):
        resp = client.get("/api/v1/skills/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 401

    def test_detail_with_aliases(self, client, seeded_taxonomy, db_session):
        from sqlalchemy import select

        from app.models.skill import CanonicalSkill

        skill = db_session.scalar(select(CanonicalSkill).where(CanonicalSkill.slug == "python"))
        resp = client.get(f"/api/v1/skills/{skill.id}", headers=_candidate(client))
        assert resp.status_code == 200
        body = resp.json()
        assert body["slug"] == "python"
        assert body["name"] == "Python"
        assert body["category"] == "Programming Languages"
        assert body["skill_type"] == "hard"
        assert "bahasa pemrograman python" in body["aliases"]
        assert body["taxonomy_version"] == "1.1.0"
        assert "fastapi" in body["related"]

    def test_404_envelope_when_missing(self, client, seeded_taxonomy):
        resp = client.get(
            "/api/v1/skills/00000000-0000-0000-0000-000000000000", headers=_candidate(client)
        )
        assert resp.status_code == 404
        error = resp.json()["error"]
        assert error["code"] == "NOT_FOUND"
        assert error["message"]


class TestRbac:
    def test_candidate_and_hr_both_200(self, client, seeded_taxonomy):
        for headers in (_candidate(client), _hr(client)):
            resp = client.get("/api/v1/skills/taxonomy", headers=headers)
            assert resp.status_code == 200


# --- Skill kandidat (M2 Wave 2B) ---

ITEM_KEYS = {
    "id",
    "canonical",
    "raw_name",
    "confidence",
    "evidence",
    "source_section",
    "extraction_method",
    "status",
    "needs_review",
    "suggestions",
}


def _candidate_with_confirmed_cv(client):
    """Kandidat + CV terunggah + hasil ekstraksi TERKONFIRMASI (hook skill jalan)."""
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 200, resp.text
    return headers, cv


def _get_cv_skills(client, headers, cv_id) -> dict:
    resp = client.get(f"/api/v1/cvs/{cv_id}/skills", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestCvSkillsEndpoint:
    def test_401_without_token(self, client, seeded_taxonomy):
        assert client.get(f"/api/v1/cvs/{uuid4()}/skills").status_code == 401

    def test_confirm_hook_persists_suggested_rows(self, client, seeded_taxonomy):
        headers, cv = _candidate_with_confirmed_cv(client)
        data = _get_cv_skills(client, headers, cv["id"])
        assert data["total"] == len(data["items"]) >= 2
        slugs = {i["canonical"]["slug"] for i in data["items"]}
        assert {"sql", "python"} <= slugs
        for item in data["items"]:
            assert set(item) == ITEM_KEYS
            # Hanya item berpadanan kanon yang disimpan (FK NOT NULL).
            assert item["canonical"] is not None
            assert set(item["canonical"]) == {"slug", "name", "category", "skill_type"}
            assert item["status"] == "suggested"
            assert item["extraction_method"] in ("explicit", "inferred")
            assert item["needs_review"] is False
            assert item["suggestions"] == []

    def test_reconfirm_does_not_duplicate(self, client, seeded_taxonomy):
        headers, cv = _candidate_with_confirmed_cv(client)
        first = _get_cv_skills(client, headers, cv["id"])
        resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
        assert resp.status_code == 200
        second = _get_cv_skills(client, headers, cv["id"])
        assert second["total"] == first["total"]
        assert {i["canonical"]["slug"] for i in second["items"]} == {
            i["canonical"]["slug"] for i in first["items"]
        }

    def test_rbac_and_ownership(self, client, seeded_taxonomy):
        _, headers_owner = make_candidate(client, email="owner-cvskills@example.com")
        cv = upload_cv(client, headers_owner, make_multiline_pdf(CV_LINES))
        assert (
            client.put(
                f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers_owner
            ).status_code
            == 200
        )
        # HR → 403 di kedua endpoint.
        _, hr_headers, _ = make_hr_with_company(client)
        assert client.get(f"/api/v1/cvs/{cv['id']}/skills", headers=hr_headers).status_code == 403
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/skills/apply",
                json={"skill_ids": []},
                headers=hr_headers,
            ).status_code
            == 403
        )
        # Kandidat lain → 404 (keberadaan tidak dibocorkan).
        _, headers_other = make_candidate(client, email="other-cvskills@example.com")
        assert (
            client.get(f"/api/v1/cvs/{cv['id']}/skills", headers=headers_other).status_code == 404
        )
        assert (
            client.post(
                f"/api/v1/cvs/{cv['id']}/skills/apply",
                json={"skill_ids": []},
                headers=headers_other,
            ).status_code
            == 404
        )
        # CV tidak ada → 404.
        assert client.get(f"/api/v1/cvs/{uuid4()}/skills", headers=headers_owner).status_code == 404


class TestApplySkillsEndpoint:
    def test_apply_then_reconfirm_preserves_accepted(self, client, seeded_taxonomy):
        headers, cv = _candidate_with_confirmed_cv(client)
        data = _get_cv_skills(client, headers, cv["id"])
        chosen = data["items"][:2]
        chosen_ids = [i["id"] for i in chosen]

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/skills/apply", json={"skill_ids": chosen_ids}, headers=headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["applied"] == 2
        # Idempoten: apply ulang → 0.
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/skills/apply", json={"skill_ids": chosen_ids}, headers=headers
        )
        assert resp.json()["applied"] == 0

        # Konfirmasi ulang: baris accepted dipertahankan, tidak ada duplikat suggested.
        assert (
            client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers).status_code
            == 200
        )
        after = _get_cv_skills(client, headers, cv["id"])
        assert after["total"] == data["total"]
        statuses = {i["id"]: i["status"] for i in after["items"]}
        for item_id in chosen_ids:
            assert statuses[item_id] == "accepted"

        # Profil kandidat kini memuat nama kanon skill yang diterima.
        prof = client.get("/api/v1/me/candidate-profile", headers=headers).json()
        prof_names = {s.lower() for s in prof["skills"]}
        for item in chosen:
            assert item["canonical"]["name"].lower() in prof_names

    def test_apply_max_30_returns_400(self, client, seeded_taxonomy):
        _, headers = make_candidate(client)
        resp = client.put(
            "/api/v1/me/candidate-profile",
            json={"full_name": "Budi Santoso", "skills": [f"Skill Isi {i}" for i in range(30)]},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
        assert (
            client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers).status_code
            == 200
        )
        data = _get_cv_skills(client, headers, cv["id"])
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/skills/apply",
            json={"skill_ids": [data["items"][0]["id"]]},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "Melebihi batas 30 skill profil." in resp.json()["error"]["message"]

    def test_apply_ignores_unknown_ids(self, client, seeded_taxonomy):
        headers, cv = _candidate_with_confirmed_cv(client)
        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/skills/apply",
            json={"skill_ids": [str(uuid4())]},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["applied"] == 0


class TestMyCandidateSkillsEndpoint:
    def test_401_and_rbac(self, client, seeded_taxonomy):
        assert client.get("/api/v1/me/candidate-skills").status_code == 401
        _, hr_headers, _ = make_hr_with_company(client)
        assert client.get("/api/v1/me/candidate-skills", headers=hr_headers).status_code == 403
        assert (
            client.delete(f"/api/v1/me/candidate-skills/{uuid4()}", headers=hr_headers).status_code
            == 403
        )

    def test_list_apply_delete_flow(self, client, seeded_taxonomy):
        _, headers_other = make_candidate(client, email="other-myskill@example.com")
        headers, cv = _candidate_with_confirmed_cv(client)
        data = _get_cv_skills(client, headers, cv["id"])
        target = data["items"][0]

        resp = client.post(
            f"/api/v1/cvs/{cv['id']}/skills/apply",
            json={"skill_ids": [target["id"]]},
            headers=headers,
        )
        assert resp.json()["applied"] == 1

        listing = client.get("/api/v1/me/candidate-skills", headers=headers).json()
        assert listing["total"] == 1
        item = listing["items"][0]
        assert set(item) == ITEM_KEYS
        assert item["id"] == target["id"]
        assert item["status"] == "accepted"

        # Skill milik kandidat lain → 404.
        resp = client.delete(f"/api/v1/me/candidate-skills/{item['id']}", headers=headers_other)
        assert resp.status_code == 404

        # Hapus milik sendiri → 204, daftar & profil kembali bersih.
        resp = client.delete(f"/api/v1/me/candidate-skills/{item['id']}", headers=headers)
        assert resp.status_code == 204
        assert client.get("/api/v1/me/candidate-skills", headers=headers).json()["total"] == 0
        prof = client.get("/api/v1/me/candidate-profile", headers=headers).json()
        assert item["canonical"]["name"] not in prof["skills"]

    def test_delete_missing_returns_404(self, client, seeded_taxonomy):
        _, headers = make_candidate(client)
        resp = client.delete(f"/api/v1/me/candidate-skills/{uuid4()}", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"


# --- Normalisasi skill lowongan (detail HR) ---


class TestJobSkillsNormalized:
    def test_create_job_dedupes_and_marks_needs_review(self, client, seeded_taxonomy):
        _, headers, _ = make_hr_with_company(client)
        job = create_job(
            client,
            headers,
            skills=[
                {"name": "Python", "required": True},
                {"name": "SQL", "required": True},
                {"name": "python", "required": False},
                {"name": "Bahasa Klingon", "required": False},
            ],
        )
        # JSONB skills tetap sumber tampilan (dup "python" sudah dilipat di skema).
        assert [s["name"] for s in job["skills"]] == ["Python", "SQL", "Bahasa Klingon"]

        detail = client.get(f"/api/v1/hr/jobs/{job['id']}", headers=headers).json()
        normalized = detail["skills_normalized"]
        assert normalized is not None
        # "Bahasa Klingon" tanpa padanan kanon → tidak menjadi baris job_skills.
        slugs = {n["canonical"]["slug"] for n in normalized}
        assert slugs == {"python", "sql"}
        python_row = next(n for n in normalized if n["canonical"]["slug"] == "python")
        assert python_row["raw_name"] == "Python"
        assert python_row["required"] is True
        assert python_row["confidence"] == 0.95
        assert python_row["needs_review"] is False
        for n in normalized:
            assert set(n) == {"canonical", "raw_name", "required", "confidence", "needs_review"}
            assert set(n["canonical"]) == {"slug", "name", "category"}

    def test_update_job_replaces_normalized_rows(self, client, seeded_taxonomy):
        _, headers, _ = make_hr_with_company(client)
        job = create_job(client, headers)
        resp = client.put(
            f"/api/v1/hr/jobs/{job['id']}",
            json=make_job_payload(
                skills=[{"name": "Docker", "required": True}, {"name": "Go", "required": False}]
            ),
            headers=headers,
        )
        assert resp.status_code == 200
        detail = client.get(f"/api/v1/hr/jobs/{job['id']}", headers=headers).json()
        assert {n["canonical"]["slug"] for n in detail["skills_normalized"]} == {"docker", "go"}

    def test_list_endpoints_keep_skills_normalized_none(self, client, seeded_taxonomy):
        _, headers, _ = make_hr_with_company(client)
        create_job(client, headers)
        listing = client.get("/api/v1/hr/jobs", headers=headers).json()
        assert listing["items"], "minimal satu lowongan dibuat"
        assert all(item["skills_normalized"] is None for item in listing["items"])

    def test_detail_without_taxonomy_is_none_safe(self, client):
        """Tanpa seed taksonomi: job tetap terbuat, skills_normalized kosong (bukan 500)."""
        _, headers, _ = make_hr_with_company(client)
        job = create_job(client, headers)
        detail = client.get(f"/api/v1/hr/jobs/{job['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["skills_normalized"] == []
