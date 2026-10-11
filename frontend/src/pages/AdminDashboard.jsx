import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getStatsAPI, getUsersAPI, deleteUserAPI, fetchAdminCategoriesAPI, addCategoryAPI, updateCategoryAPI, deleteCategoryAPI } from '../api/admin';
import '../assets/admin.css';
import { getUser, clearSession } from '../api/http';

export default function AdminDashboard() {
    const user = getUser();
    const navigate = useNavigate();

    const [stats, setStats] = useState({ users: 0, shops: 0, products: 0 });
    const [usersList, setUsersList] = useState([]);
    const [categories, setCategories] = useState([]);
    const [loading, setLoading] = useState(true);

    // Feature I: Phase 2 Filters
    const [userSearchTerm, setUserSearchTerm] = useState('');
    const [userRoleFilter, setUserRoleFilter] = useState('all');
    const [newCatName, setNewCatName] = useState('');

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
            const c = await fetchAdminCategoriesAPI();
            setStats(s);
            setUsersList(u);
            setCategories(c.categories);
        } catch (err) {
            console.error(err);
        }
        setLoading(false);
    };

    const handleLogout = () => {
        clearSession();
        navigate('/');
    };

    const handleApproveDeletion = async (targetId) => {
        if (!window.confirm("WARNING: Delete this account and their inventory?")) return;
        try {
            await deleteUserAPI(targetId);
            alert("Account successfully deleted.");
            loadDashboard();
        } catch (err) {
            alert(err.message);
        }
    };

    const handleAddCategory = async (e) => {
        e.preventDefault();
        try {
            await addCategoryAPI(newCatName);
            setNewCatName('');
            loadDashboard();
        } catch (err) { alert(err.message); }
    };

    const handleEditCategory = async (catId, currentName) => {
        const renamed = window.prompt("Rename Category:", currentName);
        if (!renamed || renamed.trim() === currentName) return;
        try {
            await updateCategoryAPI(catId, renamed);
            loadDashboard();
        } catch (err) { alert(err.message); }
    };

    const handleDeleteCategory = async (catId) => {
        if (!window.confirm("Delete this category? Can't do unless no products are bound to it.")) return;
        try {
            await deleteCategoryAPI(catId);
            loadDashboard();
        } catch (err) { alert(err.message); }
    };

    const filteredUsers = usersList.filter(u => {
        const matchRole = userRoleFilter === 'all' || u.role === userRoleFilter;
        const matchSearch = String(u.name).toLowerCase().includes(userSearchTerm.toLowerCase()) ||
            String(u.email).toLowerCase().includes(userSearchTerm.toLowerCase());
        return matchRole && matchSearch;
    });

    if (!user || user.role !== 'admin') return null;
    if (loading) return <div className="admin-layout"><h2>Establishing secure uplink...</h2></div>;

    return (
        <div className="admin-layout">
            <div className="admin-header">
                <div>
                    <h1>Slopee Admin Dashboard</h1>
                    <p style={{ margin: 0, color: '#888', marginTop: '5px' }}>Overview & Manage</p>
                </div>
                <div>
                    <span style={{ marginRight: '20px', fontWeight: 'bold' }}>Session: {user.username.toUpperCase()}</span>
                    <button onClick={handleLogout} className="admin-logout">Logout</button>
                </div>
            </div>

            <div className="stats-grid">
                <div className="stat-card">
                    <h3>Total Registered Accounts</h3>
                    <p>{stats.users - 1}</p>
                </div>
                <div className="stat-card">
                    <h3>Total Shops</h3>
                    <p>{stats.shops}</p>
                </div>
                <div className="stat-card">
                    <h3>Total Products Listed</h3>
                    <p>{stats.products}</p>
                </div>
            </div>

            <div className="admin-table-container">
                <h2>Requested Account Wipe</h2>
                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>Role</th>
                            <th>Identification</th>
                            <th>Request Date</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {usersList.filter(u => u.deletionRequestedAt !== null).map(u => (
                            <tr key={u.id}>
                                <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                                <td><strong>{u.name}</strong><br /><span style={{ fontSize: '12px', color: '#777' }}>{u.email}</span></td>
                                <td style={{ color: '#d32f2f', fontWeight: 'bold' }}>{new Date(u.deletionRequestedAt).toLocaleString()}</td>
                                <td>
                                    <button onClick={() => handleApproveDeletion(u.id)} className="btn-delete" style={{ background: '#c62828' }}>APPROVE TERMINATION</button>
                                </td>
                            </tr>
                        ))}
                        {usersList.filter(u => u.deletionRequestedAt !== null).length === 0 && (
                            <tr><td colSpan="4" style={{ textAlign: 'center', padding: '20px', color: '#777' }}>No termination requests.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            <div className="admin-table-container">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                    <h2 style={{ margin: 0 }}>User Accounts Management</h2>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <input type="text" placeholder="Search Names or Emails" value={userSearchTerm} onChange={e => setUserSearchTerm(e.target.value)} style={{ padding: '8px', border: '1px solid #ccc', borderRadius: '4px', width: '250px' }} />
                        <select value={userRoleFilter} onChange={e => setUserRoleFilter(e.target.value)} style={{ padding: '8px', border: '1px solid #ccc', borderRadius: '4px' }}>
                            <option value="all">All Role</option>
                            {/* <option value="admin">Admin</option> */}
                            <option value="seller">Seller</option>
                            <option value="user">User</option>
                        </select>
                    </div>
                </div>

                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>Role</th>
                            <th>Full Name</th>
                            <th>Email</th>
                            <th>Contact</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filteredUsers
                            .filter(u => u.role !== 'admin')
                            .map(u => (
                                <tr key={u.id}>
                                    <td><span className={`role-badge role-${u.role}`}>{u.role}</span></td>
                                    <td><strong>{u.name}</strong></td>
                                    <td>{u.email}</td>
                                    <td>{u.phone}</td>
                                </tr>
                            ))}
                        {filteredUsers.length === 0 && (
                            <tr><td colSpan="4" style={{ textAlign: 'center', padding: '20px', color: '#777' }}>No users found.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            <div className="admin-table-container" style={{ marginBottom: '40px' }}>
                <h2>Categories Management</h2>
                <form onSubmit={handleAddCategory} style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
                    <input required placeholder="New Taxonomy Branch..." value={newCatName} onChange={e => setNewCatName(e.target.value)} style={{ flex: 1, padding: '10px', fontSize: '15px', border: '1px solid #ccc' }} />
                    <button type="submit" style={{ padding: '10px 20px', background: '#333', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 'bold' }}>Create</button>
                </form>
                <table className="admin-table">
                    <thead>
                        <tr>
                            <th>Global ID</th>
                            <th>Name</th>
                            <th style={{ textAlign: 'center' }}>Number of Products</th>
                            <th style={{ textAlign: 'right' }}>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {categories.map(c => (
                            <tr key={c.id}>
                                <td style={{ color: '#888' }}>#{c.id}</td>
                                <td><strong>{c.name}</strong></td>
                                <td style={{ textAlign: 'center', fontWeight: 'bold', color: c.productCount > 0 ? '#4caf50' : '#888' }}>{c.productCount} Items</td>
                                <td style={{ textAlign: 'right' }}>
                                    <button onClick={() => handleEditCategory(c.id, c.name)} style={{ padding: '5px 10px', background: '#f5f5f5', border: '1px solid #ccc', cursor: 'pointer', marginRight: '5px' }}>Rename</button>
                                    <button onClick={() => handleDeleteCategory(c.id)} style={{ padding: '5px 10px', background: '#c62828', color: '#fff', border: 'none', cursor: 'pointer' }}>Take down</button>
                                </td>
                            </tr>
                        ))}
                        {categories.length === 0 && (
                            <tr><td colSpan="4" style={{ textAlign: 'center', padding: '20px', color: '#777' }}>No categories.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
