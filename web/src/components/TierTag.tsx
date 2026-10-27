import type { Tier } from '../api/types';
import './TierTag.css';

interface TierTagProps {
  tier: Tier;
}

const TIER_LABELS: Record<Tier, string> = {
  AUTO_ALLOW: 'Auto-Allow',
  LOG_AND_MONITOR: 'Log & Monitor',
  HUMAN_REVIEW: 'Human Review',
};

const TIER_CLASS: Record<Tier, string> = {
  AUTO_ALLOW: 'tier-tag--auto',
  LOG_AND_MONITOR: 'tier-tag--monitor',
  HUMAN_REVIEW: 'tier-tag--review',
};

const TIER_PATTERN: Record<Tier, string | null> = {
  AUTO_ALLOW: null,
  LOG_AND_MONITOR: 'url(#hatch-diagonal)',
  HUMAN_REVIEW: 'url(#hatch-cross)',
};

export function TierTag({ tier }: TierTagProps) {
  const pattern = TIER_PATTERN[tier];
  return (
    <span className={`tier-tag ${TIER_CLASS[tier]}`}>
      {pattern && (
        <svg
          className="tier-tag__pattern"
          width="100%"
          height="100%"
          aria-hidden="true"
        >
          <rect width="100%" height="100%" fill={pattern} />
        </svg>
      )}
      <span style={{ position: 'relative', zIndex: 1 }}>
        {TIER_LABELS[tier]}
      </span>
    </span>
  );
}
