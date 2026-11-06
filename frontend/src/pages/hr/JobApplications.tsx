import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import {
  downloadCv,
  extractDetailedErrorMessage,
  fetchHrJob,
  fetchHrJobApplications,
  updateApplicationStatus,
  type ApplicationStatus,
  type HrApplicationRow,
} from "../../lib/api";
import { applicationStatusLabels, formatDate } from "../../lib/format";
import { Alert, Badge, Button, Card, EmptyState, Select, Spinner, cn } from "../../components/ui";

/**
 * M9 — Pelamar satu lowongan (HR owner): tabel pelamar + ubah status lamaran
 * (PATCH, optimistic update + toast) + unduh CV pelamar.
 * Status terminal (hired/rejected) tidak dapat diubah lagi.
 */

const STATUS_ORDER: ApplicationStatus[] = [
  "submitted",
  "reviewed",
  "shortlisted",
  "rejected",
  "hired",
];

const TERMINAL_STATUSES: ReadonlySet<ApplicationStatus> = new Set(["hired", "rejected"]);

const statusChipCls: Record<ApplicationStatus, string> = {
  submitted: "bg-slate-100 text-slate-600",
  reviewed: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  shortlisted: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
  hired: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  rejected: "bg-red-50 text-red-600 ring-1 ring-red-200",
};

function StatusChip({ status }: { status: ApplicationStatus }) {
  return (
    <span
      data-testid="application-status-chip"
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        statusChipCls[status],
      )}
    >
      {applicationStatusLabels[status] ?? status}
    </span>
  );
}

function CoverLetterCell({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const truncated = text.length > 120;
  return (
    <div className="max-w-xs">
      <p className={cn("text-xs leading-relaxed text-slate-500", !expanded && "line-clamp-2")}>
        “{text}”
      </p>
      {truncated && (
        <button
          type="button"
          className="mt-0.5 text-[11px] font-semibold text-primary-700 hover:underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Sembunyikan" : "Tampilkan semua"}
        </button>
      )}
    </div>
  );
}

function Toast({ text }: { text: string }) {
  return (
    <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-slate-800 px-4 py-2.5 text-sm font-medium text-white shadow-lg">
      {text}
    </div>
  );
}

export default function HrJobApplicationsPage() {
  const { id } = useParams<{ id: string }>();
  const [jobTitle, setJobTitle] = useState<string | null>(null);
  const [rows, setRows] = useState<HrApplicationRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [toast, setToast] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  function showToast(text: string) {
    setToast(text);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3_000);
  }

  async function handleDownloadCv(cvId: string) {
    try {
      await downloadCv(cvId, `cv-${cvId.slice(0, 8)}.pdf`);
    } catch (err) {
      showToast(`Gagal mengunduh CV: ${extractDetailedErrorMessage(err)}`);
    }
  }

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    fetchHrJob(id)
      .then((job) => {
        if (!cancelled) setJobTitle(job.title);
      })
      .catch(() => {
        // Judul hanya pelengkap — daftar pelamar tetap dimuat.
      });
    fetchHrJobApplications(id)
      .then((res) => {
        if (cancelled) return;
        setRows(res.items ?? []);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(extractDetailedErrorMessage(err));
        setRows([]);
      });
    return () => {
      cancelled = true;
    };
  }, [id, reloadKey]);

  useEffect(
    () => () => {
      window.clearTimeout(toastTimer.current);
    },
    [],
  );

  async function handleStatusChange(row: HrApplicationRow, next: ApplicationStatus) {
    if (!id || next === row.status) return;
    // Optimistic update — rollback bila PATCH gagal.
    const prev = rows;
    setRows((current) =>
      (current ?? []).map((r) => (r.id === row.id ? { ...r, status: next } : r)),
    );
    try {
      await updateApplicationStatus(row.id, next);
      showToast(`Status ${row.candidate_name} → ${applicationStatusLabels[next]}`);
    } catch (err) {
      setRows(prev ?? []);
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setRowError(
        status === 409
          ? `Status lamaran ${row.candidate_name} sudah terminal dan tidak dapat diubah.`
          : `Gagal mengubah status: ${extractDetailedErrorMessage(err)}`,
      );
    }
  }

  if (rows === null && !loadError) return <Spinner label="Memuat pelamar…" />;

  return (
    <div className="space-y-5">
      <Link to={id ? `/hr/jobs/${id}` : "/hr/jobs"} className="text-sm font-medium text-primary-700">
        ← Kembali ke detail lowongan
      </Link>

      <div>
        <h1 className="text-2xl font-bold text-slate-800">Pelamar</h1>
        <p className="mt-1 text-sm text-slate-500">
          {jobTitle ? jobTitle : "Lowongan"}
          {rows ? ` · ${rows.length} pelamar` : ""}
        </p>
      </div>

      {rowError && <Alert kind="error">{rowError}</Alert>}
      {loadError && (
        <Card className="space-y-3">
          <Alert kind="error">{loadError}</Alert>
          <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
        </Card>
      )}

      {rows !== null && !loadError && rows.length === 0 && (
        <EmptyState title="Belum ada pelamar" description="Lamaran kandidat akan muncul di sini." />
      )}

      {rows !== null && !loadError && rows.length > 0 && (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-left text-sm" data-testid="hr-applications-table">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">Kandidat</th>
                <th className="px-4 py-3">Dilamar</th>
                <th className="px-4 py-3">Cover Letter</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">CV</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const terminal = TERMINAL_STATUSES.has(row.status);
                return (
                  <tr key={row.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 font-medium text-slate-700">{row.candidate_name}</td>
                    <td className="px-4 py-3 text-slate-500">{formatDate(row.applied_at)}</td>
                    <td className="px-4 py-3">
                      {row.cover_letter && row.cover_letter.trim() !== "" ? (
                        <CoverLetterCell text={row.cover_letter.trim()} />
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {terminal ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          <StatusChip status={row.status} />
                          <span className="text-[11px] text-slate-400">(final)</span>
                        </div>
                      ) : (
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusChip status={row.status} />
                          <Select
                            aria-label={`Ubah status ${row.candidate_name}`}
                            className="w-36"
                            value={row.status}
                            onChange={(e) =>
                              void handleStatusChange(row, e.target.value as ApplicationStatus)
                            }
                          >
                            {STATUS_ORDER.map((s) => (
                              <option key={s} value={s}>
                                {applicationStatusLabels[s] ?? s}
                              </option>
                            ))}
                          </Select>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {row.cv_id ? (
                        <button
                          type="button"
                          className="text-sm font-semibold text-primary-700 hover:underline"
                          onClick={() => void handleDownloadCv(row.cv_id as string)}
                        >
                          Unduh CV
                        </button>
                      ) : (
                        <Badge value="archived" label="Tidak ada" />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {toast && <Toast text={toast} />}
    </div>
  );
}
