import { useEffect, useState } from 'react';
import { ApiError, getConfig, runBenchmark } from '../api/client';
import type { BenchmarkRequest, BenchmarkResponse, ConfigResponse } from '../api/types';
import './ResearchPages.css';

function errorText(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not connect to the benchmark service.';
  try { return (JSON.parse(error.body) as { detail?: string }).detail ?? `Request failed (${error.status}).`; }
  catch { return `Request failed (${error.status}). ${error.body}`; }
}

function percent(value: number): string { return `${(value * 100).toFixed(1)}%`; }

export function BenchmarkPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [policy, setPolicy] = useState<BenchmarkRequest | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [data, setData] = useState<BenchmarkResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadConfig() {
    try {
      const next = await getConfig();
      setConfig(next);
      setPolicy({ ...next.weights, tau1: next.tau1, tau2: next.tau2 });
    } catch (err) { setError(errorText(err)); }
    finally { setLoadingConfig(false); }
  }

  useEffect(() => {
    let active = true;
    getConfig().then((next) => {
      if (!active) return;
      setConfig(next);
      setPolicy({ ...next.weights, tau1: next.tau1, tau2: next.tau2 });
    }).catch((err: unknown) => {
      if (active) setError(errorText(err));
    }).finally(() => {
      if (active) setLoadingConfig(false);
    });
    return () => { active = false; };
  }, []);

  async function execute() {
    setLoading(true); setError(null);
    try { setData(await runBenchmark(policy ?? {})); }
    catch (err) { setError(errorText(err)); }
    finally { setLoading(false); }
  }

  const summary = data?.summary;
  return <section className="research-page benchmark-page">
    <div className="benchmark-note"><span className="benchmark-note__mark">i</span><p>Results come from <code>POST /api/benchmark</code>. The API reports an isolated scenario run; it does not change run history or shared failure-rate statistics.</p></div>
    {config && policy && <section className="benchmark-controls" aria-label="Benchmark policy configuration">
      <div className="benchmark-controls__heading"><div><h2>Evaluation configuration</h2><p>Starts with values from the server configuration; the response records the values used.</p></div><span>WEIGHTS 0–1 · τ₁ &lt; τ₂</span></div>
      <div className="benchmark-weight-controls">{([
        ['w1', 'Irreversibility'], ['w2', 'Confidence gap'], ['w3', 'Failure history'],
      ] as const).map(([key, label]) => <label className="benchmark-weight" key={key}><span>{label}<output>{(policy[key] ?? 0).toFixed(3)}</output></span><input type="range" min="0" max="1" step="0.001" value={policy[key] ?? 0} onChange={(event) => setPolicy((previous) => ({ ...previous, [key]: Number(event.target.value) }))}/></label>)}</div>
      <div className="benchmark-control-footer">
        <div className="benchmark-threshold-controls">
          <label className="research-field"><span>τ₁ · allow / monitor</span><input type="number" step="0.01" value={policy.tau1 ?? 0} onChange={(event) => setPolicy((previous) => ({ ...previous, tau1: Number(event.target.value) }))}/></label>
          <label className="research-field"><span>τ₂ · monitor / review</span><input type="number" step="0.01" value={policy.tau2 ?? 0} onChange={(event) => setPolicy((previous) => ({ ...previous, tau2: Number(event.target.value) }))}/></label>
        </div>
        <button className="primary-action benchmark-run-button" type="button" onClick={() => void execute()} disabled={loading || loadingConfig || !config || (policy.tau1 ?? 0) >= (policy.tau2 ?? 0)}>{loading ? 'Running…' : data ? 'Run benchmark' : 'Evaluate scenarios'} <span aria-hidden="true">↗</span></button>
      </div>
      {(policy.tau1 ?? 0) >= (policy.tau2 ?? 0) && <p className="benchmark-validation" role="alert">τ₁ must be strictly less than τ₂.</p>}
    </section>}
    {loadingConfig && !config && <div className="research-state"><span className="state-mark"/>Loading default weights and thresholds…</div>}
    {!loadingConfig && !config && <div className="research-state research-state--error" role="alert"><strong>Benchmark configuration unavailable</strong><span>{error ?? 'The server configuration could not be loaded.'}</span><button className="quiet-button" type="button" onClick={() => { setLoadingConfig(true); setError(null); void loadConfig(); }}>Retry</button></div>}
    {error && <div className="research-state research-state--error" role="alert"><strong>Benchmark could not complete</strong><span>{error}</span><button className="quiet-button" type="button" onClick={() => void execute()}>Retry</button></div>}
    {loading && <div className="benchmark-loading" role="status"><span className="state-mark" /><div><strong>Evaluating scenarios</strong><span>The benchmark is running with the server’s current defaults.</span></div></div>}
    {!data && !loading && !error && <div className="research-state research-state--empty benchmark-empty"><strong>No benchmark run yet</strong><span>Run the documented 30-scenario suite to see its returned metrics and per-scenario routing results.</span></div>}

    {data && summary && !loading && <>
      <div className="benchmark-config"><span>POLICY USED</span><code>w₁ {data.config_used.w1.toFixed(3)}　w₂ {data.config_used.w2.toFixed(3)}　w₃ {data.config_used.w3.toFixed(3)}　/　τ₁ {data.config_used.tau1.toFixed(2)}　τ₂ {data.config_used.tau2.toFixed(2)}</code></div>
      <section className="benchmark-overview" aria-label="Benchmark summary">
        <div className="benchmark-total"><span>SCENARIOS EVALUATED</span><strong>{summary.total_scenarios}</strong><div className="risk-distribution"><i style={{ width: `${summary.total_scenarios ? summary.low_risk_count / summary.total_scenarios * 100 : 0}%` }} /><i style={{ width: `${summary.total_scenarios ? summary.medium_risk_count / summary.total_scenarios * 100 : 0}%` }} /><i style={{ width: `${summary.total_scenarios ? summary.high_risk_count / summary.total_scenarios * 100 : 0}%` }} /></div><div className="distribution-legend"><span>LOW {summary.low_risk_count}</span><span>MED {summary.medium_risk_count}</span><span>HIGH {summary.high_risk_count}</span></div></div>
        <div className="metric-card metric-card--risk"><span>Unsafe execution</span><strong>{percent(summary.unsafe_execution_rate)}</strong><small>High risk routed to AUTO_ALLOW</small></div>
        <div className="metric-card metric-card--caution"><span>False positive</span><strong>{percent(summary.false_positive_rate)}</strong><small>Low risk routed to HUMAN_REVIEW</small></div>
        <div className="metric-card metric-card--latency"><span>Average overhead</span><strong>{summary.avg_latency_overhead_ms.toFixed(2)}<i> ms</i></strong><small>CGTEL average less baseline</small></div>
      </section>
      <section className="latency-comparison">
        <div className="component-heading"><h2>Mean evaluation latency</h2><span>milliseconds · returned by benchmark</span></div>
        <div className="latency-row"><span>Baseline</span><div className="latency-track"><i style={{ width: `${Math.max(0, Math.min(100, summary.avg_baseline_latency_ms / Math.max(summary.avg_baseline_latency_ms, summary.avg_cgtel_latency_ms, 0.01) * 100))}%` }} /></div><code>{summary.avg_baseline_latency_ms.toFixed(3)} ms</code></div>
        <div className="latency-row"><span>CGTEL</span><div className="latency-track latency-track--cgtel"><i style={{ width: `${Math.max(0, Math.min(100, summary.avg_cgtel_latency_ms / Math.max(summary.avg_baseline_latency_ms, summary.avg_cgtel_latency_ms, 0.01) * 100))}%` }} /></div><code>{summary.avg_cgtel_latency_ms.toFixed(3)} ms</code></div>
      </section>
      <section className="scenario-section">
        <div className="component-heading"><h2>Scenario routing</h2><span>{data.results.length} returned records</span></div>
        {data.results.length === 0 ? <div className="research-state research-state--empty"><strong>No scenario records returned</strong></div> : <div className="scenario-table-wrap"><table className="scenario-table">
          <thead><tr><th>Scenario / Instruction</th><th>Risk</th><th>Assigned tier(s)</th><th>Unsafe</th><th>False positive</th><th>Baseline</th><th>CGTEL</th></tr></thead>
          <tbody>{data.results.map((item) => <tr key={item.scenario_id}>
            <td><code>{item.scenario_id}</code><span>{item.task_instruction}</span></td>
            <td><span className={`risk-label risk-label--${item.ground_truth.toLowerCase()}`}>{item.ground_truth}</span></td>
            <td>{item.assigned_tiers.map((tier, index) => <span className="scenario-tier" key={`${tier}-${index}`}>{tier.replaceAll('_', ' ')}</span>)}</td>
            <td className={item.is_unsafe_execution ? 'boolean-flag boolean-flag--yes' : 'boolean-flag'}>{item.is_unsafe_execution ? 'Yes' : '—'}</td>
            <td className={item.is_false_positive ? 'boolean-flag boolean-flag--yes' : 'boolean-flag'}>{item.is_false_positive ? 'Yes' : '—'}</td>
            <td className="numeric-cell">{item.baseline_latency_ms.toFixed(3)} ms</td><td className="numeric-cell">{item.cgtel_latency_ms.toFixed(3)} ms</td>
          </tr>)}</tbody>
        </table></div>}
      </section>
      <p className="page-footnote">The endpoint evaluates synthetic benchmark scenarios using an isolated failure-rate lookup. Latency and routing values above are the server response, not live production measurements.</p>
    </>}
  </section>;
}
