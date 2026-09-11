import React from 'react';
import { DollarSign, ShieldAlert, AlertTriangle, CreditCard } from 'lucide-react';

export default function SummaryCards({ summary }) {
  if (!summary) return null;

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  return (
    <div className="metrics-grid">
      {/* CONFIRMED LOSS */}
      <div className="metric-card danger">
        <div className="metric-header">
          <span>CONFIRMED FINANCIAL LOSS</span>
          <ShieldAlert size={20} color="#ef4444" />
        </div>
        <div className="metric-value">
          {formatCurrency(summary.confirmed_loss_amount)}
        </div>
        <div className="metric-sub">
          {summary.economic_loss_ledger ? summary.economic_loss_ledger.length : 0} proven economic loss entries in ledger
        </div>
      </div>

      {/* POTENTIAL AMOUNT REQUIRING REVIEW */}
      <div className="metric-card warning">
        <div className="metric-header">
          <span>POTENTIAL AMOUNT REQUIRING REVIEW</span>
          <AlertTriangle size={20} color="#f59e0b" />
        </div>
        <div className="metric-value" style={{ color: '#f59e0b' }}>
          {formatCurrency(summary.potential_review_amount)}
        </div>
        <div className="metric-sub">
          Not money lost • Data quality & gateway variance
        </div>
      </div>

      {/* TOTAL GROSS REVENUE */}
      <div className="metric-card">
        <div className="metric-header">
          <span>GROSS REVENUE ANALYZED</span>
          <DollarSign size={20} color="#3b82f6" />
        </div>
        <div className="metric-value">
          {formatCurrency(summary.total_gross_revenue)}
        </div>
        <div className="metric-sub">
          Across {summary.total_transactions} gateway records
        </div>
      </div>

      {/* TOTAL PROCESSING FEES */}
      <div className="metric-card">
        <div className="metric-header">
          <span>GATEWAY FEES PAID</span>
          <CreditCard size={20} color="#8b5cf6" />
        </div>
        <div className="metric-value">
          {formatCurrency(summary.total_fees_paid)}
        </div>
        <div className="metric-sub">
          {summary.total_anomalous_transactions} total flagged records ({summary.high_severity_count} High)
        </div>
      </div>
    </div>
  );
}
