import { api } from "./client";
import type {
  AuthResponse,
  CVDoc,
  CandidateProfile,
  CandidateSkillList,
  CandidateSkillSuggestionList,
  Company,
  CvExtraction,
  CvExtractionPayload,
  Job,
  JobStats,
  MeSummary,
  Page,
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
