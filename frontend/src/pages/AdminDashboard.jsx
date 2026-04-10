import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStatsAPI, getUsersAPI, deleteUserAPI } from '../api/admin';
import '../assets/admin.css';

export default function AdminDashboard() {
  const user = JSON.parse(localStorage.getItem('user'));
  const navigate = useNavigate();
  
  const [stats, setStats] = useState({ users: 0, shops: 0, products: 0 });
  const [usersList, setUsersList] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
      if (!user || user.role !== 'admin') {
          navigate('/login');
          return;
      }
      loadDashboard();
  }, []);

  const loadDashboard = async () => {
      try {
          const s = await getStatsAPI();
          const u = await getUsersAPI();
          setStats(s);
          setUsersList(u);
      } catch (err) {
          console.error(err);
      }
      setLoading(false);
  };

  const handleLogout = () => {
      localStorage.removeItem('user');
      navigate('/login');
  };

  const handleDeleteUser = async (targetId) => {
      if (!window.confirm("WARNING: Are you absolutely sure you want to permanently delete this user and irrevocably cascade delete all their shops, products, and records?")) return;
      try {
          await deleteUserAPI(targetId);
          alert("Target eradicated.");
          loadDashboard();
      } catch (err) {
          alert(err.message);
      }
  };

  if(!user || user.role !== 'admin') return null;
  if(loading) return <div className="admin-layout"><h2>Establishing secure uplink...</h2></div>;

  return (
    <div className="admin-layout">
        <div className="admin-header">
            <div>
                <h1>Slopee Admin Domain</h1>
                <p style={{margin: 0, color: '#888', marginTop: '5px'}}>Macroscopic Overview & Control</p>
            </div>
            <div>
                <span style={{ marginRight: '20px', fontWeight: 'bold' }}>Session: {user.username.toUpperCase()}</span>
                <button onClick={handleLogout} className="admin-logout">Disengage Link</button>
            </div>
        </div>
        
        <div className="stats-grid">
            <div className="stat-card">
                <h3>Total Registered Population</h3>
                <p>{stats.users}</p>
            </div>
            <div className="stat-card">
                <h3>Total Active Shopfronts</h3>
                <p>{stats.shops}</p>
            </div>
            <div className="stat-card">
                <h3>Global Products Listed</h3>
                <p>{stats.products}</p>
            </div>
        </div>

        <div className="admin-table-container">
            <h2>User Registration Terminal</h2>
            <table className="admin-table">
                <thead>
                    <tr>
                        <th>Clearance</th>
                        <th>Identification</th>
                        <th>Email Protocol</th>
                        <th>Comms Line</th>
                        <th>Executive Action</th>
                    </tr>
                </thead>
                <tbody>
                    {usersList.map(u => (
                        <tr key={u.id}>
                            <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                            <td><strong>{u.name}</strong></td>
                            <td>{u.email}</td>
                            <td>{u.phone}</td>
                            <td>
                                {u.email !== '0' ? (
                                    <button onClick={() => handleDeleteUser(u.id)} className="btn-delete">ERADICATE USER</button>
                                ) : (
                                    <span style={{color: '#555', fontSize:'12px', fontWeight: 'bold'}}>SYSTEM PROTECTED</span>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    </div>
  );
}
