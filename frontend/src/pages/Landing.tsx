import { Link } from "react-router-dom";
import { BerandaHero } from "../components/BerandaShared";
import { Logo } from "../components/layout";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface flex flex-col justify-between font-sans text-on-surface antialiased">
      {/* Public Header - thin shadow below navbar is permitted */}
      <header className="fixed top-0 left-0 w-full z-50 bg-surface-container-lowest border-b border-surface-container-high shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
        <div className="h-16 max-w-[1200px] mx-auto px-4 sm:px-6 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2">
            <Logo />
          </Link>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium text-on-surface hover:bg-surface-container-low transition-colors"
            >
              Login
            </Link>
            <Link
              to="/register"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium bg-primary-container text-on-primary hover:bg-primary transition-colors"
            >
              Register
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="w-full pt-20 sm:pt-24 pb-12 flex-1">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 flex flex-col gap-8">
          {/* Shared Hero */}
          <BerandaHero isPublic />

          {/* 3 Static Feature Overview Modules */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Module 1: Profil Cerdas */}
            <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-4">
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                    Kelengkapan Profil
                  </span>
                  <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[18px]">person_outline</span>
                  </div>
                </div>
                <div>
                  <span className="text-xl font-bold text-on-surface">Standarisasi Otomatis</span>
                  <p className="mt-1 text-sm text-on-surface-variant leading-relaxed">
                    Data diri dasar, riwayat pendidikan, dan preferensi kerja dipetakan ke taksonomi
                    keahlian standar industri untuk meningkatkan visibilitas Anda.
                  </p>
                </div>
              </div>
              <div className="w-full bg-surface-container-low h-2 rounded-full overflow-hidden">
                <div className="bg-primary h-full w-3/4 rounded-full" />
              </div>
            </div>

            {/* Module 2: Ekstraksi CV Pintar */}
            <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-4">
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                    CV Utama & Parser
                  </span>
                  <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[18px]">upload_file</span>
                  </div>
                </div>
                <div>
                  <span className="text-xl font-bold text-on-surface">Ekstraksi Dokumen PDF</span>
                  <p className="mt-1 text-sm text-on-surface-variant leading-relaxed">
                    Unggah file PDF resume untuk memicu ekstraksi data dan penyesuaian profil otomatis
                    menggunakan kecerdasan buatan terdepan.
                  </p>
                </div>
              </div>
              <div className="rounded-lg bg-surface-container-low p-3 flex items-center gap-3">
                <div className="w-9 h-9 rounded bg-surface-container-lowest flex items-center justify-center text-secondary shrink-0">
                  <span className="material-symbols-outlined text-[20px]">picture_as_pdf</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-medium text-on-surface">Format didukung: PDF</span>
                  <span className="text-[11px] text-secondary">Maksimum ukuran 10 MB</span>
                </div>
              </div>
            </div>

            {/* Module 3: Eksplorasi Lowongan */}
            <div className="bg-surface-container-lowest rounded-xl p-6 border border-slate-200 flex flex-col justify-between gap-4">
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase font-semibold text-secondary tracking-wider">
                    Eksplorasi Karir
                  </span>
                  <div className="w-8 h-8 rounded-full bg-surface-container-low flex items-center justify-center text-primary">
                    <span className="material-symbols-outlined text-[18px]">work_outline</span>
                  </div>
                </div>
                <div>
                  <span className="text-xl font-bold text-on-surface">Pencocokan Cerdas</span>
                  <p className="mt-1 text-sm text-on-surface-variant leading-relaxed">
                    Jelajahi lowongan kerja aktif dan temukan peluang yang paling sesuai dengan skor
                    kompatibilitas transparan.
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-surface-container-low p-2.5 rounded-lg text-center">
                  <span className="text-[11px] text-secondary uppercase font-semibold">Lowongan</span>
                  <p className="text-base font-bold text-on-surface">1,400+</p>
                </div>
                <div className="bg-surface-container-low p-2.5 rounded-lg text-center">
                  <span className="text-[11px] text-secondary uppercase font-semibold">Perusahaan</span>
                  <p className="text-base font-bold text-on-surface">320+</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Public Footer */}
      <footer className="w-full bg-surface-container-lowest border-t border-surface-container-high py-6">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-on-surface-variant text-xs sm:text-sm">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-on-surface">TalentSync.AI</span>
            <span>•</span>
            <span>Portal Pencari Kerja & Karir Terpadu</span>
          </div>
          <div>
            <span>© 2026 TalentSync.AI. Hak cipta dilindungi undang-undang.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
