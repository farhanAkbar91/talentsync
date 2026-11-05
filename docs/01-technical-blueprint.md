# TalentSync AI — Technical Blueprint & Planning Document

**Project:** TalentSync AI — Job Matching System Automatic by CV (ML & NLP)
**Course:** Inovasi Sistem Informasi dan Teknologi (SI-I2) — Kelompok 6, Universitas Airlangga
**Document status:** v0.1 — Draft for approval (no implementation has started)
**Date:** 4 November 2026
**Prepared by:** Engineering agent (on behalf of Kelompok 6)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Figma / UI-UX Analysis](#2-figma-uiux-analysis)
3. [Functional Requirements](#3-functional-requirements)
4. [Proposed System Architecture](#4-proposed-system-architecture)
5. [Database Schema Proposal](#5-database-schema-proposal)
6. [AI / NLP Design](#6-ai--nlp-design)
7. [Automated Data Pipeline Design](#7-automated-data-pipeline-design)
8. [MVP Scope & Innovation Value](#8-mvp-scope--innovation-value)
9. [Development Roadmap](#9-development-roadmap)
10. [Technical Risks & Mitigation](#10-technical-risks--mitigation)
11. [Decisions Requiring Approval](#11-decisions-requiring-approval)
12. [Appendix](#12-appendix)

---

## 1. Executive Summary

TalentSync AI is proposed as a **modular monolith**: a single FastAPI application with clearly separated internal modules, a React + Vite + TypeScript SPA frontend, and a single PostgreSQL database (with the `pgvector` extension for semantic search). Two auxiliary entrypoints — a scheduled job-ingestion pipeline and a small set of background tasks — live in the same codebase and share the same models. No microservices, no message broker, no heavyweight orchestration.

**AI strategy (three capabilities, all deliberately conservative):**

1. **CV extraction** — deterministic first: PyMuPDF text extraction → section segmentation → bilingual skill taxonomy matching → regex entity extraction. Output is stored as *draft* structured data that the user can review and correct in the UI before it is used for matching (human-in-the-loop parsing).
2. **Semantic matching** — a local, pretrained, multilingual sentence-transformer model (`paraphrase-multilingual-MiniLM-L12-v2`, CPU-friendly, Indonesian + English) produces embeddings; the final score is a **transparent, weighted multi-factor composite** (semantic similarity 40%, skill coverage 30%, experience relevance 20%, education fit 10%) with per-factor sub-scores, matched/missing skill chips, evidence quotes, and a template-generated explanation — matching the factor bars and skill-gap panels in the Figma design. No model training or fine-tuning.
3. **CV optimization** — an external LLM API behind a provider-agnostic adapter, **strictly evidence-grounded**: every suggested edit must reference an existing snippet of the user's CV (`source_ref`), a validator rejects edits introducing unknown employers/certifications/dates, and nothing is applied until the user approves it. The approved result becomes a **new CV version**; the original is never mutated.

**Job ingestion:** Python connector scripts for *permitted* sources only (public APIs and RSS: RemoteOK, Remotive, Arbeitnow; Adzuna/Jooble free tiers where coverage allows; Greenhouse/Lever public board JSON). **No scraping of Jobstreet, Glints, LinkedIn, or Kalibrr** — their terms prohibit it, and an academic project must be able to defend its data practices. A clearly-labeled synthetic Indonesian seed dataset provides local context for the demo. Scheduling via GitHub Actions cron (public repo = free) with Windows Task Scheduler as the local-dev path. Full lifecycle management: `posted_at / closing_at / last_seen_at`, absence from a scrape **never** closes a job by itself (3-consecutive-miss rule on *successful* runs), soft deletion everywhere.

**Honesty notes established up front:**
- The Figma URL is **not accessible** to me without authentication (verified — the fetch returns an empty shell). All design analysis below is based on the team's high-resolution canvas export (`SILIT.png`, 11792×7631 px, inspected frame-by-frame via crops now stored in `docs/design/frame-crops/`) and on the project PDF (Figures 1.4–1.10). Exact hex values, spacing, and component variants need one more input from you (Section 12).
- The design contains marketing claims (94.8% accuracy, "10 detik", 50.000+ users, "GPT-4o Optimized", "Model Semantic Match v4.2") that are **copy, not system specs**. The blueprint treats them as placeholders; the evaluation plan (Section 8.2) produces *real measured* metrics to replace them.

**Team-of-5, zero-budget MVP is feasible in ~10–12 weeks** across 8 phases (Section 9), with the matching engine + explainable skill gap + grounded CV optimization as the innovation core, each with a concrete evaluation metric.

---

## 2. Figma / UI-UX Analysis

### 2.1 Access statement (honesty first)

- ❌ **The Figma file could not be opened directly.** Figma design URLs require an authenticated browser session; the link returns an empty page shell to an unauthenticated fetcher. I am explicitly stating this rather than pretending to have inspected the live file.
- ✅ **What was inspected instead:**
  - `SILIT.png` — the team's full-canvas export (11792×7631). I cropped and read **10 frame regions** at readable resolution (kept in `docs/design/frame-crops/`).
  - The project PDF — contains high-fidelity screenshots: Landing (1.4), Registration (1.5), Login (1.6), HR Dashboard (1.7), Candidate Ranking & Semantic Matching (1.8), Detail AI Match (1.9), Skill Gap Analysis (1.10), plus the Figma link.
- ⚠️ **Still unverifiable from these sources:** exact design tokens (hex, spacing scale, font family confirmation), component variants/states (hover, disabled, focus), prototype interaction wiring, and mobile/responsive layouts (all frames are desktop). See Section 12 for what to send me.

### 2.2 Verified frame inventory (18 frames)

| # | Frame (title as designed) | Role | Key contents verified | Proposed route |
|---|---|---|---|---|
| 1 | Landing Page (light) | Public | Hero + stats (94.8% / 10 Detik / 50.000+), 6 feature cards, 7-step NLP pipeline explainer, dual-audience section, pricing (Rp 0 / Rp 149.000 / Kustom), CTA, footer | `/` |
| 2 | Landing Page (dark variant) | Public | Same, dark theme | `/` (theme) |
| 3 | Daftar ke TalentSync AI | Public | Role selection cards (Rekruter/HR vs Pencari Kerja), name, email, password + confirm + strength meter, terms checkbox, Google OAuth button | `/register` |
| 4 | Selamat Datang Kembali (Login) | Public | Role toggle, email/password, remember 30 days, forgot password link, Google Workspace button, **Demo Akses Instan** personas (Dewi Lestari — HR; Sarah Wijaya — candidate) | `/login` |
| 5 | Buat Lowongan Baru (modal) | HR | Title, department, location & type, minimum experience, **Batas Akhir Lamaran (closing date)**, **Required Skills (Pembobotan 60%)** + **Preferred Skills (40%)** tag inputs, full description, Save Draft / Publish. "AI Semantic Assistant — GPT-4o Optimized" banner | modal over `/hr/jobs` |
| 6 | Kelola Lowongan Pekerjaan | HR | Stat cards (12 total / 8 active / 3 draft / 1 closed), search + status/department/type/location filters, table (position + REQ-id, department, location & type, applicants + "14 Cocok >85%" progress, status badge, timeline posted/closing, actions), pagination, "Semantic NLP Engine — Coba Generator AI" banner | `/hr/jobs` |
| 7 | Dashboard Utama Rekruter | HR | 4 stat cards, priority vacancies list, "Kandidat Terbaik Minggu Ini" table, AI Matching Pipeline activity feed, Kesesenjangan Pasar (market gap) panel | `/hr/dashboard` |
| 8 | Peringkat Kandidat & Semantic Matching | HR | Model banner (v4.2, High Confidence), filter chips (score >80%, experience, education, location, availability), ranked candidate cards with 3 sub-score bars + matched/missing chips, shortlist, bottom "compare 2 candidates" bar, pagination | `/hr/jobs/:id/candidates` |
| 9 | Detail AI Match Kandidat | HR | Candidate header + actions (download CV, reject, interview notes), score ring 95%, 4 factor cards, "Mengapa… 95%?" XAI narrative, matched-skills table with evidence, skill-gap panel with interviewer note, relevant work-history with per-job match badges, education, HR notes + schedule interview | `/hr/applications/:id/match` |
| 10 | Analisis Kesenjangan Keterampilan (Skill Gap Analysis) | HR | **Mode Rekruter / Mode Pencari Kerja toggle**, overall fit 84%, readiness/surplus/deficit cards, target-vs-candidate competency matrix with surplus/gap labels, matched skills w/ % + evidence, gap cards (severity, interviewer instructions, training recommendation, effort estimate), AI decision banner (confidence), export PDF / send interview questions | `/hr/applications/:id/gap` |
| 11 | Unggah Berkas CV Pelamar | HR | Vacancy context switcher, dropzone **PDF/DOCX ≤10MB, multi-file, .ZIP**, pipeline steps 01–07 with live progress, **OCR/parse failure card with "Unggah Ulang / Input Manual Profil"**, per-file queue table (detected candidate name, size, status, match score), export extraction report JSON/CSV, continue to ranking | `/hr/cv-upload` |
| 12 | Unggah Batch CV Kandidat & Pemrosesan AI (dark) | HR | Dark variant of #11 + normalization status panel, live NLP extraction inspector (detected language bilingual ID/EN, estimated experience, education, key skills, LLM narrative, per-vacancy fit 94%) | same, dark |
| 13 | Unggah & Diagnosis CV Pribadi | Candidate (⚠ rendered in HR shell) | Dropzone (PDF/DOCX ≤10MB, bilingual, 1–2 columns), file card with parse status, CV Quality Score 88/100, Profile Strength (percentile claim), Profile Completeness 92%, **detected skills 16 hard / 6 soft "Terindeks ke Taxonomy ESCO"**, verified entity chips, strengths/improvements panels, download parsing transcript (JSON), "Generate Versi CV Baru dengan AI" | `/cv` |
| 14 | Rekomendasi Lowongan Kerja Cerdas | Candidate (⚠ rendered in HR shell) | Stats (18 matches, avg relevance 87.5%), filters (score, location, salary, type, sort by AI relevance), ranked job cards with **"Mengapa Lowongan Ini Cocok"** panel, mini factor bars, matched-skills chips, minor skill gap chip, Save / Quick Apply (1-Click), right rail: Akselerasi Karier AI (certification modules), Career Agent interview simulation, talent-pool activity | `/recommendations` |
| 15 | Candidate Home / "Rekomendasi AI" | Candidate | **Candidate top-nav: Beranda · Cari Lowongan · Rekomendasi AI · CV Builder AI · Lamaran Saya · Analisis CV · Portal Rekruter**, profile header, 4 stat cards, last-CV-diagnosis panel (strengths / recommendations), AI job recommendations, skill-gap progress rail vs target role, training material recommendations, Career Agent | `/` (candidate home) |
| 16 | Analisis Kompatibilitas Komprehensif Skill Gap (dark) | Candidate | Candidate-side deep-dive vs one target job (comprehensive compatibility breakdown) | `/jobs/:id/compatibility` |
| 17 | AI CV Builder & ATS Optimizer | Candidate | 7-step wizard (Data Pribadi → Ringkasan → Pendidikan → Pengalaman → Skills → Sertifikasi → AI Enhance), per-bullet **AI Helper & Generative Rewrite** (perbaiki/profesionalkan/ringkas/tambah metrik/optimalkan ATS), impact-phrasing suggestion card, **live ATS preview (94/100 "Lolos ATS")**, A4/mobile preview, "Unduh PDF (ATS Certified)", Harvard-format note | `/cv/builder` |
| 18 | Pricing sections (in landing variants) | Public | Rp 0 Free 30 Hari / Rp 149.000 Pro Team / Kustom Enterprise | static |

### 2.3 Navigation structures observed

**Candidate top-nav (frame 15):** `Beranda · Cari Lowongan · Rekomendasi AI · CV Builder AI · Lamaran Saya · Analisis CV` + `Portal Rekruter` link + avatar menu.

**HR sidebar — three inconsistent variants across frames (needs canonicalization — see 2.8):**
- Variant A (light crops): Dashboard, Kelola Lowongan, Unggah CV Pelamar, Peringkat & Skor Kecocokan, Analisis Skill Gap, Rekomendasi Lowongan, CV Builder AI, Pengaturan.
- Variant B (PDF Fig 1.7): Dashboard, Kelola Lowongan, Peringkat AI, Unggah CV & AI, Detail AI Match, Analisis Gap Skill, CV Builder AI, Portal Pencari Kerja, Analytics, Pengaturan.
- Variant C (dark batch upload): …, AI Candidate Ranking, Detail AI Match, Skill Gap Analysis, Recruitment Analytics, Unggah Batch CV, Pengaturan + "NLP Fetch Tokens 845 Kuota" meter.

**Public:** logo → landing; login ⇄ register; demo personas shortcut on login.

### 2.4 Route map proposal

| Route | Page | Frame(s) | Status |
|---|---|---|---|
| `/` | Landing (public) | 1, 2 | Designed |
| `/login`, `/register`, `/forgot-password` | Auth | 3, 4 | Reset flow **missing** |
| `/jobs`, `/jobs/:id`, `/jobs/:id/apply` | Candidate job search / detail / apply | — | **Missing entirely** (nav item exists) |
| `/jobs/:id/compatibility` | Candidate compatibility vs my CV | 16 | Designed (dark only) |
| `/` (auth candidate) · `/recommendations` | Candidate home · recommendations | 15, 14 | Designed |
| `/cv` · `/cv/builder` | CV upload & diagnosis · CV builder | 13, 17 | Designed |
| `/applications` | Lamaran Saya (tracking) | — | **Missing** (nav item exists) |
| `/profile` | Candidate profile edit | (partially 15) | Partial — **editor missing** |
| `/hr/dashboard` | HR dashboard | 7 | Designed |
| `/hr/jobs`, `/hr/jobs/new`, `/hr/jobs/:id/edit` | Vacancy CRUD | 6, 5 | Designed (edit = reuse modal, confirm) |
| `/hr/jobs/:id/candidates` | Ranking & semantic matching | 8 | Designed |
| `/hr/applications/:id/match`, `/gap` | Candidate detail, skill gap | 9, 10 | Designed |
| `/hr/cv-upload` | Batch CV upload for a vacancy | 11, 12 | Designed (scope decision D8) |
| `/hr/company` | Company profile management | — | **Missing** |
| `/hr/settings`, `/settings` | Settings | — | **Missing** |
| `/hr/analytics` | Analytics | — | Missing (dashboard covers basics) |

### 2.5 Reusable component inventory (for the design system)

`AppShell` variants (PublicHeader · CandidateTopnav · RecruiterSidebar+Topbar), `StatCard`, `ScoreRing` (circular % gauge), `FactorBar` (label + % + progress), `ComparisonMatrixRow` (target vs candidate + surplus/gap badge), `SkillChip` (variants: matched / missing / verified / extracted), `RankedCandidateCard` (rank badge, avatar, sub-scores, chips, CTA row), `RecommendationJobCard` (match ring, "why this matches" panel, salary, save/apply), `FilterChipBar` (applied-filters with ×), `DataTable` (+ `StatusBadge`, `Pagination`, row kebab menu), `UploadDropzone`, `FileQueueTable` (per-file status/progress/action), `PipelineStepIndicator` (numbered steps with states), `FailureAlertCard` (OCR failure w/ retry / manual input), `ModelBanner` (dark, model version + confidence), `AIExplanationPanel` (dark navy narrative panel), `WizardStepper` (7-step), `BeforeAfterSuggestionCard` (original vs AI suggestion + apply), `LivePreviewPanel` (A4 CV), `BottomSelectionBar` (bulk compare), `PricingCard`, `SectionFeatureCard`, `EmptyState` / `Skeleton` (⚠ not designed — must be created), form controls (input w/ icon, password w/ strength, select, tag input, date picker, textarea w/ toolbar).

### 2.6 Design tokens (preliminary — to confirm against Figma)

| Token | Observed approximation | Confidence |
|---|---|---|
| Primary (buttons, active nav, links) | Indigo ~`#4F46E5`, hover ~`#4338CA` | Medium |
| Primary surface / selected inputs | ~`#EEF2FF`–`#E0E7FF` | Medium |
| Page background | ~`#F8FAFC` | Medium |
| Card surface | `#FFFFFF`, radius ~12–16px, soft shadow | Medium |
| Dark surfaces (sidebar dark variants, AI panels) | Navy ~`#0B1220`–`#111827`, white text | Medium |
| Success / Danger / Warning | Emerald ~`#10B981` / Red ~`#DC2626` / Amber ~`#F59E0B` | Medium |
| Typography | Inter-like sans; bold display; semibold card titles; small muted meta text | Medium |
| Chips/badges | Fully rounded (pill); soft tinted backgrounds | High |

Exact values must be extracted from the Figma file (or from clean frame exports) before frontend build; a `tokens.css` will be the single source of truth.

### 2.7 Missing screens / workflows (must be designed or consciously de-scoped)

1. **Candidate job search & browse** (`Cari Lowongan` — nav item exists, no frame).
2. **Candidate job detail** (description, requirements, salary, apply CTA) — prerequisite of nearly every candidate flow.
3. **Apply flow** (form/confirmation; cards reference "Lamar Cepat 1-Click" but no flow is designed).
4. **Lamaran Saya** (application tracking with statuses — nav item exists, no frame).
5. **Forgot / reset password** (link exists on login).
6. **Company profile management** (HR requirement; no frame).
7. **Settings pages** (both roles; sidebar item exists).
8. **Edit vacancy** (assumed to reuse the create modal — confirm).
9. **Empty states, error pages (404/500), loading skeletons** — not designed anywhere.
10. **Notifications** (bell icon exists; page/behavior undefined).
11. **Email verification / privacy policy / terms pages** (footer links exist).
12. **Mobile / responsive layouts** — all frames are desktop.

### 2.8 Design ↔ functionality inconsistencies (to resolve before frontend build)

1. **Role-shell confusion:** candidate pages (13, 14) are drawn inside the HR shell with "HR Admin" in the topbar, while frame 15 uses the proper candidate nav. The skill-gap page (10) has a *Mode Rekruter / Mode Pencari Kerja* toggle. → Decision needed on shared vs role-specific pages (proposal in §3).
2. **Three different HR sidebars** (2.3) — a canonical navigation must be fixed (proposal in §2.4/§11 D15).
3. **File formats:** design explicitly supports **PDF + DOCX + ZIP batch**, while the brief says "Upload their CV (PDF)" and even names DOCX-format parsing as a problem to solve. → D2.
4. **LLM-in-the-loop parsing:** "ALGORITMA PARSER BERBASIS LLM", "GPT-4o Optimized", "AI Semantic Assistant" — the design implies LLM-driven parsing and JD generation. Our blueprint uses deterministic parsing with optional LLM assistance (cheaper, testable, private). → D3/D16.
5. **Marketing numbers as UI data** (94.8% accuracy, "Top 8% dari 4.250 kandidat", "50.000+", "v4.2/v4.8 engine") — must be replaced by computed values or clearly-static copy. → D13.
6. **Pricing/subscription UI** exists but payments are out of scope. → D9 (static content).
7. **Dark theme** duplicates exist for ~6 pages — doubles token/component work. → D11 (light-only MVP recommended).
8. **Features shown beyond the brief:** interview-simulation Career Agent, training-material recommendations, talent-pool activity stats, quota metering, market-gap analytics panel, HR notes & interview scheduling, messaging. → explicitly parked as post-MVP (§8.1) except where noted.
9. **Cross-role links** ("Portal Rekruter" in candidate nav; "Portal Pencari Kerja" in HR sidebar) — supported; just needs a canonical treatment.
10. **Date format** MM/DD/YYYY in frames vs Indonesian locale — standardize to DD MMM YYYY (id-ID).
11. **Positive signals adopted by this blueprint:** weighted skills 60/40 in the vacancy form (§6.3), closing date per vacancy (`closing_at`), OCR-failure handling with manual-input fallback (§6.1), bilingual ID/EN parsing (§6.2), extraction transcript export (JSON), evidence-based matched-skill cards, ESCO-style taxonomy hint (§6.2).

### 2.9 UI implementation specification (skeleton — finalized after frame verification)

- **Page/route mapping:** §2.4. **Component inventory:** §2.5.
- **Tokens:** `styles/tokens.css` + Tailwind theme extension (colors, radius, shadow, spacing, typography) — pending exact values.
- **Responsive behavior:** desktop-first per Figma; breakpoints `lg` (sidebar collapses to drawer), `md` (stat cards stack), `sm` (single column, tables → card lists). Responsive frames do not exist in Figma → we will define behavior and present it for review before build.
- **Role-specific navigation:** `PublicShell`, `CandidateShell` (top-nav per frame 15), `RecruiterShell` (sidebar per canonicalized variant).
- **Recommended frontend folder structure:** §4.4.
- **Rule:** no visual redesign without approval; deviations discovered during build (e.g., impossible layouts) will be logged in a `docs/ui-decisions.md` file for your review.

---

## 3. Functional Requirements

Convention: `FR-H-*` = Job Hunter, `FR-R-*` = HR/Recruiter, `FR-P-*` = Platform. Priority: **M** = MVP, **P** = post-MVP.

### 3.1 Feature inventory

| Module | Features | Roles | Priority |
|---|---|---|---|
| Auth & Accounts | register, login, logout, session refresh, password reset, role-based routing, demo personas | Both | M |
| Profiles | candidate profile; company profile | Both | M (company: M-lean) |
| CV Management | upload PDF, versioning, primary CV selection, download, delete (soft) | H / R | M |
| CV Extraction | parse, structure, review & correct, confidence flags, JSON transcript | H / R | M |
| Job Management (internal) | create (weighted skills), draft/publish/pause/close, edit, list w/ stats | R | M |
| Job Catalog (external) | ingested vacancies, source badges, search/filter | H (R view) | M |
| Job Search | keyword + filters (category, location, salary, type, work mode), pagination | H | M |
| Matching Engine | multi-factor score, matched/missing skills, evidence, explanation | Both | M |
| Recommendations | top-k jobs for candidate, "why" panel, filters | H | M |
| Skill Gap Analysis | competency matrix, gaps with severity + study recommendations | Both | M |
| CV Optimization | grounded suggestions, review/approve per edit, versioning, export | H | M |
| Applications | apply (internal jobs), status tracking (candidate), applicant inbox + status transitions + notes (HR) | Both | M |
| Candidate Ranking | ranked applicants per vacancy, compare ≤3, shortlist | R | M |
| Ingestion Pipeline | connectors, normalize, dedupe, upsert, expire, logs, schedule | P | M |
| Analytics | recruiter dashboard aggregates (computed) | R | M (dashboard only) |
| Extras | DOCX/ZIP upload, batch HR upload, Google OAuth, dark mode, market-gap panel, interview sim, training recs, messaging, payments | — | P |

### 3.2 Job Hunter requirements

- **FR-H-1 (M)** Register as candidate (email+password), agree to terms/PDP notice; login/logout; auto-logout on refresh-token expiry.
- **FR-H-2 (M)** Create/edit profile: headline, summary, phone, location, links (LinkedIn/GitHub/portfolio), skills, expected salary, work preferences.
- **FR-H-3 (M)** Upload CV (PDF, ≤10 MB, bilingual ID/EN); multiple CVs allowed; select primary CV; download own CV; delete (soft).
- **FR-H-4 (M)** Extraction runs automatically after upload; user reviews extracted sections (contact, skills, education, experience, certifications) and can correct any field; corrections become the canonical structured profile used by matching.
- **FR-H-5 (M)** Browse/search jobs (internal + ingested, clearly source-badged); filters: keyword, location, work mode, employment type, salary range, category; sort by date/relevance.
- **FR-H-6 (M)** Save/bookmark jobs.
- **FR-H-7 (M)** View AI recommendations: ranked by composite match score, with "why this matches" (criteria met x/y, factor bars, matched chips), refreshable on CV update.
- **FR-H-8 (M)** View per-job compatibility: overall score + factor breakdown + matched/missing skills + evidence quotes + skill-gap analysis (target vs current, with study recommendations).
- **FR-H-9 (M)** Generate AI CV optimization suggestions for a specific job; review each suggestion (side-by-side diff + rationale); accept/reject individually; approved edits create a new CV version; export approved version as PDF.
- **FR-H-10 (M)** Apply to internal jobs with a selected CV (+ optional note); one active application per job; withdraw while pending.
- **FR-H-11 (M)** Track applications: status timeline (submitted → in review → shortlisted → interview → offer → hired/rejected/withdrawn), last-updated timestamp.
- **FR-H-12 (M)** Delete account / request data deletion (PDP alignment; hard-deletes CVs and profile, retains anonymized aggregates).

### 3.3 HR / Recruiter requirements

- **FR-R-1 (M)** Register as recruiter; create/edit company profile (name, industry, description, logo, website, location); a recruiter belongs to exactly one company in MVP.
- **FR-R-2 (M)** Create vacancy with: title, department, location & work mode, employment type, min experience, **closing date**, **required skills (weight 60%)** and **preferred skills (40%)** (tag input with autocomplete from taxonomy), full description/responsibilities/qualifications, salary range (optional); save draft; publish; pause; close; edit until closed.
- **FR-R-3 (M)** Vacancy list with stats (total, active, draft, closed), filters, per-vacancy applicant count and ">85% match" count; pagination.
- **FR-R-4 (M)** View applicants per vacancy ranked by match score (ranked cards: score ring, factor bars, matched/missing chips); filter by score/experience/education/location; sort by score/date.
- **FR-R-5 (M)** Open candidate detail: extracted profile, score decomposition (factors + XAI narrative), matched skills with evidence, gap analysis with interviewer notes, relevant work history, education; download the CV file (access-controlled).
- **FR-R-6 (M)** Manage application status through the pipeline; add internal notes; rejection marks reason (optional free text).
- **FR-R-7 (M)** Select 2–3 candidates and open a side-by-side comparison (scores, factors, skills, experience).
- **FR-R-8 (M)** Dashboard with computed aggregates: active positions, applicants processed, high-match count, recent pipeline activity (recent applications/parses), weekly top candidates.
- **FR-R-9 (M)** Export: candidate skill-gap report (PDF) and extraction summaries (JSON/CSV).
- **FR-R-10 (P)** Batch-upload CVs for a vacancy (PDF/DOCX/ZIP) with per-file pipeline status and manual-input fallback on failure. *(Designed in Figma; deferred — D8.)*
- **FR-R-11 (P)** AI-assisted JD generation from title + keywords ("Coba Generator AI").

### 3.4 Platform requirements

- **FR-P-1 (M)** Ingestion pipeline per §7: ≥2 permitted connectors, normalize, dedupe, upsert, expire, log; scheduled (GitHub Actions) + manual trigger endpoint.
- **FR-P-2 (M)** External jobs display source badge and link out ("apply on original site"); internally-posted jobs accept platform applications. (D14)
- **FR-P-3 (M)** Health endpoint; structured request logging with request IDs; audit log for auth and HR status changes.
- **FR-P-4 (M)** Seed script: demo personas (Dewi Lestari / Sarah Wijaya), sample companies/vacancies, synthetic Indonesian job dataset, sample PDF CVs for testing.
- **FR-P-5 (P)** Admin page for pipeline monitoring (runs, failures, source health). MVP: CLI/SQL inspection only.

### 3.5 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Performance — job search p95 | < 500 ms |
| NFR-2 | Performance — CV upload→parsed (background) | < 30 s for ≤10 pages |
| NFR-3 | Performance — match 1 CV vs 500 jobs (embedding cache hit) | < 5 s CPU |
| NFR-4 | Performance — LLM optimization call | < 30 s, streamed status |
| NFR-5 | Security — passwords | bcrypt/argon2; JWT access (15 min) + refresh (7–30 d); rotate on use |
| NFR-6 | Security — authorization | Role checks server-side on every route; object-level checks (HR sees only own-company applications; candidate sees only own data) |
| NFR-7 | Security — files | Magic-byte + size validation, random storage names, no public serving (streamed through authorized endpoint) |
| NFR-8 | Privacy (UU PDP alignment) | Consent notice at upload; data minimization; CV hard-delete on request; access & audit logs; no PII in logs (names/emails masked) |
| NFR-9 | Reliability | All external calls (LLM, job APIs) timeout + retry + circuit-break; pipeline runs never corrupt data (transactional upserts) |
| NFR-10 | Maintainability | Modular monolith boundaries; ≥70% test coverage on services; Alembic migrations; OpenAPI documented |
| NFR-11 | Observability | Structured JSON logs with levels + run IDs; ingestion summary per run |
| NFR-12 | Portability | `docker compose up` gives full working stack (web, api, db+pgvector) on a laptop |
| NFR-13 | Budget | Rp 0: local dev + free tiers only; no paid services in MVP |
| NFR-14 | i18n | UI in Indonesian (matches design); code/docs in English; matching handles ID+EN text |
| NFR-15 | Accessibility | Semantic HTML, keyboard navigation, focus states (no formal WCAG audit in MVP) |

### 3.6 Core user workflows

**W1 — Candidate: CV → insight → apply**
Register → upload CV (PDF) → parse → review/correct extraction → browse/receive recommendations → open job → view compatibility & skill gap → (optional) generate optimization → review/approve suggestions → export optimized CV → apply with chosen CV → track status.

**W2 — Recruiter: vacancy → ranked shortlist → decision**
Register → create company → create vacancy (weighted skills, closing date) → publish → applicants apply / parse → open ranked list → filter/compare → open candidate detail (factors, evidence, gap) → set status (shortlist → interview → offer/hire/reject) → notes.

**W3 — Ingestion (scheduled, unattended)**
Trigger (cron) → per enabled connector: fetch → validate → normalize → dedupe → upsert (new/changed/touched) → mark expirations (closing date passed; 3-miss rule on successful runs) → write run summary + logs → alert on failure (log level; no destructive action).

**W4 — CV optimization (human-in-the-loop)**
Select CV + target job → engine builds grounded context (extracted CV + JD + gap analysis) → LLM returns structured edit list (each with `source_ref` + rationale) → validator screens edits (fabrication heuristics) → UI shows side-by-side diffs → user accepts/rejects per edit → applied edits produce CV version n+1 → optional PDF export.

**W5 — Demo personas (from login design)**
One-click login as Dewi (HR, populated company/vacancies/applicants) or Sarah (candidate, CV parsed + recommendations ready) — backed by seed data for grading demos.

---

## 4. Proposed System Architecture

### 4.1 High-level overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                            Client (Browser)                          │
│        React 18 + Vite + TypeScript SPA (Tailwind, TanStack Query)   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS / JSON  (REST /api/v1)
┌──────────────────────────────▼───────────────────────────────────────┐
│                     FastAPI Modular Monolith (api)                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌───────────┐  │
│  │  Auth &  │ │  Jobs &  │ │  CV &    │ │ Matching  │ │ Applic. & │  │
│  │  Users   │ │  Search  │ │ Extract  │ │ + Recs    │ │ Screening │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ └───────────┘  │
│  ┌────────────────────┐  ┌───────────────────────────────────────┐   │
│  │ CV Optimization    │  │ ai/ core: embedder, scorer, explainer │   │
│  │ (LLM adapter)      │  │ taxonomy, pdf parser                  │   │
│  └────────────────────┘  └───────────────────────────────────────┘   │
│  BackgroundTasks: parse+embed on upload · expire sweep · match batch │
└───────┬──────────────────────────────┬───────────────────────────────┘
        │ SQLAlchemy / Alembic         │ external
┌───────▼────────────────┐   ┌─────────▼──────────────┐   ┌──────────┐
│  PostgreSQL 16         │   │ LLM API (adapter:      │   │ Uploads  │
│  (+ pgvector)          │   │ Gemini/Groq/OpenAI…)   │   │ (volume) │
└───────▲────────────────┘   └────────────────────────┘   └──────────┘
        │
┌───────┴──────────────────────────────────────────────────────────────┐
│  Ingestion pipeline (same codebase, separate entrypoint:             │
│  python -m pipeline.run --source all)                                │
│  connectors → normalize → dedupe → upsert → expire → logs            │
│  Scheduled by: GitHub Actions cron (cloud) · Windows Task Scheduler  │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 Key architectural decisions (recommendation / why / alternatives / trade-offs)

**A1 — Modular monolith, not microservices.**
- *Recommend:* one deployable FastAPI app; `pipeline` and background tasks are entrypoints into the same package.
- *Why:* 5-person student team, single database, no independent scaling needs; monolith maximizes velocity and keeps AI + data + API consistent.
- *Alternatives:* microservices (deployment/ops overhead, no benefit at this scale); serverless functions (cold starts conflict with loading a 500 MB model; state management pain).
- *Trade-offs:* less isolation of failures; mitigated by module boundaries and separate entrypoints.

**A2 — Local pretrained embeddings, not an embedding API.**
- *Recommend:* `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, multilingual incl. Indonesian, ~0.5 GB, CPU-friendly, Apache-2.0).
- *Why:* Rp 0 budget, offline reliability for demos, no per-call cost, sufficient quality for short professional texts; Indonesian + English in one model matches the bilingual requirement.
- *Alternatives:* OpenAI/Cohere embeddings (better recall, but cost + network dependency + data privacy of sending CVs to third parties); `paraphrase-multilingual-mpnet-base-v2` (better quality, ~3× slower/heavier); Indonesian-specific SBERT models (e.g., IndoSBERT variants — evaluate in P8 as an upgrade path); LaBSE (longer context 512, heavier).
- *Trade-offs:* lower ceiling on semantic quality; mitigated by the multi-factor score (semantic is only 40%) and the skill-coverage factor carrying precise signal. Note: model context is short (~128 tokens) → texts are chunked and mean-pooled (§6.3).

**A3 — pgvector in PostgreSQL for job vectors; in-process cosine for candidate matching.**
- *Recommend:* store job + CV embeddings as `vector(384)` via the `pgvector` extension (official Docker image); recommendations use a single SQL KNN query; candidate↔job matches cached in `match_results`.
- *Why:* one database, no extra service; SQL-level similarity simplifies filtering + ordering; pgvector setup is one Docker image line.
- *Alternatives:* pure JSONB embeddings + numpy in app memory (fine at ≤1k jobs, but filtering/re-ranking logic lives in Python); dedicated vector DB (Qdrant/Milvus — unjustified infra).
- *Trade-offs:* pgvector adds an extension dependency (acceptable: still "just Postgres"); fallback to JSONB if extension issues arise locally.

**A4 — Deterministic-first CV parsing; LLM only as optional assist.**
- *Recommend:* PyMuPDF + heuristics + taxonomy for extraction; user reviews/corrects; LLM assist optional later (e.g., normalizing messy sections).
- *Why:* testable, free, private, debuggable; 100% LLM parsing is expensive per CV, non-deterministic, and hard to grade.
- *Alternatives:* LLM-based parsing (matches the design's "parser berbasis LLM" copy but costs/latency/privacy); cloud OCR services (paid).
- *Trade-offs:* lower extraction quality on exotic layouts → mitigated by human review step + confidence flags (design already includes "Input Manual Profil" fallback).

**A5 — Provider-agnostic LLM adapter for optimization.**
- *Recommend:* clean `LLMClient` interface; default provider with a free tier (e.g., Google Gemini Flash or Groq), configurable via env; strict JSON-schema outputs.
- *Why:* zero budget; avoids lock-in; lets you swap providers without touching domain code.
- *Alternatives:* hard-coding one provider (fragile); local LLM via Ollama (quality/speed on student hardware is a risk for structured rewriting).
- *Trade-offs:* free tiers have quota/rate limits → caching, one-call-per-generation, queued processing. → D3.

**A6 — JWT (access+refresh) with role claims; no OAuth in MVP.**
- *Why:* simplest secure path matching the design; Google OAuth button deferred (D7).
- *Alternatives:* session cookies (fine too, but JWT fits the SPA + future mobile); server sessions via Redis (extra infra).
- *Trade-offs:* token revocation complexity → short access TTL + refresh rotation.

**A7 — Files on local disk (Docker volume), streamed via authorized endpoints.**
- *Alternatives:* S3/R2/Supabase storage (post-MVP if deployed publicly).
- *Trade-offs:* not horizontally scalable — irrelevant for MVP.

**A8 — Background work via FastAPI BackgroundTasks (no broker).**
- *Why:* parse+embed of one CV is seconds of CPU; a broker (Redis/RQ/Celery) is premature.
- *Alternatives:* Celery+Redis (robust retries — post-MVP if queues grow).
- *Trade-offs:* tasks die with the process → acceptable; failed tasks are marked `failed` and re-runnable from the UI.

### 4.3 Backend module structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI factory, router mounting
│   ├── core/                    # config (pydantic-settings), security, deps, logging, errors
│   ├── db/                      # session, base, alembic/
│   ├── models/                  # SQLAlchemy: user, company, cv, job, match, application,
│   │                            #   optimization, ingestion, audit, saved_job, note
│   ├── schemas/                 # Pydantic request/response models
│   ├── api/v1/                  # routers: auth, users, companies, jobs, cvs, matches,
│   │                            #   recommendations, applications, optimizations, ingestion, health
│   ├── services/                # business logic (one service per module)
│   ├── ai/
│   │   ├── extraction/          # pdf_reader, segmenter, skill_extractor, taxonomy/*.json
│   │   ├── matching/            # embedder, scorer, explainer, calibration
│   │   └── optimization/        # llm_client, prompts, grounding_validator
│   ├── pipeline/                # connectors/ (remoteok, remotive, arbeitnow, adzuna?, rss, greenhouse),
│   │                            #   normalize.py, dedupe.py, loader.py, expire.py, quality.py,
│   │                            #   run.py (entrypoint)
│   └── tasks/                   # background task functions (on_cv_uploaded, expire_sweep)
├── scripts/                     # seed_demo_data.py, ingest_once.py, evaluate_matching.py
├── tests/                       # unit/, integration/ (dockerized Postgres), ai_eval/
├── pyproject.toml
└── Dockerfile
```

### 4.4 Frontend module structure

```
frontend/
├── src/
│   ├── app/                     # router, providers, query client
│   ├── features/
│   │   ├── auth/                # login, register, forgot-password + api
│   │   ├── jobs/                # search, detail, apply, compatibility
│   │   ├── recommendations/
│   │   ├── cv/                  # upload/diagnosis, builder, optimize-review
│   │   ├── applications/        # lamaran saya
│   │   ├── profile/
│   │   ├── recruiter/           # dashboard, jobs, candidates, match-detail, gap, company, settings
│   │   └── landing/
│   ├── components/ui/           # design-system components (§2.5)
│   ├── components/layout/       # PublicHeader, CandidateTopnav, RecruiterSidebar
│   ├── lib/                     # api client (axios + interceptors), auth store, formatters
│   ├── styles/                  # tokens.css, tailwind.config
│   └── types/                   # shared TS types (generated from OpenAPI where possible)
├── index.html · vite.config.ts · tailwind.config.ts
```

### 4.5 API integration strategy

- REST `/api/v1`, JSON; OpenAPI auto-docs (Swagger UI) doubles as the integration contract.
- **Consistent error envelope:** `{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [...], "request_id": "..."}}`; HTTP status semantics; global exception handlers.
- Frontend consumes via typed API layer generated/checked against OpenAPI schemas; TanStack Query for caching/retries; no business logic in components.
- Long-running operations (parse, embed, LLM) are async: client receives `202` + status polling endpoint (design already shows progress states).
- Versioning: path version `/v1`; breaking changes require a migration note in docs.
- No API keys in frontend; all third-party calls server-side.

### 4.6 Cross-cutting concerns

- **Config:** pydantic-settings + `.env` (never committed; `.env.example` documented). Secrets: local `.env`; GitHub Actions uses repo Secrets.
- **Logging:** structlog-style JSON logs; request-ID middleware; PII masking filter (emails/names); LLM prompts logged hashed, not verbatim (may contain CV content).
- **Validation:** Pydantic v2 strict schemas at the edge; DB CHECK constraints as the last line of defense.
- **Error handling:** domain exceptions → consistent envelope; unexpected errors logged with stack + request ID, generic message to client.
- **Migrations:** Alembic; every schema change is a reviewed migration; CI runs migrations against a fresh Postgres.

---

## 5. Database Schema Proposal

### 5.1 ERD (core)

```
users ──1:1── candidate_profiles
users ──1:*── company_members ──*:1── companies
users ──1:*── cvs (owner=candidate | uploaded_by=HR)          cvs ──self FK── parent_cv_id (versions)
cvs  ──1:1── cv_extractions          cvs ──1:*── cv_embeddings
jobs ──1:1── job_embeddings          jobs ──*:1── companies (nullable) / users (posted_by)
jobs ──*:1── ingestion_runs          ingestion_runs ──1:*── ingestion_logs
pipeline_sources ──1:*── ingestion_runs
(cvs × jobs) ──1:*── match_results   (unique per cv+job+model_version)
(cvs × jobs) ──1:*── cv_optimizations
users ──1:*── applications ──*:1── jobs ; applications ──*:1── cvs (snapshot)
applications ──1:*── application_notes
users ──1:*── saved_jobs ──*:1── jobs
users ──1:*── audit_logs
```

### 5.2 Table specifications

**users** — `id` PK; `email` CITEXT UNIQUE NOT NULL; `password_hash` NOT NULL; `full_name`; `role` CHECK('candidate','recruiter'); `is_active` BOOL DEFAULT true; `last_login_at`; `created_at`; `updated_at`.

**candidate_profiles** — `user_id` PK FK; `phone`, `headline`, `summary`, `location`, `desired_roles` JSONB, `skills` JSONB (user-curated, canonical names), `links` JSONB, `expected_salary_min/max`, `updated_at`.

**companies** — `id` PK; `name` NOT NULL; `slug` UNIQUE; `industry`, `description`, `website`, `logo_path`, `size_range`, `location`; `created_by_user_id` FK; timestamps.

**company_members** — (`company_id`,`user_id`) PK; `role_in_company` CHECK('owner','admin','member'); UNIQUE(user_id) in MVP (one company per recruiter).

**cvs** — `id` PK; `candidate_user_id` FK NULL (HR-uploaded, post-MVP); `uploaded_by_user_id` FK NOT NULL; `source` CHECK('candidate','hr_upload'); `status` CHECK('pending','processing','ready','failed'); `file_path` NOT NULL; `original_filename`; `mime_type` CHECK('application/pdf'[,docx post-MVP]); `file_size_bytes`; `content_sha256`; `parent_cv_id` FK self NULL (optimization version chain); `version` INT DEFAULT 1; `is_primary` BOOL; `deleted_at`; timestamps. UNIQUE(`candidate_user_id`,`content_sha256`). CHECK: an optimization child cannot be re-parented.

**cv_extractions** — `id` PK; `cv_id` FK UNIQUE; `payload` JSONB NOT NULL (structured: contact, skills[{name, canonical, type, evidence}], education[], experiences[], certifications[], languages[]); `raw_text` TEXT; `page_count`; `parser_version`; `confidence` NUMERIC(4,3); `needs_review` BOOL; `confirmed_at`/`confirmed_by_user_id` (canonical after user review); timestamps.

**jobs** — `id` PK; `source_type` CHECK('hr','ingest') NOT NULL; `source_name` TEXT NULL ('remoteok',…; NULL for hr); `external_id` TEXT NULL; `external_url` TEXT; `company_id` FK NULL; `company_name` NOT NULL (normalized display); `title` NOT NULL; `title_normalized`; `description` NOT NULL; `responsibilities` TEXT; `requirements` TEXT; `skills` JSONB NOT NULL DEFAULT '[]' — `[{name, canonical, required:boolean, weight:number}]` (HR form enforces 60/40); `category`; `employment_type` CHECK('full_time','part_time','contract','internship','freelance'); `work_mode` CHECK('onsite','hybrid','remote'); `seniority`; `location_text`, `city`, `country`; `salary_min`,`salary_max` NUMERIC; `salary_currency` DEFAULT 'IDR'; `salary_period`; `status` CHECK('draft','active','paused','closed','expired','archived') DEFAULT 'draft'; `closed_reason` CHECK('deadline','source_closed','unseen','manual', NULL); `posted_at` TIMESTAMPTZ; `closing_at` TIMESTAMPTZ NULL; `last_seen_at` TIMESTAMPTZ; `unseen_streak` INT DEFAULT 0; `content_hash`; `duplicate_of_id` FK self NULL; `posted_by_user_id` FK NULL; `ingest_run_id` FK NULL; `deleted_at`; timestamps.
- UNIQUE(`source_name`,`external_id`) WHERE `source_type='ingest'`
- CHECK(`salary_min` IS NULL OR `salary_max` IS NULL OR `salary_min` <= `salary_max`)

**job_embeddings / cv_embeddings** — `id` PK; FK; `model` TEXT; `text_kind` CHECK('full','skills','title_req'); `vector vector(384)` NOT NULL; `created_at`; UNIQUE(FK, model, text_kind).

**match_results** — `id` PK; `cv_id` FK; `job_id` FK; `overall` NUMERIC(5,2); `factors` JSONB `{semantic, skill_coverage, experience, education}`; `matched_skills` JSONB; `missing_skills` JSONB; `evidence` JSONB (per matched skill: quote spans from CV); `explanation` TEXT (template narrative); `model_version` TEXT; `computed_at`; UNIQUE(`cv_id`,`job_id`,`model_version`).

**applications** — `id` PK; `job_id` FK; `candidate_user_id` FK; `cv_id` FK (snapshot of submitted CV); `match_score_snapshot` NUMERIC; `status` CHECK('submitted','in_review','shortlisted','interview','offer','hired','rejected','withdrawn') DEFAULT 'submitted'; `cover_note` TEXT; `applied_at`; `decided_at`; `updated_at`; UNIQUE(`job_id`,`candidate_user_id`). FK to jobs prevents hard delete when applications exist.

**cv_optimizations** — `id` PK; `cv_id` FK; `job_id` FK; `status` CHECK('generating','ready','applied','discarded'); `suggestions` JSONB — `[{id, section, source_ref, original_text, suggested_text, rationale, validator_report, user_decision}]`; `llm_provider`, `llm_model`, `prompt_version`; `grounding_report` JSONB; `created_at`; `applied_at` (sets new cv version).

**application_notes** — `id`; `application_id` FK; `author_user_id` FK; `body`; `created_at`.

**saved_jobs** — (`candidate_user_id`,`job_id`) PK; `created_at`.

**pipeline_sources** — `id`; `name` UNIQUE; `type` CHECK('api','rss','scraper'); `enabled` BOOL; `config` JSONB; `schedule_cron`; `notes`; `last_run_at`.

**ingestion_runs** — `id`; `source_name` FK; `trigger` CHECK('cron','manual'); `status` CHECK('running','success','partial','failed'); `started_at`, `finished_at`; `fetched`,`inserted`,`updated`,`expired`,`rejected` INT; `error_summary`.

**ingestion_logs** — `id`; `run_id` FK; `ts`; `level`; `stage`; `message`; `context` JSONB.

**audit_logs** — `id`; `user_id` FK NULL; `action`; `entity_type`; `entity_id`; `context` JSONB; `created_at`.

### 5.3 Job lifecycle & soft-deletion strategy

```
INTERNAL (HR-created):  draft ──publish──► active ⇄ paused
                              active ──HR──► closed (reason=manual)
                              active ──sweep──► expired (closing_at < now, reason=deadline)
                              closed/expired ──HR──► archived (soft delete: deleted_at set)
EXTERNAL (ingested):    active ──sweep──► expired (reason=deadline | source_closed | unseen)
                              (no draft/archived: source owns the record; soft delete only)
```

Lifecycle rules (per the brief):
1. `posted_at`, `closing_at`, `last_seen_at` always maintained. External jobs without a closing date get `closing_at = posted_at + default_ttl` (configurable, e.g., 45 days) so expiration is never unbounded.
2. **Absence from one scrape ≠ closed.** On every *successful* run touching a source, jobs not re-observed get `unseen_streak += 1`; observed jobs reset to 0. Only when `unseen_streak ≥ 3` (≈ one day of misses at 8-hour runs) → `status='expired', closed_reason='unseen'`.
3. **Failed runs never mutate job statuses** — the run is logged `failed` and expiry logic is skipped for that source. Source unreachable (HTTP 5xx/timeouts) vs empty result set are distinguished in run status.
4. A closing date passing (`closing_at < now`) sets `expired (deadline)` regardless of visibility.
5. Soft deletion (`deleted_at` / `archived`) everywhere; applications keep referential integrity (FK RESTRICT on jobs). Expired jobs remain visible to candidates only in their application history; they disappear from search/recommendations.
6. Status sweeps run as a cheap DB job at the end of each ingestion run and at API startup (idempotent).

**Application lifecycle:** `submitted → in_review → shortlisted → interview → offer → hired | rejected`; `submitted | in_review` may → `withdrawn` (candidate action only); transitions restricted by role and validated server-side; every change writes `audit_logs`.

### 5.4 Indexing strategy

- `jobs`: partial index `(status, closing_at)` WHERE `deleted_at IS NULL AND status='active'`; GIN trigram on `(title, company_name)` (pg_trgm) for fuzzy search; GIN on `skills`; `(source_name, last_seen_at)`; `(city)`, `(employment_type)`, `(work_mode)`.
- `match_results`: `(job_id, overall DESC)` (ranking page), `(cv_id)` (recommendation cache).
- `cvs`: `(candidate_user_id)`, `(status)`; `applications`: `(job_id, status)`, `(candidate_user_id)`.
- `ingestion_logs`: `(run_id, ts)`; `audit_logs`: `(entity_type, entity_id)`.
- Full-text: `tsvector` column on jobs (weighted title/description) with GIN — for keyword search before/alongside semantic search.

### 5.5 Migration & data policy

- Alembic autogenerate + manual review; seed migration only via scripts (not migrations).
- Retention: CVs of rejected applications retained 6 months (configurable) then soft-deleted by sweep (PDP-aligned); audit logs 1 year.
- Backups: `pg_dump` scheduled locally (MVP); none in cloud until hosted (D12).

---

## 6. AI / NLP Design

### 6.1 CV information extraction pipeline

```
PDF bytes ─► PyMuPDF (text blocks, per-page, layout flags)
        ─► text cleaning (dehyphenate, bullet normalize, whitespace)
        ─► section segmentation (bilingual heading heuristics:
            "Pengalaman Kerja/Work Experience", "Pendidikan/Education",
            "Keahlian/Skills", "Sertifikasi/Certifications", …)
        ─► entity extraction:
            • contact: regex (email, phone ID formats, URLs, LinkedIn/GitHub)
            • skills: taxonomy alias matching (§6.2) over n-grams
              + embedding-assisted linking for unknown phrases (threshold)
            • experience: date-range parsing (ID+EN month names, ranges,
              "sekarang/present"), title/company heuristics
            • education: degree keywords (S1/S2/SMA/BSc/MSc/…), GPA regex,
              institution + years
            • certifications: keyword-led line parsing
        ─► structured payload JSON + per-field confidence + needs_review flags
        ─► stored as DRAFT  ──►  user reviews/edits in UI  ──► CONFIRMED (used by matching)
```

Design decisions:
- **Human-in-the-loop is a feature, not an apology:** the Figma design itself includes manual-input fallback and "Ekstraksi Entitas & Kata Kunci Terverifikasi" (verified entities). The confirmed extraction is the canonical matching input, which also protects matching quality from parser noise.
- Failure modes handled explicitly (per frame 11): scanned/no-text PDFs → `failed` with "unggah ulang / input manual" path; bilingual documents supported; 1–2 column layouts handled by block ordering heuristics.
- PyMuPDF is AGPL-3.0 — acceptable for this academic, open-source context (noted in §12; pdfplumber MIT is the drop-in fallback if licensing ever matters).

### 6.2 Skill taxonomy (bilingual ID/EN)

- A curated YAML/JSON taxonomy: canonical skill + aliases + optional ESCO link (e.g., `reactjs` ← ["react", "react.js", "reactjs"]; `komunikasi` ← ["communication", "soft skill komunikasi"]). Seed ≈300–500 tech + business skills; grows via alias review.
- ESCO (EU classification, free download) is used as the *reference vocabulary* for canonical grouping and hard/soft tagging — the design explicitly references "Taxonomy ESCO".
- Hard/soft classification + weighting hooks (used by skill-coverage factor and the vacancy form's 60/40 split).
- Extension path: alias review UI for HR-admin (post-MVP); for MVP, taxonomy edits are code/seed changes.

### 6.3 Semantic matching engine (multi-factor, explainable)

**Factor 1 — Semantic similarity (40%).** Chunked embedding (model context ≈128 tokens → job text split into title+skills, requirements chunks, responsibilities chunks; CV into summary, per-experience, skills) with mean pooling; cosine similarity between CV profile vector and job vector; calibrated to 0–100 via a fixed monotone mapping (tunable constants stored per `model_version`, e.g., `score = clamp((cos − 0.2)/0.6)`).

**Factor 2 — Skill coverage (30%).** Required skills (weight 60% within factor) + preferred skills (40%) — mirroring the vacancy form. Each skill matched via taxonomy canonicalization; partial credit for related skills (taxonomy `related_to` edges) at 0.5; matched/missing lists emitted with evidence quotes.

**Factor 3 — Experience relevance (20%).** `0.6 × min(years_have, years_req)/years_req` + `0.4 × max cosine(title_history_chunks, job_title_req)` (did they do this kind of work).

**Factor 4 — Education fit (10%).** Ordinal level match (exceeds=100, meets=90, one-level-below=55, unrelated=25).

**Composite:** weighted sum → 0–100; label bands matching the design: ≥85 *Sangat Cocok*, 70–84 *Cocok*, 55–69 *Cukup*, <55 *Kurang*.

**Computation strategy:** job vectors computed at publish/ingest and cached; CV vectors at confirm; per-pair scores computed on demand and cached in `match_results`; recommendations = one KNN query + re-rank with factors 2–4 over top-100 candidates. Batch recomputation triggered by CV confirmation and job edits (background task).

### 6.4 Explainability artifacts (this is the differentiator)

For every score, the API returns: factor sub-scores; matched skills (`{name, match_type: exact|synonym|related, evidence: quote from CV}`); missing skills (`{name, importance: required|preferred, severity: critical|moderate|minor}` derived from weight & gap size); top-3 supporting experiences; a template-generated narrative ("Mengapa skor X?" — deterministic Indonesian text assembled from the factors, no LLM needed → always truthful) and interviewer-focus notes (deterministic: critical gaps + verification questions). The design's dark "AI explanation" panels and the skill-gap matrix (target vs candidate with surplus/gap deltas) map 1:1 to these artifacts. Optional LLM *polish* of the narrative is post-MVP and never changes the numbers.

**Skill gap analysis** = the missing-skills structure aggregated per competency domain (taxonomy categories), rendered as the target-vs-candidate matrix (§ frame 10) with severity, recommended learning modules (static mapping from taxonomy → curated course/resource links for MVP), and estimated effort bands.

### 6.5 LLM-based CV optimization (evidence-grounded)

**Contract (JSON schema enforced):**
```
{ "edits": [ { "section": "experience|summary|skills_ordering",
               "source_ref": "<id of an existing CV bullet/line>",
               "original_text": "...", "suggested_text": "...",
               "rationale": "...", "change_type": "reword|reorder|emphasize|quantify" } ],
  "summary_note": "..." }
```

**Grounding rules (prompt + validator):**
1. Every edit MUST reference an existing `source_ref`; the validator rejects edits whose `source_ref` doesn't resolve.
2. Suggested text may only reorganize/reword/strengthen wording of the referenced content. Proper nouns (companies, institutions, certifications, degrees) appearing in `suggested_text` must exist in the extracted CV lexicon; violation → edit flagged/rejected.
3. Dates, employers, titles facts are immutable — edits touching parsed dates are blocked.
4. No new skills/certificates may be *claimed*; skills may only be re-ordered/renamed to canonical names already present.
5. The validator output (`grounding_report`) travels with the suggestions and is visible in the review UI.

**Workflow:** generation is one API call per (cv, job); results cached in `cv_optimizations`; UI shows side-by-side diffs with per-edit accept/reject; accepted set is applied → **new `cvs` row (version n+1, `parent_cv_id` chain)** → re-embed + re-match → PDF export (ReportLab) with a clean Harvard-ish template. Original CV is immutable. Every generation logs provider, model, prompt version (auditability).

**Non-goals:** the LLM never writes scores, never ranks candidates, never contacts anyone, and never mutates the original file.

### 6.6 Model selection & evaluation plan

| Capability | MVP model | Alternatives evaluated later | Metric & target |
|---|---|---|---|
| Embedding | paraphrase-multilingual-MiniLM-L12-v2 | mpnet-multilingual, IndoSBERT variants, LaBSE | Matching agreement with human labels on golden set: Spearman ≥ 0.6, nDCG@10 ≥ 0.75 (initial targets; reported honestly) |
| Extraction | PyMuPDF + taxonomy + regex | + LLM-assisted normalization | Skill extraction F1 ≥ 0.80 on annotated golden CVs (20–30 CVs, ID+EN) |
| Optimization | free-tier LLM via adapter | provider swap A/B | Groundedness: ≥95% of accepted edits pass validator; **0 fabricated credentials** in audit sample; user acceptance rate tracked |
| Explanations | deterministic templates | LLM polish | Human clarity rating in demo survey |

Golden set: synthetic CVs (generated by the team, clearly labeled) + volunteer CVs from classmates with consent; evaluation scripts live in `scripts/evaluate_matching.py` and produce a metrics report for the course paper — this is how the marketing numbers on the landing page get replaced with real ones.

---

## 7. Automated Data Pipeline Design

### 7.1 Goals & constraints

Unattended daily freshness of the external job catalog; strict lifecycle integrity; zero paid infrastructure; full auditability; and — critically — **legal defensibility** for an academic project.

### 7.2 Source strategy (proposed whitelist — D5)

| Source | Method | Permission posture | Notes |
|---|---|---|---|
| RemoteOK | Public JSON API | Permitted w/ attribution | Remote tech jobs; some ID-relevant remote roles |
| Remotive | Public JSON API | Permitted | Remote jobs |
| Arbeitnow | Public JSON API | Permitted | EU + remote |
| Adzuna API | Free-tier REST (key) | Permitted | Indonesia coverage **to be verified** before commitment |
| Jooble API | Free-tier REST (key, approval) | Permitted | Has Indonesia coverage (verify) |
| Greenhouse/Lever boards | Public per-company JSON | Permitted | Career pages of selected companies using these ATSes |
| RSS feeds | feedparser | Permitted where offered | Backup/general |
| Jobstreet / Glints / LinkedIn / Kalibrr | — | **Not scraped — ToS prohibit** | Represented by the synthetic seed set instead |

Synthetic seed dataset: ~50–100 realistic Indonesian vacancies (clearly flagged `source_name='seed'`, excluded from "live" claims) so the demo shows local salary/city context. The landing page/API will label data provenance honestly — this is a feature ("data sources & provenance" section), not a limitation.

### 7.3 Pipeline stages

```
schedule trigger
  └─ for each enabled source:
       fetch (timeout, retry ≤3, circuit breaker)
       └─ validate raw records (required fields: title, company, url/desc; else → rejected + logged)
       └─ normalize: strip HTML (BeautifulSoup), parse salary (multi-currency→IDR-normalized
          display but keep original), split location (city/country/remote), map employment type,
          extract skills from description (taxonomy), set posted_at/closing_at
       └─ dedupe:
           • intra-source: external_id (authoritative)
           • intra-source fuzzy: sha1(norm(company)+norm(title)+city) → duplicate_of
           • cross-source: deferred to post-MVP (log-only candidate duplicates)
       └─ upsert (single transaction per batch, ON CONFLICT):
           • new → INSERT (status=active, unseen_streak=0)
           • hash changed → UPDATE content fields, keep status
           • hash same → UPDATE last_seen_at only, reset unseen_streak
       └─ expiry sweep (§5.3): deadline pass; unseen_streak≥3 on successful runs only
       └─ quality summary: completeness score per record, counts → ingestion_runs
  └─ run summary row + logs; failures never mutate job state
```

### 7.4 Scheduling (zero-budget)

- **GitHub Actions (primary):** cron `0 */8 * * *` in the public repo (free for public repos); `pipeline.run` executed with `DATABASE_URL` from repo Secrets pointing at a free-tier hosted Postgres (e.g., Neon) **only if** the team opts to host the DB (D12); otherwise Actions writes a JSON/CSV artifact consumed locally. Note GH disables schedules after 60 days of repo inactivity — a keep-alive commit or manual trigger covers this.
- **Windows Task Scheduler (local dev/demo):** `.bat` → `venv\Scripts\python -m pipeline.run --source all` every 8 hours; logs to file.
- Manual trigger: authenticated `POST /api/v1/ingestion/runs` (admin) for demos.

### 7.5 Monitoring & data quality (MVP: logs + tables, no dashboards)

`ingestion_runs` gives: per-run fetched/inserted/updated/expired/rejected, duration, status, error summary. `ingestion_logs` retains per-stage WARN/ERROR with context (no PII — job data only). Data-quality gates: records failing required-field checks are counted and logged with reasons (top-N in run summary). A simple health endpoint exposes last-run status per source. (Post-MVP: admin page with charts — the "Data Quality & Pipeline Monitoring" module.)

---

## 8. MVP Scope & Innovation Value

### 8.1 MVP cut list

**IN (MVP):** everything in §3 marked M — auth+roles, profiles, PDF CV upload→extract→review, internal job CRUD w/ weighted skills + lifecycle, external catalog via ≥2 permitted connectors + full lifecycle, job search, recommendations, multi-factor match + explanations, skill-gap analysis (both roles), grounded CV optimization + versioning + PDF export, applications + status pipelines (both roles), candidate ranking + compare, recruiter dashboard (computed), ingestion scheduling + monitoring tables, demo seed data, landing (static), light theme only, Indonesian UI.

**OUT (post-MVP, with rationale):**

| Deferred | Why |
|---|---|
| DOCX / ZIP / batch HR upload | PDF covers the core loop; batch flow is a large separate pipeline (D8) |
| Google OAuth | Setup + review overhead vs value for grading (D7) |
| CV Builder from scratch (7-step wizard) | Overlaps optimization flow; big editor surface (D16) |
| Payments/pricing (functional) | Out of academic scope; static content only (D9) |
| Interview simulation, training marketplace, talent-pool stats | Impressive but peripheral; roadmap candidates |
| Market-gap analytics panel | Needs corpus analytics; post-MVP |
| Dark mode, i18n EN, messaging, notifications center, admin UI | Polish/infra, not core innovation |

### 8.2 Innovation value & evaluation (per course requirements)

The innovation claim is **system-level integration and measurable workflow improvement**, not novel algorithms:

| Rank | Capability | Innovation value | How effectiveness is evaluated |
|---|---|---|---|
| 1 | **Explainable multi-factor semantic matching + skill gap** (candidate & HR, same engine) | Core differentiator vs keyword ATS; transparency story (anti-black-box) | nDCG@10 / Spearman vs human HR ranking on golden set; % of top-10 recommended jobs marked relevant; user clarity survey |
| 2 | **Evidence-grounded LLM CV optimization with mandatory human approval** | LLM used *safely* in a high-stakes document domain; audit trail | Groundedness audit (0 fabrications), acceptance rate of suggestions, pre/post match-score delta on real CVs |
| 3 | **Automated multi-source ingestion with strict lifecycle integrity** | End-to-end data engineering story (rare in student projects) | Dedupe precision (manual audit sample), expiry correctness (test scenarios), pipeline success rate, freshness lag |
| 4 | **Dual-role closed loop** (CV→match→apply→screen→decide→feedback) | Demonstrates a complete information system, not a demo screen | Task-completion time vs manual baseline (screening time benchmark), demo-script walkthrough |

Deliverable for the course: an `EVALUATION.md` + metrics report generated by `scripts/evaluate_matching.py`, feeding the final paper with *measured* numbers (replacing design mockups like "94.8%").

---

## 9. Development Roadmap

### 9.1 Phases (≈12 weeks, parallelizable for 5 people)

| Phase | Weeks | Scope | Deliverables | Exit criteria | Depends on |
|---|---|---|---|---|---|
| **P0 Setup** | 0.5 | Repo, Docker Compose (web, api, db+pgvector), CI (lint+test), `.env` scheme, Alembic init, Tailwind + tokens bootstrap | Running skeleton; hello-world e2e | `docker compose up` works; CI green | — |
| **P1 Auth & Profiles** | 1–2 | Users, JWT, roles, candidate profile, company+members, forgot-password, demo personas seed | Auth flows in UI per frames 3–4 | Register/login/refresh/reset E2E; RBAC tests | P0 |
| **P2 Jobs core** | 1.5–2.5 (par.) | Internal job CRUD (weighted skills, closing date), lifecycle states, public search + filters + detail, saved jobs | HR jobs table (frame 6) + create modal (frame 5) + candidate search/detail (**new UI**, D-need) | Job lifecycle state machine tested; search p95 < 500 ms | P1 |
| **P3 CV extraction** | 2–3 (par.) | Upload, PyMuPDF pipeline, taxonomy v1, extraction review UI (frame 13), versioning, transcript export | Candidate can upload → review → confirm | Extraction F1 baseline measured; failure paths (scan) handled | P1 |
| **P4 Matching & recommendations** | 2–3 | Embedder, scorer, calibration, `match_results`, recommendations endpoint, candidate compatibility UI (frame 16), HR ranking UI (frame 8), candidate detail (frame 9) | The core intelligence, visible in both shells | nDCG baseline report; recommendations < 1 s (cached) | P2, P3 |
| **P5 Applications & screening** | 1.5–2 | Apply flow + **Lamaran Saya** (new UI), HR applicants + status pipeline + notes + compare, dashboard aggregates (frame 7) | Complete dual-role loop | W1+W2 workflows pass E2E | P4 |
| **P6 CV optimization** | 1.5–2 | LLM adapter, prompts, grounding validator, review/diff UI, version+export PDF | Optimize→review→export loop (frames 14/17 partial) | Groundedness audit ≥95%; 0 fabrications in sample | P4 |
| **P7 Ingestion** | 2 (par. from P2) | Connectors (≥2), normalize/dedupe/upsert/expire, logs, GH Actions + Task Scheduler, seed synthetic ID dataset | Live external catalog w/ provenance badges | 3 consecutive scheduled runs green; lifecycle rules unit-tested | P2 |
| **P8 Hardening & evaluation** | 1.5–2 | Security pass, empty/error states, perf pass, golden-set evaluation, docs (README, ADRs, EVALUATION.md), demo rehearsal | v1.0 MVP + evaluation report | All NFR targets measured & reported | all |

Milestone mapping: **M1** (end P2): browsable platform; **M2** (end P4): intelligence working both sides; **M3** (end P6): full candidate value loop; **M4** (end P8): submission-ready MVP.

### 9.2 Suggested team allocation (5 members, adjustable)

- **A — Backend core:** auth, users, companies, jobs, applications, API quality.
- **B — AI/NLP:** extraction, taxonomy, matching, explanations, evaluation scripts.
- **C — Frontend candidate:** auth UI, jobs, recommendations, CV flows, applications.
- **D — Frontend HR + design system:** shells, tokens/components, HR screens, responsive behavior.
- **E — Pipeline + QA + docs:** connectors, scheduling, seed data, test plans, evaluation runs, demo scripts.
Cross-pairing: B+A on matching API; C+D on design system from day 1.

### 9.3 Testing strategy

- **Backend:** pytest + httpx against dockerized Postgres (pgvector); unit tests for scorers/dedupe/expiry (pure functions); API integration tests per router incl. RBAC negative cases; migration test in CI.
- **AI:** golden-set scripts (extraction F1, matching nDCG, groundedness audit) run in CI nightly (local runner ok); regression thresholds gate merges into `ai/`.
- **Pipeline:** connector contract tests with recorded fixtures; normalization property tests; lifecycle scenario tests (deadline, 3-miss, failed-run).
- **Frontend:** Vitest for utils/stores; React Testing Library for forms & critical components; Playwright smoke for W1/W2 (P8).
- **Manual:** scripted demo per milestone; UAT by teammates in both roles; accessibility spot-checks (keyboard nav).

---

## 10. Technical Risks & Mitigation

| # | Risk | L | I | Mitigation |
|---|---|---|---|---|
| R1 | Legal/ethical limits on scraping Indonesian portals | High | High | Only permitted APIs/RSS; no Jobstreet/Glints/LinkedIn; synthetic ID seed; provenance labels; document compliance in report |
| R2 | LLM fabricates credentials in CV suggestions | Med | Critical | `source_ref` contract, entity-allowlist validator, per-edit approval, immutable originals, audit sampling |
| R3 | Embedding quality weaker on Indonesian text | Med | Med | Multilingual model; skill-coverage factor carries exact signal (60% of factor weight); golden-set eval; model swap path |
| R4 | PDF layout variance breaks parsing | High | Med | Block-order heuristics for 1–2 columns; confidence flags; mandatory review UI; manual-input fallback (already in design) |
| R5 | Free-tier compute limits (0.5 GB model, CPU inference) | Med | Med | MiniLM; lazy load; batched embed; cached vectors; demo on laptop; deploy local-first (D12) |
| R6 | Free LLM quota exhaustion / rate limits | Med | Med | Provider-agnostic adapter; 1 call per generation; caching; queue + graceful "try later" state |
| R7 | Dedupe false merges/splits corrupt catalog | Med | Med | Conservative keys (company+title+city), `duplicate_of` markers, manual-audit sample, log-only cross-source |
| R8 | External source outages distort lifecycle | Med | Med | Failed-run isolation (no expiry mutations), unseen-streak rule, per-source health in run summary |
| R9 | Scope creep (chat, pricing, builder, dark mode…) | High | High | §8.1 cut list; change control via §11 decision log |
| R10 | UU PDP / privacy exposure of CVs | Med | High | Consent flow, role-scoped access, audit logs, PII-free logs, delete flows, local-only storage MVP |
| R11 | Figma→code fidelity drift | Med | Med | Tokens file as single source; component inventory; UI-decision log; frame crops as reference |
| R12 | Demo-day infra failure (model load, DB) | Low | High | Seed snapshot scripts; pre-warmed vectors; offline mode for matching (local model); rehearsal in P8 |
| R13 | Team parallel-work conflicts | Med | Med | API-contract-first (OpenAPI), module ownership, weekly integration checkpoint |
| R14 | GH Actions schedule limits / secrets handling | Low | Low | Keep-alive commits; manual trigger endpoint; secrets only in GH Secrets; DB access least-privilege |

---

## 11. Decisions Requiring Approval

Each: **recommendation → alternatives → what I need from you.**

| # | Decision | Recommendation | Alternatives |
|---|---|---|---|
| **D1** | UI language | Indonesian UI (matches Figma), English code/docs | ID+EN i18n (adds effort) |
| **D2** | CV file formats | **PDF only** in MVP (brief says PDF; DOCX post-MVP) | PDF+DOCX now (design shows DOCX; doubles parser work) |
| **D3** | LLM provider for optimization | Provider-agnostic adapter; default to a free-tier provider (Gemini Flash or Groq) — you register & own the key | OpenAI/Anthropic paid; local Ollama |
| **D4** | Embedding model | `paraphrase-multilingual-MiniLM-L12-v2` local | mpnet (heavier), LaBSE, IndoSBERT (evaluated P8), embedding API |
| **D5** | Ingestion source whitelist | RemoteOK + Remotive + Arbeitnow (+Adzuna/Jooble if ID coverage verified); **no scraping** of major ID portals; synthetic ID seed set | Company boards (Greenhouse/Lever) as 3rd source; RSS-only |
| **D6** | Vector storage | pgvector via Docker image | JSONB + numpy (simpler, fine ≤1k jobs) |
| **D7** | Google OAuth | Defer post-MVP; hide button in MVP | Build now (needs Google Cloud project) |
| **D8** | HR batch CV upload (designed in Figma, in use-case diagram) | **Defer post-MVP**; MVP = candidates apply with own CVs (privacy + scope) | Include minimal single-CV HR upload |
| **D9** | Pricing sections | Keep as static marketing content, no payments | Omit from MVP |
| **D10** | Optimized CV export | PDF via ReportLab (Harvard-style template per design) | + DOCX via python-docx (post-MVP) |
| **D11** | Dark mode | Light-only MVP; tokens prepared for dark later | Ship dark variants (design exists for ~6 pages) |
| **D12** | Deployment for demo | Local Docker Compose primary; optional free-tier cloud (Neon DB + Render/Railway) if time allows | Cloud-only |
| **D13** | Marketing claims in UI | Replace mock metrics with real computed values; engine labels become our versioning (e.g., "Match Engine v1") | Keep as static copy with disclaimer |
| **D14** | External jobs & applying | Show ingested jobs in search with source badge; application happens on the original site (out-link); only HR-posted jobs accept in-platform applications | Allow in-platform "intent to apply" for external jobs |
| **D15** | Canonical HR navigation | Merge the 3 sidebar variants: Dashboard · Kelola Lowongan · Peringkat & Kecocokan · Analisis Skill Gap · Portal (public jobs) · Pengaturan (+CV upload if D8 approved) | Keep design's variant B |
| **D16** | CV Builder from scratch (frame 17) | Post-MVP; MVP = upload→optimize (reuses gap+LLM stack) | Build wizard now (large) |
| **D17** | Out-of-MVP confirmations | Messaging, interview scheduling, notifications center, market-gap panel, talent-pool stats, quota metering = post-MVP | Promote any to MVP |

**Inputs I need from you (also §12):** (1) approvals/edits on D1–D17; (2) Figma access: either enable link sharing + send 4–6 clean frame exports of the pages in §2.7 gaps (or grant a read-only personal access token so I can pull tokens via the Figma API); (3) confirmation of the LLM provider you can register; (4) any vacancies/sources you specifically want ingested.

---

## 12. Appendix

### 12.1 What I still need for pixel-accurate UI implementation

Exact design tokens (colors/type/spacing) — best via Figma file access or Dev-Mode inspection; component states (hover/focus/disabled); any mobile frames; prototype link wiring (which button goes where). The frame crops in `docs/design/frame-crops/` cover content, but not exact values.

### 12.2 License notes

PyMuPDF (AGPL-3.0) — acceptable for this academic open-source context; pdfplumber (MIT) as fallback. sentence-transformers, FastAPI, SQLAlchemy, pgvector, ReportLab, python-docx, BeautifulSoup — permissive (MIT/BSD/Apache/PostgreSQL). ESCO data — free reuse with attribution. LLM provider terms — review when D3 is chosen.

### 12.3 Reference artifacts

- Project brief PDF (Kel6_Project UTS ISIT_TalentSync AI) — Figures 1.3–1.10.
- `docs/design/frame-crops/` — 10 high-res frame crops used for this analysis.
- Figma link (requires authenticated access): `https://www.figma.com/design/b6lVoxlvyDYoX2wFNiLbYH/SILIT?node-id=0-1`

---

*End of document. Awaiting approval before any implementation begins.*
