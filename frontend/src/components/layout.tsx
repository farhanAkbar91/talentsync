import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { homePathFor, useAuth } from "../lib/auth";
import { Spinner } from "./ui";

export { Spinner };

export function Logo() {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-sm font-bold text-white">
        TS
      </span>
      <span className="font-semibold text-slate-800">
        TalentSync<span className="text-primary-600">.AI</span>
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
  const link = ({ isActive }: { isActive: boolean }) =>
    cn0(
      "rounded-lg px-3 py-1.5 text-sm font-medium",
      isActive ? "bg-primary-600 text-white" : "text-slate-600 hover:bg-primary-50",
    );
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
          <Logo />
          <nav className="flex items-center gap-1">
            <NavLink to="/app" end className={link}>
              Beranda
            </NavLink>
            <NavLink to="/app/jobs" className={link}>
              Cari Lowongan
            </NavLink>
            <NavLink to="/app/recommendations" className={link}>
              Rekomendasi
            </NavLink>
            <NavLink to="/app/cv" className={link}>
              CV Saya
            </NavLink>
            <NavLink to="/app/profile" className={link}>
              Profil
            </NavLink>
          </nav>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-slate-500 sm:block">{user?.email}</span>
            <LogoutButton />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        <Outlet />
      </main>
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
