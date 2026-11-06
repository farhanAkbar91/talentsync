/** Helper format tampilan (id-ID). */

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatSalary(
  min: number | null,
  max: number | null,
  currency: string = "IDR",
): string {
  if (!min && !max) return "Tidak ditampilkan";
  const fmt = (n: number) =>
    new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 }).format(n);
  if (min && max) return `${currency} ${fmt(min)} – ${fmt(max)} / bln`;
  if (min) return `${currency} ${fmt(min)} / bln`;
  if (max) return `hingga ${currency} ${fmt(max)} / bln`;
  return "Tidak ditampilkan";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Keyakinan dari backend bisa 0–1 atau 0–100 — rapikan ke persen bulat (M2). */
export function toConfidencePercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return value <= 1 ? Math.round(value * 100) : Math.round(value);
}

export const employmentTypeLabels: Record<string, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Kontrak",
  internship: "Internship",
  freelance: "Freelance",
};

export const workModeLabels: Record<string, string> = {
  onsite: "Onsite",
  hybrid: "Hybrid",
  remote: "Remote",
};

export const jobStatusLabels: Record<string, string> = {
  draft: "Draft",
  active: "Aktif",
  paused: "Dijeda",
  closed: "Ditutup",
  expired: "Kedaluwarsa",
  archived: "Diarsipkan",
};

export const cvStatusLabels: Record<string, string> = {
  pending: "Menunggu",
  processing: "Diproses",
  ready: "Siap",
  failed: "Gagal",
};

/** Label status lamaran (M9) — dipakai halaman kandidat & HR. */
export const applicationStatusLabels: Record<string, string> = {
  submitted: "Terkirim",
  reviewed: "Ditinjau",
  shortlisted: "Shortlist",
  hired: "Diterima",
  rejected: "Ditolak",
};
