import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DataTable from './DataTable';
import DataChart from './DataChart';
import MermaidViewer from './MermaidViewer';
import { getFollowUpSuggestions } from '../utils/suggestionHelper';
import { sourceIcon } from './SourceSelector';

function Markdown({ children }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children: codeChildren, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const lang = match ? match[1].toLowerCase() : '';
            const rawContent = String(codeChildren || '').replace(/\n$/, '');

            if (
              !inline &&
              (lang === 'mermaid' ||
                rawContent.startsWith('erDiagram') ||
                rawContent.startsWith('graph ') ||
                rawContent.startsWith('flowchart ') ||
                rawContent.startsWith('sequenceDiagram') ||
                rawContent.startsWith('classDiagram') ||
                rawContent.startsWith('stateDiagram'))
            ) {
              return <MermaidViewer code={rawContent} />;
            }
            return (
              <code className={className} {...props}>
                {codeChildren}
              </code>
            );
          }
        }}
      >
        {children || ''}
      </ReactMarkdown>
    </div>
  );
}

function formatUserDate(timestamp) {
  const d = timestamp ? new Date(timestamp) : new Date();
  if (isNaN(d.getTime())) {
    return {
      short: 'Today',
      full: new Date().toLocaleString()
    };
  }
  const short = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const full = d.toLocaleString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });
  return { short, full };
}

export default function MessageBubble({
  message,
  index,
  onSelectSuggestion,
  previousUserPrompt,
  onPickSource,
  onEditQuery,
  onRetryQuery,
  queryLoading
}) {
  const {
    sender, text, sql, data, error, source,
    source_badge: sourceBadge, routing,
    needs_clarification: needsClarification, candidates,
    timestamp
  } = message;

  const wantsChart = Boolean(previousUserPrompt && /chart|pie|donut|plot|graph|distribution|visualize|breakdown/i.test(previousUserPrompt));
  const [activeTab, setActiveTab] = useState(wantsChart ? 'chart' : 'answer'); // answer | table | chart
  const [showSql, setShowSql] = useState(false);
  const [copiedSql, setCopiedSql] = useState(false);
  const [copiedQuery, setCopiedQuery] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(text || '');

  useEffect(() => {
    setEditText(text || '');
  }, [text]);

  const hasData = data && Array.isArray(data) && data.length > 0;
  const queryLabel = 'SQL Query';

  const copySqlToClipboard = () => {
    if (!sql) return;
    navigator.clipboard.writeText(sql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  const handleCopyQuery = () => {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
    }
    setCopiedQuery(true);
    setTimeout(() => setCopiedQuery(false), 2000);
  };

  const handleSaveEdit = () => {
    const trimmed = editText.trim();
    if (!trimmed || queryLoading) return;
    setIsEditing(false);
    if (onEditQuery) {
      onEditQuery(trimmed, index);
    }
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditText(text || '');
  };

  const { short: dateShort, full: dateFull } = formatUserDate(timestamp);

  // User query rendering with Claude-style options: Date, Copy, Edit, Retry
  if (sender === 'user') {
    return (
      <div className="message-row user">
        <div className="user-message-container">
          {isEditing ? (
            <div className="user-message-edit-card">
              <textarea
                className="user-message-edit-textarea"
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSaveEdit();
                  } else if (e.key === 'Escape') {
                    handleCancelEdit();
                  }
                }}
                rows={Math.min(6, Math.max(2, (editText || '').split('\n').length))}
                autoFocus
                placeholder="Edit your prompt..."
              />
              <div className="user-message-edit-footer">
                <span className="user-edit-hint">Enter to submit • Shift+Enter for new line</span>
                <div className="user-edit-actions-btns">
                  <button
                    type="button"
                    className="user-edit-cancel-btn"
                    onClick={handleCancelEdit}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="user-edit-submit-btn"
                    onClick={handleSaveEdit}
                    disabled={!editText.trim() || queryLoading}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5" />
                      <polyline points="5 12 12 5 19 12" />
                    </svg>
                    <span>Save & Submit</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="message-bubble">
                <Markdown>{text}</Markdown>
              </div>

              {/* Claude-style User Query Actions Toolbar */}
              <div className="user-query-toolbar">
                {/* 1. Date (e.g. Sep 15) with hover tooltip for full date and time */}
                <div className="user-query-date-pill" title={dateFull}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="user-date-icon">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                  <span className="user-date-text">{dateShort}</span>
                </div>

                <div className="user-toolbar-actions-group">
                  {/* 2. Copy */}
                  <button
                    type="button"
                    className="user-toolbar-btn"
                    onClick={handleCopyQuery}
                    title={copiedQuery ? 'Copied!' : 'Copy prompt'}
                  >
                    {copiedQuery ? (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="action-success-icon">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    ) : (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                      </svg>
                    )}
                  </button>

                  {/* 3. Edit */}
                  <button
                    type="button"
                    className="user-toolbar-btn"
                    onClick={() => {
                      setIsEditing(true);
                      setEditText(text || '');
                    }}
                    title="Edit prompt"
                    disabled={queryLoading}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 20h9" />
                      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                    </svg>
                  </button>

                  {/* 4. Retry */}
                  <button
                    type="button"
                    className="user-toolbar-btn"
                    onClick={() => onRetryQuery && onRetryQuery(index)}
                    title="Retry query"
                    disabled={queryLoading}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                    </svg>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    );
  }

  // Assistant response rendering
  const followUpSuggestions =
    sender === 'assistant' && !needsClarification
      ? getFollowUpSuggestions(previousUserPrompt, message.source_id || message.source_badge || message.source)
      : [];

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
              <button
                className={`vis-tab ${activeTab === 'chart' ? 'active' : ''}`}
                onClick={() => setActiveTab('chart')}
              >
                🥧 Chart View
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
                <DataChart data={data} userPrompt={previousUserPrompt} />
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
                    {copiedSql ? 'Copied!' : `Copy ${queryLabel}`}
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
