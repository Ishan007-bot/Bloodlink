import { useCallback, useEffect, useState } from 'react';
import { BLOOD_GROUPS, api } from '../api.js';
import { formatDate } from '../format.js';

const EMPTY = { name: '', blood_group: 'O+', phone: '', city: '' };

export default function Donors({ notify }) {
  const [donors, setDonors] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [group, setGroup] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      api
        .donors({ blood_group: group })
        .then(setDonors)
        .catch((e) => notify(e.message, 'error')),
    [group, notify],
  );

  useEffect(() => {
    load();
  }, [load]);

  const run = async (action, message) => {
    setBusy(true);
    try {
      const value = await action();
      notify(message(value));
      await load();
      return true;
    } catch (e) {
      notify(e.message, 'error');
      return false;
    } finally {
      setBusy(false);
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    const ok = await run(() => api.createDonor(form), (d) => `Donor ${d.name} (${d.blood_group}) registered`);
    if (ok) setForm(EMPTY);
  };

  const today = new Date().toISOString().slice(0, 10);

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Register a donor</h2>
          <p className="muted">A donor can give whole blood again 90 days after their last donation.</p>
        </div>
        <form className="form-grid" onSubmit={submit}>
          <label>
            Name
            <input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
            Phone
            <input
              value={form.phone}
              pattern="[0-9+\- ]*"
              placeholder="+91 98765 43210"
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </label>
          <label>
            City
            <input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
          </label>
          <button className="primary" disabled={busy}>
            Register donor
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-head row">
          <div>
            <h2>Donors</h2>
            <p className="muted">{donors.length} shown</p>
          </div>
          <select value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Filter by blood group">
            <option value="">All groups</option>
            {BLOOD_GROUPS.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Group</th>
                <th>City</th>
                <th>Last donation</th>
                <th>Eligible</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {donors.map((d) => {
                const eligible = !d.next_eligible_on || d.next_eligible_on <= today;
                return (
                  <tr key={d.id}>
                    <td>
                      {d.name}
                      {d.phone && <small>{d.phone}</small>}
                    </td>
                    <td>
                      <span className="chip">{d.blood_group}</span>
                    </td>
                    <td>{d.city || '—'}</td>
                    <td>{formatDate(d.last_donation_on)}</td>
                    <td>
                      {eligible ? (
                        <span className="badge status-fulfilled">Now</span>
                      ) : (
                        <span className="badge status-pending">{formatDate(d.next_eligible_on)}</span>
                      )}
                    </td>
                    <td className="row-actions">
                      <button
                        className="small primary"
                        disabled={busy || !eligible}
                        title={eligible ? 'Record a donation today' : 'Not eligible yet'}
                        onClick={() =>
                          run(
                            () => api.recordDonation(d.id),
                            (u) => `Unit #${u.id} (${u.blood_group}) added to stock from ${d.name}`,
                          )
                        }
                      >
                        Record donation
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {donors.length === 0 && <p className="empty">No donors yet.</p>}
        </div>
      </section>
    </>
  );
}
