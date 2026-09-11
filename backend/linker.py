from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Set, Tuple
from decimal import Decimal

try:
    from adapters.base import CanonicalEvent
except ImportError:
    from .adapters.base import CanonicalEvent

class CrossProviderLink(BaseModel):
    link_id: str
    shopify_event_id: str
    paypal_event_id: str
    shared_order_reference: str
    currency: str
    matched_amount: float
    confidence: float = 1.0
    link_reason: str

def perform_conservative_cross_provider_linking(events: List[CanonicalEvent]) -> List[CrossProviderLink]:
    """
    Conservative V1 Cross-Provider Linker.
    Only links events between SHOPIFY and PAYPAL when:
    - Both events have non-empty matching normalized merchant order/invoice references (source_order_reference)
    - Both events share the exact same currency
    - Both event types are compatible (e.g. sale to sale, refund to refund)
    Does NOT link by Item ID, does NOT link by amount alone, does NOT link across currencies.
    """
    shopify_by_order: Dict[Tuple[str, str], List[CanonicalEvent]] = {}
    paypal_by_order: Dict[Tuple[str, str], List[CanonicalEvent]] = {}

    for ev in events:
        order_ref = ev.source_order_reference or ev.order_id
        if not order_ref or not str(order_ref).strip():
            continue
        order_key = (order_ref.strip().lower(), ev.currency)
        if ev.provider == "SHOPIFY":
            shopify_by_order.setdefault(order_key, []).append(ev)
        elif ev.provider == "PAYPAL":
            paypal_by_order.setdefault(order_key, []).append(ev)

    links: List[CrossProviderLink] = []
    seen_pairs: Set[Tuple[str, str]] = set()

    for (ord_key, curr), s_events in shopify_by_order.items():
        if (ord_key, curr) in paypal_by_order:
            p_events = paypal_by_order[(ord_key, curr)]
            for s_ev in s_events:
                for p_ev in p_events:
                    # Check type compatibility
                    if s_ev.type != p_ev.type:
                        continue

                    pair_id = (s_ev.transaction_id, p_ev.transaction_id)
                    if pair_id in seen_pairs:
                        continue
                    seen_pairs.add(pair_id)

                    s_src_id = s_ev.source_transaction_id or s_ev.transaction_id
                    p_src_id = p_ev.source_transaction_id or p_ev.transaction_id

                    link_id = f"LINK-{s_src_id}-{p_src_id}"
                    links.append(CrossProviderLink(
                        link_id=link_id,
                        shopify_event_id=s_ev.transaction_id,
                        paypal_event_id=p_ev.transaction_id,
                        shared_order_reference=s_ev.order_id or ord_key,
                        currency=curr,
                        matched_amount=float(abs(s_ev.gross_amount)),
                        confidence=1.0,
                        link_reason=f"Deterministic cross-provider merchant order reference match: '{ord_key}' ({curr})"
                    ))

    return links
