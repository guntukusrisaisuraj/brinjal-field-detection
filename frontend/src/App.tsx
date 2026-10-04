import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import AppShell from './components/layout/AppShell';
import LoginPage from './pages/LoginPage';
import GeoLocationPage from './pages/GeoLocationPage';
import SavedLocationsPage from './pages/SavedLocationsPage';
import AnalysisPage from './pages/AnalysisPage';
import SatellitePage from './pages/SatellitePage';
import ProfilePage from './pages/ProfilePage';

import type {
  AppState, AnalyzeResult, TrainingResult, ModelMetrics,
  AreaStatistics, PredictionPoint, ProbabilityLayer, User, SavedLocation,
} from './types';

// ─── Context interface ────────────────────────────────────────────────────────

interface AppContextValue {
  state: AppState;

  // Auth
  login: (user: User) => void;
  logout: () => void;

  // Locations
  addSavedLocation: (loc: SavedLocation) => void;
  removeSavedLocation: (id: string) => void;
  setSavedLocations: (locs: SavedLocation[]) => void;

  // Pipeline
  setAnalyzeResult: (jobId: string, result: AnalyzeResult) => void;
  setTrainingResult: (jobId: string, result: TrainingResult) => void;
  setModelResult: (jobId: string, modelId: string, metrics: ModelMetrics) => void;
  setClassifyResult: (jobId: string, stats: AreaStatistics, preds: PredictionPoint[], layer: ProbabilityLayer) => void;
  updateParam: (key: keyof AppState, value: unknown) => void;
  resetAll: () => void;
}

// ─── Default state ────────────────────────────────────────────────────────────

const defaultState: AppState = {
  // Auth
  user: null,

  // Navigation
  activePage: 'home',

  // Locations
  savedLocations: [],
  activeLocationId: null,

  // Jobs
  analyzeJobId: null,
  trainingJobId: null,
  trainJobId: null,
  classifyJobId: null,
  modelId: null,

  // Results
  analyzeResult: null,
  trainingResult: null,
  modelMetrics: null,
  statistics: null,
  predictions: [],
  probabilityLayer: null,
  spectralIndices: null,
  agriScore: null,

  // Parameters
  cloudThreshold: 20,
  ndviThreshold: 0.25,
  confidenceHighThreshold: 0.75,
  confidenceMediumThreshold: 0.50,
  minFieldAreaHa: 0.05,
  nEstimators: 200,

  // UI
  activeLayer: 'satellite',
  activeSatelliteSource: 'sentinel2',
  isLoading: false,

  // Satellite intelligence
  landsatResult: null,
  alphaEarthResult: null,
};

// ─── Context ──────────────────────────────────────────────────────────────────

export const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}

// ─── Protected route wrapper ──────────────────────────────────────────────────

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { state } = useApp();
  if (!state.user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [state, setState] = useState<AppState>(() => {
    // Restore user session from localStorage
    try {
      const stored = localStorage.getItem('agrisense_user');
      if (stored) {
        const user = JSON.parse(stored) as User;
        return { ...defaultState, user };
      }
    } catch {}
    return defaultState;
  });

  // ── Auth ──────────────────────────────────────────────────────────────────

  const login = useCallback((user: User) => {
    localStorage.setItem('agrisense_user', JSON.stringify(user));
    setState(s => ({ ...s, user }));
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('agrisense_user');
    setState(defaultState);
  }, []);

  // ── Locations ─────────────────────────────────────────────────────────────

  const addSavedLocation = useCallback((loc: SavedLocation) => {
    setState(s => ({ ...s, savedLocations: [loc, ...s.savedLocations] }));
  }, []);

  const removeSavedLocation = useCallback((id: string) => {
    setState(s => ({ ...s, savedLocations: s.savedLocations.filter(l => l.location_id !== id) }));
  }, []);

  const setSavedLocations = useCallback((locs: SavedLocation[]) => {
    setState(s => ({ ...s, savedLocations: locs }));
  }, []);

  // ── Pipeline ──────────────────────────────────────────────────────────────

  const setAnalyzeResult = useCallback((jobId: string, result: AnalyzeResult) => {
    setState(s => ({ ...s, analyzeJobId: jobId, analyzeResult: result }));
  }, []);

  const setTrainingResult = useCallback((jobId: string, result: TrainingResult) => {
    setState(s => ({ ...s, trainingJobId: jobId, trainingResult: result }));
  }, []);

  const setModelResult = useCallback((jobId: string, modelId: string, metrics: ModelMetrics) => {
    setState(s => ({ ...s, trainJobId: jobId, modelId, modelMetrics: metrics }));
  }, []);

  const setClassifyResult = useCallback((jobId: string, stats: AreaStatistics, preds: PredictionPoint[], layer: ProbabilityLayer) => {
    setState(s => ({
      ...s, classifyJobId: jobId,
      statistics: stats, predictions: preds, probabilityLayer: layer,
      activeLayer: layer.count ? 'brinjal_probability' : 'satellite',
    }));
  }, []);

  const updateParam = useCallback((key: keyof AppState, value: unknown) => {
    setState(s => ({ ...s, [key]: value }));
  }, []);

  const resetAll = useCallback(() => setState(s => ({ ...defaultState, user: s.user })), []);

  const ctx: AppContextValue = {
    state,
    login, logout,
    addSavedLocation, removeSavedLocation, setSavedLocations,
    setAnalyzeResult, setTrainingResult, setModelResult, setClassifyResult,
    updateParam, resetAll,
  };

  return (
    <AppContext.Provider value={ctx}>
      <BrowserRouter>
        <Routes>
          {/* Login — no shell */}
          <Route path="/login" element={<LoginPage />} />

          {/* Authenticated pages — inside AppShell */}
          <Route
            path="/home"
            element={
              <RequireAuth>
                <AppShell><GeoLocationPage /></AppShell>
              </RequireAuth>
            }
          />
          <Route
            path="/locations"
            element={
              <RequireAuth>
                <AppShell><SavedLocationsPage /></AppShell>
              </RequireAuth>
            }
          />
          <Route
            path="/analysis"
            element={
              <RequireAuth>
                <AppShell><AnalysisPage /></AppShell>
              </RequireAuth>
            }
          />
          <Route
            path="/satellite"
            element={
              <RequireAuth>
                <AppShell><SatellitePage /></AppShell>
              </RequireAuth>
            }
          />
          <Route
            path="/profile"
            element={
              <RequireAuth>
                <AppShell><ProfilePage /></AppShell>
              </RequireAuth>
            }
          />

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    </AppContext.Provider>
  );
}
