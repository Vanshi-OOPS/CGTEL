import type { RunStatus, Tier } from '../api/types';
import './StatusBadge.css';

function slug(value: string): string { return value.toLowerCase().replaceAll('_', '-'); }

export function StatusBadge({ status }: { status: RunStatus }) {
  return <span className={`status-badge status-badge--${slug(status)}`}><i aria-hidden="true" />{status.replaceAll('_', ' ')}</span>;
}

export function DecisionBadge({ tier }: { tier: Tier | null | undefined }) {
  if (!tier) return <span className="decision-badge decision-badge--none">Not assessed</span>;
  return <span className={`decision-badge decision-badge--${slug(tier)}`}><i aria-hidden="true" />{tier.replaceAll('_', ' ')}</span>;
}
