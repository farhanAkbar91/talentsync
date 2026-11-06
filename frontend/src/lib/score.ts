/** Helper skor 0–100 — dipakai bersama halaman Kompatibilitas & Rekomendasi (M4/M6). */

export function clampPct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(100, Math.max(0, v));
}

export function formatScore(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** Tier skor menentukan warna ring/chip (≥85 hijau, 70–84 teal, 55–69 amber, <55 merah). */
export function scoreTier(score: number): {
  label: string;
  stroke: string;
  chip: string;
} {
  if (score >= 85) {
    return {
      label: "Sangat Cocok",
      stroke: "stroke-emerald-500",
      chip: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    };
  }
  if (score >= 70) {
    return {
      label: "Cocok",
      stroke: "stroke-teal-500",
      chip: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
    };
  }
  if (score >= 55) {
    return {
      label: "Cukup",
      stroke: "stroke-amber-500",
      chip: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    };
  }
  return {
    label: "Kurang",
    stroke: "stroke-red-500",
    chip: "bg-red-50 text-red-700 ring-1 ring-red-200",
  };
}
