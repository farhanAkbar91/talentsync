import { useEffect, useState } from "react";
import {
  deleteMySkill,
  extractErrorMessage,
  fetchCandidateProfile,
  fetchMySkills,
  updateCandidateProfile,
  type CandidateProfile,
  type CandidateSkill,
  type CertificationItem,
  type EducationItem,
  type ExperienceItem,
} from "../../lib/api";
import { Alert, Button, Select, Spinner, TagInput } from "../../components/ui";

export default function CandidateProfilePage() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [skills, setSkills] = useState<string[]>([]);
  const [education, setEducation] = useState<EducationItem[]>([]);
  const [experience, setExperience] = useState<ExperienceItem[]>([]);
  const [certifications, setCertifications] = useState<CertificationItem[]>([]);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [summaryLen, setSummaryLen] = useState(0);

  // M2 — skill terstandardisasi yang diterapkan dari CV (read-only + hapus).
  const [cvSkills, setCvSkills] = useState<CandidateSkill[] | null>(null);
  const [cvSkillsError, setCvSkillsError] = useState<string | null>(null);
  const [removingCvSkillId, setRemovingCvSkillId] = useState<string | null>(null);

  useEffect(() => {
    fetchCandidateProfile()
      .then((p) => {
        setProfile(p);
        setSkills(p.skills);
        setEducation(p.education);
        setExperience(p.experience);
        setCertifications(p.certifications);
        setLinks(p.links);
        setSummaryLen(p.summary?.length ?? 0);
      })
      .catch((err) =>
        setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal memuat." }),
      );
  }, []);

  async function refreshCvSkills(): Promise<void> {
    try {
      const res = await fetchMySkills();
      setCvSkills(res.items);
      setCvSkillsError(null);
    } catch (err) {
      setCvSkillsError(extractErrorMessage(err));
    }
  }

  useEffect(() => {
    void refreshCvSkills();
  }, []);

  async function handleRemoveCvSkill(item: CandidateSkill) {
    setRemovingCvSkillId(item.id);
    try {
      await deleteMySkill(item.id);
      await refreshCvSkills();
      const name = item.canonical.name.toLowerCase();
      setSkills((prev) => prev.filter((s) => s.toLowerCase() !== name));
      setMessage({
        kind: "success",
        text: `Skill "${item.canonical.name}" dihapus dari profil.`,
      });
    } catch (err) {
      setMessage({ kind: "error", text: extractErrorMessage(err) });
    } finally {
      setRemovingCvSkillId(null);
    }
  }

  if (!profile) return <Spinner />;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const updated = await updateCandidateProfile({
        full_name: (document.getElementById("p-name") as HTMLInputElement).value,
        phone: (document.getElementById("p-phone") as HTMLInputElement).value || null,
        location: (document.getElementById("p-location") as HTMLInputElement).value || null,
        headline: (document.getElementById("p-headline") as HTMLInputElement).value || null,
        summary: (document.getElementById("p-summary") as HTMLTextAreaElement).value || null,
        skills,
        education,
        experience,
        certifications,
        links,
      });
      setProfile(updated);
      setMessage({ kind: "success", text: "Profil berhasil disimpan." });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal menyimpan." });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="flex flex-col gap-6 max-w-[1040px] mx-auto" onSubmit={save}>
      {/* Top Header - directly starts with page title */}
      <div className="flex flex-row items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface">
            Profil Saya
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button type="submit" disabled={busy}>
            <span className="material-symbols-outlined text-[18px]">check_circle</span>
            <span>{busy ? "Menyimpan…" : "Simpan Profil"}</span>
          </Button>
        </div>
      </div>

      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      {/* Main Card: Data Diri Form */}
      <div className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8 flex flex-col gap-6">
        {/* Card Header */}
        <div className="flex items-center justify-between border-b border-surface-container pb-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-primary-fixed flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[20px]">badge</span>
            </div>
            <div>
              <h2 className="text-base font-semibold text-on-surface">Data Diri</h2>
              <p className="text-xs text-on-surface-variant">
                Lengkapi informasi dasar dan tautan profesional Anda agar mudah ditinjau oleh perekrut.
              </p>
            </div>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface-container-low border border-slate-200 text-on-surface-variant text-xs">
            <span className="w-2 h-2 rounded-full bg-tertiary" />
            <span>Akun Terverifikasi</span>
          </span>
        </div>

        <div className="flex flex-col gap-5">
          {/* Row 1: Nama Lengkap & Email */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="p-name"
                className="text-sm font-medium text-on-surface flex items-center gap-1"
              >
                Nama Lengkap <span className="text-error font-bold">*</span>
              </label>
              <input
                id="p-name"
                name="namaLengkap"
                type="text"
                required
                minLength={2}
                defaultValue={profile.full_name}
                className="w-full h-11 px-3.5 rounded-lg bg-surface-container-low text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all border border-slate-200"
              />
              <p className="text-[11px] text-on-surface-variant">
                Nama resmi yang tercantum pada kartu identitas Anda.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="p-email"
                className="text-sm font-medium text-on-surface flex items-center justify-between"
              >
                <span>Email (akun)</span>
                <span className="text-xs text-on-surface-variant flex items-center gap-1">
                  <span className="material-symbols-outlined text-[13px]">lock</span>
                  <span>Hanya Baca</span>
                </span>
              </label>
              <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px]">alternate_email</span>
                </div>
                <input
                  id="p-email"
                  type="email"
                  readOnly
                  tabIndex={-1}
                  value={profile.email}
                  className="w-full h-11 pl-10 pr-9 rounded-lg bg-surface-container-low text-secondary text-sm cursor-not-allowed select-none focus:outline-none"
                />
                <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none text-on-surface-variant">
                  <span className="material-symbols-outlined text-[16px]">lock</span>
                </div>
              </div>
              <p className="text-[11px] text-on-surface-variant">
                Alamat email terdaftar dan tidak dapat diubah secara langsung.
              </p>
            </div>
          </div>

          {/* Row 2: Nomor Telepon & Lokasi */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="p-phone" className="text-sm font-medium text-on-surface">
                Nomor Telepon
              </label>
              <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px]">call</span>
                </div>
                <input
                  id="p-phone"
                  type="tel"
                  placeholder="+62 …"
                  defaultValue={profile.phone ?? ""}
                  className="w-full h-11 pl-10 pr-3.5 rounded-lg bg-surface-container-low text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="p-location" className="text-sm font-medium text-on-surface">
                Lokasi
              </label>
              <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                  <span className="material-symbols-outlined text-[18px]">pin_drop</span>
                </div>
                <input
                  id="p-location"
                  type="text"
                  placeholder="Jakarta Selatan"
                  defaultValue={profile.location ?? ""}
                  className="w-full h-11 pl-10 pr-3.5 rounded-lg bg-surface-container-low text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
                />
              </div>
            </div>
          </div>

          {/* Row 3: Headline */}
          <div className="flex flex-col gap-1.5">
            <label htmlFor="p-headline" className="text-sm font-medium text-on-surface">
              Headline
            </label>
            <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                <span className="material-symbols-outlined text-[18px]">work_outline</span>
              </div>
              <input
                id="p-headline"
                type="text"
                placeholder="Senior UI/UX Designer"
                defaultValue={profile.headline ?? ""}
                className="w-full h-11 pl-10 pr-3.5 rounded-lg bg-surface-container-low text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
              />
            </div>
          </div>

          {/* Row 4: Ringkasan Profesional */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor="p-summary" className="text-sm font-medium text-on-surface">
                Ringkasan Profesional
              </label>
              <span
                className={
                  "text-xs " +
                  (summaryLen > 600 ? "text-error font-semibold" : "text-on-surface-variant")
                }
              >
                {summaryLen} / 600
              </span>
            </div>
            <textarea
              id="p-summary"
              rows={4}
              placeholder="Ringkasan singkat pengalaman dan keahlian utama Anda…"
              defaultValue={profile.summary ?? ""}
              onChange={(e) => setSummaryLen(e.target.value.length)}
              className="w-full p-3 rounded-lg bg-surface-container-low text-on-surface text-sm focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all resize-y min-h-[100px] border border-slate-200"
            />
          </div>

          {/* Row 5: Keahlian (Skills) */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-on-surface">Keahlian (Skills)</label>
            <TagInput
              value={skills}
              onChange={setSkills}
              placeholder="mis. React, Python…"
            />
            <p className="text-[11px] text-on-surface-variant">
              Ketik keahlian lalu tekan Enter atau koma untuk menambahkan.
            </p>
          </div>

          {/* Row 6: Tautan Profesional */}
          <div className="pt-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-secondary mb-3 flex items-center gap-1.5">
              <span className="material-symbols-outlined text-primary text-[18px]">share</span>
              <span>Tautan Profesional & Portofolio</span>
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-on-surface" htmlFor="link-linkedin">
                  LinkedIn
                </label>
                <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                    <span className="material-symbols-outlined text-[16px]">link</span>
                  </div>
                  <input
                    id="link-linkedin"
                    type="url"
                    placeholder="https://linkedin.com/in/…"
                    defaultValue={profile.links["linkedin"] ?? ""}
                    onChange={(e) => setLinks({ ...links, linkedin: e.target.value })}
                    className="w-full h-10 pl-9 pr-3 rounded-lg bg-surface-container-low text-on-surface text-xs focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-on-surface" htmlFor="link-github">
                  GitHub
                </label>
                <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                    <span className="material-symbols-outlined text-[16px]">terminal</span>
                  </div>
                  <input
                    id="link-github"
                    type="url"
                    placeholder="https://github.com/…"
                    defaultValue={profile.links["github"] ?? ""}
                    onChange={(e) => setLinks({ ...links, github: e.target.value })}
                    className="w-full h-10 pl-9 pr-3 rounded-lg bg-surface-container-low text-on-surface text-xs focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-on-surface" htmlFor="link-portfolio">
                  Portofolio
                </label>
                <div className="relative rounded-lg bg-surface-container-low border border-slate-200">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-on-surface-variant">
                    <span className="material-symbols-outlined text-[16px]">language</span>
                  </div>
                  <input
                    id="link-portfolio"
                    type="url"
                    placeholder="https://myportfolio.com"
                    defaultValue={profile.links["portfolio"] ?? ""}
                    onChange={(e) => setLinks({ ...links, portfolio: e.target.value })}
                    className="w-full h-10 pl-9 pr-3 rounded-lg bg-surface-container-low text-on-surface text-xs focus:bg-surface-container-lowest focus:outline-none focus:ring-2 focus:ring-primary-container transition-all"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Save Action */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pt-4 border-t border-surface-container">
          <div className="flex items-center gap-2 text-on-surface-variant text-xs">
            <span className="material-symbols-outlined text-[16px] text-tertiary">info</span>
            <span>Perubahan akan segera disinkronkan ke seluruh sistem lamaran Anda.</span>
          </div>
          <Button type="submit" disabled={busy}>
            <span className="material-symbols-outlined text-[18px]">check_circle</span>
            <span>{busy ? "Menyimpan…" : "Simpan Profil"}</span>
          </Button>
        </div>
      </div>

      {/* Card: Skill terstandardisasi (dari CV) */}
      <div className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8 flex flex-col gap-4">
        <div>
          <h2 className="text-base font-semibold text-on-surface">
            Skill terstandardisasi (dari CV)
          </h2>
          <p className="mt-0.5 text-xs text-on-surface-variant">
            Diterapkan dari hasil pemetaan skill CV ke kamus standar. Menghapus di sini juga
            menghapus nama yang sama dari daftar keahlian di atas.
          </p>
        </div>
        {cvSkillsError && <Alert kind="error">{cvSkillsError}</Alert>}
        {cvSkills === null ? (
          <Spinner label="Memuat skill terstandardisasi…" />
        ) : cvSkills.length === 0 ? (
          <p className="text-xs text-secondary italic">Belum ada skill dari CV yang diterapkan.</p>
        ) : (
          <ul className="space-y-2">
            {cvSkills.map((s) => (
              <li
                key={s.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-surface-container-low border border-slate-200 px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-on-surface">{s.canonical.name}</span>
                  <span className="inline-flex items-center rounded-full bg-surface-container px-2 py-0.5 text-[11px] font-medium text-secondary">
                    {s.canonical.category}
                  </span>
                </div>
                <button
                  type="button"
                  disabled={removingCvSkillId === s.id}
                  onClick={() => void handleRemoveCvSkill(s)}
                  className="px-2.5 py-1 rounded text-xs font-semibold text-error hover:bg-error-container/40 transition-colors disabled:opacity-50"
                >
                  {removingCvSkillId === s.id ? "Menghapus…" : "Hapus"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Card: Pendidikan */}
      <div className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-on-surface">Pendidikan</h2>
            <p className="text-xs text-on-surface-variant">Riwayat pendidikan formal</p>
          </div>
          <button
            type="button"
            onClick={() => setEducation([...education, { school: "", degree: "S1" }])}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface-container-high hover:bg-primary-fixed text-primary transition-colors flex items-center gap-1 border border-slate-200"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            <span>Tambah</span>
          </button>
        </div>
        {education.map((edu, i) => (
          <div
            key={i}
            className="grid gap-3 rounded-lg bg-surface-container-low border border-slate-200 p-3.5 sm:grid-cols-6 items-center"
          >
            <input
              className="sm:col-span-2 h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Institusi / Universitas"
              value={edu.school}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, school: e.target.value };
                setEducation(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Gelar (S1, SMA…)"
              value={edu.degree ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, degree: e.target.value };
                setEducation(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Bidang Studi"
              value={edu.field_of_study ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, field_of_study: e.target.value };
                setEducation(next);
              }}
            />
            <input
              type="number"
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Tahun Mulai"
              value={edu.start_year ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, start_year: e.target.value ? Number(e.target.value) : null };
                setEducation(next);
              }}
            />
            <div className="flex gap-2">
              <input
                type="number"
                className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface flex-1 focus:outline-none focus:ring-1 focus:ring-primary-container"
                placeholder="Tahun Selesai"
                value={edu.end_year ?? ""}
                onChange={(e) => {
                  const next = [...education];
                  next[i] = { ...edu, end_year: e.target.value ? Number(e.target.value) : null };
                  setEducation(next);
                }}
              />
              <button
                type="button"
                onClick={() => setEducation(education.filter((_, j) => j !== i))}
                className="w-10 h-10 rounded-lg text-error hover:bg-error-container/40 flex items-center justify-center transition-colors shrink-0"
                title="Hapus"
              >
                <span className="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Card: Pengalaman Kerja */}
      <div className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-on-surface">Pengalaman Kerja</h2>
            <p className="text-xs text-on-surface-variant">Riwayat pekerjaan profesional</p>
          </div>
          <button
            type="button"
            onClick={() => setExperience([...experience, { company: "", title: "" }])}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface-container-high hover:bg-primary-fixed text-primary transition-colors flex items-center gap-1 border border-slate-200"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            <span>Tambah</span>
          </button>
        </div>
        {experience.map((exp, i) => (
          <div
            key={i}
            className="grid gap-3 rounded-lg bg-surface-container-low border border-slate-200 p-3.5 sm:grid-cols-2"
          >
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Perusahaan"
              value={exp.company}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, company: e.target.value };
                setExperience(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Posisi / Jabatan"
              value={exp.title}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, title: e.target.value };
                setExperience(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Mulai (mis. 2023-01)"
              value={exp.start_period ?? ""}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, start_period: e.target.value };
                setExperience(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Selesai (mis. 2025-06 / sekarang)"
              value={exp.end_period ?? ""}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, end_period: e.target.value };
                setExperience(next);
              }}
            />
            <textarea
              className="sm:col-span-2 p-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Deskripsi tanggung jawab & dampak…"
              value={exp.description ?? ""}
              rows={2}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, description: e.target.value };
                setExperience(next);
              }}
            />
            <div className="sm:col-span-2 flex justify-end">
              <button
                type="button"
                onClick={() => setExperience(experience.filter((_, j) => j !== i))}
                className="px-3 py-1 rounded text-xs font-semibold text-error hover:bg-error-container/40 transition-colors"
              >
                Hapus Pengalaman
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Card: Sertifikasi */}
      <div className="w-full bg-surface-container-lowest rounded-xl border border-slate-200 p-6 sm:p-8 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-on-surface">Sertifikasi</h2>
            <p className="text-xs text-on-surface-variant">Sertifikat keahlian profesional</p>
          </div>
          <button
            type="button"
            onClick={() => setCertifications([...certifications, { name: "" }])}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-surface-container-high hover:bg-primary-fixed text-primary transition-colors flex items-center gap-1 border border-slate-200"
          >
            <span className="material-symbols-outlined text-[16px]">add</span>
            <span>Tambah</span>
          </button>
        </div>
        {certifications.map((cert, i) => (
          <div
            key={i}
            className="grid gap-3 rounded-lg bg-surface-container-low border border-slate-200 p-3.5 sm:grid-cols-4 items-center"
          >
            <input
              className="sm:col-span-2 h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Nama sertifikasi"
              value={cert.name}
              onChange={(e) => {
                const next = [...certifications];
                next[i] = { ...cert, name: e.target.value };
                setCertifications(next);
              }}
            />
            <input
              className="h-10 px-3 rounded-lg bg-surface-container-lowest border border-slate-200 text-xs text-on-surface focus:outline-none focus:ring-1 focus:ring-primary-container"
              placeholder="Penerbit"
              value={cert.issuer ?? ""}
              onChange={(e) => {
                const next = [...certifications];
                next[i] = { ...cert, issuer: e.target.value };
                setCertifications(next);
              }}
            />
            <div className="flex gap-2">
              <Select
                value={cert.year ?? ""}
                onChange={(e) => {
                  const next = [...certifications];
                  next[i] = { ...cert, year: e.target.value ? Number(e.target.value) : null };
                  setCertifications(next);
                }}
              >
                <option value="">Tahun</option>
                {Array.from({ length: 40 }, (_, k) => new Date().getFullYear() - k).map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </Select>
              <button
                type="button"
                onClick={() => setCertifications(certifications.filter((_, j) => j !== i))}
                className="w-10 h-10 rounded-lg text-error hover:bg-error-container/40 flex items-center justify-center transition-colors shrink-0"
                title="Hapus"
              >
                <span className="material-symbols-outlined text-[18px]">delete</span>
              </button>
            </div>
          </div>
        ))}
      </div>
    </form>
  );
}
