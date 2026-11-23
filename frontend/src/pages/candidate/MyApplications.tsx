import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  extractDetailedErrorMessage,
  fetchMyApplications,
  type MyApplicationRow,
} from "../../lib/api";
import { applicationStatusLabels, formatDateTime } from "../../lib/format";
import { Alert, Button, Spinner, cn } from "../../components/ui";

type PageState = "loading" | "ready" | "error";

const statusChipCls: Record<MyApplicationRow["status"], string> = {
  submitted: "bg-surface-variant text-on-surface-variant",
  reviewed: "bg-secondary-container text-on-secondary-container",
  shortlisted: "bg-primary-fixed text-primary font-semibold",
  hired: "bg-tertiary-fixed text-on-tertiary-fixed font-semibold",
  rejected: "bg-error-container text-on-error-container font-semibold",
};

function StatusChip({ status }: { status: MyApplicationRow["status"] }) {
  return (
    <span
      data-testid="application-status"
      className={cn(
        "inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold",
        statusChipCls[status] ?? "bg-surface-container text-on-surface-variant",
      )}
    >
      {applicationStatusLabels[status] ?? status}
    </span>
  );
}

function CoverLetterPreview({ text }: { text: string }) {
  const truncated = text.length > 160;
  return (
    <p className="mt-2 max-w-2xl text-xs leading-relaxed text-secondary italic bg-surface-container-low p-2.5 rounded-lg border border-slate-200">
      “{truncated ? `${text.slice(0, 160).trimEnd()}…` : text}”
    </p>
  );
}

export default function MyApplicationsPage() {
  const [state, setState] = useState<PageState>("loading");
  const [items, setItems] = useState<MyApplicationRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setLoadError(null);
    fetchMyApplications()
      .then((res) => {
        if (cancelled) return;
        setItems(res.items ?? []);
        setState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(extractDetailedErrorMessage(err));
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  if (state === "loading") return <Spinner label="Memuat lamaran…" />;

  return (
    <div className="flex flex-col gap-6">
      {/* Page Header - directly starts with page title */}
      <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
            Lamaran Saya
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant max-w-xl">
            Semua lamaran yang Anda kirim beserta statusnya.
          </p>
        </div>

        {/* Quick Stat Pill */}
        <div className="inline-flex items-center gap-3 bg-surface-container-lowest px-4 py-2 rounded-xl border border-slate-200 self-start sm:self-auto">
          <div className="w-8 h-8 rounded-lg bg-surface-container-high flex items-center justify-center text-primary">
            <span className="material-symbols-outlined text-[18px]">folder_open</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[11px] text-on-surface-variant uppercase font-semibold">
              Total Terkirim
            </span>
            <span className="text-sm font-bold text-on-surface leading-none">
              {items.length} Berkas
            </span>
          </div>
        </div>
      </section>

      {/* Error state */}
      {state === "error" && (
        <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 space-y-3">
          <Alert kind="error">{loadError ?? "Gagal memuat lamaran."}</Alert>
          <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
        </div>
      )}

      {/* Empty State Container */}
      {state === "ready" && items.length === 0 && (
        <section className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 overflow-hidden p-6 sm:p-10 flex flex-col items-center justify-center text-center relative">
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary-fixed/30 rounded-full blur-3xl pointer-events-none" />
          <div className="relative z-10 max-w-md mx-auto flex flex-col items-center py-6">
            <div className="relative mb-6 group">
              <div className="w-20 h-20 rounded-2xl bg-surface-container-low flex items-center justify-center text-primary-container transition-transform duration-300 group-hover:scale-105 border border-slate-200">
                <span className="material-symbols-outlined text-[44px]">drafts</span>
              </div>
              <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-surface-container-lowest border border-slate-200 flex items-center justify-center text-on-surface-variant">
                <span className="material-symbols-outlined text-[16px] text-primary">search</span>
              </div>
            </div>
            <h2 className="text-xl font-semibold text-on-surface mb-2">Belum ada lamaran</h2>
            <p className="text-sm text-on-surface-variant mb-6 leading-relaxed">
              Jelajahi lowongan yang cocok dan kirim lamaran pertama Anda.
            </p>
            <Link
              to="/app/recommendations"
              className="inline-flex items-center justify-center gap-2 bg-primary-container hover:bg-primary text-on-primary text-sm font-medium px-6 py-2.5 rounded-lg transition-all duration-200"
            >
              <span>Lihat Rekomendasi</span>
              <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
            </Link>
          </div>
        </section>
      )}

      {/* Application List Container */}
      {state === "ready" && items.length > 0 && (
        <div className="flex flex-col gap-4" data-testid="application-list">
          {items.map((row) => (
            <article
              key={row.id}
              className="bg-surface-container-lowest rounded-xl p-5 sm:p-6 border border-slate-200 flex flex-col sm:flex-row sm:items-start justify-between gap-4"
            >
              <div className="min-w-0 flex-1">
                <Link
                  to={`/app/jobs/${row.job_id}`}
                  className="text-base sm:text-lg font-semibold text-primary hover:text-primary-container transition-colors tracking-tight block truncate"
                >
                  {row.job_title}
                </Link>
                <p className="mt-1 text-xs sm:text-sm text-on-surface-variant">
                  <span className="font-medium text-on-surface">{row.company || "—"}</span>
                  <span className="mx-2 text-secondary/40">•</span>
                  <span>Dilamar {formatDateTime(row.applied_at)}</span>
                </p>
                {row.cover_letter && row.cover_letter.trim() !== "" && (
                  <CoverLetterPreview text={row.cover_letter.trim()} />
                )}
              </div>
              <div className="shrink-0 self-start sm:self-center">
                <StatusChip status={row.status} />
              </div>
            </article>
          ))}
        </div>
      )}

      {/* Recruitment Status Flow Guidance */}
      <section className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8">
        <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 gap-2 border-b border-surface-container">
          <div>
            <span className="text-xs text-primary font-bold uppercase tracking-wider">
              Tahapan Rekrutmen
            </span>
            <h3 className="text-lg font-semibold text-on-surface">Alur Status Lamaran</h3>
          </div>
          <div className="flex items-center gap-1.5 text-on-surface-variant bg-surface-container-low px-3 py-1.5 rounded-lg border border-slate-200 self-start">
            <span className="material-symbols-outlined text-[16px] text-primary">verified_user</span>
            <span className="text-xs font-medium">Sinkronisasi Otomatis TalentSync.AI</span>
          </div>
        </div>

        {/* 5 Status Steps */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 pt-6">
          {/* Step 1: Terkirim */}
          <div className="flex flex-col p-4 rounded-xl bg-[#f5f3ff] border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="w-6 h-6 rounded-full bg-primary-fixed text-primary text-xs font-bold flex items-center justify-center">
                1
              </span>
              <span className="material-symbols-outlined text-primary text-[20px]">send</span>
            </div>
            <span className="text-sm font-semibold text-on-surface mb-1">Terkirim</span>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Berkas aplikasi telah berhasil tersimpan di sistem perusahaan tujuan.
            </p>
          </div>

          {/* Step 2: Ditinjau */}
          <div className="flex flex-col p-4 rounded-xl bg-[#f5f3ff] border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="w-6 h-6 rounded-full bg-primary-fixed text-primary text-xs font-bold flex items-center justify-center">
                2
              </span>
              <span className="material-symbols-outlined text-primary text-[20px]">visibility</span>
            </div>
            <span className="text-sm font-semibold text-on-surface mb-1">Ditinjau</span>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Resume dan profil dinilai oleh tim HRD dan sistem pencocokan kandidat.
            </p>
          </div>

          {/* Step 3: Shortlist */}
          <div className="flex flex-col p-4 rounded-xl bg-[#f5f3ff] border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="w-6 h-6 rounded-full bg-primary-fixed text-primary text-xs font-bold flex items-center justify-center">
                3
              </span>
              <span className="material-symbols-outlined text-primary text-[20px]">bookmark</span>
            </div>
            <span className="text-sm font-semibold text-on-surface mb-1">Shortlist</span>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Kualifikasi Anda masuk daftar prioritas untuk proses seleksi lanjutan.
            </p>
          </div>

          {/* Step 4: Diterima */}
          <div className="flex flex-col p-4 rounded-xl bg-[#f5f3ff] border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="w-6 h-6 rounded-full bg-primary-fixed text-primary text-xs font-bold flex items-center justify-center">
                4a
              </span>
              <span className="material-symbols-outlined text-primary text-[20px]">check_circle</span>
            </div>
            <span className="text-sm font-semibold text-on-surface mb-1">Diterima</span>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Selamat! Anda lolos seluruh tahap seleksi menuju penawaran kerja (offering).
            </p>
          </div>

          {/* Step 5: Ditolak */}
          <div className="flex flex-col p-4 rounded-xl bg-[#f5f3ff] border border-slate-200">
            <div className="flex items-center justify-between mb-3">
              <span className="w-6 h-6 rounded-full bg-primary-fixed text-primary text-xs font-bold flex items-center justify-center">
                4b
              </span>
              <span className="material-symbols-outlined text-primary text-[20px]">cancel</span>
            </div>
            <span className="text-sm font-semibold text-on-surface mb-1">Ditolak</span>
            <p className="text-xs text-on-surface-variant leading-relaxed">
              Profil belum memenuhi kriteria saat ini, tetap simpan CV untuk lowongan lain.
            </p>
          </div>
        </div>

        <div className="mt-6 pt-4 border-t border-surface-container-high flex items-center gap-2 text-on-surface-variant">
          <span className="material-symbols-outlined text-primary text-[18px] shrink-0">info</span>
          <p className="text-xs italic text-on-surface-variant">
            Catatan: Status diperbarui secara berkala oleh tim perekrut sesuai tahapan seleksi.
          </p>
        </div>
      </section>
    </div>
  );
}
