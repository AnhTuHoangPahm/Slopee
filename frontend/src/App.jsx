import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Home from './pages/Home';
import AdminDashboard from './pages/AdminDashboard';
import SellerDashboard from './pages/SellerDashboard';
import Cart from './pages/Cart';
import Checkout from './pages/Checkout';
import MyOrders from './pages/MyOrders';
import ProductView from './pages/ProductView';
import UserSettings from './pages/UserSettings';
import Tetris from './pages/Tetris';
import RequireRole from './components/RequireRole';
import { WalletProvider } from './hooks/useWallet';

export default function App() {
  return (
    <WalletProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/product/:id" element={<ProductView />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/admin" element={<RequireRole roles="admin"><AdminDashboard /></RequireRole>} />
          <Route path="/seller" element={<RequireRole roles="seller"><SellerDashboard /></RequireRole>} />
          <Route path="/cart" element={<RequireRole><Cart /></RequireRole>} />
          <Route path="/checkout" element={<RequireRole><Checkout /></RequireRole>} />
          <Route path="/orders" element={<RequireRole><MyOrders /></RequireRole>} />
          <Route path="/settings" element={<RequireRole><UserSettings /></RequireRole>} />
          <Route path="/play/tetris" element={<Tetris />} />
        </Routes>
      </BrowserRouter>
    </WalletProvider>
  );
}
