import React from 'react';
import { ShieldAlert, AlertTriangle } from 'lucide-react';

export default function RiskBreakdown({ summary }) {
  if (!summary) return null;

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const confirmedRules = summary.risk_by_rule.filter(r => r.classification === 'CONFIRMED_LOSS');
  const reviewRules = summary.risk_by_rule.filter(r => r.classification === 'REVIEW_REQUIRED');

  return (
    <div className="breakdown-grid">
      {/* Confirmed Loss Rules */}
      <div className="breakdown-card" style={{ borderColor: 'rgba(239, 68, 68, 0.3)' }}>
        <div className="section-header" style={{ marginBottom: '1rem' }}>
          <div className="section-title" style={{ color: 'var(--danger-red)' }}>
            <ShieldAlert size={18} color="var(--danger-red)" /> Confirmed Revenue Loss Rules
          </div>
        </div>

        <div>
          {confirmedRules.map((rule) => {
            const pct = summary.confirmed_loss_amount > 0 
              ? Math.min(100, (rule.risk_amount / summary.confirmed_loss_amount) * 100) 
              : 0;

            return (
              <div key={rule.rule_id} className="breakdown-item" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.4rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                  <span style={{ fontWeight: 600 }}>{rule.rule_name}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: rule.count > 0 ? 'var(--danger-red)' : 'var(--text-muted)' }}>
                    {formatCurrency(rule.risk_amount)} ({rule.count} event{rule.count === 1 ? '' : 's'})
                  </span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ 
                    height: '100%', 
                    width: `${pct}%`, 
                    background: rule.count > 0 ? 'var(--danger-red)' : 'transparent',
                    transition: 'width 0.3s ease'
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Review Required Rules */}
      <div className="breakdown-card" style={{ borderColor: 'rgba(245, 158, 11, 0.3)' }}>
        <div className="section-header" style={{ marginBottom: '1rem' }}>
          <div className="section-title" style={{ color: 'var(--warning-amber)' }}>
            <AlertTriangle size={18} color="var(--warning-amber)" /> Potential Risk / Review Required Rules
          </div>
        </div>

        <div>
          {reviewRules.map((rule) => {
            const pct = summary.potential_risk_amount > 0 
              ? Math.min(100, (rule.risk_amount / summary.potential_risk_amount) * 100) 
              : 0;

            return (
              <div key={rule.rule_id} className="breakdown-item" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '0.4rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                  <span style={{ fontWeight: 600 }}>{rule.rule_name}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: rule.count > 0 ? 'var(--warning-amber)' : 'var(--text-muted)' }}>
                    {formatCurrency(rule.risk_amount)} ({rule.count} event{rule.count === 1 ? '' : 's'})
                  </span>
                </div>
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.06)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ 
                    height: '100%', 
                    width: `${pct}%`, 
                    background: rule.count > 0 ? 'var(--warning-amber)' : 'transparent',
                    transition: 'width 0.3s ease'
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
