import React from 'react';
import { DollarSign, ShieldAlert, AlertTriangle, CreditCard, Layers } from 'lucide-react';

export default function SummaryCards({ summary }) {
  if (!summary) return null;

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const reviewIssueCount = summary.review_issue_ledger ? summary.review_issue_ledger.length : 0;
  const economicLossCount = summary.economic_loss_ledger ? summary.economic_loss_ledger.length : 0;

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
          {economicLossCount} proven economic loss entries in ledger
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
          {reviewIssueCount} unique review issue ledger items
        </div>
      </div>

      {/* GROSS REVENUE ANALYZED */}
      <div className="metric-card">
        <div className="metric-header">
          <span>GROSS REVENUE ANALYZED</span>
          <DollarSign size={20} color="#3b82f6" />
        </div>
        <div className="metric-value">
          {formatCurrency(summary.total_gross_revenue)}
        </div>
        <div className="metric-sub">
          Across {summary.economic_event_count} unique economic events ({summary.raw_record_count} raw rows)
        </div>
      </div>

      {/* FEES ANALYZED */}
      <div className="metric-card">
        <div className="metric-header">
          <span>FEES ANALYZED</span>
          <CreditCard size={20} color="#8b5cf6" />
        </div>
        <div className="metric-value">
          {formatCurrency(summary.total_fees_paid)}
        </div>
        <div className="metric-sub">
          {summary.total_anomalous_transactions} flagged raw records ({summary.high_severity_count} High)
        </div>
      </div>
    </div>
  );
}
