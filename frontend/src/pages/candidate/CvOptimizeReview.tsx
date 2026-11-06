import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  applyCvOptimization,
  createCvOptimization,
  extractDetailedErrorMessage,
  fetchCvOptimization,
  type GroundingReport,
  type OptimizationRow,
  type OptimizationSuggestion,
} from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { Alert, Button, Card, Checkbox, Spinner, cn } from "../../components/ui";

/**
 * M8 — Review saran optimasi CV dari LLM (aturan grounding memvalidasi).
 * - Polling GET detail selama status "generating" (interval 2 dtk, maks 90 dtk).
 * - failed → kartu error + "Coba lagi" (POST regenerate).
 * - completed → UI review: perbandingan teks asli vs saran, keputusan per saran,
 *   lalu POST apply (hanya saran yang dicentang) → CV versi baru (otomatis
 *   terkonfirmasi & utama). CV asli tidak pernah diubah.
 */

const POLL_INTERVAL_MS = 2_000;
const POLL_MAX_MS = 90_000;

const secondaryLinkCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50";

type Phase = "loading" | "generating" | "failed" | "ready" | "applied" | "error";

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

function GroundingBadge({ report }: { report: GroundingReport | null }) {
  if (!report) return null;
  return (
    <span
      data-testid="grounding-badge"
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        report.passed
          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
          : "bg-red-50 text-red-600 ring-1 ring-red-200",
      )}
    >
      {report.passed ? "Grounding lulus" : "Ada pelanggaran"}
      <span className="ml-1 font-normal opacity-70">· {report.checked} aturan diperiksa</span>
    </span>
  );
}

/** Keputusan awal: centang semua saran KECUALI yang ditolak validator grounding. */
function initialDecisions(row: OptimizationRow): Record<string, boolean> {
  const decisions: Record<string, boolean> = {};
  const rejected = new Set((row.grounding_report?.violations ?? []).map((v) => v.suggestion_id));
  for (const s of row.suggestions ?? []) {
    decisions[s.suggestion_id] = !rejected.has(s.suggestion_id);
  }
  return decisions;
}

function violationsFor(
  report: GroundingReport | null,
  suggestionId: string,
): { rule: string; detail: string }[] {
  return (report?.violations ?? []).filter((v) => v.suggestion_id === suggestionId);
}

function SuggestionCard({
  suggestion,
  accepted,
  report,
  onToggle,
}: {
  suggestion: OptimizationSuggestion;
  accepted: boolean;
  report: GroundingReport | null;
  onToggle: (id: string, next: boolean) => void;
}) {
  const violations = violationsFor(report, suggestion.suggestion_id);
  const rejectedByValidator = violations.length > 0;
  return (
    <Card
      className={cn("space-y-3", rejectedByValidator && "ring-2! ring-red-200!")}
      data-testid="suggestion-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center rounded-full bg-primary-100 px-2 py-0.5 text-[11px] font-semibold text-primary-700">
            {suggestion.section}
          </span>
          <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
            {suggestion.change_type}
          </span>
          <span className="text-[11px] text-slate-400">sumber: {suggestion.source_ref}</span>
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-2 text-sm font-medium text-slate-700">
          <Checkbox
            checked={accepted}
            aria-label={`Terima saran ${suggestion.section}`}
            onChange={(e) => onToggle(suggestion.suggestion_id, e.target.checked)}
          />
          Terima
        </label>
      </div>

      <div className="grid gap-2 md:grid-cols-2">
        <div className="rounded-xl bg-red-50/70 p-3 ring-1 ring-red-100">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-red-400">Teks asli</p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-red-700 line-through decoration-red-300">
            {suggestion.original_text}
          </p>
        </div>
        <div className="rounded-xl bg-emerald-50/70 p-3 ring-1 ring-emerald-100">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-500">
            Saran perubahan
          </p>
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-emerald-800">
            {suggestion.suggested_text}
          </p>
        </div>
      </div>

      {suggestion.rationale && suggestion.rationale.trim() !== "" && (
        <p className="text-xs leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Alasan:</span> {suggestion.rationale}
        </p>
      )}

      {rejectedByValidator && (
        <div className="rounded-lg bg-red-50 px-3 py-2 ring-1 ring-red-200">
          <p className="text-xs font-semibold text-red-600">Ditolak validator</p>
          <ul className="mt-1 space-y-0.5">
            {violations.map((v, i) => (
              <li key={i} className="text-[11px] leading-relaxed text-red-500">
                {v.rule}
                {v.detail ? ` — ${v.detail}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

// --- Halaman ---

export default function CvOptimizeReviewPage() {
  // Param rute bernama ":id" (konsisten dengan halaman review/skills) — alias ke cvId.
  const { id: cvId, optId: optIdParam } = useParams<{ id: string; optId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const routeState = location.state as { cached?: boolean; jobTitle?: string } | null;

  const [optId, setOptId] = useState<string | null>(optIdParam ?? null);
  const [row, setRow] = useState<OptimizationRow | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, boolean>>({});
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [appliedResult, setAppliedResult] = useState<{ new_cv_id: string; applied: number } | null>(
    null,
  );
  const [regenerating, setRegenerating] = useState(false);

  const pollTimer = useRef<number | undefined>(undefined);
  const pollDeadline = useRef<number>(0);

  // Muat + polling detail optimasi.
  useEffect(() => {
    if (!cvId || !optId) return;
    let cancelled = false;

    async function tick(first: boolean) {
      if (cancelled || !cvId || !optId) return;
      try {
        const res = await fetchCvOptimization(cvId, optId);
        if (cancelled) return;
        setRow(res);
        if (res.status === "generating") {
          if (Date.now() > pollDeadline.current) {
            // Lebih dari 90 dtk — hentikan polling, tampilkan state timeout.
            setTimedOut(true);
            setPhase("error");
            return;
          }
          setPhase("generating");
          pollTimer.current = window.setTimeout(() => void tick(false), POLL_INTERVAL_MS);
          return;
        }
        if (res.status === "failed") {
          setPhase("failed");
          return;
        }
        if (res.status === "applied") {
          setPhase("applied");
          return;
        }
        setDecisions(initialDecisions(res));
        setPhase("ready");
      } catch (err) {
        if (cancelled) return;
        // Beri kesempatan satu percobaan ulang saat polling (server sesekali gagal);
        // error pada pemanggilan pertama langsung ditampilkan.
        if (!first && Date.now() <= pollDeadline.current) {
          pollTimer.current = window.setTimeout(() => void tick(false), POLL_INTERVAL_MS);
          return;
        }
        setLoadError(extractDetailedErrorMessage(err));
        setPhase("error");
      }
    }

    setPhase("loading");
    setLoadError(null);
    setTimedOut(false);
    setRow(null);
    setAppliedResult(null);
    setApplyError(null);
    pollDeadline.current = Date.now() + POLL_MAX_MS;
    void tick(true);

    return () => {
      cancelled = true;
      window.clearTimeout(pollTimer.current);
    };
  }, [cvId, optId]);

  const acceptedCount = useMemo(
    () => Object.values(decisions).filter(Boolean).length,
    [decisions],
  );

  function toggleDecision(id: string, next: boolean) {
    setDecisions((d) => ({ ...d, [id]: next }));
  }

  async function handleApply() {
    if (!cvId || !optId || applying || !row) return;
    setApplying(true);
    setApplyError(null);
    try {
      // Hanya entri yang diterima (true) yang dikirim.
      const payload: Record<string, boolean> = {};
      for (const [id, accepted] of Object.entries(decisions)) {
        if (accepted) payload[id] = true;
      }
      const res = await applyCvOptimization(cvId, optId, payload);
      setAppliedResult(res);
      setPhase("applied");
    } catch (err) {
      setApplyError(extractDetailedErrorMessage(err));
    } finally {
      setApplying(false);
    }
  }

  async function handleRegenerate() {
    if (!cvId || !row || regenerating) return;
    setRegenerating(true);
    setLoadError(null);
    try {
      const start = await createCvOptimization(cvId, {
        job_id: row.job_id,
        regenerate: true,
      });
      setOptId(start.id);
      navigate(`/app/cv/${cvId}/optimize/${start.id}`, {
        replace: true,
        state: { cached: start.cached ?? false, jobTitle: routeState?.jobTitle },
      });
    } catch (err) {
      setLoadError(extractDetailedErrorMessage(err));
      setPhase("error");
    } finally {
      setRegenerating(false);
    }
  }

  // --- State render awal ---
  if (phase === "loading") return <Spinner label="Memuat hasil optimasi…" />;

  if (phase === "generating") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Optimasi CV</h1>
        <Card>
          <Spinner label="LLM menyusun saran…" />
          <p className="text-center text-xs text-slate-400">
            Proses biasanya selesai dalam beberapa puluh detik. Halaman ini diperbarui otomatis.
          </p>
        </Card>
        <Link to="/app/cv" className={secondaryLinkCls}>
          Kembali
        </Link>
      </div>
    );
  }

  if (phase === "failed" && row) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Optimasi CV</h1>
        <Card className="space-y-3">
          <Alert kind="error">
            {row.error_message ?? "Pembuatan saran optimasi gagal. Silakan coba lagi."}
          </Alert>
          <div className="flex flex-wrap gap-2">
            <Button data-testid="optimize-retry" onClick={handleRegenerate} disabled={regenerating}>
              {regenerating ? "Menyiapkan…" : "Coba lagi"}
            </Button>
            <Link to="/app/cv" className={secondaryLinkCls}>
              Kembali
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  if (phase === "error" || !row) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Optimasi CV</h1>
        <Card className="space-y-3">
          <Alert kind="error">
            {timedOut
              ? "Pembuatan saran memakan waktu lebih dari 90 detik. Coba lagi."
              : (loadError ?? "Hasil optimasi tidak ditemukan atau bukan milik Anda.")}
          </Alert>
          <div className="flex flex-wrap gap-2">
            {(timedOut || loadError !== null) && row && (
              <Button onClick={handleRegenerate} disabled={regenerating}>
                Coba lagi
              </Button>
            )}
            <Link to="/app/cv" className={secondaryLinkCls}>
              Kembali ke CV Saya
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  const suggestions = row.suggestions ?? [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Review Optimasi CV</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Lowongan {shortId(row.job_id)}</span>
            {routeState?.jobTitle && (
              <span className="text-slate-400">· {routeState.jobTitle}</span>
            )}
            {row.llm_model && (
              <span className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-700 ring-1 ring-blue-200">
                {row.llm_model}
              </span>
            )}
            {row.prompt_version && (
              <span className="text-xs text-slate-400">prompt {row.prompt_version}</span>
            )}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <GroundingBadge report={row.grounding_report} />
          <span className="text-xs text-slate-400">
            Dibuat {formatDateTime(row.created_at)}
          </span>
        </div>
      </div>

      {routeState?.cached && (
        <Alert kind="info">Menggunakan hasil sebelumnya — tidak memanggil LLM lagi.</Alert>
      )}

      {phase === "applied" && (
        <div className="space-y-3" data-testid="optimize-applied">
          <Alert kind="success">CV versi baru dibuat.</Alert>
          <Card className="space-y-2">
            <p className="text-sm text-slate-600">
              Versi baru otomatis menjadi CV utama dan terkonfirmasi — tidak perlu review ulang
              ekstraksi.
            </p>
            {appliedResult && (
              <p className="text-xs text-slate-400">
                {appliedResult.applied} saran diterapkan · CV baru{" "}
                <span className="font-mono">{shortId(appliedResult.new_cv_id)}</span>
              </p>
            )}
            <div className="flex flex-wrap gap-2 pt-1">
              <Link to="/app/cv">
                <Button>Buka CV saya</Button>
              </Link>
              <Link to="/app/jobs" className={secondaryLinkCls}>
                Lihat lowongan lain
              </Link>
            </div>
          </Card>
        </div>
      )}

      {phase === "ready" && (
        <>
          <p className="text-sm text-slate-500">
            Pilih saran yang ingin diterapkan ke CV versi baru. Saran yang ditolak validator
            grounding tidak disarankan diterima.
          </p>
          <div className="space-y-4">
            {suggestions.length === 0 && (
              <Card>
                <p className="text-sm text-slate-400">
                  LLM tidak menemukan perubahan yang layak untuk lowongan ini.
                </p>
              </Card>
            )}
            {suggestions.map((s) => (
              <SuggestionCard
                key={s.suggestion_id}
                suggestion={s}
                accepted={decisions[s.suggestion_id] ?? false}
                report={row.grounding_report}
                onToggle={toggleDecision}
              />
            ))}
          </div>

          {applyError && <Alert kind="error">{applyError}</Alert>}

          {/* Footer aksi */}
          <div className="sticky bottom-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-lg backdrop-blur">
            <p className="text-xs leading-relaxed text-slate-400">
              Saran dari LLM divalidasi aturan grounding; CV asli tidak pernah diubah.
            </p>
            <div className="flex gap-2">
              <Link to="/app/cv" className={secondaryLinkCls}>
                Kembali
              </Link>
              <Button
                data-testid="apply-optimizations"
                onClick={handleApply}
                disabled={applying || acceptedCount === 0}
                title={acceptedCount === 0 ? "Pilih minimal satu saran" : undefined}
              >
                {applying
                  ? "Menerapkan…"
                  : `Terapkan yang dipilih (${acceptedCount})`}
              </Button>
            </div>
          </div>
        </>
      )}

      {phase === "applied" && suggestions.length > 0 && (
        <div className="space-y-4 opacity-80">
          <p className="text-sm text-slate-500">
            Keputusan tersimpan — saran yang diterima sudah menjadi bagian dari CV versi baru.
          </p>
          {suggestions.map((s) => (
            <SuggestionCard
              key={s.suggestion_id}
              suggestion={s}
              accepted={row.decisions?.[s.suggestion_id] ?? false}
              report={row.grounding_report}
              onToggle={() => undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
