import React from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { User, LogOut, Shield, Star, Database } from 'lucide-react';
import { useApp } from '../App';

export default function ProfilePage() {
  const navigate = useNavigate();
  const { state, logout } = useApp();
  const { user, savedLocations } = state;

  const handleLogout = () => {
    logout();
    toast.success('Logged out');
    navigate('/login');
  };

  if (!user) {
    navigate('/login');
    return null;
  }

  return (
    <div className="page">
      <h1 className="page-title">Profile</h1>
      <p className="page-subtitle" style={{ marginBottom: 28 }}>Account overview and platform settings</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, maxWidth: 720 }}>
        {/* User card */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ width: 60, height: 60, borderRadius: '50%', background: 'linear-gradient(135deg, var(--clr-primary), var(--clr-accent))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <User size={28} color="#fff" />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--clr-text)', fontFamily: 'Outfit, sans-serif' }}>{user.name}</div>
              <div style={{ fontSize: 13, color: 'var(--clr-text-muted)' }}>{user.email}</div>
              <span className={`badge ${user.role === 'demo' ? 'badge-warning' : 'badge-primary'}`} style={{ marginTop: 6 }}>
                {user.role === 'demo' ? '⚡ Demo Mode' : user.role === 'admin' ? '👑 Admin' : '🌿 User'}
              </span>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="stat-card">
          <div className="stat-label">Saved Locations</div>
          <div className="stat-value">{savedLocations.length}</div>
          <div className="stat-sub">Farm / AOI entries</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Analyses Run</div>
          <div className="stat-value">{state.analyzeJobId ? 1 : 0}</div>
          <div className="stat-sub">This session</div>
        </div>

        {/* GEE status */}
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Database size={14} color="var(--clr-primary-light)" /> Platform Status
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { label: 'AgriSense AI', status: 'Running', ok: true },
              { label: 'FastAPI Backend', status: 'Connected', ok: true },
              { label: 'Google Earth Engine', status: 'Check /api/health', ok: null },
              { label: 'Planet Labs', status: 'Requires PLANET_API_KEY', ok: false },
            ].map(item => (
              <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--clr-glass-border)' }}>
                <div style={{ fontSize: 12, color: 'var(--clr-text-muted)' }}>{item.label}</div>
                <span className={`badge ${item.ok === true ? 'badge-success' : item.ok === null ? 'badge-dim' : 'badge-warning'}`}>
                  {item.status}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Logout */}
        <button className="btn btn-danger" style={{ gridColumn: '1 / -1' }} onClick={handleLogout}>
          <LogOut size={14} /> Sign Out
        </button>
      </div>

      <div className="disclaimer" style={{ marginTop: 20, maxWidth: 540 }}>
        <strong>AgriSense AI</strong> — Satellite-powered Agriculture Intelligence Platform.
        Backend: FastAPI + Google Earth Engine. Frontend: React + TypeScript + Vite.
        All satellite data is sourced from real GEE datasets. Planet integration requires a paid subscription.
      </div>
    </div>
  );
}
