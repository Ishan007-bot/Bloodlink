const dateTime = new Intl.DateTimeFormat('en-IN', {
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
const dateOnly = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });

// The API returns naive UTC timestamps; mark them as UTC so the browser shows local time.
const asUtc = (value) => new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);

export const formatDateTime = (value) => (value ? dateTime.format(asUtc(value)) : '—');
export const formatDate = (value) => (value ? dateOnly.format(new Date(value)) : '—');
export const percent = (value) => `${Math.round((value ?? 0) * 1000) / 10}%`;

export function daysLeft(expiresAt) {
  const ms = asUtc(expiresAt) - Date.now();
  return Math.max(0, Math.ceil(ms / 86_400_000));
}
