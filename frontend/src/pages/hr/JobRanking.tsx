import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  extractDetailedErrorMessage,
  fetchHrJob,
  fetchHrJobRanking,
  fetchRankingCompare,
  type MatchFactorKey,
  type MatchFactorRecord,
  type RankingCompareResult,
  type RankingRow,
} from "../../lib/api";
import { applicationStatusLabels } from "../../lib/format";
import { clampPct, formatScore, scoreTier } from "../../lib/score";
import { Alert, Button, Card, Checkbox, EmptyState, Spinner, cn } from "../../components/ui";

/**
 * M9 — Ranking Kandidat (HR owner): daftar pelamar terurut skor kecocokan
 * (GET /hr/jobs/{id}/ranking). overall null = CV belum terkonfirmasi (diposisikan
 * terakhir oleh backend, tampil redup). Pilih 2 kandidat → panel perbandingan
 * dari GET /hr/jobs/{id}/compare?ids=a,b.
 */

const MAX_SKILL_CHIPS = 5;

const FACTOR_ROWS: { key: MatchFactorKey; label: string }[] = [
  { key: "semantic", label: "Semantic" },
  { key: "skill_coverage", label: "Skill Coverage" },
  { key: "experience", label: "Pengalaman" },
  { key: "education", label: "Pendidikan" },
];

/** Bar mini satu faktor (pola visual sama dengan halaman kompatibilitas). */
function MiniFactorBar({ label, value }: { label: string; value: number }) {
  const pct = clampPct(value);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="font-medium text-slate-600">{label}</span>
        <span className="font-semibold tabular-nums text-slate-700">{formatScore(value)}</span>
      </div>
      <div
        role="img"
        aria-label={`${label}: ${formatScore(value)} dari 100`}
        className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100"
      >
        <div className="h-full rounded-full bg-primary-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function FactorBars({ factors }: { factors: MatchFactorRecord }) {
  return (
    <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
      {FACTOR_ROWS.map(({ key, label }) => (
        <MiniFactorBar key={key} label={label} value={factors?.[key] ?? 0} />
      ))}
    </div>
  );
}

function SkillChips({ skills }: { skills: string[] }) {
  const shown = skills.slice(0, MAX_SKILL_CHIPS);
  const extra = skills.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {shown.map((s) => (
        <span
          key={s}
          className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600"
        >
          {s}
        </span>
      ))}
      {extra > 0 && <span className="text-[11px] text-slate-400">+{extra} lainnya</span>}
      {skills.length === 0 && <span className="text-[11px] text-slate-400">—</span>}
    </div>
  );
}

function ScoreCell({ overall, label }: { overall: number | null; label: string | null }) {
  if (overall === null) {
    return <span className="text-sm font-medium text-slate-400">—</span>;
  }
  const tier = scoreTier(clampPct(overall));
  return (
    <div className="flex flex-col items-end gap-1">
      <span data-testid="ranking-score" className="text-2xl font-bold tabular-nums text-slate-800">
        {formatScore(overall)}
      </span>
      <span
        className={cn(
          "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
          tier.chip,
        )}
      >
        {label || tier.label}
      </span>
    </div>
  );
}

function StatusChip({ status }: { status: RankingRow["status"] }) {
  const cls: Record<RankingRow["status"], string> = {
    submitted: "bg-slate-100 text-slate-600",
    reviewed: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    shortlisted: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
    hired: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    rejected: "bg-red-50 text-red-600 ring-1 ring-red-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        cls[status],
      )}
    >
      {applicationStatusLabels[status] ?? status}
    </span>
  );
}

function RankingCard({
  row,
  rank,
  selected,
  selectable,
  onToggle,
}: {
  row: RankingRow;
  rank: number;
  selected: boolean;
  selectable: boolean;
  onToggle: (applicationId: string, next: boolean) => void;
}) {
  const unconfirmed = row.overall === null;
  return (
    <Card
      className={cn(
        "flex flex-wrap items-start gap-4",
        unconfirmed && "bg-slate-50 opacity-70",
        selected && "ring-2! ring-primary-300!",
      )}
      data-testid="ranking-row"
    >
      <div className="flex shrink-0 flex-col items-center gap-2">
        <span
          aria-label={`Peringkat ${rank}`}
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold",
            unconfirmed ? "bg-slate-200 text-slate-400" : "bg-primary-50 text-primary-700",
          )}
        >
          {rank}
        </span>
        {!unconfirmed && (
          <Checkbox
            aria-label={`Pilih ${row.candidate_name} untuk dibandingkan`}
            className="h-4.5 w-4.5"
            checked={selected}
            disabled={!selectable && !selected}
            onChange={(e) => onToggle(row.application_id, e.target.checked)}
          />
        )}
      </div>

      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-base font-semibold text-slate-800">{row.candidate_name}</span>
          <StatusChip status={row.status} />
        </div>

        {unconfirmed ? (
          <p className="text-sm text-slate-400">CV belum terkonfirmasi</p>
        ) : (
          <>
            <FactorBars factors={row.factors} />
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <SkillChips skills={row.matched_skills} />
              <span className="text-xs font-medium text-slate-600">
                Wajib {row.matched_required}/{row.total_required}
              </span>
              {row.missing_critical > 0 && (
                <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600 ring-1 ring-red-200">
                  {row.missing_critical} skill wajib tidak ada
                </span>
              )}
            </div>
          </>
        )}
      </div>

      <div className="shrink-0">
        <ScoreCell overall={row.overall} label={row.label} />
      </div>
    </Card>
  );
}

/** Kolom perbandingan: nama, skor + chip, 4 faktor, skill cocok, missing critical. */
function CompareColumn({
  side,
  title,
}: {
  side: RankingCompareResult["a"];
  title: string;
}) {
  const tier = side.overall !== null ? scoreTier(clampPct(side.overall)) : null;
  // Backend compare mengirim objek skill detail — rapikan ke nama tampilan.
  const skillNames = side.matched_skills.map((s) =>
    typeof s === "string" ? s : (s.display ?? s.name ?? ""),
  ).filter((n) => n !== "");
  return (
    <div className="space-y-3 rounded-xl bg-slate-50 p-4">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{title}</p>
      <p className="text-base font-bold text-slate-800">{side.candidate_name}</p>
      <div className="flex items-center gap-2">
        <span className="text-2xl font-bold tabular-nums text-slate-800">
          {side.overall !== null ? formatScore(side.overall) : "—"}
        </span>
        {tier && (
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
              tier.chip,
            )}
          >
            {tier.label}
          </span>
        )}
        {side.overall === null && (
          <span className="text-xs text-slate-400">CV belum terkonfirmasi</span>
        )}
      </div>
      <FactorBars factors={side.factors} />
      <div className="space-y-1.5">
        <p className="text-xs font-semibold text-slate-600">Skill cocok</p>
        <SkillChips skills={skillNames} />
      </div>
      <p className="text-xs font-medium text-slate-600">
        {side.missing_critical > 0 ? (
          <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600 ring-1 ring-red-200">
            {side.missing_critical} skill wajib tidak ada
          </span>
        ) : (
          "Semua skill wajib terpenuhi"
        )}
      </p>
    </div>
  );
}

// --- Halaman ---

export default function HrJobRankingPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const titleFromState = (location.state as { jobTitle?: string } | null)?.jobTitle ?? null;

  const [jobTitle, setJobTitle] = useState<string | null>(titleFromState);
  const [rows, setRows] = useState<RankingRow[] | null>(null);
  const [modelVersion, setModelVersion] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [compare, setCompare] = useState<RankingCompareResult | null>(null);
  const [comparing, setComparing] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setRows(null);
    setLoadError(null);
    setSelectedIds([]);
    setCompare(null);
    setCompareError(null);
    fetchHrJobRanking(id)
      .then((res) => {
        if (cancelled) return;
        setRows(res.items ?? []);
        setModelVersion(res.model_version ?? null);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(extractDetailedErrorMessage(err));
      });
    if (!titleFromState) {
      fetchHrJob(id)
        .then((job) => {
          if (!cancelled) setJobTitle(job.title);
        })
        .catch(() => undefined);
    }
    return () => {
      cancelled = true;
    };
    // titleFromState stabil per lokasi.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, reloadKey]);

  function toggleSelected(applicationId: string, next: boolean) {
    setSelectedIds((prev) => {
      if (!next) return prev.filter((x) => x !== applicationId);
      if (prev.includes(applicationId) || prev.length >= 2) return prev;
      return [...prev, applicationId];
    });
    setCompare(null);
    setCompareError(null);
  }

  const nameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of rows ?? []) map.set(row.application_id, row.candidate_name);
    return map;
  }, [rows]);

  async function handleCompare() {
    if (!id || selectedIds.length !== 2) return;
    setComparing(true);
    setCompareError(null);
    try {
      setCompare(await fetchRankingCompare(id, [selectedIds[0], selectedIds[1]]));
    } catch (err) {
      setCompareError(extractDetailedErrorMessage(err));
    } finally {
      setComparing(false);
    }
  }

  if (rows === null && !loadError) return <Spinner label="Memuat ranking…" />;

  return (
    <div className="space-y-5">
      <Link to={id ? `/hr/jobs/${id}` : "/hr/jobs"} className="text-sm font-medium text-primary-700">
        ← Kembali ke detail lowongan
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-slate-800">Ranking Kandidat</h1>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
          {jobTitle ? jobTitle : "Lowongan"}
          {modelVersion && (
            <span className="text-xs text-slate-400">· model {modelVersion}</span>
          )}
        </p>
      </div>

      {loadError && (
        <Card className="space-y-3">
          <Alert kind="error">{loadError}</Alert>
          <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
        </Card>
      )}

      {rows !== null && !loadError && rows.length === 0 && (
        <EmptyState title="Belum ada pelamar" description="Ranking muncul setelah ada lamaran masuk." />
      )}

      {rows !== null && !loadError && rows.length > 0 && (
        <div className="space-y-3" data-testid="ranking-list">
          {rows.map((row, i) => (
            <RankingCard
              key={row.application_id}
              row={row}
              rank={i + 1}
              selected={selectedIds.includes(row.application_id)}
              selectable={selectedIds.length < 2}
              onToggle={toggleSelected}
            />
          ))}
          <p className="text-xs text-slate-400">
            Kandidat dengan CV belum terkonfirmasi tidak memiliki skor dan ditempatkan paling
            akhir. Centang dua kandidat untuk membandingkan.
          </p>
        </div>
      )}

      {compareError && <Alert kind="error">{compareError}</Alert>}

      {compare && (
        <Card className="space-y-3" data-testid="compare-panel">
          <h2 className="text-sm font-semibold text-slate-700">Perbandingan Kandidat</h2>
          <div className="grid gap-3 md:grid-cols-2">
            <CompareColumn side={compare.a} title={nameById.get(selectedIds[0]) ?? "Kandidat A"} />
            <CompareColumn side={compare.b} title={nameById.get(selectedIds[1]) ?? "Kandidat B"} />
          </div>
        </Card>
      )}

      {/* Compare bar (fixed bawah) — aktif saat 2 kandidat dipilih */}
      {selectedIds.length > 0 && (
        <div className="sticky bottom-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-lg backdrop-blur">
          <p className="text-sm text-slate-600">
            {selectedIds.length} dari 2 kandidat dipilih
            {selectedIds.length === 1 && nameById.get(selectedIds[0]) && (
              <span className="font-semibold"> · {nameById.get(selectedIds[0])}</span>
            )}
          </p>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setSelectedIds([])}>
              Bersihkan
            </Button>
            <Button
              data-testid="compare-button"
              onClick={handleCompare}
              disabled={comparing || selectedIds.length !== 2}
              title={selectedIds.length !== 2 ? "Pilih dua kandidat" : undefined}
            >
              {comparing ? "Membandingkan…" : "Bandingkan"}
            </Button>
          </div>
        </div>
      )}

      <div className={cn("h-2", selectedIds.length > 0 && "h-16")} aria-hidden="true" />
    </div>
  );
}
