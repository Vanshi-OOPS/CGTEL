import type { Weights, ContributingSignals } from '../api/types';
import './ContributionBar.css';

interface ContributionBarProps {
  score: number;
  signals: ContributingSignals;
  weights: Weights;
}

export function ContributionBar({
  score,
  signals,
  weights,
}: ContributionBarProps) {
  const termRev = weights.w1 * signals.reversibility;
  const confGap = 1 - signals.confidence;
  const termConf = weights.w2 * confGap;
  const termFail = weights.w3 * signals.failure_rate;

  // Guard against division by zero
  const total = score > 0 ? score : 1;
  const pctRev = ((termRev / total) * 100).toFixed(1);
  const pctConf = ((termConf / total) * 100).toFixed(1);
  const pctFail = ((termFail / total) * 100).toFixed(1);

  const fmt = (n: number) => n.toFixed(4);
  const fmtW = (n: number) => {
    // Show as fraction if close to 1/3
    if (Math.abs(n - 1 / 3) < 0.002) return '1/3';
    return n.toFixed(3);
  };

  return (
    <div className="contribution-bar">
      <div className="contribution-bar__bar">
        {/* Reversibility - solid ink */}
        <div
          className="contribution-bar__segment contribution-bar__segment--reversibility"
          style={{ width: `${pctRev}%` }}
          title={`Reversibility: ${fmt(termRev)}`}
        />
        {/* Confidence gap - diagonal hatch */}
        <svg
          className="contribution-bar__segment"
          style={{ width: `${pctConf}%` }}
          preserveAspectRatio="none"
          width="100%"
          height="100%"
        >
          <rect width="100%" height="100%" fill="url(#hatch-diagonal-ink)" />
        </svg>
        {/* Failure rate - dotted */}
        <svg
          className="contribution-bar__segment"
          style={{ width: `${pctFail}%` }}
          preserveAspectRatio="none"
          width="100%"
          height="100%"
        >
          <rect width="100%" height="100%" fill="url(#hatch-dots)" />
        </svg>
      </div>

      <table className="contribution-bar__table">
        <tbody>
          <tr>
            <td>
              <span className="contribution-bar__swatch contribution-bar__swatch--solid" />
              {fmtW(weights.w1)} × {fmt(signals.reversibility)} = {fmt(termRev)}
            </td>
            <td>reversibility</td>
          </tr>
          <tr>
            <td>
              <svg
                className="contribution-bar__swatch"
                width="10"
                height="10"
                style={{ border: 'none' }}
              >
                <rect width="10" height="10" fill="url(#hatch-diagonal-ink)" />
              </svg>
              {fmtW(weights.w2)} × {fmt(confGap)} = {fmt(termConf)}
            </td>
            <td>
              agreement gap (agreement {signals.confidence.toFixed(2)})
            </td>
          </tr>
          <tr>
            <td>
              <svg
                className="contribution-bar__swatch"
                width="10"
                height="10"
                style={{ border: 'none' }}
              >
                <rect width="10" height="10" fill="url(#hatch-dots)" />
              </svg>
              {fmtW(weights.w3)} × {fmt(signals.failure_rate)} = {fmt(termFail)}
            </td>
            <td>tool failure history</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
