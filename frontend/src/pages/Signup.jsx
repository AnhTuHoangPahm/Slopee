import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { signupAPI } from '../api/auth';
import '../assets/auth.css';

export default function Signup() {
    const [formData, setFormData] = useState({
        role: 'user', name: '', email: '', phone: '', username: '', password: '', pass_phrase: ''
    });
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const handleChange = (e) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSignup = async (e) => {
        e.preventDefault();
        setError('');
        try {
            await signupAPI(formData);
            alert("Account created successfully! Please log in.");
            navigate('/login');
        } catch (err) {
            setError(err.message);
        }
    };

    return (
        <div className="auth-container">
            <div className="auth-card signup-card">
                <h2>Sign Up for Slopee</h2>
                {error && <div className="auth-error">{error}</div>}
                <form onSubmit={handleSignup}>
                    <div className="role-selector">
                        <label>
                            <input type="radio" name="role" value="user" checked={formData.role === 'user'} onChange={handleChange} /> Plain User
                        </label>
                        <label>
                            <input type="radio" name="role" value="seller" checked={formData.role === 'seller'} onChange={handleChange} /> Seller
                        </label>
                    </div>

                    <input type="text" name="name" placeholder="Full Name" value={formData.name} onChange={handleChange} required />
                    <input type="email" name="email" placeholder="Email" value={formData.email} onChange={handleChange} required />
                    <input type="text" name="phone" placeholder="Phone Number" value={formData.phone} onChange={handleChange} required />
                    <input type="text" name="username" placeholder="Username (min 4 chars)" value={formData.username} onChange={handleChange} required />
                    <input type="password" name="password" placeholder="Password" value={formData.password} onChange={handleChange} required />
                    <input type="password" name="pass_phrase" placeholder="6-Digit Payment Passphrase" maxLength="6" pattern="\d{6}" value={formData.pass_phrase} onChange={handleChange} required title="Must be exactly 6 numeric digits" />

                    <button type="submit" className="btn-primary">SIGN UP</button>
                </form>
                <div className="auth-footer">
                    Have an account? <Link to="/login">Log In</Link>
                </div>
            </div>
        </div>
    );
}
