import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import { api, clearSession, getStoredSession, onSessionInvalidated, setSession } from '../api/client';
import { CurrentUser, Role } from '../api/types';

interface AuthContextValue {
  user: CurrentUser | null;
  login: (username: string, password: string) => Promise<CurrentUser>;
  logout: () => void;
  canWriteCases: boolean;
  canReview: boolean;
  canAdmin: boolean;
  demoNotice: string;
}

const DEMO_NOTICE =
  'Local demo mode: synthetic users and demo-grade token signing. Not production security.';

const AuthContext = createContext<AuthContextValue | null>(null);

interface LoginResponse {
  token: string;
  username: string;
  display_name: string;
  role: Role;
  bureau_code?: string | null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // Atomic restore: only a session with BOTH a token and a valid user object
  // is treated as authenticated; anything partial is cleared by the client.
  const [user, setUser] = useState<CurrentUser | null>(
    () => getStoredSession<CurrentUser>()?.user ?? null,
  );

  // When the backend rejects a session (401) or storage is incomplete, the
  // API client invalidates the session and asks us to drop React state, so the
  // protected router sends the user back to the login screen.
  useEffect(
    () =>
      onSessionInvalidated(() => {
        setUser(null);
      }),
    [],
  );

  const value = useMemo<AuthContextValue>(() => {
    const role = user?.role;
    return {
      user,
      async login(username: string, password: string) {
        const resp = await api.post<LoginResponse>('/auth/login', { username, password });
        const u: CurrentUser = {
          username: resp.username,
          display_name: resp.display_name,
          role: resp.role,
          bureau_code: resp.bureau_code ?? null,
        };
        setSession(resp.token, u);
        setUser(u);
        return u;
      },
      logout() {
        clearSession();
        setUser(null);
      },
      canWriteCases: role === 'ADMIN' || role === 'BUREAU_OFFICER',
      canReview: role === 'ADMIN' || role === 'REVIEWER',
      canAdmin: role === 'ADMIN',
      demoNotice: DEMO_NOTICE,
    };
  }, [user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
