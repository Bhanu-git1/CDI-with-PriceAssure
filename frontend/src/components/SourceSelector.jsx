import React, { useEffect, useRef, useState } from 'react';

/**
 * Data source picker shown inside the prompt input.
 *
 * "Auto" is the default and defers to the backend router. Choosing a concrete
 * source overrides routing entirely, which is the quickest way to settle an
 * ambiguous question — the user already knows which system they mean.
 */
const AUTO = { id: 'auto', short_label: 'Auto', badge: 'auto', domain: 'Let the assistant pick the data source' };

const SalesforceLogo = () => (
  <svg width="18" height="18" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ display:'inline-block', verticalAlign:'middle' }}>
    {/* Salesforce cloud shape */}
    <path
      d="M26.5 13C29.7 13 32.6 14.4 34.6 16.6C36.2 15.1 38.4 14.2 40.8 14.2C46.1 14.2 50.4 18.5 50.4 23.8C50.4 24.4 50.3 25 50.2 25.6C53.5 27 55.8 30.3 55.8 34.1C55.8 39.3 51.5 43.5 46.3 43.5H19.2C13.5 43.5 8.8 38.9 8.8 33.1C8.8 28.8 11.4 25.1 15.1 23.4C14.9 22.7 14.8 21.9 14.8 21.1C14.8 16.6 18.5 13 23 13C24.2 13 25.4 13.3 26.5 13.8V13Z"
      fill="#00A1E0"
    />
    {/* WiFi-style signal arcs inside cloud */}
    <circle cx="32" cy="32" r="4" fill="white"/>
    <path d="M24.5 32C24.5 27.9 27.9 24.5 32 24.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none"/>
    <path d="M39.5 32C39.5 27.9 36.1 24.5 32 24.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none"/>
    <path d="M20 32C20 25.4 25.4 20 32 20" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none"/>
    <path d="M44 32C44 25.4 38.6 20 32 20" stroke="white" strokeWidth="2.5" strokeLinecap="round" fill="none"/>
  </svg>
);

const BADGE_ICON = {
  auto: '✨',
  mysql: '🗄️',
  gpo: '📋',
  salesforce: <SalesforceLogo />,
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
