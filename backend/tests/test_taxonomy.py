"""Uji fondasi taksonomi skill: validitas berkas data, seed idempoten, normalizer."""

import json
import re
from pathlib import Path

import pytest

import app.models  # noqa: F401 — daftarkan model
from app.core.config import Settings
from app.services import taxonomy_service as ts

GOLDEN_CV_DIR = Path(__file__).resolve().parents[2] / "eval" / "golden" / "cvs"
GOLDEN_JOB_DIR = Path(__file__).resolve().parents[2] / "eval" / "golden" / "jobs"


@pytest.fixture(scope="module")
def taxonomy_data() -> dict:
    return json.loads(ts.DEFAULT_TAXONOMY_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def skills_by_slug(taxonomy_data) -> dict[str, dict]:
    return {s["slug"]: s for s in taxonomy_data["skills"]}


def _aliases_of(skill: dict) -> set[str]:
    return {a.strip().lower() for a in skill.get("aliases", [])} | {skill["name"].strip().lower()}


class TestDataFileValidity:
    def test_at_least_300_canonical_skills(self, taxonomy_data):
        assert len(taxonomy_data["skills"]) >= 300

    def test_categories_match_required_list(self, taxonomy_data):
        expected = [
            "Programming Languages",
            "Web Development",
            "Mobile Development",
            "Data Engineering",
            "Data Analytics",
            "Machine Learning",
            "Artificial Intelligence",
            "Database Management",
            "Cloud Computing",
            "DevOps",
            "Cybersecurity",
            "Networking",
            "Software Engineering",
            "Project Management",
            "Business Analysis",
            "Design & UI/UX",
            "Quality Assurance",
            "Communication",
            "Leadership",
            "Other Professional Skills",
            "Languages",
        ]
        assert taxonomy_data["categories"] == expected

    def test_slugs_unique_and_kebab(self, taxonomy_data):
        slugs = [s["slug"] for s in taxonomy_data["skills"]]
        assert len(slugs) == len(set(slugs))
        pattern = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
        bad = [s for s in slugs if not pattern.match(s)]
        assert bad == []

    def test_aliases_unique_globally(self, taxonomy_data):
        owner: dict[str, str] = {}
        for s in taxonomy_data["skills"]:
            for alias in s.get("aliases", []):
                text = alias.strip().lower()
                assert text, f"alias kosong di {s['slug']}"
                assert text == alias, f"alias tidak lowercase/bersih: {alias!r}"
                assert text not in owner, f"alias duplikat global: {text!r}"
                owner[text] = s["slug"]
        assert len(owner) >= 300

    def test_alias_not_equal_to_other_skill_name(self, taxonomy_data, skills_by_slug):
        name_owner = {s["name"].strip().lower(): s["slug"] for s in taxonomy_data["skills"]}
        for s in taxonomy_data["skills"]:
            for alias in s.get("aliases", []):
                owner = name_owner.get(alias.strip().lower())
                assert owner is None or owner == s["slug"], (
                    f"alias {alias!r} ({s['slug']}) berbenturan dengan nama {owner}"
                )

    def test_normalized_keys_unique_across_names_and_aliases(self, taxonomy_data):
        owner: dict[str, str] = {}
        for s in taxonomy_data["skills"]:
            keys = [s["name"], *s.get("aliases", [])]
            for key in keys:
                nk = ts.normalize_text(key)
                assert nk, f"kunci kosong: {key!r}"
                if nk in owner and owner[nk] != s["slug"]:
                    pytest.fail(
                        f"kunci ternormalisasi bentrok: {nk!r} ({owner[nk]} vs {s['slug']})"
                    )
                owner[nk] = s["slug"]

    def test_related_slugs_exist(self, skills_by_slug):
        for slug, s in skills_by_slug.items():
            for related in s.get("related", []):
                assert related in skills_by_slug, f"{slug} -> related '{related}' tidak ada"

    def test_categories_valid_and_populated(self, taxonomy_data):
        allowed = set(taxonomy_data["categories"])
        counts: dict[str, int] = {}
        for s in taxonomy_data["skills"]:
            assert s["category"] in allowed, f"kategori aneh: {s['category']}"
            assert s["skill_type"] in ("hard", "soft")
            counts[s["category"]] = counts.get(s["category"], 0) + 1
        assert set(counts) == allowed, "ada kategori kosong"

    def test_soft_categories_contain_genuine_soft_skills(self, skills_by_slug):
        soft_expected = {
            "public-speaking",
            "negotiation",
            "stakeholder-management",
            "teamwork",
            "time-management",
            "critical-thinking",
            "presentation-skills",
            "writing-skills",
            "mentoring",
            "conflict-resolution",
            "active-listening",
            "adaptability",
            "problem-solving",
            "decision-making",
            "customer-service",
        }
        for slug in soft_expected:
            assert slug in skills_by_slug, f"soft skill wajib tidak ada: {slug}"
            assert skills_by_slug[slug]["skill_type"] == "soft"

    def test_no_ambiguous_pm_alias_anywhere(self, taxonomy_data):
        for s in taxonomy_data["skills"]:
            assert "pm" not in [a.strip().lower() for a in s.get("aliases", [])]


class TestAntiFalsePositive:
    def test_javascript_not_alias_of_java(self, skills_by_slug):
        assert "javascript" not in _aliases_of(skills_by_slug["java"])

    def test_react_native_not_alias_of_react(self, skills_by_slug):
        react = skills_by_slug["react"]
        assert "react native" not in _aliases_of(react)
        assert "react-native" not in _aliases_of(react)
        assert "react-native" in skills_by_slug

    def test_postgresql_not_alias_of_sql(self, skills_by_slug):
        assert "postgresql" not in _aliases_of(skills_by_slug["sql"])

    def test_deep_learning_not_alias_of_machine_learning(self, skills_by_slug):
        assert "deep learning" not in _aliases_of(skills_by_slug["machine-learning"])
        assert "deep-learning" in skills_by_slug

    def test_data_engineering_not_alias_of_data_analysis(self, skills_by_slug):
        assert "data engineering" not in _aliases_of(skills_by_slug["data-analysis"])
        assert "data-engineering" in skills_by_slug

    def test_ml_alias_only_under_machine_learning(self, taxonomy_data):
        owners = [
            s["slug"]
            for s in taxonomy_data["skills"]
            if "ml" in [a.strip().lower() for a in s.get("aliases", [])]
        ]
        assert owners == ["machine-learning"]


class TestGoldenCoverage:
    @staticmethod
    def _golden_skill_names() -> set[str]:
        names: set[str] = set()
        for directory in (GOLDEN_CV_DIR, GOLDEN_JOB_DIR):
            for path in sorted(directory.glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                for skill in data.get("skills", []):
                    names.add(skill if isinstance(skill, str) else skill.get("name"))
        names.discard(None)
        names.add("manajemen bug")  # disebut blueprint lowongan QA
        return names

    def test_every_golden_cv_and_job_skill_resolves(self, taxonomy_data):
        lookup = {}
        for s in taxonomy_data["skills"]:
            lookup[ts.normalize_text(s["name"])] = s["slug"]
            for alias in s.get("aliases", []):
                lookup[ts.normalize_text(alias)] = s["slug"]
        unresolved = [
            name
            for name in sorted(self._golden_skill_names())
            if ts.normalize_text(name) not in lookup
        ]
        assert unresolved == []


class TestSeed:
    def test_seed_is_idempotent(self, seeded_taxonomy, db_session):
        first = seeded_taxonomy
        second = ts.seed_from_json(db_session)
        assert first == second
        assert first["canonical"] >= 300

    def test_seed_result_shape(self, seeded_taxonomy):
        assert set(seeded_taxonomy) == {"canonical", "aliases", "version"}
        assert seeded_taxonomy["version"] == "1.1.0"
        assert seeded_taxonomy["aliases"] >= seeded_taxonomy["canonical"]

    def test_seed_updates_changed_canonical(self, seeded_taxonomy, db_session):
        from sqlalchemy import select

        from app.models.skill import CanonicalSkill

        skill = db_session.scalar(select(CanonicalSkill).where(CanonicalSkill.slug == "python"))
        assert skill is not None
        assert skill.taxonomy_version == "1.1.0"
        assert skill.is_active is True


class TestNormalizeSkill:
    def test_exact_canonical_name(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "Python")
        assert result["canonical"].slug == "python"
        assert result["confidence"] == 0.95
        assert result["method"] == "exact"
        assert result["needs_review"] is False
        assert result["suggestions"] == []

    def test_alias_indonesian(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "bahasa pemrograman python")
        assert result["canonical"].slug == "python"
        assert result["method"] == "alias"
        assert result["confidence"] == 0.95

    def test_alias_ml(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "ml")
        assert result["canonical"].slug == "machine-learning"
        assert result["method"] == "alias"

    def test_punctuation_is_kept_inside_words(self, seeded_taxonomy, db_session):
        for raw, slug in [
            ("C++", "cpp"),
            ("c#", "csharp"),
            (".NET", "dotnet"),
            ("Node.js", "nodejs"),
            ("ci/cd", "ci-cd"),
            ("CI/CD", "ci-cd"),
        ]:
            result = ts.normalize_skill(db_session, raw)
            assert result["canonical"] is not None and result["canonical"].slug == slug, raw

    def test_react_native_and_java_do_not_cross_match(self, seeded_taxonomy, db_session):
        assert ts.normalize_skill(db_session, "React Native")["canonical"].slug == "react-native"
        assert ts.normalize_skill(db_session, "Java")["canonical"].slug == "java"
        # Word-boundary guard: "javascript" tidak pernah jatuh ke "java".
        result = ts.normalize_skill(db_session, "javascript")
        assert result["canonical"].slug == "javascript"
        garbled = ts.normalize_skill(db_session, "javascript developer")
        assert garbled["canonical"] is None
        assert all(s["slug"] != "java" for s in garbled["suggestions"])

    def test_fuzzy_unique_accept(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "typecript")  # typo tunggal yang jelas
        assert result["canonical"].slug == "typescript"
        assert result["method"] == "fuzzy"
        assert result["confidence"] == 0.8
        assert result["needs_review"] is False

    def test_ambiguous_input_goes_to_review_with_suggestions(self, seeded_taxonomy, db_session):
        # "ui ux design" hampir sama jauhnya ke UI Design dan UX Design.
        result = ts.normalize_skill(db_session, "ui ux design")
        assert result["canonical"] is None
        assert result["method"] == "none"
        assert result["needs_review"] is True
        suggested = {s["slug"] for s in result["suggestions"]}
        assert suggested == {"ui-design", "ux-design"}
        for suggestion in result["suggestions"]:
            assert set(suggestion) == {"slug", "name", "score"}

    def test_fuzzy_not_forced_when_runner_up_close(self, seeded_taxonomy, db_session):
        # "ui ux design" di atas ambang 0.85 tetapi runner-up menyusul rapat
        # (selisih < margin 0.03) -> tidak boleh dipaksa ke salah satu kandidat.
        result = ts.normalize_skill(db_session, "ui ux design", fuzzy_threshold=0.85)
        assert result["canonical"] is None
        assert result["needs_review"] is True
        assert {s["slug"] for s in result["suggestions"]} == {"ui-design", "ux-design"}

    def test_unmatched_garbage(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "xyzzy qwop flux")
        assert result["canonical"] is None
        assert result["confidence"] == 0.0
        assert result["method"] == "none"
        assert result["needs_review"] is True
        assert result["suggestions"] == []

    def test_empty_input(self, seeded_taxonomy, db_session):
        result = ts.normalize_skill(db_session, "   ")
        assert result["canonical"] is None
        assert result["needs_review"] is True

    def test_fuzzy_threshold_param_respected(self, seeded_taxonomy, db_session):
        # Ambang 1.0 mematikan fuzzy: typo tidak pernah diterima otomatis.
        result = ts.normalize_skill(db_session, "typecript", fuzzy_threshold=1.0)
        assert result["canonical"] is None
        assert result["needs_review"] is True

    def test_every_golden_name_normalizes_to_expected_slug(self, seeded_taxonomy, db_session):
        # Sampel representatif golden set (semua nama sudah diuji resolusinya di data).
        samples = {
            "SQL": "sql",
            "Python": "python",
            "pandas": "pandas",
            "Excel": "excel",
            "Power BI": "power-bi",
            "visualisasi data": "data-visualization",
            "Flutter": "flutter",
            "Figma": "figma",
            "agile": "agile",
            "product roadmap": "product-roadmap",
            "statistika": "statistics",
            "stakeholder management": "stakeholder-management",
            "testing": "software-testing",
            "usability testing": "usability-testing",
            "wireframe": "wireframing",
        }
        for raw, slug in samples.items():
            result = ts.normalize_skill(db_session, raw)
            assert result["canonical"] is not None, raw
            assert result["canonical"].slug == slug, raw


class TestLoadAliasIndex:
    def test_includes_names_and_aliases(self, seeded_taxonomy, db_session):
        index = ts.load_alias_index(db_session)
        assert index["python"].slug == "python"
        assert index["bahasa pemrograman python"].slug == "python"
        assert index["ml"].slug == "machine-learning"
        # Satu alias hanya menunjuk satu skill kanon.
        assert len(index) >= 700

    def test_autocomplete_ranking_java_family(self, seeded_taxonomy, db_session):
        results = ts.autocomplete(db_session, "java")
        slugs = [s.slug for s in results]
        assert "java" in slugs and "javascript" in slugs
        assert slugs.index("java") < slugs.index("javascript")

    def test_autocomplete_short_query_returns_empty(self, seeded_taxonomy, db_session):
        # Kontrak: q < 2 karakter -> kosong (bukan error).
        assert ts.autocomplete(db_session, "p") == []
        assert ts.autocomplete(db_session, " ") == []


class TestSettings:
    def test_default_threshold(self):
        settings = Settings(app_env="test", secret_key="x" * 8)
        assert settings.skill_fuzzy_threshold == 0.92

    def test_threshold_bounds(self):
        with pytest.raises(ValueError):
            Settings(app_env="test", secret_key="x" * 8, skill_fuzzy_threshold=0.3)
        with pytest.raises(ValueError):
            Settings(app_env="test", secret_key="x" * 8, skill_fuzzy_threshold=1.5)
