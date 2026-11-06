import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import {
  confirmExtraction,
  extractDetailedErrorMessage,
  getExtraction,
  type CvExtraction,
  type CvExtractionPayload,
  type ExtractionContact,
  type ExtractionFieldConfidence,
} from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Spinner,
  Textarea,
  cn,
} from "../../components/ui";

/**
 * M1 — Review Ekstraksi: kandidat memeriksa & memperbaiki hasil bacaan parser
 * terhadap CV-nya, lalu mengonfirmasi (PUT /cvs/{id}/extraction/confirm).
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const secondaryLinkCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 transition hover:bg-slate-50";

// --- Helper nilai (data dari parser bisa null/sebagian) ---

function toNum(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function toArr<T>(v: T[] | null | undefined): T[] {
  return Array.isArray(v) ? v : [];
}

function toConf(v: number | null | undefined): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

/** Salin payload ke bentuk aman-UI: semua array pasti ada, null dikanonalkan. */
function normalizePayload(raw: CvExtractionPayload): CvExtractionPayload {
  return {
    parser_version: raw?.parser_version ?? "pymupdf-heuristic-v1",
    generated_at: raw?.generated_at ?? null,
    contact: {
      name: raw?.contact?.name ?? null,
      email: raw?.contact?.email ?? null,
      phone: raw?.contact?.phone ?? null,
      location: raw?.contact?.location ?? null,
      links: toArr(raw?.contact?.links),
    },
    summary: raw?.summary ?? null,
    experiences: toArr(raw?.experiences).map((x) => ({
      title: x?.title ?? null,
      company: x?.company ?? null,
      period: x?.period ?? null,
      start: x?.start ?? null,
      end: x?.end ?? null,
      current: x?.current ?? false,
      bullets: toArr(x?.bullets),
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    education: toArr(raw?.education).map((x) => ({
      degree: x?.degree ?? null,
      institution: x?.institution ?? null,
      field: x?.field ?? null,
      years: x?.years ?? null,
      gpa: toNum(x?.gpa),
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    skills: toArr(raw?.skills).map((x) => ({
      name: x?.name ?? "",
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    certifications: toArr(raw?.certifications).map((x) => ({
      name: x?.name ?? "",
      issuer: x?.issuer ?? null,
      year: toNum(x?.year),
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    languages: toArr(raw?.languages).map((x) => ({
      language: x?.language ?? "",
      level: x?.level ?? null,
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    projects: toArr(raw?.projects).map((x) => ({
      name: x?.name ?? null,
      description: x?.description ?? null,
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    awards: toArr(raw?.awards).map((x) => ({
      text: x?.text ?? "",
      evidence: x?.evidence ?? "",
      confidence: toConf(x?.confidence),
    })),
    field_confidence: raw?.field_confidence ?? {},
    needs_review: toArr(raw?.needs_review),
    sections_found: toArr(raw?.sections_found),
  };
}

/** Rapikan sebelum dikirim: buang item kosong hasil editing (bullet/baris kosong). */
function sanitizeForSubmit(p: CvExtractionPayload): CvExtractionPayload {
  return {
    ...p,
    experiences: p.experiences.map((x) => ({
      ...x,
      bullets: x.bullets.filter((b) => b.trim() !== ""),
    })),
    skills: p.skills.filter((s) => s.name.trim() !== ""),
    awards: p.awards.filter((a) => a.text.trim() !== ""),
  };
}

function replaceItem<T>(list: T[], index: number, item: Partial<T>): T[] {
  return list.map((it, i) => (i === index ? { ...it, ...item } : it));
}

// --- Keyakinan & penanda perlu review ---

type SectionKey =
  | "kontak"
  | "ringkasan"
  | "pengalaman"
  | "pendidikan"
  | "keahlian"
  | "sertifikasi"
  | "bahasa"
  | "proyek"
  | "penghargaan";

/** Kunci field_confidence/needs_review per bagian UI. Kontak = min() dari 4 bidangnya. */
const SECTION_CONF_KEYS: Record<
  SectionKey,
  readonly (keyof ExtractionFieldConfidence)[]
> = {
  kontak: ["name", "email", "phone", "location"],
  ringkasan: ["summary"],
  pengalaman: ["experiences"],
  pendidikan: ["education"],
  keahlian: ["skills"],
  sertifikasi: ["certifications"],
  bahasa: ["languages"],
  proyek: [],
  penghargaan: [],
};

function sectionConfidence(payload: CvExtractionPayload, key: SectionKey): number | null {
  const values = SECTION_CONF_KEYS[key]
    .map((k) => payload.field_confidence[k])
    .filter((v): v is number => typeof v === "number");
  return values.length ? Math.min(...values) : null;
}

function sectionNeedsReview(payload: CvExtractionPayload, key: SectionKey): boolean {
  return SECTION_CONF_KEYS[key].some((k) => payload.needs_review.includes(k));
}

function confidenceBadge(conf: number): { label: string; className: string } {
  if (conf >= 0.8) {
    return {
      label: "Keyakinan tinggi",
      className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
    };
  }
  if (conf >= 0.6) {
    return { label: "Cukup", className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200" };
  }
  return { label: "Perlu review", className: "bg-red-50 text-red-600 ring-1 ring-red-200" };
}

function ConfidenceChip({ conf }: { conf: number }) {
  const badge = confidenceBadge(conf);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        badge.className,
      )}
    >
      {badge.label}
    </span>
  );
}

// --- Potongan UI ---

function ReviewCard({
  title,
  sectionKey,
  payload,
  action,
  children,
}: {
  title: string;
  sectionKey: SectionKey;
  payload: CvExtractionPayload;
  action?: ReactNode;
  children: ReactNode;
}) {
  const conf = sectionConfidence(payload, sectionKey);
  const flagged = sectionNeedsReview(payload, sectionKey);
  return (
    <Card className={cn("space-y-4", flagged && "ring-2! ring-red-300!")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          {conf !== null && <ConfidenceChip conf={conf} />}
          {flagged && (
            <span className="inline-flex items-center rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600 ring-1 ring-red-200">
              perlu diperiksa
            </span>
          )}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}

function ItemBox({ children, onRemove }: { children: ReactNode; onRemove: () => void }) {
  return (
    <div className="space-y-3 rounded-xl bg-slate-50 p-3">
      {children}
      <div className="flex justify-end">
        <Button type="button" variant="danger" onClick={onRemove}>
          Hapus
        </Button>
      </div>
    </div>
  );
}

function EvidenceQuote({ text }: { text: string }) {
  const t = text.trim();
  if (!t) return null;
  return <p className="text-xs italic text-slate-400">Bukti: “{t}”</p>;
}

function EmptyNote({ hint }: { hint?: string }) {
  return <p className="text-xs text-slate-400">{hint ?? "Tidak terdeteksi."}</p>;
}

// --- Halaman ---

type LoadState = "loading" | "error" | "empty" | "ready";

export default function ReviewExtractionPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>("loading");
  const [extraction, setExtraction] = useState<CvExtraction | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<CvExtractionPayload | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ name?: string; email?: string }>({});
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!id) {
      setState("error");
      setLoadError("CV tidak ditemukan.");
      return;
    }
    setState("loading");
    getExtraction(id)
      .then((res) => {
        if (cancelled) return;
        setExtraction(res);
        if (res.payload) {
          setForm(normalizePayload(res.payload));
          setState("ready");
        } else {
          setState("empty");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          axios.isAxiosError(err) && err.response?.status === 404
            ? "Ekstraksi tidak ditemukan atau bukan milik Anda."
            : extractDetailedErrorMessage(err),
        );
        setState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  function setContact(patchC: Partial<ExtractionContact>) {
    setForm((f) => (f ? { ...f, contact: { ...f.contact, ...patchC } } : f));
  }

  async function handleSubmit() {
    if (!form || !id || submitting || confirmed) return;
    const errs: { name?: string; email?: string } = {};
    if (!form.contact.name || !form.contact.name.trim()) {
      errs.name = "Nama wajib diisi sebelum konfirmasi.";
    }
    const email = form.contact.email?.trim() ?? "";
    if (email && !EMAIL_RE.test(email)) {
      errs.email = "Format email tidak valid.";
    }
    setFieldErrors(errs);
    if (errs.name || errs.email) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      await confirmExtraction(id, sanitizeForSubmit(form));
      setConfirmed(true);
      window.setTimeout(() => navigate("/app/cv"), 900);
    } catch (err) {
      setSubmitError(extractDetailedErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (state === "loading") return <Spinner label="Memuat hasil ekstraksi…" />;

  if (state === "error") {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Review Ekstraksi</h1>
        <Card className="space-y-3">
          <Alert kind="error">{loadError ?? "Terjadi kesalahan."}</Alert>
          <Link to="/app/cv" className={secondaryLinkCls}>
            Kembali ke CV Saya
          </Link>
        </Card>
      </div>
    );
  }

  if (state === "empty" || !form) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">Review Ekstraksi</h1>
        <EmptyState
          title="Hasil ekstraksi belum tersedia"
          description={
            extraction?.status === "failed"
              ? "Proses ekstraksi gagal. Coba unggah ulang CV Anda."
              : "Proses ekstraksi masih berjalan atau hasil belum dibuat. Coba lagi nanti."
          }
        />
        <Link to="/app/cv" className={secondaryLinkCls}>
          Kembali ke CV Saya
        </Link>
      </div>
    );
  }

  const shortId = id ? `${id.slice(0, 8)}…` : "—";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Review Ekstraksi</h1>
          <p className="mt-1 text-sm text-slate-500">
            CV <span className="font-medium text-slate-600">{shortId}</span>
            {extraction?.parser_version && (
              <span className="text-slate-400"> · parser {extraction.parser_version}</span>
            )}
            {extraction?.confirmed_at && (
              <span className="text-slate-400">
                {" "}
                · dikonfirmasi {formatDateTime(extraction.confirmed_at)}
              </span>
            )}
          </p>
        </div>
        <Badge
          value={extraction?.confirmed_at ? "ready" : "pending"}
          label={extraction?.confirmed_at ? "Terkonfirmasi" : "Belum dikonfirmasi"}
        />
      </div>

      <p className="text-sm text-slate-500">
        Periksa hasil bacaan AI terhadap CV Anda — perbaiki bila ada yang keliru, lalu konfirmasi.
        Data yang dikonfirmasi akan dipakai untuk pencocokan lowongan.
      </p>

      {confirmed && (
        <Alert kind="success">Ekstraksi dikonfirmasi. Mengembalikan ke daftar CV…</Alert>
      )}
      {submitError && <Alert kind="error">{submitError}</Alert>}

      {/* Kontak */}
      <ReviewCard title="Kontak" sectionKey="kontak" payload={form}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nama" required error={fieldErrors.name}>
            <Input
              value={form.contact.name ?? ""}
              placeholder="mis. Sarah Wijaya"
              onChange={(e) => setContact({ name: e.target.value === "" ? null : e.target.value })}
            />
          </Field>
          <Field label="Email" error={fieldErrors.email}>
            <Input
              type="email"
              value={form.contact.email ?? ""}
              placeholder="nama@email.com"
              onChange={(e) => setContact({ email: e.target.value === "" ? null : e.target.value })}
            />
          </Field>
          <Field label="Telepon">
            <Input
              value={form.contact.phone ?? ""}
              placeholder="+62 …"
              onChange={(e) => setContact({ phone: e.target.value === "" ? null : e.target.value })}
            />
          </Field>
          <Field label="Lokasi">
            <Input
              value={form.contact.location ?? ""}
              placeholder="Jakarta Selatan"
              onChange={(e) =>
                setContact({ location: e.target.value === "" ? null : e.target.value })
              }
            />
          </Field>
        </div>
      </ReviewCard>

      {/* Ringkasan */}
      <ReviewCard title="Ringkasan" sectionKey="ringkasan" payload={form}>
        <Field label="Ringkasan Profesional">
          <Textarea
            value={form.summary ?? ""}
            placeholder="Ringkasan singkat pengalaman dan keahlian utama Anda…"
            onChange={(e) => {
              const v = e.target.value;
              setForm((f) => (f ? { ...f, summary: v === "" ? null : v } : f));
            }}
          />
        </Field>
      </ReviewCard>

      {/* Pengalaman */}
      <ReviewCard
        title="Pengalaman"
        sectionKey="pengalaman"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                experiences: [
                  ...form.experiences,
                  {
                    title: null,
                    company: null,
                    period: null,
                    start: null,
                    end: null,
                    current: false,
                    bullets: [],
                    evidence: "",
                    confidence: 0,
                  },
                ],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.experiences.length === 0 && <EmptyNote />}
        {form.experiences.map((exp, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                experiences: form.experiences.filter((_, j) => j !== i),
              })
            }
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <Input
                placeholder="Judul posisi"
                value={exp.title ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    experiences: replaceItem(form.experiences, i, {
                      title: v === "" ? null : v,
                    }),
                  });
                }}
              />
              <Input
                placeholder="Perusahaan"
                value={exp.company ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    experiences: replaceItem(form.experiences, i, {
                      company: v === "" ? null : v,
                    }),
                  });
                }}
              />
              <Input
                placeholder="Periode (mis. 2022–2025)"
                value={exp.period ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    experiences: replaceItem(form.experiences, i, {
                      period: v === "" ? null : v,
                    }),
                  });
                }}
              />
            </div>
            <Textarea
              rows={3}
              placeholder="Poin pencapaian — satu per baris…"
              value={exp.bullets.join("\n")}
              onChange={(e) => {
                const lines = e.target.value.split("\n");
                setForm({
                  ...form,
                  experiences: replaceItem(form.experiences, i, { bullets: lines }),
                });
              }}
            />
            <EvidenceQuote text={exp.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Pendidikan */}
      <ReviewCard
        title="Pendidikan"
        sectionKey="pendidikan"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                education: [
                  ...form.education,
                  {
                    degree: null,
                    institution: null,
                    field: null,
                    years: null,
                    gpa: null,
                    evidence: "",
                    confidence: 0,
                  },
                ],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.education.length === 0 && <EmptyNote />}
        {form.education.map((edu, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                education: form.education.filter((_, j) => j !== i),
              })
            }
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <Input
                placeholder="Jenjang (S1, SMA…)"
                value={edu.degree ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    education: replaceItem(form.education, i, { degree: v === "" ? null : v }),
                  });
                }}
              />
              <Input
                placeholder="Institusi"
                value={edu.institution ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    education: replaceItem(form.education, i, {
                      institution: v === "" ? null : v,
                    }),
                  });
                }}
              />
              <Input
                placeholder="Jurusan"
                value={edu.field ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    education: replaceItem(form.education, i, { field: v === "" ? null : v }),
                  });
                }}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                placeholder="Tahun (mis. 2019–2023)"
                value={edu.years ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    education: replaceItem(form.education, i, { years: v === "" ? null : v }),
                  });
                }}
              />
              <Input
                type="number"
                step="0.01"
                min={0}
                max={4}
                placeholder="IPK (mis. 3.75)"
                value={edu.gpa ?? ""}
                onChange={(e) => {
                  const v = toNum(e.target.value);
                  setForm({
                    ...form,
                    education: replaceItem(form.education, i, { gpa: v }),
                  });
                }}
              />
            </div>
            <EvidenceQuote text={edu.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Keahlian */}
      <ReviewCard title="Keahlian" sectionKey="keahlian" payload={form}>
        {form.skills.length === 0 && (
          <EmptyNote hint="Tidak terdeteksi — tulis keahlian di bawah (pisahkan dengan koma)." />
        )}
        <Field label="Keahlian (pisahkan dengan koma)">
          <Textarea
            rows={2}
            placeholder="mis. React, Python, SQL"
            value={form.skills.map((s) => s.name).join(", ")}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw.trim() === "") {
                setForm({ ...form, skills: [] });
                return;
              }
              const names = raw.split(",").map((n) => n.trim());
              setForm({
                ...form,
                skills: names.map((name, j) => ({
                  name,
                  evidence: form.skills[j]?.evidence ?? "",
                  confidence: form.skills[j]?.confidence ?? 0,
                })),
              });
            }}
          />
        </Field>
        {form.skills.some((s) => s.evidence.trim() !== "") && (
          <ul className="space-y-1">
            {form.skills
              .filter((s) => s.evidence.trim() !== "")
              .map((s, j) => (
                <li key={j} className="text-xs italic text-slate-400">
                  {s.name || "—"}: “{s.evidence.trim()}”
                </li>
              ))}
          </ul>
        )}
      </ReviewCard>

      {/* Sertifikasi */}
      <ReviewCard
        title="Sertifikasi"
        sectionKey="sertifikasi"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                certifications: [
                  ...form.certifications,
                  { name: "", issuer: null, year: null, evidence: "", confidence: 0 },
                ],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.certifications.length === 0 && <EmptyNote />}
        {form.certifications.map((cert, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                certifications: form.certifications.filter((_, j) => j !== i),
              })
            }
          >
            <div className="grid gap-3 sm:grid-cols-4">
              <Input
                className="sm:col-span-2"
                placeholder="Nama sertifikasi"
                value={cert.name}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    certifications: replaceItem(form.certifications, i, { name: v }),
                  });
                }}
              />
              <Input
                placeholder="Penerbit"
                value={cert.issuer ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    certifications: replaceItem(form.certifications, i, {
                      issuer: v === "" ? null : v,
                    }),
                  });
                }}
              />
              <Input
                type="number"
                placeholder="Tahun"
                value={cert.year ?? ""}
                onChange={(e) => {
                  const v = toNum(e.target.value);
                  setForm({
                    ...form,
                    certifications: replaceItem(form.certifications, i, { year: v }),
                  });
                }}
              />
            </div>
            <EvidenceQuote text={cert.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Bahasa */}
      <ReviewCard
        title="Bahasa"
        sectionKey="bahasa"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                languages: [
                  ...form.languages,
                  { language: "", level: null, evidence: "", confidence: 0 },
                ],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.languages.length === 0 && <EmptyNote />}
        {form.languages.map((lang, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                languages: form.languages.filter((_, j) => j !== i),
              })
            }
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <Input
                placeholder="Bahasa (mis. Indonesia)"
                value={lang.language}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    languages: replaceItem(form.languages, i, { language: v }),
                  });
                }}
              />
              <Input
                placeholder="Level (mis. Lancar / TOEFL 550)"
                value={lang.level ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({
                    ...form,
                    languages: replaceItem(form.languages, i, { level: v === "" ? null : v }),
                  });
                }}
              />
            </div>
            <EvidenceQuote text={lang.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Proyek */}
      <ReviewCard
        title="Proyek"
        sectionKey="proyek"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                projects: [
                  ...form.projects,
                  { name: null, description: null, evidence: "", confidence: 0 },
                ],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.projects.length === 0 && <EmptyNote />}
        {form.projects.map((proj, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                projects: form.projects.filter((_, j) => j !== i),
              })
            }
          >
            <Input
              placeholder="Nama proyek"
              value={proj.name ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setForm({
                  ...form,
                  projects: replaceItem(form.projects, i, { name: v === "" ? null : v }),
                });
              }}
            />
            <Textarea
              rows={2}
              placeholder="Deskripsi proyek…"
              value={proj.description ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setForm({
                  ...form,
                  projects: replaceItem(form.projects, i, {
                    description: v === "" ? null : v,
                  }),
                });
              }}
            />
            <EvidenceQuote text={proj.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Penghargaan */}
      <ReviewCard
        title="Penghargaan"
        sectionKey="penghargaan"
        payload={form}
        action={
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              setForm({
                ...form,
                awards: [...form.awards, { text: "", evidence: "", confidence: 0 }],
              })
            }
          >
            + Tambah
          </Button>
        }
      >
        {form.awards.length === 0 && <EmptyNote />}
        {form.awards.map((award, i) => (
          <ItemBox
            key={i}
            onRemove={() =>
              setForm({
                ...form,
                awards: form.awards.filter((_, j) => j !== i),
              })
            }
          >
            <Textarea
              rows={2}
              placeholder="Uraian penghargaan…"
              value={award.text}
              onChange={(e) => {
                const v = e.target.value;
                setForm({
                  ...form,
                  awards: replaceItem(form.awards, i, { text: v }),
                });
              }}
            />
            <EvidenceQuote text={award.evidence} />
          </ItemBox>
        ))}
      </ReviewCard>

      {/* Aksi */}
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 pt-5">
        <Button onClick={handleSubmit} disabled={submitting || confirmed}>
          {confirmed ? "Terkonfirmasi" : submitting ? "Menyimpan…" : "Simpan & Konfirmasi"}
        </Button>
        <Link to="/app/cv" className={secondaryLinkCls}>
          Kembali
        </Link>
      </div>
    </div>
  );
}
