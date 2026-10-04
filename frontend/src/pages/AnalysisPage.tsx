import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useLocation as useRouterLocation } from 'react-router-dom';
import { toast } from 'react-hot-toast';
import { BarChart2, Cpu, Download, MapPin } from 'lucide-react';
import { useApp } from '../App';
import MapView from '../components/MapView';
import TrainingDataUpload from '../components/TrainingDataUpload';
import {
  startAnalysis, pollUntilDone, trainModel, runClassification,
  getPredictions, getProbabilityLayer, getExportUrl, getSatelliteSources, getLandsatInfo, startLandsatAnalysis, getAlphaEarthEmbedding, checkPlanetAccess,
  getDiscoveryStates, startStateDiscovery,
} from '../services/api';
import type {
  AnalyzeRequest, AnalyzeResult, ModelMetrics, AreaStatistics,
  PredictionPoint, SpectralIndices, SatelliteSource, SatelliteSourceId, LandsatResult, LandsatInfo, PlanetAccessResult, AOI, PolygonGeometry, StateDiscoveryResult,
} from '../types';
import { INDEX_DEFINITIONS } from '../types';

// ─── Helpers ───────────────────────────────────────────────

const fmt = (v: number | undefined | null, dec = 2) =>
  v != null ? v.toFixed(dec) : '?';

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null) {
    const candidate = error as { message?: unknown; response?: { data?: { detail?: unknown } } };
    const detail = candidate.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (detail != null) return JSON.stringify(detail);
    if (typeof candidate.message === 'string') return candidate.message;
  }
  return fallback;
}

function IndexCard({ def, value }: { def: typeof INDEX_DEFINITIONS[0]; value: number | null | undefined }) {
  const hasValue = value != null;
  const [lo, hi] = def.range;
  const pct = hasValue ? ((value! - lo) / (hi - lo)) * 100 : 0;

  return (
    <div className="index-card fade-in" title={def.description}>
      <div className="index-card-accent" style={{ background: def.color }} />
      <div style={{ marginTop: 6 }}>
        <div className="index-name">{def.name}</div>
        <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', lineHeight: 1.4, marginBottom: 4 }}>{def.description}</div>
        <div className="index-value" style={{ color: hasValue ? def.color : 'var(--clr-text-dim)' }}>
          {hasValue ? value!.toFixed(4) : 'Unavailable'}
        </div>
        <div className="index-bar">
          <div className="index-bar-fill" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: def.color }} />
        </div>
        <div className="index-formula" title={`Formula: ${def.formula}`}>{def.formula}</div>
      </div>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────

export default function AnalysisPage() {
  const routerLoc = useRouterLocation();
  const preloadedLoc = (routerLoc.state as any)?.location;
  const { state, setAnalyzeResult, setTrainingResult, setModelResult, setClassifyResult, updateParam } = useApp();

  const [sources, setSources] = useState<SatelliteSource[]>([]);
  const [sourceError, setSourceError] = useState('');
  const [imageryBusy, setImageryBusy] = useState(false);
  const [landsatInfo, setLandsatInfo] = useState<LandsatInfo | null>(null);
  const [landsatInfoError, setLandsatInfoError] = useState('');
  const [planetAccess, setPlanetAccess] = useState<PlanetAccessResult | null>(null);
  const [planetError, setPlanetError] = useState('');
  const [planetChecking, setPlanetChecking] = useState(false);
  const [sourceFailure, setSourceFailure] = useState<{ source: SatelliteSourceId; message: string } | null>(null);
  const [aoiMode, setAoiMode] = useState<'point' | 'draw' | 'geojson'>('point');
  const [selectedPolygon, setSelectedPolygon] = useState<PolygonGeometry | null>(null);
  const [aoiError, setAoiError] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const discoverySectionRef = useRef<HTMLDivElement>(null);
  const detailedAoiRef = useRef<HTMLDetailsElement>(null);
  const trainingSectionRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<'pipeline' | 'results' | 'model'>('pipeline');

  // AOI state (pre-fill from saved location if navigated from Locations page)
  const [lat, setLat] = useState(String(preloadedLoc?.latitude ?? '22.57'));
  const [lon, setLon] = useState(String(preloadedLoc?.longitude ?? '88.36'));
  const [radiusKm, setRadiusKm] = useState(String(preloadedLoc?.radius_km ?? '0.01'));
  const [dateFrom, setDateFrom] = useState(preloadedLoc?.date_from || '2025-01-01');
  const [dateTo, setDateTo] = useState(preloadedLoc?.date_to || '2025-03-31');

  // Progress
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMsg, setAnalyzeMsg] = useState('');
  const [trainProgress, setTrainProgress] = useState(0);
  const [trainMsg, setTrainMsg] = useState('');
  const [classifyProgress, setClassifyProgress] = useState(0);
  const [classifyMsg, setClassifyMsg] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [alphaearthMlEnabled, setAlphaearthMlEnabled] = useState(false);
  const [discoveryStates, setDiscoveryStates] = useState<string[]>([]);
  const [selectedState, setSelectedState] = useState('');
  const [stateDiscoveryBusy, setStateDiscoveryBusy] = useState(false);
  const [stateDiscoveryProgress, setStateDiscoveryProgress] = useState(0);
  const [stateDiscoveryMessage, setStateDiscoveryMessage] = useState('');
  const [stateDiscoveryError, setStateDiscoveryError] = useState('');
  const [stateDiscoveryResult, setStateDiscoveryResult] = useState<StateDiscoveryResult | null>(null);
  const [focusFieldId, setFocusFieldId] = useState<string | null>(null);
  const [stateAlphaearthEnabled, setStateAlphaearthEnabled] = useState(false);

  const source = state.activeSatelliteSource;
  const sourceMeta = sources.find(item => item.id === source);
  const availableIndices = source === 'sentinel2'
    ? ['NDVI', 'EVI', 'SAVI', 'NDWI', 'NDRE', 'NDBI']
    : source === 'landsat' ? ['NDVI', 'EVI', 'SAVI', 'NDWI', 'NDBI'] : [];

  useEffect(() => {
    getSatelliteSources().then(result => setSources(result.sources))
      .catch(error => setSourceError(getApiErrorMessage(error, 'Source metadata unavailable.')));
    getLandsatInfo().then(setLandsatInfo)
      .catch(error => setLandsatInfoError(getApiErrorMessage(error, 'Landsat information unavailable.')));
  }, []);

  useEffect(() => {
    getDiscoveryStates().then(result => {
      setDiscoveryStates(result.states);
    }).catch(error => setStateDiscoveryError(getApiErrorMessage(error, 'State list is unavailable.')));
  }, []);

  useEffect(() => {
    setStateAlphaearthEnabled(Boolean(state.modelMetrics?.alphaearth_enabled));
  }, [state.modelId, state.modelMetrics?.alphaearth_enabled]);

  useEffect(() => {
    if (source !== 'planet') return;
    let active = true;
    setPlanetChecking(true);
    setPlanetAccess(null);
    setPlanetError('');
    checkPlanetAccess()
      .then(result => { if (active) setPlanetAccess(result); })
      .catch(error => { if (active) { setPlanetAccess(null); setPlanetError(getApiErrorMessage(error, 'Planet access check failed.')); } })
      .finally(() => { if (active) setPlanetChecking(false); });
    return () => { active = false; };
  }, [source]);

  const currentSourceFailure = sourceFailure?.source === source ? sourceFailure.message : '';
  const sourceStatus = currentSourceFailure ? 'Unavailable' : source === 'sentinel2'
    ? analyzeMsg ? 'Running' : state.analyzeResult ? 'Complete' : 'Ready'
    : source === 'landsat'
      ? imageryBusy ? 'Running' : state.landsatResult ? 'Complete' : landsatInfo ? 'Ready' : landsatInfoError ? 'Unavailable' : 'Ready'
      : source === 'alphaearth'
        ? imageryBusy ? 'Running' : state.alphaEarthResult ? state.alphaEarthResult.accessible ? 'Complete' : 'Unavailable' : 'Ready'
        : planetChecking ? 'Running' : planetError ? 'Unavailable' : planetAccess ? !planetAccess.configured ? 'Configuration required' : planetAccess.valid ? 'Complete' : 'Unavailable' : 'Ready';
  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null;
  const isPosition = (value: unknown): value is GeoJSON.Position =>
    Array.isArray(value) && value.length >= 2 && value.every((part) => typeof part === 'number' && Number.isFinite(part)) &&
    value[0] >= -180 && value[0] <= 180 && value[1] >= -90 && value[1] <= 90;
  const isRing = (value: unknown): value is GeoJSON.Position[] =>
    Array.isArray(value) && value.length >= 4 && value.every(isPosition) &&
    value[0][0] === value[value.length - 1][0] && value[0][1] === value[value.length - 1][1];
  const isPolygonGeometry = (value: unknown): value is GeoJSON.Polygon =>
    isRecord(value) && value.type === 'Polygon' && Array.isArray(value.coordinates) &&
    value.coordinates.length > 0 && value.coordinates.every(isRing);
  const isMultiPolygonGeometry = (value: unknown): value is GeoJSON.MultiPolygon =>
    isRecord(value) && value.type === 'MultiPolygon' && Array.isArray(value.coordinates) &&
    value.coordinates.length > 0 && value.coordinates.every((polygon) =>
      Array.isArray(polygon) && polygon.length > 0 && polygon.every(isRing));

  const normalizePolygonGeoJson = (input: unknown): PolygonGeometry => {
    if (!isRecord(input)) throw new Error('GeoJSON must be an object.');
    if (input.type === 'Polygon') {
      if (isPolygonGeometry(input)) return input;
      throw new Error('Polygon coordinates must contain closed rings with valid longitude/latitude positions.');
    }
    if (input.type === 'MultiPolygon') {
      if (isMultiPolygonGeometry(input)) return input;
      throw new Error('MultiPolygon coordinates must contain closed rings with valid longitude/latitude positions.');
    }
    if (input.type === 'Feature') {
      const geometry = input.geometry;
      if (isPolygonGeometry(geometry) || isMultiPolygonGeometry(geometry)) return geometry;
      throw new Error('Feature geometry must be a Polygon or MultiPolygon.');
    }
    if (input.type === 'FeatureCollection') {
      if (!Array.isArray(input.features) || input.features.length === 0) {
        throw new Error('FeatureCollection must contain at least one polygon feature.');
      }
      const geometries: PolygonGeometry[] = input.features.map((feature) => {
        if (!isRecord(feature) || feature.type !== 'Feature') {
          throw new Error('FeatureCollection entries must be GeoJSON Features.');
        }
        const geometry = feature.geometry;
        if (isPolygonGeometry(geometry) || isMultiPolygonGeometry(geometry)) return geometry;
        throw new Error('Every feature must contain a Polygon or MultiPolygon geometry.');
      });
      const coordinates: GeoJSON.Position[][][] = geometries.flatMap((geometry) =>
        geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates);
      return { type: 'MultiPolygon', coordinates };
    }
    if (typeof input.type === 'string') {
      throw new Error(`Unsupported geometry type: ${input.type}. Use Polygon or MultiPolygon.`);
    }
    throw new Error('Expected a Polygon, MultiPolygon, Feature, or FeatureCollection.');
  };

  const handleGeoJsonFile = async (file?: File) => {
    if (!file) return;
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const geometry = normalizePolygonGeoJson(parsed);
      setSelectedPolygon(geometry);
      setAoiError('');
      setAoiMode('geojson');
      toast.success('GeoJSON AOI selected and displayed on the map.');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Check the file structure.';
      setAoiError(`Invalid GeoJSON: ${message}`);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDrawnAOI = useCallback((feature: GeoJSON.Feature | null) => {
    if (!feature) {
      setSelectedPolygon(null);
      return;
    }
    if (isPolygonGeometry(feature.geometry) || isMultiPolygonGeometry(feature.geometry)) {
      setSelectedPolygon(feature.geometry);
      setAoiError('');
      setAoiMode('draw');
    }
  }, []);

  const clearPolygonAOI = () => {
    setSelectedPolygon(null);
    setAoiError('');
    setAoiMode('point');
    if (fileRef.current) fileRef.current.value = '';
  };

  const polygonVertexCount = (geometry: PolygonGeometry): number => {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    return polygons.reduce((total, polygon) => total + polygon.reduce((ringTotal, ring) =>
      ringTotal + ring.length - (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? 1 : 0), 0), 0);
  };

  const downloadGeoJsonCoordinates = () => {
    if (!selectedPolygon) return;
    const rows = ['feature_id,geometry_type,ring_index,vertex_index,latitude,longitude'];
    const polygons = selectedPolygon.type === 'Polygon' ? [selectedPolygon.coordinates] : selectedPolygon.coordinates;
    polygons.forEach((polygon, polygonIndex) => polygon.forEach((ring, ringIndex) => {
      const closed = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1];
      ring.slice(0, closed ? -1 : undefined).forEach((position, vertexIndex) => {
        rows.push([polygonIndex + 1, selectedPolygon.type, `${polygonIndex + 1}-${ringIndex + 1}`, vertexIndex + 1, position[1], position[0]].join(','));
      });
    }));
    const blob = new Blob([rows.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'aoi-coordinates.csv';
    link.click();
    URL.revokeObjectURL(link.href);
  };
  const buildCurrentAOI = (): AOI | null => {
    if (selectedPolygon) {
      setAoiError('');
      return { geojson: selectedPolygon };
    }
    if (aoiMode !== 'point') {
      const message = 'Finish drawing a polygon or import a valid GeoJSON file before analysis.';
      setAoiError(message);
      toast.error(message);
      return null;
    }
    const latitude = Number(lat);
    const longitude = Number(lon);
    const radius = Number(radiusKm);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
        !Number.isFinite(longitude) || longitude < -180 || longitude > 180 ||
        !Number.isFinite(radius) || radius <= 0) {
      const message = 'Enter valid latitude, longitude, and a positive radius.';
      setAoiError(message);
      toast.error(message);
      return null;
    }
    setAoiError('');
    return { latitude, longitude, radius_km: radius };
  };

  const runImagery = async () => {
    if (source === 'sentinel2') {
      setSourceFailure(null);
      await handleLoadData();
      return;
    }
    if (source === 'planet') {
      setPlanetChecking(true);
      setPlanetAccess(null);
      setPlanetError('');
      try {
        const result = await checkPlanetAccess();
        setPlanetAccess(result);
        if (!result.configured) toast.error(result.error || 'Planet API configuration is required.');
        else if (!result.valid) toast.error(result.error || 'Planet access is unavailable.');
        else toast.success('Planet access is configured. Planet imagery analysis is not available in this workflow.');
      } catch (error) {
        const message = getApiErrorMessage(error, 'Planet access check failed.');
        setPlanetError(message);
        toast.error(message);
      } finally {
        setPlanetChecking(false);
      }
      return;
    }

    const aoi = buildCurrentAOI();
    if (!aoi) return;
    setSourceFailure(null);
    setImageryBusy(true);
    setAnalyzeProgress(0);
    setAnalyzeMsg(source === 'landsat' ? 'Queuing Landsat analysis...' : 'Loading AlphaEarth embeddings...');
    try {
      if (source === 'landsat') {
        const { job_id } = await startLandsatAnalysis({
          aoi,
          date_from: dateFrom,
          date_to: dateTo,
          cloud_threshold: cloudThreshold,
        });
        const done = await pollUntilDone(job_id, job => {
          setAnalyzeProgress(job.progress);
          setAnalyzeMsg(job.message);
        });
        const result = done.result as unknown as LandsatResult;
        updateParam('landsatResult', result);
        updateParam('activeLayer', result.tile_urls.ndvi_url ? 'landsat_ndvi' : 'satellite');
        toast.success(`${result.sensor === 'LC09' ? 'Landsat 9' : result.sensor === 'LC08' ? 'Landsat 8' : result.sensor} analysis complete`);
      } else {
        updateParam('alphaEarthResult', null);
        updateParam('activeLayer', 'satellite');
        const result = await getAlphaEarthEmbedding({ aoi, date_from: dateFrom, date_to: dateTo });
        updateParam('alphaEarthResult', result);
        updateParam('activeLayer', result.accessible && result.tile_url ? 'alphaearth' : 'satellite');
        if (result.accessible) toast.success(`AlphaEarth ${result.year} embedding loaded`);
        else toast.error(result.error || 'AlphaEarth data is unavailable for this AOI.');
      }
    } catch (error) {
      const message = getApiErrorMessage(error, `${sourceMeta?.name || source} analysis failed.`);
      setSourceFailure({ source, message });
      toast.error(message);
    } finally {
      setImageryBusy(false);
      setAnalyzeMsg('');
    }
  };


  const { cloudThreshold, ndviThreshold, confidenceHighThreshold, confidenceMediumThreshold,
    minFieldAreaHa, nEstimators } = state;

  const step1Done = !!state.analyzeJobId;
  const step2Done = !!state.trainingJobId;
  const step3Done = !!state.modelId;
  const step4Done = !!state.classifyJobId;

  // ─── Step 1: Load Data ─────────────────────────────────
  const handleLoadData = async () => {
    const aoi = buildCurrentAOI();
    if (!aoi) return;
    setSourceFailure(null);
    setIsRunning(true);
    setAnalyzeMsg('Queuing analysis...');
    setAnalyzeProgress(0);
    try {
      const req: AnalyzeRequest = {
        aoi,
        date_from: dateFrom,
        date_to: dateTo,
        cloud_threshold: cloudThreshold,
        ndvi_threshold: ndviThreshold,
        scale_meters: 30,
      };
      const { job_id } = await startAnalysis(req);
      const done = await pollUntilDone(job_id, j => {
        setAnalyzeProgress(j.progress);
        setAnalyzeMsg(j.message);
      });
      const result = done.result as unknown as AnalyzeResult;
      setAnalyzeResult(job_id, result);
      updateParam('analyzeJobId', job_id);
      toast.success(`✓ Loaded ${result.collection_info?.image_count ?? '?'} Sentinel-2 images`);
      updateParam('activeLayer', result.tile_urls?.ndvi_url ? 'ndvi' : 'satellite');
      setActiveTab('results');

    } catch (error) {
      const message = getApiErrorMessage(error, 'Sentinel-2 analysis failed.');
      setSourceFailure({ source: 'sentinel2', message });
      toast.error(message);
    } finally {
      setIsRunning(false);
      setAnalyzeMsg('');
    }
  };

  // ─── Step 3: Train ─────────────────────────────────────
  const handleTrainModel = async () => {
    if (!state.analyzeJobId || !state.trainingJobId) {
      toast.error('Complete steps 1 & 2 first'); return;
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
        alphaearth_enabled: state.trainingResult?.alphaearth_enabled ?? false,
      });
      const done = await pollUntilDone(job_id, j => {
        setTrainProgress(j.progress);
        setTrainMsg(j.message);
      });
      const metrics = done.result as unknown as ModelMetrics;
      setModelResult(job_id, metrics.model_id, metrics);
      updateParam('modelId', metrics.model_id);
      toast.success(`✓ Model trained — Accuracy: ${(metrics.overall_accuracy * 100).toFixed(1)}%`);
      setStateDiscoveryError('');
      setActiveTab('results');
      detailedAoiRef.current?.removeAttribute('open');
      requestAnimationFrame(() => discoverySectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } catch (err: any) {
      toast.error(err.message ?? 'Training failed');
    } finally {
      setIsRunning(false);
      setTrainMsg('');
    }
  };

  // ─── Step 4: Classify ──────────────────────────────────
  const handleClassify = async () => {
    if (!state.analyzeJobId || !state.modelId) {
      toast.error('Complete all previous steps first'); return;
    }
    setIsRunning(true);
    setClassifyMsg('Queuing classification...');
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
      const done = await pollUntilDone(job_id, j => {
        setClassifyProgress(j.progress);
        setClassifyMsg(j.message);
      });
      const stats = (done.result as any)?.statistics as AreaStatistics;
      let preds: PredictionPoint[] = [];
      try { preds = await getPredictions(job_id); } catch {}
      const probabilityLayer = await getProbabilityLayer(job_id);
      setClassifyResult(job_id, stats, preds, probabilityLayer);
      updateParam('classifyJobId', job_id);
      toast.success(`✓ Classification complete — ${stats?.predicted_brinjal_ha?.toFixed(1)} ha predicted`);
      setActiveTab('results');
    } catch (err: any) {
      toast.error(err.message ?? 'Classification failed');
    } finally {
      setIsRunning(false);
      setClassifyMsg('');
    }
  };

  const handleStateDiscovery = async () => {
    if (!state.modelId) {
      setStateDiscoveryError('A trained Random Forest model is required. Train the model in Detailed AOI workflow first.');
      return;
    }
    const modelUsesAlphaEarth = Boolean(state.modelMetrics?.alphaearth_enabled);
    if (modelUsesAlphaEarth !== stateAlphaearthEnabled) {
      setStateDiscoveryError('AlphaEarth setting does not match the trained model feature schema. Use the same AlphaEarth setting that was selected during training.');
      return;
    }
    setStateDiscoveryError('');
    setStateDiscoveryBusy(true);
    setStateDiscoveryError('');
    setStateDiscoveryProgress(0);
    setStateDiscoveryMessage('Queueing state-wide candidate search...');
    try {
      const { job_id } = await startStateDiscovery({
        state: selectedState,
        date_from: dateFrom,
        date_to: dateTo,
        cloud_threshold: state.cloudThreshold,
        ndvi_threshold: state.ndviThreshold,
        alphaearth_enabled: stateAlphaearthEnabled,
        model_id: state.modelId,
        min_field_area_ha: minFieldAreaHa,
      });
      const done = await pollUntilDone(job_id, job => {
        setStateDiscoveryProgress(job.progress);
        setStateDiscoveryMessage(job.message);
      });
      const result = done.result as unknown as StateDiscoveryResult;
      setStateDiscoveryResult(result);
      updateParam('classifyJobId', job_id);
      updateParam('predictions', result.fields);
      updateParam('activeLayer', 'brinjal');
      const probability = await getProbabilityLayer(job_id);
      updateParam('probabilityLayer', probability);
      setFocusFieldId(null);
      setActiveTab('results');
      toast.success(result.message);
    } catch (error) {
      const message = getApiErrorMessage(error, 'State discovery failed.');
      setStateDiscoveryError(message);
      toast.error(message);
    } finally {
      setStateDiscoveryBusy(false);
      setStateDiscoveryMessage('');
    }
  };

  const handleExport = (format: 'csv' | 'geojson' | 'report') => {
    if (!state.classifyJobId) { toast.error('Run classification first'); return; }
    const url = getExportUrl(state.classifyJobId, format);
    const a = document.createElement('a');
    a.href = url; a.download = '';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    toast.success(`Downloading ${format.toUpperCase()}...`);
  };

  const stats = state.statistics;
  const metrics = state.modelMetrics;

  return (
    <div className="analysis-workspace">
      {/* Left sidebar */}
      <aside className="analysis-controls">
        {/* Header */}
        <div style={{ padding: '20px 18px 0' }}>
          <h1 style={{ fontFamily: 'Outfit, sans-serif', fontSize: 18, fontWeight: 700, color: 'var(--clr-text)', marginBottom: 2 }}>
            BRINJAL FIELD DISCOVERY
          </h1>
          <p style={{ fontSize: 11, color: 'var(--clr-text-dim)' }}>Sentinel-2 imagery · Random Forest classification</p>
        </div>

        {/* State discovery: primary workflow, independent from coordinate AOIs. */}
        <div ref={discoverySectionRef} className="section" style={{ marginTop: 12 }}>
          <div className="section-title"><div className="section-title-accent" />Find candidate brinjal fields</div>
          <div className="form-group">
            <label className="form-label">Country</label>
            <input className="form-input" value="India" readOnly aria-readonly="true" />
          </div>
          <div className="form-group">
            <label className="form-label">State</label>
            <select className="form-select" value={selectedState} onChange={event => setSelectedState(event.target.value)} disabled={!discoveryStates.length || stateDiscoveryBusy}>
              <option value="">Select State</option>
              {discoveryStates.map(name => <option key={name} value={name}>{name}</option>)}
            </select>
            {stateDiscoveryError && !stateDiscoveryBusy && <div className="notice notice-muted" role="alert" style={{ marginTop: 6 }}>{stateDiscoveryError}</div>}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="form-group" style={{ marginBottom: 8 }}>
              <label className="form-label">Analysis From</label>
              <input type="date" className="form-input" value={dateFrom} onChange={event => setDateFrom(event.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 8 }}>
              <label className="form-label">Analysis To</label>
              <input type="date" className="form-input" value={dateTo} onChange={event => setDateTo(event.target.value)} />
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="form-group">
              <label className="form-label">Cloud threshold (%)</label>
              <input type="number" min="0" max="100" className="form-input" value={state.cloudThreshold} onChange={event => updateParam('cloudThreshold', Number(event.target.value))} />
            </div>
            <div className="form-group">
              <label className="form-label">NDVI threshold (Detailed AOI)</label>
              <input type="number" min="0" max="1" step="0.01" className="form-input" value={state.ndviThreshold} onChange={event => updateParam('ndviThreshold', Number(event.target.value))} />
            </div>
          </div>
          <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 11, color: 'var(--clr-text-muted)', marginBottom: 10 }}>
            <input type="checkbox" checked={stateAlphaearthEnabled} onChange={event => setStateAlphaearthEnabled(event.target.checked)} />
            <span>Use AlphaEarth embeddings (64 learned dimensions; must match the trained model)</span>
          </label>
          <div className="notice notice-muted" style={{ marginBottom: 8, fontSize: 10 }}>
            Candidate screening only (not confirmed brinjal): healthy-like requires NDVI &ge;0.40, EVI &ge;0.20, SAVI &ge;0.30, NDRE &ge;0.25; young/stressed-like requires NDVI &ge;0.25, EVI &ge;0.10, SAVI &ge;0.20, NDRE &ge;0.15. The young/stressed screen has higher false-positive risk. NDWI and NDBI are features, not screening gates.
          </div>
          <div className="disclaimer" style={{ marginTop: 8, fontSize: 10 }}>
            Initial brinjal candidate screening uses preliminary spectral-index guidance. Candidate regions are not confirmed brinjal cultivation. Final classification requires labelled field data and model validation.
          </div>
          <button className="btn btn-primary btn-block" onClick={handleStateDiscovery} disabled={stateDiscoveryBusy || !selectedState || !discoveryStates.length}>
            {stateDiscoveryBusy ? 'Finding candidate fields...' : 'Find Brinjal Fields'}
          </button>
          {!selectedState && <div className="notice notice-muted" style={{ marginTop: 7 }}>Select a state to search for candidate brinjal fields.</div>}
          <div className="notice notice-muted" style={{ marginBottom: 8 }}>
            Model: <strong>{state.modelId ? 'Ready' : 'Not trained'}</strong>
            {state.modelId && <><br />Model ID: {state.modelId}<br />Feature schema: {state.modelMetrics?.alphaearth_enabled ? 'Sentinel-2 + AlphaEarth embeddings (64)' : 'Sentinel-2 only'}</>}
          </div>
          {stateDiscoveryError && !stateDiscoveryBusy && <div className="notice notice-muted" role="alert" style={{ marginTop: 7 }}>
            {stateDiscoveryError}
            {!state.modelId && <button type="button" className="btn btn-outline btn-sm" style={{ display: 'block', marginTop: 7 }} onClick={() => {
              updateParam('activeSatelliteSource', 'sentinel2');
              detailedAoiRef.current?.setAttribute('open', '');
              requestAnimationFrame(() => trainingSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
            }}>Go to Model Training</button>}
          </div>}
          {stateDiscoveryBusy && <div style={{ marginTop: 8 }}>
            <div className="progress-bar"><div className="progress-bar-fill" style={{ width: `${stateDiscoveryProgress}%` }} /></div>
            <div className="job-status running" style={{ marginTop: 5, fontSize: 11 }}>{stateDiscoveryMessage}</div>
          </div>}
          <div className="disclaimer" style={{ marginTop: 9, fontSize: 10 }}>
            Model-predicted candidate regions must be validated with representative ground-truth data before being treated as confirmed cultivation. Region outlines are not cadastral farm boundaries.
          </div>
        </div>

        <details ref={detailedAoiRef} style={{ margin: '0 12px 12px', padding: '10px 12px', border: '1px solid var(--clr-glass-border)', borderRadius: 'var(--radius)' }}>
          <summary style={{ cursor: 'pointer', color: 'var(--clr-text-muted)', fontSize: 11, fontWeight: 600 }}>
            Detailed AOI workflow (coordinate / polygon)
          </summary>
        {/* Pipeline steps */}
        <div className="section" style={{ marginTop: 12 }}>
            <div className="section-title"><div className="section-title-accent" />Detailed AOI workflow (coordinate / polygon)</div>
          <div className="pipeline">
            {[
              { num: 1, label: 'AOI & Imagery', done: step1Done },
              { num: 2, label: 'Training Data', done: step2Done },
              { num: 3, label: 'Model Training', done: step3Done },
              { num: 4, label: 'Classification', done: step4Done },
            ].map(s => (
              <div key={s.num} className={`pipeline-step ${s.done ? 'done' : s.num === (!step1Done ? 1 : !step2Done ? 2 : !step3Done ? 3 : 4) ? 'active' : ''}`}>
                <div className="pipeline-num">{s.done ? '?' : s.num}</div>
                {s.label}
              </div>
            ))}
          </div>
        </div>

        {/* AOI */}
        <div className="section">
          <div className="section-title"><div className="section-title-accent" /><MapPin size={13} />Area of Interest</div>
          <label className="form-label">AOI mode</label>
          <select className="form-select" value={aoiMode} onChange={event => {
            const nextMode = event.target.value as typeof aoiMode;
            setAoiMode(nextMode);
            setSelectedPolygon(null);
            setAoiError('');
            if (fileRef.current) fileRef.current.value = '';
          }}>
            <option value="point">Point / Radius</option>
            <option value="draw">Draw Polygon</option>
            <option value="geojson">GeoJSON upload</option>
          </select>
          {aoiMode === 'point' && <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Latitude</label>
                <input className="form-input" value={lat} onChange={event => setLat(event.target.value)} placeholder="22.57" />
              </div>
              <div className="form-group" style={{ marginBottom: 0 }}>
                <label className="form-label">Longitude</label>
                <input className="form-input" value={lon} onChange={event => setLon(event.target.value)} placeholder="88.36" />
              </div>
            </div>
            <div className="form-group" style={{ marginTop: 8 }}>
              <label className="form-label">Radius (km)</label>
              <input className="form-input" value={radiusKm} onChange={event => setRadiusKm(event.target.value)} placeholder="25" />
            </div>
          </>}
          {aoiMode === 'draw' && <div className="notice notice-muted" style={{ marginTop: 8 }}>
            Click at least three map locations, then double-click to finish the polygon.
          </div>}
          {aoiMode === 'geojson' && <div style={{ margin: '8px 0' }}>
            <input ref={fileRef} type="file" accept=".geojson,.json,application/geo+json,application/json" onChange={event => handleGeoJsonFile(event.target.files?.[0])} />
            <div className="notice notice-muted" style={{ marginTop: 6 }}>Import a Polygon, MultiPolygon, Feature, or polygon FeatureCollection.</div>
          </div>}
          {selectedPolygon && <div className="notice notice-muted" style={{ marginTop: 8 }}>
            <strong>Polygon selected</strong><br />Vertices: {polygonVertexCount(selectedPolygon)}
            <button className="btn btn-outline btn-sm" style={{ marginLeft: 8 }} onClick={clearPolygonAOI}>Clear AOI</button>
          </div>}
          {aoiError && <div className="notice notice-muted" role="alert" style={{ marginTop: 8 }}>{aoiError}</div>}
          <label className="form-label" style={{marginTop:10}}>DATA SOURCE</label>
          <select className="form-select" value={source} onChange={event => {
            const next = event.target.value as SatelliteSourceId;
            setSourceFailure(null);
            updateParam('activeSatelliteSource', next);
            const nextLayer = next === 'sentinel2'
              ? state.analyzeResult?.tile_urls.ndvi_url ? 'ndvi' : 'satellite'
              : next === 'landsat'
                ? state.landsatResult?.tile_urls.ndvi_url ? 'landsat_ndvi' : 'satellite'
                : next === 'alphaearth'
                  ? state.alphaEarthResult?.accessible && state.alphaEarthResult.tile_url ? 'alphaearth' : 'satellite'
                  : 'satellite';
            updateParam('activeLayer', nextLayer);
          }}>{(['sentinel2', 'landsat', 'planet', 'alphaearth'] as SatelliteSourceId[]).map(id => {
            const item = sources.find(candidate => candidate.id === id);
            return <option key={id} value={id}>{item?.name || id} {item?.resolution_m ? `? ${item.resolution_m} m` : ''}</option>;
          })}</select>
          <div className="notice notice-muted" style={{ marginTop: 6 }}>
            <div><strong>STATUS</strong> {sourceStatus}</div>
            {source === 'landsat' && <div style={{ marginTop: 3 }}>Landsat multispectral resolution: 30 m</div>}
            {source === 'landsat' && landsatInfo && <div style={{ marginTop: 3 }}>Available sensors: {landsatInfo.sensors.map(sensor => sensor.name).join(', ')}. NDRE is not available.</div>}
            {source === 'landsat' && landsatInfoError && <div style={{ marginTop: 3 }}>{landsatInfoError}</div>}
            {currentSourceFailure && <div style={{ marginTop: 3 }} role="alert">{currentSourceFailure}</div>}
            {source === 'planet' && planetAccess && <div style={{ marginTop: 3 }}>
              {!planetAccess.configured ? planetAccess.error || 'PLANET_API_KEY configuration is required.' : !planetAccess.valid ? planetAccess.error || 'Planet access is unavailable.' : `Access verified${planetAccess.item_types.length ? ` ? ${planetAccess.item_types.join(', ')}` : ''}. Imagery analysis is not available here.`}
            </div>}
            {source === 'planet' && planetError && <div style={{ marginTop: 3 }}>{planetError}</div>}
            {source === 'alphaearth' && state.alphaEarthResult?.error && <div style={{ marginTop: 3 }}>{state.alphaEarthResult.error}</div>}
          </div>
          {sourceError ? <div className="notice notice-muted">{sourceError}</div> : sourceMeta && <div className="notice notice-muted" style={{marginTop:6}}><strong>{sourceMeta.available ? 'Available' : sourceMeta.requires_credentials && !sourceMeta.credential_configured ? 'Credentials required' : 'Unavailable'}</strong> | {sourceMeta.agency} | {sourceMeta.resolution_m} m | revisit {sourceMeta.revisit_days} days<br/>{sourceMeta.description}<br/>{sourceMeta.indices?.length ? 'Indices: '+sourceMeta.indices.join(', ') : ''}{sourceMeta.use_cases?.length ? <><br/>Use cases: {sourceMeta.use_cases.join(', ')}</> : null}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">From</label>
              <input type="date" className="form-input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 0 }}>
              <label className="form-label">To</label>
              <input type="date" className="form-input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
            </div>
          </div>
        </div>

        {/* Step 1 button */}
        <div className="section">
          <button id="analysis-load-btn" className="btn btn-primary btn-block" onClick={runImagery} disabled={isRunning || imageryBusy || planetChecking} style={{ marginBottom: 6 }}>
            {source === 'sentinel2' ? 'Load Sentinel-2 data' : source === 'landsat' ? 'Run Landsat analysis' : source === 'planet' ? 'Check Planet access' : 'Load AlphaEarth embedding'}
          </button>
          {analyzeMsg && (
            <>
              <div className="progress-bar" style={{ marginBottom: 4 }}><div className="progress-bar-fill" style={{ width: `${analyzeProgress}%` }} /></div>
              <div className="job-status running"><div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)', fontSize: 11 }}>{analyzeMsg}</span></div>
            </>
          )}
          {source === 'sentinel2' && step1Done && <div className="job-status completed" style={{ marginTop: 6, fontSize: 11 }}>✓ {state.analyzeResult?.collection_info?.image_count} Sentinel-2 images loaded</div>}
        </div>

        {/* Step 2: training data upload */}
          {source === 'sentinel2' && <div className="section">
            <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', fontSize: 12, color: 'var(--clr-text-muted)' }}>
              <input type="checkbox" checked={alphaearthMlEnabled} onChange={e => setAlphaearthMlEnabled(e.target.checked)} />
              <span>Use AlphaEarth embeddings for ML (64 learned embedding features)<br /><small>Learned dimensions, not spectral bands. Requires real Earth Engine AlphaEarth coverage.</small></span>
            </label>
            <TrainingDataUpload alphaearthEnabled={alphaearthMlEnabled} onTrainingComplete={(jobId, result) => { updateParam('trainingJobId', jobId); if (result) setTrainingResult(jobId, result); }} />
          </div>}

        {/* Steps 3 & 4 */}
        {source === 'sentinel2' && <div ref={trainingSectionRef} className="section">
          <button id="analysis-train-btn" className="btn btn-primary btn-block" style={{ marginBottom: 8 }} onClick={handleTrainModel} disabled={isRunning || !step2Done}>
            <Cpu size={14} /> Step 3: Train Random Forest
          </button>
          {trainMsg && (
            <>
              <div className="progress-bar" style={{ marginBottom: 4 }}><div className="progress-bar-fill" style={{ width: `${trainProgress}%` }} /></div>
              <div className="job-status running"><div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)', fontSize: 11 }}>{trainMsg}</span></div>
            </>
          )}
          {step3Done && <div className="job-status completed" style={{ marginBottom: 8, fontSize: 11 }}>✓ Accuracy: {((metrics?.overall_accuracy ?? 0) * 100).toFixed(1)}%</div>}

          <button id="analysis-classify-btn" className="btn btn-accent btn-block" onClick={handleClassify} disabled={isRunning || !step3Done}>
            🌾 Step 4: Run Brinjal Detection
          </button>
          {classifyMsg && (
            <>
              <div className="progress-bar" style={{ marginBottom: 4 }}><div className="progress-bar-fill" style={{ width: `${classifyProgress}%` }} /></div>
              <div className="job-status running"><div className="job-spinner" /><span style={{ color: 'var(--clr-text-muted)', fontSize: 11 }}>{classifyMsg}</span></div>
            </>
          )}
          {step4Done && <div className="job-status completed" style={{ fontSize: 11 }}>✓ Classification complete</div>}
        </div>}
        {/* Export */}
        {selectedPolygon && <div className="section"><button className="btn btn-outline btn-block btn-sm" onClick={downloadGeoJsonCoordinates}><Download size={11}/> Export AOI vertices (CSV)</button></div>}
        {source === 'sentinel2' && step4Done && (
          <div className="section">
            <div className="section-title"><div className="section-title-accent" /><Download size={12} />Export Results</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {(['csv', 'geojson', 'report'] as const).map(f => (
                <button key={f} className="btn btn-outline btn-block btn-sm" onClick={() => handleExport(f)}>
                  <Download size={11} /> {f.toUpperCase()} {f === 'csv' ? '(Table)' : f === 'geojson' ? '(Spatial)' : '(Report)'}
                </button>
              ))}
            </div>
          </div>
        )}
        </details>
      </aside>

      {/* Map center */}
        <div className="analysis-map">
          <MapView aoiGeometry={selectedPolygon ? { type: 'Feature', properties: {}, geometry: selectedPolygon } : null} drawEnabled={aoiMode === 'draw'} onDrawnAOI={handleDrawnAOI} landsatTileUrl={state.landsatResult?.tile_urls.ndvi_url} landsatTrueColorTileUrl={state.landsatResult?.tile_urls.true_color_url} landsatBounds={state.landsatResult?.aoi_bounds} alphaEarthTileUrl={state.alphaEarthResult?.accessible ? state.alphaEarthResult.tile_url || undefined : undefined} alphaEarthBounds={state.alphaEarthResult?.aoi_bounds || undefined} stateBounds={stateDiscoveryResult?.state_bounds} focusFieldId={focusFieldId} />
        </div>

      {/* Right panel: results */}
      <aside className="analysis-results">
        {/* Tabs */}
        <div style={{ padding: '14px 14px 0' }}>
          <div className="tabs">
            {[
              { key: 'results', label: '📊 Results' },
              { key: 'model',   label: '🤖 Model' },
            ].map(t => (
              <button key={t.key} className={`tab${activeTab === t.key ? ' active' : ''}`}
                onClick={() => setActiveTab(t.key as any)}>{t.label}</button>
            ))}
          </div>
        </div>

        {/* Results tab */}
        {activeTab === 'results' && (
          <div className="fade-in">
            {stateDiscoveryResult && (
              <div className="section">
                <div className="section-title"><div className="section-title-accent" />{stateDiscoveryResult.state} candidate summary</div>
                <div className="stat-grid" style={{ marginBottom: 8 }}>
                  <div className="stat-card"><div className="stat-label">Candidate fields</div><div className="stat-value">{stateDiscoveryResult.candidate_field_count}</div></div>
                  <div className="stat-card"><div className="stat-label">Candidate area</div><div className="stat-value">{stateDiscoveryResult.total_candidate_area_ha.toFixed(2)}<span className="stat-unit"> ha</span></div></div>
                  <div className="stat-card"><div className="stat-label">Average probability</div><div className="stat-value">{stateDiscoveryResult.average_brinjal_probability == null ? 'Unavailable' : `${(stateDiscoveryResult.average_brinjal_probability * 100).toFixed(1)}%`}</div></div>
                </div>
                <div className="notice notice-muted" style={{ marginBottom: 8 }}>
                  High: {stateDiscoveryResult.high_confidence_count} Â· Medium: {stateDiscoveryResult.medium_confidence_count} Â· Low: {stateDiscoveryResult.low_confidence_count}
                  <br />{stateDiscoveryResult.message}
                </div>
                {stateDiscoveryResult.candidate_field_count === 0 ? (
                  <div className="empty-state" style={{ padding: '16px 8px' }}>No candidate brinjal fields were detected for the selected state and analysis period.</div>
                ) : (
                  <>
                    <div className="section-title" style={{ marginTop: 10 }}>Farms</div>
                    <div style={{ maxHeight: 360, overflowY: 'auto' }}>
                      {state.predictions.filter(field => field.field_id).map(field => (
                        <div key={field.field_id} className="stat-card" style={{ marginBottom: 6, padding: 9 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                            <strong>{field.field_id}</strong>
                            <button className="btn btn-outline btn-sm" onClick={() => { setFocusFieldId(field.field_id ?? null); updateParam('activeLayer', 'brinjal'); }}>View</button>
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--clr-text-dim)', marginTop: 4 }}>
                            Possible brinjal-like vegetation · Candidate / pseudo-label · Requires field verification<br />
                            Probability: {(field.brinjal_probability * 100).toFixed(1)}% Â· Area: {(field.area_hectares ?? field.area_ha ?? 0).toFixed(2)} ha<br />
                            Lat: {field.latitude.toFixed(6)} Â· Lon: {field.longitude.toFixed(6)} Â· Confidence: {field.confidence ?? field.confidence_level}
                          </div>
                          {field.feature_values && <details style={{ marginTop: 5, fontSize: 10 }}>
                            <summary style={{ cursor: 'pointer' }}>Sentinel-2 and optional AlphaEarth feature values</summary>
                            <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 180, overflowY: 'auto' }}>
                              {JSON.stringify(field.feature_values, null, 2)}
                            </pre>
                          </details>}
                        </div>
                      ))}
                    </div>
                  </>
                )}
                <div className="disclaimer" style={{ marginTop: 8 }}>{stateDiscoveryResult.validation_note}<br />{stateDiscoveryResult.boundary_note}</div>
              </div>
            )}
            {/* Spectral indices */}
            <div className="section">
              <div className="section-title"><div className="section-title-accent" />Spectral indices</div>
              {source === 'sentinel2' ? state.analyzeResult?.index_stats ? (
                <div className="index-grid">
                  {availableIndices.map(key => {
                    const def = INDEX_DEFINITIONS.find(item => item.key === key);
                    return def ? <IndexCard key={key} def={def} value={state.analyzeResult?.index_stats[def.key] ?? null} /> : null;
                  })}
                </div>
              ) : (
                <div className="notice notice-muted">Run Sentinel-2 analysis to calculate AOI mean index statistics.</div>
              ) : source === 'landsat' ? state.landsatResult ? (
                <>
                  <div className="notice notice-muted" style={{ marginBottom: 8 }}>
                    {state.landsatResult.sensor === 'LC09' ? 'Landsat 9 (LC09)' : state.landsatResult.sensor === 'LC08' ? 'Landsat 8 (LC08)' : `Landsat sensor ${state.landsatResult.sensor}`} ? {state.landsatResult.image_count} images ? {state.landsatResult.date_from} to {state.landsatResult.date_to}
                  </div>
                  <div className="index-grid">
                    {availableIndices.map(key => {
                      const def = INDEX_DEFINITIONS.find(item => item.key === key);
                      const value = state.landsatResult?.index_stats[key as keyof SpectralIndices];
                      return def && typeof value === 'number' && Number.isFinite(value)
                        ? <IndexCard key={key} def={def} value={value} /> : null;
                    })}
                  </div>
                </>
              ) : (
                <div className="notice notice-muted">Run Landsat analysis to load its returned index statistics. Available indices: {landsatInfo?.indices.join(', ') || 'NDVI, EVI, SAVI, NDWI, NDBI'}.</div>
              ) : source === 'alphaearth' ? (
                <div className="notice notice-muted">AlphaEarth is an embedding product. Spectral-index values are not available from this result.</div>
              ) : (
                <div className="notice notice-muted">Planet spectral-index results are not available in this workflow.</div>
              )}
            </div>

            {source === 'alphaearth' && state.alphaEarthResult && (
              <div className="section">
                <div className="section-title"><div className="section-title-accent" />AlphaEarth embedding</div>
                <div className="notice notice-muted">
                  {state.alphaEarthResult.accessible ? <>
                    Source: {state.alphaEarthResult.source}<br />
                    Resolution: {state.alphaEarthResult.resolution_m} m ? Embedding dimensions: {state.alphaEarthResult.embedding_dims}<br />
                    Annual period: {state.alphaEarthResult.annual_period_start} to {state.alphaEarthResult.annual_period_end} (year {state.alphaEarthResult.year})<br />
                    Requested dates: {state.alphaEarthResult.requested_date_from} to {state.alphaEarthResult.requested_date_to}<br />
                    {state.alphaEarthResult.date_selection}<br />
                    AOI bounds: {state.alphaEarthResult.aoi_bounds ? 'returned; map zoomed to AOI' : 'unavailable'} ? Images: {state.alphaEarthResult.n_images} ? Bands: {state.alphaEarthResult.n_embedding_bands}<br />
                    Visualization: {state.alphaEarthResult.visualization_label}. {state.alphaEarthResult.visualization_available ? 'Map tile available.' : state.alphaEarthResult.visualization_message}
                  </> : state.alphaEarthResult.error || 'AlphaEarth is unavailable for this AOI.'}
                </div>
              </div>
            )}
            {source === 'planet' && planetAccess && (
              <div className="section">
                <div className="section-title"><div className="section-title-accent" />Planet access</div>
                <div className="notice notice-muted">
                  {!planetAccess.configured ? planetAccess.error || 'PLANET_API_KEY configuration is required.' : !planetAccess.valid ? planetAccess.error || 'Planet access is unavailable.' : <>Planet API access verified. {planetAccess.item_types.length ? `Available item types: ${planetAccess.item_types.join(', ')}.` : 'No item types were returned.'} Imagery analysis is not available in this workflow.</>}
                </div>
              </div>
            )}

            {/* Area statistics */}
            {source === 'sentinel2' && stats && (
              <div className="section">
                <div className="section-title"><div className="section-title-accent" /><BarChart2 size={12} />Area Statistics</div>
                <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', marginBottom: 10 }}>
                  📅 {stats.date_from} → {stats.date_to} · ☁ ≤{stats.cloud_threshold}% · 🌿 ≥{stats.ndvi_threshold}
                </div>
                <div className="stat-grid" style={{ marginBottom: 10 }}>
                  <div className="stat-card">
                    <div className="stat-label">Total Analyzed</div>
                    <div className="stat-value">{fmt(stats.total_area_ha)}<span className="stat-unit"> ha</span></div>
                    <div className="stat-sub">{fmt(stats.total_area_km2, 3)} km²</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Vegetated</div>
                    <div className="stat-value">{fmt(stats.vegetated_area_ha)}<span className="stat-unit"> ha</span></div>
                    <div className="stat-sub">{fmt(stats.vegetated_area_pct, 1)}% of total</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Low-NDVI</div>
                    <div className="stat-value">{fmt(stats.low_ndvi_area_ha)}<span className="stat-unit"> ha</span></div>
                    <div className="stat-sub">{fmt(stats.low_ndvi_area_pct, 1)}% masked</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Other Crop</div>
                    <div className="stat-value">{fmt(stats.predicted_other_crop_ha)}<span className="stat-unit"> ha</span></div>
                  </div>
                </div>

                {/* Brinjal highlight */}
                <div className="stat-card highlight" style={{ marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div className="stat-label">🍆 Predicted Brinjal Area</div>
                      <div className="stat-value" style={{ fontSize: 28 }}>{fmt(stats.predicted_brinjal_ha)}<span className="stat-unit"> ha</span></div>
                      <div style={{ fontSize: 10, color: 'var(--clr-primary-light)', marginTop: 2 }}>{fmt(stats.predicted_brinjal_pct, 1)}% of analyzed area</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 11, color: 'var(--clr-text-dim)' }}>Fields</div>
                      <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--clr-primary-light)', fontFamily: 'JetBrains Mono, monospace' }}>{stats.num_brinjal_fields}</div>
                    </div>
                  </div>
                </div>

                <div className="stat-card" style={{ marginBottom: 8 }}>
                  <div className="stat-label">Avg Brinjal Confidence</div>
                  <div className="stat-value" style={{ fontSize: 22 }}>{(stats.avg_brinjal_confidence * 100).toFixed(1)}<span className="stat-unit">%</span></div>
                  <div className="progress-bar" style={{ marginTop: 8 }}>
                    <div className="progress-bar-fill" style={{ width: `${stats.avg_brinjal_confidence * 100}%` }} />
                  </div>
                </div>

                <div className="disclaimer">
                  <strong>⚠ Note:</strong> Results are "Predicted Brinjal Fields" from a Random Forest model.
                  Classification depends on training data quality. Not confirmed cultivation.
                </div>
              </div>
            )}

            {source === 'sentinel2' && !stats && !step1Done && (
              <div className="empty-state" style={{ padding: '40px 24px' }}>
                <div className="empty-state-icon">📊</div>
                <div className="empty-state-title">No analysis yet</div>
                <div className="empty-state-desc">Run the pipeline to see spectral indices, scores and classification results.</div>
              </div>
            )}
          </div>
        )}

        {/* Model tab */}
        {activeTab === 'model' && (
          <div className="fade-in">
            {source !== 'sentinel2' ? (
              <div className="notice notice-muted" style={{ margin: 16 }}>Random Forest training and classification are available for Sentinel-2 analyses.</div>
            ) : metrics ? (
              <div className="section">
                <div className="section-title"><div className="section-title-accent" />Model Performance</div>
                <div className="stat-grid" style={{ marginBottom: 12 }}>
                  <div className="stat-card success">
                    <div className="stat-label">Accuracy</div>
                    <div className="stat-value">{(metrics.overall_accuracy * 100).toFixed(1)}<span className="stat-unit">%</span></div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">F1 Score</div>
                    <div className="stat-value">{(metrics.macro_f1 * 100).toFixed(1)}<span className="stat-unit">%</span></div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Training</div>
                    <div className="stat-value">{metrics.n_training_samples}<span className="stat-unit"> px</span></div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">RF Trees</div>
                    <div className="stat-value">{metrics.n_estimators}</div>
                  </div>
                </div>

                <div className="section-title" style={{ marginBottom: 10 }}>Feature Importances</div>
                {Object.entries(metrics.feature_importances)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 12)
                  .map(([feat, imp]) => (
                    <div key={feat} className="feature-bar">
                      <div className="feature-name">{feat}</div>
                      <div className="feature-track">
                        <div className="feature-fill" style={{ width: `${imp * 100}%` }} />
                      </div>
                      <div className="feature-pct">{(imp * 100).toFixed(1)}%</div>
                    </div>
                  ))}
                <div className="disclaimer" style={{ marginTop: 12 }}>
                  <strong>⚠ Note:</strong> Evaluation metrics (accuracy, F1, precision, recall) are calculated on the validation split of the extracted training samples. They represent demonstration model performance on the provided dataset, not guaranteed real-world accuracy.
                </div>
              </div>
            ) : (
              <div className="empty-state" style={{ padding: '40px 24px' }}>
                <div className="empty-state-icon">🤖</div>
                <div className="empty-state-title">No model trained yet</div>
                <div className="empty-state-desc">Upload training data and run the Random Forest trainer to see model metrics here.</div>
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
