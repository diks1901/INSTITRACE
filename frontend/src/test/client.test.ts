import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, buildQuery, clearSession, getToken, setSession } from '../api/client';

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
