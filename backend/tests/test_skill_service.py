"""Service test skill kandidat & lowongan (M2 Wave 2B).

Fokus: extract_skills_from_payload (explicit/inferred/batas frasa/presedens),
persist_cv_skills (idempoten, preserve accepted, hormati UNIQUE),
apply_skills_to_profile (ownership, dedupe profil, guard batas 30),
get_cv_skills (accepted dari CV lain), delete_my_skill, normalize_job_skills,
serta sinkronisasi job_skills di job_service.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.company import Company, CompanyMember
from app.models.cv import CV, CvExtraction
from app.models.profile import CandidateProfile
from app.models.skill import CandidateSkill, CanonicalSkill, JobSkill
from app.models.user import User
from app.schemas.job import JobIn
from app.services import job_service, skill_service

# --- Helper pembuatan baris langsung di DB (tanpa HTTP) ---


def make_user(db, role: str = "candidate") -> User:
    user = User(
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.test",
        password_hash="hash-palsu-untuk-test",
        full_name="Budi Santoso",
        role=role,
    )
    db.add(user)
    db.flush()
    db.add(CandidateProfile(user_id=user.id))
    db.flush()
    return user


def make_cv_with_payload(db, user: User, payload: dict | None):
    cv = CV(
        candidate_user_id=user.id,
        status="ready",
        file_path="test/uploads/cv.pdf",
        original_filename="cv.pdf",
        mime_type="application/pdf",
        file_size_bytes=100,
        content_sha256=uuid.uuid4().hex,
    )
    db.add(cv)
    db.flush()
    extraction = CvExtraction(cv_id=cv.id, status="done", parser_version="test-v1", payload=payload)
    db.add(extraction)
    db.flush()
    return cv, extraction


def make_payload(skills=None, bullets=None, summary=None) -> dict:
    return {
        "skills": skills or [],
        "experiences": ([{"bullets": bullets}] if bullets else []),
        "projects": [],
        "summary": summary,
    }


def rows_by_slug(db, rows: list[CandidateSkill]) -> dict[str, CandidateSkill]:
    """Peta slug kanon -> baris (slug unik per baris karena UNIQUE(kandidat, kanon))."""
    return {db.get(CanonicalSkill, r.canonical_skill_id).slug: r for r in rows}


def all_rows(db, user: User) -> list[CandidateSkill]:
    return list(
        db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_user_id == user.id))
    )


# --- extract_skills_from_payload ---


class TestExtractSkillsFromPayload:
    def test_explicit_normalization(self, db_session, seeded_taxonomy):
        payload = make_payload(
            skills=[
                {"name": "SQL", "evidence": "KEAHLIAN", "confidence": 0.8},
                {"name": "Python", "confidence": 0.9},
            ]
        )
        items = skill_service.extract_skills_from_payload(db_session, payload)
        assert [i["raw_name"] for i in items] == ["SQL", "Python"]
        slugs = {i["canonical"]["slug"] for i in items}
        assert slugs == {"sql", "python"}
        for item in items:
            assert item["extraction_method"] == "explicit"
            assert item["source_section"] == "skills"
            assert item["confidence"] == 0.95
            assert item["needs_review"] is False
            assert item["canonical"]["name"] in ("SQL", "Python")
            assert set(item["canonical"]) == {"slug", "name", "category", "skill_type"}
        assert items[0]["evidence"] == "KEAHLIAN"

    def test_inferred_from_bullets(self, db_session, seeded_taxonomy):
        bullet = "Menangani pekerjaan analis data menggunakan SQL dan Excel pivot."
        items = skill_service.extract_skills_from_payload(
            db_session, make_payload(bullets=[bullet])
        )
        assert items, "minimal sql & excel harus ditemukan dari bullet"
        slugs = {i["canonical"]["slug"] for i in items}
        assert {"sql", "excel"} <= slugs
        for item in items:
            assert item["extraction_method"] == "inferred"
            assert item["source_section"] == "experience"
            assert item["confidence"] == 0.7
            assert item["needs_review"] is False
            assert "Menangani pekerjaan" in item["evidence"]

    def test_inferred_from_summary_and_projects(self, db_session, seeded_taxonomy):
        payload = make_payload(summary="Terbiasa dengan Docker dan Git dalam kerja harian.")
        payload["projects"] = [{"name": "Portal", "description": "Dibangun dengan FastAPI."}]
        items = skill_service.extract_skills_from_payload(db_session, payload)
        slugs = {i["canonical"]["slug"] for i in items}
        assert {"docker", "git", "fastapi"} <= slugs
        sections = {i["canonical"]["slug"]: i["source_section"] for i in items}
        assert sections["docker"] == "summary"
        assert sections["fastapi"] == "projects"

    def test_phrase_boundary_javascript_does_not_match_java(self, db_session, seeded_taxonomy):
        items = skill_service.extract_skills_from_payload(
            db_session, make_payload(bullets=["javascript developer pada tim produk."])
        )
        slugs = {i["canonical"]["slug"] for i in items}
        assert "javascript" in slugs
        assert "java" not in slugs

    def test_explicit_precedence_over_inferred(self, db_session, seeded_taxonomy):
        payload = make_payload(
            skills=[{"name": "SQL"}],
            bullets=["menggunakan SQL dan Excel harian."],
        )
        items = skill_service.extract_skills_from_payload(db_session, payload)
        sql = [i for i in items if i["canonical"]["slug"] == "sql"]
        excel = [i for i in items if i["canonical"]["slug"] == "excel"]
        assert len(sql) == 1 and sql[0]["extraction_method"] == "explicit"
        assert len(excel) == 1 and excel[0]["extraction_method"] == "inferred"

    def test_unmatched_raw_included_with_needs_review(self, db_session, seeded_taxonomy):
        items = skill_service.extract_skills_from_payload(
            db_session, make_payload(skills=[{"name": "Bahasa Klingon", "confidence": 0.8}])
        )
        assert len(items) == 1
        item = items[0]
        assert item["canonical"] is None
        assert item["raw_name"] == "Bahasa Klingon"
        assert item["needs_review"] is True
        # Confidence payload TIDAK dipakai untuk item tanpa padanan (tetap 0.0).
        assert item["confidence"] == 0.0
        assert item["source_section"] == "skills"
        assert item["extraction_method"] == "explicit"

    def test_result_ordering_and_dedupe(self, db_session, seeded_taxonomy):
        payload = make_payload(
            skills=[{"name": "Docker"}, {"name": "docker"}, {"name": "Bahasa Klingon"}],
            bullets=["memakai SQL dan Excel."],
        )
        items = skill_service.extract_skills_from_payload(db_session, payload)
        methods = [i["extraction_method"] for i in items]
        assert methods[0] == "explicit"  # Docker (matched)
        assert "inferred" in methods  # SQL & Excel
        assert (
            methods[-1] == "explicit" and items[-1]["canonical"] is None
        )  # unmatched paling akhir
        slugs = [i["canonical"]["slug"] for i in items if i["canonical"]]
        assert len(slugs) == len(set(slugs)), "dedupe per slug kanon"
        assert len([i for i in items if i["canonical"] is None]) == 1

    def test_empty_payload_returns_empty(self, db_session, seeded_taxonomy):
        assert skill_service.extract_skills_from_payload(db_session, None) == []
        assert skill_service.extract_skills_from_payload(db_session, {}) == []


# --- persist_cv_skills ---


class TestPersistCvSkills:
    def test_creates_suggested_rows_with_source_cv(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, extraction = make_cv_with_payload(
            db_session,
            user,
            make_payload(skills=[{"name": "SQL"}], bullets=["menggunakan Excel harian."]),
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        rows = all_rows(db_session, user)
        by_slug = rows_by_slug(db_session, rows)
        assert set(by_slug) == {"sql", "excel"}
        for row in rows:
            assert row.status == "suggested"
            assert row.source_cv_id == cv.id
        assert by_slug["sql"].extraction_method == "explicit"
        assert by_slug["excel"].extraction_method == "inferred"

    def test_idempotent_second_call_yields_same_state(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, extraction = make_cv_with_payload(
            db_session, user, make_payload(skills=[{"name": "SQL"}, {"name": "Docker"}])
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        first = [(r.canonical_skill_id, r.status, r.raw_name) for r in all_rows(db_session, user)]
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        second = [(r.canonical_skill_id, r.status, r.raw_name) for r in all_rows(db_session, user)]
        assert sorted(first) == sorted(second)

    def test_preserves_accepted_and_rejected_rows(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, extraction = make_cv_with_payload(
            db_session,
            user,
            make_payload(skills=[{"name": "SQL"}, {"name": "Docker"}, {"name": "Go"}]),
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        by_slug = rows_by_slug(db_session, all_rows(db_session, user))
        by_slug["sql"].status = "accepted"
        by_slug["go"].status = "rejected"
        db_session.commit()

        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        by_slug2 = rows_by_slug(db_session, all_rows(db_session, user))
        assert set(by_slug2) == {"sql", "docker", "go"}  # tidak ada duplikat
        assert by_slug2["sql"].status == "accepted"  # keputusan kandidat dipertahankan
        assert by_slug2["go"].status == "rejected"
        assert by_slug2["docker"].status == "suggested"

    def test_skips_suggested_from_other_cv(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv1, ex1 = make_cv_with_payload(db_session, user, make_payload(skills=[{"name": "SQL"}]))
        skill_service.persist_cv_skills(db_session, user, cv1.id, ex1)
        db_session.commit()
        cv2, ex2 = make_cv_with_payload(db_session, user, make_payload(skills=[{"name": "SQL"}]))
        skill_service.persist_cv_skills(db_session, user, cv2.id, ex2)
        db_session.commit()
        rows = all_rows(db_session, user)
        assert len(rows) == 1  # UNIQUE(kandidat, kanon) dihormati
        assert rows[0].source_cv_id == cv1.id

    def test_skips_unmatched_items(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, extraction = make_cv_with_payload(
            db_session, user, make_payload(skills=[{"name": "Bahasa Klingon"}, {"name": "SQL"}])
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        rows = all_rows(db_session, user)
        assert len(rows) == 1
        assert db_session.get(CanonicalSkill, rows[0].canonical_skill_id).slug == "sql"


# --- apply_skills_to_profile ---


class TestApplySkillsToProfile:
    def _setup_cv(self, db_session, user: User, skill_names: list[str]):
        cv, extraction = make_cv_with_payload(
            db_session, user, make_payload(skills=[{"name": n} for n in skill_names])
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        return cv, rows_by_slug(db_session, all_rows(db_session, user))

    def test_other_users_cv_raises_not_found(self, db_session, seeded_taxonomy):
        owner = make_user(db_session)
        other = make_user(db_session)
        cv, by_slug = self._setup_cv(db_session, owner, ["SQL"])
        with pytest.raises(NotFoundError):
            skill_service.apply_skills_to_profile(db_session, other, cv.id, [by_slug["sql"].id])

    def test_accept_and_merge_profile_case_insensitive(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        profile = db_session.get(CandidateProfile, user.id)
        profile.skills = ["sql"]  # sudah ada (huruf kecil) — tidak boleh terduplikasi
        db_session.commit()
        cv, by_slug = self._setup_cv(db_session, user, ["SQL", "Docker"])

        applied = skill_service.apply_skills_to_profile(
            db_session, user, cv.id, [by_slug["sql"].id, by_slug["docker"].id]
        )
        assert applied == 2
        # Nama kanon "SQL" (huruf campuran) tidak ditambahkan ulang; Docker ya.
        assert profile.skills == ["sql", "Docker"]
        assert by_slug["sql"].status == "accepted"
        assert by_slug["docker"].status == "accepted"
        assert by_slug["sql"].extraction_method == "explicit"  # metode tidak berubah

        # Idempoten: panggilan kedua mengembalikan 0, profil tetap.
        assert (
            skill_service.apply_skills_to_profile(
                db_session, user, cv.id, [by_slug["sql"].id, by_slug["docker"].id]
            )
            == 0
        )
        assert profile.skills == ["sql", "Docker"]

    def test_ignores_rows_from_other_cv(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv1, by_slug1 = self._setup_cv(db_session, user, ["SQL"])
        cv2, by_slug2 = self._setup_cv(db_session, user, ["Docker"])
        applied = skill_service.apply_skills_to_profile(
            db_session, user, cv1.id, [by_slug1["sql"].id, by_slug2["docker"].id]
        )
        assert applied == 1  # baris docker milik cv2 → diabaikan
        assert by_slug2["docker"].status == "suggested"

    def test_max_30_guard_raises_and_keeps_state(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        profile = db_session.get(CandidateProfile, user.id)
        profile.skills = [f"skill-{i}" for i in range(30)]
        db_session.commit()
        cv, by_slug = self._setup_cv(db_session, user, ["SQL"])

        with pytest.raises(BadRequestError) as exc:
            skill_service.apply_skills_to_profile(db_session, user, cv.id, [by_slug["sql"].id])
        assert "Melebihi batas 30 skill profil." in str(exc.value)
        # Tidak ada perubahan state (baris tetap suggested, profil tetap 30).
        db_session.expire_all()
        assert db_session.get(CandidateSkill, by_slug["sql"].id).status == "suggested"
        assert len(db_session.get(CandidateProfile, user.id).skills) == 30


# --- get_cv_skills ---


class TestGetCvSkills:
    def test_marks_accepted_from_other_cv(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv1, ex1 = make_cv_with_payload(db_session, user, make_payload(skills=[{"name": "SQL"}]))
        skill_service.persist_cv_skills(db_session, user, cv1.id, ex1)
        cv2, ex2 = make_cv_with_payload(db_session, user, make_payload(skills=[{"name": "Docker"}]))
        skill_service.persist_cv_skills(db_session, user, cv2.id, ex2)
        db_session.commit()
        by_slug2 = rows_by_slug(db_session, all_rows(db_session, user))
        by_slug2["docker"].status = "accepted"
        db_session.commit()

        rows = rows_by_slug(db_session, skill_service.get_cv_skills(db_session, user, cv1.id))
        assert set(rows) == {"sql", "docker"}
        docker_view = rows["docker"]
        assert docker_view.status == "accepted" and docker_view.source_cv_id == cv2.id
        assert rows["sql"].status == "suggested"

    def test_other_users_cv_raises_not_found(self, db_session, seeded_taxonomy):
        owner = make_user(db_session)
        other = make_user(db_session)
        make_cv_with_payload(db_session, owner, make_payload(skills=[{"name": "SQL"}]))
        with pytest.raises(NotFoundError):
            skill_service.get_cv_skills(db_session, other, _cv_id_of(db_session, owner))


def _cv_id_of(db, user: User) -> uuid.UUID:
    return db.scalar(select(CV).where(CV.candidate_user_id == user.id)).id


# --- list_my_skills & delete_my_skill ---


class TestMySkills:
    def test_list_only_accepted_ordered_by_name(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, extraction = make_cv_with_payload(
            db_session,
            user,
            make_payload(skills=[{"name": "Docker"}, {"name": "SQL"}, {"name": "Go"}]),
        )
        skill_service.persist_cv_skills(db_session, user, cv.id, extraction)
        db_session.commit()
        by_slug = rows_by_slug(db_session, all_rows(db_session, user))
        by_slug["docker"].status = "accepted"
        by_slug["go"].status = "accepted"
        db_session.commit()  # SQL tetap suggested → tidak masuk daftar

        rows = skill_service.list_my_skills(db_session, user)
        names = [db_session.get(CanonicalSkill, r.canonical_skill_id).name for r in rows]
        assert names == ["Docker", "Go"]  # hanya accepted, urut nama kanon

    def test_delete_removes_row_and_profile_name(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, by_slug = TestApplySkillsToProfile()._setup_cv(db_session, user, ["SQL", "Docker"])
        skill_service.apply_skills_to_profile(
            db_session, user, cv.id, [by_slug["sql"].id, by_slug["docker"].id]
        )
        profile = db_session.get(CandidateProfile, user.id)
        assert set(profile.skills) == {"SQL", "Docker"}

        skill_service.delete_my_skill(db_session, user, by_slug["sql"].id)
        assert db_session.get(CandidateSkill, by_slug["sql"].id) is None
        assert profile.skills == ["Docker"]

    def test_delete_profile_without_name_is_best_effort(self, db_session, seeded_taxonomy):
        user = make_user(db_session)
        cv, by_slug = TestApplySkillsToProfile()._setup_cv(db_session, user, ["SQL"])
        profile = db_session.get(CandidateProfile, user.id)
        profile.skills = ["halo lain"]  # nama kanon tidak ada di profil
        db_session.commit()
        skill_service.delete_my_skill(db_session, user, by_slug["sql"].id)
        assert profile.skills == ["halo lain"]

    def test_delete_other_users_skill_raises_not_found(self, db_session, seeded_taxonomy):
        owner = make_user(db_session)
        other = make_user(db_session)
        cv, by_slug = TestApplySkillsToProfile()._setup_cv(db_session, owner, ["SQL"])
        with pytest.raises(NotFoundError):
            skill_service.delete_my_skill(db_session, other, by_slug["sql"].id)


# --- normalize_job_skills + sinkronisasi job_service ---


def make_job_in(skills: list[dict]) -> JobIn:
    from app.schemas.job import SkillIn

    return JobIn(
        title="Data Engineer",
        description="Membangun pipeline data perusahaan bersama tim data platform.",
        skills=[SkillIn(**s) for s in skills],
        employment_type="full_time",
        work_mode="hybrid",
    )


def make_hr_with_company_rows(db) -> User:
    user = make_user(db, role="hr")
    company = Company(name="PT Uji Integrasi", created_by_user_id=user.id)
    db.add(company)
    db.flush()
    db.add(CompanyMember(company_id=company.id, user_id=user.id, role_in_company="owner"))
    db.flush()
    return user


class TestNormalizeJobSkills:
    def test_dedupe_canonical_with_required_precedence(self, db_session, seeded_taxonomy):
        items = skill_service.normalize_job_skills(
            db_session,
            [
                {"name": "Python", "required": True},
                {"name": "SQL", "required": True},
                {"name": "python", "required": False},
            ],
        )
        assert len(items) == 2
        py = next(
            i
            for i in items
            if db_session.get(CanonicalSkill, i["canonical_skill_id"]).slug == "python"
        )
        assert py["required"] is True
        assert py["confidence"] == 0.95
        assert py["needs_review"] is False
        assert py["evidence"] is None

    def test_unmatched_kept_but_not_persistable(self, db_session, seeded_taxonomy):
        items = skill_service.normalize_job_skills(
            db_session,
            [{"name": "Bahasa Klingon", "required": False}, {"name": "SQL", "required": True}],
        )
        assert len(items) == 2
        klingon = next(i for i in items if i["canonical_skill_id"] is None)
        assert klingon["raw_name"] == "Bahasa Klingon"
        assert klingon["needs_review"] is True
        assert klingon["confidence"] == 0.0

        sql = next(i for i in items if i["canonical_skill_id"] is not None)
        assert db_session.get(CanonicalSkill, sql["canonical_skill_id"]).slug == "sql"

    def test_unmatched_dupe_takes_required_precedence(self, db_session, seeded_taxonomy):
        items = skill_service.normalize_job_skills(
            db_session,
            [
                {"name": "Bahasa Klingon", "required": False},
                {"name": "bahasa klingon", "required": True},
            ],
        )
        assert len(items) == 1
        assert items[0]["required"] is True


class TestJobServiceSkillsSync:
    def test_create_job_persists_matched_only(self, db_session, seeded_taxonomy):
        user = make_hr_with_company_rows(db_session)
        job = job_service.create_job(
            db_session,
            user,
            make_job_in(
                [
                    {"name": "Python", "required": True},
                    {"name": "SQL", "required": True},
                    {"name": "Bahasa Klingon", "required": False},
                ]
            ),
        )
        rows = db_session.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
        slugs = {db_session.get(CanonicalSkill, r.canonical_skill_id).slug for r in rows}
        assert slugs == {"python", "sql"}  # Bahasa Klingon tidak jadi baris
        # JSONB skills tetap sumber tampilan utuh.
        assert [s["name"] for s in job.skills] == ["Python", "SQL", "Bahasa Klingon"]
        python_row = next(
            r for r in rows if db_session.get(CanonicalSkill, r.canonical_skill_id).slug == "python"
        )
        assert python_row.required is True and python_row.confidence == 0.95

    def test_update_job_replaces_rows(self, db_session, seeded_taxonomy):
        user = make_hr_with_company_rows(db_session)
        job = job_service.create_job(
            db_session,
            user,
            make_job_in([{"name": "Python", "required": True}, {"name": "SQL", "required": True}]),
        )
        job_service.update_job(
            db_session,
            user,
            job.id,
            make_job_in([{"name": "Docker", "required": True}, {"name": "Go", "required": False}]),
        )
        rows = db_session.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
        slugs = {db_session.get(CanonicalSkill, r.canonical_skill_id).slug for r in rows}
        assert slugs == {"docker", "go"}  # baris lama terganti penuh

    def test_create_job_without_taxonomy_stays_graceful(self, db_session):
        """Tanpa seed taksonomi: skill tidak jadi baris job_skills, JSONB tetap."""
        user = make_hr_with_company_rows(db_session)
        job = job_service.create_job(
            db_session,
            user,
            make_job_in([{"name": "Python", "required": True}]),
        )
        assert db_session.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all() == []
        assert [s["name"] for s in job.skills] == ["Python"]
