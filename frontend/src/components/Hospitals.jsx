import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';

const EMPTY = { name: '', city: '', contact_phone: '' };

export default function Hospitals({ notify }) {
  const [hospitals, setHospitals] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      api
        .hospitals()
        .then(setHospitals)
        .catch((e) => notify(e.message, 'error')),
    [notify],
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
    if (await run(() => api.createHospital(form), (h) => `${h.name} added`)) setForm(EMPTY);
  };

  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Add a hospital</h2>
          <p className="muted">Hospitals raise blood requests against the bank&apos;s stock.</p>
        </div>
        <form className="form-grid" onSubmit={submit}>
          <label>
            Name
            <input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>
            City
            <input required minLength={2} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
          </label>
          <label>
            Contact phone
            <input
              value={form.contact_phone}
              pattern="[0-9+\- ]*"
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
            />
          </label>
          <button className="primary" disabled={busy}>
            Add hospital
          </button>
        </form>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Hospitals</h2>
          <p className="muted">A hospital with requests on record cannot be deleted.</p>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>City</th>
                <th>Contact</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {hospitals.map((h) => (
                <tr key={h.id}>
                  <td>{h.name}</td>
                  <td>{h.city}</td>
                  <td>{h.contact_phone || '—'}</td>
                  <td className="row-actions">
                    <button
                      className="small ghost"
                      disabled={busy}
                      onClick={() => run(() => api.deleteHospital(h.id), () => `${h.name} removed`)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {hospitals.length === 0 && <p className="empty">No hospitals yet.</p>}
        </div>
      </section>
    </>
  );
}
