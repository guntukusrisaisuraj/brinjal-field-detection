import React, { useEffect, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  Home, MapPin, BarChart2, Satellite, User, Leaf,
  AlertTriangle, CheckCircle
} from 'lucide-react';
import { checkHealth } from '../../services/api';
import type { HealthStatus } from '../../types';

interface NavItem {
  to: string;
  icon: React.ReactNode;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/home',       icon: <Home size={18} />,      label: 'Home' },
  { to: '/locations',  icon: <MapPin size={18} />,     label: 'Farms' },
  { to: '/analysis',   icon: <BarChart2 size={18} />,  label: 'Analysis' },
  { to: '/satellite',  icon: <Satellite size={18} />,  label: 'Satellite' },
  { to: '/profile',    icon: <User size={18} />,       label: 'Profile' },
];

export default function Sidebar() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const location = useLocation();

  useEffect(() => {
    checkHealth()
      .then(setHealth)
      .catch(() => setHealth({
        status: 'error', gee_authenticated: false,
        version: '?', message: 'Backend not reachable'
      }));

    const interval = setInterval(() => {
      checkHealth().then(setHealth).catch(() => {});
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  const geeOk = health?.gee_authenticated ?? false;

  return (
    <nav className="app-sidebar" role="navigation" aria-label="Main navigation">
      {/* Logo */}
      <div className="sidebar-logo" title="AgriSense AI">
        <Leaf size={22} color="#fff" />
      </div>

      {/* Nav links */}
      <div className="sidebar-nav">
        {NAV_ITEMS.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `sidebar-item${isActive ? ' active' : ''}`
            }
            title={item.label}
          >
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>

      {/* Divider */}
      <div className="sidebar-divider" />

      {/* GEE status dot */}
      <div
        className={`sidebar-status${geeOk ? ' ok' : ''}`}
        title={
          health === null
            ? 'Connecting to backend...'
            : geeOk
            ? `GEE Connected — v${health.version}`
            : `GEE Not Authenticated — ${health.message}`
        }
      >
        {geeOk
          ? <CheckCircle size={8} style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)' }} />
          : null}
      </div>
    </nav>
  );
}
