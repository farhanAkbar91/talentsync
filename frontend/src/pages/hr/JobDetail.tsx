import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { archiveJob, extractErrorMessage, fetchHrJob, transitionJob, type Job } from "../../lib/api";
import { employmentTypeLabels, formatDate, formatSalary, jobStatusLabels, toConfidencePercent, workModeLabels } from "../../lib/format";
import { Alert, Badge, Button, Card, Spinner, cn } from "../../components/ui";

const nextActions: Record<string, { action: "publish" | "pause" | "resume" | "close"; label: string; variant?: "primary" | "secondary" }[]> = {
  draft: [{ action: "publish", label: "Terbitkan Lowongan" }],
  active: [
    { action: "pause", label: "Jeda", variant: "secondary" },
    { action: "close", label: "Tutup", variant: "secondary" },
  ],
  paused: [
    { action: "resume", label: "Aktifkan Kembali" },
    { action: "close", label: "Tutup", variant: "secondary" },
  ],
  closed: [],
};

export default function HrJobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!id) return;
    try {
      setJob(await fetchHrJob(id));
    } catch (err) {
      setError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error)
    return (
      <div className="space-y-4">
        <Alert kind="error">{error}</Alert>
        <Link to="/hr/jobs">
          <Button variant="secondary">← Kembali</Button>
        </Link>
      </div>
    );
  if (!job) return <Spinner />;

  const status = job.status ?? "draft";
  const actions = nextActions[status] ?? [];

  async function doTransition(action: "publish" | "pause" | "resume" | "close") {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      setJob(await transitionJob(id, action));
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function doArchive() {
    if (!id || !window.confirm("Arsipkan lowongan ini? Lowongan tidak akan tampil lagi di katalog.")) return;
    setBusy(true);
    try {
      await archiveJob(id);
      navigate("/hr/jobs");
    } catch (err) {
      setError(extractErrorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Link to="/hr/jobs" className="text-sm font-medium text-primary-700">
        ← Kembali ke daftar lowongan
      </Link>

      {error && <Alert kind="error">{error}</Alert>}

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-800">{job.title}</h1>
              <Badge value={status} label={jobStatusLabels[status]} />
            </div>
            <p className="mt-1 text-sm text-slate-500">
              {job.company.name}
              {job.location_text ? ` • ${job.location_text}` : ""}
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
            <p className="text-xs text-slate-400">Batas: {formatDate(job.closing_at)}</p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
          {actions.map((a) => (
            <Button key={a.action} variant={a.variant ?? "primary"} disabled={busy} onClick={() => doTransition(a.action)}>
              {a.label}
            </Button>
          ))}
          {["draft", "active", "paused"].includes(status) && (
            <Link to={`/hr/jobs/${job.id}/edit`}>
              <Button variant="secondary" disabled={busy}>
                Edit
              </Button>
            </Link>
          )}
          <Button variant="danger" disabled={busy} onClick={doArchive}>
            Arsipkan
          </Button>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card>
            <h2 className="text-sm font-semibold text-slate-700">Deskripsi</h2>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">{job.description}</p>
          </Card>
          {job.responsibilities && (
            <Card>
              <h2 className="text-sm font-semibold text-slate-700">Tanggung Jawab</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">{job.responsibilities}</p>
            </Card>
          )}
          {job.requirements && (
            <Card>
              <h2 className="text-sm font-semibold text-slate-700">Kualifikasi</h2>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-600">{job.requirements}</p>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card>
            <h2 className="text-sm font-semibold text-slate-700">Kriteria Kompetensi</h2>
            <p className="mt-1 text-xs font-medium text-primary-700">Wajib — 60%</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {job.skills.filter((s) => s.required).map((s) => (
                <span key={s.name} className="rounded-full bg-primary-600 px-2.5 py-1 text-xs font-medium text-white">
                  {s.name}
                </span>
              ))}
              {job.skills.filter((s) => s.required).length === 0 && (
                <span className="text-xs text-slate-400">—</span>
              )}
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500">Nilai Tambah — 40%</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {job.skills.filter((s) => !s.required).map((s) => (
                <span key={s.name} className="rounded-full bg-primary-100 px-2.5 py-1 text-xs font-medium text-primary-700">
                  {s.name}
                </span>
              ))}
              {job.skills.filter((s) => !s.required).length === 0 && (
                <span className="text-xs text-slate-400">—</span>
              )}
            </div>
          </Card>

          {job.skills_normalized && job.skills_normalized.length > 0 && (
            <Card>
              <h2 className="text-sm font-semibold text-slate-700">Pemetaan skill (kamus standar)</h2>
              <p className="mt-0.5 text-xs text-slate-400">
                Hasil pemetaan skill lowongan ke kamus skill standar.
              </p>
              <ul className="mt-2 space-y-2">
                {job.skills_normalized.map((ns) => {
                  const pct = toConfidencePercent(ns.confidence);
                  return (
                    <li
                      key={`${ns.canonical.slug}-${ns.raw_name}`}
                      className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-sm"
                    >
                      <span className="font-semibold text-slate-800">{ns.canonical.name}</span>
                      <span className="text-xs text-slate-400">{ns.canonical.category}</span>
                      <span className="text-xs text-slate-500">
                        dari teks: <span className="italic">“{ns.raw_name}”</span>
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                          ns.required
                            ? "bg-primary-600 text-white"
                            : "bg-primary-100 text-primary-700",
                        )}
                      >
                        {ns.required ? "Wajib" : "Disarankan"}
                      </span>
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                          pct >= 80
                            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                            : pct >= 60
                              ? "bg-amber-50 text-amber-700 ring-1 ring-amber-200"
                              : "bg-red-50 text-red-600 ring-1 ring-red-200",
                        )}
                      >
                        {pct}%
                      </span>
                      {ns.needs_review && (
                        <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
                          Perlu review
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
