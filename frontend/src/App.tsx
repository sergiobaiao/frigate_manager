import { Link, Route, Routes, useLocation } from 'react-router-dom';

import DashboardPage from './pages/DashboardPage';
import HostDetailPage from './pages/HostDetailPage';
import HostsPage from './pages/HostsPage';
import SettingsPage from './pages/SettingsPage';

import './styles/layout.css';

const App = () => {
  const location = useLocation();

  return (
    <div className="app-container">
      <aside className="sidebar">
        <h1 className="logo">Frigate Manager</h1>
        <nav>
          <Link className={location.pathname === '/' ? 'active' : ''} to="/">
            Dashboard
          </Link>
          <Link className={location.pathname.startsWith('/hosts') ? 'active' : ''} to="/hosts">
            Hosts
          </Link>
          <Link className={location.pathname === '/settings' ? 'active' : ''} to="/settings">
            Settings
          </Link>
        </nav>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/hosts" element={<HostsPage />} />
          <Route path="/hosts/:id" element={<HostDetailPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
};

export default App;
