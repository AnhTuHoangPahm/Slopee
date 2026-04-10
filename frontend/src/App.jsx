import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import AdminDashboard from './pages/AdminDashboard';
import SellerDashboard from './pages/SellerDashboard';

// Temporary Home Component for testing routing post-login
function Home() {
  const user = JSON.parse(localStorage.getItem('user'));
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial' }}>
      <h1>Welcome to Slopee!</h1>
      {user ? (
          <div>
            <p>Logged in as: <strong>{user.username}</strong> (Role: {user.role})</p>
            {user.role === 'seller' && (
                <button onClick={() => window.location.href='/seller'} style={{ marginBottom: '10px', display: 'block', padding: '10px', background: '#ee4d2d', color: '#fff', border: 'none' }}>
                    Go To My Shop Dashboard
                </button>
            )}
            <button onClick={() => { localStorage.removeItem('user'); window.location.reload(); }}>Log out</button>
          </div>
      ) : (
          <p>You are not logged in. <a href="/login">Go to Login</a></p>
      )}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/seller" element={<SellerDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}
