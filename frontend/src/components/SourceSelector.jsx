import React, { useEffect, useRef, useState } from 'react';

/**
 * Data source picker shown inside the prompt input.
 *
 * "Auto" is the default and defers to the backend router. Choosing a concrete
 * source overrides routing entirely, which is the quickest way to settle an
 * ambiguous question — the user already knows which system they mean.
 */
const AUTO = { id: 'auto', short_label: 'Auto', badge: 'auto', domain: 'Let the assistant pick the data source' };

const BADGE_ICON = {
  auto: '✨',
  mysql: '🗄️',
  gpo: '📋',
  salesforce: '☁️',
};

export function sourceIcon(badge) {
  return BADGE_ICON[badge] || '🗄️';
}

export default function SourceSelector({ sources, value, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const options = [AUTO, ...(sources || [])];
  const selected = options.find((o) => o.id === value) || AUTO;

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Nothing to choose between until the catalogue has loaded.
  if (!sources || sources.length === 0) return null;

  return (
    <div className="source-selector" ref={wrapRef}>
      <button
        type="button"
        className={`source-selector-btn ${value !== 'auto' ? 'pinned' : ''}`}
        onClick={() => setOpen((p) => !p)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={
          value === 'auto'
            ? 'Data source: chosen automatically from your question'
            : `Data source pinned to ${selected.short_label}`
        }
      >
        <span className="source-selector-icon">{sourceIcon(selected.badge)}</span>
        <span className="source-selector-label">{selected.short_label}</span>
        <svg
          className={`source-selector-caret ${open ? 'open' : ''}`}
          width="11" height="11" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="source-selector-menu" role="listbox">
          <div className="source-selector-menu-head">Ask this question of</div>
          {options.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="option"
              aria-selected={opt.id === value}
              className={`source-selector-option ${opt.id === value ? 'selected' : ''}`}
              onClick={() => {
                onChange(opt.id);
                setOpen(false);
              }}
            >
              <span className="source-selector-option-icon">{sourceIcon(opt.badge)}</span>
              <span className="source-selector-option-body">
                <span className="source-selector-option-label">{opt.short_label}</span>
                {opt.domain && (
                  <span className="source-selector-option-desc">{opt.domain}</span>
                )}
              </span>
              {opt.id === value && (
                <svg
                  className="source-selector-check"
                  width="13" height="13" viewBox="0 0 24 24" fill="none"
                  stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
