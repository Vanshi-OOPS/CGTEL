import { useCallback, useEffect, useMemo, useState } from 'react';
import { getRuns, ApiError } from '../api/client';
import type { RunRecord } from '../api/types';
import './ResearchPages.css';

function prettyTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function scoreText(run: RunRecord): string {
  const score = run.decision?.score;
  return run.decision?.assessed && score !== null && score !== undefined
    ? score.toFixed(4)
    : '—';
}

export function LedgerPage() {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('ALL');

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await getRuns(1000));
    } catch (err) {
      setError(err instanceof ApiError ? `Request failed (${err.status}). ${err.message}` : 'Could not connect to the run history service.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    async function loadInitialRuns() {
      try {
        const records = await getRuns(1000);
        if (active) setRuns(records);
      } catch (err) {
        if (active) setError(err instanceof ApiError ? `Request failed (${err.status}). ${err.message}` : 'Could not connect to the run history service.');
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadInitialRuns();
    return () => { active = false; };
  }, []);

  const statuses = useMemo(() => [...new Set(runs.map((run) => run.status))].sort(), [runs]);
  const filteredRuns = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return runs.filter((run) => {
      const matchesStatus = status === 'ALL' || run.status === status;
      const haystack = [run.run_id, run.task, run.tool_name ?? '', run.status].join(' ').toLowerCase();
      return matchesStatus && (!needle || haystack.includes(needle));
    });
  }, [query, runs, status]);

  return (
    <section className="research-page">
      <div className="ledger-toolbar">
        <label className="research-field ledger-search">
          <span>Find a run</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Task, tool, run ID…" />
        </label>
        <label className="research-field">
          <span>Outcome</span>
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="ALL">All recorded states</option>
            {statuses.map((item) => <option key={item} value={item}>{item.replaceAll('_', ' ')}</option>)}
          </select>
        </label>
        <div className="ledger-count"><strong>{filteredRuns.length}</strong><span>of {runs.length} records</span></div>
        <button className="quiet-button" type="button" onClick={() => { setLoading(true); setError(null); void loadRuns(); }} disabled={loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <div className="research-state research-state--error" role="alert"><strong>Ledger unavailable</strong><span>{error}</span><button className="quiet-button" onClick={() => { setLoading(true); setError(null); void loadRuns(); }}>Try again</button></div>}
      {loading && !runs.length && <div className="research-state"><span className="state-mark" />Fetching recorded runs…</div>}
      {!loading && !error && runs.length === 0 && <div className="research-state research-state--empty"><strong>No runs recorded</strong><span>Completed and in-progress runs will appear here after requests are filed from the Desk.</span></div>}
      {!loading && !error && runs.length > 0 && filteredRuns.length === 0 && <div className="research-state research-state--empty"><strong>No matching records</strong><span>Try a different search or outcome filter.</span></div>}

      {filteredRuns.length > 0 && (
        <div className="ledger-table-wrap">
          <table className="ledger-table">
            <thead><tr><th>Run / Created</th><th>Task / Tool</th><th>Risk</th><th>Decision</th><th>Outcome</th><th><span className="sr-only">Details</span></th></tr></thead>
            <tbody>
              {filteredRuns.map((run) => (
                <tr key={run.run_id}>
                  <td className="ledger-id"><code>{run.run_id}</code><time dateTime={run.created_at}>{prettyTime(run.created_at)}</time></td>
                  <td className="ledger-task"><span>{run.task}</span><code>{run.tool_name ?? 'No tool proposed'}</code></td>
                  <td className="ledger-score">{scoreText(run)}</td>
                  <td>{run.decision?.tier ? <span className={`decision-chip decision-chip--${run.decision.tier.toLowerCase().replaceAll('_', '-')}`}>{run.decision.tier.replaceAll('_', ' ')}</span> : <span className="muted-dash">Not assessed</span>}</td>
                  <td><span className={`status-chip status-chip--${run.status.toLowerCase().replaceAll('_', '-')}`}>{run.status.replaceAll('_', ' ')}</span></td>
                  <td className="ledger-detail-cell"><details className="ledger-detail"><summary>Inspect</summary><div className="ledger-detail__body">
                    <div className="detail-pair"><span>Mode</span><code>{run.mode} · {run.llm_mode}</code></div>
                    <div className="detail-pair"><span>Arguments</span><pre>{JSON.stringify(run.args ?? {}, null, 2)}</pre></div>
                    {run.decision?.signals && <div className="detail-pair"><span>Signals</span><pre>{JSON.stringify(run.decision.signals, null, 2)}</pre></div>}
                    {run.decision?.signals?.floor_applied === true && <div className="detail-pair"><span>Decision floor</span><code>floor: {String(run.decision.signals.floor ?? 'unknown')}</code></div>}
                    {run.error && <div className="detail-pair"><span>Error</span><pre>{run.error}</pre></div>}
                    {run.result !== null && run.result !== undefined && <div className="detail-pair"><span>Result</span><pre>{typeof run.result === 'string' ? run.result : JSON.stringify(run.result, null, 2)}</pre></div>}
                    {run.outcome_log && <div className="detail-pair"><span>Outcome log</span><pre>{JSON.stringify(run.outcome_log, null, 2)}</pre></div>}
                    {!!run.ignored_calls?.length && <div className="detail-pair"><span>Ignored calls</span><pre>{JSON.stringify(run.ignored_calls, null, 2)}</pre></div>}
                  </div></details></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="page-footnote">The API returns up to 1,000 runs, newest first. Scores are omitted for runs that were not assessed.</p>
    </section>
  );
}
