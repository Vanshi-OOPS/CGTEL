import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ApiError, approveChatTool, getRuns, sendChatMessage } from '../api/client';
import type { ChatToolEvent, RunRecord } from '../api/types';
import { Icon } from '../components/Icon';
import './Chat.css';

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  toolEvents: ChatToolEvent[];
};

function getSessionId(): string {
  const key = 'cgtel-chat-session-id';
  const existing = window.sessionStorage.getItem(key);
  if (existing) return existing;
  const created = window.crypto?.randomUUID?.() ?? `chat-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  window.sessionStorage.setItem(key, created);
  return created;
}

function describeError(error: unknown): string {
  if (!(error instanceof ApiError)) return 'The chat service could not be reached.';
  try {
    const detail = (JSON.parse(error.body) as { detail?: string }).detail;
    return detail ?? `The chat request failed (${error.status}).`;
  } catch {
    return `The chat request failed (${error.status}).`;
  }
}

function decisionClass(decision: string | null): string {
  if (decision === 'AUTO_ALLOW') return 'chat-tool--allow';
  if (decision === 'LOG_AND_MONITOR') return 'chat-tool--monitor';
  if (decision === 'HUMAN_REVIEW') return 'chat-tool--review';
  return 'chat-tool--unknown';
}

function ToolEvent({
  event,
  queued,
}: {
  event: ChatToolEvent;
  queued: boolean;
}) {
  return <article className={`chat-tool ${decisionClass(event.decision)} ${event.status === 'pending_approval' ? 'chat-tool--pending' : ''}`}>
    <div className="chat-tool__topline">
      <span className="chat-tool__name"><Icon name="shield" size={13} />{event.tool}</span>
      <span className="chat-tool__status">{event.status.replaceAll('_', ' ')}</span>
    </div>
    <div className="chat-tool__meta">
      <span className="chat-tool__decision">{event.decision?.replaceAll('_', ' ') ?? 'Decision unavailable'}</span>
      <code>{event.risk === null ? 'RISK —' : `RISK ${event.risk.toFixed(4)}`}</code>
    </div>
    {event.score_breakdown?.floor_applied && <p className="chat-tool__queued">floor: {event.score_breakdown.floor}</p>}
    {event.score_breakdown && <details className="chat-tool__args"><summary>Score breakdown{event.score_breakdown.degraded ? ' · degraded samples' : ''}</summary><pre>{JSON.stringify(event.score_breakdown, null, 2)}</pre></details>}
    <details className="chat-tool__args"><summary>Arguments</summary><pre>{JSON.stringify(event.args, null, 2)}</pre></details>
    {event.status === 'pending_approval' && event.run_id && queued && <p className="chat-tool__queued">Queued · a higher-risk action is awaiting review</p>}
    {event.status === 'pending_approval' && !event.run_id && <p className="chat-tool__warning">Approval ID was not returned by the chat service.</p>}
  </article>;
}

export function ChatPage() {
  const [sessionId] = useState(getSessionId);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null);
  const [dismissedReviewId, setDismissedReviewId] = useState<string | null>(null);
  const [restoringReviews, setRestoringReviews] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const pendingReviews = messages.flatMap((message) => message.toolEvents)
    .filter((event) => event.status === 'pending_approval' && event.decision === 'HUMAN_REVIEW' && event.run_id)
    .sort((a, b) => (b.risk ?? -1) - (a.risk ?? -1));
  const activeReview = pendingReviews.find((event) => event.run_id !== dismissedReviewId) ?? null;

  useEffect(() => {
    let cancelled = false;
    void getRuns(100).then((runs: RunRecord[]) => {
      if (cancelled) return;
      const pending = runs.filter((run) => run.llm_mode === 'direct_tool'
        && run.status === 'RUNNING'
        && run.decision?.tier === 'HUMAN_REVIEW'
        && run.tool_name && run.args);
      if (pending.length === 0) return;
      setMessages((previous) => {
        const knownIds = new Set(previous.flatMap((message) => message.toolEvents.map((event) => event.run_id)));
        const recovered = pending.filter((run) => !knownIds.has(run.run_id)).map((run) => ({
          id: `recovered-${run.run_id}`,
          role: 'assistant' as const,
          content: 'This action is awaiting human approval.',
          toolEvents: [{
            tool: run.tool_name!,
            args: run.args!,
            decision: run.decision?.tier ?? 'HUMAN_REVIEW',
            risk: run.decision?.score ?? null,
            status: 'pending_approval',
            run_id: run.run_id,
            score_breakdown: {
              V: run.decision?.signals?.reversibility ?? null,
              C: run.decision?.signals?.confidence ?? null,
              F: run.decision?.signals?.failure_rate ?? null,
              severity_prior: run.decision?.signals?.severity_prior ?? null,
              historical_failure_rate: run.decision?.signals?.historical_failure_rate ?? null,
              weights: run.decision?.signals?.weights ?? { w1: 0.25, w2: 0.25, w3: 0.5 },
              R: run.decision?.score ?? null,
              score_based_decision: run.decision?.signals?.score_based_decision ?? null,
              floor: run.decision?.signals?.floor ?? null,
              floor_applied: Boolean(run.decision?.signals?.floor_applied),
              decision: run.decision?.tier ?? 'HUMAN_REVIEW',
              degraded: Boolean(run.outcome_log?.degraded),
            },
          }],
        }));
        return [...previous, ...recovered];
      });
    }).catch(() => {
      // Chat remains usable if the run ledger is temporarily unavailable.
    }).finally(() => {
      if (!cancelled) setRestoringReviews(false);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending, busyRunId]);

  async function submitMessage(message: string, appendUser: boolean) {
    if (!message || sending || activeReview) return;
    setError(null);
    setSending(true);
    setDraft('');
    if (appendUser) {
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'user', content: message, toolEvents: [] }]);
    }
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 45_000);
    try {
      const response = await sendChatMessage({ session_id: sessionId, message }, controller.signal);
      setMessages((previous) => [...previous, { id: crypto.randomUUID(), role: 'assistant', content: response.reply, toolEvents: response.tool_events }]);
      if (response.error) {
        setLastFailedMessage(message);
        setError(response.error);
      } else {
        setLastFailedMessage(null);
      }
      setDraft('');
    } catch (requestError) {
      setLastFailedMessage(message);
      setError(controller.signal.aborted ? 'The chat request timed out after 45 seconds.' : describeError(requestError));
    } finally {
      window.clearTimeout(timeoutId);
      setSending(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const draftMessage = draft.trim();
    const message = draftMessage || lastFailedMessage;
    if (!message || sending || activeReview) return;
    await submitMessage(message, Boolean(draftMessage) && lastFailedMessage !== message);
  }

  async function retryLastMessage() {
    if (!lastFailedMessage || sending || activeReview) return;
    await submitMessage(lastFailedMessage, false);
  }

  function handleInputKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function resolveReview(event: ChatToolEvent, approved: boolean) {
    if (!event.run_id || busyRunId) return;
    setBusyRunId(event.run_id);
    setError(null);
    try {
      const response = await approveChatTool({ run_id: event.run_id, approved });
      if (response.error) setError(response.error);
      const resolvedEvent = response.tool_events[0];
      setMessages((previous) => [
        ...previous.map((message) => ({
          ...message,
          toolEvents: message.toolEvents.map((toolEvent) => toolEvent.run_id === event.run_id && resolvedEvent
            ? { ...toolEvent, status: resolvedEvent.status }
            : toolEvent),
        })),
        { id: crypto.randomUUID(), role: 'assistant', content: response.reply, toolEvents: [] },
      ]);
    } catch (requestError) {
      setError(describeError(requestError));
    } finally {
      setBusyRunId(null);
    }
  }

  return <section className="chat-page">
    <div className="chat-intro"><div><span className="chat-eyebrow">CGTEL / ASSISTANT SESSION</span><h2>Ask. Inspect. Approve.</h2><p>Gemini can propose sandbox actions. CGTEL scores each call before it runs.</p></div><span className="chat-session"><i /> SESSION <code>{sessionId.slice(0, 8)}</code></span></div>
    <section className="chat-console" aria-label="Chat conversation">
      <div className="chat-messages" ref={listRef} aria-live="polite">
        {messages.length === 0 && !sending && <div className="chat-empty"><span className="chat-empty__icon"><Icon name="activity" size={21} /></span><strong>Start a conversation</strong><p>Replies and tool decisions from this session will appear here.</p></div>}
        {messages.map((message) => <article className={`chat-message chat-message--${message.role}`} key={message.id}>
          <div className="chat-message__avatar">{message.role === 'assistant' ? <Icon name="shield" size={15} /> : 'YOU'}</div>
          <div className="chat-message__body">
            <div className="chat-message__label">{message.role === 'assistant' ? 'CGTEL ASSISTANT' : 'YOU'}</div>
            <p className="chat-message__content">{message.content}</p>
            {message.toolEvents.length > 0 && <div className="chat-tool-events" aria-label="Tool events">
              {message.toolEvents.map((toolEvent, index) => <div key={`${toolEvent.run_id ?? toolEvent.tool}-${index}`}>
                <ToolEvent event={toolEvent} queued={toolEvent.run_id !== activeReview?.run_id} />
                {toolEvent.status === 'pending_approval' && toolEvent.decision === 'HUMAN_REVIEW' && toolEvent.run_id === dismissedReviewId && <button type="button" className="chat-review-resume" onClick={() => setDismissedReviewId(null)}>Review pending</button>}
              </div>)}
            </div>}
          </div>
        </article>)}
        {sending && <div className="chat-typing" role="status"><span /><span /><span /> Gemini is responding</div>}
      </div>
      {error && <div className="chat-error" role="alert"><strong>Message not completed</strong><span>{error}</span>{lastFailedMessage && <button type="button" className="chat-error__retry" onClick={() => void retryLastMessage()} disabled={sending}>Retry</button>}<button type="button" className="chat-error__dismiss" onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
      <form className="chat-composer" onSubmit={sendMessage}>
        <label className="visually-hidden" htmlFor="chat-input">Message the CGTEL assistant</label>
        <textarea id="chat-input" rows={2} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleInputKey} placeholder="Ask about a task or request a sandbox action…" disabled={sending || restoringReviews || activeReview !== null} />
        <div className="chat-composer__footer"><span>{activeReview ? 'RESOLVE THE PENDING REVIEW TO CONTINUE' : 'ENTER TO SEND · SHIFT + ENTER FOR NEW LINE'}</span><button type="submit" disabled={sending || restoringReviews || activeReview !== null || (!draft.trim() && !lastFailedMessage)}>{sending ? 'Sending…' : !draft.trim() && lastFailedMessage ? 'Send again' : 'Send'} <Icon name="arrow" size={15} /></button></div>
      </form>
    </section>
    {activeReview && <div className="chat-review-overlay">
      <section className="chat-review-modal" role="dialog" aria-modal="true" aria-labelledby="chat-review-title">
        <button type="button" className="chat-review-close" aria-label="Dismiss review modal" onClick={() => setDismissedReviewId(activeReview.run_id ?? null)}>×</button>
        <span className="chat-eyebrow">CGTEL / HUMAN REVIEW</span>
        <h2 id="chat-review-title">Approve this action?</h2>
        <p className="chat-review-modal__tool"><Icon name="shield" size={15} />{activeReview.tool}</p>
        <div className="chat-review-modal__risk"><span>RISK SCORE</span><strong>{activeReview.risk === null ? 'Unavailable' : activeReview.risk.toFixed(4)}</strong></div>
        <details className="chat-tool__args" open><summary>Arguments</summary><pre>{JSON.stringify(activeReview.args, null, 2)}</pre></details>
        <p className="chat-review-modal__queue">{pendingReviews.length > 1 ? `${pendingReviews.length - 1} other action${pendingReviews.length === 2 ? '' : 's'} queued by risk score.` : 'This action will remain held until you decide.'}</p>
        <div className="chat-tool__actions">
          <button type="button" className="chat-approve" disabled={busyRunId !== null} onClick={() => void resolveReview(activeReview, true)}>{busyRunId === activeReview.run_id ? 'Resolving…' : 'Approve'}</button>
          <button type="button" className="chat-deny" disabled={busyRunId !== null} onClick={() => void resolveReview(activeReview, false)}>Deny</button>
        </div>
      </section>
    </div>}
    <p className="chat-footnote">Tool actions are restricted by CGTEL policy. Email and payment tools record mock actions only.</p>
  </section>;
}
