import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createJob,
  extractErrorMessage,
  fetchHrJob,
  transitionJob,
  updateJob,
  type Job,
} from "../../lib/api";
import { employmentTypeLabels, workModeLabels } from "../../lib/format";
import { Alert, Button, Card, Field, Input, Select, Spinner, TagInput, Textarea } from "../../components/ui";

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
  const [requiredSkills, setRequiredSkills] = useState<string[]>([]);
  const [preferredSkills, setPreferredSkills] = useState<string[]>([]);

  const [loading, setLoading] = useState(isEdit);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setRequiredSkills(job.skills.filter((s) => s.required).map((s) => s.name));
        setPreferredSkills(job.skills.filter((s) => !s.required).map((s) => s.name));
      })
      .catch((err) => setError(extractErrorMessage(err)))
      .finally(() => setLoading(false));
  }, [id]);

  function buildPayload() {
    return {
      title,
      description,
      responsibilities: responsibilities || null,
      requirements: requirements || null,
      skills: [
        ...requiredSkills.map((name) => ({ name, required: true })),
        ...preferredSkills.map((name) => ({ name, required: false })),
      ],
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
        <Field label="Required Skills — Wajib (Pembobotan 60%)" required>
          <TagInput value={requiredSkills} onChange={setRequiredSkills} placeholder="mis. React.js, Node.js…" />
        </Field>
        <Field label="Preferred Skills — Nilai Tambah (Pembobotan 40%)">
          <TagInput value={preferredSkills} onChange={setPreferredSkills} placeholder="mis. Docker, Kubernetes…" />
        </Field>
        <p className="text-xs text-slate-400">
          Minimal satu skill wajib. Skill yang sama di kedua daftar otomatis digabung sebagai wajib.
        </p>
      </Card>
    </form>
  );
}
