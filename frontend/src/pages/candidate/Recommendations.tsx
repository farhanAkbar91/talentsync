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
import { Alert, Button, EmptyState, cn } from "../../components/ui";

type PageState = "loading" | "ready" | "needCv" | "error";

const MAX_SKILL_CHIPS = 5;

function employmentTypeLabel(value: string | null): string | null {
  if (!value) return null;
  return employmentTypeLabels[value] ?? value;
}

function SkillChip({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center rounded-full bg-surface-container px-2.5 py-0.5 text-xs font-medium text-on-surface-variant">
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
    <article className="bg-surface-container-lowest rounded-xl p-5 sm:p-6 border border-slate-200 flex flex-col sm:flex-row items-start gap-4">
      <span
        aria-label={`Peringkat ${rank}`}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-fixed text-sm font-bold text-primary"
      >
        {rank}
      </span>

      <div className="min-w-0 flex-1 space-y-2.5">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Link
            to={`/app/jobs/${item.job_id}`}
            data-recommendation-link
            className="text-base sm:text-lg font-semibold text-primary hover:text-primary-container transition-colors tracking-tight"
          >
            {item.title}
          </Link>
          {metaParts.length > 0 && (
            <span className="text-xs sm:text-sm text-secondary">{metaParts.join(" · ")}</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {shownSkills.map((s) => (
            <SkillChip key={s} name={s} />
          ))}
          {extraSkills > 0 && (
            <span className="text-xs text-secondary font-medium">+{extraSkills} lainnya</span>
          )}
          {item.matched_skills.length === 0 && (
            <span className="text-xs text-secondary">Belum ada skill yang cocok terdeteksi</span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-medium text-on-surface-variant">
            Wajib terpenuhi {item.matched_required}/{item.total_required}
          </span>
          {item.missing_critical > 0 && (
            <span className="inline-flex items-center rounded-full bg-error-container px-2.5 py-0.5 text-xs font-semibold text-on-error-container">
              {item.missing_critical} skill wajib belum ada
            </span>
          )}
        </div>

        {item.reason && item.reason.trim() !== "" && (
          <p className="text-xs italic text-secondary leading-relaxed">{item.reason}</p>
        )}
      </div>

      <div className="flex sm:flex-col items-center justify-between sm:justify-center gap-2 shrink-0 self-stretch sm:self-auto pt-2 sm:pt-0 border-t sm:border-t-0 border-surface-container">
        <span className="text-2xl font-bold tabular-nums text-on-surface">
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
    </article>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse" aria-hidden="true">
      <div className="bg-surface-container-lowest rounded-xl p-6 h-28 border border-slate-200" />
      <div className="bg-surface-container-lowest rounded-xl p-6 h-36 border border-slate-200" />
      <div className="bg-surface-container-lowest rounded-xl p-6 h-36 border border-slate-200" />
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

  return (
    <div className="flex flex-col gap-6">
      {/* Header Section - directly starts with page title */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
            Rekomendasi Lowongan
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant max-w-2xl">
            Rekomendasi pekerjaan yang disesuaikan secara cerdas dengan profil dan keahlian Anda.
          </p>
        </div>
        <div className="flex items-center gap-2 bg-surface-container-low px-4 py-2 rounded-lg border border-slate-200 self-start md:self-auto">
          <span
            className={
              "w-2.5 h-2.5 rounded-full inline-block " +
              (state === "ready" ? "bg-tertiary" : "bg-secondary-fixed-dim")
            }
          />
          <span className="text-xs text-on-surface-variant">
            Status CV:{" "}
            <strong className="text-on-surface font-semibold">
              {state === "ready" ? "Terkonfirmasi" : "Belum Dikonfirmasi"}
            </strong>
          </span>
        </div>
      </div>

      {/* needCv (400 MATCH_UNAVAILABLE) State */}
      {state === "needCv" && (
        <div className="bg-surface-container-lowest rounded-xl border border-slate-200 overflow-hidden flex flex-col p-6 sm:p-12 items-center text-center relative">
          <div className="absolute inset-0 bg-gradient-to-b from-primary-fixed/30 via-transparent to-transparent pointer-events-none" />
          <div className="relative mb-6">
            <div className="w-20 h-20 rounded-full bg-surface-container-low flex items-center justify-center text-primary-container">
              <span className="material-symbols-outlined text-[36px]">description</span>
            </div>
            <div className="absolute -bottom-1 -right-1 w-8 h-8 rounded-full bg-primary-container text-on-primary flex items-center justify-center">
              <span className="material-symbols-outlined text-[18px]">verified</span>
            </div>
          </div>

          <div className="max-w-xl mx-auto flex flex-col items-center gap-3 relative z-10">
            <h2 className="text-xl font-semibold text-on-surface">
              Aktifkan CV utama yang sudah dikonfirmasi
            </h2>
            <p className="text-sm text-on-surface-variant leading-relaxed">
              Rekomendasi hanya dihitung dari CV utama yang hasil ekstraksinya sudah Anda konfirmasi.
              Unggah atau pilih CV utama, lalu review dan konfirmasi ekstraksinya — setelah itu
              daftar lowongan yang paling mirip dengan profil Anda akan muncul di sini.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-3 mt-6 relative z-10 w-full sm:w-auto">
            <Link
              to="/app/cv"
              className="w-full sm:w-auto px-6 py-2.5 bg-primary-container text-on-primary text-sm font-medium rounded-lg hover:bg-primary transition-all flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-[18px]">upload_file</span>
              <span>Buka CV Saya</span>
            </Link>
            <Link
              to="/app/jobs"
              className="w-full sm:w-auto px-6 py-2.5 bg-surface-container-lowest text-on-surface text-sm font-medium rounded-lg hover:bg-surface-container-low transition-all border border-slate-200 flex items-center justify-center gap-2"
            >
              <span className="material-symbols-outlined text-[18px] text-on-surface-variant">
                search
              </span>
              <span>Cari lowongan manual</span>
            </Link>
          </div>

          <div className="mt-8 pt-4 w-full max-w-xl flex items-center justify-center gap-2 text-on-surface-variant text-xs">
            <span className="material-symbols-outlined text-[16px] text-tertiary">lock_reset</span>
            <span>
              Privasi terjamin: Data resume hanya diproses untuk kalkulasi kecocokan kualifikasi pribadi.
            </span>
          </div>
        </div>
      )}

      {/* Error state */}
      {state === "error" && (
        <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 space-y-4">
          <Alert kind="error">
            {loadError ?? "Terjadi kesalahan saat menghitung rekomendasi."}
          </Alert>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
            <Link
              to="/app/jobs"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-surface-container-lowest px-4 py-2 text-sm font-semibold text-on-surface border border-slate-300 transition hover:bg-surface-container-low"
            >
              Cari lowongan manual
            </Link>
          </div>
        </div>
      )}

      {/* Ready state with recommendations list */}
      {state === "ready" && (
        <>
          <div className="bg-surface-container-lowest rounded-xl p-4 sm:p-5 border border-slate-200 space-y-1">
            <p className="text-sm font-semibold text-on-surface">
              {total > 0
                ? `${total} lowongan dinilai terhadap CV utama Anda`
                : "Lowongan aktif dinilai terhadap CV utama Anda"}
            </p>
            {computedAt && (
              <p className="text-xs text-secondary">
                Dihitung {formatDateTime(computedAt)}
                {modelVersion ? ` · model ${modelVersion}` : ""}
              </p>
            )}
          </div>

          {items.length === 0 ? (
            <EmptyState
              title="Belum ada lowongan aktif yang bisa dinilai"
              description="Rekomendasi muncul ketika ada lowongan aktif di platform. Coba lagi nanti atau jelajahi lowongan secara manual."
            />
          ) : (
            <div className="space-y-4">
              {items.map((item, i) => (
                <RecommendationCard key={item.job_id} item={item} rank={i + 1} />
              ))}
              <p className="text-xs text-secondary italic">
                Urutan berdasarkan kemiripan &amp; kriteria lowongan — bukan jaminan diterima.
              </p>
            </div>
          )}
        </>
      )}

      {/* 3-Step Process Explanation Card */}
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-on-surface">
            Cara Kerja Rekomendasi Pintar
          </h3>
          <span className="text-xs text-on-surface-variant hidden sm:inline-block">
            3 Langkah Mudah
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Step 1 */}
          <div className="bg-surface-container-lowest p-5 rounded-xl border border-slate-200 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-primary px-2.5 py-0.5 bg-primary-fixed rounded-full">
                LANGKAH 01
              </span>
              <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary-container">
                <span className="material-symbols-outlined text-[18px]">cloud_upload</span>
              </div>
            </div>
            <h4 className="text-sm font-semibold text-on-surface mt-1">1. Unggah CV PDF</h4>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Unggah berkas resume Anda di menu CV Saya. Sistem kami menerima dokumen standar ATS dan non-ATS.
            </p>
          </div>

          {/* Step 2 */}
          <div className="bg-surface-container-lowest p-5 rounded-xl border border-slate-200 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-primary px-2.5 py-0.5 bg-primary-fixed rounded-full">
                LANGKAH 02
              </span>
              <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary-container">
                <span className="material-symbols-outlined text-[18px]">fact_check</span>
              </div>
            </div>
            <h4 className="text-sm font-semibold text-on-surface mt-1">2. Konfirmasi Ekstraksi</h4>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Tinjau riwayat, skill, dan data yang diekstrak oleh sistem. Anda bebas mengoreksi informasi sebelum validasi final.
            </p>
          </div>

          {/* Step 3 */}
          <div className="bg-surface-container-lowest p-5 rounded-xl border border-slate-200 flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-primary px-2.5 py-0.5 bg-primary-fixed rounded-full">
                LANGKAH 03
              </span>
              <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary-container">
                <span className="material-symbols-outlined text-[18px]">recommend</span>
              </div>
            </div>
            <h4 className="text-sm font-semibold text-on-surface mt-1">3. Dapatkan Rekomendasi</h4>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Mesin AI akan menampilkan lowongan dengan skor kecocokan tertinggi secara otomatis setiap hari.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
