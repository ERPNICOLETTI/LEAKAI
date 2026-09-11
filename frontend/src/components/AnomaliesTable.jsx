import React, { useState } from 'react';
import { Search, ShieldAlert, AlertTriangle, Info, CheckCircle2 } from 'lucide-react';

export default function AnomaliesTable({ transactions }) {
  const [filter, setFilter] = useState('anomalous'); // 'all', 'anomalous', 'confirmed', 'review'
  const [search, setSearch] = useState('');

  if (!transactions || transactions.length === 0) return null;

  const filtered = transactions.filter(tx => {
    const matchesSearch = tx.transaction_id.toLowerCase().includes(search.toLowerCase()) ||
                          (tx.order_id && tx.order_id.toLowerCase().includes(search.toLowerCase())) ||
                          tx.type.toLowerCase().includes(search.toLowerCase());
    if (!matchesSearch) return false;

    if (filter === 'anomalous') return tx.has_anomaly;
    if (filter === 'confirmed') return tx.flags.some(f => f.classification === 'CONFIRMED_LOSS');
    if (filter === 'review') return tx.flags.some(f => f.classification === 'REVIEW_REQUIRED');
    return true;
  });

  const formatCurrency = (val) => {
    const isNeg = val < 0;
    const str = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Math.abs(val));
    return isNeg ? `-${str}` : str;
  };

  const getTypeBadge = (type) => {
    const t = type.toLowerCase();
    let bg = 'rgba(255, 255, 255, 0.08)';
    let color = '#94a3b8';

    if (t === 'sale') { bg = 'rgba(16, 185, 129, 0.12)'; color = '#10b981'; }
    else if (t === 'refund') { bg = 'rgba(239, 68, 68, 0.12)'; color = '#ef4444'; }
    else if (t === 'chargeback') { bg = 'rgba(245, 158, 11, 0.12)'; color = '#f59e0b'; }
    else if (t === 'payout') { bg = 'rgba(59, 130, 246, 0.12)'; color = '#3b82f6'; }

    return (
      <span style={{ 
        padding: '0.2rem 0.55rem', 
        borderRadius: '4px', 
        fontSize: '0.725rem', 
        fontWeight: 700, 
        textTransform: 'uppercase',
        background: bg,
        color: color
      }}>
        {t}
      </span>
    );
  };

  const getClassificationTag = (classification) => {
    if (classification === 'CONFIRMED_LOSS') {
      return <span className="badge badge-high"><ShieldAlert size={12} /> CONFIRMED LOSS</span>;
    }
    return <span className="badge badge-medium"><AlertTriangle size={12} /> REVIEW REQUIRED</span>;
  };

  return (
    <div className="table-container">
      <div className="filter-bar">
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
          <Search size={16} style={{ position: 'absolute', left: '10px', color: 'var(--text-muted)' }} />
          <input 
            type="text" 
            placeholder="Search Tx ID, Order ID, Type..." 
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="search-input"
            style={{ paddingLeft: '32px' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', marginLeft: 'auto' }}>
          <button 
            className={`filter-chip ${filter === 'anomalous' ? 'active' : ''}`}
            onClick={() => setFilter('anomalous')}
          >
            All Leaks ({transactions.filter(t => t.has_anomaly).length})
          </button>
          <button 
            className={`filter-chip ${filter === 'confirmed' ? 'active' : ''}`}
            onClick={() => setFilter('confirmed')}
          >
            Confirmed Losses Only
          </button>
          <button 
            className={`filter-chip ${filter === 'review' ? 'active' : ''}`}
            onClick={() => setFilter('review')}
          >
            Review Required
          </button>
          <button 
            className={`filter-chip ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All ({transactions.length})
          </button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Tx ID</th>
              <th>Order ID</th>
              <th>Date</th>
              <th>Type</th>
              <th>Gross</th>
              <th>Fee</th>
              <th>Net Settlement</th>
              <th>Reconciliation Findings</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
                  No transactions match the selected filters.
                </td>
              </tr>
            ) : (
              filtered.map((tx, idx) => (
                <tr key={`${tx.transaction_id}-${idx}`} className={tx.has_anomaly ? 'anomalous-row' : ''}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-main)', fontWeight: 600 }}>
                    {tx.transaction_id}
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: tx.order_id ? 'var(--text-muted)' : 'var(--danger-red)' }}>
                    {tx.order_id || '— (MISSING)'}
                  </td>
                  <td>{tx.date}</td>
                  <td>{getTypeBadge(tx.type)}</td>
                  <td className="tx-amount">{formatCurrency(tx.gross_amount)}</td>
                  <td className="tx-amount" style={{ color: tx.fee < 0 ? 'var(--danger-red)' : 'var(--text-muted)' }}>
                    {formatCurrency(tx.fee)}
                  </td>
                  <td className="tx-amount" style={{ color: 'var(--accent-blue)' }}>
                    {formatCurrency(tx.net_amount)}
                  </td>
                  <td>
                    {!tx.has_anomaly ? (
                      <span style={{ color: 'var(--success-emerald)', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                        <CheckCircle2 size={14} /> Reconciled
                      </span>
                    ) : (
                      <div>
                        {tx.flags.map((flag, i) => (
                          <div key={i} style={{ marginBottom: i < tx.flags.length - 1 ? '0.5rem' : '0' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                              {getClassificationTag(flag.classification)}
                              <span style={{ fontWeight: 700, fontSize: '0.8rem' }}>{flag.rule_name}</span>
                            </div>
                            <div className="flag-box" style={{ 
                              borderLeftColor: flag.classification === 'CONFIRMED_LOSS' ? 'var(--danger-red)' : 'var(--warning-amber)' 
                            }}>
                              {flag.description}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
