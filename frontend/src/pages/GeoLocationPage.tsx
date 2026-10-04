import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { MapPin, Search, Save, Sliders, Calendar, AlertCircle, CheckCircle, Navigation } from 'lucide-react';
import { useApp } from '../App';
import { createLocation } from '../services/api';

// Fix leaflet default icons
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

function validateLat(v: string): string | null {
  const n = parseFloat(v);
  if (isNaN(n)) return 'Must be a number';
  if (n < -90 || n > 90) return 'Must be between −90 and 90';
  return null;
}

function validateLon(v: string): string | null {
  const n = parseFloat(v);
  if (isNaN(n)) return 'Must be a number';
  if (n < -180 || n > 180) return 'Must be between −180 and 180';
  return null;
}

export default function GeoLocationPage() {
  const navigate = useNavigate();
  const { addSavedLocation, state } = useApp();

  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const circleRef = useRef<L.Circle | null>(null);

  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [name, setName] = useState('');
  const [radiusKm, setRadiusKm] = useState('10');
  const [dateFrom, setDateFrom] = useState('2023-10-01');
  const [dateTo, setDateTo] = useState('2024-02-28');
  const [cloudThreshold, setCloudThreshold] = useState(20);
  const [ndviThreshold, setNdviThreshold] = useState(0.25);

  const [latError, setLatError] = useState<string | null>(null);
  const [lonError, setLonError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [located, setLocated] = useState(false);

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      center: [20.5937, 78.9629],
      zoom: 5,
      zoomControl: true,
    });

    // Satellite basemap
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { attribution: 'Tiles © Esri', maxZoom: 18 }
    ).addTo(map);

    // Map click → fill coords
    map.on('click', (e: L.LeafletMouseEvent) => {
      setLat(e.latlng.lat.toFixed(6));
      setLon(e.latlng.lng.toFixed(6));
      setLatError(null);
      setLonError(null);
      placeMarker(map, e.latlng.lat, e.latlng.lng, parseFloat(radiusKm) || 10);
      setLocated(true);
    });

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  const placeMarker = useCallback((map: L.Map, latN: number, lonN: number, rad: number) => {
    if (markerRef.current) map.removeLayer(markerRef.current);
    if (circleRef.current) map.removeLayer(circleRef.current);

    const customIcon = L.divIcon({
      html: `<div style="width:20px;height:20px;background:linear-gradient(135deg,#7C3AED,#10B981);border-radius:50%;border:3px solid #fff;box-shadow:0 0 12px rgba(124,58,237,0.7)"></div>`,
      iconSize: [20, 20],
      iconAnchor: [10, 10],
      className: '',
    });

    markerRef.current = L.marker([latN, lonN], { icon: customIcon })
      .bindPopup(`<div style="font-size:12px;font-family:JetBrains Mono"><b>${latN.toFixed(5)}, ${lonN.toFixed(5)}</b><br/>Radius: ${rad} km</div>`)
      .addTo(map);

    circleRef.current = L.circle([latN, lonN], {
      radius: rad * 1000,
      color: '#7C3AED',
      weight: 2,
      fillOpacity: 0.08,
      dashArray: '5 5',
    }).addTo(map);

    map.setView([latN, lonN], 11, { animate: true });
  }, []);

  const handleLocate = () => {
    const latErr = validateLat(lat);
    const lonErr = validateLon(lon);
    setLatError(latErr);
    setLonError(lonErr);
    if (latErr || lonErr) return;

    const latN = parseFloat(lat);
    const lonN = parseFloat(lon);
    const map = mapRef.current;
    if (!map) return;

    placeMarker(map, latN, lonN, parseFloat(radiusKm) || 10);
    setLocated(true);
    toast.success(`Located: ${latN.toFixed(5)}, ${lonN.toFixed(5)}`);
  };

  const handleSave = async () => {
    if (!located) { toast.error('Locate the point on the map first'); return; }
    const latErr = validateLat(lat);
    const lonErr = validateLon(lon);
    if (latErr || lonErr) { toast.error('Fix coordinate errors first'); return; }

    setSaving(true);
    try {
      const loc = await createLocation({
        latitude: parseFloat(lat),
        longitude: parseFloat(lon),
        name: name || `Farm @ ${parseFloat(lat).toFixed(4)}, ${parseFloat(lon).toFixed(4)}`,
        radius_km: parseFloat(radiusKm) || 10,
        date_from: dateFrom,
        date_to: dateTo,
        cloud_threshold: cloudThreshold,
        ndvi_threshold: ndviThreshold,
        user_id: state.user?.id ?? 'default',
      });
      addSavedLocation(loc);
      toast.success('Farm location saved!');
      navigate('/locations');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? 'Failed to save location');
    } finally {
      setSaving(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleLocate();
  };

  return (
    <div style={{ height: '100vh', display: 'flex', overflow: 'hidden' }}>
      {/* Left panel */}
      <aside style={{ width: 320, background: 'var(--clr-surface)', borderRight: '1px solid var(--clr-glass-border)', overflowY: 'auto', flexShrink: 0 }}>
        {/* Header */}
        <div style={{ padding: '20px 20px 0' }}>
          <h1 style={{ fontFamily: 'Outfit, sans-serif', fontSize: 20, fontWeight: 800, background: 'linear-gradient(120deg, #E0E7FF, #A78BFA)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', marginBottom: 4 }}>
            Geo-Location
          </h1>
          <p style={{ fontSize: 12, color: 'var(--clr-text-dim)', lineHeight: 1.5 }}>
            Enter coordinates or click the map to pin a farm/AOI.
          </p>
        </div>

        {/* Coordinates */}
        <div className="section" style={{ marginTop: 12 }}>
          <div className="section-title"><div className="section-title-accent" /><MapPin size={12} />Coordinates</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Latitude</label>
              <input
                id="geo-lat"
                className={`form-input${latError ? ' error' : located && !latError ? ' valid' : ''}`}
                value={lat}
                onChange={e => { setLat(e.target.value); setLatError(null); setLocated(false); }}
                onKeyPress={handleKeyPress}
                placeholder="20.5937"
              />
              {latError && <div className="form-error"><AlertCircle size={10} />{latError}</div>}
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">Longitude</label>
              <input
                id="geo-lon"
                className={`form-input${lonError ? ' error' : located && !lonError ? ' valid' : ''}`}
                value={lon}
                onChange={e => { setLon(e.target.value); setLonError(null); setLocated(false); }}
                onKeyPress={handleKeyPress}
                placeholder="78.9629"
              />
              {lonError && <div className="form-error"><AlertCircle size={10} />{lonError}</div>}
            </div>
          </div>

          {located && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, fontSize: 11, color: 'var(--clr-accent-light)' }}>
              <CheckCircle size={12} /> Point located on map
            </div>
          )}

          <button
            id="geo-locate-btn"
            className="btn btn-primary btn-block"
            style={{ marginTop: 12 }}
            onClick={handleLocate}
          >
            <Navigation size={14} /> Locate on Map
          </button>

          <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 6, textAlign: 'center' }}>
            Or click directly on the map
          </div>
        </div>

        {/* Farm name */}
        <div className="section">
          <div className="section-title"><div className="section-title-accent" />Farm Details</div>
          <div className="form-group">
            <label className="form-label">Farm / AOI Name (optional)</label>
            <input
              id="geo-name"
              className="form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. North Field – Murshidabad"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Analysis Radius: <span style={{ color: 'var(--clr-primary-light)', fontFamily: 'JetBrains Mono' }}>{radiusKm} km</span></label>
            <div className="range-row">
              <input
                type="range"
                className="form-range"
                min={1} max={100} step={1}
                value={radiusKm}
                onChange={e => {
                  setRadiusKm(e.target.value);
                  if (located && mapRef.current) {
                    placeMarker(mapRef.current, parseFloat(lat), parseFloat(lon), parseFloat(e.target.value));
                  }
                }}
              />
              <span className="range-value">{radiusKm}</span>
            </div>
          </div>
        </div>

        {/* Date range */}
        <div className="section">
          <div className="section-title"><div className="section-title-accent" /><Calendar size={12} />Date Range</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">From</label>
              <input id="geo-date-from" type="date" className="form-input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">To</label>
              <input id="geo-date-to" type="date" className="form-input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
          </div>
          <div className="alert alert-info" style={{ marginTop: 10, fontSize: 10 }}>
            🌾 Brinjal rabi season: Oct–Mar. Kharif: Jun–Sep.
          </div>
        </div>

        {/* Parameters */}
        <div className="section">
          <div className="section-title"><div className="section-title-accent" /><Sliders size={12} />Parameters</div>
          <div className="form-group">
            <label className="form-label">Cloud Threshold: <span style={{ color: 'var(--clr-primary-light)', fontFamily: 'JetBrains Mono' }}>{cloudThreshold}%</span></label>
            <div className="range-row">
              <input type="range" className="form-range" min={0} max={100} step={5} value={cloudThreshold} onChange={e => setCloudThreshold(Number(e.target.value))} />
              <span className="range-value">{cloudThreshold}%</span>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label">NDVI Threshold: <span style={{ color: 'var(--clr-primary-light)', fontFamily: 'JetBrains Mono' }}>{ndviThreshold}</span></label>
            <div className="range-row">
              <input type="range" className="form-range" min={0.05} max={0.5} step={0.05} value={ndviThreshold} onChange={e => setNdviThreshold(Number(e.target.value))} />
              <span className="range-value">{ndviThreshold}</span>
            </div>
          </div>
        </div>

        {/* Save button */}
        <div style={{ padding: '16px 20px 24px' }}>
          <button
            id="geo-save-btn"
            className="btn btn-accent btn-block btn-lg"
            onClick={handleSave}
            disabled={saving || !located}
          >
            {saving ? <div className="spinner" /> : <Save size={16} />}
            {saving ? 'Saving...' : 'Save Farm Location'}
          </button>
          {!located && (
            <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', textAlign: 'center', marginTop: 8 }}>
              Locate a point first to enable saving
            </div>
          )}
        </div>
      </aside>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative' }}>
        <div ref={containerRef} style={{ height: '100%', width: '100%' }} />

        {/* Map hint overlay */}
        {!located && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            background: 'rgba(8,13,26,0.88)', backdropFilter: 'blur(10px)',
            border: '1px solid var(--clr-glass-border)',
            borderRadius: 'var(--radius)', padding: '20px 28px',
            textAlign: 'center', zIndex: 500, pointerEvents: 'none',
          }}>
            <div style={{ fontSize: 36, marginBottom: 10 }}>🛰️</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--clr-text)', marginBottom: 4 }}>
              Click the map to pin a location
            </div>
            <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', lineHeight: 1.5 }}>
              Or enter lat/lon in the panel and click<br />"Locate on Map"
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
