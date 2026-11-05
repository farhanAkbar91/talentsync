import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import { Alert, Button, Card, Field, Input } from "../../components/ui";
import type { Role } from "../../lib/api";

const roleCards: { role: Role; title: string; description: string }[] = [
  {
    role: "hr",
    title: "Rekruter / HR",
    description:
      "Saya ingin memasang lowongan, screening CV pelamar secara otomatis, dan mendapatkan peringkat talenta terbaik.",
  },
  {
    role: "candidate",
    title: "Pencari Kerja",
    description:
      "Saya ingin menganalisis CV saya, melihat skill gap, dan mendapatkan rekomendasi pekerjaan paling relevan.",
  },
];

function strength(password: string): number {
  let score = 0;
  if (password.length >= 8) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  return score;
}

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>("candidate");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const score = useMemo(() => strength(password), [password]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Konfirmasi kata sandi tidak sama.");
      return;
    }
    if (!agree) {
      setError("Centang persetujuan Syarat & Ketentuan terlebih dahulu.");
      return;
    }
    setBusy(true);
    try {
      await register({ role, full_name: fullName, email, password });
      navigate(role === "hr" ? "/hr/company" : "/app", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pendaftaran gagal.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-10">
      <Card className="w-full max-w-lg p-6">
        <div className="text-center">
          <span className="inline-flex items-center rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-700">
            TalentSync AI Platform
          </span>
          <h1 className="mt-3 text-2xl font-bold text-slate-800">Daftar ke TalentSync AI</h1>
          <p className="mt-1 text-sm text-slate-500">
            Pilih peran Anda untuk mendapatkan pengalaman yang disesuaikan.
          </p>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          {roleCards.map((card) => (
            <button
              key={card.role}
              type="button"
              onClick={() => setRole(card.role)}
              className={
                "rounded-xl p-4 text-left ring-1 transition " +
                (role === card.role
                  ? "bg-primary-50 ring-2 ring-primary-500"
                  : "bg-white ring-slate-200 hover:bg-slate-50")
              }
            >
              <span className="text-sm font-bold text-slate-800">{card.title}</span>
              <span className="mt-1 block text-xs leading-relaxed text-slate-500">
                {card.description}
              </span>
            </button>
          ))}
        </div>

        <form className="mt-5 space-y-4" onSubmit={submit}>
          {error && <Alert kind="error">{error}</Alert>}
          <Field label="Nama Lengkap" required>
            <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required minLength={2} />
          </Field>
          <Field label="Email" required>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Kata Sandi" required>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                maxLength={72}
              />
            </Field>
            <Field label="Konfirmasi Kata Sandi" required>
              <Input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                required
              />
            </Field>
          </div>

          <div>
            <div className="flex gap-1">
              {[0, 1, 2, 3].map((i) => (
                <span
                  key={i}
                  className={
                    "h-1.5 flex-1 rounded-full " +
                    (i < score
                      ? score <= 1
                        ? "bg-red-400"
                        : score === 2
                          ? "bg-amber-400"
                          : "bg-emerald-500"
                      : "bg-slate-200")
                  }
                />
              ))}
            </div>
            <p className="mt-1 text-xs text-slate-400">
              Gunakan minimal 8 karakter dengan kombinasi huruf besar, kecil, angka, dan simbol.
            </p>
          </div>

          <label className="flex items-start gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={agree}
              onChange={(e) => setAgree(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-primary-600"
            />
            <span>
              Saya menyetujui Syarat &amp; Ketentuan serta kebijakan privasi data pribadi
              TalentSync AI. Data CV saya diproses hanya untuk keperluan pencocokan lowongan.
            </span>
          </label>

          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Mendaftarkan…" : "Daftar Akun Sekarang"}
          </Button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-500">
          Sudah memiliki akun?{" "}
          <Link to="/login" className="font-semibold text-primary-700">
            Masuk di sini
          </Link>
        </p>
      </Card>
    </div>
  );
}
