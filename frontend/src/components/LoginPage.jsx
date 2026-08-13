import React, { useState } from 'react';

export default function LoginPage({ onLogin }) {
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    // No validation — any credentials are accepted.
    onLogin(userId || 'Guest');
  };

  return (
    <div className="login-screen">
      <div className="login-card">
        <h1>Pharma AI Agent</h1>
        <p className="login-subtitle">Sign in to access the AI data assistant</p>

        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <label htmlFor="login-userid">User ID</label>
            <input
              id="login-userid"
              type="text"
              placeholder="Enter any user ID"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              autoFocus
            />
          </div>

          <div className="login-field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              type="password"
              placeholder="Enter any password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button type="submit" className="login-submit-btn">
            Sign In
          </button>
        </form>
      </div>
    </div>
  );
}
