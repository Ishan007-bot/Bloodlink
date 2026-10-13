// Thin wrapper around fetch. Paths are relative, so the same build works behind
// the Vite dev proxy, Nginx in Docker Compose, and the Kubernetes Ingress.

async function request(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(describeError(data) || `${method} ${path} failed (${response.status})`);
  }
  return data;
}

function describeError(data) {
  if (!data || data.detail === undefined) return null;
  if (typeof data.detail === 'string') return data.detail;
  // FastAPI validation errors: [{loc: [...], msg: "..."}]
  return data.detail.map((d) => `${d.loc.slice(1).join('.')}: ${d.msg}`).join('; ');
}

const query = (params) => {
  const entries = Object.entries(params).filter(([, v]) => v !== '' && v !== undefined && v !== null);
  return entries.length ? `?${new URLSearchParams(entries)}` : '';
};

export const api = {
  inventory: () => request('GET', '/api/inventory'),
  stats: () => request('GET', '/api/stats'),
  compatibility: () => request('GET', '/api/compatibility'),

  donors: (filters = {}) => request('GET', `/api/donors${query(filters)}`),
  createDonor: (donor) => request('POST', '/api/donors', donor),
  deleteDonor: (id) => request('DELETE', `/api/donors/${id}`),
  recordDonation: (donorId) => request('POST', '/api/donations', { donor_id: donorId }),

  hospitals: () => request('GET', '/api/hospitals'),
  createHospital: (hospital) => request('POST', '/api/hospitals', hospital),
  deleteHospital: (id) => request('DELETE', `/api/hospitals/${id}`),

  requests: (filters = {}) => request('GET', `/api/requests${query(filters)}`),
  createRequest: (req) => request('POST', '/api/requests', req),
  cancelRequest: (id) => request('PUT', `/api/requests/${id}`, { status: 'CANCELLED' }),
  fulfil: (id) => request('POST', `/api/requests/${id}/fulfil`),
  processQueue: () => request('POST', '/api/requests/process-queue'),
};

export const BLOOD_GROUPS = ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'];
