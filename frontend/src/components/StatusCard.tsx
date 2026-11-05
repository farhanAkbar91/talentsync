export type LoadState = "loading" | "ok" | "fail";

interface StatusCardProps {
  title: string;
  state: LoadState;
  detail?: string;
}

const stateStyles: Record<LoadState, { dot: string; label: string }> = {
  loading: { dot: "bg-amber-400", label: "Memeriksa…" },
  ok: { dot: "bg-emerald-500", label: "OK" },
  fail: { dot: "bg-red-500", label: "Gagal" },
};

export default function StatusCard({ title, state, detail }: StatusCardProps) {
  const style = stateStyles[state];
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
        <span className="flex items-center gap-2 text-xs font-medium text-slate-500">
          <span className={`h-2.5 w-2.5 rounded-full ${style.dot}`} />
          {style.label}
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-slate-600">
        {detail ?? "—"}
      </p>
    </div>
  );
}
