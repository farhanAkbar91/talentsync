import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  clearRefreshToken,
  extractDetailedErrorMessage,
  login as apiLogin,
  logout as apiLogout,
  readRefreshToken,
  register as apiRegister,
  setAccessToken,
  setUnauthorizedHandler,
  storeRefreshToken,
  type Role,
  type User,
} from "./api";

interface AuthContextValue {
  user: User | null;
  initializing: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (payload: {
    role: Role;
    full_name: string;
    email: string;
    password: string;
  }) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

// Pemulihan sesi sekali per muat halaman (single-flight). React StrictMode
// menjalankan effect mount dua kali di dev — tanpa dedupe, dua POST /auth/refresh
// berlomba memakai refresh token sekali pakai (satu 200, satu 401) dan sesi
// bisa terbuang acak saat hard reload.
interface RestoredSession {
  access_token: string;
  refresh_token: string;
  user: User;
}

let restoreInFlight: Promise<RestoredSession | null> | null = null;

function restoreSession(): Promise<RestoredSession | null> {
  if (!restoreInFlight) {
    restoreInFlight = (async () => {
      if (!readRefreshToken()) return null;
      try {
        // Panggilan langsung via axios (bukan wrapper) agar tidak memicu loop 401.
        const { default: axios } = await import("axios");
        const { data } = await axios.post<RestoredSession>("/api/v1/auth/refresh", {
          refresh_token: readRefreshToken(),
        });
        return data;
      } catch {
        clearRefreshToken();
        return null;
      }
    })();
  }
  return restoreInFlight;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);

  // Sesi pulih saat halaman dimuat: refresh token disimpan, access token diperbarui.
  useEffect(() => {
    let cancelled = false;
    restoreSession().then((data) => {
      if (cancelled) return;
      if (data) {
        setAccessToken(data.access_token);
        storeRefreshToken(data.refresh_token);
        setUser(data.user);
      }
      setInitializing(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Sesi tak dapat dipulihkan (refresh gagal) → bersihkan state user agar guard
  // melempar pengguna ke /login, bukan stuck di halaman dengan 401 berulang.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const data = await apiLogin(email, password);
      setAccessToken(data.access_token);
      storeRefreshToken(data.refresh_token);
      setUser(data.user);
      return data.user;
    } catch (err) {
      throw new Error(extractDetailedErrorMessage(err));
    }
  }, []);

  const register = useCallback(
    async (payload: { role: Role; full_name: string; email: string; password: string }) => {
      try {
        const data = await apiRegister({ ...payload, role: payload.role });
        setAccessToken(data.access_token);
        storeRefreshToken(data.refresh_token);
        setUser(data.user);
        return data.user;
      } catch (err) {
        throw new Error(extractDetailedErrorMessage(err));
      }
    },
    [],
  );

  const logout = useCallback(async () => {
    const refresh = readRefreshToken();
    try {
      if (refresh) await apiLogout(refresh);
    } catch {
      // abaikan kegagalan logout server — sesi lokal tetap dibersihkan
    } finally {
      setAccessToken(null);
      clearRefreshToken();
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, initializing, login, register, logout }),
    [user, initializing, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth harus dipakai di dalam AuthProvider");
  return ctx;
}

export function homePathFor(role: Role | undefined | null): string {
  return role === "hr" ? "/hr" : "/app";
}
