import { NavLink, Navigate, Outlet, useNavigate, Link } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { homePathFor, useAuth } from "../lib/auth";
import { Spinner } from "./ui";

export { Spinner };

export function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img
        src="/assets/talentsync-logo.png"
        alt="TalentSync Logo"
        className="h-9 w-auto object-contain"
      />
      <span className="text-lg font-semibold tracking-tight text-on-surface">
        TalentSync<span className="text-primary-container">.AI</span>
      </span>
    </div>
  );
}

export function RequireRole({ role, children }: { role: "candidate" | "hr"; children: ReactNode }) {
  const { user, initializing } = useAuth();
  if (initializing) return <Spinner label="Memeriksa sesi…" />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to={homePathFor(user.role)} replace />;
  return <>{children}</>;
}

function LogoutButton() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <button
      className="text-xs font-medium text-slate-500 hover:text-red-600"
      onClick={async () => {
        await logout();
        navigate("/login");
      }}
    >
      Keluar
    </button>
  );
}

export function CandidateLayout() {
  const { user } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const link = ({ isActive }: { isActive: boolean }) =>
    cn0(
      "px-3 py-1.5 rounded-lg text-sm font-medium transition-all duration-150",
      isActive
        ? "bg-primary-fixed text-primary font-semibold"
        : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface",
    );

  const mobileLink = ({ isActive }: { isActive: boolean }) =>
    cn0(
      "block px-3 py-2 rounded-lg text-sm font-medium transition-all",
      isActive
        ? "bg-primary-fixed text-primary font-semibold"
        : "text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface",
    );

  return (
    <div className="min-h-screen bg-surface flex flex-col justify-between font-sans text-on-surface antialiased">
      {/* Stitch Candidate Header */}
      <header className="fixed top-0 left-0 w-full z-50 bg-surface-container-lowest border-b border-surface-container-high shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
        <div className="h-16 max-w-[1200px] mx-auto px-4 sm:px-6 flex items-center justify-between gap-4">
          <Link to="/app" className="flex items-center gap-2">
            <Logo />
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            <NavLink to="/app" end className={link}>
              Beranda
            </NavLink>
            <NavLink to="/app/jobs" className={link}>
              Cari Lowongan
            </NavLink>
            <NavLink to="/app/recommendations" className={link}>
              Rekomendasi
            </NavLink>
            <NavLink to="/app/applications" className={link}>
              Lamaran
            </NavLink>
            <NavLink to="/app/cv" className={link}>
              CV Saya
            </NavLink>
            <NavLink to="/app/profile" className={link}>
              Profil
            </NavLink>
          </nav>

          {/* User info & Logout */}
          <div className="flex items-center gap-3">
            <div className="hidden sm:flex items-center gap-2 pl-3 py-1">
              <div className="text-right">
                <p className="text-xs font-medium text-on-surface truncate max-w-[180px]">
                  {user?.email}
                </p>
                <div className="flex justify-end">
                  <LogoutButton />
                </div>
              </div>
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-white text-[18px]">person</span>
              </div>
            </div>

            {/* Mobile Hamburger Toggle */}
            <div className="flex md:hidden items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                <span className="material-symbols-outlined text-white text-[18px]">person</span>
              </div>
              <button
                type="button"
                onClick={() => setMobileMenuOpen((open) => !open)}
                className="p-1.5 rounded-lg text-on-surface-variant hover:bg-surface-container-low transition-colors"
                aria-label="Toggle navigation menu"
              >
                <span className="material-symbols-outlined text-[24px]">
                  {mobileMenuOpen ? "close" : "menu"}
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation Dropdown */}
        {mobileMenuOpen && (
          <div className="md:hidden border-t border-b border-surface-container-high bg-surface-container-lowest px-4 py-3 flex flex-col gap-1">
            <div className="pb-2 mb-2 border-b border-surface-container-high flex items-center justify-between">
              <span className="text-xs text-on-surface-variant truncate">{user?.email}</span>
              <LogoutButton />
            </div>
            <NavLink
              to="/app"
              end
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              Beranda
            </NavLink>
            <NavLink
              to="/app/jobs"
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              Cari Lowongan
            </NavLink>
            <NavLink
              to="/app/recommendations"
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              Rekomendasi
            </NavLink>
            <NavLink
              to="/app/applications"
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              Lamaran
            </NavLink>
            <NavLink
              to="/app/cv"
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              CV Saya
            </NavLink>
            <NavLink
              to="/app/profile"
              className={mobileLink}
              onClick={() => setMobileMenuOpen(false)}
            >
              Profil
            </NavLink>
          </div>
        )}
      </header>

      {/* Main Content Area */}
      <main className="w-full pt-20 pb-12 bg-surface min-h-[calc(100vh-4rem-5rem)] flex-1">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6">
          <Outlet />
        </div>
      </main>

      {/* Stitch Candidate Footer */}
      <footer className="w-full bg-surface-container-lowest border-t border-surface-container-high py-6">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4 text-on-surface-variant text-xs sm:text-sm">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-on-surface">TalentSync.AI</span>
            <span>•</span>
            <span>Portal Pencari Kerja & Karir Terpadu</span>
          </div>
          <div className="flex items-center gap-4 text-xs">
            <span className="text-secondary hover:text-primary transition-colors cursor-pointer">
              Bantuan
            </span>
            <span className="text-secondary hover:text-primary transition-colors cursor-pointer">
              Privasi
            </span>
            <span className="text-secondary hover:text-primary transition-colors cursor-pointer">
              Ketentuan Layanan
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function HRLayout() {
  const { user } = useAuth();
  const link = ({ isActive }: { isActive: boolean }) =>
    cn0(
      "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium",
      isActive ? "bg-primary-600 text-white" : "text-slate-600 hover:bg-primary-50",
    );
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col gap-1 border-r border-slate-200 bg-white p-4">
        <div className="px-2 pb-4 pt-2">
          <Logo />
          <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-primary-600">
            Portal Rekruter
          </p>
        </div>
        <NavLink to="/hr" end className={link}>
          Dashboard
        </NavLink>
        <NavLink to="/hr/jobs" className={link}>
          Kelola Lowongan
        </NavLink>
        <NavLink to="/hr/company" className={link}>
          Profil Perusahaan
        </NavLink>
        <div className="mt-auto border-t border-slate-100 pt-3">
          <p className="px-2 text-xs font-medium text-slate-700">{user?.full_name}</p>
          <p className="px-2 text-[11px] text-slate-400">{user?.email}</p>
          <div className="px-2 pt-2">
            <LogoutButton />
          </div>
        </div>
      </aside>
      <main className="flex-1 bg-slate-50 p-8">
        <div className="mx-auto max-w-4xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

// hindari import ganda cn
function cn0(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}
