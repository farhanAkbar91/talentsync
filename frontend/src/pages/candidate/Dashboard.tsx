import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchCvs, fetchMeSummary, type CVDoc, type MeSummary } from "../../lib/api";
import { cvStatusLabels } from "../../lib/format";
import { Badge, Button, Card, Spinner } from "../../components/ui";

function completeness(profile: MeSummary["candidate_profile"]): number {
  if (!profile) return 0;
  const checks = [
    profile.phone,
    profile.location,
    profile.headline,
    profile.summary,
    profile.skills.length > 0,
    profile.education.length > 0,
    profile.experience.length > 0,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

export default function CandidateDashboard() {
  const [summary, setSummary] = useState<MeSummary | null>(null);
  const [cvs, setCvs] = useState<CVDoc[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchMeSummary(), fetchCvs()])
      .then(([s, c]) => {
        setSummary(s);
        setCvs(c);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Gagal memuat dashboard."));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!summary || !cvs) return <Spinner />;

  const profile = summary.candidate_profile;
  const primary = cvs.find((cv) => cv.is_primary);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">
          Selamat Datang, {summary.user.full_name.split(" ")[0]}
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Lengkapi profil dan CV Anda untuk mendapatkan rekomendasi terbaik saat mesin AI aktif.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Kelengkapan Profil
          </p>
          <p className="mt-2 text-3xl font-bold text-primary-700">{completeness(profile)}%</p>
          <Link to="/app/profile" className="mt-2 inline-block text-xs font-medium text-primary-700">
            Lengkapi profil →
          </Link>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">CV Utama</p>
          <div className="mt-2 flex items-center gap-2">
            {primary ? (
              <>
                <Badge value={primary.status} label={cvStatusLabels[primary.status]} />
                <span className="truncate text-sm text-slate-600">{primary.original_filename}</span>
              </>
            ) : (
              <span className="text-sm text-slate-500">Belum ada CV</span>
            )}
          </div>
          <Link to="/app/cv" className="mt-2 inline-block text-xs font-medium text-primary-700">
            Kelola CV →
          </Link>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            Cari Lowongan
          </p>
          <p className="mt-2 text-sm text-slate-600">
            Jelajahi lowongan aktif dari perusahaan di platform.
          </p>
          <Link to="/app/jobs">
            <Button className="mt-2 w-full">Jelajahi Lowongan</Button>
          </Link>
        </Card>
      </div>

      <Card>
        <h2 className="text-sm font-semibold text-slate-700">Info Fase</h2>
        <p className="mt-2 text-sm text-slate-500">
          Rekomendasi AI, analisis kecocokan, dan alur lamaran diaktifkan pada fase berikutnya
          (AI Engine &amp; Applications). Saat ini profil dan CV Anda sudah tersimpan aman dan
          siap diproses mesin matching.
        </p>
      </Card>
    </div>
  );
}
