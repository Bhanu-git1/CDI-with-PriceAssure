import React, { useState, useEffect, useRef } from 'react';
import MessageBubble from './components/MessageBubble';
import './App.css';

export default function App() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState('connecting'); // online | offline | connecting
  const [activeModel, setActiveModel] = useState('');

  const messagesEndRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, queryLoading]);

  // Fetch Server Status on mount
  const checkStatus = async () => {
    try {
      // Fetch server stats
      const statusRes = await fetch('/api/');
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setServerStatus('online');
        setActiveModel(statusData.provider || 'AI Model');
      } else {
        setServerStatus('offline');
      }
    } catch (err) {
      console.error("Failed to connect to API backend:", err);
      setServerStatus('offline');
    }
  };

  useEffect(() => {
    checkStatus();
  }, []);

  const handleSendMessage = async (textToSend) => {
    const queryText = textToSend || inputValue;
    if (!queryText.trim()) return;

    // Add user message to log
    const userMsg = { sender: 'user', text: queryText };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setQueryLoading(true);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: queryText, history: messages })
      });

      if (!response.ok) {
        throw new Error(`Server returned status: ${response.status}`);
      }

      const result = await response.json();

      // Add assistant response to log
      const assistantMsg = {
        sender: 'assistant',
        text: result.answer,
        sql: result.sql,
        data: result.data,
        error: result.error
      };

      setMessages(prev => [...prev, assistantMsg]);

      // Refresh status in case of changes
      if (result.sql && (result.sql.toUpperCase().includes('CREATE') || result.sql.toUpperCase().includes('ALTER'))) {
        checkStatus();
      }

    } catch (error) {
      console.error("Chat Error:", error);
      setMessages(prev => [...prev, {
        sender: 'assistant',
        text: "Could not retrieve database output.",
        error: error.message
      }]);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSendMessage();
    }
  };

  return (
    <div className="app-container">
      {/* Main Chat Workstation */}
      <div className="main-chat-area">

        {/* Navigation / Header */}
        <div className="chat-header">
          <div className="chat-header-title">
            <h1>MCP MySQL Database Assistant</h1>
          </div>
          <div className="chat-header-status">
            <span>Model: <strong>{activeModel || 'Detecting...'}</strong></span>
            <div className="status-dot" style={{
              backgroundColor: serverStatus === 'online' ? 'var(--status-success)' : serverStatus === 'connecting' ? 'var(--status-warning)' : 'var(--status-danger)',
              boxShadow: `0 0 8px ${serverStatus === 'online' ? 'var(--status-success)' : serverStatus === 'connecting' ? 'var(--status-warning)' : 'var(--status-danger)'}`
            }} />
            <span style={{ fontSize: '0.8rem', textTransform: 'capitalize' }}>{serverStatus}</span>
          </div>
        </div>

        {/* Messaging Box */}
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state">
              <h3>Database Intelligence Hub 🔍</h3>
              <p>
                Ask questions about your data in plain English. The AI will translate your question into a read-only SQL query, retrieve results from MySQL via the Model Context Protocol (MCP), and display charts or tables!
              </p>

              <div style={{ width: '100%', marginTop: '24px' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '12px', fontWeight: '600' }}>
                  {/* TRY ASKING ABOUT YOUR `Leakage_Activity` TABLE: */}
                </p>
                <div className="suggested-queries">
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show me a list of all tables in the database")}
                  >
                    📋 List all tables in the database
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show the first 5 rows in the Leakage_Activity table")}
                  >
                    📈 View sample rows from Leakage_Activity
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Which brand has the highest leakage percentage?")}
                  >
                    🏷️ Find the brand with highest leakage percentage
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("What is the average Leakage_Percentage grouped by State?")}
                  >
                    🗺️ Average leakage percentage by State
                  </button>
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg, index) => (
              <MessageBubble key={index} message={msg} />
            ))
          )}

          {/* Assistant Loading Response State */}
          {queryLoading && (
            <div className="message-row assistant">
              <div className="message-bubble" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border-color)' }}>
                <div className="loading-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  AI generating SQL & executing via MCP...
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Message Input Workspace */}
        <div className="input-area">
          <div className="input-container">
            <input
              type="text"
              placeholder="Ask a question about database records (e.g. 'Show average brand rejections by State')..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              disabled={queryLoading}
            />
            <button
              className="send-btn"
              onClick={() => handleSendMessage()}
              disabled={queryLoading || !inputValue.trim()}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
