import React, { useState } from 'react';

function Login({ setToken }) {
  const [isRegister, setIsRegister] = useState(false);
  const [loginType, setLoginType] = useState('user'); // 'user' | 'admin'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setMessage('');

    const endpoint = isRegister ? '/api/users' : '/api/login';
    const payload = isRegister ? { name, email, password } : { email, password };

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (response.ok) {
        if (isRegister) {
          setMessage('Registration successful! Please log in.');
          setIsRegister(false);
          setPassword(''); // Clear password for security
        } else {
          setToken(data.token);
          localStorage.setItem('token', data.token);
          localStorage.setItem('user_id', data.user_id);
          localStorage.setItem('name', data.name);
          localStorage.setItem('role', data.role);
        }
      } else {
        setError(data.error || 'Action failed');
      }
    } catch (err) {
      setError('Network error. Please try again.');
    }
  };

  return (
    <div className="form-container">
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <button
          type="button"
          onClick={() => { setLoginType('user'); setIsRegister(false); setError(''); setMessage(''); }}
          style={{
            flex: 1,
            background: loginType === 'user' ? '#4c6ef5' : '#e9ecef',
            color: loginType === 'user' ? '#fff' : '#000',
            border: '1px solid #ced4da'
          }}
        >
          User
        </button>
        <button
          type="button"
          onClick={() => { setLoginType('admin'); setIsRegister(false); setError(''); setMessage(''); }}
          style={{
            flex: 1,
            background: loginType === 'admin' ? '#e03131' : '#e9ecef',
            color: loginType === 'admin' ? '#fff' : '#000',
            border: '1px solid #ced4da'
          }}
        >
          Admin
        </button>
      </div>

      <h2>{isRegister ? 'Create Account' : loginType === 'admin' ? 'Admin Login' : 'User Login'}</h2>
      {error && <p style={{ color: '#ff6b6b', marginBottom: '1rem' }}>{error}</p>}
      {message && <p style={{ color: '#51cf66', marginBottom: '1rem' }}>{message}</p>}
      
      <form onSubmit={handleSubmit}>
        {isRegister && (
          <div>
            <input
              type="text"
              placeholder="Full Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
        )}
        <div>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button type="submit" style={{ width: '100%', marginTop: '10px' }}>
          {isRegister ? 'Sign Up' : 'Sign In'}
        </button>
      </form>

      <div style={{ marginTop: '1.5rem', fontSize: '0.9rem' }}>
        {isRegister ? 'Already have an account? ' : "Don't have an account? "}
        <button 
          onClick={() => {
            setIsRegister(!isRegister);
            setError('');
            setMessage('');
            setLoginType('user'); // registration is for users only
          }}
          style={{ 
            background: 'none', 
            border: 'none', 
            color: '#646cff', 
            textDecoration: 'underline', 
            cursor: 'pointer', 
            padding: 0,
            fontSize: 'inherit'
          }}
        >
          {isRegister ? 'Login here' : 'Register here'}
        </button>
      </div>
    </div>
  );
}

export default Login;
