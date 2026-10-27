import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  ConfigResponse,
  HealthResponse,
  StatsResponse,
  RunStartedEvent,
  ScoredEvent,
  ReviewRequiredEvent,
  ReviewResolvedEvent,
  ReviewTimeoutEvent,
  RunFinishedEvent,
  RunErrorEvent,
  StampVariant,
  RunStatus,
  Tier,
  ContributingSignals,
} from '../api/types';
import {
  getHealth,
  getConfig,
  getStats,
  startRun,
  submitReview,
  subscribeToRun,
  ApiError,
} from '../api/client';
import { Stamp } from '../components/Stamp';
import { Icon } from '../components/Icon';
import { RiskRuler } from '../components/RiskRuler';
import { ContributionBar } from '../components/ContributionBar';
import { TierTag } from '../components/TierTag';
import { JsonBlock } from '../components/JsonBlock';
import { SlipModal } from '../components/SlipModal';
import { Textarea, Button, Toggle } from '../components/Primitives';
import './Desk.css';

const SAMPLE_CASES = [
  {
    instruction:
      'Read the application configuration file config/app_settings.json.',
    note: null,
  },
  {
    instruction:
      'Delete the temporary session cache file at /tmp/session_cache.tmp.',
    note: null,
  },
  {
    instruction:
      'Process a subscription payment of 149.99 USD for account acc_user_4042.',
    note: null,
  },
  {
    instruction:
      'Reject the proposed subscription payment of 149.99 USD for account acc_user_4042.',
    note: 'Trap: the offline rule-based proposer still proposes a payment here because it only matches keywords.',
  },
];

// Map backend status to stamp variant
function statusToStamp(status: RunStatus): StampVariant {
  switch (status) {
    case 'EXECUTED':
      return 'AUTHORISED';
    case 'DENIED_BY_HUMAN_REVIEW':
      return 'REFUSED';
    case 'EXECUTION_ERROR':
      return 'REFUSED';
    case 'REJECTED_UNSUPPORTED_TOOL':
    case 'REJECTED_INVALID_ARGS':
      return 'REJECTED MALFORMED';
    case 'LLM_ERROR':
    case 'NO_TOOL_CALL':
      return 'NOT ASSESSED';
    default:
      return 'NOT ASSESSED';
  }
}

// Policy explanation per tier
function policyExplanation(tier: Tier, score: number, tau1: number, tau2: number): string {
  switch (tier) {
    case 'AUTO_ALLOW':
      return `R = ${score.toFixed(4)} < τ₁ ${tau1.toFixed(2)} — auto-allowed, no human oversight required.`;
    case 'LOG_AND_MONITOR':
      return `τ₁ ${tau1.toFixed(2)} ≤ R = ${score.toFixed(4)} < τ₂ ${tau2.toFixed(2)} — logged and monitored, proceeding with caution.`;
    case 'HUMAN_REVIEW':
      return `R = ${score.toFixed(4)} ≥ τ₂ ${tau2.toFixed(2)} — held for human review before execution.`;
  }
}

// Stages
interface CaseState {
  runId: string | null;
  task: string | null;
  llmMode: string | null;
  // Stage 1: PROPOSED
  toolName: string | null;
  args: Record<string, unknown> | null;
  // Stage 2: SCORED
  score: number | null;
  tier: Tier | null;
  signals: ContributingSignals | null;
  assessed: boolean;
  // Stage 3: ROUTED (same as scored tier but we show it separately)
  routed: boolean;
  // Stage 4: REVIEW
  reviewRequired: boolean;
  reviewTimeoutSeconds: number;
  reviewTimedOut: boolean;
  reviewResolved: boolean;
  reviewApproved: boolean | null;
  // Stage 5: OUTCOME
  status: RunStatus | null;
  result: string | null;
  error: string | null;
  outcomeLog: Record<string, unknown> | null;
  finished: boolean;
  // Error
  runError: string | null;
}

const INITIAL_CASE: CaseState = {
  runId: null,
  task: null,
  llmMode: null,
  toolName: null,
  args: null,
  score: null,
  tier: null,
  signals: null,
  assessed: true,
  routed: false,
  reviewRequired: false,
  reviewTimeoutSeconds: 120,
  reviewTimedOut: false,
  reviewResolved: false,
  reviewApproved: null,
  status: null,
  result: null,
  error: null,
  outcomeLog: null,
  finished: false,
  runError: null,
};

export function DeskPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [backendDown, setBackendDown] = useState(false);

  const [instruction, setInstruction] = useState('');
  const [isLive, setIsLive] = useState(false);
  const [running, setRunning] = useState(false);
  const [busyError, setBusyError] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [caseState, setCaseState] = useState<CaseState>(INITIAL_CASE);
  const esRef = useRef<EventSource | null>(null);

  function parseEvent<T>(data: string): T | null {
    try {
      const value: unknown = JSON.parse(data);
      return value !== null && typeof value === 'object' ? value as T : null;
    } catch {
      return null;
    }
  }

  function asObject(value: unknown): Record<string, unknown> | null {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : null;
  }

  // Fetch health & config on mount
  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [h, c, s] = await Promise.all([
          getHealth(),
          getConfig(),
          getStats(),
        ]);
        if (cancelled) return;
        setHealth(h);
        setConfig(c);
        setStats(s);
        setBackendDown(false);
      } catch {
        if (!cancelled) setBackendDown(true);
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, []);

  // Refresh stats after run finishes
  const refreshStats = useCallback(async () => {
    try {
      const s = await getStats();
      setStats(s);
    } catch {
      // ignore
    }
  }, []);

  // File a request
  const handleSubmit = useCallback(async () => {
    if (!instruction.trim() || running) return;
    setBusyError(false);
    setRunning(true);
    setCaseState(INITIAL_CASE);

    // Close previous EventSource
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }

    try {
      const response = await startRun({
        task: instruction.trim(),
        mode: isLive ? 'live' : 'offline',
      });

      const runId = typeof response?.run_id === 'string' ? response.run_id : '';
      if (!runId) throw new Error('The server did not return a run ID.');
      setCaseState((prev) => ({ ...prev, runId, task: instruction.trim() }));

      // Subscribe to SSE
      const es = subscribeToRun(runId, {
        onRunStarted: (data) => {
          const evt = parseEvent<RunStartedEvent>(data);
          if (!evt) return;
          setCaseState((prev) => ({
            ...prev,
            llmMode: typeof evt.llm_mode === 'string' ? evt.llm_mode : null,
          }));
        },
        onScored: (data) => {
          const evt = parseEvent<ScoredEvent>(data);
          if (!evt) return;
          const args = asObject(evt.args);
          const signals = asObject(evt.contributing_signals);
          setCaseState((prev) => ({
            ...prev,
            toolName: evt.tool_name,
            args,
            score: typeof evt.score === 'number' && Number.isFinite(evt.score) ? evt.score : null,
            tier: evt.tier ?? null,
            signals: signals as ContributingSignals | null,
            assessed: true,
            routed: true,
          }));
        },
        onReviewRequired: (data) => {
          const evt = parseEvent<ReviewRequiredEvent>(data);
          if (!evt) return;
          const args = asObject(evt.args);
          const signals = asObject(evt.signals) as ContributingSignals | null;
          setCaseState((prev) => ({
            ...prev,
            toolName: prev.toolName ?? (typeof evt.tool_name === 'string' ? evt.tool_name : null),
            args: prev.args ?? args,
            score: prev.score ?? (typeof evt.score === 'number' && Number.isFinite(evt.score) ? evt.score : null),
            signals: prev.signals ?? signals,
            reviewRequired: true,
            reviewTimeoutSeconds: typeof evt.timeout_seconds === 'number' ? evt.timeout_seconds : 120,
          }));
        },
        onReviewResolved: (data) => {
          const evt = parseEvent<ReviewResolvedEvent>(data);
          if (!evt) return;
          setCaseState((prev) => ({
            ...prev,
            reviewRequired: false,
            reviewResolved: true,
            reviewApproved: typeof evt.approved === 'boolean' ? evt.approved : null,
          }));
        },
        onReviewTimeout: (data) => {
          const evt = parseEvent<ReviewTimeoutEvent>(data);
          if (!evt) return;
          setCaseState((prev) => ({
            ...prev,
            reviewTimedOut: true,
            reviewTimeoutSeconds: typeof evt.timeout_seconds === 'number' ? evt.timeout_seconds : 120,
          }));
        },
        onRunFinished: (data) => {
          const evt = parseEvent<RunFinishedEvent>(data);
          if (!evt) return;
          const decision = asObject(evt.decision);
          const args = asObject(evt.args);
          const outcomeLog = asObject(evt.outcome_log);
          const ignoredCalls = Array.isArray(evt.ignored_calls) ? evt.ignored_calls : [];
          void ignoredCalls;
          const assessed = decision?.assessed === true;
          const decisionSignals = asObject(decision?.signals) as ContributingSignals | null;
          setCaseState((prev) => ({
            ...prev,
            toolName: prev.toolName ?? (typeof evt.tool_name === 'string' ? evt.tool_name : null),
            args: prev.args ?? args,
            score: assessed && typeof decision?.score === 'number' ? decision.score : prev.score,
            tier: assessed && typeof decision?.tier === 'string' ? decision.tier as Tier : prev.tier,
            signals: assessed ? decisionSignals ?? prev.signals : prev.signals,
            assessed: decision ? assessed : prev.assessed,
            routed: assessed ? true : prev.routed,
            status: typeof evt.status === 'string' ? evt.status as RunStatus : null,
            result: evt.result === null || typeof evt.result === 'string' ? evt.result : JSON.stringify(evt.result, null, 2),
            error: typeof evt.error === 'string' ? evt.error : null,
            outcomeLog,
            finished: true,
            reviewRequired: false,
          }));
          setRunning(false);
          es.close();
          refreshStats();
        },
        onRunError: (data) => {
          const evt = parseEvent<RunErrorEvent>(data);
          if (!evt) return;
          setCaseState((prev) => ({
            ...prev,
            runError: typeof evt.error === 'string' ? evt.error : 'The run failed unexpectedly.',
            finished: true,
          }));
          setRunning(false);
          es.close();
        },
        onError: () => {
          // EventSource error - could be backend restart
          setRunning(false);
          es.close();
        },
      });

      esRef.current = es;
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setBusyError(true);
      }
      setRunning(false);
    }
  }, [instruction, isLive, running, refreshStats]);

  // Review actions
  const handleReview = useCallback(
    async (approve: boolean) => {
      if (!caseState.runId) return;
      setReviewError(null);
      try {
        const response = await submitReview(caseState.runId, { approve });
        if (!response || typeof response !== 'object' || typeof response.approved !== 'boolean') {
          throw new Error('The server returned an invalid review response.');
        }
        // The SSE will update the state
      } catch (error) {
        setReviewError(error instanceof Error ? error.message : 'Could not submit the review decision.');
      }
    },
    [caseState.runId],
  );

  // Cleanup
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  if (backendDown) {
    return (
      <div className="error-banner">
        Checkpoint unreachable — start the server with{' '}
        <code>uvicorn server.app:app --port 8000</code>
      </div>
    );
  }

  const tau1 = config?.tau1 ?? 0.15;
  const tau2 = config?.tau2 ?? 0.35;
  const weights = config?.weights ?? { w1: 0.333, w2: 0.333, w3: 0.333 };

  return (
    <div className="desk-workspace">
      <section className="desk-workspace__left" aria-label="Tool call workspace">
        <section className="desk-panel desk-intake">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">01 / REQUEST</span><h2>Instruction</h2></div><span className="workspace-tag">AGENT INPUT</span></header>
          <div className="desk-panel__body">
            <Textarea label="Describe the task for the agent" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="e.g. Read the application configuration file…" disabled={running} />
            <div className="desk-intake__controls">
              <Toggle label={isLive ? 'Live Gemini' : 'Offline fallback'} checked={isLive} onChange={setIsLive} disabled={!health?.live_available} disabledNote={!health?.live_available ? 'No GEMINI_API_KEY set on server' : undefined} />
              <Button onClick={handleSubmit} disabled={running || !instruction.trim()} fullWidth>{running ? 'Processing request…' : 'File request'} <span aria-hidden="true">↗</span></Button>
            </div>
            {busyError && <div className="busy-banner" role="alert">Another run is currently active. Wait for it to finish.</div>}
            {reviewError && <div className="busy-banner" role="alert">{reviewError}</div>}
            <details className="desk-samples"><summary><span>Sample instructions</span><span>4 cases</span></summary>
              <div className="desk-samples__list">{SAMPLE_CASES.map((sample, index) => <div className="desk-sample-row" key={index}>
                <button className="intake__sample" onClick={() => setInstruction(sample.instruction)} disabled={running} type="button"><span className="desk-sample-row__number">0{index + 1}</span><span>{sample.instruction}</span></button>
                {sample.note && <p className="intake__sample-note">{sample.note}</p>}
              </div>)}</div>
            </details>
          </div>
        </section>

        <section className="desk-panel desk-proposal">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">02 / TOOL PROPOSAL</span><h2>Proposed call</h2></div>{caseState.llmMode && <span className="workspace-tag">{caseState.llmMode.replaceAll('_', ' ')}</span>}</header>
          {!caseState.runId && !running ? <div className="desk-workspace__empty"><span className="workspace-empty-mark"><Icon name="desk" size={20}/></span><strong>Ready for a request</strong><p>The selected task and the agent’s proposed tool call will appear here.</p></div> :
            <div className="desk-panel__body">
              {caseState.task && <div className="desk-task-line"><span>REQUEST</span><p>{caseState.task}</p></div>}
              {caseState.runId && <div className="desk-run-id"><span>RUN ID</span><code>{caseState.runId}</code></div>}
              {caseState.toolName ? <div className="tool-call-card"><div className="tool-call-card__heading"><Icon name="shield" size={15}/><code>{caseState.toolName}</code><span>SIMULATED TOOL</span></div><pre>{JSON.stringify(caseState.args ?? {}, null, 2)}</pre></div> : running ? <div className="proposal-skeleton"><div/><div/><div/></div> : <div className="desk-workspace__empty"><strong>No tool call proposed</strong><p>This run did not include a tool proposal.</p></div>}
            </div>}
        </section>

        {(caseState.finished || caseState.runError) && <section className="desk-panel desk-outcome">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">03 / EXECUTION</span><h2>Run outcome</h2></div>{caseState.status && <span className="workspace-tag">{caseState.status.replaceAll('_', ' ')}</span>}</header>
          <div className="desk-panel__body">
            {caseState.status && <div className="desk-outcome__stamp"><Stamp variant={statusToStamp(caseState.status)} size="md" /></div>}
            {caseState.result && <div className="desk-result"><span>RESULT</span><pre>{caseState.result}</pre></div>}
            {caseState.error && <div className="casefile__error" role="alert">{caseState.error}</div>}
            {caseState.runError && <div className="casefile__error" role="alert">{caseState.runError}</div>}
            {caseState.outcomeLog && <JsonBlock label="Outcome log" data={caseState.outcomeLog} />}
          </div>
        </section>}
      </section>

      <aside className="desk-workspace__right" aria-label="Risk analysis and session">
        <section className="desk-panel desk-risk">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">ANALYSIS / 01</span><h2>Risk assessment</h2></div>{caseState.score !== null && <span className="risk-current-score">{caseState.score.toFixed(4)}</span>}</header>
          <div className="desk-panel__body">
            {caseState.score !== null && caseState.assessed ? <>
              <RiskRuler score={caseState.score} tau1={tau1} tau2={tau2} assessed={caseState.assessed}/>
              {caseState.signals && <><ContributionBar score={caseState.score} signals={caseState.signals} weights={weights}/><div className="casefile__signal-row">{caseState.signals.confidence_source && <span className="casefile__signal">CONFIDENCE SOURCE <strong>{caseState.signals.confidence_source}</strong></span>}</div></>}
            </> : caseState.finished && !caseState.assessed ? <><RiskRuler score={null} tau1={tau1} tau2={tau2} assessed={false}/><p className="analysis-note">This run was rejected or returned without an assessed decision.</p></> : running && caseState.toolName ? <div className="proposal-skeleton"><div/><div/></div> : <div className="analysis-idle"><Icon name="activity" size={19}/><span>Risk appears after a tool call is scored.</span></div>}
          </div>
        </section>

        <section className="desk-panel desk-decision">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">ANALYSIS / 02</span><h2>Policy decision</h2></div></header>
          <div className="desk-panel__body">
            {caseState.routed && caseState.tier && caseState.score !== null ? <><TierTag tier={caseState.tier}/><p className="casefile__policy-line">{policyExplanation(caseState.signals?.score_based_decision && ['AUTO_ALLOW', 'LOG_AND_MONITOR', 'HUMAN_REVIEW'].includes(caseState.signals.score_based_decision) ? caseState.signals.score_based_decision as Tier : caseState.tier, caseState.score, tau1, tau2)}</p>{caseState.signals?.floor_applied && <p className="casefile__policy-line">Decision raised by floor: {caseState.signals.floor}</p>}</> : caseState.finished ? <div className="analysis-idle"><span>No assessed policy tier for this run.</span></div> : <div className="analysis-idle"><span>Decision state will appear when scoring completes.</span></div>}
            {caseState.reviewRequired && !caseState.reviewResolved && <div className="review-pending"><span className="review-pending__dot"/><div><strong>Human review pending</strong><small>Choose approve or deny in the review dialog. Expires in {Math.ceil(caseState.reviewTimeoutSeconds)} seconds.</small></div></div>}
            {caseState.reviewResolved && <div className={'review-resolution ' + (caseState.reviewApproved ? 'review-resolution--approved' : 'review-resolution--denied')}><strong>{caseState.reviewApproved ? 'Approved by reviewer' : caseState.reviewTimedOut ? 'Timed out · denied by default' : 'Denied by reviewer'}</strong></div>}
            {caseState.reviewTimedOut && !caseState.reviewResolved && <div className="review-resolution review-resolution--denied"><strong>Timed out · denied by default</strong></div>}
          </div>
        </section>

        <section className="desk-panel desk-session">
          <header className="desk-panel__header"><div><span className="desk-panel__eyebrow">SESSION TELEMETRY</span><h2>Execution totals</h2></div></header>
          <div className="desk-panel__body">
            {stats ? <>
              <div className="session__tally">
                <div className="session__tally-item"><div className="session__tally-count">{stats.session_totals.executed}</div><div className="session__tally-label">Executed</div></div>
                <div className="session__tally-item"><div className="session__tally-count">{stats.session_totals.denied}</div><div className="session__tally-label">Denied</div></div>
                <div className="session__tally-item"><div className="session__tally-count">{stats.session_totals.rejected}</div><div className="session__tally-label">Rejected</div></div>
                <div className="session__tally-item"><div className="session__tally-count">{stats.session_totals.errors}</div><div className="session__tally-label">Errors</div></div>
              </div>
              {stats.tools.length > 0 ? <><table className="session__tool-table"><thead><tr><th>Tool</th><th>Calls</th><th>Fail %</th></tr></thead><tbody>{stats.tools.map((tool) => <tr key={tool.tool_name}><td>{tool.tool_name}</td><td>{tool.total_calls}</td><td>{(tool.failure_rate * 100).toFixed(1)}%</td></tr>)}</tbody></table><p className="session__note">Failure rate updates only from calls that executed.</p></> : <p className="session__note">No per-tool execution history is available yet.</p>}
            </> : <div className="proposal-skeleton"><div/><div/></div>}
          </div>
        </section>
      </aside>

      {caseState.reviewRequired && !caseState.reviewResolved && caseState.signals && caseState.score !== null && <SlipModal toolName={caseState.toolName ?? 'unknown'} args={caseState.args ?? {}} score={caseState.score} signals={caseState.signals} weights={weights} timeoutSeconds={caseState.reviewTimeoutSeconds} timedOut={caseState.reviewTimedOut} onApprove={() => handleReview(true)} onDeny={() => handleReview(false)}/>}
    </div>
  );
}

