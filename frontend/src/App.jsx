import React, { useState, useEffect } from 'react';
import Login from './Login';
import AdminDashboard from './AdminDashboard';
import UserDashboard from './UserDashboard';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [userName, setUserName] = useState(localStorage.getItem('name'));
  const [role, setRole] = useState(localStorage.getItem('role'));

  useEffect(() => {
    if (token) {
      setUserName(localStorage.getItem('name'));
      setRole(localStorage.getItem('role'));
    }
  }, [token]);

  const handleLogout = () => {
    setToken(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user_id');
    localStorage.removeItem('name');
    localStorage.removeItem('role');
  };

  if (!token) {
    return <Login setToken={setToken} />;
  }

  return (
    <div className="container">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>Welcome, {userName}! <span style={{fontSize: '0.6em', background: '#eee', padding: '2px 6px', borderRadius: '4px'}}>{role}</span></h1>
        <button onClick={handleLogout}>Logout</button>
      </header>
      
      {role === 'admin' ? (
        <AdminDashboard token={token} handleLogout={handleLogout} />
      ) : (
        <UserDashboard token={token} handleLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
