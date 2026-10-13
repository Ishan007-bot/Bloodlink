import { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import Dashboard from './components/Dashboard.jsx';
import Donors from './components/Donors.jsx';
import Hospitals from './components/Hospitals.jsx';
import Requests from './components/Requests.jsx';

const TABS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'requests', label: 'Requests' },
  { id: 'donors', label: 'Donors' },
  { id: 'hospitals', label: 'Hospitals' },
];

export default function App() {
  const [tab, setTab] = useState('dashboard');
  const [notice, setNotice] = useState(null);
  const [online, setOnline] = useState(null);

  // Components call notify() after an action; errors stay until dismissed, successes fade.
  const notify = useCallback((message, kind = 'ok') => setNotice({ message, kind, at: Date.now() }), []);

  useEffect(() => {
    if (!notice || notice.kind === 'error') return undefined;
    const timer = setTimeout(() => setNotice(null), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const check = () =>
      api
        .stats()
        .then(() => setOnline(true))
        .catch(() => setOnline(false));
    check();
    const timer = setInterval(check, 15000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 32 32" aria-hidden="true">
            <path d="M16 2C16 2 6 14 6 20a10 10 0 0 0 20 0C26 14 16 2 16 2z" />
          </svg>
          <div>
            <strong>BloodLink</strong>
            <span>Blood bank inventory &amp; hospital requests</span>
          </div>
        </div>
        <span className={`status-pill ${online ? 'up' : online === false ? 'down' : ''}`}>
          {online === null ? 'Connecting…' : online ? 'API online' : 'API unreachable'}
        </span>
      </header>

      <nav className="tabs" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={tab === t.id ? 'active' : ''}
            onClick={() => setTab(t.id)}
            aria-current={tab === t.id ? 'page' : undefined}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {notice && (
        <div className={`notice ${notice.kind}`} role={notice.kind === 'error' ? 'alert' : 'status'}>
          <span>{notice.message}</span>
          <button onClick={() => setNotice(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <main>
        {tab === 'dashboard' && <Dashboard notify={notify} goTo={setTab} />}
        {tab === 'requests' && <Requests notify={notify} />}
        {tab === 'donors' && <Donors notify={notify} />}
        {tab === 'hospitals' && <Hospitals notify={notify} />}
      </main>

      <footer>BloodLink · FastAPI + React · Shelf life 42 days · Donation gap 90 days</footer>
    </div>
  );
}
