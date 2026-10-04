/**
 * Global TypeScript types for the AgriSense AI platform.
 */

// ─── Job ────────────────────────────────────────────────────────────────────

export type JobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface Job {
  job_id: string;
  job_type: string;
  status: JobStatus;
  progress: number;
  message: string;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

// ─── User / Auth ─────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  role: 'demo' | 'user' | 'admin';
  created_at: string;
}

// ─── Saved Locations ─────────────────────────────────────────────────────────

export interface SavedLocation {
  location_id: string;
  latitude: number;
  longitude: number;
  name: string;
  radius_km: number;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  ndvi_threshold: number;
  user_id: string;
  status: 'saved' | 'analyzing' | 'complete' | 'failed';
  analyze_job_id: string | null;
  classify_job_id: string | null;
  created_at: string;
  updated_at: string;
  result_summary: AreaStatistics | null;
}

export interface CreateLocationRequest {
  latitude: number;
  longitude: number;
  name?: string;
  radius_km?: number;
  date_from?: string;
  date_to?: string;
  cloud_threshold?: number;
  ndvi_threshold?: number;
  user_id?: string;
}

// ─── AOI ────────────────────────────────────────────────────────────────────

export type PolygonGeometry = GeoJSON.Polygon | GeoJSON.MultiPolygon;
export type AOIGeoJSON =
  | PolygonGeometry
  | GeoJSON.Feature<PolygonGeometry>
  | GeoJSON.FeatureCollection<PolygonGeometry>;

export interface AOI {
  state?: string;
  district?: string;
  latitude?: number;
  longitude?: number;
  radius_km?: number;
  geojson?: AOIGeoJSON | null;
}

export interface AnalyzeRequest {
  aoi: AOI;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  ndvi_threshold: number;
  scale_meters: number;
}

export interface AnalyzeResult {
  analyze_job_id: string;
  collection_info: {
    image_count: number;
    date_range: { first: string; last: string } | null;
    dates: string[];
  };
  tile_urls: {
    ndvi_url: string;
    mask_url: string;
  };
  index_stats: SpectralIndices;
  aoi_bounds: GeoJSON.Feature;
  ndvi_threshold: number;
  cloud_threshold: number;
  date_from: string;
  date_to: string;
  scale_meters: number;
}

// ─── Spectral Indices ────────────────────────────────────────────────────────

export interface SpectralIndices {
  NDVI?: number | null;
  EVI?: number | null;
  NDWI?: number | null;
  SAVI?: number | null;
  NDBI?: number | null;
  NDRE?: number | null;
}

export interface IndexDefinition {
  key: keyof SpectralIndices;
  name: string;
  formula: string;
  description: string;
  range: [number, number];
  goodRange: [number, number];
  color: string;
}

export const INDEX_DEFINITIONS: IndexDefinition[] = [
  {
    key: 'NDVI',
    name: 'NDVI',
    formula: '(NIR − RED) / (NIR + RED)',
    description: 'Normalized Difference Vegetation Index — measures live green vegetation density.',
    range: [-1, 1],
    goodRange: [0.3, 0.8],
    color: '#10B981',
  },
  {
    key: 'EVI',
    name: 'EVI',
    formula: '2.5 × (NIR − RED) / (NIR + 6×RED − 7.5×BLUE + 1)',
    description: 'Enhanced Vegetation Index — corrects for atmospheric and soil disturbances.',
    range: [-1, 2],
    goodRange: [0.2, 0.6],
    color: '#34D399',
  },
  {
    key: 'NDWI',
    name: 'NDWI',
    formula: '(GREEN − NIR) / (GREEN + NIR)',
    description: 'Normalized Difference Water Index — highlights water content in vegetation.',
    range: [-1, 1],
    goodRange: [-0.3, 0.1],
    color: '#3B82F6',
  },
  {
    key: 'SAVI',
    name: 'SAVI',
    formula: '((NIR − RED) / (NIR + RED + 0.5)) × 1.5',
    description: 'Soil-Adjusted Vegetation Index — reduces soil brightness influence.',
    range: [-1, 1],
    goodRange: [0.2, 0.5],
    color: '#A78BFA',
  },
  {
    key: 'NDRE',
    name: 'NDRE',
    formula: '(NIR_Narrow − Red_Edge) / (NIR_Narrow + Red_Edge)',
    description: 'Normalized Difference Red Edge — sensitive to chlorophyll and crop health. Sentinel-2 only.',
    range: [-1, 1],
    goodRange: [0.2, 0.5],
    color: '#F59E0B',
  },
  {
    key: 'NDBI',
    name: 'NDBI',
    formula: '(SWIR − NIR) / (SWIR + NIR)',
    description: 'Normalized Difference Built-up Index — identifies impervious/built surfaces.',
    range: [-1, 1],
    goodRange: [-0.5, -0.1],
    color: '#EF4444',
  },
];

// ─── Agricultural Score ──────────────────────────────────────────────────────

export interface ScoreComponent {
  raw_value: number;
  normalised: number;
  weight: number;
  contribution: number;
}

export interface AgriScore {
  score: number;
  grade: 'A' | 'B' | 'C' | 'D';
  label: string;
  components: Record<string, ScoreComponent>;
  formula: string;
  disclaimer: string;
}

// ─── Satellite Sources ────────────────────────────────────────────────────────

export type SatelliteSourceId = 'sentinel2' | 'landsat' | 'planet' | 'alphaearth';

export interface SatelliteSource {
  id: SatelliteSourceId;
  name: string;
  agency: string;
  resolution_m: number;
  bands: number;
  revisit_days: number;
  available: boolean;
  requires_credentials: string;
  credential_configured: boolean;
  collection: string;
  description: string;
  indices?: string[];
  embedding_dims?: number;
  use_cases?: string[];
  credential_note?: string | null;
}

export interface AlphaEarthResult {
  accessible: boolean;
  dataset: string;
  source: string;
  resolution_m: number;
  embedding_dims: number;
  year: number;
  annual_period_start: string;
  annual_period_end: string;
  requested_date_from: string;
  requested_date_to: string;
  date_selection: string;
  tile_url: string | null;
  visualization_label: string;
  visualization_available: boolean;
  visualization_message: string | null;
  aoi_bounds: GeoJSON.Polygon | null;
  n_images: number;
  n_embedding_bands: number;
  band_names: string[];
  error: string | null;
}

export interface LandsatResult {
  image_count: number;
  sensor: string;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  tile_urls: { ndvi_url: string; true_color_url?: string };
  index_stats: SpectralIndices;
  aoi_bounds: GeoJSON.Polygon;
}

export interface LandsatInfo {
  sensors: Array<{
    id: string;
    name: string;
    collection: string;
    launch_date: string;
    resolution_m: number;
    bands: Record<string, string>;
    revisit_days: number;
  }>;
  indices: string[];
  note: string;
}

export interface PlanetAccessResult {
  configured: boolean;
  valid: boolean;
  item_types: string[];
  quota_used: string | null;
  error: string | null;
}

// ─── Training ───────────────────────────────────────────────────────────────

export type CropClass =
  | 'brinjal'
  | 'other_crop'
  | 'bare_soil'
  | 'built_up'
  | 'water'
  | 'other_vegetation';

export const CROP_CLASS_COLORS: Record<CropClass, string> = {
  brinjal: '#8B5CF6',
  other_crop: '#10B981',
  bare_soil: '#D97706',
  built_up: '#EF4444',
  water: '#3B82F6',
  other_vegetation: '#6B7280',
};

export const CROP_CLASS_LABELS: Record<CropClass, string> = {
  brinjal: 'Brinjal',
  other_crop: 'Other Crop',
  bare_soil: 'Bare Soil',
  built_up: 'Built-up',
  water: 'Water',
  other_vegetation: 'Other Vegetation',
};

export interface TrainingPolygon {
  id: string;
  geometry: GeoJSON.Geometry;
  crop_class: CropClass;
  label?: string;
}

export interface TrainingResult {
  training_job_id: string;
  n_samples: number;
  class_counts: Array<{ class_name: string; count: number }>;
  feature_names: string[];
  alphaearth_enabled?: boolean;
  alphaearth_collection?: string;
  alphaearth_dimensions?: number;
  alphaearth_feature_names?: string[];
}

// ─── Model ───────────────────────────────────────────────────────────────────

export interface ClassMetrics {
  crop_class: string;
  precision: number;
  recall: number;
  f1_score: number;
  support: number;
}

export interface ModelMetrics {
  model_id: string;
  model_type: string;
  n_estimators: number;
  overall_accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  n_training_samples: number;
  n_validation_samples: number;
  class_metrics: ClassMetrics[];
  confusion_matrix: number[][];
  class_names: string[];
  feature_importances: Record<string, number>;
  trained_at: string;
  alphaearth_enabled?: boolean;
  alphaearth_collection?: string;
  alphaearth_dimensions?: number;
  alphaearth_feature_names?: string[];
  feature_sources?: string[];
  model_comparison?: null | {
    evaluation_label: string;
    model_a: Record<string, string | number | string[]>;
    model_b: Record<string, string | number | string[]>;
  };
}

// ─── Classification ───────────────────────────────────────────────────────

export interface AreaStatistics {
  total_area_ha: number;
  total_area_km2: number;
  vegetated_area_ha: number;
  vegetated_area_pct: number;
  low_ndvi_area_ha: number;
  low_ndvi_area_pct: number;
  predicted_brinjal_ha: number;
  predicted_brinjal_pct: number;
  predicted_other_crop_ha: number;
  num_brinjal_fields: number;
  avg_brinjal_confidence: number;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  ndvi_threshold: number;
}

export interface PredictionPoint {
  latitude: number;
  longitude: number;
  predicted_class: string;
  brinjal_probability: number;
  confidence_level: 'high' | 'medium' | 'low';
  ndvi: number | null;
  is_low_ndvi: boolean;
  date: string;
  field_id?: string;
  area_ha?: number;
  area_hectares?: number;
  confidence?: 'high' | 'medium' | 'low';
  geometry?: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  geometry_source?: string;
  label_source?: 'spectral_pseudo_label' | 'ground_truth' | 'random_forest_prediction' | string;
  label_type?: string;
  prediction_source?: string;
  screening_class?: 0 | 1 | 2 | null;
  screening_class_name?: string;
  feature_values?: Record<string, number>;
  extended_index_statistics?: Record<string, {
    min: number | null;
    max: number | null;
    mean: number | null;
    median: number | null;
    std: number | null;
    status: string;
  }>;
  mdlca_status?: string;
}

export interface StateDiscoveryResult {
  job_id: string;
  state: string;
  state_bounds: GeoJSON.Polygon;
  candidate_field_count: number;
  total_candidate_area_ha: number;
  average_brinjal_probability: number | null;
  high_confidence_count: number;
  medium_confidence_count: number;
  low_confidence_count: number;
  date_from: string;
  date_to: string;
  cloud_threshold: number;
  min_field_area_ha: number;
  feature_sources: string[];
  alphaearth_enabled: boolean;
  alphaearth_year: number | null;
  candidate_source: string;
  candidate_screening_guidance: {
    purpose: string;
    healthy_rule: Record<string, number>;
    young_stressed_rule: Record<string, number>;
    young_stressed_false_positive_risk: string;
    ndwi_ndbi_are_screening_gates: boolean;
  };
  boundary_note: string;
  validation_note: string;
  message: string;
  fields: PredictionPoint[];
}

export interface ProbabilityLayerPoint {
  latitude: number;
  longitude: number;
  probability: number;
}

export interface ProbabilityLayer {
  job_id: string;
  layer_type: 'brinjal_probability';
  bounds: { south: number; west: number; north: number; east: number } | null;
  points: ProbabilityLayerPoint[];
  count: number;
  source: 'random_forest_prediction_records';
}

// ─── App State ───────────────────────────────────────────────────────────────

export interface AppState {
  // Auth
  user: User | null;

  // Navigation
  activePage: string;

  // Saved locations
  savedLocations: SavedLocation[];
  activeLocationId: string | null;

  // Pipeline step tracking
  analyzeJobId: string | null;
  trainingJobId: string | null;
  trainJobId: string | null;
  classifyJobId: string | null;
  modelId: string | null;

  // Results
  analyzeResult: AnalyzeResult | null;
  trainingResult: TrainingResult | null;
  modelMetrics: ModelMetrics | null;
  statistics: AreaStatistics | null;
  predictions: PredictionPoint[];
  probabilityLayer: ProbabilityLayer | null;
  spectralIndices: SpectralIndices | null;
  agriScore: AgriScore | null;

  // Parameters
  cloudThreshold: number;
  ndviThreshold: number;
  confidenceHighThreshold: number;
  confidenceMediumThreshold: number;
  minFieldAreaHa: number;
  nEstimators: number;

  // UI
  activeLayer: string;
  activeSatelliteSource: SatelliteSourceId;
  isLoading: boolean;

  // Satellite intelligence
  landsatResult: LandsatResult | null;
  alphaEarthResult: AlphaEarthResult | null;
}

// ─── Health ───────────────────────────────────────────────────────────────

export interface HealthStatus {
  status: string;
  gee_authenticated: boolean;
  version: string;
  message: string;
}
