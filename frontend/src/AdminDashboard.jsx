import React, { useState, useEffect } from 'react';

function AdminDashboard({ token, handleLogout }) {
  const [adminReports, setAdminReports] = useState([]);
  const [error, setError] = useState('');
  const [selectedUserName, setSelectedUserName] = useState(() => localStorage.getItem('admin_selected_user_name') || '');
  const [selectedUserId, setSelectedUserId] = useState(() => localStorage.getItem('admin_selected_user_id') || '');

  useEffect(() => {
    fetchAdminReports();
  }, [token]);

  useEffect(() => {
    localStorage.setItem('admin_selected_user_name', selectedUserName);
  }, [selectedUserName]);

  useEffect(() => {
    localStorage.setItem('admin_selected_user_id', selectedUserId);
  }, [selectedUserId]);

  const fetchAdminReports = async () => {
    try {
      const response = await fetch('/api/admin/reports', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAdminReports(data);
      } else {
        if (response.status === 401 || response.status === 403) {
          handleLogout();
        } else {
          setError('Failed to fetch admin reports');
        }
      }
    } catch (err) {
      setError('Error connecting to server');
    }
  };

  return (
    <div className="card admin-panel" style={{ borderTop: '4px solid #e03131' }}>
      <h3>Admin Dashboard - System Reports</h3>
      <p>Viewing parsed logs from server storage.</p>

      <div style={{ display: 'grid', gap: '8px', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', margin: '16px 0', padding: '12px', background: '#f8f9fa', borderRadius: '8px', border: '1px solid #e9ecef' }}>
        <div style={{ gridColumn: '1 / -1', fontWeight: 600 }}>User context (saved locally)</div>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', textAlign: 'left' }}>
          <span style={{ fontSize: '0.9rem', color: '#495057' }}>Username</span>
          <input
            type="text"
            placeholder="e.g. Alice User"
            value={selectedUserName}
            onChange={(e) => setSelectedUserName(e.target.value)}
            style={{ width: '100%' }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', textAlign: 'left' }}>
          <span style={{ fontSize: '0.9rem', color: '#495057' }}>User ID</span>
          <input
            type="text"
            placeholder="e.g. 42"
            value={selectedUserId}
            onChange={(e) => setSelectedUserId(e.target.value)}
            style={{ width: '100%' }}
          />
        </label>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '0.9rem', color: '#495057' }}>These values are stored locally to help you tag or look up user-specific actions.</span>
          <button type="button" onClick={() => { setSelectedUserName(''); setSelectedUserId(''); }}>Clear</button>
        </div>
      </div>
      
      {error && <p style={{ color: 'red' }}>{error}</p>}

      {adminReports.length === 0 ? (
         <p>No reports available or no logs processed yet.</p>
      ) : (
         <div style={{ overflowX: 'auto' }}>
           <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
             <thead>
               <tr style={{ textAlign: 'left', borderBottom: '2px solid #ddd', background: '#f8f9fa' }}>
                 <th style={{ padding: '10px' }}>Status</th>
                 <th style={{ padding: '10px' }}>Log Content</th>
               </tr>
             </thead>
             <tbody>
               {adminReports.map((report, index) => (
                 <tr key={index} style={{ borderBottom: '1px solid #eee' }}>
                   <td style={{ padding: '10px', color: report.status === 'Danger' ? '#e03131' : '#2f9e44', fontWeight: 'bold' }}>
                     {report.status}
                   </td>
                   <td style={{ padding: '10px', fontFamily: 'monospace' }}>{report.content}</td>
                 </tr>
               ))}
             </tbody>
           </table>
         </div>
      )}
    </div>
  );
}

export default AdminDashboard;