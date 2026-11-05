import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function cn(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

// --- Button ---

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-primary-600 text-white hover:bg-primary-700 disabled:bg-primary-300",
  secondary:
    "bg-white text-slate-700 ring-1 ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
  ghost: "text-primary-700 hover:bg-primary-50",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed",
        buttonVariants[variant],
        className,
      )}
      {...props}
    />
  );
}

// --- Form fields ---

export function Field({
  label,
  required,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">
        {label}
        {required && <span className="text-red-500"> *</span>}
      </span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-600">{error}</span>}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full rounded-lg border-0 bg-primary-50/60 px-3 py-2 text-sm text-slate-800 ring-1 ring-slate-200 outline-none placeholder:text-slate-400 focus:bg-white focus:ring-2 focus:ring-primary-500",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full rounded-lg border-0 bg-primary-50/60 px-3 py-2 text-sm text-slate-800 ring-1 ring-slate-200 outline-none focus:bg-white focus:ring-2 focus:ring-primary-500",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full rounded-lg border-0 bg-primary-50/60 px-3 py-2 text-sm text-slate-800 ring-1 ring-slate-200 outline-none placeholder:text-slate-400 focus:bg-white focus:ring-2 focus:ring-primary-500",
        className,
      )}
      rows={4}
      {...props}
    />
  );
}

// --- Layout primitives ---

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200", className)}>
      {children}
    </div>
  );
}

export function Alert({ kind, children }: { kind: "error" | "success" | "info"; children: ReactNode }) {
  const styles = {
    error: "bg-red-50 text-red-700 ring-red-200",
    success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    info: "bg-primary-50 text-primary-700 ring-primary-200",
  };
  return <div className={cn("rounded-lg px-4 py-3 text-sm ring-1", styles[kind])}>{children}</div>;
}

// --- Badge ---

const badgeColors: Record<string, string> = {
  draft: "bg-slate-100 text-slate-600",
  active: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  paused: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  closed: "bg-red-50 text-red-600 ring-1 ring-red-200",
  expired: "bg-red-50 text-red-600 ring-1 ring-red-200",
  archived: "bg-slate-100 text-slate-400",
  pending: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  processing: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  ready: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  failed: "bg-red-50 text-red-600 ring-1 ring-red-200",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        badgeColors[value] ?? "bg-slate-100 text-slate-600",
      )}
    >
      {label ?? value}
    </span>
  );
}

// --- Lainnya ---

export function Spinner({ label = "Memuat…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-10 text-sm text-slate-500">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-primary-200 border-t-primary-600" />
      {label}
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 px-6 py-10 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {description && <p className="mt-1 text-xs text-slate-400">{description}</p>}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-1 py-4">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ‹
      </Button>
      <span className="px-3 text-sm text-slate-600">
        Halaman {page} dari {pages}
      </span>
      <Button variant="secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        ›
      </Button>
    </div>
  );
}

export function TagInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg bg-primary-50/60 p-2 ring-1 ring-slate-200">
      {value.map((tag) => (
        <span
          key={tag}
          className="inline-flex items-center gap-1 rounded-full bg-primary-100 px-2.5 py-1 text-xs font-medium text-primary-700"
        >
          {tag}
          <button
            type="button"
            className="text-primary-400 hover:text-primary-700"
            onClick={() => onChange(value.filter((t) => t !== tag))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="min-w-32 flex-1 border-0 bg-transparent text-sm outline-none placeholder:text-slate-400"
        placeholder={placeholder ?? "Ketik lalu Enter…"}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            const v = e.currentTarget.value.trim();
            if (v && !value.some((t) => t.toLowerCase() === v.toLowerCase())) {
              onChange([...value, v]);
            }
            e.currentTarget.value = "";
          }
        }}
      />
    </div>
  );
}

export function StatCard({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</span>
      <span className="text-2xl font-bold text-slate-800">{value}</span>
      {detail && <span className="text-xs text-slate-500">{detail}</span>}
    </Card>
  );
}
