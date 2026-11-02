import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const NAV_GROUPS: { label: string; items: { to: string; label: string; end?: boolean }[] }[] = [
  { label: 'Overview', items: [{ to: '/', label: 'Dashboard', end: true }] },
  { label: 'Institutions', items: [{ to: '/institutions', label: 'Institution Directory' }] },
  { label: 'Complaint Management', items: [{ to: '/cases', label: 'Case Registry' }] },
  { label: 'Coordination', items: [{ to: '/coordination', label: 'Coordination Centre' }] },
  { label: 'Review and Accountability', items: [{ to: '/audit', label: 'Audit Trail' }] },
  { label: 'Reporting', items: [{ to: '/reports', label: 'Reports and Analytics' }] },
  { label: 'Administration', items: [{ to: '/settings', label: 'Settings and System Status' }] },
];

const ROLE_LABELS: Record<string, string> = {
  ADMIN: 'Administrator',
  BUREAU_OFFICER: 'Bureau Officer',
  REVIEWER: 'Reviewer',
  READ_ONLY_MANAGER: 'Read-only Manager',
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [navOpen, setNavOpen] = useState(false);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div className="utility-bar">
        <span className="ub-context">
          Smart India Hackathon 2026 · Problem Statement SIH26264 · Team SONARA (197721) — prototype
        </span>
        <span className="ub-user">
          {user && (
            <>
              <span>{user.display_name}</span>
              <span className="ub-role">{ROLE_LABELS[user.role] ?? user.role}</span>
              <button
                className="ub-logout"
                onClick={() => {
                  logout();
                  navigate('/login');
                }}
              >
                Sign out
              </button>
            </>
          )}
        </span>
      </div>

      <aside className={`sidebar${navOpen ? ' open' : ''}`}>
        <div className="brand">
          <h1>INSTITRACE</h1>
          <small>
            Institution Complaint Monitoring and Cross-Bureau Coordination System
          </small>
        </div>
        <nav aria-label="Primary" onClick={() => setNavOpen(false)}>
          {NAV_GROUPS.map((group) => (
            <div key={group.label}>
              <div className="nav-group-label">{group.label}</div>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => (isActive ? 'active' : '')}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="demo-tag">
          <strong>DEMO · SYNTHETIC DATA</strong>
          <br />
          No real AICTE records or persons. Deadline thresholds are prototype defaults, not
          official SLAs.
        </div>
      </aside>

      <button
        type="button"
        className="nav-toggle"
        aria-label={navOpen ? 'Close navigation menu' : 'Open navigation menu'}
        aria-expanded={navOpen}
        onClick={() => setNavOpen((v) => !v)}
      >
        ☰ Menu
      </button>

      <div className="main">
        <header className="gov-header">
          <div>
            <h2>Institution-Related Complaint Monitoring and Administration Portal</h2>
            <div className="hdr-meta">
              INSTITRACE prototype · AICTE Regulation Bureau context · not an official AICTE website
            </div>
          </div>
          <span className="badge demo-flag">DEMO · SYNTHETIC DATA</span>
        </header>
        <main className="content" id="main-content">
          <Outlet />
        </main>
        <footer className="gov-footer">
          <div className="f-title">INSTITRACE</div>
          <div>
            Institution Complaint Monitoring and Coordination Prototype · Smart India Hackathon
            2026 — SIH26264 · Team SONARA — 197721 · Prototype environment — synthetic data.
          </div>
          <div className="f-disclaimer">
            Production AICTE integration has not been established; this is not an official
            Government of India or AICTE service.
          </div>
        </footer>
      </div>
    </div>
  );
}
