import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { ApiError, getRuns } from '../api/client';
import type { RunRecord, Tier } from '../api/types';
import { Icon } from '../components/Icon';
import { DecisionBadge, StatusBadge } from '../components/StatusBadge';
import './Overview.css';

const DECISIONS: { tier: Tier | 'NOT_ASSESSED'; title: string }[] = [
  { tier: 'AUTO_ALLOW', title: 'Auto allow' },
  { tier: 'LOG_AND_MONITOR', title: 'Log & monitor' },
  { tier: 'HUMAN_REVIEW', title: 'Human review' },
  { tier: 'NOT_ASSESSED', title: 'Not assessed' },
];

function assessedScore(run: RunRecord): number | null {
  const score = run.decision?.score;
  return run.decision?.assessed && score !== null && score !== undefined && Number.isFinite(score) ? score : null;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'The run service could not be reached.';
  return `The run request failed (${error.status}).`;
}

function Metric({ label, value, note, icon, accent }: { label: string; value: string; note: string; icon: 'activity' | 'shield' | 'policy' | 'benchmark'; accent: string }) {
  return <article className={`overview-metric overview-metric--${accent}`}>
    <div className="overview-metric__top"><span>{label}</span><span className="overview-metric__icon"><Icon name={icon} size={16} /></span></div>
    <strong>{value}</strong><small>{note}</small>
  </article>;
}

function RiskGauge({ value, sampleSize }: { value: number | null; sampleSize: number }) {
  const radius = 59;
  const circumference = 2 * Math.PI * radius;
  const fraction = value === null ? 0 : Math.max(0, Math.min(1, value));
  return <div className="risk-gauge-layout">
    <div className="risk-gauge">
      <svg viewBox="0 0 150 150" role="img" aria-label={value === null ? 'Average risk unavailable; there are no assessed scores' : `Average assessed risk score ${value.toFixed(4)} from ${sampleSize} runs`}>
        <defs><linearGradient id="overview-risk-gradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#9d72ff"/><stop offset="58%" stopColor="#df64ce"/><stop offset="100%" stopColor="#ff866f"/></linearGradient></defs>
        <circle className="risk-gauge__track" cx="75" cy="75" r={radius} />
        {value !== null && <circle className="risk-gauge__value" cx="75" cy="75" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - fraction)} />}
      </svg>
      <div className="risk-gauge__center"><strong>{value === null ? '—' : value.toFixed(3)}</strong><span>AVG RISK</span></div>
    </div>
    <div className="risk-gauge__meta"><div><b>{value === null ? 'No scored runs' : `${sampleSize} assessed ${sampleSize === 1 ? 'run' : 'runs'}`}</b><span>Mean of available assessed decision scores.</span></div><div className="risk-gauge__scale"><span>0.00</span><span>1.00</span></div></div>
  </div>;
}

function ActivityChart({ runs }: { runs: RunRecord[] }) {
  const points = useMemo(() => runs.map((run) => ({ run, score: assessedScore(run), time: Date.parse(run.created_at) })).filter((point) => point.score !== null && Number.isFinite(point.time)).sort((a, b) => a.time - b.time).slice(-24), [runs]);
  if (!points.length) return <div className="chart-empty">Activity will appear after runs have assessed scores and usable timestamps.</div>;
  const left = 28; const right = 616; const top = 18; const bottom = 156;
  const minTime = points[0].time; const maxTime = points[points.length - 1].time;
  const coords = points.map(({ score, time }) => ({ x: left + (maxTime === minTime ? .5 : (time - minTime) / (maxTime - minTime)) * (right - left), y: bottom - (score as number) * (bottom - top) }));
  const polyline = coords.map(({ x, y }) => `${x},${y}`).join(' ');
  return <div className="activity-chart">
    <svg viewBox="0 0 640 190" role="img" aria-label={`Risk score over time for ${points.length} assessed runs`}>
      <defs><linearGradient id="activity-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a26bdb" stopOpacity=".24"/><stop offset="100%" stopColor="#a26bdb" stopOpacity="0"/></linearGradient><linearGradient id="activity-line" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#9a72f0"/><stop offset="56%" stopColor="#d56bd1"/><stop offset="100%" stopColor="#f28a8f"/></linearGradient></defs>
      {[0, .25, .5, .75, 1].map((value) => { const y = bottom - value * (bottom - top); return <g key={value}><line x1={left} x2={right} y1={y} y2={y} className="activity-chart__grid"/><text x="2" y={y + 4} className="activity-chart__axis">{value.toFixed(2)}</text></g>; })}
      {points.length > 1 && <polygon points={`${left},${bottom} ${polyline} ${right},${bottom}`} fill="url(#activity-fill)"/>}
      {points.length > 1 && <polyline points={polyline} className="activity-chart__line"/>}
      {coords.map((point, index) => <circle key={points[index].run.run_id} className="activity-chart__dot" cx={point.x} cy={point.y} r="4"><title>{`${formatTime(points[index].run.created_at)} · score ${points[index].score?.toFixed(4)} · ${points[index].run.run_id}`}</title></circle>)}
      <text x={left} y="182" className="activity-chart__axis">{formatTime(new Date(minTime).toISOString())}</text>
      <text x={right} y="182" textAnchor="end" className="activity-chart__axis">{formatTime(new Date(maxTime).toISOString())}</text>
    </svg>
    <div className="activity-chart__legend"><span><i />Assessed risk score</span><span>Most recent {points.length} scored runs · max 24 shown</span></div>
  </div>;
}

function DecisionDistribution({ runs }: { runs: RunRecord[] }) {
  const counts = DECISIONS.map((item) => ({ ...item, count: runs.filter((run) => item.tier === 'NOT_ASSESSED' ? !run.decision?.assessed || !run.decision?.tier : run.decision?.tier === item.tier).length }));
  const denominator = runs.length || 1;
  return <div className="decision-distribution">{counts.map((item) => <div className="distribution-row" key={item.tier}>
    <div className="distribution-row__label"><span className={`distribution-dot distribution-dot--${item.tier.toLowerCase().replaceAll('_', '-')}`} />{item.title}<strong>{item.count}</strong></div>
    <div className="distribution-row__track"><span className={`distribution-row__fill distribution-row__fill--${item.tier.toLowerCase().replaceAll('_', '-')}`} style={{ width: `${item.count / denominator * 100}%` }} /></div>
  </div>)}</div>;
}

function RecentRuns({ runs }: { runs: RunRecord[] }) {
  if (!runs.length) return <div className="overview-empty">No runs have been recorded yet. File a request from Desk to see its audit entry here.</div>;
  return <div className="overview-table-wrap"><table className="overview-table">
    <thead><tr><th>Created</th><th>Tool</th><th>Risk</th><th>Decision</th><th>Run status</th><th><span className="sr-only">Inspect run</span></th></tr></thead>
    <tbody>{runs.slice(0, 7).map((run) => <tr key={run.run_id}>
      <td><time dateTime={run.created_at}>{formatTime(run.created_at)}</time><code>{run.run_id}</code></td>
      <td className="overview-table__tool">{run.tool_name ?? '—'}</td>
      <td className="overview-table__score">{assessedScore(run)?.toFixed(4) ?? '—'}</td>
      <td><DecisionBadge tier={run.decision?.tier} /></td>
      <td><StatusBadge status={run.status} /></td>
      <td><details className="overview-run-details"><summary>Inspect</summary><div><span>MODE</span><code>{run.mode} · {run.llm_mode}</code><span>ARGUMENTS</span><pre>{JSON.stringify(run.args ?? {}, null, 2)}</pre>{run.result !== null && run.result !== undefined && <><span>RESULT</span><pre>{typeof run.result === 'string' ? run.result : JSON.stringify(run.result, null, 2)}</pre></>}{run.error && <><span>ERROR</span><pre>{run.error}</pre></>}</div></details></td>
    </tr>)}</tbody>
  </table></div>;
}

export function OverviewPage() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try { setRuns(await getRuns(1000)); }
    catch (err) { setError(errorMessage(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { let active = true; (async () => {
    try { const result = await getRuns(1000); if (active) setRuns(result); }
    catch (err) { if (active) setError(errorMessage(err)); }
    finally { if (active) setLoading(false); }
  })(); return () => { active = false; }; }, []);

  const assessed = useMemo(() => runs.map((run) => assessedScore(run)).filter((score): score is number => score !== null), [runs]);
  const average = assessed.length ? assessed.reduce((sum, score) => sum + score, 0) / assessed.length : null;
  const denied = runs.filter((run) => run.status === 'DENIED_BY_HUMAN_REVIEW').length;
  const reviewTier = runs.filter((run) => run.decision?.tier === 'HUMAN_REVIEW').length;

  return <section className="overview-page">
    <div className="overview-welcome"><div><span className="overview-eyebrow">SECURITY OPERATIONS / LIVE OVERVIEW</span><h1>Control, at a glance.</h1><p>Run decisions and risk signals from the latest records returned by CGTEL.</p></div><button className="overview-refresh" onClick={() => { setLoading(true); void refresh(); }} disabled={loading} type="button"><Icon name="refresh" size={15}/>{loading ? 'Refreshing' : 'Refresh'}</button></div>
    {error && <div className="overview-error" role="alert"><strong>Overview data unavailable</strong><span>{error}</span><button onClick={() => { setLoading(true); void refresh(); }} type="button">Retry</button></div>}
    {loading && runs.length === 0 && !error && <div className="overview-loading" role="status"><span className="loading-pulse"/>Loading recent run records…</div>}
    <div className="overview-metrics">
      <Metric label="Run records returned" value={error && !runs.length ? '—' : String(runs.length)} note="Newest first · API limit 1,000" icon="activity" accent="violet" />
      <Metric label="Denied by review" value={error && !runs.length ? '—' : String(denied)} note="Status: DENIED_BY_HUMAN_REVIEW" icon="shield" accent="coral" />
      <Metric label="Human review tier" value={error && !runs.length ? '—' : String(reviewTier)} note="Decision tier: HUMAN_REVIEW" icon="policy" accent="magenta" />
      <Metric label="Mean assessed risk" value={average === null ? '—' : average.toFixed(3)} note={assessed.length ? `Calculated from ${assessed.length} scored records` : 'No assessed scores in this set'} icon="benchmark" accent="lavender" />
    </div>

    <div className="overview-analytics">
      <article className="overview-panel overview-panel--gauge"><header className="overview-panel__header"><div><h2>Risk posture</h2><p>Mean score from assessed runs</p></div><span className="panel-kicker">0—1 SCORE</span></header><RiskGauge value={average} sampleSize={assessed.length}/></article>
      <article className="overview-panel overview-panel--distribution"><header className="overview-panel__header"><div><h2>Decision distribution</h2><p>Category counts among returned run records</p></div><span className="panel-kicker">{runs.length} RECORDS</span></header>{runs.length ? <DecisionDistribution runs={runs}/> : <div className="chart-empty">Decision distribution is unavailable until run records are returned.</div>}</article>
      <article className="overview-panel overview-panel--activity"><header className="overview-panel__header"><div><h2>Risk over time</h2><p>Assessed scores in timestamp order</p></div><span className="panel-kicker">LATEST 24</span></header><ActivityChart runs={runs}/></article>
      <article className="overview-quick"><div><span className="overview-eyebrow">QUICK ACTION</span><h2>Test an instruction</h2><p>Submit a request and inspect how CGTEL proposes, scores, and routes the tool call.</p></div><Link className="overview-primary-link" to="/desk">Open Desk <Icon name="arrow" size={16}/></Link><div className="overview-shortcuts"><Link to="/ledger">Audit ledger <Icon name="arrow" size={14}/></Link><Link to="/policy-lab">Policy lab <Icon name="arrow" size={14}/></Link><Link to="/benchmarks">Benchmarks <Icon name="arrow" size={14}/></Link></div></article>
    </div>

    <section className="overview-recent"><header className="overview-panel__header"><div><h2>Recent runs</h2><p>Latest API records with scores and decisions</p></div><Link className="text-link" to="/ledger">Open ledger <Icon name="arrow" size={14}/></Link></header>{error && !runs.length ? <div className="overview-empty">Recent runs could not be loaded.</div> : <RecentRuns runs={runs}/>}</section>
  </section>;
}
