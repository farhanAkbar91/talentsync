import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { extractDetailedErrorMessage, fetchMyApplications, type MyApplicationRow } from "../../lib/api";
import { applicationStatusLabels, formatDateTime } from "../../lib/format";
import { Alert, Button, Card, EmptyState, Spinner, cn } from "../../components/ui";

/**
 * M8 — Lamaran Saya: daftar lamaran kandidat (GET /applications/mine,
 * terbaru lebih dulu) dengan chip status & pratinjau cover letter.
 */

type PageState = "loading" | "ready" | "error";

const statusChipCls: Record<MyApplicationRow["status"], string> = {
  submitted: "bg-slate-100 text-slate-600",
  reviewed: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  shortlisted: "bg-teal-50 text-teal-700 ring-1 ring-teal-200",
  hired: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  rejected: "bg-red-50 text-red-600 ring-1 ring-red-200",
};

function StatusChip({ status }: { status: MyApplicationRow["status"] }) {
  return (
    <span
      data-testid="application-status"
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        statusChipCls[status],
      )}
    >
      {applicationStatusLabels[status] ?? status}
    </span>
  );
}

function CoverLetterPreview({ text }: { text: string }) {
  const truncated = text.length > 160;
  return (
    <p className="mt-1 max-w-2xl text-xs leading-relaxed text-slate-400">
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
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Lamaran Saya</h1>
        <p className="mt-1 text-sm text-slate-500">
          Semua lamaran yang Anda kirim beserta statusnya.
        </p>
      </div>

      {state === "error" && (
        <Card className="space-y-3">
          <Alert kind="error">{loadError ?? "Gagal memuat lamaran."}</Alert>
          <Button onClick={() => setReloadKey((k) => k + 1)}>Coba Lagi</Button>
        </Card>
      )}

      {state === "ready" && items.length === 0 && (
        <EmptyState
          title="Belum ada lamaran"
          description="Jelajahi lowongan yang cocok dan kirim lamaran pertama Anda."
        >
          <Link to="/app/recommendations">
            <Button className="mt-4">Lihat Rekomendasi</Button>
          </Link>
        </EmptyState>
      )}

      {state === "ready" && items.length > 0 && (
        <div className="space-y-3" data-testid="application-list">
          {items.map((row) => (
            <Card key={row.id} className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <Link
                  to={`/app/jobs/${row.job_id}`}
                  className="text-base font-semibold text-primary-700 underline decoration-primary-200 underline-offset-2 hover:decoration-primary-500"
                >
                  {row.job_title}
                </Link>
                <p className="mt-0.5 text-sm text-slate-500">
                  {row.company || "—"} · Dilamar {formatDateTime(row.applied_at)}
                </p>
                {row.cover_letter && row.cover_letter.trim() !== "" && (
                  <CoverLetterPreview text={row.cover_letter.trim()} />
                )}
              </div>
              <StatusChip status={row.status} />
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
