import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

/**
 * Mount strategy:
 * 1. window.__SF_CHAT_MOUNT__ — element ref passed from Salesforce LWC (Shadow DOM safe)
 * 2. #sf-chat-root — fallback for direct DOM mounting
 * 3. #root — fallback for standalone dev mode
 */
function mount() {
  const rootElement =
    window.__SF_CHAT_MOUNT__ ||
    document.getElementById('sf-chat-root') ||
    document.getElementById('root');

  if (rootElement) {
    ReactDOM.createRoot(rootElement).render(
      <React.StrictMode>
        <App />
      </React.StrictMode>,
    );
  } else {
    console.warn('MCP Chat: No mount element found. Retrying in 500ms...');
    // In Salesforce, the LWC might still be creating the mount point
    setTimeout(mount, 500);
  }
}

mount();
