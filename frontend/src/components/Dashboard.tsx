import React from 'react';
import Header from './Header';
import ControlPanel from './ControlPanel';
import MapView from './MapView';
import StatisticsPanel from './StatisticsPanel';
import ModelPanel from './ModelPanel';
import ExportPanel from './ExportPanel';

export default function Dashboard() {
  return (
    <div className="app-layout">
      {/* Header */}
      <div className="app-header">
        <Header />
      </div>

      {/* Left sidebar: controls */}
      <aside className="app-sidebar">
        <ControlPanel />
      </aside>

      {/* Centre: map */}
      <main className="app-map">
        <MapView />
      </main>

      {/* Right panel: stats + model */}
      <aside className="app-panel">
        <StatisticsPanel />
        <ModelPanel />
        <ExportPanel />
      </aside>
    </div>
  );
}
