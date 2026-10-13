export function StatusBadge({ status }) {
  return <span className={`badge status-${status.toLowerCase()}`}>{status}</span>;
}

export function PriorityBadge({ priority }) {
  return <span className={`badge priority-${priority.toLowerCase()}`}>{priority}</span>;
}
