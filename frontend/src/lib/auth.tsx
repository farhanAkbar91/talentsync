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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);

  // Sesi pulih saat halaman dimuat: refresh token disimpan, access token diperbarui.
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      if (!readRefreshToken()) {
        setInitializing(false);
        return;
      }
      try {
        // Panggilan langsung via axios (bukan wrapper) agar tidak memicu loop 401.
        const { default: axios } = await import("axios");
        const { data } = await axios.post("/api/v1/auth/refresh", {
          refresh_token: readRefreshToken(),
        });
        if (cancelled) return;
        setAccessToken(data.access_token);
        storeRefreshToken(data.refresh_token);
        setUser(data.user);
      } catch {
        if (!cancelled) clearRefreshToken();
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void restore();
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
