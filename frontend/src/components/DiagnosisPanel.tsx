import { useEffect, useState } from "react";
import axios from "axios";
import { fetchDiagnosis, type DiagnosisResult, type DiagnosisRule } from "../lib/api";
import { clampPct } from "../lib/score";
import { Card, cn } from "./ui";

/**
 * M7 — Panel Diagnosis CV (otomatis): kualitas CV dinilai aturan tetap, tanpa LLM
 * (GET /cvs/{cv_id}/diagnosis). 409 → catatan "Ekstraksi belum selesai";
 * error lain (mis. 404 bukan pemilik / tidak ada ekstraksi) → panel disembunyikan.
 */

type PanelState = "loading" | "ready" | "pending" | "hidden";

/** Chip label kualitas: ≥80 hijau "Baik", ≥60 amber "Cukup", <60 merah "Perlu Perbaikan". */
function qualityTier(score: number): { label: string; chip: string } {
  if (score >= 80) {
    return { label: "Baik", chip: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" };
  }
  if (score >= 60) {
    return { label: "Cukup", chip: "bg-amber-50 text-amber-700 ring-1 ring-amber-200" };
  }
  return { label: "Perlu Perbaikan", chip: "bg-red-50 text-red-600 ring-1 ring-red-200" };
}

function StrengthItem({ rule }: { rule: DiagnosisRule }) {
  return (
    <li className="flex items-start gap-2">
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-[10px] font-bold text-emerald-700"
      >
        ✓
      </span>
      <span className="text-sm text-slate-700">{rule.text}</span>
    </li>
  );
}

function ImprovementItem({ rule }: { rule: DiagnosisRule }) {
  // penting → merah/amber, saran → slate.
  const severityChip =
    rule.severity === "penting"
      ? "bg-red-50 text-red-600 ring-1 ring-red-200"
      : rule.severity === "saran"
        ? "bg-slate-100 text-slate-600 ring-1 ring-slate-200"
        : "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  const severityLabel =
    rule.severity === "penting" ? "Penting" : rule.severity === "saran" ? "Saran" : "Perbaikan";
  return (
    <li className="flex items-start gap-2">
      <span
        aria-hidden="true"
        className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-amber-100 text-[10px] font-bold text-amber-700"
      >
        !
      </span>
      <span className="min-w-0 flex-1 text-sm text-slate-700">{rule.text}</span>
      <span
        className={cn(
          "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
          severityChip,
        )}
      >
        {severityLabel}
      </span>
    </li>
  );
}

export function DiagnosisPanel({ cvId }: { cvId: string | undefined }) {
  const [state, setState] = useState<PanelState>("loading");
  const [diagnosis, setDiagnosis] = useState<DiagnosisResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!cvId) {
      setState("hidden");
      return;
    }
    setState("loading");
    fetchDiagnosis(cvId)
      .then((res) => {
        if (cancelled) return;
        setDiagnosis(res);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        const status = axios.isAxiosError(err) ? err.response?.status : undefined;
        setState(status === 409 ? "pending" : "hidden");
      });
    return () => {
      cancelled = true;
    };
  }, [cvId]);

  if (state === "hidden") return null;

  if (state === "loading") {
    return (
      <Card aria-hidden="true">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-48 rounded bg-slate-200/70" />
          <div className="h-4 w-full max-w-sm rounded bg-slate-200/70" />
        </div>
      </Card>
    );
  }

  if (state === "pending") {
    return (
      <Card className="space-y-1.5">
        <h2 className="text-sm font-semibold text-slate-700">Diagnosis CV (otomatis)</h2>
        <p className="text-sm text-slate-400">Ekstraksi belum selesai.</p>
      </Card>
    );
  }

  if (!diagnosis) return null;

  const score = clampPct(diagnosis.quality_score);
  const tier = qualityTier(score);
  const hasStrengths = diagnosis.strengths.length > 0;
  const hasImprovements = diagnosis.improvements.length > 0;

  return (
    <Card className="space-y-4 ring-2! ring-primary-100!">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-baseline gap-1.5">
          <span data-testid="diagnosis-score" className="text-4xl font-bold tabular-nums text-slate-800">
            {Number.isInteger(score) ? score : score.toFixed(1)}
          </span>
          <span className="text-xs text-slate-400">/ 100</span>
        </div>
        <div className="space-y-1">
          <h2 className="text-sm font-semibold text-slate-700">Diagnosis CV (otomatis)</h2>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
              tier.chip,
            )}
          >
            {diagnosis.label || tier.label}
          </span>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Kekuatan
          </h3>
          {hasStrengths ? (
            <ul className="space-y-2">
              {diagnosis.strengths.map((rule) => (
                <StrengthItem key={rule.rule_id} rule={rule} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400">Belum ada kekuatan yang terdeteksi.</p>
          )}
        </div>
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Perlu diperbaiki
          </h3>
          {hasImprovements ? (
            <ul className="space-y-2">
              {diagnosis.improvements.map((rule) => (
                <ImprovementItem key={rule.rule_id} rule={rule} />
              ))}
            </ul>
          ) : (
            <p className="text-sm text-slate-400">Tidak ada perbaikan yang disarankan.</p>
          )}
        </div>
      </div>

      <p className="text-[11px] text-slate-400">Diatur aturan tetap — tanpa LLM.</p>
    </Card>
  );
}
