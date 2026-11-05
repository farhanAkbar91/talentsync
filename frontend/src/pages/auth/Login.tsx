import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { homePathFor, useAuth } from "../../lib/auth";
import { Alert, Button, Card, Field, Input } from "../../components/ui";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [portal, setPortal] = useState<"hr" | "candidate">("candidate");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const user = await login(email, password);
      navigate(homePathFor(user.role), { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gagal masuk.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-4 flex flex-col items-center gap-1">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary-600 text-lg font-bold text-white">
            TS
          </span>
          <p className="font-semibold">
            TalentSync<span className="text-primary-600">.AI</span>
          </p>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-400">
            Semantic HR Intelligence
          </p>
        </div>

        <Card className="p-6">
          <h1 className="text-xl font-bold text-slate-800">Selamat Datang Kembali</h1>
          <p className="mt-1 text-sm text-slate-500">
            Akses portal rekrutmen cerdas sesuai peran Anda.
          </p>

          <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl bg-slate-100 p-1">
            {(["candidate", "hr"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setPortal(r)}
                className={
                  "rounded-lg px-3 py-2 text-sm font-semibold transition " +
                  (portal === r ? "bg-primary-600 text-white" : "text-slate-600 hover:bg-white")
                }
              >
                {r === "hr" ? "Rekruter / HR" : "Pencari Kerja"}
              </button>
            ))}
          </div>

          <form className="mt-5 space-y-4" onSubmit={submit}>
            {error && <Alert kind="error">{error}</Alert>}
            <Field label="Email" required>
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={portal === "hr" ? "dewi@perusahaan.co.id" : "kandidat@email.com"}
                required
              />
            </Field>
            <Field label="Kata Sandi" required>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </Field>
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Memproses…" : "Masuk ke Akun →"}
            </Button>
          </form>

          <div className="mt-4 rounded-xl bg-primary-50 p-3 text-xs text-slate-600">
            <p className="font-semibold text-primary-700">Demo Akses (seed data)</p>
            <p>
              Akun demo dibuat lewat <code>scripts/seed_demo_data.py</code> — lihat README untuk
              kredensialnya.
            </p>
          </div>

          <p className="mt-4 text-center text-sm text-slate-500">
            Belum memiliki akun?{" "}
            <Link to="/register" className="font-semibold text-primary-700">
              Daftar Sekarang
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
