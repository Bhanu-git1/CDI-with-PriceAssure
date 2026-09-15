import React, { useState, useEffect, useRef } from 'react';
import logoMain from '../assets/SRM_logo.png';
import { getApiEndpoint } from '../utils/apiEndpoint';

const STANDARD_ROLES = [
  'Commercial Operations',
  'Sales Representative',
  'District Manager',
  'Brand Manager',
  'Data Analyst',
  'Executive / VP',
  'Administrator'
];

export default function LoginPage({ onLogin }) {
  const [activeTab, setActiveTab] = useState('signin'); // 'signin' | 'signup'
  
  // Sign In fields
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);

  // Sign Up fields
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [signupUsername, setSignupUsername] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [role, setRole] = useState('Commercial Operations');
  const [customRole, setCustomRole] = useState('');
  const [showSignupPassword, setShowSignupPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  // Validation & async status states
  const [usernameStatus, setUsernameStatus] = useState({ state: 'idle', message: '' }); // idle | checking | available | taken
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const apiEndpoint = getApiEndpoint();
  const usernameDebounceRef = useRef(null);

  // Real-time username availability check on debounce
  useEffect(() => {
    if (activeTab !== 'signup') return;
    
    const trimmedUser = signupUsername.trim();
    if (!trimmedUser) {
      setUsernameStatus({ state: 'idle', message: '' });
      return;
    }

    if (trimmedUser.length < 3) {
      setUsernameStatus({ state: 'invalid', message: 'Username must be at least 3 characters' });
      return;
    }

    setUsernameStatus({ state: 'checking', message: 'Checking availability...' });

    if (usernameDebounceRef.current) {
      clearTimeout(usernameDebounceRef.current);
    }

    usernameDebounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`${apiEndpoint}/api/auth/check-username?username=${encodeURIComponent(trimmedUser)}`, {
          headers: { 'ngrok-skip-browser-warning': 'true' }
        });
        if (res.ok) {
          const data = await res.json();
          if (data.exists) {
            setUsernameStatus({ state: 'taken', message: `Username '${trimmedUser}' is already taken. Please choose another.` });
          } else {
            setUsernameStatus({ state: 'available', message: `Username '${trimmedUser}' is available!` });
          }
        } else {
          setUsernameStatus({ state: 'idle', message: '' });
        }
      } catch (err) {
        console.warn('Failed to check username availability:', err);
        setUsernameStatus({ state: 'idle', message: '' });
      }
    }, 400);

    return () => {
      if (usernameDebounceRef.current) {
        clearTimeout(usernameDebounceRef.current);
      }
    };
  }, [signupUsername, activeTab, apiEndpoint]);

  // Clear messages on tab change
  const handleTabSwitch = (tab) => {
    setActiveTab(tab);
    setErrorMessage('');
    setSuccessMessage('');
  };

  // Sign In submit handler
  const handleSignInSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    if (!loginUsername.trim()) {
      setErrorMessage('Please enter your Username.');
      return;
    }
    if (!loginPassword) {
      setErrorMessage('Please enter your Password.');
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiEndpoint}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({
          username: loginUsername.trim(),
          password: loginPassword
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Invalid username or password.');
      }

      const userProfile = data.user || {
        username: loginUsername.trim(),
        firstName: loginUsername.trim(),
        lastName: '',
        role: 'User'
      };

      onLogin(userProfile);
    } catch (err) {
      setErrorMessage(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  // Sign Up / Registration submit handler
  const handleSignUpSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    const fName = firstName.trim();
    const lName = lastName.trim();
    const uName = signupUsername.trim();
    const finalRole = role === 'Other' ? customRole.trim() : role;

    // 1. Mandatory fields
    if (!fName) {
      setErrorMessage('Please enter your First Name.');
      return;
    }
    if (!lName) {
      setErrorMessage('Please enter your Last Name.');
      return;
    }
    if (!uName) {
      setErrorMessage('Please enter a Username.');
      return;
    }
    if (!finalRole) {
      setErrorMessage('Please select or specify a Role.');
      return;
    }
    if (!signupPassword) {
      setErrorMessage('Please enter a Password.');
      return;
    }
    if (signupPassword.length < 4) {
      setErrorMessage('Password must be at least 4 characters long.');
      return;
    }

    // 2. Check Password vs Confirm Password
    if (signupPassword !== confirmPassword) {
      setErrorMessage('Password and Confirm Password do not match. Please verify both fields.');
      return;
    }

    // 3. Check username availability state
    if (usernameStatus.state === 'taken') {
      setErrorMessage(`The username '${uName}' is already taken. Please choose a different username.`);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${apiEndpoint}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'ngrok-skip-browser-warning': 'true'
        },
        body: JSON.stringify({
          firstName: fName,
          lastName: lName,
          userName: uName,
          password: signupPassword,
          confirmPassword: confirmPassword,
          role: finalRole
        })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed. Please try again.');
      }

      setSuccessMessage('Account created successfully! Signing you in...');
      
      const userProfile = data.user || {
        username: uName,
        firstName: fName,
        lastName: lName,
        role: finalRole
      };

      setTimeout(() => {
        onLogin(userProfile);
      }, 800);

    } catch (err) {
      setErrorMessage(err.message || 'Registration failed. Please verify your details.');
    } finally {
      setLoading(false);
    }
  };

  const passwordsMatch = signupPassword && confirmPassword && signupPassword === confirmPassword;
  const passwordsMismatch = signupPassword && confirmPassword && signupPassword !== confirmPassword;

  return (
    <div className="login-screen">
      <div className={`login-card ${activeTab === 'signup' ? 'signup-mode' : ''}`}>
        
        {/* Brand Header */}
        <div className="login-header">
          <img src={logoMain} alt="SRM Commercial Decision Intelligence" className="login-logo" />
          <h1 className="login-title">Commercial Decision Intelligence</h1>
          <p className="login-subtitle">Pharma Command Centre & Dynamic Intelligence Assistant</p>
        </div>

        {/* Tab Navigation */}
        <div className="auth-tab-group">
          <button
            type="button"
            className={`auth-tab-btn ${activeTab === 'signin' ? 'active' : ''}`}
            onClick={() => handleTabSwitch('signin')}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab-btn ${activeTab === 'signup' ? 'active' : ''}`}
            onClick={() => handleTabSwitch('signup')}
          >
            Register / Sign Up
          </button>
        </div>

        {/* Error / Success Banners */}
        {errorMessage && (
          <div className="auth-alert error" role="alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{errorMessage}</span>
          </div>
        )}

        {successMessage && (
          <div className="auth-alert success" role="alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            <span>{successMessage}</span>
          </div>
        )}

        {/* SIGN IN FORM */}
        {activeTab === 'signin' && (
          <form onSubmit={handleSignInSubmit} className="login-form">
            <div className="login-field">
              <label htmlFor="signin-username">Username</label>
              <div className="input-wrapper">
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <input
                  id="signin-username"
                  type="text"
                  placeholder="Enter your username"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  autoFocus
                  required
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="signin-password">Password</label>
              <div className="input-wrapper">
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                <input
                  id="signin-password"
                  type={showLoginPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowLoginPassword(!showLoginPassword)}
                  title={showLoginPassword ? 'Hide password' : 'Show password'}
                >
                  {showLoginPassword ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <button type="submit" className="login-submit-btn" disabled={loading}>
              {loading ? (
                <span className="btn-loading-content">
                  <svg className="btn-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  Authenticating...
                </span>
              ) : (
                'Sign In'
              )}
            </button>

            <div className="auth-footer-prompt">
              Don't have an account?{' '}
              <button type="button" className="inline-link-btn" onClick={() => handleTabSwitch('signup')}>
                Create an account
              </button>
            </div>
          </form>
        )}

        {/* SIGN UP / REGISTRATION FORM */}
        {activeTab === 'signup' && (
          <form onSubmit={handleSignUpSubmit} className="login-form signup-grid-form">
            
            {/* Name Row: FirstName & LastName */}
            <div className="field-row">
              <div className="login-field">
                <label htmlFor="reg-firstname">First Name *</label>
                <div className="input-wrapper">
                  <input
                    id="reg-firstname"
                    type="text"
                    placeholder="e.g. John"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
              </div>

              <div className="login-field">
                <label htmlFor="reg-lastname">Last Name *</label>
                <div className="input-wrapper">
                  <input
                    id="reg-lastname"
                    type="text"
                    placeholder="e.g. Doe"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    required
                  />
                </div>
              </div>
            </div>

            {/* Username with Live Availability Check */}
            <div className="login-field">
              <div className="field-label-row">
                <label htmlFor="reg-username">Username *</label>
                {usernameStatus.message && (
                  <span className={`username-status-badge ${usernameStatus.state}`}>
                    {usernameStatus.state === 'checking' && '⏳ '}
                    {usernameStatus.state === 'available' && '✓ '}
                    {usernameStatus.state === 'taken' && '✕ '}
                    {usernameStatus.message}
                  </span>
                )}
              </div>
              <div className={`input-wrapper ${usernameStatus.state === 'taken' ? 'input-error' : usernameStatus.state === 'available' ? 'input-success' : ''}`}>
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <input
                  id="reg-username"
                  type="text"
                  placeholder="Choose unique username (e.g. jdoe)"
                  value={signupUsername}
                  onChange={(e) => setSignupUsername(e.target.value)}
                  required
                />
              </div>
            </div>

            {/* Role Selection */}
            <div className="login-field">
              <label htmlFor="reg-role">Role *</label>
              <div className="input-wrapper">
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="8.5" cy="7" r="4" />
                  <line x1="20" y1="8" x2="20" y2="14" />
                  <line x1="23" y1="11" x2="17" y2="11" />
                </svg>
                <select
                  id="reg-role"
                  className="auth-select"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  required
                >
                  {STANDARD_ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                  <option value="Other">Other (Custom Role...)</option>
                </select>
              </div>

              {role === 'Other' && (
                <div className="input-wrapper custom-role-wrapper">
                  <input
                    type="text"
                    placeholder="Enter custom role title"
                    value={customRole}
                    onChange={(e) => setCustomRole(e.target.value)}
                    required
                  />
                </div>
              )}
            </div>

            {/* Password Field */}
            <div className="login-field">
              <label htmlFor="reg-password">Password *</label>
              <div className="input-wrapper">
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                <input
                  id="reg-password"
                  type={showSignupPassword ? 'text' : 'password'}
                  placeholder="Create strong password"
                  value={signupPassword}
                  onChange={(e) => setSignupPassword(e.target.value)}
                  required
                  minLength={4}
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowSignupPassword(!showSignupPassword)}
                  title={showSignupPassword ? 'Hide password' : 'Show password'}
                >
                  {showSignupPassword ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Confirm Password Field */}
            <div className="login-field">
              <div className="field-label-row">
                <label htmlFor="reg-confirmpassword">Confirm Password *</label>
                {confirmPassword && (
                  <span className={`match-status-badge ${passwordsMatch ? 'match' : 'mismatch'}`}>
                    {passwordsMatch ? '✓ Passwords match' : '✕ Passwords do not match'}
                  </span>
                )}
              </div>
              <div className={`input-wrapper ${passwordsMismatch ? 'input-error' : passwordsMatch ? 'input-success' : ''}`}>
                <svg className="field-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                <input
                  id="reg-confirmpassword"
                  type={showConfirmPassword ? 'text' : 'password'}
                  placeholder="Re-enter password to confirm"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="password-toggle-btn"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  title={showConfirmPassword ? 'Hide password' : 'Show password'}
                >
                  {showConfirmPassword ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Submit Registration */}
            <button
              type="submit"
              className="login-submit-btn"
              disabled={loading || usernameStatus.state === 'taken' || passwordsMismatch}
            >
              {loading ? (
                <span className="btn-loading-content">
                  <svg className="btn-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  Creating User & Registering...
                </span>
              ) : (
                'Register & Access Workspace'
              )}
            </button>

            <div className="auth-footer-prompt">
              Already have an account?{' '}
              <button type="button" className="inline-link-btn" onClick={() => handleTabSwitch('signin')}>
                Sign in here
              </button>
            </div>
          </form>
        )}

      </div>
    </div>
  );
}
