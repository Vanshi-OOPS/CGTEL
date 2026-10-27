import { useState } from 'react';
import type { StampVariant } from '../api/types';
import './Stamp.css';

interface StampProps {
  variant: StampVariant;
  size?: 'sm' | 'md' | 'lg';
  animate?: boolean;
}

const STAMP_CONFIG: Record<
  StampVariant,
  { color: string; borderColor: string; rotation: number }
> = {
  AUTHORISED: { color: 'var(--ink)', borderColor: 'var(--ink)', rotation: -2 },
  FLAGGED: {
    color: 'var(--ochre-text)',
    borderColor: 'var(--ochre)',
    rotation: 1.5,
  },
  'HELD FOR REVIEW': {
    color: 'var(--vermilion)',
    borderColor: 'var(--vermilion)',
    rotation: -1,
  },
  REFUSED: {
    color: 'var(--vermilion)',
    borderColor: 'var(--vermilion)',
    rotation: 2,
  },
  'REJECTED MALFORMED': {
    color: 'var(--ink-soft)',
    borderColor: 'var(--ink-soft)',
    rotation: -1.5,
  },
  'NOT ASSESSED': {
    color: 'var(--ink-soft)',
    borderColor: 'var(--ink-soft)',
    rotation: 0.5,
  },
};

const SIZE_MAP = {
  sm: { width: 160, height: 52, fontSize: 11, borderWidth: 2, pad: 8 },
  md: { width: 240, height: 72, fontSize: 16, borderWidth: 3, pad: 12 },
  lg: { width: 320, height: 96, fontSize: 22, borderWidth: 4, pad: 16 },
};

export function Stamp({ variant, size = 'md', animate = true }: StampProps) {
  const config = STAMP_CONFIG[variant];
  const dims = SIZE_MAP[size];
  const [animated] = useState(animate);

  const needsShake = variant === 'HELD FOR REVIEW' || variant === 'REFUSED';

  return (
    <div
      className={`stamp-container ${needsShake && animated ? 'stamp-shake-container' : ''}`}
    >
      <svg
        className={`stamp-svg ${animated ? 'stamp-animated' : ''}`}
        width={dims.width}
        height={dims.height}
        viewBox={`0 0 ${dims.width} ${dims.height}`}
        style={{
          transform: `rotate(${config.rotation}deg)`,
          filter: 'url(#roughen)',
        }}
        role="img"
        aria-label={`Stamp: ${variant}`}
      >
        {/* Double border */}
        <rect
          x={1}
          y={1}
          width={dims.width - 2}
          height={dims.height - 2}
          fill="none"
          stroke={config.borderColor}
          strokeWidth={dims.borderWidth}
          rx={1}
        />
        <rect
          x={dims.borderWidth + 3}
          y={dims.borderWidth + 3}
          width={dims.width - (dims.borderWidth + 3) * 2}
          height={dims.height - (dims.borderWidth + 3) * 2}
          fill="none"
          stroke={config.borderColor}
          strokeWidth={1}
          rx={1}
        />
        <text
          x={dims.width / 2}
          y={dims.height / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="'IBM Plex Mono', monospace"
          fontSize={dims.fontSize}
          fontWeight="600"
          letterSpacing="0.1em"
          fill={config.color}
        >
          {variant}
        </text>
      </svg>
    </div>
  );
}
