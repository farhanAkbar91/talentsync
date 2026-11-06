import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchCvs,
  fetchMeSummary,
  fetchRecommendations,
  type CVDoc,
  type MeSummary,
  type RecommendationItem,
} from "../../lib/api";
import { cvStatusLabels } from "../../lib/format";
import { clampPct, formatScore, scoreTier } from "../../lib/score";
import { Badge, Button, Card, cn, Spinner } from "../../components/ui";

function completeness(profile: MeSummary["candidate_profile"]): number {
  if (!profile) return 0;
  const checks = [
    profile.phone,
    profile.location,
    profile.headline,
    profile.summary,
    profile.skills.length > 0,
    profile.education.length > 0,
    profile.experience.length > 0,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

/**
 * M6 — Teaser rekomendasi di dashboard: top-3 lowongan paling mirip (limit=3).
 * Kartu disembunyikan seluruhnya saat belum ada CV utama terkonfirmasi (400),
 * gagal memuat, atau belum ada lowongan aktif yang bisa dinilai.
 */
function RecommendationsTeaser() {
  const [items, setItems] = useState<RecommendationItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRecommendations(3)
      .then((res) => {
        if (!cancelled) setItems(res.items ?? []);
      })
      .catch(() => {
        if (!cancelled) setItems([]); // 400/error → sembunyikan kartu
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (items === null) {
    return (
      <Card aria-hidden="true">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-44 rounded bg-slate-200/70" />
          <div className="h-4 w-full max-w-md rounded bg-slate-200/70" />
          <div className="h-4 w-64 rounded bg-slate-200/70" />
        </div>
      </Card>
    );
  }

  if (items.length === 0) return null;

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-700">Rekomendasi untuk Anda</h2>
        <Link to="/app/recommendations" className="text-xs font-medium text-primary-700">
          Lihat semua →
        </Link>
      </div>
      <ul className="divide-y divide-slate-100">
        {items.map((item) => {
          const tier = scoreTier(clampPct(item.overall));
          return (
            <li key={item.job_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 first:pt-0 last:pb-0">
              <Link
                to={`/app/jobs/${item.job_id}`}
                className="min-w-0 flex-1 truncate text-sm font-semibold text-primary-700 underline decoration-primary-200 underline-offset-2 hover:decoration-primary-500"
              >
                {item.title}
              </Link>
              <span className="text-sm font-semibold tabular-nums text-slate-800">
                {formatScore(clampPct(item.overall))}
              </span>
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold",
                  tier.chip,
                )}
              >
                {item.label || tier.label}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export default function CandidateDashboard() {
  const [summary, setSummary] = useState<MeSummary | null>(null);
  const [cvs, setCvs] = useState<CVDoc[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchMeSummary(), fetchCvs()])
      .then(([s, c]) => {
        setSummary(s);
        setCvs(c);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat dashboard."));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!summary || !cvs) return <Spinner />;

  const profile = summary.candidate_profile;
  const primary = cvs.find((cv) => cv.is_primary);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Selamat Datang, {summary.user.full_name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Lengkapi profil dan CV Anda untuk mendapatkan rekomendasi terbaik saat mesin AI aktif.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Kelengkapan Profil
          </p>
          <p className="mt-2 text-3xl font-bold text-primary-700">{completeness(profile)}%</p>
          <Link to="/app/profile" className="mt-2 inline-block text-xs font-medium text-primary-700">
            Lengkapi profil →
          </Link>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">CV Utama</p>
          <div className="mt-2 flex items-center gap-2">
            {primary ? (
              <>
                <Badge value={primary.status} label={cvStatusLabels[primary.status]} />
                <span className="truncate text-sm text-slate-600">{primary.original_filename}</span>
              </>
            ) : (
              <span className="text-sm text-slate-500">Belum ada CV</span>
            )}
          </div>
          <Link to="/app/cv" className="mt-2 inline-block text-xs font-medium text-primary-700">
            Kelola CV →
          </Link>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Cari Lowongan
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Jelajahi lowongan aktif dari perusahaan di platform.
          </p>
          <Link to="/app/jobs">
            <Button className="mt-2 w-full">Jelajahi Lowongan</Button>
          </Link>
        </Card>
      </div>

      <RecommendationsTeaser />

      <Card>
        <h2 className="text-sm font-semibold text-slate-700">Info Fase</h2>
        <p className="mt-2 text-sm text-slate-500">
          Pencocokan AI sudah aktif: rekomendasi lowongan, skor kompatibilitas, dan analisis skill
          gap tersedia setelah ekstraksi CV dikonfirmasi. Alur lamaran menyusul pada fase
          berikutnya (Applications).
        </p>
      </Card>
    </div>
  );
}
