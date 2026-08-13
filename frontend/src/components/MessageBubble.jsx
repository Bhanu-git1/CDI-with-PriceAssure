import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DataTable from './DataTable';

function Markdown({ children }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ''}</ReactMarkdown>
    </div>
  );
}

export default function MessageBubble({ message }) {
  const { sender, text, sql, data, error, source } = message;
  const [activeTab, setActiveTab] = useState('explanation'); // explanation | table | chart
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

  return (
    <div className={`message-row ${sender}`}>
      <div className="message-bubble">
        {sender === 'assistant' && hasData ? (
          <div className="visualization-container">
            <div className="vis-tabs">
              <button
                className={`vis-tab ${activeTab === 'explanation' ? 'active' : ''}`}
                onClick={() => setActiveTab('explanation')}
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
              {activeTab === 'explanation' && (
                <Markdown>{text}</Markdown>
              )}
              {activeTab === 'table' && (
                <DataTable data={data} />
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
                <span className={`source-badge source-badge-${source.toLowerCase()}`}>
                  {source === 'Salesforce' ? '☁️' : '🗄️'} Source: {source}
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
    </div>
    </div >
  );
}
