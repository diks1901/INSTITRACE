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

// Endpoints that never require authentication. Everything else is protected
// and must never be requested without a bearer token.
const PUBLIC_PATHS = new Set(['/auth/login', '/health', '/meta']);

// React auth state is synchronized with the storage-level session via this
// subscription: when the server rejects a session (401) or the session is
// found incomplete, subscribers clear their in-memory state.
type SessionListener = () => void;
const sessionListeners = new Set<SessionListener>();

export function onSessionInvalidated(cb: SessionListener): () => void {
  sessionListeners.add(cb);
  return () => sessionListeners.delete(cb);
}

function notifySessionInvalidated() {
  sessionListeners.forEach((cb) => cb());
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function setSession(token: string, user: unknown) {
  if (!token) throw new ApiError(0, 'Login failed: the server did not return a session token.');
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

// Atomic session restore: BOTH a non-empty token and a parseable stored user
// must exist. A partial session (either half missing/malformed) is cleared,
// never treated as logged in.
export function getStoredSession<T>(): { token: string; user: T } | null {
  const token = localStorage.getItem(TOKEN_KEY);
  const raw = localStorage.getItem(USER_KEY);
  if (!token || !raw) {
    if (token || raw) {
      clearSession();
      notifySessionInvalidated();
    }
    return null;
  }
  try {
    const user = JSON.parse(raw) as T;
    if (!user || typeof user !== 'object') throw new Error('malformed user');
    return { token, user };
  } catch {
    clearSession();
    notifySessionInvalidated();
    return null;
  }
}

export function getStoredUser<T>(): T | null {
  return getStoredSession<T>()?.user ?? null;
}

export function isProtectedPath(path: string): boolean {
  return !PUBLIC_PATHS.has(path);
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
  const token = getToken();

  // Protected requests must not silently proceed without a bearer token.
  if (isProtectedPath(path) && !token) {
    clearSession();
    notifySessionInvalidated();
    // Never include the token itself (or its absence details) in messages.
    throw new ApiError(401, 'Your session has expired or is missing. Please sign in again.');
  }

  const headers: Record<string, string> = {};
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
    if (resp.status === 401) {
      // Server rejected the session: drop storage AND React state so the
      // user is returned to the login screen, not left in the portal shell.
      clearSession();
      notifySessionInvalidated();
    }
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
