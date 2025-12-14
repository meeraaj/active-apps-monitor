import React, { useState, useEffect } from 'react';

function AdminDashboard({ token, handleLogout }) {
  const [adminReports, setAdminReports] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchAdminReports();
  }, [token]);

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