import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { MapPin, Trash2, BarChart2, Download, RefreshCw, Plus, Eye } from 'lucide-react';
import * as XLSX from 'xlsx';
import { useApp } from '../App';
import { listLocations, deleteLocation } from '../services/api';
import type { SavedLocation } from '../types';

const STATUS_COLORS: Record<string, string> = {
  saved:     'var(--clr-text-dim)',
  analyzing: 'var(--clr-blue)',
  complete:  'var(--clr-success)',
  failed:    'var(--clr-error)',
};

const STATUS_BG: Record<string, string> = {
  saved:     'rgba(75,94,122,0.15)',
  analyzing: 'rgba(59,130,246,0.15)',
  complete:  'rgba(16,185,129,0.15)',
  failed:    'rgba(239,68,68,0.15)',
};

export default function SavedLocationsPage() {
  const navigate = useNavigate();
  const { state, removeSavedLocation, setSavedLocations } = useApp();
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const { savedLocations } = state;

  const refresh = async () => {
    setLoading(true);
    try {
      const locs = await listLocations(state.user?.id);
      setSavedLocations(locs);
    } catch {
      toast.error('Could not fetch locations from server');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const handleDelete = async (loc: SavedLocation) => {
    if (!confirm(`Delete "${loc.name}"?`)) return;
    setDeleting(loc.location_id);
    try {
      await deleteLocation(loc.location_id);
      removeSavedLocation(loc.location_id);
      toast.success('Location deleted');
    } catch {
      toast.error('Failed to delete location');
    } finally {
      setDeleting(null);
    }
  };

  const handleAnalyze = (loc: SavedLocation) => {
    navigate('/analysis', { state: { location: loc } });
  };

  const handleViewMap = (loc: SavedLocation) => {
    navigate('/home', { state: { previewLat: loc.latitude, previewLon: loc.longitude } });
  };

  const handleDownloadExcel = () => {
    if (!savedLocations.length) { toast.error('No locations to export'); return; }

    const rows = savedLocations.map(loc => ({
      Name: loc.name,
      Latitude: loc.latitude,
      Longitude: loc.longitude,
      'Radius (km)': loc.radius_km,
      'Date From': loc.date_from,
      'Date To': loc.date_to,
      'Cloud Threshold (%)': loc.cloud_threshold,
      'NDVI Threshold': loc.ndvi_threshold,
      Status: loc.status,
      'Brinjal Area (ha)': loc.result_summary?.predicted_brinjal_ha ?? '',
      'Total Area (ha)': loc.result_summary?.total_area_ha ?? '',
      'Avg Confidence': loc.result_summary?.avg_brinjal_confidence ?? '',
      'Saved At': loc.created_at,
    }));

    const ws = XLSX.utils.json_to_sheet(rows);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Saved Locations');
    XLSX.writeFile(wb, `agrisense_locations_${Date.now()}.xlsx`);
    toast.success('Excel downloaded!');
  };

  return (
    <div className="page" style={{ maxWidth: '100%' }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
        <div className="page-header" style={{ marginBottom: 0 }}>
          <h1 className="page-title">Saved Locations</h1>
          <p className="page-subtitle">
            {savedLocations.length} farm{savedLocations.length !== 1 ? 's' : ''} saved
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button className="btn btn-ghost btn-sm" onClick={handleDownloadExcel} disabled={!savedLocations.length}>
            <Download size={13} /> Export Excel
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/home')}>
            <Plus size={13} /> Add Location
          </button>
        </div>
      </div>

      {/* Empty state */}
      {!savedLocations.length && !loading && (
        <div className="empty-state" style={{ minHeight: 400 }}>
          <div className="empty-state-icon">🗺️</div>
          <div className="empty-state-title">No farm locations saved yet</div>
          <div className="empty-state-desc">
            Go to the Home page and pin a coordinate on the map to save your first farm.
          </div>
          <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={() => navigate('/home')}>
            <Plus size={14} /> Add First Location
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <div className="spinner spinner-lg" />
        </div>
      )}

      {/* Grid */}
      {!loading && savedLocations.length > 0 && (
        <div className="card-grid">
          {savedLocations.map(loc => (
            <div key={loc.location_id} className="loc-card fade-in">
              {/* Status stripe */}
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: STATUS_COLORS[loc.status] || 'var(--clr-text-dim)', borderRadius: '14px 14px 0 0' }} />

              <div className="loc-card-header">
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <MapPin size={14} color="var(--clr-primary-light)" />
                    <div className="loc-card-name">{loc.name}</div>
                  </div>
                  <div className="loc-card-coords">
                    {loc.latitude.toFixed(5)}, {loc.longitude.toFixed(5)}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 2 }}>
                    Radius: {loc.radius_km} km · {loc.date_from} → {loc.date_to}
                  </div>
                </div>
                <span style={{
                  fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px',
                  padding: '3px 8px', borderRadius: 20,
                  background: STATUS_BG[loc.status] || 'rgba(75,94,122,0.15)',
                  color: STATUS_COLORS[loc.status] || 'var(--clr-text-dim)',
                  flexShrink: 0,
                }}>
                  {loc.status}
                </span>
              </div>

              {/* Result summary if available */}
              {loc.result_summary && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6, margin: '10px 0', padding: '10px', background: 'var(--clr-surface-2)', borderRadius: 8 }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginBottom: 2 }}>Brinjal</div>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13, fontWeight: 700, color: 'var(--clr-primary-light)' }}>
                      {loc.result_summary.predicted_brinjal_ha?.toFixed(1)} ha
                    </div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginBottom: 2 }}>Area</div>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13, fontWeight: 700, color: 'var(--clr-text)' }}>
                      {loc.result_summary.total_area_ha?.toFixed(1)} ha
                    </div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginBottom: 2 }}>Confidence</div>
                    <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 13, fontWeight: 700, color: 'var(--clr-accent-light)' }}>
                      {((loc.result_summary.avg_brinjal_confidence ?? 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
              )}

              <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginBottom: 10 }}>
                Saved {new Date(loc.created_at).toLocaleDateString()}
              </div>

              {/* Actions */}
              <div className="loc-card-actions">
                <button className="btn btn-ghost btn-sm" style={{ flex: 1, fontSize: 11 }} onClick={() => handleViewMap(loc)}>
                  <Eye size={12} /> Map
                </button>
                <button className="btn btn-primary btn-sm" style={{ flex: 2, fontSize: 11 }} onClick={() => handleAnalyze(loc)}>
                  <BarChart2 size={12} /> Analyze
                </button>
                <button
                  className="btn btn-danger btn-sm btn-icon"
                  onClick={() => handleDelete(loc)}
                  disabled={deleting === loc.location_id}
                  title="Delete location"
                >
                  {deleting === loc.location_id ? <div className="spinner" style={{ width: 12, height: 12 }} /> : <Trash2 size={12} />}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Excel note */}
      {savedLocations.length > 0 && (
        <div className="disclaimer" style={{ marginTop: 24, maxWidth: 600 }}>
          <strong>⚠ Note:</strong> Results labeled "Predicted Brinjal" are model outputs.
          Treat as preliminary suitability estimates, not confirmed cultivation records.
          Export your data for further validation.
        </div>
      )}
    </div>
  );
}
