import { createContext, ReactNode, useContext, useMemo, useState } from 'react';
import { api, clearSession, getStoredUser, setSession } from '../api/client';
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
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(() => getStoredUser<CurrentUser>());

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
