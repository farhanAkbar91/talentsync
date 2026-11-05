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
