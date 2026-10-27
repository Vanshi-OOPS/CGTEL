import type { ButtonHTMLAttributes, Ref, TextareaHTMLAttributes } from 'react';
import './Primitives.css';

/* ─── Button ─── */
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'outline' | 'vermilion' | 'vermilion-fill';
  fullWidth?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = 'primary',
  fullWidth = false,
  className = '',
  children,
  ref,
  ...rest
}: ButtonProps) {
  const cls = [
    'btn',
    variant === 'outline' && 'btn--outline',
    variant === 'vermilion' && 'btn--vermilion',
    variant === 'vermilion-fill' && 'btn--vermilion-fill',
    fullWidth && 'btn--full',
    className,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <button ref={ref} className={cls} {...rest}>
      {children}
    </button>
  );
}

/* ─── Field ─── */
interface FieldProps {
  label: string;
  children: React.ReactNode;
}

export function Field({ label, children }: FieldProps) {
  return (
    <div className="field">
      <label className="field__label">{label}</label>
      {children}
    </div>
  );
}

/* ─── Textarea ─── */
interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string;
}

export function Textarea({ label, ...rest }: TextareaProps) {
  return (
    <Field label={label}>
      <textarea className="field__textarea" {...rest} />
    </Field>
  );
}

/* ─── Toggle ─── */
interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  disabledNote?: string;
}

export function Toggle({
  label,
  checked,
  onChange,
  disabled = false,
  disabledNote,
}: ToggleProps) {
  return (
    <div className={`toggle ${disabled ? 'toggle--disabled' : ''}`}>
      <div
        className={`toggle__track ${checked ? 'toggle__track--active' : ''}`}
        role="switch"
        aria-checked={checked}
        aria-label={label}
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && onChange(!checked)}
        onKeyDown={(e) => {
          if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            onChange(!checked);
          }
        }}
      >
        <div className="toggle__thumb" />
      </div>
      <div>
        <span className="toggle__label">{label}</span>
        {disabled && disabledNote && (
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              color: 'var(--ink-soft)',
              marginTop: '2px',
            }}
          >
            {disabledNote}
          </div>
        )}
      </div>
    </div>
  );
}
