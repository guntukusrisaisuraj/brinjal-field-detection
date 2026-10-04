import React, { useState, useRef } from 'react';
import { toast } from 'react-hot-toast';
import { Upload, Trash2 } from 'lucide-react';
import { useApp } from '../App';
import { uploadTrainingData, uploadTrainingFile, pollUntilDone } from '../services/api';
import type { CropClass, TrainingPolygon, TrainingResult } from '../types';
import { CROP_CLASS_COLORS, CROP_CLASS_LABELS } from '../types';

const CROP_CLASSES: CropClass[] = [
  'brinjal', 'other_crop', 'bare_soil', 'built_up', 'water', 'other_vegetation',
];

const SAMPLE_GEOJSON = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[88.36, 22.57], [88.37, 22.57], [88.37, 22.58], [88.36, 22.58], [88.36, 22.57]]] },
      properties: { crop_class: 'brinjal', label: 'WB brinjal field' },
    },
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[85.14, 25.35], [85.15, 25.35], [85.15, 25.36], [85.14, 25.36], [85.14, 25.35]]] },
      properties: { crop_class: 'brinjal', label: 'Bihar brinjal field' },
    },
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[85.20, 25.40], [85.21, 25.40], [85.21, 25.41], [85.20, 25.41], [85.20, 25.40]]] },
      properties: { crop_class: 'other_crop', label: 'Rice paddy' },
    },
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[77.20, 28.70], [77.21, 28.70], [77.21, 28.71], [77.20, 28.71], [77.20, 28.70]]] },
      properties: { crop_class: 'built_up', label: 'Urban Delhi' },
    },
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[80.50, 22.80], [80.51, 22.80], [80.51, 22.81], [80.50, 22.81], [80.50, 22.80]]] },
      properties: { crop_class: 'bare_soil', label: 'Fallow field' },
    },
    {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [[[76.95, 11.00], [76.96, 11.00], [76.96, 11.01], [76.95, 11.01], [76.95, 11.00]]] },
      properties: { crop_class: 'water', label: 'Water body' },
    },
  ],
};

interface Props {
  /** Called with (jobId, result?) when feature extraction completes successfully. */
  onTrainingComplete: (jobId: string, result?: TrainingResult) => void;
  alphaearthEnabled?: boolean;
}

export default function TrainingDataUpload({ onTrainingComplete, alphaearthEnabled = false }: Props) {
  const { state } = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [manualPolygons, setManualPolygons] = useState<TrainingPolygon[]>([]);
  const [selectedClass, setSelectedClass] = useState<CropClass>('brinjal');
  const [tab, setTab] = useState<'upload' | 'sample' | 'drawn'>('upload');

  const analyzeJobId = state.analyzeJobId;

  const handleUploadFile = async (file: File) => {
    if (!analyzeJobId) {
      toast.error('Run "Load Satellite Data" first to get an analysis job.');
      return;
    }
    setIsUploading(true);
    setStatusMsg('Uploading file...');
    try {
      const { job_id } = await uploadTrainingFile(analyzeJobId, file, alphaearthEnabled);
      setStatusMsg('Extracting pixel features from polygons...');
      const done = await pollUntilDone(job_id, (j) => {
        setProgress(j.progress);
        setStatusMsg(j.message);
      });
      const result = done.result as unknown as TrainingResult;
      toast.success(`Extracted ${result?.n_samples ?? '?'} training pixels`);
      onTrainingComplete(job_id, result);
    } catch (err: any) {
      toast.error(err.message ?? 'Upload failed');
    } finally {
      setIsUploading(false);
      setStatusMsg('');
      setProgress(0);
    }
  };

  const handleUseSample = async () => {
    if (!analyzeJobId) {
      toast.error('Run "Load Satellite Data" first.');
      return;
    }
    setIsUploading(true);
    setStatusMsg('Using demo training data (West Bengal, Bihar, Karnataka, Odisha)...');
    try {
      const { job_id } = await uploadTrainingData(analyzeJobId, JSON.stringify(SAMPLE_GEOJSON), alphaearthEnabled);
      const done = await pollUntilDone(job_id, (j) => {
        setProgress(j.progress);
        setStatusMsg(j.message);
      });
      toast.success(`Demo: extracted ${(done.result as any)?.n_samples ?? '?'} training pixels`);
      onTrainingComplete(job_id, done.result as unknown as TrainingResult);
    } catch (err: any) {
      toast.error(err.message ?? 'Demo training upload failed');
    } finally {
      setIsUploading(false);
      setStatusMsg('');
      setProgress(0);
    }
  };

  const removePolygon = (id: string) =>
    setManualPolygons(ps => ps.filter(p => p.id !== id));

  return (
    <div className="section fade-in">
      <div className="section-title">
        <div className="section-title-accent" />
        Training Data
      </div>

      <div className="disclaimer">
        <strong>⚠ Important:</strong> Training polygons define where brinjal and other classes
        are located. The Random Forest model learns from these examples.
        Results are labelled <strong>"Predicted Brinjal"</strong> — not confirmed ground truth.
      </div>

      {/* Tabs */}
      <div className="tabs">
        {(['upload', 'sample', 'drawn'] as const).map(t => (
          <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t === 'upload' ? '📂 Upload' : t === 'sample' ? '🧪 Demo' : '✏️ Drawn'}
          </button>
        ))}
      </div>

      {/* Upload tab */}
      {tab === 'upload' && (
        <div>
          <p style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 10, lineHeight: 1.6 }}>
            Upload a GeoJSON FeatureCollection. Each Feature must have a
            <code style={{ background: 'var(--clr-surface-3)', padding: '1px 4px', borderRadius: 3, margin: '0 3px' }}>crop_class</code>
            property set to one of: brinjal, other_crop, bare_soil, built_up, water, other_vegetation.
          </p>
          <input
            type="file"
            ref={fileInputRef}
            accept=".geojson,.json"
            style={{ display: 'none' }}
            onChange={e => {
              const f = e.target.files?.[0];
              if (f) handleUploadFile(f);
              e.target.value = '';
            }}
          />
          <button
            className="btn btn-outline btn-block"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading || !analyzeJobId}
          >
            <Upload size={14} /> Choose GeoJSON File
          </button>
        </div>
      )}

      {/* Demo tab */}
      {tab === 'sample' && (
        <div>
          <div className="alert alert-info" style={{ marginBottom: 10 }}>
            Uses pre-defined sample polygons across West Bengal, Bihar, Odisha, and Karnataka.
            Clearly labelled as <strong>DEMONSTRATION DATA</strong> — replace with real ground truth for production.
          </div>
          <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 10 }}>
            <div style={{ fontWeight: 600, color: 'var(--clr-text-muted)', marginBottom: 6 }}>Sample includes:</div>
            {CROP_CLASSES.map(cls => (
              <div key={cls} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <div style={{ width: 8, height: 8, borderRadius: 2, background: CROP_CLASS_COLORS[cls] }} />
                {CROP_CLASS_LABELS[cls]}
              </div>
            ))}
          </div>
          <button
            className="btn btn-accent btn-block"
            onClick={handleUseSample}
            disabled={isUploading || !analyzeJobId}
          >
            🧪 Use Demo Training Data
          </button>
        </div>
      )}

      {/* Drawn polygons tab */}
      {tab === 'drawn' && (
        <div>
          <p style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 8, lineHeight: 1.5 }}>
            Draw polygons on the map using the draw tool, then assign a class here.
            (Map drawing integration — polygons appear below after drawing on the map.)
          </p>
          <div className="form-group">
            <label className="form-label">Class for next drawn polygon</label>
            <select
              className="form-select"
              value={selectedClass}
              onChange={e => setSelectedClass(e.target.value as CropClass)}
            >
              {CROP_CLASSES.map(cls => (
                <option key={cls} value={cls}>{CROP_CLASS_LABELS[cls]}</option>
              ))}
            </select>
          </div>
          {manualPolygons.length === 0 ? (
            <p style={{ fontSize: 11, color: 'var(--clr-text-dim)', textAlign: 'center', padding: '16px 0' }}>
              No polygons drawn yet. Use the draw tool on the map.
            </p>
          ) : (
            <div style={{ maxHeight: 180, overflowY: 'auto' }}>
              {manualPolygons.map(p => (
                <div key={p.id} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '5px 8px', background: 'var(--clr-glass)',
                  borderRadius: 'var(--radius-sm)', marginBottom: 4,
                  border: '1px solid var(--clr-glass-border)',
                }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: CROP_CLASS_COLORS[p.crop_class], flexShrink: 0 }} />
                  <span style={{ fontSize: 11, flex: 1 }}>{CROP_CLASS_LABELS[p.crop_class]}</span>
                  <button className="btn btn-sm btn-outline" style={{ padding: '2px 6px' }} onClick={() => removePolygon(p.id)}>
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Progress */}
      {isUploading && (
        <div style={{ marginTop: 10 }}>
          <div className="progress-bar" style={{ marginBottom: 6 }}>
            <div className="progress-bar-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="job-status running">
            <div className="job-spinner" />
            <span style={{ color: 'var(--clr-text-muted)' }}>{statusMsg}</span>
          </div>
        </div>
      )}

      {/* Extracted Training Result */}
      {!isUploading && state.trainingResult && (
        <div className="job-status completed" style={{ marginTop: 10, fontSize: 11, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ fontWeight: 600 }}>✓ Extracted {state.trainingResult.n_samples} training pixel samples</div>
          {state.trainingResult.class_counts && state.trainingResult.class_counts.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 2 }}>
              {state.trainingResult.class_counts.map(c => (
                <span key={c.class_name} style={{ background: 'var(--clr-glass)', padding: '2px 6px', borderRadius: 4, border: '1px solid var(--clr-glass-border)' }}>
                  {c.class_name}: {c.count}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
