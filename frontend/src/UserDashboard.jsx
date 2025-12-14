import React, { useState, useEffect } from 'react';

function UserDashboard({ token, handleLogout }) {
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchLogs();
  }, [token]);

  const fetchLogs = async () => {
    try {
      const response = await fetch('/api/logs', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setLogs(data);
      } else {
        if (response.status === 401) {
          handleLogout();
        } else {
          setError('Failed to fetch logs');
        }
      }
    } catch (err) {
      setError('Error connecting to server');
    }
  };

  return (
    <div className="card user-panel" style={{ borderTop: '4px solid #2f9e44' }}>
      <h3>Your Activity Logs</h3>
      
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {logs.length === 0 ? (
        <p>No logs found.</p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {logs.map((log) => (
            <li key={log.id} style={{ padding: '10px', borderBottom: '1px solid #eee' }}>
              <strong>{new Date(log.timestamp).toLocaleString()}</strong>
              <br />
              <span style={{ color: '#666', fontSize: '0.9em' }}>{log.log_file_url}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default UserDashboard;