import { useState } from 'react';
import './JsonBlock.css';

interface JsonBlockProps {
  label?: string;
  data: unknown;
  defaultOpen?: boolean;
}

export function JsonBlock({
  label = 'Raw data',
  data,
  defaultOpen = false,
}: JsonBlockProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="json-block">
      <div
        className="json-block__header"
        onClick={() => setOpen(!open)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen(!open);
          }
        }}
        role="button"
        tabIndex={0}
        aria-expanded={open}
      >
        <span className="json-block__label">{label}</span>
        <span className="json-block__toggle">{open ? '▾ COLLAPSE' : '▸ EXPAND'}</span>
      </div>
      {open && (
        <div className="json-block__content">
          <pre className="json-block__pre">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
