from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from decimal import Decimal

class CanonicalEvent(BaseModel):
    # Core Normalized Fields
    transaction_id: str  # Namespaced canonical ID e.g. "SHOPIFY:tx_101"
    order_id: Optional[str] = None
    date: str
    type: str  # sale, refund, fee, payout, chargeback
    gross_amount: Decimal
    fee: Decimal
    net_amount: Decimal
    currency: str = "USD"
    has_source_fee: bool = True
    has_source_net: bool = True

    # Provenance Metadata
    provider: str  # e.g. "SHOPIFY", "PAYPAL", "GENERIC"
    export_type: str  # e.g. "SHOPIFY_PAYMENTS_TRANSACTIONS", "PAYPAL_ACTIVITY"
    source_file_id: Optional[str] = None
    source_row_number: int
    source_transaction_id: str
    source_order_reference: Optional[str] = None
    source_payout_reference: Optional[str] = None
    source_parent_reference: Optional[str] = None
    adapter_version: str = "1.0.0"

    raw_data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True

class DetectionResult(BaseModel):
    provider_detected: str  # "SHOPIFY", "PAYPAL", "GENERIC", "UNKNOWN"
    export_type_detected: str
    confidence: float  # 0.0 to 1.0
    required_columns_present: List[str] = Field(default_factory=list)
    missing_columns: List[str] = Field(default_factory=list)
    ambiguous_match: bool = False
    details: str = ""
