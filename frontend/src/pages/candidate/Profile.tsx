import { useEffect, useState } from "react";
import {
  fetchCandidateProfile,
  updateCandidateProfile,
  type CandidateProfile,
  type CertificationItem,
  type EducationItem,
  type ExperienceItem,
} from "../../lib/api";
import { Alert, Button, Card, Field, Input, Select, Spinner, TagInput, Textarea } from "../../components/ui";

export default function CandidateProfilePage() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [skills, setSkills] = useState<string[]>([]);
  const [education, setEducation] = useState<EducationItem[]>([]);
  const [experience, setExperience] = useState<ExperienceItem[]>([]);
  const [certifications, setCertifications] = useState<CertificationItem[]>([]);
  const [links, setLinks] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCandidateProfile()
      .then((p) => {
        setProfile(p);
        setSkills(p.skills);
        setEducation(p.education);
        setExperience(p.experience);
        setCertifications(p.certifications);
        setLinks(p.links);
      })
      .catch((err) => setMessage({ kind: "error", text: err instanceof Error ? err.message : "Gagal memuat." }));
  }, []);

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
    <form className="space-y-6" onSubmit={save}>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">Profil Saya</h1>
        <Button type="submit" disabled={busy}>
          {busy ? "Menyimpan…" : "Simpan Profil"}
        </Button>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      <Card className="space-y-4">
        <h2 className="text-sm font-semibold text-slate-700">Data Diri</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nama Lengkap" required>
            <Input id="p-name" defaultValue={profile.full_name} required minLength={2} />
          </Field>
          <Field label="Email (akun)">
            <Input value={profile.email} disabled className="opacity-60" />
          </Field>
          <Field label="Nomor Telepon">
            <Input id="p-phone" defaultValue={profile.phone ?? ""} placeholder="+62 …" />
          </Field>
          <Field label="Lokasi">
            <Input id="p-location" defaultValue={profile.location ?? ""} placeholder="Jakarta Selatan" />
          </Field>
        </div>
        <Field label="Headline">
          <Input id="p-headline" defaultValue={profile.headline ?? ""} placeholder="Senior UI/UX Designer" />
        </Field>
        <Field label="Ringkasan Profesional">
          <Textarea
            id="p-summary"
            defaultValue={profile.summary ?? ""}
            placeholder="Ringkasan singkat pengalaman dan keahlian utama Anda…"
          />
        </Field>
        <Field label="Keahlian (Skills)">
          <TagInput value={skills} onChange={setSkills} placeholder="mis. React, Python…" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="LinkedIn">
            <Input
              defaultValue={profile.links["linkedin"] ?? ""}
              onChange={(e) => setLinks({ ...links, linkedin: e.target.value })}
            />
          </Field>
          <Field label="GitHub">
            <Input
              defaultValue={profile.links["github"] ?? ""}
              onChange={(e) => setLinks({ ...links, github: e.target.value })}
            />
          </Field>
          <Field label="Portofolio">
            <Input
              defaultValue={profile.links["portfolio"] ?? ""}
              onChange={(e) => setLinks({ ...links, portfolio: e.target.value })}
            />
          </Field>
        </div>
      </Card>

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Pendidikan</h2>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setEducation([...education, { school: "", degree: "S1" }])}
          >
            + Tambah
          </Button>
        </div>
        {education.map((edu, i) => (
          <div key={i} className="grid gap-3 rounded-xl bg-slate-50 p-3 sm:grid-cols-6">
            <Input
              className="sm:col-span-2"
              placeholder="Institusi"
              value={edu.school}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, school: e.target.value };
                setEducation(next);
              }}
            />
            <Input
              placeholder="Gelar (S1, SMA…)"
              value={edu.degree ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, degree: e.target.value };
                setEducation(next);
              }}
            />
            <Input
              placeholder="Bidang"
              value={edu.field_of_study ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, field_of_study: e.target.value };
                setEducation(next);
              }}
            />
            <Input
              type="number"
              placeholder="Dari"
              value={edu.start_year ?? ""}
              onChange={(e) => {
                const next = [...education];
                next[i] = { ...edu, start_year: e.target.value ? Number(e.target.value) : null };
                setEducation(next);
              }}
            />
            <div className="flex gap-2">
              <Input
                type="number"
                placeholder="Sampai"
                value={edu.end_year ?? ""}
                onChange={(e) => {
                  const next = [...education];
                  next[i] = { ...edu, end_year: e.target.value ? Number(e.target.value) : null };
                  setEducation(next);
                }}
              />
              <Button type="button" variant="danger" onClick={() => setEducation(education.filter((_, j) => j !== i))}>
                ×
              </Button>
            </div>
          </div>
        ))}
      </Card>

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Pengalaman Kerja</h2>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setExperience([...experience, { company: "", title: "" }])}
          >
            + Tambah
          </Button>
        </div>
        {experience.map((exp, i) => (
          <div key={i} className="grid gap-3 rounded-xl bg-slate-50 p-3 sm:grid-cols-2">
            <Input
              placeholder="Perusahaan"
              value={exp.company}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, company: e.target.value };
                setExperience(next);
              }}
            />
            <Input
              placeholder="Posisi"
              value={exp.title}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, title: e.target.value };
                setExperience(next);
              }}
            />
            <Input
              placeholder="Mulai (mis. 2023-01)"
              value={exp.start_period ?? ""}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, start_period: e.target.value };
                setExperience(next);
              }}
            />
            <Input
              placeholder="Selesai (mis. 2025-06 / sekarang)"
              value={exp.end_period ?? ""}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, end_period: e.target.value };
                setExperience(next);
              }}
            />
            <Textarea
              className="sm:col-span-2"
              placeholder="Deskripsi tanggung jawab & dampak…"
              value={exp.description ?? ""}
              onChange={(e) => {
                const next = [...experience];
                next[i] = { ...exp, description: e.target.value };
                setExperience(next);
              }}
            />
            <div>
              <Button type="button" variant="danger" onClick={() => setExperience(experience.filter((_, j) => j !== i))}>
                Hapus
              </Button>
            </div>
          </div>
        ))}
      </Card>

      <Card className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">Sertifikasi</h2>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setCertifications([...certifications, { name: "" }])}
          >
            + Tambah
          </Button>
        </div>
        {certifications.map((cert, i) => (
          <div key={i} className="grid gap-3 rounded-xl bg-slate-50 p-3 sm:grid-cols-4">
            <Input
              className="sm:col-span-2"
              placeholder="Nama sertifikasi"
              value={cert.name}
              onChange={(e) => {
                const next = [...certifications];
                next[i] = { ...cert, name: e.target.value };
                setCertifications(next);
              }}
            />
            <Input
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
              <Button
                type="button"
                variant="danger"
                onClick={() => setCertifications(certifications.filter((_, j) => j !== i))}
              >
                ×
              </Button>
            </div>
          </div>
        ))}
      </Card>
    </form>
  );
}
