import { useEffect, useState } from "react";
import {
  createCompany,
  extractErrorMessage,
  fetchCompany,
  updateCompany,
  type Company,
} from "../../lib/api";
import { Alert, Button, Card, Field, Input, Spinner, Textarea } from "../../components/ui";

export default function CompanyPage() {
  const [company, setCompany] = useState<Company | null>(null);
  const [loading, setLoading] = useState(true);
  const [exists, setExists] = useState(false);
  const [message, setMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCompany()
      .then((c) => {
        setCompany(c);
        setExists(true);
      })
      .catch(() => setExists(false))
      .finally(() => setLoading(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    const payload = {
      name: (document.getElementById("c-name") as HTMLInputElement).value,
      description: (document.getElementById("c-desc") as HTMLTextAreaElement).value || null,
      industry: (document.getElementById("c-industry") as HTMLInputElement).value || null,
      location: (document.getElementById("c-location") as HTMLInputElement).value || null,
      website: (document.getElementById("c-web") as HTMLInputElement).value || null,
      contact_email: (document.getElementById("c-email") as HTMLInputElement).value || null,
    };
    try {
      const saved = exists ? await updateCompany(payload) : await createCompany(payload);
      setCompany(saved);
      setExists(true);
      setMessage({ kind: "success", text: "Profil perusahaan tersimpan." });
    } catch (err) {
      setMessage({ kind: "error", text: extractErrorMessage(err) });
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spinner />;

  return (
    <form className="space-y-5" onSubmit={submit}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Profil Perusahaan</h1>
          <p className="mt-1 text-sm text-slate-500">
            {exists ? "Perbarui informasi perusahaan Anda." : "Satu akun HR terhubung ke satu perusahaan."}
          </p>
        </div>
        <Button type="submit" disabled={busy}>
          {busy ? "Menyimpan…" : exists ? "Simpan Perubahan" : "Buat Perusahaan"}
        </Button>
      </div>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}

      <Card className="space-y-4">
        <Field label="Nama Perusahaan" required>
          <Input id="c-name" defaultValue={company?.name ?? ""} required minLength={2} />
        </Field>
        <Field label="Deskripsi">
          <Textarea id="c-desc" defaultValue={company?.description ?? ""} placeholder="Tentang perusahaan, produk, budaya kerja…" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Industri">
            <Input id="c-industry" defaultValue={company?.industry ?? ""} placeholder="Teknologi, Keuangan, …" />
          </Field>
          <Field label="Lokasi">
            <Input id="c-location" defaultValue={company?.location ?? ""} placeholder="Jakarta Selatan" />
          </Field>
          <Field label="Website">
            <Input id="c-web" type="url" defaultValue={company?.website ?? ""} placeholder="https://…" />
          </Field>
          <Field label="Email Kontak HR">
            <Input id="c-email" type="email" defaultValue={company?.contact_email ?? ""} placeholder="hr@perusahaan.co.id" />
          </Field>
        </div>
      </Card>
    </form>
  );
}
