from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class AnomalyFlag(BaseModel):
    rule_id: str
    rule_name: str
    severity: str  # HIGH, MEDIUM, LOW
    classification: str  # CONFIRMED_LOSS, REVIEW_REQUIRED
    description: str
    amount_at_risk: float

class TransactionRecord(BaseModel):
    transaction_id: str
    order_id: Optional[str] = None
    date: str
    type: str  # sale, refund, fee, payout, chargeback
    gross_amount: float
    fee: float
    net_amount: float
    currency: str = "USD"
    flags: List[AnomalyFlag] = []
    has_anomaly: bool = False
    raw_data: Dict[str, Any] = {}

class CategoryRisk(BaseModel):
    category: str
    risk_amount: float
    count: int

class RuleBreakdown(BaseModel):
    rule_id: str
    rule_name: str
    classification: str
    count: int
    risk_amount: float

class AuditSummary(BaseModel):
    total_transactions: int
    total_gross_revenue: float
    total_fees_paid: float
    total_anomalous_transactions: int
    confirmed_loss_amount: float
    potential_risk_amount: float
    high_severity_count: int
    risk_by_type: List[CategoryRisk]
    risk_by_rule: List[RuleBreakdown]

class AnalysisResponse(BaseModel):
    summary: AuditSummary
    transactions: List[TransactionRecord]
    filename: str
    processed_at: str
