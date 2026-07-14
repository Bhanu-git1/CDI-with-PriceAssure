import React, { useState, useEffect, useRef } from 'react';
import MessageBubble from './components/MessageBubble';
import './App.css';

// Default endpoint fallback
const getInitialEndpoint = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  const savedUrl = localStorage.getItem('__sf_chat_api_endpoint__');
  return savedUrl || envUrl || 'http://localhost:8000';
};

export default function App() {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState('connecting'); // online | offline | connecting
  const [activeModel, setActiveModel] = useState('');
  
  // Dynamic API endpoint configuration
  const [apiEndpoint, setApiEndpoint] = useState(getInitialEndpoint());
  const [showSettings, setShowSettings] = useState(false);
  const [tempEndpoint, setTempEndpoint] = useState(apiEndpoint);

  const messagesEndRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, queryLoading]);

  // Fetch Server Status on mount/endpoint change
  const checkStatus = async (targetEndpoint = apiEndpoint) => {
    setServerStatus('connecting');
    try {
      const statusRes = await fetch(`${targetEndpoint}/api/`, {
        headers: { 'ngrok-skip-browser-warning': 'true' }
      });
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
  }, [apiEndpoint]);

  const handleSendMessage = async (textToSend) => {
    const queryText = textToSend || inputValue;
    if (!queryText.trim()) return;

    // Add user message to log
    const userMsg = { sender: 'user', text: queryText };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setQueryLoading(true);

    try {
      const requestBody = {
        message: queryText,
        history: messages
      };

      const response = await fetch(`${apiEndpoint}/api/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify(requestBody)
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

    } catch (error) {
      console.error("Chat Error:", error);
      setMessages(prev => [...prev, {
        sender: 'assistant',
        text: "Could not retrieve Salesforce data.",
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
            <div className="header-logo">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" fill="url(#sfGrad)"/>
                <path d="M8 12l2 2 4-4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                <defs>
                  <linearGradient id="sfGrad" x1="2" y1="2" x2="22" y2="22">
                    <stop offset="0%" stopColor="#00A1E0"/>
                    <stop offset="100%" stopColor="#032D60"/>
                  </linearGradient>
                </defs>
              </svg>
              <h1>Salesforce Data Assistant</h1>
            </div>
          </div>
          <div className="chat-header-status">
            <span>Model: <strong>{activeModel || 'Detecting...'}</strong></span>
            <div className="status-dot" style={{
              backgroundColor: serverStatus === 'online' ? 'var(--status-success)' : serverStatus === 'connecting' ? 'var(--status-warning)' : 'var(--status-danger)',
              boxShadow: `0 0 8px ${serverStatus === 'online' ? 'var(--status-success)' : serverStatus === 'connecting' ? 'var(--status-warning)' : 'var(--status-danger)'}`
            }} />
            <span style={{ fontSize: '0.8rem', textTransform: 'capitalize' }}>{serverStatus}</span>
            <button 
              onClick={() => setShowSettings(!showSettings)}
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                fontSize: '1rem',
                display: 'flex',
                alignItems: 'center',
                padding: '4px',
                marginLeft: '8px',
                transition: 'transform 0.2s ease'
              }}
              title="Configure Backend Connection"
            >
              ⚙️
            </button>
          </div>
        </div>

        {/* Dynamic Endpoint Configuration Panel */}
        {showSettings && (
          <div className="endpoint-settings-panel" style={{
            background: 'var(--bg-tertiary)',
            borderBottom: '1px solid var(--border-color)',
            padding: '12px 32px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            fontSize: '0.85rem',
            animation: 'slideDown 0.2s ease'
          }}>
            <span style={{ fontWeight: '600', color: 'var(--text-secondary)' }}>Connection Endpoint:</span>
            <input 
              type="text" 
              value={tempEndpoint}
              onChange={(e) => setTempEndpoint(e.target.value)}
              placeholder="e.g. https://abc123.ngrok-free.app or http://localhost:8000"
              style={{
                flex: 1,
                padding: '6px 12px',
                borderRadius: '6px',
                border: '1px solid var(--border-color)',
                outline: 'none',
                fontSize: '0.85rem'
              }}
            />
            <button 
              onClick={() => {
                const cleanUrl = tempEndpoint.trim().replace(/\/$/, ""); // trim trailing slash
                localStorage.setItem('__sf_chat_api_endpoint__', cleanUrl);
                setApiEndpoint(cleanUrl);
                setTempEndpoint(cleanUrl);
                setShowSettings(false);
              }}
              style={{
                background: 'var(--accent-primary)',
                color: 'white',
                border: 'none',
                padding: '6px 12px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              Save
            </button>
            <button 
              onClick={() => {
                setTempEndpoint(apiEndpoint);
                setShowSettings(false);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-secondary)',
                cursor: 'pointer'
              }}
            >
              Cancel
            </button>
          </div>
        )}

        {/* Messaging Box */}
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="url(#emptyGrad)" strokeWidth="1.5"/>
                  <path d="M8 12l2 2 4-4" stroke="url(#emptyGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <defs>
                    <linearGradient id="emptyGrad" x1="4" y1="4" x2="20" y2="20">
                      <stop offset="0%" stopColor="#00A1E0"/>
                      <stop offset="100%" stopColor="#1B96FF"/>
                    </linearGradient>
                  </defs>
                </svg>
              </div>
              <h3>Salesforce Intelligence Hub ☁️</h3>
              <p>
                Ask questions about your CRM data in plain English. The AI will translate your question into a read-only SOQL query, execute it against your Salesforce org via the Model Context Protocol (MCP), and display results with charts and tables!
              </p>

              <div style={{ width: '100%', marginTop: '24px' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '12px', fontWeight: '600' }}>
                  TRY ASKING ABOUT YOUR SALESFORCE DATA:
                </p>
                <div className="suggested-queries">
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show me the top 10 accounts by annual revenue")}
                  >
                    🏢 Top 10 accounts by annual revenue
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("What is the total opportunity amount by stage?")}
                  >
                    📊 Opportunity pipeline by stage
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show me open high-priority cases from the last 30 days")}
                  >
                    🎫 Recent high-priority open cases
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("How many leads were converted this year?")}
                  >
                    🎯 Lead conversions this year
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
                  AI generating SOQL & querying Salesforce via MCP...
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
              placeholder="Ask about Accounts, Contacts, Opportunities, Cases... (e.g., 'Show top deals closing this month')"
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
