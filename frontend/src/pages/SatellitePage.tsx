import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import { Satellite, CheckCircle, XCircle, AlertTriangle, RefreshCw, ExternalLink, Info } from 'lucide-react';
import { useApp } from '../App';
import { getSatelliteSources, checkPlanetAccess, getAlphaEarthEmbedding } from '../services/api';
import type { SatelliteSource, SatelliteSourceId, AlphaEarthResult } from '../types';

// ─── Satellite icon map ────────────────────────────────────
const SAT_ICONS: Record<string, string> = {
  sentinel2:  '🛰️',
  landsat:    '🌍',
  planet:     '🔭',
  alphaearth: '🧠',
};

const SAT_GRADIENTS: Record<string, string> = {
  sentinel2:  'linear-gradient(135deg, #1a3a5c, #2563eb)',
  landsat:    'linear-gradient(135deg, #1a4a2e, #16a34a)',
  planet:     'linear-gradient(135deg, #3a1a1a, #dc2626)',
  alphaearth: 'linear-gradient(135deg, #2a1a4a, #7c3aed)',
};

// ─── Credential badge ──────────────────────────────────────
function CredBadge({ configured }: { configured: boolean }) {
  return configured ? (
    <span className="badge badge-success"><CheckCircle size={9} /> Configured</span>
  ) : (
    <span className="badge badge-warning"><AlertTriangle size={9} /> Requires Credentials</span>
  );
}

// ─── AlphaEarth detail panel ───────────────────────────────
function AlphaEarthPanel({ aoi }: { aoi: { latitude: number; longitude: number; radius_km: number } }) {
  const [result, setResult] = useState<AlphaEarthResult | null>(null);
  const [loading, setLoading] = useState(false);

  const fetch = async () => {
    setLoading(true);
    try {
      const res = await getAlphaEarthEmbedding({
        aoi: { latitude: aoi.latitude, longitude: aoi.longitude, radius_km: aoi.radius_km },
        date_from: '2023-01-01',
        date_to: '2023-12-31',
      });
      setResult(res);
    } catch (err: any) {
      toast.error(err.response?.data?.detail ?? 'AlphaEarth request failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--clr-text)' }}>
          🧠 AlphaEarth Embedding
        </div>
        <button className="btn btn-ghost btn-sm" onClick={fetch} disabled={loading}>
          {loading ? <div className="spinner" style={{ width: 12, height: 12 }} /> : <RefreshCw size={12} />}
          {loading ? 'Fetching...' : 'Fetch'}
        </button>
      </div>

      {!result && !loading && (
        <div style={{ fontSize: 12, color: 'var(--clr-text-dim)', lineHeight: 1.6 }}>
          Click <strong>Fetch</strong> to request 64-dimensional satellite embeddings
          for the current AOI from the <code style={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}>
          GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL</code> dataset.
          Requires GEE credentials and dataset allowlisting.
        </div>
      )}

      {result && (
        <div className="fade-in">
          {result.error ? (
            <div className="alert alert-warning" style={{ fontSize: 11 }}>
              <strong>Not accessible:</strong> {result.error}
              <br /><br />
              <a href="https://earthengine.google.com/noncommercial/" target="_blank" rel="noreferrer"
                style={{ color: 'var(--clr-blue-light)', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                Request access <ExternalLink size={10} />
              </a>
            </div>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
                <div className="stat-card">
                  <div className="stat-label">Resolution</div>
                  <div className="stat-value">{result.resolution_m}<span className="stat-unit">m</span></div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Embedding Dims</div>
                  <div className="stat-value">{result.embedding_dims}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Annual Year</div>
                  <div className="stat-value" style={{ fontSize: 16 }}>{result.year}</div>
                </div>
              </div>

              <div className="notice notice-muted" style={{ marginBottom: 10 }}>
                {result.source}: annual period {result.annual_period_start} to {result.annual_period_end}.
                The requested range selects a full annual embedding; it does not represent ordinary date-by-date imagery.
                <br />{result.visualization_available ? result.visualization_label : result.visualization_message}
              </div>

              <div className="disclaimer">
                <strong>⚠ Research feature.</strong> AlphaEarth embeddings are dense representations
                of satellite imagery, not raw spectral bands. They are suitable for downstream
                classification and change detection tasks.
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────
export default function SatellitePage() {
  const { state, updateParam } = useApp();
  const [sources, setSources] = useState<SatelliteSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<SatelliteSourceId>('sentinel2');
  const [planetStatus, setPlanetStatus] = useState<any>(null);
  const [checkingPlanet, setCheckingPlanet] = useState(false);

  const loadSources = async () => {
    setLoading(true);
    try {
      const { sources: s } = await getSatelliteSources();
      setSources(s);
    } catch {
      toast.error('Could not fetch satellite source info');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSources(); }, []);

  const handlePlanetCheck = async () => {
    setCheckingPlanet(true);
    try {
      const res = await checkPlanetAccess();
      setPlanetStatus(res);
      if (res.valid) toast.success('Planet API key is valid!');
      else toast.error(res.error ?? 'Planet key invalid');
    } catch {
      toast.error('Planet check failed');
    } finally {
      setCheckingPlanet(false);
    }
  };

  const selectedSource = sources.find(s => s.id === selected);

  return (
    <div className="page" style={{ maxWidth: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <h1 className="page-title">Satellite Intelligence</h1>
          <p className="page-subtitle">Select a data source and explore coverage, specs, and AI embeddings</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={loadSources} disabled={loading}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <div className="spinner spinner-lg" />
        </div>
      )}

      {/* Source cards grid */}
      {!loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 32 }}>
          {sources.map(src => (
            <div
              key={src.id}
              className={`sat-card${selected === src.id ? ' active' : ''}${!src.available ? ' unavailable' : ''}`}
              onClick={() => src.available && setSelected(src.id as SatelliteSourceId)}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && src.available && setSelected(src.id as SatelliteSourceId)}
              id={`sat-card-${src.id}`}
            >
              <div className="sat-card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div className="sat-card-icon" style={{ background: SAT_GRADIENTS[src.id] }}>
                    {SAT_ICONS[src.id]}
                  </div>
                  <div>
                    <div className="sat-card-name">{src.name}</div>
                    <div className="sat-card-agency">{src.agency}</div>
                  </div>
                </div>
                {selected === src.id && <CheckCircle size={18} color="var(--clr-primary-light)" />}
              </div>

              <p style={{ fontSize: 11, color: 'var(--clr-text-dim)', lineHeight: 1.6, marginBottom: 12 }}>
                {src.description}
              </p>

              <div className="sat-specs">
                <div className="sat-spec">
                  <div className="sat-spec-label">Resolution</div>
                  <div className="sat-spec-value">{src.resolution_m}m</div>
                </div>
                <div className="sat-spec">
                  <div className="sat-spec-label">{src.id === 'alphaearth' ? 'Embed Dims' : 'Bands'}</div>
                  <div className="sat-spec-value">{src.bands}</div>
                </div>
                <div className="sat-spec">
                  <div className="sat-spec-label">Revisit</div>
                  <div className="sat-spec-value">{src.revisit_days}d</div>
                </div>
                <div className="sat-spec">
                  <div className="sat-spec-label">Status</div>
                  <div className="sat-spec-value" style={{ fontSize: 11 }}>
                    {src.available ? '✓ Ready' : '⚠ Locked'}
                  </div>
                </div>
              </div>

              {/* Credential note */}
              <div style={{ marginTop: 8 }}>
                <CredBadge configured={src.credential_configured} />
                {src.credential_note && (
                  <div style={{ fontSize: 10, color: 'var(--clr-amber)', marginTop: 6, lineHeight: 1.5 }}>
                    {src.credential_note}
                  </div>
                )}
              </div>

              {/* Indices */}
              {src.indices && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 10 }}>
                  {src.indices.map(idx => (
                    <span key={idx} className="badge badge-dim" style={{ fontSize: 9 }}>{idx}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Detail panel for selected source */}
      {selectedSource && (
        <div className="fade-in" style={{ maxWidth: 900 }}>
          <div style={{ fontFamily: 'Outfit, sans-serif', fontSize: 18, fontWeight: 700, color: 'var(--clr-text)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 10 }}>
            {SAT_ICONS[selectedSource.id]} {selectedSource.name} — Details
          </div>

          {/* Sentinel-2 */}
          {selected === 'sentinel2' && (
            <div className="card">
              <div className="alert alert-success" style={{ fontSize: 12 }}>
                ✅ Sentinel-2 is the <strong>primary data source</strong> for this platform.
                All NDVI, EVI, NDWI, SAVI, NDRE, NDBI computation and brinjal classification runs on Sentinel-2.
                Use the <strong>Analysis</strong> page to run the full pipeline.
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginTop: 12 }}>
                {[
                  { label: 'Collection', value: 'COPERNICUS/S2_SR_HARMONIZED' },
                  { label: 'Cloud mask', value: 'QA60 + SCL' },
                  { label: 'Red-edge bands', value: 'B5, B6, B7, B8A' },
                  { label: 'NDRE support', value: '✓ Yes' },
                  { label: 'Min resolution', value: '10m (visible/NIR)' },
                  { label: 'Archive from', value: '2015' },
                ].map(r => (
                  <div key={r.label} className="stat-card" style={{ padding: '10px 12px' }}>
                    <div className="stat-label">{r.label}</div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--clr-text)', fontFamily: 'JetBrains Mono, monospace', wordBreak: 'break-all' }}>{r.value}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Landsat */}
          {selected === 'landsat' && (
            <div className="card">
              <div className="alert alert-info" style={{ fontSize: 12 }}>
                Landsat 8/9 provides 30m resolution imagery with a 50+ year archive (1972–present).
                Use for <strong>historical change detection</strong> and longer-term trend analysis.
                Use the Analysis page with the Landsat endpoint to run NDVI/EVI/NDWI/SAVI/NDBI.
              </div>
              <div className="disclaimer" style={{ marginTop: 12 }}>
                <strong>Note:</strong> Landsat does not have red-edge bands. NDRE is unavailable.
                No brinjal-specific Random Forest model is trained on Landsat — use Sentinel-2 for classification.
              </div>
            </div>
          )}

          {/* Planet */}
          {selected === 'planet' && (
            <div className="card">
              <div className="alert alert-warning" style={{ fontSize: 12 }}>
                <strong>⚠ Requires Planet API Key.</strong> Planet imagery is <strong>never mocked</strong>.
                Set <code style={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}>PLANET_API_KEY</code> in
                <code style={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}> backend/.env</code>.
              </div>
              <button className="btn btn-outline btn-sm" style={{ marginTop: 12, marginBottom: 12 }} onClick={handlePlanetCheck} disabled={checkingPlanet}>
                {checkingPlanet ? <div className="spinner" style={{ width: 12, height: 12 }} /> : <ExternalLink size={12} />}
                Validate Planet API Key
              </button>

              {planetStatus && (
                <div className={`alert ${planetStatus.valid ? 'alert-success' : 'alert-error'}`} style={{ fontSize: 11 }}>
                  {planetStatus.valid ? (
                    <>✓ API key is valid. Available item types: {planetStatus.item_types?.join(', ') || 'none'}</>
                  ) : (
                    <>{planetStatus.error}</>
                  )}
                </div>
              )}

              <div className="disclaimer" style={{ marginTop: 8 }}>
                <strong>Note:</strong> A Planet subscription is required.
                Visit <a href="https://www.planet.com/account/#/user-settings" target="_blank" rel="noreferrer"
                  style={{ color: 'var(--clr-blue-light)' }}>planet.com</a> to obtain your API key.
              </div>
            </div>
          )}

          {/* AlphaEarth */}
          {selected === 'alphaearth' && (
            <div>
              <div className="card">
                <div className="alert alert-info" style={{ fontSize: 12 }}>
                  <strong>GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL</strong> — 64-dimensional dense
                  satellite embeddings at 10m resolution. Requires GEE project access.
                  May require allowlisting — see{' '}
                  <a href="https://earthengine.google.com/noncommercial/" target="_blank" rel="noreferrer"
                    style={{ color: 'var(--clr-blue-light)' }}>earthengine.google.com</a>.
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 12 }}>
                  {(selectedSource.use_cases ?? []).map(uc => (
                    <span key={uc} className="badge badge-primary">{uc}</span>
                  ))}
                </div>
              </div>
              <AlphaEarthPanel aoi={{ latitude: 22.57, longitude: 88.36, radius_km: 25 }} />
            </div>
          )}

          {/* Comparison note */}
          <div className="card" style={{ marginTop: 16 }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--clr-text)', marginBottom: 10 }}>
              📊 Source Comparison
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                <thead>
                  <tr>
                    {['Source', 'Resolution', 'Revisit', 'NDRE', 'Cost', 'Best For'].map(h => (
                      <th key={h} style={{ padding: '8px 10px', background: 'var(--clr-surface-2)', color: 'var(--clr-text-muted)', textAlign: 'left', fontSize: 10, borderBottom: '1px solid var(--clr-glass-border)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Sentinel-2', '10m', '5 days', '✓', 'Free', 'Crop classification'],
                    ['Landsat 8/9', '30m', '16 days', '✗', 'Free', 'Historical analysis'],
                    ['Planet', '3-5m', '1 day', '✗', 'Paid', 'Sub-field monitoring'],
                    ['AlphaEarth', '10m', 'Annual', 'N/A', 'GEE', 'Embedding / transfer learning'],
                  ].map(row => (
                    <tr key={row[0]} style={{ borderBottom: '1px solid var(--clr-glass-border)' }}>
                      {row.map((cell, i) => (
                        <td key={i} style={{ padding: '8px 10px', color: i === 0 ? 'var(--clr-text)' : 'var(--clr-text-dim)' }}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
