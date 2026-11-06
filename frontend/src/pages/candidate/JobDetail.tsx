import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import {
  applyToJob,
  createCvOptimization,
  extractDetailedErrorMessage,
  fetchCvs,
  fetchMyApplications,
  type MyApplicationRow,
} from "../../lib/api";
import {
  applicationStatusLabels,
  employmentTypeLabels,
  formatDate,
  formatSalary,
  workModeLabels,
} from "../../lib/format";
import { fetchPublicJob, type Job } from "../../lib/api";
import { Alert, Badge, Button, Card, Spinner, Textarea, cn } from "../../components/ui";

/**
 * Detail lowongan (kandidat).
 * - Lamaran: GET /applications/mine sekali saat mount untuk mendeteksi lamaran
 *   yang sudah ada; tombol "Lamar dengan CV Utama" → POST /jobs/{id}/apply
 *   (cover letter opsional). 409 duplicate → status sudah melamar; 400 → edukasi CV.
 * - Optimasi CV (M8): tombol "Optimalkan CV untuk Lowongan Ini" — dicek saat klik
 *   (pola sama dengan "Cek Kompatibilitas"); 400 MATCH_UNAVAILABLE → edukasi.
 */

type ApplyState = "idle" | "open" | "submitting" | "success" | "duplicate" | "needCv" | "error";

function StatusChip({ status }: { status: MyApplicationRow["status"] }) {
  const cls: Record<MyApplicationRow["status"], string> = {
    submitted: "bg-slate-100 text-slate-600",
    reviewed: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
    shortlisted: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
    hired: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    rejected: "bg-red-50 text-red-600 ring-1 ring-red-200",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        cls[status],
      )}
    >
      {applicationStatusLabels[status] ?? status}
    </span>
  );
}

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Lamaran ---
  const [myApplication, setMyApplication] = useState<MyApplicationRow | null>(null);
  const [applyState, setApplyState] = useState<ApplyState>("idle");
  const [coverLetter, setCoverLetter] = useState("");
  const [applyError, setApplyError] = useState<string | null>(null);

  // --- Optimasi CV (M8) ---
  const [optimizing, setOptimizing] = useState(false);
  const [optimizeNeedCv, setOptimizeNeedCv] = useState(false);
  const [optimizeError, setOptimizeError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchPublicJob(id)
      .then(setJob)
      .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat lowongan."));
  }, [id]);

  // Satu request saat mount: apakah kandidat sudah melamar lowongan ini?
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    fetchMyApplications()
      .then((res) => {
        if (cancelled) return;
        const mine = res.items.find((row) => row.job_id === id) ?? null;
        if (mine) {
          setMyApplication(mine);
          setApplyState("duplicate");
        }
      })
      .catch(() => {
        // Best-effort: biarkan tombol lamar tampil; backend akan menolak bila duplikat.
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleApplySubmit() {
    if (!id) return;
    setApplyState("submitting");
    setApplyError(null);
    try {
      await applyToJob(id, coverLetter);
      setApplyState("success");
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status === 409) {
        setApplyState("duplicate");
        return;
      }
      if (status === 400) {
        // APPLICATION_UNAVAILABLE — butuh CV utama terkonfirmasi.
        setApplyState("needCv");
        return;
      }
      setApplyError(extractDetailedErrorMessage(err));
      setApplyState("error");
    }
  }

  async function handleOptimize() {
    if (!id || !job || optimizing) return;
    setOptimizing(true);
    setOptimizeNeedCv(false);
    setOptimizeError(null);
    try {
      // Butuh cv_id eksplisit → ambil CV milik kandidat, pakai yang utama.
      const cvs = await fetchCvs();
      const primary = cvs.find((c) => c.is_primary);
      if (!primary) {
        setOptimizeNeedCv(true);
        return;
      }
      const start = await createCvOptimization(primary.id, { job_id: id });
      navigate(`/app/cv/${primary.id}/optimize/${start.id}`, {
        state: { cached: start.cached ?? false, jobTitle: job.title },
      });
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status === 400) {
        // MATCH_UNAVAILABLE — CV utama belum dikonfirmasi.
        setOptimizeNeedCv(true);
        return;
      }
      setOptimizeError(extractDetailedErrorMessage(err));
    } finally {
      setOptimizing(false);
    }
  }

  if (error)
    return (
      <div className="space-y-4">
        <Alert kind="error">{error}</Alert>
        <Link to="/app/jobs">
          <Button variant="secondary">← Kembali ke daftar</Button>
        </Link>
      </div>
    );
  if (!job) return <Spinner />;

  const alreadyApplied = applyState === "duplicate" || applyState === "success";
  const duplicateFromFetch = applyState === "duplicate" && myApplication !== null;
  const submitting = applyState === "submitting";

  return (
    <div className="space-y-5">
      <Link to="/app/jobs" className="text-sm font-medium text-primary-700">
        ← Kembali ke daftar lowongan
      </Link>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">{job.title}</h1>
            <p className="mt-1 text-sm text-slate-500">
              {job.company.name}
              {job.location_text ? ` • ${job.location_text}` : ""}
              {job.company.industry ? ` • ${job.company.industry}` : ""}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <Badge value={job.employment_type} label={employmentTypeLabels[job.employment_type] ?? job.employment_type} />
              <Badge value={job.work_mode} label={workModeLabels[job.work_mode] ?? job.work_mode} />
              {job.seniority && <Badge value="draft" label={job.seniority} />}
            </div>
          </div>
          <div className="text-right text-sm">
            <p className="font-semibold text-slate-700">
              {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
            </p>
            <p className="text-xs text-slate-400">Diposting {formatDate(job.posted_at)}</p>
            {job.closing_at && <p className="text-xs text-slate-400">Batas: {formatDate(job.closing_at)}</p>}
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <h2 className="text-sm font-semibold text-slate-700">Deskripsi Pekerjaan</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
              {job.description}
            </p>
          </Card>
          {job.responsibilities && (
            <Card>
              <h2 className="text-sm font-semibold text-slate-700">Tanggung Jawab</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                {job.responsibilities}
              </p>
            </Card>
          )}
          {job.requirements && (
            <Card>
              <h2 className="text-sm font-semibold text-slate-700">Kualifikasi</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">
                {job.requirements}
              </p>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card>
            <h2 className="text-sm font-semibold text-slate-700">Keahlian Diminta</h2>
            <p className="mt-1 text-xs text-slate-400">
              Solid = wajib (bobot 60%) · Pudar = nilai tambah (bobot 40%)
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.skills.map((s) => (
                <span
                  key={s.name}
                  className={
                    "rounded-full px-2.5 py-1 text-xs font-medium " +
                    (s.required ? "bg-primary-600 text-white" : "bg-primary-100 text-primary-700")
                  }
                >
                  {s.name}
                  {!s.required && " (plus)"}
                </span>
              ))}
            </div>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-700">Lamar Posisi Ini</h2>
            <p className="mt-2 text-xs text-slate-500">
              Lihat seberapa cocok profil Anda dengan lowongan ini sebelum melamar.
            </p>
            <Link to={`/app/jobs/${job.id}/compatibility`} state={{ jobTitle: job.title }}>
              <Button className="mt-3 w-full">Cek Kompatibilitas</Button>
            </Link>

            {/* Status lamaran / tombol lamar */}
            {alreadyApplied ? (
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  {applyState === "success" ? (
                    <span
                      data-testid="apply-success-chip"
                      className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200"
                    >
                      Lamaran terkirim
                    </span>
                  ) : (
                    <StatusChip status={myApplication?.status ?? "submitted"} />
                  )}
                </div>
                <Link to="/app/applications">
                  <Button variant="secondary" className="w-full">
                    Lihat Lamaran Saya
                  </Button>
                </Link>
              </div>
            ) : applyState === "needCv" ? (
              <div className="mt-3 space-y-2">
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-700 ring-1 ring-amber-200">
                  Melamar memakai CV utama yang sudah dikonfirmasi. Unggah CV, lalu review dan
                  konfirmasi ekstraksinya terlebih dahulu.
                </p>
                <Link to="/app/cv">
                  <Button variant="secondary" className="w-full">
                    Buka CV Saya
                  </Button>
                </Link>
              </div>
            ) : applyState === "error" ? (
              <div className="mt-3 space-y-2">
                <Alert kind="error">{applyError ?? "Gagal mengirim lamaran."}</Alert>
                <Button className="w-full" onClick={() => setApplyState("open")}>
                  Coba Lagi
                </Button>
              </div>
            ) : (
              <>
                {duplicateFromFetch && (
                  <p className="mt-3 text-xs text-slate-400">Anda sudah melamar.</p>
                )}
                <Button
                  data-testid="apply-open"
                  className="mt-3 w-full"
                  onClick={() => {
                    setApplyState("open");
                    setApplyError(null);
                  }}
                >
                  Lamar dengan CV Utama
                </Button>
              </>
            )}

            {/* Form lamaran (modal kecil) — tetap tampil saat mengirim */}
            {(applyState === "open" || applyState === "submitting") && (
              <div
                className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
                role="dialog"
                aria-modal="true"
                aria-label="Lamar dengan CV Utama"
              >
                <Card className="w-full max-w-md space-y-4">
                  <div>
                    <h3 className="text-base font-bold text-slate-800">Lamar dengan CV Utama</h3>
                    <p className="mt-1 text-xs text-slate-500">
                      {job.title} · {job.company.name}
                    </p>
                  </div>
                  <p className="text-xs text-slate-500">
                    Lamaran dikirim memakai CV utama Anda yang sudah dikonfirmasi. Cover letter
                    bersifat opsional.
                  </p>
                  <Textarea
                    aria-label="Cover letter (opsional)"
                    placeholder="Ceritakan singkat mengapa Anda cocok untuk posisi ini…"
                    value={coverLetter}
                    rows={5}
                    onChange={(e) => setCoverLetter(e.target.value)}
                  />
                  {applyError && <Alert kind="error">{applyError}</Alert>}
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="secondary"
                      disabled={submitting}
                      onClick={() => {
                        setApplyState("idle");
                        setApplyError(null);
                      }}
                    >
                      Batal
                    </Button>
                    <Button disabled={submitting} onClick={handleApplySubmit}>
                      {submitting ? "Mengirim…" : "Kirim Lamaran"}
                    </Button>
                  </div>
                </Card>
              </div>
            )}

            {/* Optimasi CV (M8) */}
            <div className="mt-3 border-t border-slate-100 pt-3">
              <Button
                data-testid="optimize-start"
                variant="secondary"
                className="w-full"
                disabled={optimizing}
                onClick={handleOptimize}
              >
                {optimizing ? "Menyiapkan…" : "Optimalkan CV untuk Lowongan Ini"}
              </Button>
              {optimizeNeedCv && (
                <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-700 ring-1 ring-amber-200">
                  Optimasi hanya berjalan pada CV utama yang hasil ekstraksinya sudah Anda
                  konfirmasi. Pilih CV utama, lalu review dan konfirmasi ekstraksinya terlebih
                  dahulu.
                </p>
              )}
              {optimizeError && (
                <div className="mt-2">
                  <Alert kind="error">{optimizeError}</Alert>
                </div>
              )}
            </div>

            <Link to="/app/cv">
              <Button variant="secondary" className="mt-3 w-full">
                Kelola CV Saya
              </Button>
            </Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
