import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchHrJobStats, fetchHrJobs, fetchMeSummary, type Job, type JobStats, type MeSummary } from "../../lib/api";
import { formatDate, jobStatusLabels } from "../../lib/format";
import { Badge, Button, Card, EmptyState, Spinner, StatCard } from "../../components/ui";

export default function HrDashboard() {
  const [summary, setSummary] = useState<MeSummary | null>(null);
  const [stats, setStats] = useState<JobStats | null>(null);
  const [recent, setRecent] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchMeSummary(), fetchHrJobStats(), fetchHrJobs({ page: 1, size: 5 })])
      .then(([s, st, jobs]) => {
        setSummary(s);
        setStats(st);
        setRecent(jobs.items);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat dashboard."));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!summary || !stats || !recent) return <Spinner />;

  if (!summary.company) {
    return (
      <Card>
        <h1 className="text-xl font-bold text-slate-800">Selamat Datang, {summary.user.full_name}</h1>
        <p className="mt-2 text-sm text-slate-500">
          Anda belum terhubung dengan perusahaan. Lengkapi profil perusahaan untuk mulai
          memasang lowongan.
        </p>
        <Link to="/hr/company">
          <Button className="mt-4">Buat Profil Perusahaan</Button>
        </Link>
      </Card>
    );
  }

  const by = stats.by_status;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Selamat Datang, {summary.user.full_name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-sm text-slate-500">{summary.company.name}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <StatCard label="Total Lowongan" value={String(stats.total)} />
        <StatCard label="Aktif" value={String(by["active"] ?? 0)} detail="Menerima pelamar" />
        <StatCard label="Draft" value={String(by["draft"] ?? 0)} detail="Belum diterbitkan" />
        <StatCard label="Ditutup" value={String(by["closed"] ?? 0)} />
      </div>

      <Card className="p-0">
        <div className="flex items-center justify-between px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-700">Lowongan Terbaru</h2>
          <Link to="/hr/jobs" className="text-xs font-medium text-primary-700">
            Lihat semua →
          </Link>
        </div>
        {recent.length === 0 ? (
          <div className="px-5 pb-5">
            <EmptyState title="Belum ada lowongan" description="Buat lowongan pertama Anda." />
            <div className="mt-3 text-center">
              <Link to="/hr/jobs/new">
                <Button>+ Buat Lowongan Baru</Button>
              </Link>
            </div>
          </div>
        ) : (
          <table className="w-full text-left text-sm">
            <tbody>
              {recent.map((job) => (
                <tr key={job.id} className="border-t border-slate-100">
                  <td className="px-5 py-3">
                    <Link to={`/hr/jobs/${job.id}`} className="font-medium text-slate-700 hover:text-primary-700">
                      {job.title}
                    </Link>
                    <span className="ml-2 text-xs text-slate-400">{job.location_text}</span>
                  </td>
                  <td className="px-5 py-3 text-xs text-slate-400">Diposting {formatDate(job.posted_at)}</td>
                  <td className="px-5 py-3 text-right">
                    <Badge value={job.status ?? "draft"} label={jobStatusLabels[job.status ?? "draft"]} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-slate-700">Info Fase</h2>
        <p className="mt-2 text-sm text-slate-500">
          Peringkat kandidat otomatis, semantic matching, dan analisis skill gap diaktifkan pada
          fase AI berikutnya. Lowongan yang Anda terbitkan sekarang sudah memakai struktur skill
          berbobot (wajib 60% / nilai tambah 40%) yang siap diproses mesin matching.
        </p>
      </Card>
    </div>
  );
}
