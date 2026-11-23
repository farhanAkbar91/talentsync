import { Link } from "react-router-dom";
import type { ReactNode } from "react";

export function BerandaHero({
  isPublic = false,
  customCtas,
}: {
  isPublic?: boolean;
  customCtas?: ReactNode;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl bg-white border border-slate-200 flex flex-col md:flex-row items-stretch justify-between">
      {/* Decorative Indigo Ambient Accent */}
      <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full bg-primary-fixed-dim/20 blur-3xl pointer-events-none" />

      {/* Left Content Block (white behind text) */}
      <div className="relative z-10 flex-1 bg-white p-6 sm:p-8 md:p-10 flex flex-col justify-between gap-6">
        <div className="flex flex-col gap-2 max-w-xl">
          <div className="flex items-center gap-1.5 text-primary text-xs font-semibold tracking-wide uppercase">
            <span>Rekomendasi Cerdas</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-on-surface leading-tight">
            Temukan peluang yang sesuai dengan keahlianmu.
          </h2>
          <p className="text-sm sm:text-base text-on-surface-variant leading-relaxed">
            Sistem kami menganalisis portofolio, keahlian khusus, dan latar belakang karir Anda untuk
            mencocokkan lowongan kerja paling relevan secara otomatis. Mulai dengan mengunggah resume
            terbaru Anda.
          </p>
        </div>

        {/* Quick Action CTAs */}
        {!isPublic && (
          <div className="flex flex-wrap items-center gap-3 pt-1">
            {customCtas ? (
              customCtas
            ) : (
              <>
                <Link
                  to="/app/jobs"
                  className="inline-flex items-center justify-center gap-2 px-5 h-10 rounded-lg bg-primary-container text-on-primary text-sm font-medium hover:opacity-95 transition-opacity"
                >
                  <span className="material-symbols-outlined text-[18px]">search</span>
                  <span>Jelajahi Lowongan</span>
                </Link>
                <Link
                  to="/app/cv"
                  className="inline-flex items-center justify-center gap-2 px-5 h-10 rounded-lg bg-white text-on-surface text-sm font-medium hover:bg-surface-container-low transition-colors border border-slate-200"
                >
                  <span className="material-symbols-outlined text-[18px]">description</span>
                  <span>Kelola CV</span>
                </Link>
              </>
            )}
          </div>
        )}
      </div>

      {/* Right Graphic / Media Anchor */}
      <div className="relative w-full md:w-[420px] bg-white flex items-center justify-center p-4 sm:p-6 shrink-0">
        <img
          alt="Ilustrasi TalentSync"
          className="w-full max-h-64 sm:max-h-72 md:max-h-80 object-contain select-none"
          src="/assets/talentsync-hero.png"
        />
      </div>
    </div>
  );
}
