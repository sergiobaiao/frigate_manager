import { NavLink, Route, Routes } from 'react-router-dom';
import DashboardPage from './pages/DashboardPage.jsx';
import HostsPage from './pages/HostsPage.jsx';
import SettingsPage from './pages/SettingsPage.jsx';
import HostDetailPage from './pages/HostDetailPage.jsx';

const App = () => (
  <div className="app-container">
    <aside className="sidebar">
      <h1>Frigate Monitor</h1>
      <nav>
        <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          Dashboard
        </NavLink>
        <NavLink to="/hosts" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          Hosts
        </NavLink>
        <NavLink to="/settings" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
          Configurações
        </NavLink>
      </nav>
    </aside>
    <main className="content">
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/hosts" element={<HostsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/hosts/:hostId" element={<HostDetailPage />} />
      </Routes>
    </main>
  </div>
);

export default App;
