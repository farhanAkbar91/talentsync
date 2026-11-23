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
    <div className="flex min-h-screen items-center justify-center bg-surface px-4 py-10">
      <div className="w-full max-w-lg">
        {/* Brand header aligned with Login */}
        <div className="mb-6 flex flex-col items-center gap-2">
          <img
            src="/assets/talentsync-logo.png"
            alt="TalentSync Logo"
            className="h-12 w-auto object-contain"
          />
          <div className="text-center">
            <p className="text-xl font-bold tracking-tight text-on-surface">
              TalentSync<span className="text-primary-container">.AI</span>
            </p>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-secondary">
              Semantic HR Intelligence
            </p>
          </div>
        </div>

        <Card className="p-6 border border-slate-200 shadow-none">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-slate-800">Daftar ke TalentSync AI</h1>
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
                  "rounded-xl p-4 text-left border transition " +
                  (role === card.role
                    ? "bg-primary-50 border-primary-500 ring-1 ring-primary-500"
                    : "bg-white border-slate-200 hover:bg-slate-50")
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
                  minLength={8}
                  maxLength={72}
                />
              </Field>
            </div>

            {password && (
              <div className="space-y-1">
                <div className="flex gap-1">
                  {[1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className={
                        "h-1.5 flex-1 rounded-full " +
                        (i <= score
                          ? score <= 2
                            ? "bg-amber-500"
                            : "bg-emerald-500"
                          : "bg-slate-200")
                      }
                    />
                  ))}
                </div>
                <p className="text-[11px] text-slate-500">
                  Minimal 8 karakter, kombinasi huruf besar, kecil, angka, dan simbol.
                </p>
              </div>
            )}

            <label className="flex items-start gap-2 pt-2 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={agree}
                onChange={(e) => setAgree(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                Saya menyetujui Syarat &amp; Ketentuan serta Kebijakan Privasi TalentSync AI.
              </span>
            </label>

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Mendaftarkan…" : "Daftar Akun Sekarang"}
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-slate-500">
            Sudah memiliki akun?{" "}
            <Link to="/login" className="font-semibold text-primary-700 hover:underline">
              Masuk
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
