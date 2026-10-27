import { useEffect, useRef, useState, useCallback } from 'react';
import type { ContributingSignals, Weights } from '../api/types';
import { Button } from './Primitives';
import { ContributionBar } from './ContributionBar';
import './SlipModal.css';

interface SlipModalProps {
  toolName: string;
  args: Record<string, unknown>;
  score: number;
  signals: ContributingSignals;
  weights: Weights;
  timeoutSeconds: number;
  timedOut: boolean;
  onApprove: () => void;
  onDeny: () => void;
}

export function SlipModal({
  toolName,
  args,
  score,
  signals,
  weights,
  timeoutSeconds,
  timedOut,
  onApprove,
  onDeny,
}: SlipModalProps) {
  const [countdown, setCountdown] = useState(Math.ceil(timeoutSeconds));
  const modalRef = useRef<HTMLDivElement>(null);
  const approveRef = useRef<HTMLButtonElement>(null);

  // Focus trap
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;

    const focusable = modal.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    // Focus the approve button initially
    approveRef.current?.focus();

    const trapFocus = (e: KeyboardEvent) => {
      if (e.key === 'Tab') {
        if (e.shiftKey) {
          if (document.activeElement === first) {
            e.preventDefault();
            last?.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first?.focus();
          }
        }
      }
    };

    modal.addEventListener('keydown', trapFocus);
    return () => modal.removeEventListener('keydown', trapFocus);
  }, []);

  // Keyboard shortcuts
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (timedOut) return;
      if (e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        onApprove();
      } else if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        onDeny();
      } else if (e.key === 'Escape') {
        // Esc does NOT deny — just focus buttons
        e.preventDefault();
        approveRef.current?.focus();
      }
    },
    [onApprove, onDeny, timedOut],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  // Countdown timer
  useEffect(() => {
    if (timedOut) return;
    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [timedOut]);

  // Restore focus on unmount
  useEffect(() => {
    const prev = document.activeElement as HTMLElement;
    return () => {
      prev?.focus?.();
    };
  }, []);

  return (
    <div className="slip-overlay" role="dialog" aria-modal="true" aria-label="Human review required">
      <div className="slip-modal" ref={modalRef}>
        <div className="slip-modal__header">
          <span className="slip-modal__title">
            {timedOut ? 'Review Timed Out' : 'Human Review Required'}
          </span>
          <span className="slip-modal__countdown">
            {timedOut ? '0s' : `${countdown}s`}
          </span>
        </div>

        {timedOut ? (
          <div className="slip-modal__timeout-notice">
            Timed out — denied by default
          </div>
        ) : (
          <>
            <div className="slip-modal__body">
              <div className="slip-modal__row">
                <span className="slip-modal__row-label">Tool</span>
                <span className="slip-modal__row-value">{toolName}</span>
              </div>
              <div className="slip-modal__row">
                <span className="slip-modal__row-label">Args</span>
                <pre className="slip-modal__row-value" style={{ margin: 0 }}>
                  {JSON.stringify(args, null, 2)}
                </pre>
              </div>
              <div className="slip-modal__row">
                <span className="slip-modal__row-label">Risk</span>
                <span className="slip-modal__score-display">
                  {score.toFixed(4)}
                </span>
              </div>
              <div style={{ marginTop: 'var(--sp-3)' }}>
                <ContributionBar
                  score={score}
                  signals={signals}
                  weights={weights}
                />
              </div>
            </div>

            <div className="slip-modal__actions">
              <Button ref={approveRef} onClick={onApprove}>
                Approve<span className="slip-modal__kbd">[Y]</span>
              </Button>
              <Button variant="vermilion" onClick={onDeny}>
                Deny<span className="slip-modal__kbd">[N]</span>
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
