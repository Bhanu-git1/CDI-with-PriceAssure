import React, { useState } from 'react';
import DataTable from './DataTable';
import DataChart from './DataChart';

export default function MessageBubble({ message }) {
  const { sender, text, sql, data, error } = message;
  const [activeTab, setActiveTab] = useState('explanation'); // explanation | table | chart
  const [showSql, setShowSql] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasData = data && Array.isArray(data) && data.length > 0;

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
              <button
                className={`vis-tab ${activeTab === 'chart' ? 'active' : ''}`}
                onClick={() => setActiveTab('chart')}
              >
                📈 Bar Chart
              </button>
            </div>

            <div className="vis-content">
              {activeTab === 'explanation' && (
                <div style={{ whiteSpace: 'pre-line' }}>{text}</div>
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
          <div style={{ whiteSpace: 'pre-line' }}>{text}</div>
        )}

        {/* Display SQL block under explanation if available */}
        {sender === 'assistant' && sql && (
          <div style={{ marginTop: '12px' }}>
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
              {showSql ? 'Hide Generated SQL 🔼' : 'Show Generated SQL 🔽'}
            </button>
            
            {showSql && (
          <div className="sql-container">
            <div className="sql-header">
              <span>MySQL SELECT Query</span>
              <button onClick={copySqlToClipboard}>
                {copied ? 'Copied!' : 'Copy SQL'}
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
