import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  api,
  buildQuery,
  clearSession,
  getStoredSession,
  getToken,
  onSessionInvalidated,
  setSession,
} from '../api/client';

describe('buildQuery', () => {
  it('omits empty values and encodes parameters', () => {
    const q = buildQuery({ q: 'sun rise', region: '', page: 2, skip: undefined, none: null });
    expect(q).toBe('?q=sun+rise&page=2');
  });

  it('returns empty string when nothing is set', () => {
    expect(buildQuery({})).toBe('');
  });
});

describe('api client', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('attaches bearer token from session storage', async () => {
    setSession('tok123', { username: 'admin' });
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await api.get('/dashboard/summary');
    const [, init] = fetchSpy.mock.calls[0];
    expect((init?.headers as Record<string, string>)['Authorization']).toBe('Bearer tok123');
  });

  it('normalizes backend error envelopes into ApiError', async () => {
    setSession('tok', { username: 'admin' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 422, message: 'Invalid status transition PENDING -> PENDING', details: [] } }),
        { status: 422 },
      ),
    );
    await expect(api.get('/cases/1')).rejects.toMatchObject({
      code: 422,
      message: 'Invalid status transition PENDING -> PENDING',
    });
    await expect(api.get('/cases/1')).rejects.toBeInstanceOf(ApiError);
  });

  it('clears the session on 401 responses', async () => {
    setSession('stale', { username: 'admin' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 401, message: 'Token expired' } }), { status: 401 }),
    );
    await expect(api.get('/cases')).rejects.toMatchObject({ code: 401 });
    expect(getToken()).toBeNull();
    clearSession();
  });
});

describe('session lifecycle (auth hardening)', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  // 1. token + user both present -> session restores
  it('restores the session when both token and user are stored', () => {
    setSession('tok-abc', { username: 'reviewer', role: 'REVIEWER' });
    const s = getStoredSession<{ username: string; role: string }>();
    expect(s?.token).toBe('tok-abc');
    expect(s?.user.username).toBe('reviewer');
  });

  // 2. user present but token missing -> session rejected (and cleared)
  it('rejects a session with user but no token', () => {
    localStorage.setItem('institrace.user', JSON.stringify({ username: 'admin' }));
    const cleared = vi.fn();
    const off = onSessionInvalidated(cleared);
    expect(getStoredSession()).toBeNull();
    expect(localStorage.getItem('institrace.user')).toBeNull();
    expect(cleared).toHaveBeenCalledTimes(1);
    off();
  });

  // 3. token present but user missing/malformed -> session rejected
  it('rejects a session with token but no user', () => {
    localStorage.setItem('institrace.token', 'tok-only');
    expect(getStoredSession()).toBeNull();
    expect(getToken()).toBeNull();
  });

  it('rejects a session whose stored user is malformed JSON', () => {
    setSession('tok', { username: 'admin' });
    localStorage.setItem('institrace.user', '{not-json');
    expect(getStoredSession()).toBeNull();
    expect(getToken()).toBeNull();
  });

  // 4. protected API request without a token -> rejected BEFORE any request
  it('blocks protected calls without a token before fetch runs', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const cleared = vi.fn();
    const off = onSessionInvalidated(cleared);
    await expect(api.get('/cases')).rejects.toMatchObject({
      code: 401,
      message: expect.stringContaining('sign in'),
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(cleared).toHaveBeenCalledTimes(1);
    off();
  });

  // 5. valid token -> Authorization header attached (see existing test) and
  //    public endpoints still work with no token at all
  it('allows unauthenticated endpoints without a token', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => new Response(JSON.stringify({ status: 'ok' }), { status: 200 }));
    for (const path of ['/auth/login', '/health', '/meta']) {
      await (path === '/auth/login'
        ? api.post(path, { username: 'x', password: 'y' })
        : api.get(path));
    }
    expect(fetchSpy).toHaveBeenCalledTimes(3);
    for (const [, init] of fetchSpy.mock.calls) {
      expect((init?.headers as Record<string, string>)['Authorization']).toBeUndefined();
    }
  });

  // 6. backend 401 -> storage AND auth listeners (React state) synchronized
  it('a backend 401 clears storage and notifies auth state listeners', async () => {
    setSession('expired', { username: 'admin' });
    const cleared = vi.fn();
    const off = onSessionInvalidated(cleared);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 401, message: 'Token expired' } }), { status: 401 }),
    );
    await expect(api.get('/cases')).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
    expect(localStorage.getItem('institrace.user')).toBeNull();
    expect(cleared).toHaveBeenCalledTimes(1);
    off();
  });

  // 7. successful login response -> both session values stored together
  it('stores token and user together on successful login', () => {
    const resp = { token: 'fresh-tok', username: 'manager', display_name: 'M', role: 'READ_ONLY_MANAGER' };
    setSession(resp.token, {
      username: resp.username,
      display_name: resp.display_name,
      role: resp.role,
    });
    expect(getToken()).toBe('fresh-tok');
    const s = getStoredSession<{ role: string }>();
    expect(s?.user.role).toBe('READ_ONLY_MANAGER');
  });

  it('never stores a session when the server returns an empty token', () => {
    expect(() => setSession('', { username: 'admin' })).toThrow(/token/i);
    expect(getToken()).toBeNull();
  });
});
