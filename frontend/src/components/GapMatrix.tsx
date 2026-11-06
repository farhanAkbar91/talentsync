import type { GapMatrixRow, GapStatus, SkillSeverity } from "../lib/api";
import { cn } from "./ui";

/**
 * M5 — Matriks kesenjangan skill per kategori (props-driven, tanpa fetching).
 * Setiap baris: nama kategori, dua bar mini (target vs kandidat), label delta
 * (+/−) dan chip status. Bar murni visual — nilai tetap terbaca dari teks.
 */

const statusChip: Record<GapStatus, { label: string; className: string }> = {
  surplus: { label: "Surplus", className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" },
  met: { label: "Terpenuhi", className: "bg-teal-50 text-teal-700 ring-1 ring-teal-200" },
  // Gap: intensitas mengikuti besarnya delta — merah bila ≥ 40 poin, selain itu amber.
  gap: { label: "Gap", className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200" },
};

function deltaLabel(delta: number): string {
  return delta > 0 ? `+${delta}` : `${delta}`;
}

function clampPct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(100, Math.max(0, v));
}

function candidateBarClass(status: GapStatus, delta: number): string {
  if (status === "gap") return Math.abs(delta) >= 40 ? "bg-red-500" : "bg-amber-500";
  if (status === "surplus") return "bg-emerald-500";
  return "bg-primary-500";
}

function MatrixRow({ row }: { row: GapMatrixRow }) {
  const chip =
    row.status === "gap" && Math.abs(row.delta) >= 40
      ? { label: "Gap", className: "bg-red-50 text-red-700 ring-1 ring-red-200" }
      : statusChip[row.status];
  return (
    <li className="space-y-2 py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-800">{row.category}</span>
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "text-xs font-semibold tabular-nums",
              row.status === "surplus" && "text-emerald-700",
              row.status === "met" && "text-slate-500",
              row.status === "gap" && (Math.abs(row.delta) >= 40 ? "text-red-700" : "text-amber-700"),
            )}
          >
            {deltaLabel(row.delta)}
          </span>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
              chip.className,
            )}
          >
            {chip.label}
          </span>
        </span>
      </div>
      <p className="text-xs text-slate-500">
        Target: {row.target}% · Kandidat: {row.candidate}%
      </p>
      <div
        role="img"
        aria-label={`Grafik ${row.category}: target ${row.target}%, kandidat ${row.candidate}%, ${chip.label.toLowerCase()} ${deltaLabel(row.delta)}`}
        className="space-y-1"
      >
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-slate-300"
            style={{ width: `${clampPct(row.target)}%` }}
          />
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className={cn("h-full rounded-full", candidateBarClass(row.status, row.delta))}
            style={{ width: `${clampPct(row.candidate)}%` }}
          />
        </div>
      </div>
    </li>
  );
}

export function GapMatrix({ matrix }: { matrix: GapMatrixRow[] }) {
  if (matrix.length === 0) {
    return <p className="text-sm text-slate-400">Belum ada data matriks kesenjangan.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-4 text-[11px] text-slate-400" aria-hidden="true">
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-4 rounded-full bg-slate-300" /> Target lowongan
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-4 rounded-full bg-primary-500" /> Kandidat
        </span>
      </div>
      <ul className="divide-y divide-slate-100">
        {matrix.map((row) => (
          <MatrixRow key={row.category} row={row} />
        ))}
      </ul>
    </div>
  );
}

/** Chip tingkat kepentingan skill yang belum terpenuhi (dipakai lintas halaman M4/M5). */
export function SeverityChip({ severity }: { severity: SkillSeverity }) {
  const styles: Record<SkillSeverity, string> = {
    kritis: "bg-red-50 text-red-700 ring-1 ring-red-200",
    menengah: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    minor: "bg-slate-100 text-slate-600",
  };
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        styles[severity] ?? styles.minor,
      )}
    >
      {severity}
    </span>
  );
}
