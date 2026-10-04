import React, { useState } from 'react';
import { toast } from 'react-hot-toast';
import { useApp } from '../App';
import {
  startAnalysis,
  pollUntilDone,
  trainModel,
  runClassification,
  getPredictions,
  getProbabilityLayer,
} from '../services/api';
import type { AnalyzeRequest, AnalyzeResult, ModelMetrics, AreaStatistics, PredictionPoint } from '../types';
import TrainingDataUpload from './TrainingDataUpload';

const INDIA_STATES = [
  'Andhra Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Gujarat',
  'Haryana', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh',
  'Maharashtra', 'Odisha', 'Punjab', 'Rajasthan', 'Tamil Nadu',
  'Telangana', 'Uttar Pradesh', 'West Bengal',
];

export default function ControlPanel() {
  const { state, setAnalyzeResult, setModelResult, setClassifyResult, updateParam } = useApp();

  // AOI form
  const [state_, setState_] = useState('West Bengal');
  const [district, setDistrict] = useState('');
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [radiusKm, setRadiusKm] = useState('25');
  const [dateFrom, setDateFrom] = useState('2023-10-01');
  const [dateTo, setDateTo] = useState('2024-02-28');

  // Job tracking
  const [analyzeJobId, setAnalyzeJobId] = useState<string | null>(null);
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMsg, setAnalyzeMsg] = useState('');
  const [trainJobId, setTrainJobId] = useState<string | null>(null);
  const [trainProgress, setTrainProgress] = useState(0);
  const [trainMsg, setTrainMsg] = useState('');
  const [classifyProgress, setClassifyProgress] = useState(0);
  const [classifyMsg, setClassifyMsg] = useState('');
  const [isRunning, setIsRunning] = useState(false);

  const { cloudThreshold, ndviThreshold, confidenceHighThreshold, confidenceMediumThreshold,
    minFieldAreaHa, nEstimators } = state;

  // Pipeline step states
  const step1Done = !!state.analyzeJobId;
  const step2Done = !!state.trainingJobId;
  const step3Done = !!state.modelId;
  const step4Done = !!state.classifyJobId;

  // ─── Step 1: Load Satellite Data ───────────────────────────────────────
  const handleLoadData = async () => {
    setIsRunning(true);
    setAnalyzeMsg('Queuing analysis job...');
    setAnalyzeProgress(0);
    try {
      const req: AnalyzeRequest = {
        aoi: {
          state: state_ || undefined,
          district: district || undefined,
          latitude: lat ? parseFloat(lat) : undefined,
          longitude: lon ? parseFloat(lon) : undefined,
          radius_km: radiusKm ? parseFloat(radiusKm) : 25,
        },
        date_from: dateFrom,
        date_to: dateTo,
        cloud_threshold: cloudThreshold,
        ndvi_threshold: ndviThreshold,
        scale_meters: 30,
      };
      const { job_id } = await startAnalysis(req);
      setAnalyzeJobId(job_id);
      const done = await pollUntilDone(job_id, (j) => {
        setAnalyzeProgress(j.progress);
        setAnalyzeMsg(j.message);
      });
      const result = done.result as unknown as AnalyzeResult;
      setAnalyzeResult(job_id, result);
      updateParam('analyzeJobId', job_id);
      toast.success(`Loaded ${result.collection_info?.image_count ?? '?'} Sentinel-2 images`);
    } catch (err: any) {
      toast.error(err.message ?? 'Analysis failed');
    } finally {
      setIsRunning(false);
      setAnalyzeMsg('');
    }
  };

  // ─── Step 3: Train Model ────────────────────────────────────────────────
  const handleTrainModel = async () => {
    if (!state.analyzeJobId || !state.trainingJobId) {
      toast.error('Complete Load Data and Upload Training Data first.');
      return;
    }
    setIsRunning(true);
    setTrainMsg('Queuing training job...');
    setTrainProgress(0);
    try {
      const { job_id } = await trainModel({
        analyze_job_id: state.analyzeJobId,
        training_job_id: state.trainingJobId,
        n_estimators: nEstimators,
        test_size: 0.25,
        random_state: 42,
      });
      setTrainJobId(job_id);
      const done = await pollUntilDone(job_id, (j) => {
        setTrainProgress(j.progress);
        setTrainMsg(j.message);
      });
      const metrics = done.result as unknown as ModelMetrics;
      setModelResult(job_id, metrics.model_id, metrics);
      updateParam('modelId', metrics.model_id);
      toast.success(`Model trained! Accuracy: ${(metrics.overall_accuracy * 100).toFixed(1)}%`);
    } catch (err: any) {
      toast.error(err.message ?? 'Training failed');
    } finally {
      setIsRunning(false);
      setTrainMsg('');
    }
  };

  // ─── Step 4: Run Brinjal Detection ─────────────────────────────────────
  const handleClassify = async () => {
    if (!state.analyzeJobId || !state.modelId) {
      toast.error('Complete all previous steps first.');
      return;
    }
    setIsRunning(true);
    setClassifyMsg('Queuing classification job...');
    setClassifyProgress(0);
    try {
      const { job_id } = await runClassification({
        analyze_job_id: state.analyzeJobId,
        model_id: state.modelId,
        confidence_high_threshold: confidenceHighThreshold,
        confidence_medium_threshold: confidenceMediumThreshold,
        min_field_area_ha: minFieldAreaHa,
        ndvi_threshold: ndviThreshold,
      });
      const done = await pollUntilDone(job_id, (j) => {
        setClassifyProgress(j.progress);
        setClassifyMsg(j.message);
      });
      const stats = (done.result as any)?.statistics as AreaStatistics;
      const predictions = await getPredictions(job_id);
      const probabilityLayer = await getProbabilityLayer(job_id);
      setClassifyResult(job_id, stats, predictions, probabilityLayer);
      updateParam('classifyJobId', job_id);
      toast.success(`Classification complete! Predicted brinjal: ${stats?.predicted_brinjal_ha?.toFixed(1)} ha`);
    } catch (err: any) {
      toast.error(err.message ?? 'Classification failed');
    } finally {
      setIsRunning(false);
      setClassifyMsg('');
    }
  };

  return (
    <div style={{ height: '100%' }}>
      {/* Pipeline Overview */}
      <div className="section">
        <div className="section-title"><div className="section-title-accent" />Pipeline</div>
        <div className="pipeline">
          {[
            { num: 1, label: 'Load Satellite Data', done: step1Done },
            { num: 2, label: 'Upload Training Data', done: step2Done },
            { num: 3, label: 'Train Model', done: step3Done },
            { num: 4, label: 'Run Brinjal Detection', done: step4Done },
          ].map(s => (
            <div key={s.num} className={`pipeline-step ${s.done ? 'done' : s.num === (!step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : 4) ? 'active' : ''}`}>
              <div className="pipeline-num">{s.done ? '✓' : s.num}</div>
              {s.label}
            </div>
          ))}
        </div>
      </div>

      {/* AOI */}
      <div className="section">
        <div className="section-title"><div className="section-title-accent" />Area of Interest</div>
        <div className="form-group">
          <label className="form-label">State</label>
          <select className="form-select" value={state_} onChange={e => setState_(e.target.value)}>
            <option value="">-- Select State --</option>
            {INDIA_STATES.map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label className="form-label">District (optional)</label>
          <input className="form-input" value={district} onChange={e => setDistrict(e.target.value)} placeholder="e.g. Murshidabad" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div className="form-group">
            <label className="form-label">Latitude</label>
            <input className="form-input" value={lat} onChange={e => setLat(e.target.value)} placeholder="22.57" />
          </div>
          <div className="form-group">
            <label className="form-label">Longitude</label>
            <input className="form-input" value={lon} onChange={e => setLon(e.target.value)} placeholder="88.36" />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Radius around point (km)</label>
          <input className="form-input" value={radiusKm} onChange={e => setRadiusKm(e.target.value)} placeholder="25" />
        </div>
      </div>

      {/* Date range */}
      <div className="section">
        <div className="section-title"><div className="section-title-accent" />Date Range</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div className="form-group">
            <label className="form-label">From</label>
            <input className="form-input" type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">To</label>
            <input className="form-input" type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} />
          </div>
        </div>
        <div className="alert alert-info" style={{ fontSize: 10 }}>
          Brinjal rabi season: Oct – Mar. Kharif: Jun – Sep. Use a 4–6 month window.
        </div>
      </div>

      {/* Parameters */}
      <div className="section">
        <div className="section-title"><div className="section-title-accent" />Parameters</div>

        <div className="form-group">
          <label className="form-label">Cloud Threshold: <span style={{ color: 'var(--clr-primary-light)' }}>{cloudThreshold}%</span></label>
          <div className="range-row">
            <input type="range" className="form-range" min={0} max={100} step={5}
              value={cloudThreshold}
              onChange={e => updateParam('cloudThreshold', Number(e.target.value))} />
            <span className="range-value">{cloudThreshold}%</span>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">NDVI Threshold (vegetation filter): <span style={{ color: 'var(--clr-primary-light)' }}>{ndviThreshold}</span></label>
          <div className="range-row">
            <input type="range" className="form-range" min={0.1} max={0.5} step={0.05}
              value={ndviThreshold}
              onChange={e => updateParam('ndviThreshold', Number(e.target.value))} />
            <span className="range-value">{ndviThreshold}</span>
          </div>
          <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 3 }}>
            Pixels with NDVI &lt; {ndviThreshold} = low/non-vegetation (excluded from crop classification)
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div className="form-group">
            <label className="form-label">High Confidence ≥</label>
            <select className="form-select" value={confidenceHighThreshold}
              onChange={e => updateParam('confidenceHighThreshold', Number(e.target.value))}>
              {[0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Med Confidence ≥</label>
            <select className="form-select" value={confidenceMediumThreshold}
              onChange={e => updateParam('confidenceMediumThreshold', Number(e.target.value))}>
              {[0.40, 0.45, 0.50, 0.55, 0.60].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div className="form-group">
            <label className="form-label">Min Field Area (ha)</label>
            <select className="form-select" value={minFieldAreaHa}
              onChange={e => updateParam('minFieldAreaHa', Number(e.target.value))}>
              {[0.01, 0.05, 0.10, 0.25, 0.50, 1.0].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">RF Trees</label>
            <select className="form-select" value={nEstimators}
              onChange={e => updateParam('nEstimators', Number(e.target.value))}>
              {[50, 100, 150, 200, 300, 500].map(v => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="section">
        <div className="section-title"><div className="section-title-accent" />Actions</div>

        {/* Step 1 */}
        <button className="btn btn-primary btn-block" style={{ marginBottom: 8 }}
          onClick={handleLoadData} disabled={isRunning}>
          🛰️ Load Satellite Data
        </button>
        {analyzeMsg && (
          <div>
            <div className="progress-bar" style={{ marginBottom: 4 }}>
              <div className="progress-bar-fill" style={{ width: `${analyzeProgress}%` }} />
            </div>
            <div className="job-status running">
              <div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)' }}>{analyzeMsg}</span>
            </div>
          </div>
        )}
        {step1Done && <div className="job-status completed" style={{ marginBottom: 8 }}>
          ✓ Sentinel-2 data loaded — {state.analyzeResult?.collection_info?.image_count ?? '?'} images
        </div>}
      </div>

      {/* Step 2: Training Data */}
      <TrainingDataUpload
        onTrainingComplete={(jobId) => {
          updateParam('trainingJobId', jobId);
        }}
      />

      {/* Steps 3 & 4 */}
      <div className="section">
        <button className="btn btn-primary btn-block" style={{ marginBottom: 8 }}
          onClick={handleTrainModel} disabled={isRunning || !step2Done}>
          🤖 Train Random Forest
        </button>
        {trainMsg && (
          <div>
            <div className="progress-bar" style={{ marginBottom: 4 }}>
              <div className="progress-bar-fill" style={{ width: `${trainProgress}%` }} />
            </div>
            <div className="job-status running"><div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)' }}>{trainMsg}</span></div>
          </div>
        )}
        {step3Done && <div className="job-status completed" style={{ marginBottom: 8 }}>
          ✓ Model trained — Accuracy: {((state.modelMetrics?.overall_accuracy ?? 0) * 100).toFixed(1)}%
        </div>}

        <button className="btn btn-accent btn-block"
          onClick={handleClassify} disabled={isRunning || !step3Done}>
          🌾 Run Brinjal Detection
        </button>
        {classifyMsg && (
          <div>
            <div className="progress-bar" style={{ marginBottom: 4 }}>
              <div className="progress-bar-fill" style={{ width: `${classifyProgress}%` }} />
            </div>
            <div className="job-status running"><div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)' }}>{classifyMsg}</span></div>
          </div>
        )}
        {step4Done && <div className="job-status completed">
          ✓ Classification complete
        </div>}
      </div>
    </div>
  );
}
