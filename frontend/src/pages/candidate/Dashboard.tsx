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
import { Badge, Spinner } from "../../components/ui";
import { BerandaHero } from "../../components/BerandaShared";

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
      <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 animate-pulse space-y-3">
        <div className="h-4 w-44 rounded bg-slate-200" />
        <div className="h-4 w-full max-w-md rounded bg-slate-200" />
        <div className="h-4 w-64 rounded bg-slate-200" />
      </div>
    );
  }

  if (items.length === 0) return null;

  return (
    <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-surface-container pb-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary-fixed flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
          </div>
          <div>
            <h2 className="text-base font-semibold text-on-surface">Rekomendasi untuk Anda</h2>
            <p className="text-xs text-on-surface-variant">Lowongan paling relevan dengan profil Anda</p>
          </div>
        </div>
        <Link
          to="/app/recommendations"
          className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
        >
          <span>Lihat semua</span>
          <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
        </Link>
      </div>
      <ul className="divide-y divide-surface-container-high">
        {items.map((item) => {
          const tier = scoreTier(clampPct(item.overall));
          return (
            <li
              key={item.job_id}
              className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0 flex-1">
                <Link
                  to={`/app/jobs/${item.job_id}`}
                  className="text-sm font-semibold text-primary hover:text-primary-container transition-colors truncate block"
                >
                  {item.title}
                </Link>
                {item.company && (
                  <p className="text-xs text-on-surface-variant mt-0.5">{item.company}</p>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-sm font-bold tabular-nums text-on-surface">
                  {formatScore(clampPct(item.overall))}
                </span>
                <span
                  className={
                    "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold " +
                    tier.chip
                  }
                >
                  {item.label || tier.label}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
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

  if (error) return <p className="text-sm text-error p-4">{error}</p>;
  if (!summary || !cvs) return <Spinner />;

  const profile = summary.candidate_profile;
  const primary = cvs.find((cv) => cv.is_primary);
  const firstName = summary.user.full_name?.split(" ")[0] || "Kandidat";
  const pct = completeness(profile);

  return (
    <div className="flex flex-col gap-6">
      {/* Top Greeting Section */}
      <div className="flex flex-col gap-1">
        <div>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-primary-fixed text-primary text-xs uppercase tracking-wider font-semibold">
            Kandidat
          </span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
          Selamat Datang, {firstName}
        </h1>
        <p className="text-sm sm:text-base text-on-surface-variant max-w-2xl">
          Lengkapi profil dan CV Anda untuk mendapatkan rekomendasi terbaik saat mesin AI aktif.
        </p>
      </div>

      {/* Shared Hero */}
      <BerandaHero isPublic={false} />

      {/* Candidate Status Overview Cards (3 modules) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: Kelengkapan Profil */}
        <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-6">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                Kelengkapan Profil
              </span>
              <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                <span className="material-symbols-outlined text-[18px]">person_outline</span>
              </div>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold text-on-surface">{pct}%</span>
              <span
                className={
                  "text-xs font-medium " +
                  (pct === 100
                    ? "text-tertiary"
                    : pct > 0
                      ? "text-primary-container"
                      : "text-error")
                }
              >
                {pct === 100 ? "Lengkap" : pct > 0 ? "Sebagian terisi" : "Belum diisi"}
              </span>
            </div>
            <div className="w-full bg-surface-container-low h-2 rounded-full overflow-hidden">
              <div
                className="bg-primary h-full transition-all duration-500 rounded-full"
                style={{ width: `${pct}%` }}
              />
            </div>
            <p className="text-xs text-on-surface-variant">
              Data diri dasar, riwayat pendidikan, dan preferensi kerja Anda.
            </p>
          </div>
          <Link
            to="/app/profile"
            className="inline-flex items-center gap-1.5 text-primary text-sm font-semibold hover:text-primary-container transition-colors group"
          >
            <span>Lengkapi profil</span>
            <span className="material-symbols-outlined text-[18px] group-hover:translate-x-1 transition-transform">
              arrow_forward
            </span>
          </Link>
        </div>

        {/* Card 2: CV Utama */}
        <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-6">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                CV Utama
              </span>
              <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                <span className="material-symbols-outlined text-[18px]">upload_file</span>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              {primary ? (
                <div className="flex flex-wrap items-center gap-2">
                  <Badge value={primary.status} label={cvStatusLabels[primary.status]} />
                  <span className="text-sm font-semibold text-on-surface truncate block max-w-full">
                    {primary.original_filename}
                  </span>
                </div>
              ) : (
                <span className="text-lg font-semibold text-on-surface">Belum ada CV</span>
              )}
              <p className="text-xs text-on-surface-variant mt-1">
                Unggah file PDF resume untuk memicu ekstraksi data dan auto-matching AI.
              </p>
            </div>
            <div className="rounded-lg bg-surface-container-low p-3 flex items-center gap-3">
              <div className="w-9 h-9 rounded bg-surface-container-lowest flex items-center justify-center text-secondary shrink-0">
                <span className="material-symbols-outlined text-[20px]">picture_as_pdf</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-medium text-on-surface">Format didukung: PDF</span>
                <span className="text-[11px] text-secondary">Maksimum ukuran 10 MB</span>
              </div>
            </div>
          </div>
          <Link
            to="/app/cv"
            className="inline-flex items-center gap-1.5 text-primary text-sm font-semibold hover:text-primary-container transition-colors group"
          >
            <span>Kelola CV</span>
            <span className="material-symbols-outlined text-[18px] group-hover:translate-x-1 transition-transform">
              arrow_forward
            </span>
          </Link>
        </div>

        {/* Card 3: Cari Lowongan */}
        <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-6">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                Cari Lowongan
              </span>
              <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                <span className="material-symbols-outlined text-[18px]">work_outline</span>
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-lg font-semibold text-on-surface">Eksplorasi Karir</span>
              <p className="text-xs text-on-surface-variant">
                Jelajahi lowongan aktif dari perusahaan di platform.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-surface-container-low p-2.5 rounded-lg text-center">
                <span className="text-[11px] text-secondary uppercase font-semibold">Lowongan</span>
                <p className="text-base font-bold text-on-surface">Aktif</p>
              </div>
              <div className="bg-surface-container-low p-2.5 rounded-lg text-center">
                <span className="text-[11px] text-secondary uppercase font-semibold">Mitra</span>
                <p className="text-base font-bold text-on-surface">Terverifikasi</p>
              </div>
            </div>
          </div>
          <Link
            to="/app/jobs"
            className="inline-flex items-center justify-center gap-2 w-full h-10 rounded-lg bg-surface-container-low text-primary text-sm font-medium hover:bg-primary hover:text-on-primary transition-all border border-slate-200"
          >
            <span className="material-symbols-outlined text-[18px]">travel_explore</span>
            <span>Jelajahi Lowongan</span>
          </Link>
        </div>
      </div>

      {/* Recommendations Teaser */}
      <RecommendationsTeaser />
    </div>
  );
}
