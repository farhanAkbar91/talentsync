import { api } from "./client";
import type {
  ApplicationCreated,
  ApplicationStatus,
  AuthResponse,
  CVDoc,
  CandidateProfile,
  CandidateSkillList,
  CandidateSkillSuggestionList,
  Company,
  CompatibilityResult,
  CvExtraction,
  CvExtractionPayload,
  DiagnosisResult,
  GapResult,
  HrApplicationList,
  Job,
  JobStats,
  MeSummary,
  MyApplicationList,
  OptimizationApplyResult,
  OptimizationRow,
  OptimizationStart,
  Page,
  RankingCompareResult,
  RankingList,
  RecommendationList,
  SkillAutocompleteItem,
  SkillTaxonomy,
} from "./types";

export * from "./types";
export { api, extractErrorMessage, extractDetailedErrorMessage } from "./client";
export {
  setAccessToken,
  setUnauthorizedHandler,
  storeRefreshToken,
  readRefreshToken,
  clearRefreshToken,
} from "./client";

// --- auth ---
export async function register(payload: {
  role: string;
  full_name: string;
  email: string;
  password: string;
}): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>("/auth/register", payload);
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>("/auth/login", { email, password });
  return data;
}

export async function logout(refreshToken: string): Promise<void> {
  await api.post("/auth/logout", { refresh_token: refreshToken });
}

export async function fetchMeSummary(): Promise<MeSummary> {
  const { data } = await api.get<MeSummary>("/auth/me/summary");
  return data;
}

// --- profile ---
export async function fetchCandidateProfile(): Promise<CandidateProfile> {
  const { data } = await api.get<CandidateProfile>("/me/candidate-profile");
  return data;
}

export async function updateCandidateProfile(
  payload: Record<string, unknown>,
): Promise<CandidateProfile> {
  const { data } = await api.put<CandidateProfile>("/me/candidate-profile", payload);
  return data;
}

export async function fetchCompany(): Promise<Company> {
  const { data } = await api.get<Company>("/me/company");
  return data;
}

export async function createCompany(payload: Record<string, unknown>): Promise<Company> {
  const { data } = await api.post<Company>("/me/company", payload);
  return data;
}

export async function updateCompany(payload: Record<string, unknown>): Promise<Company> {
  const { data } = await api.put<Company>("/me/company", payload);
  return data;
}

// --- jobs ---
export interface JobQuery {
  q?: string;
  location?: string;
  employment_type?: string;
  work_mode?: string;
  status?: string;
  page?: number;
  size?: number;
}

export async function fetchPublicJobs(query: JobQuery): Promise<Page<Job>> {
  const { data } = await api.get<Page<Job>>("/jobs", { params: query });
  return data;
}

export async function fetchPublicJob(id: string): Promise<Job> {
  const { data } = await api.get<Job>(`/jobs/${id}`);
  return data;
}

export async function fetchHrJobs(query: JobQuery): Promise<Page<Job>> {
  const { data } = await api.get<Page<Job>>("/hr/jobs", { params: query });
  return data;
}

export async function fetchHrJob(id: string): Promise<Job> {
  const { data } = await api.get<Job>(`/hr/jobs/${id}`);
  return data;
}

export async function fetchHrJobStats(): Promise<JobStats> {
  const { data } = await api.get<JobStats>("/hr/jobs/stats");
  return data;
}

export async function createJob(payload: Record<string, unknown>): Promise<Job> {
  const { data } = await api.post<Job>("/hr/jobs", payload);
  return data;
}

export async function updateJob(id: string, payload: Record<string, unknown>): Promise<Job> {
  const { data } = await api.put<Job>(`/hr/jobs/${id}`, payload);
  return data;
}

export async function transitionJob(
  id: string,
  action: "publish" | "pause" | "resume" | "close",
): Promise<Job> {
  const { data } = await api.post<Job>(`/hr/jobs/${id}/${action}`);
  return data;
}

export async function archiveJob(id: string): Promise<void> {
  await api.delete(`/hr/jobs/${id}`);
}

// --- CV ---
export async function fetchCvs(): Promise<CVDoc[]> {
  const { data } = await api.get<CVDoc[]>("/cvs");
  return data;
}

export async function uploadCv(file: File): Promise<CVDoc> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<CVDoc>("/cvs", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function setPrimaryCv(id: string): Promise<CVDoc> {
  const { data } = await api.patch<CVDoc>(`/cvs/${id}/primary`);
  return data;
}

export async function deleteCv(id: string): Promise<void> {
  await api.delete(`/cvs/${id}`);
}

export async function downloadCv(id: string, filename: string): Promise<void> {
  const { data } = await api.get<Blob>(`/cvs/${id}/file`, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// --- CV ekstraksi (M1) ---
export async function getExtraction(cvId: string): Promise<CvExtraction> {
  const { data } = await api.get<CvExtraction>(`/cvs/${cvId}/extraction`);
  return data;
}

/** Kirim payload hasil review (lengkap, sudah diedit atau tidak) untuk dikonfirmasi. */
export async function confirmExtraction(
  cvId: string,
  payload: CvExtractionPayload,
): Promise<CvExtraction> {
  const { data } = await api.put<CvExtraction>(`/cvs/${cvId}/extraction/confirm`, { payload });
  return data;
}

// --- Skills terstandardisasi (M2) ---

/** Saran skill dari kamus standar (kirim hanya bila q ≥ 2 karakter). */
export async function fetchSkillAutocomplete(q: string): Promise<SkillAutocompleteItem[]> {
  const { data } = await api.get<{ items: SkillAutocompleteItem[] }>("/skills/autocomplete", {
    params: { q },
  });
  return data.items;
}

export async function fetchSkillTaxonomy(): Promise<SkillTaxonomy> {
  const { data } = await api.get<SkillTaxonomy>("/skills/taxonomy");
  return data;
}

/** Skill hasil ekstraksi & normalisasi untuk satu CV (404 bila bukan milik Anda). */
export async function fetchCvSkills(cvId: string): Promise<CandidateSkillSuggestionList> {
  const { data } = await api.get<CandidateSkillSuggestionList>(`/cvs/${cvId}/skills`);
  return data;
}

/** Terapkan skill terpilih ke profil kandidat. */
export async function applyCvSkills(
  cvId: string,
  skillIds: string[],
): Promise<{ applied: number }> {
  const { data } = await api.post<{ applied: number }>(`/cvs/${cvId}/skills/apply`, {
    skill_ids: skillIds,
  });
  return data;
}

/** Skill kandidat yang sudah diterapkan (accepted). */
export async function fetchMySkills(): Promise<CandidateSkillList> {
  const { data } = await api.get<CandidateSkillList>("/me/candidate-skills");
  return data;
}

export async function deleteMySkill(skillId: string): Promise<void> {
  await api.delete(`/me/candidate-skills/${skillId}`);
}

// --- Kompatibilitas (M4) & skill gap (M5) ---

/**
 * Skor kompatibilitas kandidat terhadap satu lowongan aktif.
 * 400 MATCH_UNAVAILABLE bila belum ada CV utama terkonfirmasi;
 * 404 bila lowongan tidak aktif / bukan milik kandidat-view.
 */
export async function fetchCompatibility(jobId: string): Promise<CompatibilityResult> {
  const { data } = await api.get<CompatibilityResult>(`/jobs/${jobId}/compatibility`);
  return data;
}

/**
 * Skill gap & rekomendasi belajar untuk satu lowongan aktif.
 * Kode error sama dengan fetchCompatibility (400 MATCH_UNAVAILABLE / 404).
 */
export async function fetchJobGap(jobId: string): Promise<GapResult> {
  const { data } = await api.get<GapResult>(`/jobs/${jobId}/gap`);
  return data;
}

// --- Rekomendasi lowongan (M6) & diagnosis CV (M7) ---

/**
 * Rekomendasi lowongan untuk CV utama terkonfirmasi (diurutkan skor DESC).
 * 400 MATCH_UNAVAILABLE bila belum ada CV utama terkonfirmasi.
 */
export async function fetchRecommendations(limit?: number): Promise<RecommendationList> {
  const { data } = await api.get<RecommendationList>("/me/recommendations", {
    params: limit === undefined ? undefined : { limit },
  });
  return data;
}

/**
 * Diagnosis kualitas CV berdasarkan aturan tetap (tanpa LLM).
 * 404 bila bukan pemilik / belum ada ekstraksi; 409 bila ekstraksi belum selesai.
 */
export async function fetchDiagnosis(cvId: string): Promise<DiagnosisResult> {
  const { data } = await api.get<DiagnosisResult>(`/cvs/${cvId}/diagnosis`);
  return data;
}

// --- Optimasi CV via LLM (M8) ---

/**
 * Mulai (atau pakai cache) pembuatan saran optimasi CV untuk satu lowongan.
 * 400 MATCH_UNAVAILABLE bila CV belum dikonfirmasi; proses berjalan async.
 */
export async function createCvOptimization(
  cvId: string,
  payload: { job_id: string; regenerate?: boolean },
): Promise<OptimizationStart> {
  const { data } = await api.post<OptimizationStart>(`/cvs/${cvId}/optimizations`, payload);
  return data;
}

/** Riwayat optimasi satu CV (terbaru lebih dulu). */
export async function fetchCvOptimizations(cvId: string): Promise<{ items: OptimizationRow[]; total: number }> {
  const { data } = await api.get<{ items: OptimizationRow[]; total: number }>(
    `/cvs/${cvId}/optimizations`,
  );
  return data;
}

/** Detail satu optimasi — dipolling selama status "generating". */
export async function fetchCvOptimization(cvId: string, optId: string): Promise<OptimizationRow> {
  const { data } = await api.get<OptimizationRow>(`/cvs/${cvId}/optimizations/${optId}`);
  return data;
}

/**
 * Terapkan saran yang diterima → CV versi baru (otomatis utama & terkonfirmasi).
 * 400 bila 0 saran diterima atau masih ada pelanggaran grounding.
 */
export async function applyCvOptimization(
  cvId: string,
  optId: string,
  decisions: Record<string, boolean>,
): Promise<OptimizationApplyResult> {
  const { data } = await api.post<OptimizationApplyResult>(
    `/cvs/${cvId}/optimizations/${optId}/apply`,
    { decisions },
  );
  return data;
}

// --- Lamaran (Applications) ---

/**
 * Kandidat melamar lowongan aktif dengan CV utamanya.
 * 409 duplicate; 400 APPLICATION_UNAVAILABLE (butuh CV utama terkonfirmasi); 404 non-aktif.
 */
export async function applyToJob(
  jobId: string,
  coverLetter?: string,
): Promise<ApplicationCreated> {
  const body = coverLetter && coverLetter.trim() !== "" ? { cover_letter: coverLetter.trim() } : {};
  const { data } = await api.post<ApplicationCreated>(`/jobs/${jobId}/apply`, body);
  return data;
}

/** Terima {items,total} ATAU array telanjang — kedua bentuk dinormalkan. */
function normalizeList<T>(data: { items?: T[] } | T[]): T[] {
  return Array.isArray(data) ? data : (data.items ?? []);
}

/** Backend memakai created_at; UI memakai applied_at/updated_at — rapikan di sini. */
interface RawApplicationItem {
  id: string;
  job_id: string;
  status: ApplicationStatus;
  cover_letter: string | null;
  created_at?: string;
  applied_at?: string;
  updated_at?: string;
}

interface RawMyApplicationItem extends RawApplicationItem {
  job_title: string;
  company: string | null;
}

interface RawHrApplicationItem extends RawApplicationItem {
  candidate_name: string;
  cv_id: string | null;
}

function rowTimestamps(raw: RawApplicationItem): { applied_at: string; updated_at: string } {
  const created = raw.created_at ?? "";
  return {
    applied_at: raw.applied_at ?? created,
    updated_at: raw.updated_at ?? created,
  };
}

/** Daftar lamaran milik kandidat (terbaru lebih dulu). */
export async function fetchMyApplications(): Promise<MyApplicationList> {
  const { data } = await api.get<RawMyApplicationItem[] | { items: RawMyApplicationItem[] }>(
    "/applications/mine",
  );
  const items = normalizeList(data).map((raw) => ({
    id: raw.id,
    job_id: raw.job_id,
    job_title: raw.job_title,
    company: raw.company ?? "",
    status: raw.status,
    cover_letter: raw.cover_letter,
    ...rowTimestamps(raw),
  }));
  return { items, total: items.length };
}

/** Daftar pelamar satu lowongan (HR owner) — GET /applications/job/{job_id}. */
export async function fetchHrJobApplications(jobId: string): Promise<HrApplicationList> {
  const { data } = await api.get<RawHrApplicationItem[] | { items: RawHrApplicationItem[] }>(
    `/applications/job/${jobId}`,
  );
  const items = normalizeList(data).map((raw) => ({
    id: raw.id,
    job_id: raw.job_id,
    candidate_name: raw.candidate_name,
    cv_id: raw.cv_id,
    status: raw.status,
    cover_letter: raw.cover_letter,
    ...rowTimestamps(raw),
  }));
  return { items, total: items.length };
}

/** Ubah status lamaran (HR owner). Status terminal tidak dapat diubah lagi. */
export async function updateApplicationStatus(
  applicationId: string,
  status: ApplicationStatus,
): Promise<void> {
  await api.patch(`/applications/${applicationId}/status`, { status });
}

// --- Ranking kandidat (M9 — HR) ---

/** Peringkat pelamar satu lowongan; overall null (CV belum terkonfirmasi) diurutkan paling akhir. */
export async function fetchHrJobRanking(jobId: string): Promise<RankingList> {
  const { data } = await api.get<RankingList>(`/hr/jobs/${jobId}/ranking`);
  return data;
}

/** Bandingkan dua pelamar (ids = application_id, maks. 2). */
export async function fetchRankingCompare(
  jobId: string,
  ids: [string, string],
): Promise<RankingCompareResult> {
  const { data } = await api.get<RankingCompareResult>(`/hr/jobs/${jobId}/compare`, {
    params: { ids: ids.join(",") },
  });
  return data;
}
