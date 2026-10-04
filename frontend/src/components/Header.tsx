import React, { useEffect, useState } from 'react';
import { Satellite, AlertTriangle, CheckCircle, Leaf } from 'lucide-react';
import { checkHealth } from '../services/api';
import type { HealthStatus } from '../types';

export default function Header() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    checkHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'error', gee_authenticated: false, version: '?', message: 'Backend not reachable' }));

    const interval = setInterval(() => {
      checkHealth().then(setHealth).catch(() => {});
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  const geeOk = health?.gee_authenticated ?? false;

  return (
    <header className="header">
      {/* Logo + title */}
      <div className="header-logo">
        <div className="header-logo-icon">🌿</div>
        <div>
          <div className="header-title">AI-Based Brinjal Crop Detection – India</div>
          <div className="header-subtitle">Sentinel-2 · Google Earth Engine · Random Forest</div>
        </div>
      </div>

      {/* Centre: pipeline indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--clr-text-dim)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <Satellite size={12} /> Sentinel-2 SR
        </span>
        <span style={{ color: 'var(--clr-surface-3)' }}>→</span>
        <span>Cloud Mask</span>
        <span style={{ color: 'var(--clr-surface-3)' }}>→</span>
        <span>NDVI Filter</span>
        <span style={{ color: 'var(--clr-surface-3)' }}>→</span>
        <span>RF Classifier</span>
        <span style={{ color: 'var(--clr-surface-3)' }}>→</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--clr-primary-light)' }}>
          <Leaf size={12} /> Predicted Brinjal Map
        </span>
      </div>

      {/* GEE status */}
      <div className="header-status">
        <div className={`status-dot ${geeOk ? 'ok' : ''}`} />
        <span style={{ fontSize: 12, color: geeOk ? 'var(--clr-accent-light)' : 'var(--clr-error)', fontWeight: 500 }}>
          {health === null ? 'Connecting...' : geeOk ? 'GEE Connected' : 'GEE Not Auth'}
        </span>
        {!geeOk && health !== null && (
          <span title={health.message} style={{ cursor: 'help' }}>
            <AlertTriangle size={13} color="var(--clr-warning)" />
          </span>
        )}
        {geeOk && <CheckCircle size={13} color="var(--clr-success)" />}
        <span style={{ color: 'var(--clr-text-dim)', fontSize: 11, marginLeft: 4 }}>v{health?.version ?? '?'}</span>
      </div>
    </header>
  );
}
