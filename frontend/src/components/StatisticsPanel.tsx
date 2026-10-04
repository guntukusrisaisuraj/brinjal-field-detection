import React from 'react';
import { useApp } from '../App';

const fmt = (v: number | undefined | null, dec = 2) =>
  v != null ? v.toFixed(dec) : '–';

export default function StatisticsPanel() {
  const { state } = useApp();
  const { statistics: stats, analyzeResult } = state;

  if (!stats && !analyzeResult) {
    return (
      <div className="section" style={{ textAlign: 'center', padding: '32px 16px' }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>📊</div>
        <div style={{ fontSize: 12, color: 'var(--clr-text-dim)' }}>
          Statistics will appear here after the classification is complete.
        </div>
      </div>
    );
  }

  return (
    <div className="section fade-in">
      <div className="section-title"><div className="section-title-accent" />Area Statistics</div>

      {analyzeResult && !stats && (
        <div className="alert alert-info" style={{ marginBottom: 10 }}>
          Sentinel-2 data loaded ({analyzeResult.collection_info?.image_count ?? '?'} images).
          Train the model and run detection to see statistics.
        </div>
      )}

      {stats && (
        <>
          {/* Period */}
          <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 10 }}>
            📅 {stats.date_from} → {stats.date_to} &nbsp;|&nbsp;
            ☁ Cloud ≤ {stats.cloud_threshold}% &nbsp;|&nbsp;
            🌿 NDVI ≥ {stats.ndvi_threshold}
          </div>

          {/* Main stats grid */}
          <div className="stat-grid" style={{ marginBottom: 8 }}>
            <div className="stat-card">
              <div className="stat-label">Total Analyzed</div>
              <div className="stat-value">{fmt(stats.total_area_ha)}<span className="stat-unit"> ha</span></div>
              <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 2 }}>{fmt(stats.total_area_km2, 3)} km²</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Vegetated Area</div>
              <div className="stat-value">{fmt(stats.vegetated_area_ha)}<span className="stat-unit"> ha</span></div>
              <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 2 }}>{fmt(stats.vegetated_area_pct, 1)}% of total</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Low-NDVI Area</div>
              <div className="stat-value">{fmt(stats.low_ndvi_area_ha)}<span className="stat-unit"> ha</span></div>
              <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 2 }}>{fmt(stats.low_ndvi_area_pct, 1)}% masked</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Other Crop</div>
              <div className="stat-value">{fmt(stats.predicted_other_crop_ha)}<span className="stat-unit"> ha</span></div>
            </div>
          </div>

          {/* Brinjal highlight */}
          <div className="stat-card highlight" style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div className="stat-label">🍆 Predicted Brinjal Area</div>
                <div className="stat-value" style={{ fontSize: 28 }}>
                  {fmt(stats.predicted_brinjal_ha)}<span className="stat-unit"> ha</span>
                </div>
                <div style={{ fontSize: 10, color: 'var(--clr-primary-light)', marginTop: 2 }}>
                  {fmt(stats.predicted_brinjal_pct, 1)}% of total analyzed area
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 11, color: 'var(--clr-text-dim)' }}>Fields</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--clr-primary-light)', fontFamily: 'JetBrains Mono, monospace' }}>
                  {stats.num_brinjal_fields}
                </div>
              </div>
            </div>
          </div>

          <div className="stat-card" style={{ marginBottom: 8 }}>
            <div className="stat-label">Avg Brinjal Confidence</div>
            <div className="stat-value" style={{ fontSize: 22 }}>
              {(stats.avg_brinjal_confidence * 100).toFixed(1)}<span className="stat-unit">%</span>
            </div>
            {/* Confidence bar */}
            <div className="progress-bar" style={{ marginTop: 6 }}>
              <div className="progress-bar-fill" style={{ width: `${stats.avg_brinjal_confidence * 100}%` }} />
            </div>
          </div>

          <div className="disclaimer">
            <strong>⚠ Note:</strong> Results labelled as <strong>"Predicted Brinjal Fields"</strong>.
            Sentinel-2 does not inherently contain brinjal labels. Classification
            depends on training data quality and cloud-free imagery availability.
          </div>
        </>
      )}
    </div>
  );
}
