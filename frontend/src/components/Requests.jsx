import { useCallback, useEffect, useState } from 'react';
import { BLOOD_GROUPS, api } from '../api.js';
import { daysLeft, formatDateTime } from '../format.js';
import { PriorityBadge, StatusBadge } from './Badges.jsx';

const EMPTY = { hospital_id: '', blood_group: 'O+', units_needed: 1, priority: 'ROUTINE', patient_ref: '' };

export default function Requests({ notify }) {
  const [requests, setRequests] = useState([]);
  const [hospitals, setHospitals] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [filter, setFilter] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      api
        .requests({ status: filter })
        .then(setRequests)
        .catch((e) => notify(e.message, 'error')),
    [filter, notify],
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .hospitals()
      .then((list) => {
        setHospitals(list);
        setForm((f) => ({ ...f, hospital_id: f.hospital_id || list[0]?.id || '' }));
      })
      .catch((e) => notify(e.message, 'error'));
  }, [notify]);

  const run = async (action, success) => {
    setBusy(true);
    try {
      const value = await action();
      if (success) notify(success(value));
      await load();
      return value;
    } catch (e) {
      notify(e.message, 'error');
      return null;
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    const created = await run(
      () => api.createRequest({ ...form, hospital_id: Number(form.hospital_id), units_needed: Number(form.units_needed) }),
      (r) => `Request #${r.id} raised: ${r.units_needed} × ${r.blood_group} (${r.priority.toLowerCase()})`,
    );
    if (created) setForm({ ...EMPTY, hospital_id: form.hospital_id });
  };

  const fulfil = async (id) => {
    const outcome = await run(() => api.fulfil(id));
    if (outcome) {
      setResult(outcome);
      const n = outcome.newly_allocated.length;
      notify(n ? `Allocated ${n} unit${n > 1 ? 's' : ''} to request #${id}` : `No compatible stock for request #${id}`,
        n ? 'ok' : 'error');
    }
  };

  const processQueue = () =>
    run(api.processQueue, (touched) =>
      touched.length ? `Queue processed: ${touched.length} request(s) received units` : 'Queue processed: no matching stock',
    );

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Raise a request</h2>
          <p className="muted">Emergency requests are served first when the queue is processed.</p>
        </div>
        {hospitals.length === 0 ? (
          <p className="empty">Add a hospital first.</p>
        ) : (
          <form className="form-grid" onSubmit={submit}>
            <label>
              Hospital
              <select value={form.hospital_id} onChange={(e) => setForm({ ...form, hospital_id: e.target.value })}>
                {hospitals.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Blood group
              <select value={form.blood_group} onChange={(e) => setForm({ ...form, blood_group: e.target.value })}>
                {BLOOD_GROUPS.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </label>
            <label>
              Units
              <input
                type="number"
                min="1"
                max="20"
                value={form.units_needed}
                onChange={(e) => setForm({ ...form, units_needed: e.target.value })}
              />
            </label>
            <label>
              Priority
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                <option value="ROUTINE">Routine</option>
                <option value="EMERGENCY">Emergency</option>
              </select>
            </label>
            <label>
              Patient ref
              <input
                value={form.patient_ref}
                maxLength={60}
                placeholder="e.g. ICU-12"
                onChange={(e) => setForm({ ...form, patient_ref: e.target.value })}
              />
            </label>
            <button className="primary" disabled={busy}>
              Raise request
            </button>
          </form>
        )}
      </section>

      {result && (
        <section className="panel result" aria-live="polite">
          <div className="panel-head row">
            <div>
              <h2>
                Request #{result.request.id}: {result.request.units_allocated}/{result.request.units_needed} units ·{' '}
                <StatusBadge status={result.request.status} />
              </h2>
              <p className="muted">Exact group first, O- kept for last, oldest units used first.</p>
            </div>
            <button className="ghost" onClick={() => setResult(null)}>
              Close
            </button>
          </div>
          {result.newly_allocated.length === 0 ? (
            <p className="empty">No compatible units are in stock right now.</p>
          ) : (
            <ul className="list">
              {result.newly_allocated.map((a) => (
                <li key={a.unit_id}>
                  <span className="chip">{a.blood_group}</span>
                  <span className="grow">
                    Unit #{a.unit_id}
                    <small>expires in {daysLeft(a.expires_at)} day{daysLeft(a.expires_at) === 1 ? '' : 's'}</small>
                  </span>
                  <span className={`badge match-${a.match_type.toLowerCase()}`}>{a.match_type}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="panel">
        <div className="panel-head row">
          <div>
            <h2>Requests</h2>
            <p className="muted">{requests.length} shown</p>
          </div>
          <div className="actions">
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter by status">
              <option value="">All statuses</option>
              <option value="PENDING">Pending</option>
              <option value="PARTIAL">Partial</option>
              <option value="FULFILLED">Fulfilled</option>
              <option value="CANCELLED">Cancelled</option>
            </select>
            <button className="primary" onClick={processQueue} disabled={busy}>
              Process queue
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Hospital</th>
                <th>Group</th>
                <th>Units</th>
                <th>Priority</th>
                <th>Status</th>
                <th>Raised</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => {
                const open = r.status === 'PENDING' || r.status === 'PARTIAL';
                return (
                  <tr key={r.id}>
                    <td>{r.id}</td>
                    <td>
                      {r.hospital_name}
                      {r.patient_ref && <small>{r.patient_ref}</small>}
                    </td>
                    <td>
                      <span className="chip">{r.blood_group}</span>
                    </td>
                    <td>
                      {r.units_allocated}/{r.units_needed}
                    </td>
                    <td>
                      <PriorityBadge priority={r.priority} />
                    </td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td>{formatDateTime(r.created_at)}</td>
                    <td className="row-actions">
                      {open && (
                        <>
                          <button className="small primary" disabled={busy} onClick={() => fulfil(r.id)}>
                            Fulfil
                          </button>
                          <button
                            className="small ghost"
                            disabled={busy}
                            onClick={() => run(() => api.cancelRequest(r.id), () => `Request #${r.id} cancelled`)}
                          >
                            Cancel
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {requests.length === 0 && <p className="empty">No requests match.</p>}
        </div>
      </section>
    </>
  );
}
