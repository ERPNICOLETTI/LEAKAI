import React, { useState } from 'react';
import { Shield, RefreshCw, FileCheck } from 'lucide-react';
import FileUpload from './components/FileUpload';
import SummaryCards from './components/SummaryCards';
import AnomaliesTable from './components/AnomaliesTable';
import RiskBreakdown from './components/RiskBreakdown';
import './App.css';

const API_BASE_URL = 'http://localhost:8000';

export default function App() {
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileUpload = async (file) => {
    setIsLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/analyze`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || 'Failed to process CSV file.');
      }

      const result = await res.json();
      setData(result);
    } catch (err) {
      setError(err.message || 'Error connecting to LeakAI backend engine.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunDemo = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE_URL}/api/demo`);
      if (!res.ok) {
        const errJson = await res.json();
        throw new Error(errJson.detail || 'Failed to execute demo.');
      }
      const result = await res.json();
      setData(result);
    } catch (err) {
      setError(err.message || 'Backend service unavailable. Make sure FastAPI server is running at localhost:8000.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setData(null);
    setError(null);
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="brand-group">
          <div className="brand-icon">
            <Shield size={24} />
          </div>
          <div>
            <h1 className="brand-title">LeakAI</h1>
            <p className="brand-subtitle">Revenue Leakage & Transaction Reconciliation Engine</p>
          </div>
        </div>

        <div className="header-badge">
          <span className="dot-indicator"></span>
          <span>Ecommerce Audit Engine v2.0 • Deterministic</span>
        </div>
      </header>

      {/* Main Content */}
      <main>
        {!data ? (
          <FileUpload 
            onFileUpload={handleFileUpload} 
            onRunDemo={handleRunDemo} 
            isLoading={isLoading} 
            error={error} 
          />
        ) : (
          <div>
            {/* Report Top Action Bar */}
            <div style={{ 
              display: 'flex', 
              justify: 'space-between', 
              alignItems: 'center', 
              marginBottom: '1.5rem',
              background: 'var(--bg-card)',
              padding: '0.85rem 1.25rem',
              borderRadius: '12px',
              border: '1px solid var(--border-color)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.875rem' }}>
                <FileCheck size={18} color="var(--success-emerald)" />
                <span>Active Report: <strong>{data.filename}</strong></span>
                <span style={{ color: 'var(--text-dim)', fontSize: '0.775rem' }}>• Processed {data.processed_at}</span>
              </div>

              <button className="btn-secondary" onClick={handleReset} style={{ padding: '0.4rem 0.85rem', fontSize: '0.8rem' }}>
                <RefreshCw size={14} /> Upload Another File
              </button>
            </div>

            {/* Metric Summary Cards */}
            <SummaryCards summary={data.summary} />

            {/* Transactions & Anomalies Table */}
            <div style={{ marginBottom: '2.5rem' }}>
              <div className="section-header">
                <h2 className="section-title">Financial Audit Findings</h2>
              </div>
              <AnomaliesTable transactions={data.transactions} />
            </div>

            {/* Risk Breakdown */}
            <div>
              <RiskBreakdown summary={data.summary} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
