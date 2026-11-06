import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  extractDetailedErrorMessage,
  fetchRecommendations,
  type RecommendationItem,
} from "../../lib/api";
import { employmentTypeLabels, formatDateTime } from "../../lib/format";
import { clampPct, formatScore, scoreTier } from "../../lib/score";
import { Alert, Button, Card, EmptyState, cn } from "../../components/ui";

/**
 * M6 — Rekomendasi lowongan untuk CV utama terkonfirmasi
 * (GET /me/recommendations, diurutkan skor DESC).
 * 400 MATCH_UNAVAILABLE → empty state edukatif (pola sama dengan halaman kompatibilitas);
 * error lain → inline + retry.
 */

const secondaryLinkCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50";

type PageState = "loading" | "ready" | "needCv" | "error";

const MAX_SKILL_CHIPS = 5;

function employmentTypeLabel(value: string | null): string | null {
  if (!value) return null;
  return employmentTypeLabels[value] ?? value;
}

function SkillChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
      {name}
    </span>
  );
}

function RecommendationCard({ item, rank }: { item: RecommendationItem; rank: number }) {
  const tier = scoreTier(clampPct(item.overall));
  const shownSkills = item.matched_skills.slice(0, MAX_SKILL_CHIPS);
  const extraSkills = item.matched_skills.length - shownSkills.length;
  const metaParts = [item.company, item.location, employmentTypeLabel(item.employment_type)].filter(
    (v): v is string => Boolean(v && v.trim() !== ""),
  );

  return (
    <Card className="flex flex-wrap items-start gap-4">
      <span
        aria-label={`Peringkat ${rank}`}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-50 text-xs font-bold text-primary-700"
      >
        {rank}
      </span>

      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Link
            to={`/app/jobs/${item.job_id}`}
            data-recommendation-link
            className="text-base font-semibold text-primary-700 underline decoration-primary-200 underline-offset-2 hover:decoration-primary-500"
          >
            {item.title}
          </Link>
          {metaParts.length > 0 && (
            <span className="text-sm text-slate-500">{metaParts.join(" · ")}</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {shownSkills.map((s) => (
            <SkillChip key={s} name={s} />
          ))}
          {extraSkills > 0 && (
            <span className="text-[11px] text-slate-400">+{extraSkills} lainnya</span>
          )}
          {item.matched_skills.length === 0 && (
            <span className="text-[11px] text-slate-400">Belum ada skill yang cocok terdeteksi</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium text-slate-600">
            Wajib terpenuhi {item.matched_required}/{item.total_required}
          </span>
          {item.missing_critical > 0 && (
            <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600 ring-1 ring-red-200">
              {item.missing_critical} skill wajib belum ada
            </span>
          )}
        </div>

        {item.reason && item.reason.trim() !== "" && (
          <p className="text-xs italic text-slate-400">{item.reason}</p>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-center gap-1">
        <span className="text-2xl font-bold tabular-nums text-slate-800">
          {formatScore(clampPct(item.overall))}
        </span>
        <span
          className={cn(
            "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
            tier.chip,
          )}
        >
          {item.label || tier.label}
        </span>
      </div>
    </Card>
  );
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-xl bg-slate-200/70", className)} />;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-5" aria-hidden="true">
      <Card className="space-y-3">
        <SkeletonBlock className="h-7 w-64" />
        <SkeletonBlock className="h-4 w-52" />
      </Card>
      {[0, 1, 2].map((i) => (
        <Card key={i} className="space-y-3">
          <SkeletonBlock className="h-5 w-72" />
          <SkeletonBlock className="h-4 w-full max-w-md" />
          <SkeletonBlock className="h-4 w-40" />
        </Card>
      ))}
      <span className="sr-only">Memuat rekomendasi…</span>
    </div>
  );
}

export default function RecommendationsPage() {
  const [state, setState] = useState<PageState>("loading");
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [computedAt, setComputedAt] = useState<string | null>(null);
  const [modelVersion, setModelVersion] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setLoadError(null);

    fetchRecommendations(10)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items ?? []);
        setTotal(res.total ?? res.items?.length ?? 0);
        setComputedAt(res.computed_at ?? null);
        setModelVersion(res.model_version ?? null);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        const status = axios.isAxiosError(err) ? err.response?.status : undefined;
        if (status === 400) {
          // MATCH_UNAVAILABLE — belum ada CV utama terkonfirmasi.
          setState("needCv");
          return;
        }
        setLoadError(extractDetailedErrorMessage(err));
        setState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  if (state === "loading") return <LoadingSkeleton />;

  if (state === "needCv") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Rekomendasi Lowongan</h1>
        <EmptyState
          title="Aktifkan CV utama yang sudah dikonfirmasi"
          description="Rekomendasi hanya dihitung dari CV utama yang hasil ekstraksinya sudah Anda konfirmasi. Unggah atau pilih CV utama, lalu review dan konfirmasi ekstraksinya — setelah itu daftar lowongan yang paling mirip dengan profil Anda akan muncul di sini."
        />
        <div className="flex flex-wrap gap-2">
          <Link to="/app/cv" className={secondaryLinkCls}>
            Buka CV Saya
          </Link>
          <Link to="/app/jobs" className={secondaryLinkCls}>
            Cari lowongan manual
          </Link>
        </div>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Rekomendasi Lowongan</h1>
        <Card className="space-y-3">
          <Alert kind="error">
            {loadError ?? "Terjadi kesalahan saat menghitung rekomendasi."}
          </Alert>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
            <Link to="/app/jobs" className={secondaryLinkCls}>
              Cari lowongan manual
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Card className="space-y-1.5">
        <h1 className="text-2xl font-bold text-slate-800">Rekomendasi Lowongan</h1>
        <p className="text-sm text-slate-500">
          {total > 0
            ? `${total} lowongan dinilai terhadap CV utama Anda`
            : "Lowongan aktif dinilai terhadap CV utama Anda"}
          {computedAt && (
            <span className="text-slate-400">
              {" "}
              · Dihitung {formatDateTime(computedAt)}
              {modelVersion ? ` · model ${modelVersion}` : ""}
            </span>
          )}
        </p>
      </Card>

      {items.length === 0 ? (
        <EmptyState
          title="Belum ada lowongan aktif yang bisa dinilai"
          description="Rekomendasi muncul ketika ada lowongan aktif di platform. Coba lagi nanti atau jelajahi lowongan secara manual."
        />
      ) : (
        <>
          <div className="space-y-4">
            {items.map((item, i) => (
              <RecommendationCard key={item.job_id} item={item} rank={i + 1} />
            ))}
          </div>
          <p className="text-xs text-slate-400">
            Urutan berdasarkan kemiripan &amp; kriteria lowongan — bukan jaminan diterima.
          </p>
        </>
      )}
    </div>
  );
}
