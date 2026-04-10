import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import '../assets/navbar.css';

export default function Navbar() {
    const navigate = useNavigate();
    const user = JSON.parse(localStorage.getItem('user'));
    const [searchTerm, setSearchTerm] = useState('');

    const handleSearchSubmit = (e) => {
        e.preventDefault();
        // Shift search queries globally into the URL so any page can execute a search and return home cleanly
        navigate(searchTerm ? `/?search=${encodeURIComponent(searchTerm)}` : '/');
    };

    const handleLogout = () => {
        localStorage.removeItem('user');
        navigate('/login');
    };

    const resetHome = () => {
        setSearchTerm('');
    };

    return (
        <header className="slopee-navbar">
            <div className="nav-container">
                <Link to="/" className="nav-logo" onClick={resetHome}>
                    Slopee
                </Link>
                
                <form className="nav-search" onSubmit={handleSearchSubmit}>
                    <input 
                        type="text" 
                        placeholder="Search for items, brands and shops..." 
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                    <button type="submit">🔍</button>
                </form>

                <div className="nav-links">
                    {user ? (
                        <>
                            <span>Hi, {user.name}</span>
                            <Link to="/cart" className="nav-icon">🛒 Cart (WIP)</Link>
                            
                            {user.role === 'seller' && (
                                <Link to="/seller" className="nav-seller-btn">Manage Shop</Link>
                            )}

                            <button onClick={handleLogout} className="nav-logout">Log Out</button>
                        </>
                    ) : (
                        <>
                            <Link to="/signup">Sign Up</Link>
                            <Link to="/login">Log In</Link>
                        </>
                    )}
                </div>
            </div>
        </header>
    );
}
