import { useEffect, useMemo, useState } from 'react';
import { ApiError, getConfig, scoreWhatIf } from '../api/client';
import type { ConfigResponse, ScoreResponse, Tier, ToolDef, ToolParam } from '../api/types';
import './ResearchPages.css';

type Values = { w1: number; w2: number; w3: number; tau1: number; tau2: number; confidence: string; severity_prior: number; minimum_decision: Tier | 'NONE' };

function apiMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return 'Could not connect to the scoring service.';
  try {
    const parsed = JSON.parse(error.body) as { detail?: string };
    return parsed.detail ?? `Request failed (${error.status}).`;
  } catch { return `Request failed (${error.status}). ${error.body}`; }
}

function ToolArguments({ tool, value, onChange }: { tool: ToolDef; value: Record<string, string | number | boolean>; onChange: (name: string, next: string | number | boolean) => void }) {
  if (tool.params.length === 0) return <p className="form-note">This tool has no declared parameters.</p>;
  return <div className="argument-grid">{tool.params.map((param: ToolParam) => {
    const id = `arg-${param.name}`;
    if (param.type.toUpperCase() === 'BOOLEAN') return <label className="argument-toggle" key={param.name} htmlFor={id}>
      <input id={id} type="checkbox" checked={Boolean(value[param.name])} onChange={(event) => onChange(param.name, event.target.checked)} />
      <span>{param.name}</span><small>{param.required ? 'required · BOOLEAN' : 'optional · BOOLEAN'}</small>
    </label>;
    const isNumber = param.type.toUpperCase() === 'NUMBER';
    return <label className="research-field" key={param.name} htmlFor={id}>
      <span>{param.name}{param.required ? ' · required' : ' · optional'}</span>
      <input id={id} type={isNumber ? 'number' : 'text'} step={isNumber ? 'any' : undefined} required={param.required} value={String(value[param.name] ?? '')} onChange={(event) => onChange(param.name, isNumber ? event.target.value : event.target.value)} />
      <small>{param.type}</small>
    </label>;
  })}</div>;
}

const initialValues: Values = { w1: 0.25, w2: 0.25, w3: 0.5, tau1: 0.15, tau2: 0.35, confidence: '', severity_prior: 0.05, minimum_decision: 'NONE' };

export function PolicyLabPage() {
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loadingConfig, setLoadingConfig] = useState(true);
  const [toolName, setToolName] = useState('');
  const [args, setArgs] = useState<Record<string, string | number | boolean>>({});
  const [values, setValues] = useState<Values>(initialValues);
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getConfig().then((next) => {
      if (!active) return;
      setConfig(next);
      const initialTool = next.tools[0]?.name ?? '';
      const initialPolicy = next.tool_policies[initialTool];
      setToolName(initialTool);
      setValues({ ...next.weights, tau1: next.tau1, tau2: next.tau2, confidence: '', severity_prior: initialPolicy?.severity_prior ?? 0, minimum_decision: initialPolicy?.minimum_decision ?? 'NONE' });
    }).catch((err: unknown) => { if (active) setError(apiMessage(err)); })
      .finally(() => { if (active) setLoadingConfig(false); });
    return () => { active = false; };
  }, []);

  const selectedTool = useMemo(() => config?.tools.find((tool) => tool.name === toolName) ?? null, [config, toolName]);
  const setArg = (name: string, value: string | number | boolean) => setArgs((previous) => ({ ...previous, [name]: value }));

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTool) return;
    setScoring(true); setError(null); setResult(null);
    try {
      const typedArgs: Record<string, unknown> = {};
      for (const param of selectedTool.params) {
        const current = args[param.name];
        if (current === undefined || current === '') continue;
        typedArgs[param.name] = param.type.toUpperCase() === 'NUMBER' ? Number(current) : current;
      }
      const response = await scoreWhatIf({
        tool_name: toolName,
        args: typedArgs,
        confidence: values.confidence === '' ? null : Number(values.confidence),
        w1: values.w1, w2: values.w2, w3: values.w3,
        tau1: values.tau1, tau2: values.tau2,
        severity_prior: values.severity_prior,
        minimum_decision: values.minimum_decision,
      });
      setResult(response);
    } catch (err) { setError(apiMessage(err)); }
    finally { setScoring(false); }
  }

  const update = (key: keyof Values, value: number | string) => setValues((previous) => ({ ...previous, [key]: value }));
  const terms = result ? [
    { key: 'reversibility', label: 'Irreversibility', term: result.terms.reversibility, signal: result.signals.reversibility, weight: values.w1, note: 'Higher when the action is harder to undo.' },
    { key: 'confidence_gap', label: 'Agreement gap', term: result.terms.confidence_gap, signal: result.signals.confidence_gap, weight: values.w2, note: 'The scoring penalty from lower confidence.' },
    { key: 'failure_rate', label: 'F signal', term: result.terms.failure_rate, signal: result.signals.failure_rate, weight: values.w3, note: 'Effective F is the higher of observed failure rate and the configured severity prior.' },
  ] : [];

  return <section className="research-page policy-page">
    {loadingConfig && <div className="research-state"><span className="state-mark" />Loading registered tools and defaults…</div>}
    {error && !config && <div className="research-state research-state--error" role="alert"><strong>Policy Lab unavailable</strong><span>{error}</span></div>}
    {config && <div className="policy-layout">
      <form className="policy-form" onSubmit={submit}>
        <div className="policy-default-strip"><span>CONFIG DEFAULTS</span><code>w₁ {config.weights.w1.toFixed(3)} · w₂ {config.weights.w2.toFixed(3)} · w₃ {config.weights.w3.toFixed(3)} / τ₁ {config.tau1.toFixed(2)} · τ₂ {config.tau2.toFixed(2)}</code></div>
        <div className="form-section-heading"><span>01</span><h2>Proposed call</h2></div>
        <label className="research-field"><span>Registered tool</span><select value={toolName} onChange={(event) => { const nextTool = event.target.value; const policy = config.tool_policies[nextTool]; setToolName(nextTool); setArgs({}); setResult(null); setValues((previous) => ({ ...previous, severity_prior: policy?.severity_prior ?? 0, minimum_decision: policy?.minimum_decision ?? 'NONE' })); }}>
          {config.tools.map((tool) => <option key={tool.name} value={tool.name}>{tool.name}</option>)}
        </select><small>{selectedTool?.description}</small></label>
        {selectedTool && <ToolArguments tool={selectedTool} value={args} onChange={setArg} />}
        <div className="threshold-controls policy-tool-controls">
          <label className="research-field"><span>F · Severity prior</span><input type="number" min="0" max="1" step="0.01" value={values.severity_prior} onChange={(event) => update('severity_prior', Number(event.target.value))} /><small>Raises the tool’s F signal; the stored failure rate may raise it further.</small></label>
          <label className="research-field"><span>Minimum decision</span><select value={values.minimum_decision} onChange={(event) => update('minimum_decision', event.target.value)}><option value="NONE">No floor</option><option value="LOG_AND_MONITOR">LOG_AND_MONITOR</option><option value="HUMAN_REVIEW">HUMAN_REVIEW</option></select><small>The floor can raise a tier, never lower the score decision.</small></label>
        </div>
        <label className="research-field confidence-field"><span>Confidence override</span><input type="number" min="0" max="1" step="0.01" value={values.confidence} placeholder="Use extractor fallback" onChange={(event) => update('confidence', event.target.value)} /><small>0–1 when set; empty uses the documented extractor fallback.</small></label>

        <div className="form-section-heading form-section-heading--space"><span>02</span><h2>Scoring weights</h2></div>
        <div className="weight-controls">{([
          ['w1', 'Irreversibility', 'w₁'], ['w2', 'Confidence gap', 'w₂'], ['w3', 'F signal', 'w₃'],
        ] as const).map(([key, label, symbol]) => <label className="weight-control" key={key}>
          <span><b>{symbol}</b>{label}<output>{values[key].toFixed(3)}</output></span>
          <input aria-label={`${label} weight`} type="range" min="0" max="1" step="0.001" value={values[key]} onChange={(event) => update(key, Number(event.target.value))} />
        </label>)}</div>

        <div className="form-section-heading form-section-heading--space"><span>03</span><h2>Decision thresholds</h2></div>
        <div className="threshold-controls">
          <label className="research-field"><span>τ₁ · allow / monitor</span><input type="number" step="0.01" value={values.tau1} onChange={(event) => update('tau1', Number(event.target.value))} /></label>
          <label className="research-field"><span>τ₂ · monitor / review</span><input type="number" step="0.01" value={values.tau2} onChange={(event) => update('tau2', Number(event.target.value))} /></label>
        </div>
        {error && <div className="inline-error" role="alert">{error}</div>}
        <button className="primary-action" type="submit" disabled={scoring || !selectedTool || !toolName}>{scoring ? 'Calculating score…' : 'Calculate risk score'} <span aria-hidden="true">↗</span></button>
      </form>

      <section className="score-analysis" aria-live="polite">
        {!result && !scoring && <div className="analysis-empty"><div className="analysis-orbit" aria-hidden="true">R</div><span>AWAITING PARAMETERS</span><p>Set the call and policy inputs, then calculate to see the backend’s result.</p></div>}
        {scoring && <div className="research-state"><span className="state-mark" />Scoring with current policy inputs…</div>}
        {result && <>
          <div className="analysis-topline"><span>LIVE RESPONSE · /api/score</span><span>{result.clamped ? 'CLAMPED' : 'UNCLAMPED'}</span></div>
          <div className={`score-hero score-hero--${result.tier.toLowerCase().replaceAll('_', '-')}`}>
            <div><span>COMPOSITE RISK</span><strong>{result.score.toFixed(4)}</strong></div>
            <span className="decision-chip">{result.tier.replaceAll('_', ' ')}</span>
          </div>
          <p className="page-footnote">Score decision: {result.score_based_tier.replaceAll('_', ' ')} · {result.floor_applied ? `floor: ${result.floor} raised the final decision` : result.floor ? `floor: ${result.floor} did not raise the score decision` : 'no minimum decision floor applied'} · F prior {result.signals.severity_prior.toFixed(3)} · effective F {result.signals.failure_rate.toFixed(3)}</p>
          <div className="component-heading"><h2>Score composition</h2><span>weighted terms · sum = score unless clamped</span></div>
          <div className="term-list">{terms.map((term, index) => <article className={`term-row term-row--${index}`} key={term.key}>
            <div className="term-row__title"><span className="term-row__index">0{index + 1}</span><strong>{term.label}</strong><code>{term.term.toFixed(4)}</code></div>
            <div className="term-track"><span style={{ width: `${Math.max(0, Math.min(100, term.term * 100))}%` }} /></div>
            <div className="term-row__meta"><span>{term.note}</span><code>{term.weight.toFixed(3)} × {term.signal.toFixed(3)}</code></div>
          </article>)}</div>
          <div className="signal-strip"><span>CONFIDENCE <b>{result.signals.confidence.toFixed(3)}</b></span><span>F SIGNAL <b>{result.signals.failure_rate.toFixed(3)}</b></span><span>SEVERITY PRIOR <b>{result.signals.severity_prior.toFixed(3)}</b></span><span>SOURCE <b>{result.signals.confidence_source}</b></span></div>
          {result.clamped && <p className="page-footnote">The backend reports that the raw weighted sum was outside the 0–1 range and was clamped.</p>}
        </>}
      </section>
    </div>}
  </section>;
}
