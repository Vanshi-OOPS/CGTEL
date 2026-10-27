import { BrowserRouter, Routes, Route, NavLink, Link, Navigate, useLocation } from 'react-router';
import { useEffect, useState } from 'react';
import type { HealthResponse } from './api/types';
import { getHealth } from './api/client';
import { PatternDefs } from './components/PatternDefs';
import { Icon, type IconName } from './components/Icon';
import { DeskPage } from './pages/Desk';
import { OverviewPage } from './pages/Overview';
import { LedgerPage } from './pages/Ledger';
import { PolicyLabPage } from './pages/PolicyLab';
import { BenchmarkPage } from './pages/Benchmark';
import { ChatPage } from './pages/Chat';
import { DeskErrorBoundary } from './components/DeskErrorBoundary';
import './App.css';

import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/600.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';

type PageInfo = { path: string; label: string; title: string; description: string; icon: IconName; action: string; actionPath: string };
const pages: PageInfo[] = [
  { path: '/', label: 'Overview', title: 'Overview', description: 'Live posture from the latest run records.', icon: 'overview', action: 'Launch a test', actionPath: '/desk' },
  { path: '/desk', label: 'Desk', title: 'Execution desk', description: 'Submit an instruction and follow its gated tool run.', icon: 'desk', action: 'View overview', actionPath: '/' },
  { path: '/chat', label: 'Chat', title: 'Security assistant', description: 'Work with sandbox tools under CGTEL policy control.', icon: 'activity', action: 'Open Desk', actionPath: '/desk' },
  { path: '/ledger', label: 'Ledger', title: 'Audit ledger', description: 'Search and inspect recorded proposals, decisions, and outcomes.', icon: 'ledger', action: 'Open Desk', actionPath: '/desk' },
  { path: '/policy-lab', label: 'Policy Lab', title: 'Policy lab', description: 'Explore what-if risk scores with the server scoring model.', icon: 'policy', action: 'View benchmarks', actionPath: '/benchmarks' },
  { path: '/benchmarks', label: 'Benchmarks', title: 'Benchmarks', description: 'Evaluate the configured policy against the synthetic scenario suite.', icon: 'benchmark', action: 'Tune policy', actionPath: '/policy-lab' },
];

function AppLayout() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [connection, setConnection] = useState<'checking' | 'connected' | 'disconnected'>('checking');
  const location = useLocation();
  const page = pages.find((item) => item.path === location.pathname) ?? pages[0];

  useEffect(() => {
    let active = true;
    getHealth().then((response) => {
      if (!active) return;
      setHealth(response);
      setConnection(response.status === 'ok' ? 'connected' : 'disconnected');
    }).catch(() => {
      if (active) setConnection('disconnected');
    });
    return () => { active = false; };
  }, []);

  return (
    <div className="app-shell">
      <PatternDefs />
      <aside className="app-sidebar">
        <Link className="brand-lockup" to="/" aria-label="CGTEL Overview">
          <span className="brand-mark"><Icon name="shield" size={19} /></span>
          <span><b>CGTEL</b><small>TOOL CONTROL LAYER</small></span>
        </Link>
        <div className="sidebar-section-label">WORKSPACE</div>
        <nav className="sidebar-nav" aria-label="Main navigation">
          {pages.map((item) => <NavLink key={item.path} to={item.path} end={item.path === '/'} className={({ isActive }) => 'sidebar-link ' + (isActive ? 'sidebar-link--active' : '')}>
            <Icon name={item.icon} size={17} /><span>{item.label}</span>{item.path === '/' && <i className="sidebar-link__marker" aria-hidden="true" />}
          </NavLink>)}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-system">
          <div className="sidebar-system__heading"><span>SERVER STATUS</span><span className={'connection-dot connection-dot--' + connection} /></div>
          <strong>{connection === 'connected' ? 'API connected' : connection === 'checking' ? 'Connecting…' : 'API unavailable'}</strong>
          <small>{health ? (health.live_available ? 'LIVE AVAILABLE · ' + health.model : 'OFFLINE FALLBACK AVAILABLE') : 'CGTEL API · /api'}</small>
        </div>
        <div className="sidebar-footer"><Icon name="activity" size={14}/><span>Local security workspace</span></div>
      </aside>
      <div className="app-main-area">
        <header className="app-topbar">
          <div className="app-topbar__title"><span className="topbar-breadcrumb">CGTEL <i>/</i> WORKSPACE</span><h1>{page.title}</h1><p>{page.description}</p></div>
          <div className="app-topbar__actions">
            {health && <span className={'mode-indicator ' + (health.mode_default === 'live' ? 'mode-indicator--live' : 'mode-indicator--offline')}><i/> {health.mode_default === 'live' ? 'LIVE DEFAULT' : 'OFFLINE DEFAULT'}</span>}
            <Link className="topbar-action" to={page.actionPath}>{page.action}<Icon name="arrow" size={15}/></Link>
          </div>
        </header>
        <main className="app-content">
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/overview" element={<Navigate to="/" replace />} />
            <Route path="/desk" element={<DeskErrorBoundary><DeskPage /></DeskErrorBoundary>} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/ledger" element={<LedgerPage />} />
            <Route path="/policy-lab" element={<PolicyLabPage />} />
            <Route path="/benchmarks" element={<BenchmarkPage />} />
            <Route path="/benchmark" element={<Navigate to="/benchmarks" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function App() {
  return <BrowserRouter><AppLayout /></BrowserRouter>;
}

export default App;
