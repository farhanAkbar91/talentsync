import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { fetchPublicJobs, type Job, type Page } from "../../lib/api";
import { employmentTypeLabels, formatDate, formatSalary, workModeLabels } from "../../lib/format";
import { EmptyState, Spinner } from "../../components/ui";

export function JobCard({ job }: { job: Job }) {
  const salaryText = formatSalary(job.salary_min, job.salary_max, job.salary_currency);

  return (
    <article className="bg-surface-container-lowest rounded-xl p-5 sm:p-6 border border-slate-200 flex flex-col gap-4 group">
      {/* Header row: Title + Company + Badges */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div className="flex items-start gap-3 sm:gap-4 min-w-0">
          <div className="w-11 h-11 sm:w-12 sm:h-12 rounded-lg bg-surface-container flex items-center justify-center shrink-0 group-hover:bg-primary-fixed transition-colors">
            <span className="material-symbols-outlined text-primary text-[22px] sm:text-[24px]">
              work
            </span>
          </div>
          <div className="flex flex-col min-w-0">
            <Link
              to={`/app/jobs/${job.id}`}
              className="text-base sm:text-lg font-semibold text-on-surface hover:text-primary transition-colors tracking-tight break-words"
            >
              {job.title}
            </Link>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-secondary text-xs sm:text-sm">
              <span className="font-medium text-on-surface">{job.company.name}</span>
              {job.location_text && (
                <>
                  <span className="text-secondary/40">•</span>
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-[14px]">location_on</span>
                    {job.location_text}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Badges: Employment Type & Mode */}
        <div className="flex items-center gap-1.5 shrink-0 self-start sm:self-auto">
          <span className="px-2.5 py-1 rounded bg-secondary-container text-on-secondary-fixed text-xs font-medium">
            {employmentTypeLabels[job.employment_type] ?? job.employment_type}
          </span>
          <span className="px-2.5 py-1 rounded bg-primary-fixed text-primary text-xs font-semibold">
            {workModeLabels[job.work_mode] ?? job.work_mode}
          </span>
        </div>
      </div>

      {/* Description Snippet */}
      {job.description && (
        <p className="text-sm text-on-surface-variant leading-relaxed line-clamp-2">
          {job.description}
        </p>
      )}

      {/* Metadata Line */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 px-3 sm:px-4 bg-surface-container-low rounded-lg text-secondary text-xs">
        <div className="flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">payments</span>
          <span>
            Gaji: <strong className="text-on-surface font-medium">{salaryText}</strong>
          </span>
        </div>
        <span className="text-secondary/40 hidden sm:inline">•</span>
        <div className="flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[16px]">calendar_today</span>
          <span>Diposting {formatDate(job.posted_at)}</span>
        </div>
        {job.closing_at && (
          <>
            <span className="text-secondary/40 hidden sm:inline">•</span>
            <div className="flex items-center gap-1.5 text-error">
              <span className="material-symbols-outlined text-[16px]">hourglass_bottom</span>
              <span>Batas: {formatDate(job.closing_at)}</span>
            </div>
          </>
        )}
      </div>

      {/* Footer: Skill Tags & Detail CTA */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
        <div className="flex flex-wrap items-center gap-1.5">
          {job.skills.slice(0, 6).map((s) => (
            <span
              key={s.name}
              className={
                "px-2.5 py-1 rounded-full text-xs font-medium " +
                (s.required
                  ? "bg-primary-fixed text-primary font-semibold"
                  : "bg-surface-container text-on-surface-variant")
              }
            >
              {s.name}
            </span>
          ))}
        </div>
        <Link
          to={`/app/jobs/${job.id}`}
          className="h-9 sm:h-10 px-4 rounded-lg bg-surface-container-high hover:bg-primary-fixed text-primary text-xs sm:text-sm font-semibold transition-colors flex items-center justify-center gap-1.5 self-end sm:self-auto shrink-0"
        >
          <span>Lihat Detail</span>
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </Link>
      </div>
    </article>
  );
}

function JobPagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (p: number) => void;
}) {
  if (pages <= 1) return null;

  let items: (number | "...")[] = [];
  if (pages <= 7) {
    items = Array.from({ length: pages }, (_, i) => i + 1);
  } else if (page <= 4) {
    items = [1, 2, 3, 4, 5, "...", pages];
  } else if (page >= pages - 3) {
    items = [1, "...", pages - 4, pages - 3, pages - 2, pages - 1, pages];
  } else {
    items = [1, "...", page - 1, page, page + 1, "...", pages];
  }

  return (
    <nav
      aria-label="Navigasi halaman lowongan"
      className="flex items-center justify-between w-full py-4 pt-6 border-t border-slate-200 gap-2"
    >
      {/* Previous button */}
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        className="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg border border-slate-200 bg-surface-container-lowest text-xs sm:text-sm font-semibold text-on-surface hover:bg-surface-container-low disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
      >
        <span>←</span>
        <span>Sebelumnya</span>
      </button>

      {/* Page Numbers */}
      <div className="flex items-center gap-1 sm:gap-1.5">
        {items.map((item, idx) => {
          if (item === "...") {
            return (
              <span
                key={`ellipsis-${idx}`}
                className="hidden sm:inline-flex px-1.5 text-xs text-secondary font-bold select-none"
              >
                …
              </span>
            );
          }
          const isCurrent = item === page;
          const isNear = Math.abs(item - page) <= 1;
          return (
            <button
              key={`page-${item}`}
              type="button"
              onClick={() => onChange(item)}
              aria-current={isCurrent ? "page" : undefined}
              className={
                "min-w-8 h-8 sm:min-w-10 sm:h-10 px-2 sm:px-3 rounded-lg text-xs sm:text-sm font-semibold transition-colors flex items-center justify-center " +
                (isNear ? "inline-flex " : "hidden sm:inline-flex ") +
                (isCurrent
                  ? "bg-primary-container text-on-primary font-bold"
                  : "border border-slate-200 bg-surface-container-lowest text-on-surface hover:bg-surface-container-low")
              }
            >
              {item}
            </button>
          );
        })}
      </div>

      {/* Next button */}
      <button
        type="button"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
        className="inline-flex items-center gap-1.5 px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg border border-slate-200 bg-surface-container-lowest text-xs sm:text-sm font-semibold text-on-surface hover:bg-surface-container-low disabled:opacity-40 disabled:cursor-not-allowed transition-colors shrink-0"
      >
        <span>Selanjutnya</span>
        <span>→</span>
      </button>
    </nav>
  );
}

export default function JobDiscovery() {
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
      if (seq !== seqRef.current) return;
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
    <div className="flex flex-col gap-6">
      {/* Top Title Section - directly starts with page title */}
      <div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
          Cari Lowongan
        </h1>
        <p className="mt-1 text-sm text-secondary">
          Lowongan aktif dari perusahaan di TalentSync AI.
        </p>
      </div>

      {/* Search & Multi-Filter Control Unit */}
      <div className="bg-surface-container-lowest rounded-xl border border-slate-200 p-4 sm:p-5">
        <form
          className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center"
          onSubmit={(e) => e.preventDefault()}
        >
          {/* Keyword Field */}
          <div className="md:col-span-4 relative flex items-center">
            <span className="material-symbols-outlined absolute left-3 text-secondary text-[20px] pointer-events-none">
              search
            </span>
            <input
              type="text"
              placeholder="Cari judul pekerjaan…"
              value={qInput}
              onChange={(e) => setQInput(e.target.value)}
              className="w-full h-11 pl-10 pr-3 bg-surface-container-low rounded-lg text-on-surface placeholder:text-secondary text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container/30 transition-all border border-transparent focus:border-primary-container"
            />
          </div>

          {/* Location Field */}
          <div className="md:col-span-3 relative flex items-center">
            <span className="material-symbols-outlined absolute left-3 text-secondary text-[20px] pointer-events-none">
              location_on
            </span>
            <input
              type="text"
              placeholder="Lokasi…"
              value={locInput}
              onChange={(e) => setLocInput(e.target.value)}
              className="w-full h-11 pl-10 pr-3 bg-surface-container-low rounded-lg text-on-surface placeholder:text-secondary text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container/30 transition-all border border-transparent focus:border-primary-container"
            />
          </div>

          {/* Job Type Select */}
          <div className="md:col-span-2 relative flex items-center">
            <select
              value={employmentType}
              onChange={(e) => {
                setEmploymentType(e.target.value);
                setPage(1);
              }}
              className="w-full h-11 px-3 bg-surface-container-low rounded-lg text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container/30 transition-all appearance-none cursor-pointer pr-8 border border-transparent focus:border-primary-container"
            >
              <option value="">Semua Tipe</option>
              {Object.entries(employmentTypeLabels).map(([val, lbl]) => (
                <option key={val} value={val}>
                  {lbl}
                </option>
              ))}
            </select>
            <span className="material-symbols-outlined absolute right-2.5 text-secondary text-[18px] pointer-events-none">
              expand_more
            </span>
          </div>

          {/* Work Mode Select */}
          <div className="md:col-span-2 relative flex items-center">
            <select
              value={workMode}
              onChange={(e) => {
                setWorkMode(e.target.value);
                setPage(1);
              }}
              className="w-full h-11 px-3 bg-surface-container-low rounded-lg text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container/30 transition-all appearance-none cursor-pointer pr-8 border border-transparent focus:border-primary-container"
            >
              <option value="">Semua Mode</option>
              {Object.entries(workModeLabels).map(([val, lbl]) => (
                <option key={val} value={val}>
                  {lbl}
                </option>
              ))}
            </select>
            <span className="material-symbols-outlined absolute right-2.5 text-secondary text-[18px] pointer-events-none">
              expand_more
            </span>
          </div>

          {/* Action indicator icon */}
          <div className="md:col-span-1">
            <div className="w-full h-11 bg-primary-container text-on-primary rounded-lg flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">manage_search</span>
            </div>
          </div>
        </form>
      </div>

      {/* Results Count Info */}
      {result && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm text-secondary">
            <span>
              <strong className="text-on-surface font-semibold">{result.total}</strong> lowongan
              ditemukan
            </span>
            <span className="text-secondary/40">•</span>
            <span className="text-xs uppercase tracking-wider text-secondary bg-surface-container-high px-2 py-0.5 rounded font-semibold">
              Live Feed
            </span>
          </div>
        </div>
      )}

      {/* Job Listings or States */}
      {loading ? (
        <Spinner />
      ) : error ? (
        <p className="text-sm text-error bg-surface-container-lowest p-4 rounded-xl border border-slate-200">
          {error}
        </p>
      ) : result && result.items.length > 0 ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-4">
            {result.items.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
          <JobPagination page={result.page} pages={result.pages} onChange={setPage} />
        </div>
      ) : (
        <EmptyState
          title="Tidak ada lowongan yang cocok"
          description="Coba ubah kata kunci atau filter pencarian Anda."
        />
      )}
    </div>
  );
}
