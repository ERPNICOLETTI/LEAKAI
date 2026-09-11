import pandas as pd
from typing import Dict, Type, Tuple, List, Optional

try:
    from adapters.base import DetectionResult, CanonicalEvent
    from adapters.shopify import ShopifyAdapter
    from adapters.paypal import PayPalAdapter
    from models import FileValidationResult
    from normalizer import validate_and_normalize_csv
except ImportError:
    from .base import DetectionResult, CanonicalEvent
    from .shopify import ShopifyAdapter
    from .paypal import PayPalAdapter
    from ..models import FileValidationResult
    from ..normalizer import validate_and_normalize_csv

class AdapterRegistry:
    def __init__(self):
        self._adapters: List[Any] = [
            ShopifyAdapter,
            PayPalAdapter
        ]

    def detect(self, headers: List[str]) -> DetectionResult:
        matches = []
        for adapter in self._adapters:
            res = adapter.detect(headers)
            if res.confidence >= 0.75:
                matches.append((adapter, res))

        if len(matches) == 1 and not matches[0][1].ambiguous_match:
            return matches[0][1]

        if len(matches) > 1:
            # Check if one is exact (1.0) and others are partial
            exact_matches = [m for m in matches if m[1].confidence == 1.0]
            if len(exact_matches) == 1:
                return exact_matches[0][1]

            return DetectionResult(
                provider_detected="UNKNOWN",
                export_type_detected="AMBIGUOUS",
                confidence=0.0,
                ambiguous_match=True,
                details="Analysis blocked: Ambiguous header match across multiple provider export schemas."
            )

        return DetectionResult(
            provider_detected="GENERIC",
            export_type_detected="GENERIC_CANONICAL_CSV",
            confidence=0.5,
            ambiguous_match=False,
            details="Generic canonical CSV format detected."
        )

    def process(self, df: pd.DataFrame, source_filename: str = "") -> Tuple[FileValidationResult, List[CanonicalEvent]]:
        headers = list(df.columns)
        detection = self.detect(headers)

        if detection.ambiguous_match:
            return FileValidationResult(
                is_valid=False,
                errors=[detection.details]
            ), []

        if detection.provider_detected == "SHOPIFY":
            return ShopifyAdapter.validate_and_normalize(df, source_filename)
        elif detection.provider_detected == "PAYPAL":
            return PayPalAdapter.validate_and_normalize(df, source_filename)
        elif detection.provider_detected == "GENERIC":
            # Pass through generic normalizer
            # Convert normalized DF back to CanonicalEvents
            try:
                # We reuse the existing validate_and_normalize_csv via bytes buffer simulation
                events: List[CanonicalEvent] = []
                for idx, row in df.iterrows():
                    row_num = idx + 1
                    tx_id = str(row['transaction_id']).strip()
                    o_id = str(row['order_id']).strip() if pd.notna(row['order_id']) and str(row['order_id']).lower() not in ['none', 'nan', ''] else None
                    events.append(CanonicalEvent(
                        transaction_id=f"GENERIC:{tx_id}",
                        order_id=o_id,
                        date=str(row['date']).strip(),
                        type=str(row['type']).lower().strip(),
                        gross_amount=row['gross_amount'],
                        fee=row['fee'],
                        net_amount=row['net_amount'],
                        currency=str(row['currency']).strip().upper(),
                        has_source_fee=bool(row.get('has_source_fee', True)),
                        has_source_net=bool(row.get('has_source_net', True)),
                        provider="GENERIC",
                        export_type="GENERIC_CANONICAL_CSV",
                        source_file_id=source_filename,
                        source_row_number=row_num,
                        source_transaction_id=tx_id,
                        source_order_reference=o_id,
                        adapter_version="1.0.0",
                        raw_data=row.get('raw_data', {})
                    ))
                return FileValidationResult(is_valid=True, errors=[], valid_row_count=len(events)), events
            except Exception as e:
                return FileValidationResult(is_valid=False, errors=[f"Generic CSV processing error: {str(e)}"]), []

        return FileValidationResult(
            is_valid=False,
            errors=[f"Unsupported provider export schema for file '{source_filename}'."]
        ), []

registry = AdapterRegistry()
