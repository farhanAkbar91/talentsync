import axios from "axios";

/**
 * Klien API terpusat.
 * - Access token disimpan di memori (variabel modul) — tidak pernah di localStorage.
 * - Refresh token disimpan di localStorage dan dirotasi server (one-time use).
 * - Interceptor 401: coba refresh sekali, lalu ulangi request asli (ADR 0002).
 */

let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

const REFRESH_KEY = "ts_refresh_token";

export function storeRefreshToken(token: string): void {
  localStorage.setItem(REFRESH_KEY, token);
}

export function readRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function clearRefreshToken(): void {
  localStorage.removeItem(REFRESH_KEY);
}

export const api = axios.create({ baseURL: "/api/v1", timeout: 20_000 });

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshInFlight: Promise<string | null> | null = null;

/** Handler yang dipanggil saat sesi tak dapat dipulihkan (refresh gagal) —
 *  didaftarkan AuthProvider untuk membersihkan state user. */
let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  unauthorizedHandler = fn;
}

async function doRefresh(): Promise<string | null> {
  const refresh = readRefreshToken();
  if (!refresh) return null;
  try {
    const { data } = await axios.post("/api/v1/auth/refresh", { refresh_token: refresh });
    storeRefreshToken(data.refresh_token);
    accessToken = data.access_token;
    return data.access_token;
  } catch {
    clearRefreshToken();
    accessToken = null;
    unauthorizedHandler?.();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config ?? {};
    const isAuthCall = typeof original.url === "string" && original.url.includes("/auth/");
    if (error.response?.status === 401 && !original._retried && !isAuthCall) {
      original._retried = true;
      refreshInFlight = refreshInFlight ?? doRefresh().finally(() => (refreshInFlight = null));
      const token = await refreshInFlight;
      if (token) {
        original.headers = { ...original.headers, Authorization: `Bearer ${token}` };
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

export interface ApiErrorBody {
  error?: { code?: string; message?: string; details?: { msg?: string }[] };
}

export function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as ApiErrorBody | undefined;
    return body?.error?.message ?? err.message;
  }
  return "Terjadi kesalahan tak terduga.";
}

/** Pesan error + detail validasi (mis. 422) agar form menunjukkan field bermasalah. */
export function extractDetailedErrorMessage(err: unknown): string {
  const base = extractErrorMessage(err);
  if (axios.isAxiosError(err)) {
    const body = err.response?.data as ApiErrorBody | undefined;
    const details = body?.error?.details ?? [];
    const msgs = details
      .map((d) => d.msg)
      .filter((m): m is string => Boolean(m))
      .slice(0, 5);
    if (msgs.length) return `${base} (${msgs.join("; ")})`;
  }
  return base;
}
