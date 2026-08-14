import React, { useState, useEffect, useRef } from 'react';
import MessageBubble from './components/MessageBubble';
import LoginPage from './components/LoginPage';
import logoMain from './assets/SRM_logo.png';
import './App.css';

// Backend API endpoint — set via VITE_API_URL at build time or cached from a prior session.
const getApiEndpoint = () => {
  const envUrl = import.meta.env.VITE_API_URL;
  const savedUrl = localStorage.getItem('__mysql_chat_api_endpoint__') || localStorage.getItem('__sf_chat_api_endpoint__');
  return savedUrl || envUrl || 'http://localhost:8000';
};

// How often to silently re-check backend/connection/LLM health in the background.
const STATUS_POLL_MS = 15000;

export default function App() {
  const [currentUser, setCurrentUser] = useState(() => localStorage.getItem('__dce_current_user__') || null);
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState('connecting'); // online | offline | connecting
  const [activeModel, setActiveModel] = useState('');
  const [connections, setConnections] = useState([]);
  const [llmStatus, setLlmStatus] = useState('connecting'); // connected | offline | connecting
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const apiEndpoint = getApiEndpoint();

  const messagesEndRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, queryLoading]);

  // Live backend/connection/LLM status check. Only shows the transient
  // "connecting" state on the very first load — background polls update
  // straight to the resolved status so the UI doesn't flicker every cycle.
  const checkStatus = async (isInitial = false) => {
    if (isInitial) {
      setServerStatus('connecting');
      setLlmStatus('connecting');
    }
    try {
      const statusRes = await fetch(`${apiEndpoint}/api/`, {
        headers: { 'ngrok-skip-browser-warning': 'true' }
      });
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setServerStatus('online');
        setActiveModel(statusData.provider || 'AI Model');
        setConnections(statusData.connections || []);
        setLlmStatus(statusData.llm?.status || 'offline');
      } else {
        setServerStatus('offline');
        setConnections([]);
        setLlmStatus('offline');
      }
    } catch (err) {
      console.error("Failed to connect to API backend:", err);
      setServerStatus('offline');
      setConnections([]);
      setLlmStatus('offline');
    }
  };

  // Check immediately on load, then keep polling in the background so
  // status reflects reality live, without requiring a page refresh.
  useEffect(() => {
    checkStatus(true);
    const interval = setInterval(() => checkStatus(false), STATUS_POLL_MS);
    return () => clearInterval(interval);
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
        error: result.error,
        source: result.source
      };

      setMessages(prev => [...prev, assistantMsg]);

    } catch (error) {
      console.error("Chat Error:", error);
      setMessages(prev => [...prev, {
        sender: 'assistant',
        text: "Could not retrieve database data.",
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

  const handleLogin = (userId) => {
    localStorage.setItem('__dce_current_user__', userId);
    setCurrentUser(userId);
  };

  const handleLogout = () => {
    localStorage.removeItem('__dce_current_user__');
    setCurrentUser(null);
  };

  if (!currentUser) {
    return <LoginPage onLogin={handleLogin} />;
  }

  // Shared color mapping for every status dot in the sidebar: healthy states
  // (online/connected) are green, the transient initial check is amber, and
  // every other state (offline, or anything unexpected) is red.
  const statusToColor = (status) => {
    if (status === 'online' || status === 'connected') return 'var(--status-success)';
    if (status === 'connecting') return 'var(--status-warning)';
    return 'var(--status-danger)';
  };
  const statusColor = statusToColor(serverStatus);
  const llmColor = statusToColor(llmStatus);

  return (
    <div className="app-container">
      {/* Left Sidebar — backend connections, model info, account */}
      <aside className={`app-sidebar ${sidebarOpen ? '' : 'sidebar-collapsed'}`}>
        <div className="sidebar-brand">
          <button className="sidebar-toggle-btn" onClick={() => setSidebarOpen(false)} title="Collapse sidebar">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <line x1="9" y1="4" x2="9" y2="20" />
            </svg>
          </button>
          <img src={logoMain} alt="Pharma AI Agent" className="sidebar-brand-logo" />
        </div>

        <div className="sidebar-scroll">
          {/* Backend System Connections */}
          <div className="sidebar-section">
            <h4 className="sidebar-section-title">Backend Connections</h4>

            <div className="connection-row">
              <span className="connection-dot" style={{ backgroundColor: statusColor, boxShadow: `0 0 6px ${statusColor}` }} />
              <span className="connection-name">API Server</span>
              <span className="connection-state" style={{ color: statusColor }}>{serverStatus}</span>
            </div>

            {connections.map((conn) => {
              const dotColor = statusToColor(conn.status);
              return (
                <div className="connection-row" key={conn.name} title={conn.detail || ''}>
                  <span className="connection-dot" style={{ backgroundColor: dotColor, boxShadow: `0 0 6px ${dotColor}` }} />
                  <span className="connection-name">{conn.name}</span>
                  <span className="connection-state" style={{ color: dotColor }}>{conn.status === 'connected' ? 'online' : conn.status}</span>
                </div>
              );
            })}
          </div>

          {/* AI Model */}
          <div className="sidebar-section">
            <h4 className="sidebar-section-title">AI Model</h4>
            <div className="connection-row" title={activeModel || ''}>
              <span className="connection-dot" style={{ backgroundColor: llmColor, boxShadow: `0 0 6px ${llmColor}` }} />
              <span className="connection-name">{activeModel || 'Detecting...'}</span>
              <span className="connection-state" style={{ color: llmColor }}>{llmStatus === 'connected' ? 'online' : llmStatus}</span>
            </div>
          </div>
        </div>

        {/* Logged-in User */}
        <div className="sidebar-user">
          <div className="user-avatar">{currentUser.charAt(0).toUpperCase()}</div>
          <div className="user-meta">
            <span className="user-name">{currentUser}</span>
            <span className="user-role">Signed in</span>
          </div>
          <button className="logout-icon-btn" onClick={handleLogout} title="Logout">
            🚪
          </button>
        </div>
      </aside>

      {/* Reopen control — shown only while the sidebar is collapsed */}
      {!sidebarOpen && (
        <button className="sidebar-expand-btn" onClick={() => setSidebarOpen(true)} title="Expand sidebar">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <line x1="9" y1="4" x2="9" y2="20" />
          </svg>
        </button>
      )}

      {/* Main Chat Workstation */}
      <div className="main-chat-area">

        {/* Messaging Box */}
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <img src={logoMain} alt="" />
              </div>
              <h3>Pharma Command Center 🏥</h3>
              <p className="empty-state-tagline">Pharma AI Agent</p>
              <p>
                Ask questions about Leakage Signals (UC1) and Journey Orchestration & HCP Fatigue (UC2). The AI will translate your questions into governed SQL and display real-time analytics!
              </p>

              <div style={{ width: '100%', marginTop: '24px' }}>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '12px', fontWeight: '600' }}>
                  SUGGESTED QUERIES:
                </p>
                <div className="suggested-queries">
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show the top 10 physician leakage records")}
                  >
                    📉 Top 10 physician leakage records
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("List all physicians flagged with a digital fatigue score above 45")}
                  >
                    ⚡ Physicians with fatigue score above 45
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Calculate leakage summary grouped by state")}
                  >
                    📊 Leakage percentage summary by state
                  </button>
                  <button
                    className="suggested-btn"
                    onClick={() => handleSendMessage("Show email open rate per campaign")}
                  >
                    📧 Email open rate per campaign
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
                  AI generating code & querying MySQL...
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
              placeholder="Ask about Leakage %, HCP Fatigue, Voice Work Details... (e.g., 'Show work details for rep 2006')"
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
