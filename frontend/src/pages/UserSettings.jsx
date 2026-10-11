import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Navbar from '../components/Navbar';
import MyOrders from './MyOrders';
import { updateProfileAPI, updateUsernameAPI, updatePasswordAPI, requestDeletionAPI, fetchUserReviewsAPI } from '../api/auth';
import { getUser, updateStoredUser } from '../api/http';

export default function UserSettings() {
    const navigate = useNavigate();
    const [user, setUser] = useState(getUser());

    const [activeTab, setActiveTab] = useState('profile');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState({ text: '', type: '' });

    // Profile State
    const [bio, setBio] = useState('');
    const [newUsername, setNewUsername] = useState(user?.username || '');

    // Security State
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');

    // Deletion State
    const [deletePass, setDeletePass] = useState('');

    // Reviews State
    const [reviews, setReviews] = useState([]);

    useEffect(() => {
        if (!user) navigate('/login');
    }, [user]);

    const showMsg = (text, type = 'success') => {
        setMessage({ text, type });
        setTimeout(() => setMessage({ text: '', type: '' }), 4000);
    };

    const handleUpdateProfile = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await updateProfileAPI(bio);
            showMsg("Bio profile updated.");
        } catch (err) {
            showMsg(err.message, 'error');
        }
        setLoading(false);
    };

    const handleUpdateUsername = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await updateUsernameAPI(newUsername);
            // Must rewrite local session to prevent corruption
            const updatedUser = { ...user, username: newUsername };
            updateStoredUser(updatedUser);
            setUser(updatedUser);
            showMsg("Username changed.");
        } catch (err) {
            showMsg(err.message, 'error');
        }
        setLoading(false);
    };

    const handleUpdatePassword = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            await updatePasswordAPI(oldPassword, newPassword);
            showMsg("Password changed.");
            setOldPassword('');
            setNewPassword('');
        } catch (err) {
            showMsg(err.message, 'error');
        }
        setLoading(false);
    };

    const handleRequestDeletion = async (e) => {
        e.preventDefault();
        if (!window.confirm("WARNING: This action is irreversible. Are you sure?")) return;
        setLoading(true);
        try {
            await requestDeletionAPI(deletePass);
            showMsg("Deletion request sent.");
            setDeletePass('');
        } catch (err) {
            showMsg(err.message, 'error');
        }
        setLoading(false);
    };

    const fetchMyReviews = async () => {
        try {
            const data = await fetchUserReviewsAPI();
            setReviews(data.reviews);
        } catch (err) {
            showMsg("Failed to fetch reviews.", "error");
        }
    };

    useEffect(() => {
        if (activeTab === 'reviews') {
            fetchMyReviews();
        }
    }, [activeTab]);


    if (!user) return null;

    const navStyle = (tab) => ({
        padding: '15px 20px', cursor: 'pointer', borderBottom: '1px solid #eee',
        background: activeTab === tab ? '#ffeee8' : '#fff', color: activeTab === tab ? '#ee4d2d' : '#333',
        fontWeight: activeTab === tab ? 'bold' : 'normal'
    });

    return (
        <div style={{ background: '#f5f5f5', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
            <Navbar />

            <div style={{ maxWidth: '1200px', margin: '40px auto', display: 'flex', gap: '20px' }}>

                {/* SETTINGS SIDEBAR NAV */}
                <div style={{ width: '250px', background: '#fff', borderRadius: '4px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)', overflow: 'hidden', height: 'fit-content' }}>
                    <div style={{ padding: '20px', borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: '15px' }}>
                        <div style={{ width: '50px', height: '50px', borderRadius: '50%', background: '#ccc' }} />
                        <div>
                            <div style={{ fontWeight: 'bold', fontSize: '14px' }}>{user.name}</div>
                            <div style={{ fontSize: '12px', color: '#888' }}>@{user.username}</div>
                        </div>
                    </div>

                    <div onClick={() => setActiveTab('profile')} style={navStyle('profile')}>👤 Profile</div>
                    <div onClick={() => setActiveTab('security')} style={navStyle('security')}>🔒 Password</div>
                    <div onClick={() => setActiveTab('orders')} style={navStyle('orders')}>📦 Orders</div>
                    <div onClick={() => setActiveTab('reviews')} style={navStyle('reviews')}>⭐ Reviews</div>
                    <div onClick={() => setActiveTab('account')} style={navStyle('account')}>⚠️ Danger Zone</div>
                </div>

                {/* DYNAMIC CONTENT CANVAS */}
                <div style={{ flex: 1, background: '#fff', padding: '30px', borderRadius: '4px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}>
                    {message.text && (
                        <div style={{ padding: '15px', background: message.type === 'error' ? '#ffebee' : '#e8f5e9', color: message.type === 'error' ? '#c62828' : '#2e7d32', marginBottom: '20px', borderRadius: '4px', fontWeight: 'bold' }}>
                            {message.text}
                        </div>
                    )}

                    {activeTab === 'profile' && (
                        <div>
                            <h2>Profile Configuration</h2>
                            <form onSubmit={handleUpdateUsername} style={{ display: 'flex', gap: '10px', marginBottom: '40px', alignItems: 'flex-end' }}>
                                <div style={{ flex: 1 }}>
                                    <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', color: '#555' }}>Username</label>
                                    <input value={newUsername} onChange={e => setNewUsername(e.target.value)} required minLength={4} style={{ width: '100%', padding: '10px', border: '1px solid #ccc', borderRadius: '3px' }} />
                                </div>
                                <button disabled={loading} style={{ padding: '11px 25px', background: '#ee4d2d', color: '#fff', border: 'none', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold' }}>Update</button>
                            </form>

                            <form onSubmit={handleUpdateProfile} style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', color: '#555' }}>Bio</label>
                                    <textarea value={bio} onChange={e => setBio(e.target.value)} placeholder="Tell us about yourself..." style={{ width: '100%', padding: '10px', border: '1px solid #ccc', borderRadius: '3px', height: '100px', fontFamily: 'inherit' }} />
                                </div>
                                <button disabled={loading} style={{ padding: '12px', background: '#444', color: '#fff', border: 'none', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold', width: '200px' }}>Update Bio</button>
                            </form>
                        </div>
                    )}

                    {activeTab === 'security' && (
                        <div>
                            <h2>Change my password</h2>
                            <form onSubmit={handleUpdatePassword} style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '400px' }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', color: '#555' }}>Current Password</label>
                                    <input type="password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} required style={{ width: '100%', padding: '10px', border: '1px solid #ccc' }} />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: '8px', fontSize: '13px', color: '#555' }}>New Password</label>
                                    <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required minLength={4} style={{ width: '100%', padding: '10px', border: '1px solid #ccc' }} />
                                </div>
                                <button disabled={loading} style={{ padding: '12px', background: '#ee4d2d', color: '#fff', border: 'none', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold' }}>Update</button>
                            </form>
                        </div>
                    )}

                    {activeTab === 'orders' && (
                        <div style={{ marginTop: '-40px' }}>
                            <MyOrders hideNavbar={true} />
                        </div>
                    )}

                    {activeTab === 'reviews' && (
                        <div>
                            <h2>Past reviews</h2>
                            {reviews.length === 0 ? <p style={{ color: '#888' }}>You haven't posted any reviews yet.</p> : (
                                reviews.map(r => (
                                    <div key={r.id} style={{ borderBottom: '1px solid #eee', padding: '20px 0' }}>
                                        <div style={{ fontSize: '12px', color: '#888', marginBottom: '10px' }}>Item: <span onClick={() => navigate(`/product/${r.productId}`)} style={{ color: '#1565c0', cursor: 'pointer', fontWeight: 'bold' }}>{r.productName}</span></div>
                                        <div style={{ color: '#ee4d2d', fontSize: '14px', marginBottom: '8px' }}>{'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}</div>
                                        <p style={{ margin: 0, color: '#333', whiteSpace: 'pre-wrap' }}>{r.comment}</p>
                                        <div style={{ fontSize: '11px', color: '#aaa', marginTop: '10px' }}>{new Date(r.createdAt).toLocaleString()}</div>
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    {activeTab === 'account' && (
                        <div>
                            <h2 style={{ color: '#d32f2f' }}>Account Termination</h2>
                            <div style={{ background: '#ffebee', padding: '20px', borderRadius: '4px', borderLeft: '4px solid #c62828' }}>
                                <h4 style={{ margin: '0 0 10px 0', color: '#c62828' }}>Issue Account Termination</h4>
                                <p style={{ fontSize: '13px', color: '#666', marginBottom: '20px' }}>This will transmit a request to permanently delete your account. This action is irreversible.</p>

                                <form onSubmit={handleRequestDeletion} style={{ display: 'flex', gap: '15px', alignItems: 'flex-end' }}>
                                    <div>
                                        <input type="password" value={deletePass} onChange={e => setDeletePass(e.target.value)} placeholder="Authentication Verify" required style={{ padding: '10px', border: '1px solid #ccc', width: '250px' }} />
                                    </div>
                                    <button disabled={loading} style={{ padding: '11px 20px', background: '#c62828', color: '#fff', border: 'none', borderRadius: '3px', cursor: 'pointer', fontWeight: 'bold' }}>Send</button>
                                </form>
                            </div>
                        </div>
                    )}

                </div>
            </div>
        </div>
    );
}
