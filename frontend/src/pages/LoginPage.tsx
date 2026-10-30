import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const DEMO_CREDENTIALS = [
  { username: 'admin', password: 'InstiTrace#Demo1', label: 'Admin' },
  { username: 'officer.rb', password: 'Officer#Demo1', label: 'Bureau Officer' },
  { username: 'reviewer', password: 'Reviewer#Demo1', label: 'Reviewer' },
  { username: 'manager', password: 'Manager#Demo1', label: 'Read-Only Manager' },
];

export default function LoginPage() {
  const { login, demoNotice } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>INSTITRACE</h1>
        <p className="sub">
          Integrated dashboard for institution-related complaint cases across AICTE
          bureaus/cells — synthetic demonstration build (SIH 2026 · SIH26264).
        </p>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        <form onSubmit={submit}>
          <label htmlFor="username">Username</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
          <button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <div className="quick-roles" aria-label="Quick-fill demo credentials">
          {DEMO_CREDENTIALS.map((c) => (
            <button
              key={c.username}
              type="button"
              className="secondary"
              onClick={() => {
                setUsername(c.username);
                setPassword(c.password);
              }}
            >
              {c.label}
              <br />
              <span className="mono">{c.username}</span>
            </button>
          ))}
        </div>
        <p className="small" style={{ marginTop: 16 }}>
          {demoNotice} Demo passwords are documented in the README and are configurable via
          environment variables.
        </p>
      </div>
    </div>
  );
}
