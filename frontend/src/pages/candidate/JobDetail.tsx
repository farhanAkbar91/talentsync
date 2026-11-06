import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  employmentTypeLabels,
  formatDate,
  formatSalary,
  workModeLabels,
} from "../../lib/format";
import { fetchPublicJob, type Job } from "../../lib/api";
import { Alert, Badge, Button, Card, Spinner } from "../../components/ui";

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchPublicJob(id)
      .then(setJob)
      .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat lowongan."));
  }, [id]);

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
            <Button className="mt-2 w-full" variant="secondary" disabled title="Fase berikutnya">
              Lamar (segera hadir)
            </Button>
            <Link to="/app/cv">
              <Button variant="secondary" className="mt-2 w-full">
                Kelola CV Saya
              </Button>
            </Link>
          </Card>
        </div>
      </div>
    </div>
  );
}
