// Typed API client. All requests use the same-origin /api prefix (proxied to
// the backend by the Vite dev server) - no hard-coded localhost in browser code.
export class ApiError extends Error {
  code: number;
  details?: unknown;

  constructor(code: number, message: string, details?: unknown) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

const TOKEN_KEY = 'institrace.token';
const USER_KEY = 'institrace.user';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setSession(token: string, user: unknown) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getStoredUser<T>(): T | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function buildQuery(params: Record<string, unknown>): string {
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    q.set(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : '';
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  raw = false,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const resp = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!resp.ok) {
    let message = `Request failed with status ${resp.status}`;
    let details: unknown;
    try {
      const data = await resp.json();
      if (data?.error?.message) {
        message = data.error.message;
        details = data.error.details;
      }
    } catch {
      /* ignore parse failures */
    }
    if (resp.status === 401) clearSession();
    throw new ApiError(resp.status, message, details);
  }
  if (raw) return (await resp.text()) as unknown as T;
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  getRaw: (path: string) => request<string>('GET', path, undefined, true),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
};
