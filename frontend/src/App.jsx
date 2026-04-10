import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';

// Temporary Home Component for testing routing post-login
function Home() {
  const user = JSON.parse(localStorage.getItem('user'));
  return (
    <div style={{ padding: '20px', fontFamily: 'Arial' }}>
      <h1>Welcome to Slopee!</h1>
      {user ? (
          <div>
            <p>Logged in as: <strong>{user.username}</strong> (Role: {user.role})</p>
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
      </Routes>
    </BrowserRouter>
  );
}
