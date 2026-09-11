from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class SchemaMappingResult(BaseModel):
    source_columns: List[str] = Field(default_factory=list)
    mapped_fields: Dict[str, str] = Field(default_factory=dict)
    missing_required_fields: List[str] = Field(default_factory=list)
    ambiguous_fields: Dict[str, List[str]] = Field(default_factory=dict)
    unused_columns: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

class FileValidationResult(BaseModel):
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    detected_columns: List[str] = Field(default_factory=list)
    mapped_columns: Dict[str, str] = Field(default_factory=dict)
    row_error_count: int = 0
    valid_row_count: int = 0

class ValidationBlockedResponse(BaseModel):
    status: str = "Analysis blocked: input validation failed."
    validation: FileValidationResult

class AnomalyFlag(BaseModel):
    rule_id: str
    rule_name: str
    severity: str  # HIGH, MEDIUM, LOW
    classification: str  # CONFIRMED_LOSS, REVIEW_REQUIRED
    description: str
    amount_at_risk: float

class EconomicLossItem(BaseModel):
    economic_loss_id: str
    order_id: Optional[str] = None
    transaction_id: str
    rule_id: str
    description: str
    proven_loss_amount: float

class ReviewIssueItem(BaseModel):
    review_issue_id: str
    rule_id: str
    order_id: Optional[str] = None
    transaction_id: Optional[str] = None
    exposure_key: Optional[str] = None
    description: str
    amount_requiring_review: float
    affected_raw_rows: List[str] = Field(default_factory=list)

class TransactionRecord(BaseModel):
    transaction_id: str
    order_id: Optional[str] = None
    date: str
    type: str  # sale, refund, fee, payout, chargeback
    gross_amount: float
    fee: float
    net_amount: float
    currency: str = "USD"
    flags: List[AnomalyFlag] = Field(default_factory=list)
    has_anomaly: bool = False
    raw_data: Dict[str, Any] = Field(default_factory=dict)

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

class CurrencyFinancialSummary(BaseModel):
    currency: str
    total_gross_revenue: float
    total_fees_paid: float
    confirmed_loss_amount: float
    potential_review_amount: float

class AuditSummary(BaseModel):
    raw_record_count: int
    economic_event_count: int
    total_transactions: int
    total_gross_revenue: float
    total_fees_paid: float
    total_anomalous_transactions: int
    confirmed_loss_amount: float
    potential_review_amount: float
    high_severity_count: int
    economic_loss_ledger: List[EconomicLossItem] = Field(default_factory=list)
    review_issue_ledger: List[ReviewIssueItem] = Field(default_factory=list)
    financials_by_currency: List[CurrencyFinancialSummary] = Field(default_factory=list)
    risk_by_type: List[CategoryRisk] = Field(default_factory=list)
    risk_by_rule: List[RuleBreakdown] = Field(default_factory=list)

class AnalysisResponse(BaseModel):
    summary: AuditSummary
    transactions: List[TransactionRecord]
    filename: str
    processed_at: str
    validation: Optional[FileValidationResult] = None
