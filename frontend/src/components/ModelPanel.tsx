import React, { useState } from 'react';
import { useApp } from '../App';

const fmt = (v: number | undefined | null, dec = 4) =>
  v != null ? v.toFixed(dec) : '–';

export default function ModelPanel() {
  const { state } = useApp();
  const { modelMetrics: metrics, trainingResult } = state;
  const [showFeatureImportance, setShowFeatureImportance] = useState(false);

  if (!metrics) {
    return (
      <div className="section" style={{ textAlign: 'center', padding: '24px 16px' }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🤖</div>
        <div style={{ fontSize: 12, color: 'var(--clr-text-dim)' }}>
          Model metrics will appear here after training.
        </div>
        {trainingResult && (
          <div className="alert alert-success" style={{ marginTop: 12, textAlign: 'left' }}>
            Training data ready: {trainingResult.n_samples} pixels extracted.
            {trainingResult.class_counts.map(c => (
              <div key={c.class_name} style={{ fontSize: 10, marginTop: 2 }}>
                • {c.class_name}: {c.count} samples
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  const accuracy = (metrics.overall_accuracy * 100).toFixed(1);
  const precision = (metrics.macro_precision * 100).toFixed(1);
  const recall = (metrics.macro_recall * 100).toFixed(1);
  const f1 = (metrics.macro_f1 * 100).toFixed(1);

  // Feature importance (top 10)
  const featureImportance = Object.entries(metrics.feature_importances ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 12);
  const maxFI = featureImportance[0]?.[1] ?? 1;

  return (
    <div className="section fade-in">
      <div className="section-title"><div className="section-title-accent" />Model Metrics</div>

      {/* Model info */}
      <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 10 }}>
        {metrics.model_type} · {metrics.n_estimators} trees ·
        Trained: {new Date(metrics.trained_at).toLocaleDateString('en-IN')}
      </div>
      <div className="alert alert-info" style={{ marginBottom: 10 }}>
        Feature sources: {metrics.feature_sources?.join(' + ') ?? 'Sentinel-2'}
        {metrics.alphaearth_enabled && <div style={{ marginTop: 4 }}>AlphaEarth values are 64 learned embedding features, not spectral bands.</div>}
      </div>
      {metrics.model_comparison && (
        <div className="alert alert-info" style={{ marginBottom: 10 }}>
          <strong>Matched feature comparison</strong>
          <div style={{ fontSize: 10, margin: '4px 0 8px' }}>{metrics.model_comparison.evaluation_label}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 10 }}>
            {[['Model A · Sentinel-2', metrics.model_comparison.model_a], ['Model B · Sentinel-2 + AlphaEarth (64)', metrics.model_comparison.model_b]].map(([title, values]) => (
              <div key={title as string}>
                <strong>{title as string}</strong>
                {['accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'brinjal_precision', 'brinjal_recall', 'brinjal_f1'].map(key => {
                  const value = (values as Record<string, unknown>)[key];
                  return <div key={key}>{key.split('_').join(' ')}: {typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : 'Unavailable'}</div>;
                })}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Samples */}
      <div className="stat-grid" style={{ marginBottom: 10 }}>
        <div className="stat-card">
          <div className="stat-label">Train Samples</div>
          <div className="stat-value" style={{ fontSize: 18 }}>{metrics.n_training_samples}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Val Samples</div>
          <div className="stat-value" style={{ fontSize: 18 }}>{metrics.n_validation_samples}</div>
        </div>
      </div>

      {/* Key metrics */}
      <div className="stat-grid" style={{ marginBottom: 10 }}>
        {[
          { label: 'Accuracy', value: accuracy, color: 'var(--clr-accent-light)' },
          { label: 'Precision', value: precision, color: 'var(--clr-primary-light)' },
          { label: 'Recall', value: recall, color: '#FCD34D' },
          { label: 'F1 Score', value: f1, color: '#93C5FD' },
        ].map(m => (
          <div key={m.label} className="stat-card">
            <div className="stat-label">{m.label}</div>
            <div className="stat-value" style={{ fontSize: 20, color: m.color }}>
              {m.value}<span className="stat-unit">%</span>
            </div>
          </div>
        ))}
      </div>

      {/* Per-class metrics */}
      {metrics.class_metrics?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--clr-text-muted)', marginBottom: 6 }}>Per-class Metrics</div>
          <div style={{ fontSize: 11, color: 'var(--clr-text-dim)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '90px 1fr 1fr 1fr 40px', gap: 4, marginBottom: 4,
              fontWeight: 600, color: 'var(--clr-text-muted)', fontSize: 10 }}>
              <span>Class</span><span>Prec</span><span>Rec</span><span>F1</span><span>N</span>
            </div>
            {metrics.class_metrics.map(cm => (
              <div key={cm.crop_class} style={{
                display: 'grid', gridTemplateColumns: '90px 1fr 1fr 1fr 40px', gap: 4,
                padding: '3px 0', borderBottom: '1px solid var(--clr-glass-border)',
              }}>
                <span style={{ color: cm.crop_class === 'brinjal' ? 'var(--clr-primary-light)' : 'var(--clr-text-muted)' }}>
                  {cm.crop_class === 'brinjal' ? '🍆' : ''} {cm.crop_class.replace('_', ' ')}
                </span>
                <span>{(cm.precision * 100).toFixed(0)}%</span>
                <span>{(cm.recall * 100).toFixed(0)}%</span>
                <span>{(cm.f1_score * 100).toFixed(0)}%</span>
                <span>{cm.support}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Confusion matrix */}
      {metrics.confusion_matrix?.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--clr-text-muted)', marginBottom: 6 }}>Confusion Matrix</div>
          <div className="confusion-matrix">
            <table className="cm-table">
              <thead>
                <tr>
                  <th>Pred↓ True→</th>
                  {metrics.class_names.map(n => (
                    <th key={n}>{n.substring(0, 5)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.confusion_matrix.map((row, i) => (
                  <tr key={i}>
                    <th>{metrics.class_names[i]?.substring(0, 5)}</th>
                    {row.map((val, j) => (
                      <td key={j} className={i === j ? 'cm-cell-diag' : 'cm-cell-off'}>
                        {val}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Feature importance */}
      {featureImportance.length > 0 && (
        <div>
          <button
            className="btn btn-outline btn-sm"
            style={{ width: '100%', marginBottom: 8 }}
            onClick={() => setShowFeatureImportance(v => !v)}
          >
            {showFeatureImportance ? '▲ Hide' : '▼ Show'} Feature Importance
          </button>
          {showFeatureImportance && (
            <div className="fade-in">
              {featureImportance.map(([name, val]) => (
                <div key={name} className="feature-bar">
                  <div className="feature-name" title={name}>{name}</div>
                  <div className="feature-track">
                    <div className="feature-fill" style={{ width: `${(val / maxFI) * 100}%` }} />
                  </div>
                  <div className="feature-pct">{(val * 100).toFixed(1)}%</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
