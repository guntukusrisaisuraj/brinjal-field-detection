import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast, Toaster } from 'react-hot-toast';
import { Leaf, Eye, EyeOff, User, Lock, Zap } from 'lucide-react';
import { useApp } from '../App';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useApp();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) { toast.error('Please enter your email'); return; }
    if (!password.trim()) { toast.error('Please enter your password'); return; }
    setLoading(true);
    await new Promise(r => setTimeout(r, 800)); // simulate auth
    login({ id: '1', email, name: email.split('@')[0] || 'User', role: 'user', created_at: new Date().toISOString() });
    toast.success('Welcome to AgriSense AI!');
    navigate('/home');
    setLoading(false);
  };

  const handleDemo = async () => {
    setLoading(true);
    await new Promise(r => setTimeout(r, 500));
    login({ id: 'demo', email: 'demo@agrisense.ai', name: 'Demo User', role: 'demo', created_at: new Date().toISOString() });
    toast.success('Entered demo mode');
    navigate('/home');
    setLoading(false);
  };

  return (
    <div className="login-page">
      <Toaster position="top-right" toastOptions={{
        style: { background: '#162035', color: '#F0F4FF', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '10px', fontSize: '13px' },
      }} />

      {/* Animated background */}
      <div className="login-bg" />
      <div style={{ position: 'absolute', inset: 0, backgroundImage: 'radial-gradient(circle at 1px 1px, rgba(124,58,237,0.06) 1px, transparent 0)', backgroundSize: '32px 32px' }} />

      <div className="login-card fade-in">
        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-icon"><Leaf size={24} color="#fff" /></div>
          <div>
            <div className="login-title">AgriSense AI</div>
            <div className="login-subtitle">Satellite-powered agriculture intelligence</div>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} autoComplete="on">
          <div className="form-group">
            <label className="form-label">Email address</label>
            <div style={{ position: 'relative' }}>
              <div style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--clr-text-dim)' }}>
                <User size={15} />
              </div>
              <input
                id="login-email"
                type="email"
                className="form-input"
                style={{ paddingLeft: 36 }}
                placeholder="you@example.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <div style={{ position: 'relative' }}>
              <div style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--clr-text-dim)' }}>
                <Lock size={15} />
              </div>
              <input
                id="login-password"
                type={showPw ? 'text' : 'password'}
                className="form-input"
                style={{ paddingLeft: 36, paddingRight: 36 }}
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                onClick={() => setShowPw(!showPw)}
                style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--clr-text-dim)', cursor: 'pointer' }}
              >
                {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-block btn-lg"
            disabled={loading}
            style={{ marginBottom: 10, marginTop: 4 }}
          >
            {loading ? <div className="spinner" /> : 'Sign In'}
          </button>
        </form>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '12px 0', color: 'var(--clr-text-dim)', fontSize: 12 }}>
          <div style={{ flex: 1, height: 1, background: 'var(--clr-glass-border)' }} />
          <span>or</span>
          <div style={{ flex: 1, height: 1, background: 'var(--clr-glass-border)' }} />
        </div>

        <button
          className="btn btn-ghost btn-block"
          onClick={handleDemo}
          disabled={loading}
          style={{ gap: 8 }}
        >
          <Zap size={15} color="var(--clr-amber)" />
          Continue in Demo Mode
        </button>

        <div className="alert alert-info" style={{ marginTop: 18, fontSize: 11 }}>
          <strong>Demo mode:</strong> All UI features are available. GEE/satellite analysis
          requires a configured backend with Earth Engine credentials.
        </div>

        {/* Features strip */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginTop: 20 }}>
          {[
            { icon: '🛰️', label: 'Sentinel-2 & Landsat' },
            { icon: '🌿', label: 'NDVI / EVI / NDWI' },
            { icon: '🤖', label: 'Random Forest AI' },
          ].map(f => (
            <div key={f.label} style={{ textAlign: 'center', padding: '10px 6px', background: 'var(--clr-glass)', borderRadius: 8, border: '1px solid var(--clr-glass-border)' }}>
              <div style={{ fontSize: 18, marginBottom: 4 }}>{f.icon}</div>
              <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', fontWeight: 600, lineHeight: 1.3 }}>{f.label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
