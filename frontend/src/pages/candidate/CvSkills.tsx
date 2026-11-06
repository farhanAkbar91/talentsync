import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import {
  applyCvSkills,
  extractDetailedErrorMessage,
  fetchCvSkills,
  type CandidateSkillSuggestion,
} from "../../lib/api";
import { toConfidencePercent } from "../../lib/format";
import { Alert, Button, Card, EmptyState, Spinner, cn } from "../../components/ui";

/**
 * M2 — Skills terstandardisasi: kandidat memeriksa hasil pemetaan skill CV
 * ke kamus standar, lalu menerapkan yang dipilih ke profilnya
 * (GET/POST /cvs/{id}/skills[/apply]).
 */

const secondaryLinkCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50";

const chipCls =
  "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-600";

function skillTypeLabel(t: string): string {
  if (t === "hard") return "Hard skill";
  if (t === "soft") return "Soft skill";
  return t;
}

function methodLabel(method: CandidateSkillSuggestion["extraction_method"]): string {
  if (method === "explicit") return "Eksplisit";
  if (method === "inferred") return "Inferred";
  return "Manual";
}

function confidenceChipCls(pct: number): string {
  if (pct >= 80) return "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
  if (pct >= 60) return "bg-amber-50 text-amber-700 ring-1 ring-amber-200";
  return "bg-red-50 text-red-600 ring-1 ring-red-200";
}

function ConfidenceChip({ conf }: { conf: number }) {
  const pct = toConfidencePercent(conf);
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        confidenceChipCls(pct),
      )}
    >
      {pct}%
    </span>
  );
}

function SkillRow({
  item,
  selected,
  onToggle,
}: {
  item: CandidateSkillSuggestion;
  selected: boolean;
  onToggle: (id: string, next: boolean) => void;
}) {
  const accepted = item.status === "accepted";
  return (
    <li className="flex items-start gap-3 py-4 first:pt-0 last:pb-0">
      <input
        type="checkbox"
        className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-primary-600 disabled:cursor-not-allowed"
        checked={accepted ? true : selected}
        disabled={accepted}
        aria-label={`Pilih ${item.canonical.name}`}
        onChange={(e) => onToggle(item.id, e.target.checked)}
      />
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <span data-skill-name className="text-sm font-semibold text-slate-800">
            {item.canonical.name}
          </span>
          <span className={chipCls}>{item.canonical.category}</span>
          <span className={chipCls}>{skillTypeLabel(item.canonical.skill_type)}</span>
          {item.needs_review && (
            <span className="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
              Perlu review — mungkin salah peta
            </span>
          )}
          {accepted && (
            <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
              Sudah diterapkan
            </span>
          )}
        </div>
        <p className="text-xs text-slate-400">
          raw: <span className="italic">“{item.raw_name}”</span>
        </p>
        <p className="text-xs text-slate-400">
          <span className={cn(item.extraction_method === "inferred" && "italic")}>
            {methodLabel(item.extraction_method)}
          </span>
          {item.extraction_method === "inferred" && (
            <span> — dari deskripsi pengalaman/proyek, bukan pernyataan langsung</span>
          )}
        </p>
        {item.evidence && item.evidence.trim() !== "" && (
          <p className="text-xs italic text-slate-400">Bukti: “{item.evidence.trim()}”</p>
        )}
        {item.suggestions.length > 0 && (
          <p className="text-xs text-slate-400">
            Kemungkinan: {item.suggestions.map((s) => s.name).join(", ")}
          </p>
        )}
      </div>
      <ConfidenceChip conf={item.confidence} />
    </li>
  );
}

type LoadState = "loading" | "error" | "empty" | "ready";

export default function CvSkillsPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<LoadState>("loading");
  const [items, setItems] = useState<CandidateSkillSuggestion[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [appliedCount, setAppliedCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setState("error");
      setLoadError("CV tidak ditemukan.");
      return;
    }
    setState("loading");
    fetchCvSkills(id)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setSelected(
          new Set(
            res.items
              .filter((it) => it.status === "suggested" && !it.needs_review)
              .map((it) => it.id),
          ),
        );
        setState(res.items.length === 0 ? "empty" : "ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          axios.isAxiosError(err) && err.response?.status === 404
            ? "Skill tidak ditemukan atau CV bukan milik Anda."
            : extractDetailedErrorMessage(err),
        );
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  function toggleSkill(skillId: string, next: boolean) {
    setSelected((prev) => {
      const nextSet = new Set(prev);
      if (next) nextSet.add(skillId);
      else nextSet.delete(skillId);
      return nextSet;
    });
  }

  async function handleApply() {
    if (!id || applying || selected.size === 0) return;
    setApplying(true);
    setApplyError(null);
    setAppliedCount(null);
    try {
      const res = await applyCvSkills(id, [...selected]);
      setAppliedCount(res.applied);
      setSelected(new Set());
    } catch (err) {
      setApplyError(extractDetailedErrorMessage(err));
      return;
    } finally {
      setApplying(false);
    }
    // Segarkan daftar agar baris yang baru diterapkan berubah jadi "Sudah diterapkan".
    try {
      const fresh = await fetchCvSkills(id);
      setItems(fresh.items);
    } catch {
      /* daftar lama tetap ditampilkan */
    }
  }

  const shortId = id ? `${id.slice(0, 8)}…` : "—";

  if (state === "loading") return <Spinner label="Memuat skill terstandardisasi…" />;

  if (state === "error") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Skills terstandardisasi</h1>
        <Card className="space-y-3">
          <Alert kind="error">{loadError ?? "Terjadi kesalahan."}</Alert>
          <Link to="/app/cv" className={secondaryLinkCls}>
            Kembali ke CV Saya
          </Link>
        </Card>
      </div>
    );
  }

  if (state === "empty") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Skills terstandardisasi</h1>
        <EmptyState
          title="Belum ada skill terstandardisasi"
          description="Skill dipetakan ke kamus standar setelah ekstraksi CV dikonfirmasi. Buka halaman review dan konfirmasi ekstraksi terlebih dahulu."
        />
        <div className="flex flex-wrap gap-2">
          {id && (
            <Link to={`/app/cv/${id}/review`} className={secondaryLinkCls}>
              Review ekstraksi
            </Link>
          )}
          <Link to="/app/cv" className={secondaryLinkCls}>
            Kembali ke CV Saya
          </Link>
        </div>
      </div>
    );
  }

  const selectableCount = items.filter((it) => it.status !== "accepted").length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Skills terstandardisasi</h1>
          <p className="mt-1 text-sm text-slate-500">
            CV <span className="font-medium text-slate-600">{shortId}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/app/cv/${id}/review`} className={secondaryLinkCls}>
            Review ekstraksi
          </Link>
          <Link to="/app/cv" className={secondaryLinkCls}>
            CV Saya
          </Link>
        </div>
      </div>

      <p className="text-sm text-slate-500">
        Hasil bacaan AI dipetakan ke kamus skill standar. Periksa petanya — skill yang Anda terapkan
        akan muncul di profil dan dipakai untuk pencocokan lowongan.
      </p>

      {applyError && <Alert kind="error">{applyError}</Alert>}
      {appliedCount !== null && (
        <Alert kind="success">
          {appliedCount} skill diterapkan ke profil.{" "}
          <Link to="/app/profile" className="font-semibold underline">
            Lihat profil
          </Link>
        </Alert>
      )}

      <Card className="p-0">
        <ul className="divide-y divide-slate-100 px-5">
          {items.map((item) => (
            <SkillRow
              key={item.id}
              item={item}
              selected={selected.has(item.id)}
              onToggle={toggleSkill}
            />
          ))}
        </ul>
      </Card>

      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-5">
        <Button
          onClick={handleApply}
          disabled={applying || selected.size === 0}
        >
          {applying ? "Menerapkan…" : "Terapkan ke Profil"}
        </Button>
        <Link to="/app/cv" className={secondaryLinkCls}>
          Kembali
        </Link>
        <span className="text-xs text-slate-400">
          {selected.size} dari {selectableCount} skill dipilih
        </span>
      </div>
    </div>
  );
}
