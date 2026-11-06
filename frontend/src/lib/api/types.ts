/** Tipe data bersama — selaras dengan skema Pydantic backend. */

export type Role = "candidate" | "hr";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export interface Skill {
  name: string;
  required: boolean;
}

export interface CompanyBrief {
  id: string;
  name: string;
  industry: string | null;
  location: string | null;
  website: string | null;
}

export interface Job {
  id: string;
  title: string;
  company: CompanyBrief;
  description: string;
  responsibilities: string | null;
  requirements: string | null;
  skills: Skill[];
  category: string | null;
  employment_type: string;
  work_mode: string;
  seniority: string | null;
  location_text: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string;
  posted_at: string | null;
  closing_at: string | null;
  // khusus versi HR
  status?: string;
  closed_reason?: string | null;
  created_at?: string;
  updated_at?: string;
  deleted_at?: string | null;
  /** M2 — hasil pemetaan skill ke kamus standar (display-only; null/absen bila belum ada). */
  skills_normalized?: NormalizedJobSkill[] | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface EducationItem {
  school: string;
  degree?: string | null;
  field_of_study?: string | null;
  start_year?: number | null;
  end_year?: number | null;
}

export interface ExperienceItem {
  company: string;
  title: string;
  start_period?: string | null;
  end_period?: string | null;
  description?: string | null;
}

export interface CertificationItem {
  name: string;
  issuer?: string | null;
  year?: number | null;
}

export interface CandidateProfile {
  user_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  headline: string | null;
  summary: string | null;
  skills: string[];
  education: EducationItem[];
  experience: ExperienceItem[];
  certifications: CertificationItem[];
  links: Record<string, string>;
  updated_at: string;
}

export interface Company {
  id: string;
  name: string;
  description: string | null;
  industry: string | null;
  location: string | null;
  website: string | null;
  contact_email: string | null;
  created_at: string;
}

export type CvStatus = "pending" | "processing" | "ready" | "failed";

export type ExtractionStatus = "pending" | "done" | "failed";

export interface CVDoc {
  id: string;
  status: CvStatus;
  original_filename: string;
  file_size_bytes: number;
  content_sha256: string;
  is_primary: boolean;
  version: number;
  page_count: number | null;
  created_at: string;
  updated_at: string;
  /** M1 — hasil ekstraksi (opsional: null/absen saat belum ada baris ekstraksi). */
  extraction_confirmed?: boolean | null;
  extraction_status?: ExtractionStatus | null;
}

// --- Ekstraksi CV (M1 — review hasil parser) ---

export interface ExtractionContact {
  name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  links: string[];
}

export interface ExtractionExperience {
  title: string | null;
  company: string | null;
  period: string | null;
  start: string | null;
  end: string | null;
  current: boolean;
  bullets: string[];
  evidence: string;
  confidence: number;
}

export interface ExtractionEducation {
  degree: string | null;
  institution: string | null;
  field: string | null;
  years: string | null;
  gpa: number | null;
  evidence: string;
  confidence: number;
}

export interface ExtractionSkill {
  name: string;
  evidence: string;
  confidence: number;
}

export interface ExtractionCertification {
  name: string;
  issuer: string | null;
  year: number | null;
  evidence: string;
  confidence: number;
}

export interface ExtractionLanguage {
  language: string;
  level: string | null;
  evidence: string;
  confidence: number;
}

export interface ExtractionProject {
  name: string | null;
  description: string | null;
  evidence: string;
  confidence: number;
}

export interface ExtractionAward {
  text: string;
  evidence: string;
  confidence: number;
}

/** Keyakinan per bidang — kunci opsional agar UI tetap aman bila parser tak mengirim. */
export type ExtractionFieldConfidence = Partial<{
  name: number;
  email: number;
  phone: number;
  location: number;
  summary: number;
  experiences: number;
  education: number;
  skills: number;
  certifications: number;
  languages: number;
}>;

export interface CvExtractionPayload {
  parser_version: string;
  generated_at: string | null;
  contact: ExtractionContact;
  summary: string | null;
  experiences: ExtractionExperience[];
  education: ExtractionEducation[];
  skills: ExtractionSkill[];
  certifications: ExtractionCertification[];
  languages: ExtractionLanguage[];
  projects: ExtractionProject[];
  awards: ExtractionAward[];
  field_confidence: ExtractionFieldConfidence;
  needs_review: string[];
  sections_found: string[];
}

export interface CvExtraction {
  cv_id: string;
  status: ExtractionStatus;
  parser_version: string;
  payload: CvExtractionPayload | null;
  confirmed_at: string | null;
  confirmed_by: string | null;
}

// --- Skill terstandardisasi (M2 — kamus skill & normalisasi) ---

export type SkillType = "hard" | "soft";

export interface CanonicalSkill {
  slug: string;
  name: string;
  category: string;
  skill_type: SkillType;
}

export interface SkillAutocompleteItem {
  id: string;
  slug: string;
  name: string;
  category: string;
  skill_type: SkillType;
}

export interface SkillTaxonomy {
  version: string;
  categories: { name: string; count: number }[];
  total: number;
}

export interface SkillSuggestionOption {
  slug: string;
  name: string;
}

export type SkillExtractionMethod = "explicit" | "inferred" | "manual";

export type SkillStatus = "suggested" | "accepted" | "rejected";

/** Item skill hasil ekstraksi & normalisasi pada sebuah CV (milik kandidat). */
export interface CandidateSkillSuggestion {
  id: string;
  canonical: CanonicalSkill;
  raw_name: string;
  confidence: number;
  evidence: string | null;
  source_section: string | null;
  extraction_method: SkillExtractionMethod;
  status: SkillStatus;
  needs_review: boolean;
  suggestions: SkillSuggestionOption[];
}

export interface CandidateSkillSuggestionList {
  items: CandidateSkillSuggestion[];
  total: number;
}

/** Skill kandidat yang sudah diterapkan ke profil. */
export interface CandidateSkill {
  id: string;
  canonical: CanonicalSkill;
  raw_name: string;
  confidence: number;
  status: SkillStatus;
  source_section: string | null;
  extraction_method: SkillExtractionMethod;
}

export interface CandidateSkillList {
  items: CandidateSkill[];
  total: number;
}

/** Hasil normalisasi skill lowongan (display-only, khusus versi HR). */
export interface NormalizedJobSkill {
  canonical: { slug: string; name: string; category: string };
  raw_name: string;
  required: boolean;
  confidence: number;
  needs_review: boolean;
}

export interface JobStats {
  total: number;
  by_status: Record<string, number>;
}

export interface MeSummary {
  user: User;
  candidate_profile?: CandidateProfile;
  company?: Company | null;
}

// --- Kompatibilitas lowongan (M4) & skill gap (M5) ---

/** Kunci faktor skor kecocokan (bobot tiap faktor 0–1, totalnya 1). */
export type MatchFactorKey = "semantic" | "skill_coverage" | "experience" | "education";

/** Nilai faktor (0–100) beserta bobotnya — dipakai untuk factors & weights. */
export type MatchFactors = Record<MatchFactorKey, number>;

export type MatchType = "exact" | "alias" | "related";

export interface MatchedSkill {
  name: string;
  display: string;
  required: boolean;
  match_type: MatchType;
  /** Kutipan dari CV yang membuktikan skill ini; null bila tidak ada. */
  evidence: string | null;
}

export type SkillSeverity = "kritis" | "menengah" | "minor";

export interface MissingSkill {
  name: string;
  display: string;
  required: boolean;
  severity: SkillSeverity;
}

export interface TopExperience {
  title: string;
  company: string;
  period: string;
  /** Relevansi 0–1 terhadap lowongan. */
  relevance: number;
}

/** Respons 200 GET /jobs/{job_id}/compatibility. */
export interface CompatibilityResult {
  job_id: string;
  cv_id: string;
  model_version: string;
  /** Skor keseluruhan 0–100. */
  overall: number;
  label: string;
  factors: MatchFactors;
  weights: MatchFactors;
  matched_skills: MatchedSkill[];
  missing_skills: MissingSkill[];
  top_experiences: TopExperience[];
  /** Narasi deterministik (aturan tetap, bukan LLM). */
  explanation: string;
  computed_at: string;
}

// --- Rekomendasi lowongan (M6) ---

/** Satu baris rekomendasi lowongan untuk CV utama terkonfirmasi. */
export interface RecommendationItem {
  job_id: string;
  title: string;
  company: string | null;
  location: string | null;
  employment_type: string | null;
  /** Skor kemiripan 0–100 (daftar diurutkan DESC). */
  overall: number;
  label: string;
  matched_required: number;
  total_required: number;
  matched_skills: string[];
  /** Jumlah skill wajib yang belum dimiliki (untuk badge merah). */
  missing_critical: number;
  /** Penjelasan singkat deterministik (aturan tetap, bukan LLM). */
  reason: string;
}

/** Respons 200 GET /me/recommendations. 400 MATCH_UNAVAILABLE bila belum ada CV utama terkonfirmasi. */
export interface RecommendationList {
  cv_id: string;
  model_version: string;
  computed_at: string;
  total: number;
  items: RecommendationItem[];
}

// --- Diagnosis CV (M7) ---

export type DiagnosisSeverity = "penting" | "saran";

/** Satu temuan aturan tetap — strengths tanpa severity, improvements memakainya. */
export interface DiagnosisRule {
  rule_id: string;
  text: string;
  severity?: DiagnosisSeverity;
}

/**
 * Respons 200 GET /cvs/{cv_id}/diagnosis.
 * 404 bila bukan pemilik / belum ada ekstraksi; 409 bila ekstraksi belum selesai.
 */
export interface DiagnosisResult {
  cv_id: string;
  quality_score: number;
  label: string;
  strengths: DiagnosisRule[];
  improvements: DiagnosisRule[];
  computed_at: string;
}

export type GapStatus = "gap" | "met" | "surplus";

export interface GapMatrixRow {
  category: string;
  /** Target cakupan kategori (%) dari kebutuhan lowongan. */
  target: number;
  /** Cakupan kandidat (%). */
  candidate: number;
  delta: number;
  status: GapStatus;
}

export interface GapItem {
  name: string;
  display: string;
  required: boolean;
  severity: SkillSeverity;
  reason: string;
}

export interface LearningSuggestion {
  category: string;
  title: string;
  provider: string;
  url: string;
}

/** Respons 200 GET /jobs/{job_id}/gap. */
export interface GapResult {
  job_id: string;
  model_version: string;
  overall: number;
  matrix: GapMatrixRow[];
  items: GapItem[];
  learning_suggestions: LearningSuggestion[];
  explanation: string;
}
