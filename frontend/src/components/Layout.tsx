import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/institutions', label: 'Institutions' },
  { to: '/cases', label: 'Case Registry' },
  { to: '/coordination', label: 'Coordination Centre' },
  { to: '/reports', label: 'Reports & Exports' },
  { to: '/audit', label: 'Audit Trail' },
  { to: '/settings', label: 'Settings & Status' },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <h1>INSTITRACE</h1>
          <small>Complaint Monitoring &amp; Cross-Bureau Coordination</small>
        </div>
        <nav aria-label="Primary">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="demo-tag">
          <strong>SYNTHETIC DEMO DATA</strong>
          <br />
          No real AICTE records. Deadline thresholds are prototype defaults, not official SLAs.
        </div>
        <div className="userbox">
          <div>{user?.display_name}</div>
          <div className="role">
            {user?.username} · {user?.role}
          </div>
          <button
            className="secondary"
            style={{ marginTop: 8, padding: '5px 10px', fontSize: 12 }}
            onClick={() => {
              logout();
              navigate('/login');
            }}
          >
            Sign out
          </button>
        </div>
      </aside>
      <div className="main">
        <div className="topbar">
          <h2>Integrated Dashboard for Institution-Related Complaint Cases</h2>
          <span className="small">AICTE Regulation Bureau · SIH2026 PS: SIH26264 · Team SONARA</span>
        </div>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
