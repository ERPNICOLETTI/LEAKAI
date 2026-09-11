import React, { useRef, useState } from 'react';
import { UploadCloud, Play, FileText, AlertCircle } from 'lucide-react';

export default function FileUpload({ onFileUpload, onRunDemo, isLoading, error }) {
  const fileInputRef = useRef(null);
  const [isDragActive, setIsDragActive] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      onFileUpload(e.target.files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragActive(true);
  };

  const handleDragLeave = () => {
    setIsDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileUpload(e.dataTransfer.files[0]);
    }
  };

  return (
    <div style={{ marginBottom: '2rem' }}>
      <div 
        className={`upload-card ${isDragActive ? 'drag-active' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleFileChange} 
          accept=".csv" 
          style={{ display: 'none' }} 
        />
        
        <div className="upload-icon-wrapper">
          {isLoading ? <div className="loading-spinner" /> : <UploadCloud size={32} />}
        </div>

        <h2 className="upload-title">
          {isLoading ? 'Analyzing Financial Records...' : 'Upload Transaction CSV'}
        </h2>
        
        <p className="upload-desc">
          Drag and drop your bank or ERP transaction file (CSV format) to run deterministic audit checks.
        </p>

        <div className="btn-group" onClick={(e) => e.stopPropagation()}>
          <button 
            className="btn-primary" 
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading}
          >
            <FileText size={18} /> Select CSV File
          </button>
          
          <button 
            className="btn-secondary" 
            onClick={onRunDemo}
            disabled={isLoading}
          >
            <Play size={18} /> Load Demo Dataset
          </button>
        </div>
      </div>

      {error && (
        <div style={{ 
          marginTop: '1rem', 
          padding: '0.85rem 1.25rem', 
          background: 'rgba(239, 68, 68, 0.15)', 
          border: '1px solid rgba(239, 68, 68, 0.3)', 
          borderRadius: '10px', 
          color: '#ef4444', 
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
