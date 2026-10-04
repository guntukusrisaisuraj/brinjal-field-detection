import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Layers, Leaf, Map as MapIcon, CircleDot } from 'lucide-react';
import { useApp } from '../App';

// Fix Leaflet default marker icons
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

const PREDICTION_COLORS: Record<string, string> = {
  brinjal: '#8B5CF6',
  other_crop: '#10B981',
  bare_soil: '#D97706',
  built_up: '#EF4444',
  water: '#3B82F6',
  other_vegetation: '#6B7280',
  low_vegetation: '#374151',
  unknown: '#9CA3AF',
};

interface MapViewProps { aoiGeometry?: GeoJSON.Feature | GeoJSON.FeatureCollection | null; drawEnabled?: boolean; onDrawnAOI?: (feature: GeoJSON.Feature | null) => void; landsatTileUrl?: string; landsatTrueColorTileUrl?: string; landsatBounds?: GeoJSON.Polygon; alphaEarthTileUrl?: string; alphaEarthBounds?: GeoJSON.Polygon | null; stateBounds?: GeoJSON.Polygon | null; focusFieldId?: string | null; }
export default function MapView({ aoiGeometry, drawEnabled = false, onDrawnAOI, landsatTileUrl, landsatTrueColorTileUrl, landsatBounds, alphaEarthTileUrl, alphaEarthBounds, stateBounds, focusFieldId }: MapViewProps) {
  const mapRef = useRef<L.Map | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const tilesRef = useRef<Record<string, L.TileLayer>>({});
  const markersRef = useRef<L.LayerGroup | null>(null);
  const probabilityRef = useRef<L.LayerGroup | null>(null);
  const aoiLayerRef = useRef<L.GeoJSON | null>(null);
  const drawPointsRef = useRef<L.LatLng[]>([]);
  const drawLineRef = useRef<L.Polyline | null>(null);
  const { state, updateParam } = useApp();
  const { activeLayer, analyzeResult, predictions, probabilityLayer, classifyJobId, activeSatelliteSource } = state;
  const hasActiveRaster = activeSatelliteSource === 'sentinel2' ? !!analyzeResult?.tile_urls?.ndvi_url : activeSatelliteSource === 'landsat' ? !!landsatTileUrl : activeSatelliteSource === 'alphaearth' ? !!alphaEarthTileUrl : false;
  const layerChoices = [{id:'satellite',label:'Satellite',color:'#6B7280',icon:<MapIcon size={13}/>}, ...(activeSatelliteSource === 'sentinel2' ? [{id:'ndvi',label:'NDVI',color:'#557b45',icon:<Leaf size={13}/>},{id:'ndvi_mask',label:'NDVI mask',color:'#3B82F6',icon:<Layers size={13}/>}]: activeSatelliteSource === 'landsat' ? [{id:'landsat_ndvi',label:'Landsat NDVI',color:'#557b45',icon:<Leaf size={13}/>}, ...(landsatTrueColorTileUrl ? [{id:'landsat_true_color',label:'Landsat true color',color:'#849b63',icon:<Layers size={13}/>}]:[])]: activeSatelliteSource === 'alphaearth' && alphaEarthTileUrl ? [{id:'alphaearth',label:'AlphaEarth Embedding',color:'#64748b',icon:<Layers size={13}/>}]:[]), ...(probabilityLayer?.count ? [{id:'brinjal_probability',label:'Brinjal Probability',color:'#E0A442',icon:<CircleDot size={13}/>}]:[]), ...(predictions.length ? [{id:'brinjal',label:'Prediction markers',color:'#80633e',icon:<CircleDot size={13}/>}]:[])];
  const visibleActiveLayer = layerChoices.some(layer => layer.id === activeLayer) ? activeLayer : 'satellite';

  // ─── Init map ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [20.5937, 78.9629], // India centre
      zoom: 5,
      zoomControl: true,
    });

    // Base: satellite tiles (ESRI)
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      {
        attribution: 'Tiles © Esri, Maxar, Earthstar Geographics',
        maxZoom: 18,
      }
    ).addTo(map);

    // India boundary overlay
    fetch('https://raw.githubusercontent.com/datameet/maps/master/Country/india-composite.geojson')
      .then(r => r.json())
      .then(data => {
        L.geoJSON(data, {
          style: {
            color: '#557b45',
            weight: 1.5,
            fillOpacity: 0,
            dashArray: '4 4',
          },
        }).addTo(map);
      })
      .catch(() => {/* ignore if boundary fetch fails */});

    markersRef.current = L.layerGroup().addTo(map);
    probabilityRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ─── GEE tile layers ──────────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const { ndvi_url, mask_url } = analyzeResult?.tile_urls || {};

    // Remove old GEE layers
    Object.values(tilesRef.current).forEach(l => map.removeLayer(l));
    tilesRef.current = {};

    if (ndvi_url) {
      tilesRef.current['ndvi'] = L.tileLayer(ndvi_url, { opacity: 0.75, maxZoom: 18 });
    }
    if (mask_url) tilesRef.current['ndvi_mask'] = L.tileLayer(mask_url, { opacity: 0.75, maxZoom: 18 });
    if (landsatTileUrl) tilesRef.current['landsat_ndvi'] = L.tileLayer(landsatTileUrl, { opacity: 0.75, maxZoom: 18 });
    if (landsatTrueColorTileUrl) tilesRef.current['landsat_true_color'] = L.tileLayer(landsatTrueColorTileUrl, { opacity: 0.9, maxZoom: 18 });
    if (alphaEarthTileUrl) tilesRef.current['alphaearth'] = L.tileLayer(alphaEarthTileUrl, { opacity: 0.75, maxZoom: 18 });

    // Zoom to AOI
    const sourceBounds = activeSatelliteSource === 'landsat'
      ? landsatBounds
      : activeSatelliteSource === 'alphaearth' ? alphaEarthBounds : analyzeResult?.aoi_bounds;
    if (sourceBounds) {
      try {
        const bounds = (sourceBounds as any)?.coordinates?.[0];
        if (bounds && bounds.length) {
          const latlngs = bounds.map((c: number[]) => [c[1], c[0]] as [number, number]);
          map.fitBounds(L.latLngBounds(latlngs), { padding: [20, 20] });
        }
      } catch { /* ignore */ }
    }
  }, [analyzeResult, landsatTileUrl, landsatTrueColorTileUrl, landsatBounds, alphaEarthTileUrl, alphaEarthBounds, activeSatelliteSource]);

  // ─── Switch active layer ──────────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (visibleActiveLayer !== activeLayer) updateParam('activeLayer', 'satellite');
    Object.entries(tilesRef.current).forEach(([id, layer]) => {
      if (visibleActiveLayer === id) {
        if (!map.hasLayer(layer)) map.addLayer(layer);
      } else {
        if (map.hasLayer(layer)) map.removeLayer(layer);
      }
    });
  }, [activeLayer, activeSatelliteSource, hasActiveRaster, visibleActiveLayer, updateParam]);

  // ─── Prediction markers ───────────────────────────────────────────────
  useEffect(() => {
    const group = markersRef.current;
    if (!group) return;
    group.clearLayers();

    if (!predictions.length || activeLayer !== 'brinjal') return;

    // Cluster as circle markers for performance
    predictions.forEach(p => {
      if (!Number.isFinite(p.latitude) || !Number.isFinite(p.longitude)) return;
      const color = PREDICTION_COLORS[p.predicted_class] ?? '#9CA3AF';
      const probability = Math.max(0, Math.min(1, Number(p.brinjal_probability) || 0));
      const opacity = 0.25 + probability * 0.7;
      const radius = 3 + probability * 7;

      if (p.geometry) {
        L.geoJSON(p.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon, {
          style: {
            color: p.field_id === focusFieldId ? '#FACC15' : color,
            weight: p.field_id === focusFieldId ? 3 : 1.5,
            fillColor: color,
            fillOpacity: p.field_id === focusFieldId ? 0.28 : 0.12,
          },
        }).addTo(group);
      }
      L.circleMarker([p.latitude, p.longitude], {
        radius,
        fillColor: color,
        color: '#fff',
        weight: 0.5,
        fillOpacity: opacity,
      })
        .bindPopup(
          `<div style="font-size:12px;line-height:1.6">
            <b style="color:${color}">${p.field_id ? 'CANDIDATE BRINJAL FIELD' : p.predicted_class.replace('_', ' ').toUpperCase()}</b><br/>
            ${p.field_id ? `Field ID: <b>${p.field_id}</b><br/>Area: ${Number(p.area_hectares ?? p.area_ha).toFixed(2)} ha<br/>` : ''}
            Brinjal prob: <b>${(p.brinjal_probability * 100).toFixed(1)}%</b><br/>
            Confidence: <span style="text-transform:capitalize">${p.confidence_level}</span><br/>
            ${p.ndvi == null ? '' : `NDVI: ${p.ndvi.toFixed(3)}<br/>`}
            Lat: ${p.latitude.toFixed(5)}, Lon: ${p.longitude.toFixed(5)}
          </div>`
        )
        .addTo(group);
    });
  }, [predictions, activeLayer, focusFieldId]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !stateBounds) return;
    const ring = stateBounds.coordinates?.[0];
    if (!ring?.length) return;
    const latlngs = ring.map(([longitude, latitude]) => [latitude, longitude] as [number, number]);
    map.fitBounds(L.latLngBounds(latlngs), { padding: [24, 24] });
  }, [stateBounds]);
  useEffect(() => {
    const map = mapRef.current;
    const field = predictions.find(item => item.field_id === focusFieldId);
    if (!map || !field) return;
    map.setView([field.latitude, field.longitude], Math.max(map.getZoom(), 15));
  }, [focusFieldId, predictions]);
  useEffect(() => {
    const group = probabilityRef.current;
    if (!group) return;
    group.clearLayers();
    if (!probabilityLayer?.points.length || activeLayer !== 'brinjal_probability') return;
    const renderer = L.canvas({ padding: 0.5 });
    probabilityLayer.points.forEach(point => {
      const probability = Math.max(0, Math.min(1, point.probability));
      const color = `hsl(${probability * 120}, 72%, 42%)`;
      L.circleMarker([point.latitude, point.longitude], {
        renderer, radius: 4, color, weight: 0.5,
        fillColor: color, fillOpacity: 0.25 + probability * 0.7,
      }).bindPopup(
        `<b>Predicted Brinjal Probability</b><br/>Model probability: ${(probability * 100).toFixed(1)}%<br/>Lat: ${point.latitude.toFixed(5)}, Lon: ${point.longitude.toFixed(5)}<br/><small>Model prediction; not ground truth.</small>`
      ).addTo(group);
    });
  }, [probabilityLayer, activeLayer]);
  useEffect(() => { const map=mapRef.current; if(!map)return; if(aoiLayerRef.current)map.removeLayer(aoiLayerRef.current); aoiLayerRef.current=aoiGeometry?L.geoJSON(aoiGeometry,{style:{color:'#fff',weight:4,opacity:.95,fillColor:'#6b8d5b',fillOpacity:.12}}).addTo(map):null; if(aoiLayerRef.current){try{map.fitBounds(aoiLayerRef.current.getBounds(),{padding:[30,30],maxZoom:15});}catch{}} },[aoiGeometry]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const clearSketch = () => {
      drawPointsRef.current = [];
      drawLineRef.current?.remove();
      drawLineRef.current = null;
    };
    if (drawEnabled) map.doubleClickZoom.disable();
    else {
      map.doubleClickZoom.enable();
      clearSketch();
    }
    const drawLine = () => {
      drawLineRef.current?.remove();
      if (drawPointsRef.current.length > 1) {
        drawLineRef.current = L.polyline(drawPointsRef.current, {
          color: '#fff', weight: 3, dashArray: '5 5',
        }).addTo(map);
      }
    };
    const handleClick = (event: L.LeafletMouseEvent) => {
      if (!drawEnabled) return;
      drawPointsRef.current.push(event.latlng);
      drawLine();
    };
    const handleDoubleClick = (event: L.LeafletMouseEvent) => {
      if (!drawEnabled) return;
      event.originalEvent.preventDefault();
      const points = drawPointsRef.current;
      while (points.length > 1) {
        const last = points[points.length - 1];
        const previous = points[points.length - 2];
        if (Math.abs(last.lat - previous.lat) >= 1e-10 || Math.abs(last.lng - previous.lng) >= 1e-10) break;
        points.pop();
      }
      if (points.length < 3) return;
      const ring: GeoJSON.Position[] = points.map(point => [point.lng, point.lat]);
      ring.push([...ring[0]]);
      onDrawnAOI?.({
        type: 'Feature',
        properties: {},
        geometry: { type: 'Polygon', coordinates: [ring] },
      });
      clearSketch();
    };
    map.on('click', handleClick);
    map.on('dblclick', handleDoubleClick);
    return () => {
      map.off('click', handleClick);
      map.off('dblclick', handleDoubleClick);
      map.doubleClickZoom.enable();
      clearSketch();
    };
  }, [drawEnabled, onDrawnAOI]);

  return (
    <div style={{ height: '100%', position: 'relative' }}>
      <div ref={containerRef} style={{ height: '100%', width: '100%' }} />

      {/* Layer toggles */}
      <div className="map-overlay-controls">
        {layerChoices.map(l => (
          <button
            key={l.id}
            className={`layer-toggle ${visibleActiveLayer === l.id ? 'active' : ''}`}
            disabled={l.id !== 'satellite' && !hasActiveRaster && l.id !== 'brinjal' && l.id !== 'brinjal_probability'}
            onClick={() => updateParam('activeLayer', l.id)}
          >
            {l.icon}
            <div className="layer-dot" style={{ background: l.color }} />
            {l.label}
          </button>
        ))}
      </div>

      {/* NDVI legend */}
      {(activeLayer === 'ndvi' || activeLayer === 'ndvi_mask' || activeLayer === 'landsat_ndvi') && (
        <div style={{ position: 'absolute', bottom: 24, left: 12, zIndex: 1000 }}>
          <div className="legend fade-in">
            {activeLayer === 'ndvi' || activeLayer === 'landsat_ndvi' ? (
              <>
                <div className="legend-title">{activeLayer === 'landsat_ndvi' ? 'Landsat NDVI' : 'NDVI'}</div>
                <div className="legend-gradient"
                  style={{ background: 'linear-gradient(to right, #d73027, #fdae61, #d9ef8b, #1a9850)' }} />
                <div className="legend-range"><span>-0.2</span><span>0.9</span></div>
                <div className="legend-item" style={{ marginTop: 6, fontSize: 10 }}>
                  Low ← vegetation → High
                </div>
              </>
            ) : (
              <>
                <div className="legend-title">NDVI Mask (threshold: {state.ndviThreshold})</div>
                <div className="legend-item">
                  <div className="legend-swatch" style={{ background: '#d73027' }} />
                  Low/Non-vegetated
                </div>
                <div className="legend-item">
                  <div className="legend-swatch" style={{ background: '#1a9850' }} />
                  Potential vegetation
                </div>
                <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginTop: 4 }}>
                  ⚠ Green ≠ brinjal. Further classification required.
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Brinjal prediction legend */}
      {activeLayer === 'brinjal' && predictions.length > 0 && (
        <div style={{ position: 'absolute', bottom: 24, left: 12, zIndex: 1000 }}>
          <div className="legend fade-in">
            <div className="legend-title">Prediction probability points</div><div className="legend-gradient" style={{background:'linear-gradient(to right, #80633e44, #80633e)'}}/><div className="legend-range"><span>Lower probability</span><span>Higher</span></div>
            {Object.entries(PREDICTION_COLORS).map(([cls, color]) => (
              <div key={cls} className="legend-item">
                <div className="legend-swatch" style={{ background: color, borderRadius: '50%' }} />
                {cls.replace('_', ' ')}
              </div>
            ))}
            <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginTop: 6, borderTop: '1px solid var(--clr-glass-border)', paddingTop: 4 }}>
              Results are "Predicted Brinjal Fields" — not confirmed cultivation.
            </div>
          </div>
        </div>
      )}

      {activeLayer === 'brinjal_probability' && probabilityLayer?.count ? (
        <div style={{ position: 'absolute', bottom: 24, left: 12, zIndex: 1000 }}>
          <div className="legend fade-in">
            <div className="legend-title">Model Brinjal Probability</div>
            <div className="legend-gradient" style={{ background: 'linear-gradient(to right, hsl(0, 72%, 42%), hsl(30, 72%, 42%), hsl(60, 72%, 42%), hsl(90, 72%, 42%), hsl(120, 72%, 42%))' }} />
            <div className="legend-range"><span>Low</span><span>High</span></div>
            <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginTop: 4 }}>Color intensity represents stored model probabilities; visualization ranges only.</div>
            <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginTop: 3 }}>Model output, not confirmed crop presence or validated accuracy.</div>
            <div style={{ fontSize: 9, color: 'var(--clr-text-dim)', marginTop: 3 }}>Demonstration training samples do not establish real-world accuracy.</div>
          </div>
        </div>
      ) : null}

      {classifyJobId && probabilityLayer && !probabilityLayer.count && (
        <div style={{ position: 'absolute', top: 54, left: 12, zIndex: 1000 }}>
          <div className="legend fade-in">No classification results available</div>
        </div>
      )}

      {/* No data hint */}
      {!analyzeResult && !landsatTileUrl && !alphaEarthTileUrl && (
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          background: 'rgba(255,255,255,0.94)', backdropFilter: 'blur(8px)',
          border: '1px solid var(--clr-glass-border)',
          borderRadius: 'var(--radius)', padding: '24px 32px',
          textAlign: 'center', zIndex: 500, pointerEvents: 'none',
        }}>
          <div style={{ marginBottom: 8, color: 'var(--clr-text-muted)' }}><MapIcon size={25} /></div>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--clr-text)', marginBottom: 4 }}>
            No satellite data loaded
          </div>
          <div style={{ fontSize: 11, color: 'var(--clr-text-dim)' }}>
            Select an AOI and imagery source to begin brinjal analysis.
          </div>
        </div>
      )}
    </div>
  );
}
