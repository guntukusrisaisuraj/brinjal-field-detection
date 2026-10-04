import React from 'react';
import { useApp } from '../App';
import { getExportUrl } from '../services/api';
import { toast } from 'react-hot-toast';
import { Download } from 'lucide-react';

export default function ExportPanel() {
  const { state } = useApp();
  const { classifyJobId } = state;

  const handleExport = (format: 'csv' | 'geojson' | 'report') => {
    if (!classifyJobId) {
      toast.error('Run Brinjal Detection first before exporting.');
      return;
    }
    const url = getExportUrl(classifyJobId, format);
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast.success(`Downloading ${format.toUpperCase()} export...`);
  };

  return (
    <div className="section">
      <div className="section-title"><div className="section-title-accent" />Export Results</div>

      {!classifyJobId ? (
        <div style={{ fontSize: 11, color: 'var(--clr-text-dim)', textAlign: 'center', padding: '12px 0' }}>
          Complete the brinjal detection to enable exports.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button className="btn btn-outline btn-block btn-sm" onClick={() => handleExport('csv')}>
            <Download size={12} /> CSV (predictions table)
          </button>
          <button className="btn btn-outline btn-block btn-sm" onClick={() => handleExport('geojson')}>
            <Download size={12} /> GeoJSON (spatial predictions)
          </button>
          <button className="btn btn-outline btn-block btn-sm" onClick={() => handleExport('report')}>
            <Download size={12} /> Summary Report (Markdown)
          </button>
        </div>
      )}

      <div className="disclaimer" style={{ marginTop: 10 }}>
        Exported results are labelled <strong>"Predicted Brinjal"</strong>.
        Treat as model output, not confirmed ground truth.
      </div>
    </div>
  );
}
