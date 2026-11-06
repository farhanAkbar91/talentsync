import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createJob,
  extractErrorMessage,
  fetchHrJob,
  fetchSkillAutocomplete,
  transitionJob,
  updateJob,
  type Job,
  type SkillAutocompleteItem,
} from "../../lib/api";
import { employmentTypeLabels, workModeLabels } from "../../lib/format";
import { Alert, Button, Card, Field, Input, Select, Spinner, Textarea, cn } from "../../components/ui";

/**
 * Form pembuatan & pengubahan lowongan (Figma: "Buat Lowongan Baru").
 * M2 — input skill berupa combobox autocomplete ke kamus standar:
 * skill dikenal → chip kanonik; teks bebas → chip "tidak dikenal".
 * Payload tetap `{name, required}` — tidak berubah dari M0.
 */

interface SkillChip {
  /** Nama yang dikirim ke backend (kanonik bila dikenal, apa adanya bila tak dikenal). */
  name: string;
  slug: string | null;
  category: string | null;
  known: boolean;
  required: boolean;
}

function chipKey(chip: SkillChip): string {
  return chip.slug ?? chip.name.toLowerCase();
}

function SkillPicker({
  chips,
  onAddKnown,
  onAddRaw,
  onToggle,
  onRemove,
}: {
  chips: SkillChip[];
  onAddKnown: (item: SkillAutocompleteItem) => string | null;
  onAddRaw: (text: string) => string | null;
  onToggle: (index: number) => void;
  onRemove: (index: number) => void;
}) {
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<SkillAutocompleteItem[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const [searching, setSearching] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const seqRef = useRef<number | undefined>(undefined);

  // Debounce 300 ms — jangan panggil API di bawah 2 karakter (kontrak backend).
  useEffect(() => {
    setHint(null);
    const q = query.trim();
    if (q.length < 2) {
      setOptions([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const timer = window.setTimeout(() => {
      const seq = (seqRef.current ?? 0) + 1;
      seqRef.current = seq;
      fetchSkillAutocomplete(q)
        .then((items) => {
          if (seq !== seqRef.current) return;
          setOptions(items);
          setHighlight(-1);
          setOpen(true);
        })
        .catch(() => {
          if (seq !== seqRef.current) return;
          setOptions([]);
        })
        .finally(() => {
          if (seq === seqRef.current) setSearching(false);
        });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  // Tutup dropdown saat klik di luar combobox.
  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (
        containerRef.current &&
        e.target instanceof Node &&
        !containerRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  function resetInput() {
    setQuery("");
    setOptions([]);
    setOpen(false);
    setHighlight(-1);
    setSearching(false);
  }

  function addKnown(item: SkillAutocompleteItem) {
    const result = onAddKnown(item);
    if (result) setHint(result);
    else resetInput();
  }

  function addRaw(text: string) {
    const result = onAddRaw(text);
    if (result) setHint(result);
    else resetInput();
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open || options.length === 0) return;
      setOpen(true);
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setHighlight((h) => {
        const next = h + delta;
        if (next < 0) return options.length - 1;
        if (next >= options.length) return 0;
        return next;
      });
      return;
    }
    if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        setOpen(false);
      }
      return;
    }
    if (e.key === "Enter") {
      // Selalu cegah submit form dari input skill.
      e.preventDefault();
      if (open && highlight >= 0 && highlight < options.length) {
        addKnown(options[highlight]);
        return;
      }
      const q = query.trim();
      if (q.length >= 2) addRaw(q);
    }
  }

  const q = query.trim();
  const showDropdown = open && q.length >= 2;

  return (
    <div className="space-y-2">
      <div className="relative" ref={containerRef}>
        <Input
          role="combobox"
          aria-expanded={showDropdown}
          aria-autocomplete="list"
          autoComplete="off"
          value={query}
          placeholder="Ketik minimal 2 huruf, mis. python…"
          onChange={(e) => {
            const v = e.target.value;
            setQuery(v);
            setOpen(v.trim().length >= 2);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (q.length >= 2) setOpen(true);
          }}
        />
        {showDropdown && (
          <div
            role="listbox"
            aria-label="Saran skill"
            className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-xl bg-white p-1 shadow-lg ring-1 ring-slate-200"
          >
            {searching && options.length === 0 && (
              <p className="px-3 py-2 text-xs text-slate-400">Mencari…</p>
            )}
            {!searching && options.length === 0 && (
              <p className="px-3 py-2 text-xs text-slate-400">
                Tidak ada di kamus — tekan Enter untuk menyimpan “{q}” apa adanya.
              </p>
            )}
            {options.map((opt, i) => (
              <button
                key={opt.id}
                type="button"
                role="option"
                aria-selected={i === highlight}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition",
                  i === highlight ? "bg-primary-50 text-primary-800" : "hover:bg-slate-50",
                )}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => addKnown(opt)}
                onMouseEnter={() => setHighlight(i)}
              >
                <span className="font-medium text-slate-700">{opt.name}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                    {opt.category}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500">
                    {opt.skill_type}
                  </span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {hint && <p className="text-xs text-amber-600">{hint}</p>}

      {chips.length > 0 && (
        <ul className="space-y-2">
          {chips.map((chip, i) => (
            <li
              key={chipKey(chip)}
              className={cn(
                "flex flex-wrap items-center justify-between gap-2 rounded-xl px-3 py-2 ring-1",
                chip.known ? "bg-primary-50/60 ring-slate-200" : "bg-amber-50 ring-amber-300",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-slate-800">{chip.name}</span>
                {chip.category && (
                  <span className="text-xs text-slate-400">{chip.category}</span>
                )}
                {!chip.known && (
                  <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-700 ring-1 ring-amber-300">
                    tidak dikenal
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onToggle(i)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-xs font-semibold ring-1 transition",
                    chip.required
                      ? "bg-primary-600 text-white ring-primary-600 hover:bg-primary-700"
                      : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50",
                  )}
                >
                  {chip.required ? "Wajib" : "Disarankan"}
                </button>
                <button
                  type="button"
                  aria-label={`Hapus ${chip.name}`}
                  onClick={() => onRemove(i)}
                  className="rounded-md px-1.5 py-1 text-lg leading-none text-slate-400 transition hover:text-red-600"
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Form pembuatan & pengubahan lowongan (Figma: "Buat Lowongan Baru", skills 60/40). */
export default function JobForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [responsibilities, setResponsibilities] = useState("");
  const [requirements, setRequirements] = useState("");
  const [category, setCategory] = useState("");
  const [employmentType, setEmploymentType] = useState("full_time");
  const [workMode, setWorkMode] = useState("hybrid");
  const [seniority, setSeniority] = useState("");
  const [locationText, setLocationText] = useState("");
  const [salaryMin, setSalaryMin] = useState("");
  const [salaryMax, setSalaryMax] = useState("");
  const [closingAt, setClosingAt] = useState("");
  const [skillChips, setSkillChips] = useState<SkillChip[]>([]);

  const [loading, setLoading] = useState(isEdit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skillsError, setSkillsError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchHrJob(id)
      .then((job: Job) => {
        setTitle(job.title);
        setDescription(job.description);
        setResponsibilities(job.responsibilities ?? "");
        setRequirements(job.requirements ?? "");
        setCategory(job.category ?? "");
        setEmploymentType(job.employment_type);
        setWorkMode(job.work_mode);
        setSeniority(job.seniority ?? "");
        setLocationText(job.location_text ?? "");
        setSalaryMin(job.salary_min?.toString() ?? "");
        setSalaryMax(job.salary_max?.toString() ?? "");
        setClosingAt(job.closing_at ? job.closing_at.slice(0, 10) : "");
        // Hidrasi chip: nama mentah dari lowongan tersimpan sebagai "tidak dikenal".
        setSkillChips(
          job.skills.map((s) => ({
            name: s.name,
            slug: null,
            category: null,
            known: false,
            required: s.required,
          })),
        );
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [id]);

  // Validasi "minimal satu skill wajib" ikut lega saat pengguna menambah/mengubah chip.
  useEffect(() => {
    if (skillChips.some((c) => c.required)) setSkillsError(null);
  }, [skillChips]);

  function addKnownSkill(item: SkillAutocompleteItem): string | null {
    const dupe = skillChips.find(
      (c) =>
        (c.slug !== null && c.slug === item.slug) ||
        c.name.toLowerCase() === item.name.toLowerCase(),
    );
    if (dupe) return `Skill "${item.name}" sudah ada di daftar.`;
    setSkillChips([
      ...skillChips,
      {
        name: item.name,
        slug: item.slug,
        category: item.category,
        known: true,
        required: true,
      },
    ]);
    return null;
  }

  function addRawSkill(text: string): string | null {
    const name = text.trim();
    if (name.length < 2) return null;
    const dupe = skillChips.find(
      (c) =>
        c.name.toLowerCase() === name.toLowerCase() ||
        (c.slug !== null && c.slug === name.toLowerCase()),
    );
    if (dupe) return `Skill "${name}" sudah ada di daftar.`;
    setSkillChips([
      ...skillChips,
      { name, slug: null, category: null, known: false, required: true },
    ]);
    return null;
  }

  function toggleSkillRequired(index: number) {
    setSkillChips((prev) =>
      prev.map((c, i) => (i === index ? { ...c, required: !c.required } : c)),
    );
  }

  function removeSkill(index: number) {
    setSkillChips((prev) => prev.filter((_, i) => i !== index));
  }

  function buildPayload() {
    return {
      title,
      description,
      responsibilities: responsibilities || null,
      requirements: requirements || null,
      skills: skillChips.map((c) => ({ name: c.name, required: c.required })),
      category: category || null,
      employment_type: employmentType,
      work_mode: workMode,
      seniority: seniority || null,
      location_text: locationText || null,
      salary_min: salaryMin ? Number(salaryMin) : null,
      salary_max: salaryMax ? Number(salaryMax) : null,
      closing_at: closingAt ? new Date(`${closingAt}T23:59:59`).toISOString() : null,
    };
  }

  async function submit(publish: boolean) {
    if (!skillChips.some((c) => c.required)) {
      setSkillsError("Minimal satu skill wajib.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (isEdit && id) {
        await updateJob(id, buildPayload());
        navigate(`/hr/jobs/${id}`);
        return;
      }
      const job = await createJob(buildPayload());
      if (publish) await transitionJob(job.id, "publish");
      navigate(`/hr/jobs/${job.id}`);
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        void submit(false);
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-800">
          {isEdit ? "Edit Lowongan" : "Buat Lowongan Baru"}
        </h1>
        <div className="flex gap-2">
          <Button type="submit" variant="secondary" disabled={busy}>
            {isEdit ? "Simpan Perubahan" : "Simpan sebagai Draft"}
          </Button>
          {!isEdit && (
            <Button type="button" disabled={busy} onClick={() => void submit(true)}>
              Terbitkan Lowongan
            </Button>
          )}
        </div>
      </div>
      {error && <Alert kind="error">{error}</Alert>}

      <Card className="space-y-4">
        <Field label="Nama Posisi Pekerjaan" required>
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior Full-Stack Engineer" required minLength={3} />
        </Field>
        <Field label="Deskripsi Pekerjaan" required>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Uraian posisi, konteks tim, dan ekspektasi…"
            required
            minLength={20}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Tanggung Jawab">
            <Textarea value={responsibilities} onChange={(e) => setResponsibilities(e.target.value)} />
          </Field>
          <Field label="Kualifikasi / Requirements">
            <Textarea value={requirements} onChange={(e) => setRequirements(e.target.value)} />
          </Field>
        </div>
      </Card>

      <Card className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Tipe Pekerjaan" required>
            <Select value={employmentType} onChange={(e) => setEmploymentType(e.target.value)}>
              {Object.entries(employmentTypeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Pengaturan Kerja" required>
            <Select value={workMode} onChange={(e) => setWorkMode(e.target.value)}>
              {Object.entries(workModeLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Level Senioritas">
            <Input value={seniority} onChange={(e) => setSeniority(e.target.value)} placeholder="Mid-Senior" />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Lokasi">
            <Input value={locationText} onChange={(e) => setLocationText(e.target.value)} placeholder="Jakarta Selatan (Hybrid 3 Hari)" />
          </Field>
          <Field label="Batas Akhir Lamaran">
            <Input type="date" value={closingAt} onChange={(e) => setClosingAt(e.target.value)} />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Gaji Minimum (opsional)">
            <Input type="number" min={0} value={salaryMin} onChange={(e) => setSalaryMin(e.target.value)} placeholder="15000000" />
          </Field>
          <Field label="Gaji Maksimum (opsional)">
            <Input type="number" min={0} value={salaryMax} onChange={(e) => setSalaryMax(e.target.value)} placeholder="30000000" />
          </Field>
        </div>
      </Card>

      <Card className="space-y-4">
        <p className="text-sm font-semibold text-slate-700">
          Kriteria Kompetensi <span className="font-normal text-slate-400">— acuan scoring ATS saat mesin matching aktif</span>
        </p>
        <Field
          label="Skills — Wajib & Disarankan (Pembobotan 60/40)"
          required
          error={skillsError ?? undefined}
        >
          <SkillPicker
            chips={skillChips}
            onAddKnown={addKnownSkill}
            onAddRaw={addRawSkill}
            onToggle={toggleSkillRequired}
            onRemove={removeSkill}
          />
        </Field>
        <p className="text-xs text-slate-400">
          Minimal satu skill wajib. Skill dipetakan ke kamus standar; skill tak dikenal tetap
          disimpan apa adanya.
        </p>
      </Card>
    </form>
  );
}
