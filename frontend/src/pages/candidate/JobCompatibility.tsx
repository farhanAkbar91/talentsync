import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import axios from "axios";
import {
  extractDetailedErrorMessage,
  fetchCompatibility,
  fetchJobGap,
  fetchPublicJob,
  type CompatibilityResult,
  type GapResult,
  type LearningSuggestion,
  type MatchFactorKey,
  type MatchedSkill,
  type MatchType,
  type MissingSkill,
  type TopExperience,
} from "../../lib/api";
import { formatDateTime, toConfidencePercent } from "../../lib/format";
import { Alert, Button, Card, EmptyState, cn } from "../../components/ui";
import { GapMatrix, SeverityChip } from "../../components/GapMatrix";

/**
 * M4/M5 — Kompatibilitas lowongan & skill gap untuk kandidat.
 * Data: GET /jobs/{id}/compatibility + GET /jobs/{id}/gap (dijalankan paralel).
 * 400 MATCH_UNAVAILABLE → empty state edukatif (CV utama belum dikonfirmasi);
 * 404 → lowongan tidak tersedia; error lain → inline + retry.
 */

const secondaryLinkCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50";

type PageState = "loading" | "ready" | "needCv" | "notFound" | "error";

// --- Helper ---

function clampPct(v: number): number {
  if (!Number.isFinite(v)) return 0;
  return Math.min(100, Math.max(0, v));
}

function formatScore(v: number): string {
  if (!Number.isFinite(v)) return "—";
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

/** Tier skor menentukan warna ring & chip (≥85 hijau, 70–84 teal, 55–69 amber, <55 merah). */
function scoreTier(score: number): {
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

const matchTypeBadge: Record<MatchType, string> = {
  exact: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  alias: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  related: "bg-slate-100 text-slate-600 ring-1 ring-slate-200",
};

const requiredChipCls =
  "inline-flex items-center rounded-full bg-primary-600 px-2 py-0.5 text-[11px] font-semibold text-white";

const FACTOR_ROWS: { key: MatchFactorKey; label: string }[] = [
  { key: "semantic", label: "Semantic" },
  { key: "skill_coverage", label: "Skill Coverage" },
  { key: "experience", label: "Pengalaman" },
  { key: "education", label: "Pendidikan" },
];

// --- Potongan UI ---

function ScoreRing({ score }: { score: number }) {
  const pct = clampPct(score);
  const tier = scoreTier(pct);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="relative h-32 w-32 shrink-0">
      <svg
        viewBox="0 0 120 120"
        className="h-full w-full -rotate-90"
        role="img"
        aria-label={`Skor kompatibilitas ${formatScore(pct)} dari 100 — ${tier.label}`}
      >
        <circle cx="60" cy="60" r={radius} fill="none" strokeWidth="10" className="stroke-slate-100" />
        <circle
          cx="60"
          cy="60"
          r={radius}
          fill="none"
          strokeWidth="10"
          strokeLinecap="round"
          className={tier.stroke}
          strokeDasharray={`${(pct / 100) * circumference} ${circumference}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span data-testid="compat-overall" className="text-3xl font-bold tabular-nums text-slate-800">
          {formatScore(pct)}
        </span>
        <span className="text-[11px] text-slate-400">dari 100</span>
      </div>
    </div>
  );
}

function FactorBarRow({ label, value, weight }: { label: string; value: number; weight: number }) {
  const pct = clampPct(value);
  const weightPct = Math.round((Number.isFinite(weight) ? weight : 0) * 100);
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-1 text-sm">
        <span className="font-medium text-slate-700">
          {label} <span className="text-xs font-normal text-slate-400">· bobot {weightPct}%</span>
        </span>
        <span className="text-sm font-semibold tabular-nums text-slate-800">{formatScore(value)}</span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${formatScore(value)} dari 100, bobot ${weightPct}%`}
        className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
      >
        <div className="h-full rounded-full bg-primary-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MatchedSkillCard({ skill }: { skill: MatchedSkill }) {
  return (
    <li className="rounded-xl bg-slate-50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-800">{skill.display}</span>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
            matchTypeBadge[skill.match_type] ?? matchTypeBadge.related,
          )}
        >
          {skill.match_type === "exact"
            ? "Exact"
            : skill.match_type === "alias"
              ? "Alias"
              : "Related"}
        </span>
        {skill.required && <span className={requiredChipCls}>Wajib</span>}
      </div>
      {skill.evidence && skill.evidence.trim() !== "" && (
        <p className="mt-1.5 text-xs italic text-slate-400">Bukti: “{skill.evidence.trim()}”</p>
      )}
    </li>
  );
}

function MissingSkillRow({ skill }: { skill: MissingSkill }) {
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-3">
      <SeverityChip severity={skill.severity} />
      <span className="text-sm font-semibold text-slate-800">{skill.display}</span>
      {skill.required && <span className={requiredChipCls}>Wajib</span>}
    </li>
  );
}

function ExperienceRow({ exp, rank }: { exp: TopExperience; rank: number }) {
  return (
    <li className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-50 text-xs font-bold text-primary-700">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-slate-800">{exp.title}</p>
        <p className="text-xs text-slate-500">
          {exp.company}
          {exp.period ? ` · ${exp.period}` : ""}
        </p>
      </div>
      <span
        className={cn(
          "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
          toConfidencePercent(exp.relevance) >= 70
            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
            : "bg-slate-100 text-slate-600",
        )}
      >
        {toConfidencePercent(exp.relevance)}% relevan
      </span>
    </li>
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="text-sm text-slate-400">{text}</p>;
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-slate-200/70", className)} />;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-5" aria-hidden="true">
      <Card className="flex flex-wrap items-center gap-6">
        <SkeletonBlock className="h-32 w-32 rounded-full" />
        <div className="min-w-0 flex-1 space-y-3">
          <SkeletonBlock className="h-4 w-40" />
          <SkeletonBlock className="h-7 w-72" />
          <SkeletonBlock className="h-4 w-56" />
        </div>
      </Card>
      <Card className="space-y-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <SkeletonBlock className="h-4 w-48" />
            <SkeletonBlock className="h-2 w-full" />
          </div>
        ))}
      </Card>
      <div className="grid gap-5 md:grid-cols-2">
        <SkeletonBlock className="h-48" />
        <SkeletonBlock className="h-48" />
      </div>
      <span className="sr-only">Memuat hasil kompatibilitas…</span>
    </div>
  );
}

/** Rekomendasi belajar dikelompokkan per kategori: category → daftar title/provider/link. */
function LearningSuggestions({ items }: { items: LearningSuggestion[] }) {
  const grouped = new Map<string, LearningSuggestion[]>();
  for (const item of items) {
    const list = grouped.get(item.category) ?? [];
    list.push(item);
    grouped.set(item.category, list);
  }
  return (
    <div className="space-y-4">
      {[...grouped.entries()].map(([category, suggestions]) => (
        <div key={category} className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{category}</p>
          <ul className="space-y-2">
            {suggestions.map((s) => (
              <li key={`${s.title}-${s.provider}`}>
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  data-learning-item
                  className="block rounded-xl bg-slate-50 p-3 transition hover:bg-primary-50"
                >
                  <span className="text-sm font-semibold text-primary-700 underline decoration-primary-200 underline-offset-2">
                    {s.title}
                  </span>
                  <span className="ml-1 text-xs text-slate-500">— {s.provider}</span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

// --- Halaman ---

export default function JobCompatibilityPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const titleFromState = (location.state as { jobTitle?: string } | null)?.jobTitle ?? null;

  const [state, setState] = useState<PageState>("loading");
  const [compat, setCompat] = useState<CompatibilityResult | null>(null);
  const [gap, setGap] = useState<GapResult | null>(null);
  const [gapError, setGapError] = useState<string | null>(null);
  const [jobTitle, setJobTitle] = useState<string | null>(titleFromState);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setState("notFound");
      return;
    }
    setState("loading");
    setLoadError(null);
    setGapError(null);
    setCompat(null);
    setGap(null);
    setJobTitle(titleFromState);

    async function load(jobId: string, hasTitle: boolean) {
      // Kompatibilitas + gap diambil paralel; judul lowongan hanya pelengkap.
      const [compatRes, gapRes, jobRes] = await Promise.allSettled([
        fetchCompatibility(jobId),
        fetchJobGap(jobId),
        hasTitle
          ? Promise.resolve(null)
          : fetchPublicJob(jobId).then((j) => {
              return j.title;
            }),
      ]);
      if (cancelled) return;
      if (jobRes.status === "fulfilled" && typeof jobRes.value === "string") {
        setJobTitle(jobRes.value);
      }

      if (compatRes.status === "fulfilled") {
        setCompat(compatRes.value);
        if (gapRes.status === "fulfilled") {
          setGap(gapRes.value);
        } else {
          // Gagal terpisah (jarang): kompatibilitas tetap tampil, bagian gap inline error.
          setGapError(extractDetailedErrorMessage(gapRes.reason));
        }
        setState("ready");
        return;
      }

      const err = compatRes.reason;
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status === 404) {
        setState("notFound");
        return;
      }
      if (status === 400) {
        // MATCH_UNAVAILABLE — belum ada CV utama terkonfirmasi.
        setState("needCv");
        return;
      }
      setLoadError(extractDetailedErrorMessage(err));
      setState("error");
    }

    void load(id, titleFromState !== null);
    return () => {
      cancelled = true;
    };
    // titleFromState stabil per lokasi; jadi pemicu hanya id & reloadKey.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reloadKey]);

  if (state === "loading") return <LoadingSkeleton />;

  if (state === "notFound") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Kompatibilitas Lowongan</h1>
        <EmptyState
          title="Lowongan tidak ditemukan"
          description="Lowongan ini sudah tidak aktif atau tidak tersedia untuk Anda."
        />
        <div className="flex flex-wrap gap-2">
          <Link to={`/app/jobs/${id ?? ""}`} className={secondaryLinkCls}>
            Kembali ke detail lowongan
          </Link>
          <Link to="/app/jobs" className={secondaryLinkCls}>
            Cari lowongan lain
          </Link>
        </div>
      </div>
    );
  }

  if (state === "needCv") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Kompatibilitas Lowongan</h1>
        <EmptyState
          title="Aktifkan CV utama yang sudah dikonfirmasi"
          description="Pencocokan hanya memakai CV utama yang hasil ekstraksinya sudah Anda konfirmasi. Unggah atau pilih CV utama, lalu review dan konfirmasi ekstraksinya — setelah itu skor kompatibilitas bisa dihitung."
        />
        <div className="flex flex-wrap gap-2">
          <Link to="/app/cv" className={secondaryLinkCls}>
            Buka CV Saya
          </Link>
          {id && (
            <Link to={`/app/jobs/${id}`} className={secondaryLinkCls}>
              Kembali ke detail lowongan
            </Link>
          )}
        </div>
      </div>
    );
  }

  if (state === "error" || !compat) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Kompatibilitas Lowongan</h1>
        <Card className="space-y-3">
          <Alert kind="error">{loadError ?? "Terjadi kesalahan saat menghitung kompatibilitas."}</Alert>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
            {id && (
              <Link to={`/app/jobs/${id}`} className={secondaryLinkCls}>
                Kembali ke detail lowongan
              </Link>
            )}
          </div>
        </Card>
      </div>
    );
  }

  const tier = scoreTier(clampPct(compat.overall));

  return (
    <div className="space-y-5">
      {/* Header: skor keseluruhan + judul lowongan */}
      <Card className="flex flex-wrap items-center gap-6">
        <ScoreRing score={compat.overall} />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Kompatibilitas Lowongan
          </p>
          <h1 className="text-2xl font-bold text-slate-800">
            {jobTitle ?? "Kompatibilitas Lowongan"}
          </h1>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
                tier.chip,
              )}
            >
              {compat.label || tier.label}
            </span>
            <span className="text-xs text-slate-400">
              model {compat.model_version} · Dihitung {formatDateTime(compat.computed_at)}
            </span>
          </div>
        </div>
      </Card>

      {/* Faktor skor */}
      <Card className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-700">Faktor Skor</h2>
        {FACTOR_ROWS.map(({ key, label }) => (
          <FactorBarRow
            key={key}
            label={label}
            value={compat.factors?.[key] ?? 0}
            weight={compat.weights?.[key] ?? 0}
          />
        ))}
      </Card>

      {/* Skill cocok vs belum terpenuhi */}
      <div className="grid gap-5 md:grid-cols-2">
        <Card className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Skill yang Cocok</h2>
          {compat.matched_skills.length === 0 ? (
            <EmptyNote text="Belum ada skill yang cocok terdeteksi." />
          ) : (
            <ul className="space-y-2">
              {compat.matched_skills.map((s) => (
                <MatchedSkillCard key={s.name} skill={s} />
              ))}
            </ul>
          )}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-sm font-semibold text-slate-700">Skill yang Belum Terpenuhi</h2>
          {compat.missing_skills.length === 0 ? (
            <EmptyNote text="Semua skill lowongan terpenuhi. Kerja bagus!" />
          ) : (
            <ul className="space-y-2">
              {compat.missing_skills.map((s) => (
                <MissingSkillRow key={s.name} skill={s} />
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Pengalaman paling relevan */}
      <Card className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Pengalaman Paling Relevan</h2>
        {compat.top_experiences.length === 0 ? (
          <EmptyNote text="Belum ada pengalaman yang bisa diperingkat." />
        ) : (
          <ol className="divide-y divide-slate-100">
            {compat.top_experiences.map((exp, i) => (
              <ExperienceRow key={`${exp.title}-${exp.company}-${i}`} exp={exp} rank={i + 1} />
            ))}
          </ol>
        )}
      </Card>

      {/* Mengapa skor ini? */}
      <Card className="space-y-2 ring-2! ring-primary-100!">
        <h2 className="text-sm font-semibold text-slate-700">Mengapa skor ini?</h2>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
          {compat.explanation}
        </p>
        <p className="text-[11px] text-slate-400">
          Penjelasan dihasilkan aturan tetap (bukan LLM).
        </p>
      </Card>

      {/* Analisis Skill Gap (M5) */}
      <Card className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-700">Analisis Skill Gap</h2>
        {gapError && <Alert kind="error">{gapError}</Alert>}
        {gap && (
          <>
            <GapMatrix matrix={gap.matrix} />

            {gap.items.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Skill yang perlu ditingkatkan
                </h3>
                <ul className="space-y-2">
                  {gap.items.map((item) => (
                    <li key={item.name} className="rounded-xl bg-slate-50 p-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityChip severity={item.severity} />
                        <span className="text-sm font-semibold text-slate-800">{item.display}</span>
                        {item.required && <span className={requiredChipCls}>Wajib</span>}
                      </div>
                      {item.reason && <p className="mt-1 text-xs text-slate-500">{item.reason}</p>}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-slate-700">Rekomendasi belajar</h3>
              {gap.learning_suggestions.length === 0 ? (
                <EmptyNote text="Belum ada rekomendasi belajar untuk gap ini." />
              ) : (
                <LearningSuggestions items={gap.learning_suggestions} />
              )}
            </div>

            {gap.explanation && (
              <div className="space-y-1 rounded-xl bg-primary-50/60 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                  Penjelasan skill gap
                </p>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                  {gap.explanation}
                </p>
                <p className="text-[11px] text-slate-400">
                  Penjelasan dihasilkan aturan tetap (bukan LLM).
                </p>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Footer */}
      {id && (
        <div className="border-t border-slate-200 pt-4">
          <Link to={`/app/jobs/${id}`} className="text-sm font-medium text-primary-700">
            ← Kembali ke detail lowongan
          </Link>
        </div>
      )}
    </div>
  );
}
