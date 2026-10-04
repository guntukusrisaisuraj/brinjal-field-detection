/**
 * API service layer – all calls to the FastAPI backend.
 * Extended with new endpoints for locations, landsat, satellite, score.
 */
import axios from 'axios';
import type {
  AnalyzeRequest,
  AreaStatistics,
  HealthStatus,
  Job,
  ModelMetrics,
  PredictionPoint,
  SavedLocation,
  CreateLocationRequest,
  AgriScore,
  LandsatResult,
  AlphaEarthResult,
  SatelliteSource,
  AOI, LandsatInfo, PlanetAccessResult,
  ProbabilityLayer,
} from '../types';

const api = axios.create({
  baseURL: '/api',
  timeout: 120_000,
});

// ─── Health ───────────────────────────────────────────────────────────────

export async function checkHealth(): Promise<HealthStatus> {
  const res = await api.get<HealthStatus>('/health');
  return res.data;
}

// ─── Analyze ─────────────────────────────────────────────────────────────

export async function startAnalysis(request: AnalyzeRequest): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/analyze', request);
  return res.data;
}

export async function startNDVI(request: AnalyzeRequest): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/ndvi', request);
  return res.data;
}

// ─── Job polling ──────────────────────────────────────────────────────────

export async function pollJob(jobId: string): Promise<Job> {
  const res = await api.get<Job>(`/results/${jobId}`);
  return res.data;
}

export function pollUntilDone(
  jobId: string,
  onProgress: (job: Job) => void,
  intervalMs = 2500,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const id = setInterval(async () => {
      try {
        const job = await pollJob(jobId);
        onProgress(job);
        if (job.status === 'completed') {
          clearInterval(id);
          resolve(job);
        } else if (job.status === 'failed') {
          clearInterval(id);
          reject(new Error(job.error ?? 'Job failed'));
        }
      } catch (err) {
        clearInterval(id);
        reject(err);
      }
    }, intervalMs);
  });
}

// ─── Training data ────────────────────────────────────────────────────────

export async function uploadTrainingData(
  analyzeJobId: string,
  geojsonBody: string,
  alphaearthEnabled = false,
): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append('analyze_job_id', analyzeJobId);
  form.append('geojson_body', geojsonBody);
  form.append('alphaearth_enabled', String(alphaearthEnabled));
  form.append('training_data_source', 'demo');
  const res = await api.post<{ job_id: string }>('/training-data', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function uploadTrainingFile(
  analyzeJobId: string,
  file: File,
  alphaearthEnabled = false,
): Promise<{ job_id: string }> {
  const form = new FormData();
  form.append('analyze_job_id', analyzeJobId);
  form.append('file', file);
  form.append('alphaearth_enabled', String(alphaearthEnabled));
  form.append('training_data_source', 'uploaded');
  const res = await api.post<{ job_id: string }>('/training-data', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

// ─── Model training ───────────────────────────────────────────────────────

export async function trainModel(params: {
  analyze_job_id: string;
  training_job_id: string;
  n_estimators: number;
  test_size: number;
  random_state: number;
  alphaearth_enabled?: boolean;
}): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/train', params);
  return res.data;
}

export async function getModelMetrics(trainJobId: string): Promise<ModelMetrics> {
  const res = await api.get<ModelMetrics>(`/model/${trainJobId}`);
  return res.data;
}

// ─── Classification ───────────────────────────────────────────────────────

export async function runClassification(params: {
  analyze_job_id: string;
  model_id: string;
  confidence_high_threshold: number;
  confidence_medium_threshold: number;
  min_field_area_ha: number;
  ndvi_threshold: number;
}): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/classify', params);
  return res.data;
}

export async function getStatistics(classifyJobId: string): Promise<AreaStatistics> {
  const res = await api.get<AreaStatistics>(`/statistics/${classifyJobId}`);
  return res.data;
}

export async function getPredictions(classifyJobId: string): Promise<PredictionPoint[]> {
  const res = await api.get<{ predictions: PredictionPoint[]; count: number }>(
    `/predictions/${classifyJobId}`,
  );
  return res.data.predictions;
}

export async function getProbabilityLayer(classifyJobId: string): Promise<ProbabilityLayer> {
  const res = await api.get<ProbabilityLayer>(`/probability-layer/${classifyJobId}`);
  return res.data;
}

export async function getDiscoveryStates(): Promise<{ country: 'India'; states: string[]; source: string }> {
  const res = await api.get<{ country: 'India'; states: string[]; source: string }>('/state-discovery/states');
  return res.data;
}

export async function startStateDiscovery(params: {
  state: string;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  ndvi_threshold: number;
  alphaearth_enabled: boolean;
  model_id: string;
  min_field_area_ha: number;
}): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/state-discovery/analyze', params);
  return res.data;
}

// ─── Export ───────────────────────────────────────────────────────────────

export function getExportUrl(classifyJobId: string, format: 'csv' | 'geojson' | 'report'): string {
  return `/api/export/${classifyJobId}?format=${format}`;
}

// ─── Locations ────────────────────────────────────────────────────────────

export async function createLocation(req: CreateLocationRequest): Promise<SavedLocation> {
  const res = await api.post<SavedLocation>('/locations', req);
  return res.data;
}

export async function listLocations(userId?: string): Promise<SavedLocation[]> {
  const res = await api.get<{ locations: SavedLocation[]; count: number }>('/locations', {
    params: userId ? { user_id: userId } : {},
  });
  return res.data.locations;
}

export async function getLocation(locationId: string): Promise<SavedLocation> {
  const res = await api.get<SavedLocation>(`/locations/${locationId}`);
  return res.data;
}

export async function updateLocation(
  locationId: string,
  updates: Partial<Pick<SavedLocation, 'status' | 'analyze_job_id' | 'classify_job_id' | 'result_summary'>>,
): Promise<SavedLocation> {
  const res = await api.patch<SavedLocation>(`/locations/${locationId}`, updates);
  return res.data;
}

export async function deleteLocation(locationId: string): Promise<void> {
  await api.delete(`/locations/${locationId}`);
}

export function getLocationExcelUrl(locationId: string): string {
  return `/api/locations/${locationId}/excel`;
}

// ─── Score ────────────────────────────────────────────────────────────────

export async function computeScore(indices: {
  ndvi: number;
  evi?: number;
  savi?: number;
  ndwi?: number;
  ndre?: number;
  ndbi?: number;
}): Promise<AgriScore> {
  const res = await api.post<AgriScore>('/score', indices);
  return res.data;
}

export async function getScoreFormula(): Promise<any> {
  const res = await api.get('/score/formula');
  return res.data;
}

// ─── Landsat ──────────────────────────────────────────────────────────────

export async function startLandsatAnalysis(params: {
  aoi: AOI;
  date_from: string;
  date_to: string;
  cloud_threshold?: number;
}): Promise<{ job_id: string }> {
  const res = await api.post<{ job_id: string }>('/landsat/analyze', params);
  return res.data;
}

export async function getLandsatInfo(): Promise<LandsatInfo> {
  const res = await api.get<LandsatInfo>('/landsat/info');
  return res.data;
}

// ─── Satellite Intelligence ───────────────────────────────────────────────

export async function getSatelliteSources(): Promise<{ sources: SatelliteSource[] }> {
  const res = await api.get<{ sources: SatelliteSource[] }>('/satellite/sources');
  return res.data;
}

export async function checkPlanetAccess(): Promise<PlanetAccessResult> {
  const res = await api.post<PlanetAccessResult>('/satellite/planet/check');
  return res.data;
}

export async function getAlphaEarthEmbedding(params: {
  aoi: AOI;
  date_from: string;
  date_to: string;
}): Promise<AlphaEarthResult> {
  const res = await api.post<AlphaEarthResult>('/satellite/alphaearth', params);
  return res.data;
}

export default api;
