import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchPublicJobs, type Job, type Page } from "../../lib/api";
import { employmentTypeLabels, formatDate, formatSalary, workModeLabels } from "../../lib/format";
import { Badge, Button, Card, EmptyState, Input, Pagination, Select, Spinner } from "../../components/ui";

export function JobCard({ job }: { job: Job }) {
  return (
    <Card className="transition hover:ring-primary-300">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to={`/app/jobs/${job.id}`}
            className="text-base font-bold text-slate-800 hover:text-primary-700"
          >
            {job.title}
          </Link>
          <p className="mt-0.5 text-sm text-slate-500">
            {job.company.name}
            {job.location_text ? ` • ${job.location_text}` : ""}
          </p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Badge value={job.employment_type} label={employmentTypeLabels[job.employment_type] ?? job.employment_type} />
          <Badge value={job.work_mode} label={workModeLabels[job.work_mode] ?? job.work_mode} />
        </div>
      </div>
      <p className="mt-2 line-clamp-2 text-sm text-slate-600">{job.description}</p>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="font-medium text-slate-700">{formatSalary(job.salary_min, job.salary_max, job.salary_currency)}</span>
        <span>Diposting {formatDate(job.posted_at)}</span>
        {job.closing_at && <span>Batas: {formatDate(job.closing_at)}</span>}
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {job.skills.slice(0, 6).map((s) => (
          <span
            key={s.name}
            className={
              "rounded-full px-2 py-0.5 text-xs font-medium " +
              (s.required ? "bg-primary-100 text-primary-700" : "bg-slate-100 text-slate-500")
            }
          >
            {s.name}
          </span>
        ))}
      </div>
      <div className="mt-3">
        <Link to={`/app/jobs/${job.id}`}>
          <Button variant="secondary">Lihat Detail</Button>
        </Link>
      </div>
    </Card>
  );
}

export default function JobDiscovery() {
  // Input teks di-debounce; filter select langsung.
  const [qInput, setQInput] = useState("");
  const [locInput, setLocInput] = useState("");
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [workMode, setWorkMode] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<Job> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Guard race: respons dari request lama tidak boleh menimpa hasil request terbaru.
  const seqRef = useRef(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(qInput);
      setLocation(locInput);
      setPage(1);
    }, 350);
    return () => clearTimeout(timer);
  }, [qInput, locInput]);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPublicJobs({
        q: q || undefined,
        location: location || undefined,
        employment_type: employmentType || undefined,
        work_mode: workMode || undefined,
        page,
        size: 8,
      });
      if (seq !== seqRef.current) return; // sudah ada request lebih baru
      setResult(data);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setError(err instanceof Error ? err.message : "Gagal memuat lowongan.");
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, [q, location, employmentType, workMode, page]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Cari Lowongan</h1>
        <p className="mt-1 text-sm text-slate-500">
          Lowongan aktif dari perusahaan di TalentSync AI.
        </p>
      </div>

      <Card className="grid gap-3 sm:grid-cols-5">
        <Input
          className="sm:col-span-2"
          placeholder="Cari judul pekerjaan…"
          value={qInput}
          onChange={(e) => setQInput(e.target.value)}
        />
        <Input
          placeholder="Lokasi…"
          value={locInput}
          onChange={(e) => setLocInput(e.target.value)}
        />
        <Select
          value={employmentType}
          onChange={(e) => {
            setEmploymentType(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Semua Tipe</option>
          {Object.entries(employmentTypeLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          value={workMode}
          onChange={(e) => {
            setWorkMode(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Semua Mode</option>
          {Object.entries(workModeLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Card>

      {loading ? (
        <Spinner />
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : result && result.items.length > 0 ? (
        <>
          <p className="text-xs text-slate-400">{result.total} lowongan ditemukan</p>
          <div className="grid gap-4">
            {result.items.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
          <Pagination page={result.page} pages={result.pages} onChange={setPage} />
        </>
      ) : (
        <EmptyState
          title="Tidak ada lowongan yang cocok"
          description="Coba ubah kata kunci atau filter pencarian Anda."
        />
      )}
    </div>
  );
}
