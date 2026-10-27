import { useEffect, useState } from 'react';
import './RiskRuler.css';

interface RiskRulerProps {
  score: number | null;
  tau1: number;
  tau2: number;
  assessed: boolean;
}

export function RiskRuler({ score, tau1, tau2, assessed }: RiskRulerProps) {
  const [displayScore, setDisplayScore] = useState(0);

  useEffect(() => {
    if (score !== null && assessed) {
      // Slight delay to trigger CSS transition
      const timer = setTimeout(() => setDisplayScore(score), 50);
      return () => clearTimeout(timer);
    }
  }, [score, assessed]);

  if (!assessed) {
    return (
      <div className="risk-ruler">
        <div className="risk-ruler__not-scored">NEVER SCORED</div>
      </div>
    );
  }

  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

  // Tick marks every 0.05, labelled every 0.25
  const ticks: { pos: number; major: boolean; label?: string }[] = [];
  for (let i = 0; i <= 20; i++) {
    const val = i * 0.05;
    const major = val % 0.25 === 0 || Math.abs(val % 0.25) < 0.001;
    ticks.push({
      pos: val,
      major,
      label: major ? val.toFixed(2) : undefined,
    });
  }

  return (
    <div className="risk-ruler">
      <div className="risk-ruler__track">
        {/* AUTO_ALLOW zone */}
        <div
          className="risk-ruler__zone risk-ruler__zone--auto"
          style={{ left: 0, width: pct(tau1) }}
        />
        {/* LOG_AND_MONITOR zone */}
        <svg
          className="risk-ruler__zone"
          style={{ left: pct(tau1), width: pct(tau2 - tau1) }}
          preserveAspectRatio="none"
          width="100%"
          height="100%"
        >
          <rect width="100%" height="100%" fill="url(#hatch-diagonal)" />
        </svg>
        {/* HUMAN_REVIEW zone */}
        <svg
          className="risk-ruler__zone"
          style={{ left: pct(tau2), width: pct(1 - tau2) }}
          preserveAspectRatio="none"
          width="100%"
          height="100%"
        >
          <rect width="100%" height="100%" fill="url(#hatch-cross)" />
        </svg>

        {/* Tau markers */}
        <div
          className="risk-ruler__threshold"
          style={{ left: pct(tau1) }}
        >
          <span className="risk-ruler__threshold-label">τ₁ {tau1.toFixed(2)}</span>
        </div>
        <div
          className="risk-ruler__threshold"
          style={{ left: pct(tau2) }}
        >
          <span className="risk-ruler__threshold-label">τ₂ {tau2.toFixed(2)}</span>
        </div>

        {/* Needle */}
        {score !== null && (
          <div
            className="risk-ruler__needle"
            style={{ left: pct(displayScore) }}
          >
            <div className="risk-ruler__needle-flag">
              {score.toFixed(4)}
            </div>
          </div>
        )}
      </div>

      {/* Tick marks */}
      <div className="risk-ruler__ticks">
        {ticks.map((t) => (
          <div key={t.pos}>
            <div
              className={`risk-ruler__tick ${t.major ? 'risk-ruler__tick--major' : ''}`}
              style={{ left: pct(t.pos) }}
            />
            {t.label && (
              <span
                className="risk-ruler__tick-label"
                style={{ left: pct(t.pos) }}
              >
                {t.label}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
