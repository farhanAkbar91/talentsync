import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { extractErrorMessage, fetchHrJobs, fetchMeSummary, type Job, type Page } from "../../lib/api";
import { formatDate, jobStatusLabels } from "../../lib/format";
import { Alert, Badge, Button, Card, EmptyState, Pagination, Select, Spinner } from "../../components/ui";

export default function HrJobsPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<Job> | null>(null);
  const [hasCompany, setHasCompany] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [jobs, summary] = await Promise.all([
        fetchHrJobs({ status: statusFilter || undefined, page, size: 10 }),
        fetchMeSummary(),
      ]);
      setResult(jobs);
      setHasCompany(Boolean(summary.company));
    } catch (err) {
      const msg = extractErrorMessage(err);
      setError(msg);
      setHasCompany(msg.toLowerCase().includes("perusahaan"));
    }
  }, [statusFilter, page]);

  useEffect(() => {
    void load();
  }, [load]);

  if (hasCompany === false) {
    return (
      <Card>
        <h1 className="text-xl font-bold text-slate-800">Profil Perusahaan Diperlukan</h1>
        <p className="mt-2 text-sm text-slate-500">
          Buat profil perusahaan terlebih dahulu sebelum memasang lowongan.
        </p>
        <Link to="/hr/company">
          <Button className="mt-4">Buat Profil Perusahaan</Button>
        </Link>
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Kelola Lowongan</h1>
          <p className="mt-1 text-sm text-slate-500">Semua lowongan milik perusahaan Anda.</p>
        </div>
        <Link to="/hr/jobs/new">
          <Button>+ Buat Lowongan Baru</Button>
        </Link>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <Card className="w-56 p-3">
        <Select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Semua Status</option>
          {Object.entries(jobStatusLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Card>

      {!result ? (
        <Spinner />
      ) : result.items.length === 0 ? (
        <EmptyState title="Belum ada lowongan" description="Buat lowongan pertama Anda." />
      ) : (
        <>
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-3">Posisi</th>
                  <th className="px-4 py-3">Lokasi &amp; Tipe</th>
                  <th className="px-4 py-3">Diposting</th>
                  <th className="px-4 py-3">Batas</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((job) => (
                  <tr key={job.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <Link to={`/hr/jobs/${job.id}`} className="font-medium text-slate-700 hover:text-primary-700">
                        {job.title}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {job.location_text ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{formatDate(job.posted_at)}</td>
                    <td className="px-4 py-3 text-slate-500">{formatDate(job.closing_at)}</td>
                    <td className="px-4 py-3">
                      <Badge value={job.status ?? "draft"} label={jobStatusLabels[job.status ?? "draft"]} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/hr/jobs/${job.id}`}>
                        <Button variant="secondary">Detail</Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Pagination page={result.page} pages={result.pages} onChange={setPage} />
        </>
      )}
    </div>
  );
}
