import React, { useState } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { loginAPI } from '../api/auth';
import { addToCartAPI } from '../api/carts';
import Navbar from '../components/Navbar';
import '../assets/auth.css';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const location = useLocation();

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        try {
            const data = await loginAPI(username, password);
            localStorage.setItem('user', JSON.stringify(data.user));
            
            // Re-fire Anonymous Cart Intents flawlessly before navigating!
            if (location.state?.pendingCartItem && data.user.role !== 'admin') {
                try {
                    await addToCartAPI(data.user.id, location.state.pendingCartItem, 1);
                } catch(err) { console.error('Intent execution failed:', err); }
            }

            if (data.user.role === 'admin') {
                navigate('/admin');
            } else {
                navigate('/');
            }
        } catch (err) {
            if (err.message.includes('Failed to fetch')) {
                setError('Network connection error: Server restarting or unreachable.');
            } else {
                setError(err.message);
            }
        }
    };

    return (
        <div style={{ backgroundColor: '#f5f5f5', minHeight: '100vh' }}>
            <Navbar />
            <div className="auth-container" style={{ minHeight: 'calc(100vh - 70px)' }}>
                <div className="auth-card">
                <h2>Log in to Slopee</h2>
                {error && <div className="auth-error">{error}</div>}
                <form onSubmit={handleLogin}>
                    <input 
                        type="text" 
                        placeholder="Username" 
                        value={username}
                        onChange={e => setUsername(e.target.value)}
                        required 
                    />
                    <input 
                        type="password" 
                        placeholder="Password" 
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        required 
                    />
                    <button type="submit" className="btn-primary">LOG IN</button>
                </form>
                <div className="auth-footer">
                    New to Slopee? <Link to="/signup">Sign Up</Link>
                </div>
            </div>
        </div>
        </div>
    );
}
