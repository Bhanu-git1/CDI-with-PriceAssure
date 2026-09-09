import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DataTable from './DataTable';
import DataChart from './DataChart';
import { getFollowUpSuggestions } from '../utils/suggestionHelper';
import { sourceIcon } from './SourceSelector';

function Markdown({ children }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ''}</ReactMarkdown>
    </div>
  );
}

export default function MessageBubble({ message, onSelectSuggestion, previousUserPrompt, onPickSource }) {
  const {
    sender, text, sql, data, error, source,
    source_badge: sourceBadge, routing,
    needs_clarification: needsClarification, candidates,
  } = message;
  const [activeTab, setActiveTab] = useState('answer'); // answer | table | chart
  const [showSql, setShowSql] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasData = data && Array.isArray(data) && data.length > 0;
  const queryLabel = 'SQL Query';

  const copySqlToClipboard = () => {
    if (!sql) return;
    navigator.clipboard.writeText(sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Suppress generic follow-ups while the assistant is waiting for the user to
  // say which data source they meant — the only useful next action is choosing.
  // Scoped to the source that answered, so a chip never moves the
  // conversation to a different database without the user asking.
  const followUpSuggestions =
    sender === 'assistant' && !needsClarification
      ? getFollowUpSuggestions(previousUserPrompt, message.source_id)
      : [];

  // Badge class comes from the backend-declared badge, falling back to the
  // label for transcripts saved before source_badge existed.
  const badgeKey = (sourceBadge || source || '').toLowerCase();
  const routingTitle = routing
    ? `Routed by ${routing.stage}` +
      (routing.confidence != null ? ` · confidence ${routing.confidence}` : '') +
      (routing.reason ? `\n${routing.reason}` : '')
    : undefined;

  return (
    <div className={`message-row ${sender}`}>
      <div className="message-bubble">
        {sender === 'assistant' && hasData ? (
          <div className="visualization-container">
            <div className="vis-tabs">
              <button
                className={`vis-tab ${activeTab === 'answer' ? 'active' : ''}`}
                onClick={() => setActiveTab('answer')}
              >
                💬 Answer
              </button>
              <button
                className={`vis-tab ${activeTab === 'table' ? 'active' : ''}`}
                onClick={() => setActiveTab('table')}
              >
                📊 Table View
              </button>
            </div>

            <div className="vis-content">
              {activeTab === 'answer' && (
                <Markdown>{text || '_No summary available for this response._'}</Markdown>
              )}
              {activeTab === 'table' && (
                <DataTable data={data} />
              )}

              {activeTab === 'chart' && (
                <DataChart data={data} />
              )}
            </div>
          </div>
        ) : (
          <Markdown>{text}</Markdown>
        )}

        {/* Display SQL block under explanation if available */}
        {sender === 'assistant' && sql && (
          <div style={{ marginTop: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <button
                onClick={() => setShowSql(!showSql)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'var(--accent-secondary)',
                  cursor: 'pointer',
                  fontSize: '0.8rem',
                  fontWeight: '600',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '2px 0'
                }}
              >
                {showSql ? `Hide Generated ${queryLabel} 🔼` : `Show Generated ${queryLabel} 🔽`}
              </button>

              {source && (
                <span className={`source-badge source-badge-${badgeKey}`} title={routingTitle}>
                  {sourceIcon(badgeKey)} Source: {source}
                </span>
              )}
            </div>

            {showSql && (
              <div className="sql-container">
                <div className="sql-header">
                  <span>{queryLabel}</span>
                  <button onClick={copySqlToClipboard}>
                    {copied ? 'Copied!' : `Copy ${queryLabel}`}
                  </button>
                </div>
                <pre className="sql-body">{sql}</pre>
              </div>
            )}
          </div>
        )}

        {/* Display Errors if any occur */}
        {error && (
          <div className="error-message">
            <strong>Execution Error:</strong> {error}
          </div>
        )}

        {/* Router abstained: let the user choose the data source rather than
            answering from a possibly wrong one. */}
        {sender === 'assistant' && needsClarification && candidates?.length > 0 && (
          <div className="source-clarify-container">
            <div className="source-clarify-chips">
              {candidates.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className="source-clarify-chip"
                  onClick={() => onPickSource && onPickSource(c.id)}
                  disabled={!onPickSource}
                  title={c.why}
                >
                  <span className="source-clarify-chip-icon">{sourceIcon(c.badge)}</span>
                  <span className="source-clarify-chip-text">Ask {c.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Display Recommended Follow-ups directly below prompt result */}
        {sender === 'assistant' && followUpSuggestions.length > 0 && onSelectSuggestion && (
          <div className="followup-suggestions-container">
            <div className="followup-suggestions-header">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className="followup-sparkle-icon">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
              <span>Recommended Follow-ups:</span>
            </div>
            <div className="followup-chips-grid">
              {followUpSuggestions.map((item, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="followup-chip-btn"
                  onClick={() => onSelectSuggestion(item.query)}
                  title={`Ask: "${item.query}"`}
                >
                  <span className="followup-chip-icon">{item.icon}</span>
                  <span className="followup-chip-text">{item.title}</span>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="followup-chip-arrow">
                    <line x1="5" y1="12" x2="19" y2="12" />
                    <polyline points="12 5 19 12 12 19" />
                  </svg>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

