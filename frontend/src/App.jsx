import React, { useState, useEffect, useRef } from 'react';
import MessageBubble from './components/MessageBubble';
import SourceSelector from './components/SourceSelector';
import LoginPage from './components/LoginPage';
import logoMain from './assets/SRM_logo.png';
import logoSmall from './assets/SRM_logo_small.png';
import { getApiEndpoint } from './utils/apiEndpoint';
import './App.css';


// How often to silently re-check backend/connection/LLM health in the background.
const STATUS_POLL_MS = 15000;

// Helper to get user-scoped storage key
const getHistoryStorageKey = (user) => `__dce_chat_history_${(user || 'guest').toLowerCase()}__`;

// Helper to load chat history from localStorage with user scoping
const loadSavedSessions = (user) => {
  try {
    const key = getHistoryStorageKey(user);
    const saved = localStorage.getItem(key);
    if (!saved) return [];
    const parsed = JSON.parse(saved);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch (err) {
    console.error("Failed to load chat history:", err);
    return [];
  }
};

export default function App() {
  const [currentUser, setCurrentUser] = useState(() => localStorage.getItem('__dce_current_user__') || null);
  const [userProfile, setUserProfile] = useState(() => {
    try {
      const saved = localStorage.getItem('__dce_user_profile__');
      return saved ? JSON.parse(saved) : null;
    } catch (e) {
      return null;
    }
  });
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [queryLoading, setQueryLoading] = useState(false);
  const [serverStatus, setServerStatus] = useState('connecting'); // online | offline | connecting
  // Short name for display; the fully-qualified model id stays on hover.
  const [activeModel, setActiveModel] = useState('');
  const [activeModelFull, setActiveModelFull] = useState('');
  const [connections, setConnections] = useState([]);
  // Data source catalogue from the backend, and the user's selection.
  // 'auto' defers to the backend router, which is the default.
  const [sources, setSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState('auto');
  const [llmStatus, setLlmStatus] = useState('connecting'); // connected | offline | connecting
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [systemStatusOpen, setSystemStatusOpen] = useState(true);
  const [modelStatusOpen, setModelStatusOpen] = useState(true);
  const [promptHistoryOpen, setPromptHistoryOpen] = useState(true);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [chatHistory, setChatHistory] = useState(() => {
    const user = localStorage.getItem('__dce_current_user__');
    return loadSavedSessions(user);
  });
  const [historyLoading, setHistoryLoading] = useState(true);
  const [selectingChatId, setSelectingChatId] = useState(null);
  const [thinkMode, setThinkMode] = useState(false);
  const [contextMenu, setContextMenu] = useState({ open: false, x: 0, y: 0, session: null });
  const [editingChatId, setEditingChatId] = useState(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem('__dce_dark_mode__') === 'true');
  const [toast, setToast] = useState(null);

  const apiEndpoint = getApiEndpoint();

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Close context menu on outside click or escape
  useEffect(() => {
    const handleGlobalClick = () => {
      if (contextMenu.open) {
        setContextMenu({ open: false, x: 0, y: 0, session: null });
      }
    };
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setContextMenu({ open: false, x: 0, y: 0, session: null });
        setEditingChatId(null);
      }
    };
    window.addEventListener('click', handleGlobalClick);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('click', handleGlobalClick);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [contextMenu.open]);

  const showToast = (message) => {
    setToast(message);
    setTimeout(() => {
      setToast(null);
    }, 2800);
  };

  const handleNewChat = () => {
    if (queryLoading) return;
    setCurrentChatId(null);
    setMessages([]);
    setInputValue('');
    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const handleSelectChat = async (session) => {
    if (historyLoading || selectingChatId || editingChatId === session.id) return;
    setCurrentChatId(session.id);

    // If messages are already present in memory, load them directly
    if (session.messages && session.messages.length > 0) {
      setMessages(session.messages);
    } else {
      setMessages([]);
      setSelectingChatId(session.id);
      setQueryLoading(true);
      try {
        const res = await fetch(`${apiEndpoint}/api/chats/${encodeURIComponent(session.id)}`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        if (res.ok) {
          const fullSession = await res.json();
          const loadedMessages = fullSession.messages || [];
          setMessages(loadedMessages);
          setChatHistory((prev) =>
            prev.map((c) => (c.id === session.id ? { ...c, messages: loadedMessages } : c))
          );
        }
      } catch (err) {
        console.error("Failed to load chat details from backend:", err);
      } finally {
        setQueryLoading(false);
        setSelectingChatId(null);
      }
    }

    if (inputRef.current) {
      inputRef.current.focus();
    }
  };

  const saveSessionToBackend = async (chatId, title, messagesToSave, isPinned = false) => {
    try {
      await fetch(`${apiEndpoint}/api/chats`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({
          id: chatId,
          title: title,
          isPinned: !!isPinned,
          user_id: currentUser || 'default_user',
          messages: messagesToSave
        })
      });
    } catch (e) {
      console.warn("Failed to persist chat session to backend:", e);
    }
  };

  const handleShare = async (session) => {
    if (!session) return;
    setContextMenu({ open: false, x: 0, y: 0, session: null });

    let msgs = session.messages;
    if (!msgs || msgs.length === 0) {
      try {
        const res = await fetch(`${apiEndpoint}/api/chats/${encodeURIComponent(session.id)}`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        if (res.ok) {
          const fullSession = await res.json();
          msgs = fullSession.messages || [];
        }
      } catch (err) {
        console.warn("Could not load full chat transcript for sharing:", err);
      }
    }

    let formattedTranscript = `=== Chat Conversation: ${session.title} ===\n\n`;
    if (msgs && msgs.length > 0) {
      formattedTranscript += msgs.map((m) => {
        const role = m.sender === 'user' ? 'User' : 'Pharma Decision Intelligence';
        const content = m.text || (m.sql ? `SQL Query:\n${m.sql}` : '');
        return `[${role}]:\n${content}`;
      }).join('\n\n----------------------------------------\n\n');
    } else {
      formattedTranscript += `Title: ${session.title}\nSession ID: ${session.id}`;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(formattedTranscript);
        showToast("Conversation copied to clipboard!");
        return;
      } catch (err) {
        console.warn("Clipboard copy failed, using fallback:", err);
      }
    }

    showToast("Conversation ready to share");
  };

  const handleStartRename = (session) => {
    if (!session) return;
    setEditingChatId(session.id);
    setEditingTitle(session.title || '');
    setContextMenu({ open: false, x: 0, y: 0, session: null });
  };

  const handleSaveRename = async (id) => {
    const trimmed = editingTitle.trim();
    if (!trimmed) {
      setEditingChatId(null);
      return;
    }
    setChatHistory((prev) => {
      const updated = prev.map((c) => (c.id === id ? { ...c, title: trimmed } : c));
      try {
        localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to save chat title:", err);
      }
      return updated;
    });
    setEditingChatId(null);
    showToast("Chat renamed");

    try {
      await fetch(`${apiEndpoint}/api/chats/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({ title: trimmed })
      });
    } catch (err) {
      console.error("Failed to rename chat on backend:", err);
    }
  };

  const handleTogglePin = async (session) => {
    if (!session) return;
    const isNowPinned = !session.isPinned;
    setChatHistory((prev) => {
      const updated = prev.map((c) => (c.id === session.id ? { ...c, isPinned: isNowPinned } : c));
      try {
        localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to update pin state:", err);
      }
      return updated;
    });
    setContextMenu({ open: false, x: 0, y: 0, session: null });
    showToast(isNowPinned ? "Chat pinned to top" : "Chat unpinned");

    try {
      await fetch(`${apiEndpoint}/api/chats/${encodeURIComponent(session.id)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({ isPinned: isNowPinned })
      });
    } catch (err) {
      console.error("Failed to update pin on backend:", err);
    }
  };

  const handleOpenContextMenu = (e, session) => {
    if (!session) return;
    e.preventDefault();
    e.stopPropagation();

    // Determine position based on button clicked or cursor coordinates
    const targetEl = e.currentTarget;
    let x, y;
    const menuWidth = 190;
    const menuHeight = 175;

    if (targetEl && targetEl.getBoundingClientRect) {
      const rect = targetEl.getBoundingClientRect();
      x = rect.right + 6;
      y = rect.top;
    } else {
      x = e.clientX || 200;
      y = e.clientY || 200;
    }

    // Keep within window viewport boundaries
    if (x + menuWidth > window.innerWidth) {
      if (targetEl && targetEl.getBoundingClientRect) {
        const rect = targetEl.getBoundingClientRect();
        x = Math.max(10, rect.left - menuWidth - 6);
      } else {
        x = Math.max(10, window.innerWidth - menuWidth - 10);
      }
    }
    if (y + menuHeight > window.innerHeight) {
      y = Math.max(10, window.innerHeight - menuHeight - 10);
    }

    if (contextMenu.open && contextMenu.session?.id === session.id) {
      setContextMenu({ open: false, x: 0, y: 0, session: null });
    } else {
      setContextMenu({
        open: true,
        x,
        y,
        session
      });
    }
  };

  const handleDeleteChat = async (sessionId) => {
    if (!sessionId) return;
    setChatHistory((prev) => {
      const updated = prev.filter((c) => c.id !== sessionId);
      try {
        localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to delete chat:", err);
      }
      return updated;
    });
    if (currentChatId === sessionId) {
      setCurrentChatId(null);
      setMessages([]);
    }
    setContextMenu({ open: false, x: 0, y: 0, session: null });
    showToast("Chat deleted");

    try {
      await fetch(`${apiEndpoint}/api/chats/${encodeURIComponent(sessionId)}`, {
        method: 'DELETE',
        headers: { 'ngrok-skip-browser-warning': 'true' }
      });
    } catch (err) {
      console.error("Failed to delete chat on backend:", err);
    }
  };

  const parseSessionCreatedDate = (session) => {
    if (!session) return new Date();

    // Prefer createdAt / created_at, then timestamp, then updatedAt
    const raw = session.createdAt || session.created_at || session.timestamp || session.updated_at || session.updatedAt;

    if (raw) {
      if (typeof raw === 'number') {
        return new Date(raw);
      }
      if (typeof raw === 'string') {
        // If ISO string like 2026-09-15T09:25:30 without timezone offset, treat as UTC
        const normalized = (raw.includes('T') && !raw.endsWith('Z') && !raw.includes('+') && !raw.slice(10).includes('-'))
          ? raw + 'Z'
          : raw;
        const parsed = new Date(normalized);
        if (!isNaN(parsed.getTime())) return parsed;
        const parsedDirect = new Date(raw);
        if (!isNaN(parsedDirect.getTime())) return parsedDirect;
      }
    }

    // Fallback to timestamp embedded in chat ID (chat-1789101854816-xxx)
    if (session.id && typeof session.id === 'string') {
      const match = session.id.match(/chat-(\d{10,13})/);
      if (match) {
        const epoch = parseInt(match[1], 10);
        const parsed = new Date(epoch);
        if (!isNaN(parsed.getTime())) return parsed;
      }
    }

    return new Date();
  };

  const getCalendarDayDifference = (sessionDate, nowDate = new Date()) => {
    const dNow = new Date(nowDate.getFullYear(), nowDate.getMonth(), nowDate.getDate());
    const dSession = new Date(sessionDate.getFullYear(), sessionDate.getMonth(), sessionDate.getDate());
    const diffMs = dNow.getTime() - dSession.getTime();
    return Math.floor(diffMs / (1000 * 60 * 60 * 24));
  };

  const groupChatsByDate = (items) => {
    if (!items || items.length === 0) return [];

    // Parse created date for all sessions and sort descending (newest on top)
    const parsedList = items.map((item) => ({
      ...item,
      _createdDate: parseSessionCreatedDate(item)
    }));

    parsedList.sort((a, b) => b._createdDate.getTime() - a._createdDate.getTime());

    const pinned = parsedList.filter((i) => i.isPinned);
    const unpinned = parsedList.filter((i) => !i.isPinned);

    const now = new Date();
    const resultGroups = [];

    // 1. Pinned group always on top
    if (pinned.length > 0) {
      resultGroups.push({
        label: 'Pinned',
        items: pinned
      });
    }

    const todayItems = [];
    const yesterdayItems = [];
    const prev7DaysItems = [];
    const prev30DaysItems = [];
    const olderMonthMap = new Map();

    unpinned.forEach((item) => {
      const diffDays = getCalendarDayDifference(item._createdDate, now);

      if (diffDays <= 0) {
        // Created Today (or future clock drift)
        todayItems.push(item);
      } else if (diffDays === 1) {
        // Created Yesterday
        yesterdayItems.push(item);
      } else if (diffDays >= 2 && diffDays <= 7) {
        // Created 2 to 7 days ago
        prev7DaysItems.push(item);
      } else if (diffDays >= 8 && diffDays <= 30) {
        // Created 8 to 30 days ago
        prev30DaysItems.push(item);
      } else {
        // Older by month & year
        const d = item._createdDate;
        const monthYearLabel = d.toLocaleDateString('en-US', {
          month: 'long',
          year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
        });
        if (!olderMonthMap.has(monthYearLabel)) {
          olderMonthMap.set(monthYearLabel, []);
        }
        olderMonthMap.get(monthYearLabel).push(item);
      }
    });

    if (todayItems.length > 0) resultGroups.push({ label: 'Today', items: todayItems });
    if (yesterdayItems.length > 0) resultGroups.push({ label: 'Yesterday', items: yesterdayItems });
    if (prev7DaysItems.length > 0) resultGroups.push({ label: 'Previous 7 Days', items: prev7DaysItems });
    if (prev30DaysItems.length > 0) resultGroups.push({ label: 'Previous 30 Days', items: prev30DaysItems });

    olderMonthMap.forEach((mItems, mLabel) => {
      if (mItems.length > 0) {
        resultGroups.push({ label: mLabel, items: mItems });
      }
    });

    return resultGroups;
  };

  const fetchChatsFromBackend = async () => {
    setHistoryLoading(true);
    try {
      const userParam = encodeURIComponent(currentUser || 'default_user');
      const res = await fetch(`${apiEndpoint}/api/chats?user_id=${userParam}&limit=1000`, {
        headers: { 'ngrok-skip-browser-warning': 'true' }
      });
      if (res.ok) {
        const data = await res.json();
        const sessions = Array.isArray(data.sessions) ? data.sessions : [];
        setChatHistory(sessions);
        try {
          localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(sessions));
        } catch (e) {}
      }
    } catch (err) {
      console.warn("Backend chat history fetch fallback to local cache:", err);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Live backend/connection/LLM status check.
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
        setActiveModel(statusData.provider_short || statusData.provider || 'AI Model');
        setActiveModelFull(statusData.llm?.full_name || statusData.provider || '');
        setConnections(statusData.connections || []);
        setSources(statusData.sources || []);
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

  // Check immediately on load and fetch chats from MySQL backend
  useEffect(() => {
    checkStatus(true);
    fetchChatsFromBackend();
    const interval = setInterval(() => checkStatus(false), STATUS_POLL_MS);
    return () => clearInterval(interval);
  }, [currentUser]);

  // `sourceOverride` lets a clarification chip re-send the same question pinned
  // to one data source, without changing the user's standing selection.
  // `historyOverride` lets edit/retry truncate or supply a specific message sequence.
  const handleSendMessage = async (textToSend, sourceOverride, historyOverride, chatIdOverride) => {
    const queryText = textToSend || inputValue;
    if (!queryText.trim()) return;
    const sourceForRequest = sourceOverride || selectedSource || 'auto';

    let chatId = chatIdOverride || currentChatId;
    const isNewChat = !chatId;
    if (isNewChat) {
      chatId = `chat-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setCurrentChatId(chatId);
    }

    const baseHistory = historyOverride !== undefined ? historyOverride : messages;
    const userMsg = { sender: 'user', text: queryText, timestamp: new Date().toISOString() };
    const updatedMessagesWithUser = [...baseHistory, userMsg];
    setMessages(updatedMessagesWithUser);
    setInputValue('');
    setQueryLoading(true);

    let sessionTitle = baseHistory.length > 0
      ? (chatHistory.find((c) => c.id === chatId)?.title || baseHistory[0].text || queryText)
      : queryText;
    let isPinnedState = false;

    // Save/update the session in chat history with user message
    setChatHistory((prev) => {
      const existing = prev.find((c) => c.id === chatId);
      let updated;
      const timestamp = new Date().toISOString();
      if (existing) {
        sessionTitle = existing.title;
        isPinnedState = existing.isPinned;
        const updatedChat = {
          ...existing,
          messages: updatedMessagesWithUser,
          timestamp
        };
        updated = [updatedChat, ...prev.filter((c) => c.id !== chatId)];
      } else {
        const newChat = {
          id: chatId,
          title: sessionTitle,
          messages: updatedMessagesWithUser,
          timestamp,
          isPinned: false
        };
        updated = [newChat, ...prev];
      }
      try {
        localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
      } catch (err) {
        console.error("Failed to store chat history:", err);
      }
      return updated;
    });

    // Save immediately to backend database
    saveSessionToBackend(chatId, sessionTitle, updatedMessagesWithUser, isPinnedState);

    try {
      const requestBody = {
        message: queryText,
        history: baseHistory,
        source: sourceForRequest
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
        source: result.source,
        // Machine-readable source id and badge: the id lets the backend keep
        // short follow-up turns on the same source, the badge drives styling.
        source_id: result.source_id,
        source_badge: result.source_badge,
        routing: result.routing,
        // Set when the router declined to guess between data sources.
        needs_clarification: result.needs_clarification,
        candidates: result.candidates,
        timestamp: new Date().toISOString()
      };

      const finalMessages = [...updatedMessagesWithUser, assistantMsg];
      setMessages(finalMessages);

      // Update session with assistant response
      setChatHistory((prev) => {
        const updated = prev.map((c) => {
          if (c.id === chatId) {
            return {
              ...c,
              messages: finalMessages,
              timestamp: new Date().toISOString()
            };
          }
          return c;
        });
        try {
          localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
        } catch (err) {
          console.error("Failed to store chat history:", err);
        }
        return updated;
      });

      // Save complete transcript to backend database
      saveSessionToBackend(chatId, sessionTitle, finalMessages, isPinnedState);

    } catch (error) {
      console.error("Chat Error:", error);
      const errorMsg = {
        sender: 'assistant',
        text: "Could not retrieve database data.",
        error: error.message,
        timestamp: new Date().toISOString()
      };
      const finalMessages = [...updatedMessagesWithUser, errorMsg];
      setMessages(finalMessages);

      setChatHistory((prev) => {
        const updated = prev.map((c) => {
          if (c.id === chatId) {
            return {
              ...c,
              messages: finalMessages,
              timestamp: new Date().toISOString()
            };
          }
          return c;
        });
        try {
          localStorage.setItem(getHistoryStorageKey(currentUser), JSON.stringify(updated));
        } catch (err) {
          console.error("Failed to store chat history:", err);
        }
        return updated;
      });

      saveSessionToBackend(chatId, sessionTitle, finalMessages, isPinnedState);
    } finally {
      setQueryLoading(false);
    }
  };

  const handleEditQuery = async (newText, msgIndex) => {
    if (queryLoading || !newText.trim()) return;
    const priorHistory = messages.slice(0, msgIndex);
    await handleSendMessage(newText, selectedSource, priorHistory, currentChatId);
  };

  const handleRetryQuery = async (msgIndex) => {
    if (queryLoading) return;
    const targetMsg = messages[msgIndex];
    if (!targetMsg || !targetMsg.text) return;
    const priorHistory = messages.slice(0, msgIndex);
    await handleSendMessage(targetMsg.text, selectedSource, priorHistory, currentChatId);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      handleSendMessage();
    }
  };

  const handleLogin = (userPayload) => {
    let username = '';
    let profile = null;

    if (typeof userPayload === 'object' && userPayload !== null) {
      username = userPayload.username || userPayload.userName || 'User';
      profile = userPayload;
    } else {
      username = String(userPayload || 'Guest');
      profile = {
        username: username,
        first_name: username,
        last_name: '',
        full_name: username,
        role: 'User'
      };
    }

    localStorage.setItem('__dce_current_user__', username);
    localStorage.setItem('__dce_user_profile__', JSON.stringify(profile));
    setCurrentUser(username);
    setUserProfile(profile);
    setCurrentChatId(null);
    setMessages([]);
    setChatHistory(loadSavedSessions(username));
    showToast(`Welcome, ${profile.first_name || username}!`);
  };

  const handleLogout = () => {
    localStorage.removeItem('__dce_current_user__');
    localStorage.removeItem('__dce_user_profile__');
    setCurrentUser(null);
    setUserProfile(null);
    setCurrentChatId(null);
    setMessages([]);
    setChatHistory([]);
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
    <div className="app-container" data-theme={darkMode ? 'dark' : 'light'}>
      {/* Left Sidebar — backend connections, model info, account */}
      <aside className={`app-sidebar ${sidebarOpen ? 'sidebar-expanded' : 'sidebar-collapsed'}`}>
        {sidebarOpen ? (
          <>
            <div className="sidebar-header-top">
              <span className="sidebar-header-label">Commercial Decision Intelligence</span>
              <button className="sidebar-toggle-btn" onClick={() => setSidebarOpen(false)} title="Collapse sidebar">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <line x1="9" y1="4" x2="9" y2="20" />
                </svg>
              </button>
            </div>

            <div className="sidebar-scroll">
              {/* Backend System Connections */}
              <div className="sidebar-section">
                <button
                  type="button"
                  className="sidebar-section-header system-status-header"
                  onClick={() => setSystemStatusOpen((prev) => !prev)}
                  aria-expanded={systemStatusOpen}
                  title={systemStatusOpen ? 'Collapse Connected System Status' : 'Expand Connected System Status'}
                >
                  <h4 className="sidebar-section-title">Connected System Status</h4>
                  <svg
                    className={`accordion-chevron ${systemStatusOpen ? 'open' : ''}`}
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>

                {systemStatusOpen && (
                  <div className="sidebar-section-content">
                    <div className="connection-row">
                      <span className="connection-dot" style={{ backgroundColor: statusColor, boxShadow: `0 0 6px ${statusColor}` }} />
                      <span className="connection-name">API Server</span>
                      <span className="connection-state" style={{ color: statusColor }}>{serverStatus}</span>
                    </div>

                    {connections.map((conn) => {
                      const dotColor = statusToColor(conn.status);
                      // Row shows the short name; the full descriptive name and
                      // any connection error go on hover.
                      const tip = [conn.label, conn.detail].filter(Boolean).join(' — ');
                      return (
                        <div className="connection-row" key={conn.id || conn.name} title={tip}>
                          <span className="connection-dot" style={{ backgroundColor: dotColor, boxShadow: `0 0 6px ${dotColor}` }} />
                          <span className="connection-name">{conn.name}</span>
                          <span className="connection-state" style={{ color: dotColor }}>{conn.status === 'connected' ? 'online' : conn.status}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* AI Model */}
              <div className="sidebar-section">
                <button
                  type="button"
                  className="sidebar-section-header system-status-header"
                  onClick={() => setModelStatusOpen((prev) => !prev)}
                  aria-expanded={modelStatusOpen}
                  title={modelStatusOpen ? 'Collapse Connected AI Model' : 'Expand Connected AI Model'}
                >
                  <h4 className="sidebar-section-title">Connected AI Model</h4>
                  <svg
                    className={`accordion-chevron ${modelStatusOpen ? 'open' : ''}`}
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>

                {modelStatusOpen && (
                  <div className="sidebar-section-content">
                    <div className="connection-row" title={activeModelFull || activeModel || ''}>
                      <span className="connection-dot" style={{ backgroundColor: llmColor, boxShadow: `0 0 6px ${llmColor}` }} />
                      <span className="connection-name">{activeModel || 'Detecting...'}</span>
                      <span className="connection-state" style={{ color: llmColor }}>{llmStatus === 'connected' ? 'online' : llmStatus}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* New Chat Action above Prompt History */}
              <div className="new-chat-container">
                <button
                  type="button"
                  className="new-chat-btn"
                  onClick={handleNewChat}
                  title="Start a new chat"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  <span>New Chat</span>
                </button>
              </div>

              {/* Chats History */}
              <div className="sidebar-section">
                <button
                  type="button"
                  className="sidebar-section-header system-status-header"
                  onClick={() => setPromptHistoryOpen((prev) => !prev)}
                  aria-expanded={promptHistoryOpen}
                  title={promptHistoryOpen ? 'Collapse Chats History' : 'Expand Chats History'}
                >
                  <div className="sidebar-title-with-badge">
                    <h4 className="sidebar-section-title">Chats History</h4>
                    {historyLoading ? (
                      <span className="history-count-badge grayout">Loading...</span>
                    ) : chatHistory.length > 0 && (
                      <span className="history-count-badge">{chatHistory.length}</span>
                    )}
                  </div>
                  <div className="sidebar-header-right">
                    <svg
                      className={`accordion-chevron ${promptHistoryOpen ? 'open' : ''}`}
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </div>
                </button>

                {promptHistoryOpen && (
                  <div className="sidebar-section-content history-accordion-content">
                    {historyLoading ? (
                      <div className="history-loading-placeholder">
                        <div className="history-prompt-item grayout disabled" title="Loading chat sessions...">
                          <svg className="history-item-icon history-spinner-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                          </svg>
                          <span className="history-prompt-text grayout-text">Loading...</span>
                        </div>
                        <div className="history-prompt-item grayout disabled" style={{ opacity: 0.4 }}>
                          <svg className="history-item-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                          </svg>
                          <span className="history-prompt-text grayout-text">Loading...</span>
                        </div>
                      </div>
                    ) : chatHistory.length === 0 ? (
                      <div className="history-empty">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="10" />
                          <polyline points="12 6 12 12 14 14" />
                        </svg>
                        <span>No prompt history yet</span>
                      </div>
                    ) : (
                      groupChatsByDate(chatHistory).map(({ label, items }) => (
                        <div key={label} className="history-date-group">
                          <div className="history-date-label">{label}</div>
                          <div className="history-items-list">
                            {items.map((session) => {
                              const isSessionLoading = selectingChatId === session.id;
                              const isDisabled = historyLoading || isSessionLoading || (selectingChatId !== null && selectingChatId !== session.id);
                              return (
                                <div
                                  key={session.id}
                                  className={`history-prompt-item ${currentChatId === session.id ? 'active' : ''} ${session.isPinned ? 'pinned' : ''} ${isDisabled ? 'grayout disabled' : ''}`}
                                  onClick={() => !isDisabled && handleSelectChat(session)}
                                  onContextMenu={(e) => !isDisabled && handleOpenContextMenu(e, session)}
                                  title={isSessionLoading ? 'Loading chat session...' : `${session.title}\n(${new Date(session.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})`}
                                >
                                  {isSessionLoading ? (
                                    <svg className="history-item-icon history-spinner-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                                    </svg>
                                  ) : (
                                    <svg className="history-item-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                                    </svg>
                                  )}
                                  
                                  {editingChatId === session.id ? (
                                    <input
                                      autoFocus
                                      className="history-rename-input"
                                      value={editingTitle}
                                      onChange={(e) => setEditingTitle(e.target.value)}
                                      onKeyDown={(e) => {
                                        if (e.key === 'Enter') handleSaveRename(session.id);
                                        if (e.key === 'Escape') setEditingChatId(null);
                                      }}
                                      onBlur={() => handleSaveRename(session.id)}
                                      onClick={(e) => e.stopPropagation()}
                                    />
                                  ) : (
                                    <span className={`history-prompt-text ${isSessionLoading ? 'grayout-text' : ''}`}>
                                      {isSessionLoading ? 'Loading...' : session.title}
                                    </span>
                                  )}

                                  <div className="history-item-actions">
                                    {session.isPinned && !isSessionLoading && (
                                      <svg className="history-item-pin-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" title="Pinned chat">
                                        <line x1="12" y1="17" x2="12" y2="22" />
                                        <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.8l-1.78.89A2 2 0 0 0 5 15.24Z" />
                                      </svg>
                                    )}

                                    {!isSessionLoading && (
                                      <button
                                        type="button"
                                        className="history-item-more-btn"
                                        onClick={(e) => handleOpenContextMenu(e, session)}
                                        title="More options"
                                      >
                                        •••
                                      </button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* SRM Logo */}
            <div className="sidebar-brand-bottom">
              <span className="sidebar-powered-by">Powered by</span>
              <img src={logoMain} alt="SRM Commercial Decision Intelligence Platform" className="sidebar-brand-logo" />
            </div>

            {/* Logged-in User */}
            <div className="sidebar-user">
              <div className="user-avatar">{((userProfile?.first_name || currentUser || 'U').charAt(0)).toUpperCase()}</div>
              <div className="user-meta">
                <span className="user-name" title={userProfile?.full_name || currentUser}>
                  {userProfile?.full_name || (userProfile?.first_name ? `${userProfile.first_name} ${userProfile.last_name || ''}`.trim() : currentUser)}
                </span>
                <span className="user-role" title={userProfile?.role || 'User'}>
                  {userProfile?.role ? `${userProfile.role} • @${currentUser}` : `@${currentUser}`}
                </span>
              </div>
              <button className="logout-icon-btn" onClick={handleLogout} title="Sign Out">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
              </button>
            </div>
          </>
        ) : (
          /* Collapsed Icon Rail matching screenshot */
          <div className="sidebar-rail-container">
            <div className="sidebar-rail-top">
              {/* Sidebar toggle / expand button */}
              <button
                type="button"
                className="sidebar-rail-btn"
                onClick={() => setSidebarOpen(true)}
                title="Expand sidebar"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="4" width="18" height="16" rx="2" />
                  <line x1="9" y1="4" x2="9" y2="20" />
                </svg>
              </button>

              {/* New Chat (Pencil/Edit in box) */}
              <button
                type="button"
                className="sidebar-rail-btn"
                onClick={handleNewChat}
                title="New chat"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
                </svg>
              </button>

              {/* Search / System Status */}
              <button
                type="button"
                className="sidebar-rail-btn"
                onClick={() => {
                  setSidebarOpen(true);
                  setSystemStatusOpen(true);
                }}
                title="Connected System Status"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
              </button>

              {/* Pin / Connected AI Model */}
              <button
                type="button"
                className="sidebar-rail-btn"
                onClick={() => {
                  setSidebarOpen(true);
                  setModelStatusOpen(true);
                }}
                title={`AI Model: ${activeModelFull || activeModel || 'Connected'} (${llmStatus})`}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="17" x2="12" y2="22" />
                  <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.8l-1.78.89A2 2 0 0 0 5 15.24Z" />
                </svg>
                <span className="rail-status-dot" style={{ backgroundColor: llmColor }} />
              </button>

              {/* Chats History */}
              <button
                type="button"
                className="sidebar-rail-btn"
                onClick={() => {
                  setSidebarOpen(true);
                  setPromptHistoryOpen(true);
                }}
                title={historyLoading ? "Loading Chats..." : "Chats History"}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
                {historyLoading ? (
                  <span className="rail-count-badge grayout">...</span>
                ) : chatHistory.length > 0 && (
                  <span className="rail-count-badge">{chatHistory.length}</span>
                )}
              </button>
            </div>

            <div className="sidebar-rail-bottom">
              {/* SRM Small Logo */}
              <div className="sidebar-rail-logo-box" onClick={() => setSidebarOpen(true)} title="SRM Commercial Decision Intelligence">
                <img src={logoSmall} alt="SRM Logo" className="sidebar-rail-logo" />
              </div>

              {/* User Avatar */}
              <div
                className="sidebar-rail-user"
                onClick={handleLogout}
                title={`Signed in as ${userProfile?.full_name || currentUser} (${userProfile?.role || 'User'}). Click to Sign Out.`}
              >
                <div className="user-avatar rail-avatar">{((userProfile?.first_name || currentUser || 'U').charAt(0)).toUpperCase()}</div>
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* Main Chat Workstation */}
      <div className="main-chat-area">

        {/* Messaging Box */}
        <div className="messages-container">
          {messages.length === 0 ? (
            <div className="empty-state-gemini">
              <h1 className="empty-state-greeting">
                What's on your mind {userProfile?.first_name || userProfile?.username || currentUser || ''}?
              </h1>

              {/* Central Pill Input Bar */}
              <div className="input-container pill-input hero-pill-input">
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Ask % of leakage, HCP fatigue..."
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyPress}
                  disabled={queryLoading}
                />

                <div className="input-right-actions">
                  <SourceSelector
                    sources={sources}
                    value={selectedSource}
                    onChange={setSelectedSource}
                    disabled={queryLoading}
                  />
                  {/* Dark Mode Toggle */}
                  <button
                    type="button"
                    className={`dark-mode-toggle-btn ${darkMode ? 'active' : ''}`}
                    onClick={() => {
                      const next = !darkMode;
                      setDarkMode(next);
                      localStorage.setItem('__dce_dark_mode__', String(next));
                    }}
                    title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                  >
                    {darkMode ? (
                      /* Sun icon */
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="5" />
                        <line x1="12" y1="1" x2="12" y2="3" />
                        <line x1="12" y1="21" x2="12" y2="23" />
                        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                        <line x1="1" y1="12" x2="3" y2="12" />
                        <line x1="21" y1="12" x2="23" y2="12" />
                        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                      </svg>
                    ) : (
                      /* Moon icon */
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                      </svg>
                    )}
                  </button>
                  <button
                    type="button"
                    className={`input-wave-btn ${inputValue.trim() ? 'has-text' : ''}`}
                    onClick={() => handleSendMessage()}
                    disabled={queryLoading || !inputValue.trim()}
                    title="Send prompt"
                  >
                    {inputValue.trim() ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="19" x2="12" y2="5" />
                        <polyline points="5 12 12 5 19 12" />
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="6" y1="9" x2="6" y2="15" />
                        <line x1="10" y1="6" x2="10" y2="18" />
                        <line x1="14" y1="4" x2="14" y2="20" />
                        <line x1="18" y1="8" x2="18" y2="16" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </div>
          ) : (
            messages.map((msg, index) => {
              let prevUserPrompt = null;
              if (msg.sender === 'assistant') {
                for (let i = index - 1; i >= 0; i--) {
                  if (messages[i].sender === 'user') {
                    prevUserPrompt = messages[i].text;
                    break;
                  }
                }
              }
              return (
                <MessageBubble
                  key={index}
                  index={index}
                  message={msg}
                  previousUserPrompt={prevUserPrompt}
                  onSelectSuggestion={(query) => handleSendMessage(query)}
                  // Re-ask the same question, pinned to the source the user picked.
                  onPickSource={(sourceId) =>
                    prevUserPrompt && handleSendMessage(prevUserPrompt, sourceId)
                  }
                  onEditQuery={handleEditQuery}
                  onRetryQuery={handleRetryQuery}
                  queryLoading={queryLoading}
                />
              );
            })
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

        {/* Message Input Workspace (when in active chat) */}
        {messages.length > 0 && (
          <div className="input-area">
            <div className="input-container pill-input">
              <input
                ref={inputRef}
                type="text"
                placeholder="Ask anything"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyPress}
                disabled={queryLoading}
              />

              <div className="input-right-actions">
                <SourceSelector
                  sources={sources}
                  value={selectedSource}
                  onChange={setSelectedSource}
                  disabled={queryLoading}
                />
                {/* Dark Mode Toggle */}
                <button
                  type="button"
                  className={`dark-mode-toggle-btn ${darkMode ? 'active' : ''}`}
                  onClick={() => {
                    const next = !darkMode;
                    setDarkMode(next);
                    localStorage.setItem('__dce_dark_mode__', String(next));
                  }}
                  title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
                >
                  {darkMode ? (
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="5" />
                      <line x1="12" y1="1" x2="12" y2="3" />
                      <line x1="12" y1="21" x2="12" y2="23" />
                      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                      <line x1="1" y1="12" x2="3" y2="12" />
                      <line x1="21" y1="12" x2="23" y2="12" />
                      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                    </svg>
                  )}
                </button>
                <button
                  type="button"
                  className={`input-wave-btn ${inputValue.trim() ? 'has-text' : ''}`}
                  onClick={() => handleSendMessage()}
                  disabled={queryLoading || !inputValue.trim()}
                  title="Send prompt"
                >
                  {inputValue.trim() ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="12" y1="19" x2="12" y2="5" />
                      <polyline points="5 12 12 5 19 12" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="6" y1="9" x2="6" y2="15" />
                      <line x1="10" y1="6" x2="10" y2="18" />
                      <line x1="14" y1="4" x2="14" y2="20" />
                      <line x1="18" y1="8" x2="18" y2="16" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Floating Chat Actions Context Menu */}
      {contextMenu.open && contextMenu.session && (
        <div
          className="chat-context-menu"
          style={{ top: `${contextMenu.y}px`, left: `${contextMenu.x}px` }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* 1. Share conversation */}
          <button
            type="button"
            className="context-menu-item"
            onClick={() => handleShare(contextMenu.session)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
              <polyline points="16 6 12 2 8 6" />
              <line x1="12" y1="2" x2="12" y2="15" />
            </svg>
            <span>Share conversation</span>
          </button>

          {/* 2. Pin */}
          <button
            type="button"
            className="context-menu-item"
            onClick={() => handleTogglePin(contextMenu.session)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="17" x2="12" y2="22" />
              <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.89A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.8l-1.78.89A2 2 0 0 0 5 15.24Z" />
            </svg>
            <span>{contextMenu.session.isPinned ? 'Unpin' : 'Pin'}</span>
          </button>

          {/* 3. Rename */}
          <button
            type="button"
            className="context-menu-item"
            onClick={() => handleStartRename(contextMenu.session)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9" />
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
            </svg>
            <span>Rename</span>
          </button>

          {/* 4. Delete */}
          <button
            type="button"
            className="context-menu-item delete"
            onClick={() => handleDeleteChat(contextMenu.session.id)}
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
            <span>Delete</span>
          </button>
        </div>
      )}

      {/* Toast Notification */}
      {toast && (
        <div className="global-toast-notification">
          {toast}
        </div>
      )}

    </div>
  );
}
