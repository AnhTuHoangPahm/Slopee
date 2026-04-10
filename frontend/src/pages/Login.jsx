import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { loginAPI } from '../api/auth';
import '../assets/auth.css';

export default function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const handleLogin = async (e) => {
        e.preventDefault();
        setError('');
        try {
            const data = await loginAPI(username, password);
            localStorage.setItem('user', JSON.stringify(data.user));
            navigate('/');
        } catch (err) {
            setError(err.message);
        }
    };

    return (
        <div className="auth-container">
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
    );
}
