import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { formatDateTime, percent } from '../format.js';
import { PriorityBadge, StatusBadge } from './Badges.jsx';

export default function Dashboard({ notify, goTo }) {
  const [inventory, setInventory] = useState([]);
  const [stats, setStats] = useState(null);
  const [compat, setCompat] = useState({});
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      Promise.all([api.inventory(), api.stats(), api.requests()])
        .then(([inv, st, reqs]) => {
          if (cancelled) return;
          setInventory(inv);
          setStats(st);
          setRecent(reqs.slice(0, 6));
        })
        .catch((e) => !cancelled && notify(e.message, 'error'));
    load();
    api
      .compatibility()
      .then((rows) => !cancelled && setCompat(Object.fromEntries(rows.map((r) => [r.blood_group, r]))))
      .catch(() => {});
    const timer = setInterval(load, 20000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [notify]);

  const expiring = inventory.filter((g) => g.expiring_soon > 0);

  return (
    <>
      <section className="kpis" aria-label="Key figures">
        <Kpi label="Units in stock" value={stats?.units_available ?? '—'} />
        <Kpi label="Open requests" value={stats?.requests_open ?? '—'} tone={stats?.requests_open ? 'warn' : ''} />
        <Kpi label="Fill rate" value={stats ? percent(stats.fill_rate) : '—'} />
        <Kpi label="Wastage (expired)" value={stats ? percent(stats.wastage_rate) : '—'} />
        <Kpi
          label="Avg emergency fill"
          value={stats?.avg_emergency_fill_minutes != null ? `${stats.avg_emergency_fill_minutes} min` : '—'}
        />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Stock by blood group</h2>
          <p className="muted">Safety stock is 10 units per group. Below 5 is critical.</p>
        </div>
        <div className="groups">
          {inventory.map((g) => (
            <article key={g.blood_group} className={`group-tile ${g.level.toLowerCase()}`}>
              <header>
                <span className="group-name">{g.blood_group}</span>
                <span className={`level ${g.level.toLowerCase()}`}>{g.level}</span>
              </header>
              <strong className="count">{g.available}</strong>
              <span className="muted">units available</span>
              {g.expiring_soon > 0 && <span className="expiring">{g.expiring_soon} expiring in 7 days</span>}
              {compat[g.blood_group] && (
                <span className="compat" title="Groups that can receive this blood">
                  Gives to: {compat[g.blood_group].can_donate_to.join(' ')}
                </span>
              )}
            </article>
          ))}
        </div>
      </section>

      <div className="two-col">
        <section className="panel">
          <div className="panel-head">
            <h2>Use first</h2>
            <p className="muted">Groups with units expiring within 7 days.</p>
          </div>
          {expiring.length === 0 ? (
            <p className="empty">Nothing expires in the next 7 days.</p>
          ) : (
            <ul className="list">
              {expiring.map((g) => (
                <li key={g.blood_group}>
                  <span className="chip">{g.blood_group}</span>
                  {g.expiring_soon} of {g.available} units
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head row">
            <div>
              <h2>Latest requests</h2>
              <p className="muted">Most recent hospital requests.</p>
            </div>
            <button className="ghost" onClick={() => goTo('requests')}>
              View all
            </button>
          </div>
          {recent.length === 0 ? (
            <p className="empty">No requests yet.</p>
          ) : (
            <ul className="list">
              {recent.map((r) => (
                <li key={r.id}>
                  <span className="chip">{r.blood_group}</span>
                  <span className="grow">
                    {r.units_needed} u · {r.hospital_name}
                    <small>{formatDateTime(r.created_at)}</small>
                  </span>
                  <PriorityBadge priority={r.priority} />
                  <StatusBadge status={r.status} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}

function Kpi({ label, value, tone = '' }) {
  return (
    <div className={`kpi ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
