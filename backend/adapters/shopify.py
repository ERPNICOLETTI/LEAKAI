import pandas as pd
from typing import List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP

try:
    from models import FileValidationResult
    from normalizer import parse_decimal_strict, validate_date, validate_currency
except ImportError:
    from ..models import FileValidationResult
    from ..normalizer import parse_decimal_strict, validate_date, validate_currency

try:
    from adapters.base import DetectionResult, CanonicalEvent
except ImportError:
    from .base import DetectionResult, CanonicalEvent

MONEY_QUANT = Decimal("0.01")

# Official Shopify Payments Transactions export schema headers
# Reference: https://help.shopify.com/en/manual/shopify-payments/reporting/payouts#export-payouts-or-transactions
SHOPIFY_PAYMENTS_REQUIRED_HEADERS = [
    "Transaction Date",
    "Type",
    "Order",
    "Amount",
    "Fee",
    "Net",
    "Payout Date",
    "Payout Currency"
]

class ShopifyAdapter:
    PROVIDER = "SHOPIFY"
    EXPORT_TYPE = "SHOPIFY_PAYMENTS_TRANSACTIONS"
    VERSION = "1.0.0"

    @classmethod
    def detect(cls, headers: List[str]) -> DetectionResult:
        clean_headers = [h.strip() for h in headers]
        matched_required = [h for h in SHOPIFY_PAYMENTS_REQUIRED_HEADERS if h in clean_headers]
        missing = [h for h in SHOPIFY_PAYMENTS_REQUIRED_HEADERS if h not in clean_headers]

        confidence = len(matched_required) / len(SHOPIFY_PAYMENTS_REQUIRED_HEADERS)
        is_exact = len(missing) == 0

        return DetectionResult(
            provider_detected=cls.PROVIDER if is_exact else ("SHOPIFY" if confidence >= 0.75 else "UNKNOWN"),
            export_type_detected=cls.EXPORT_TYPE,
            confidence=confidence,
            required_columns_present=matched_required,
            missing_columns=missing,
            ambiguous_match=not is_exact and confidence >= 0.75,
            details="Shopify Payments Transactions export format"
        )

    @classmethod
    def validate_and_normalize(cls, df: pd.DataFrame, source_filename: str = "") -> Tuple[FileValidationResult, List[CanonicalEvent]]:
        detection = cls.detect(list(df.columns))
        if detection.missing_columns:
            return FileValidationResult(
                is_valid=False,
                errors=[f"Shopify adapter error: Missing required headers {detection.missing_columns}"]
            ), []

        events: List[CanonicalEvent] = []
        errors: List[str] = []

        for idx, row in df.iterrows():
            row_num = idx + 1
            raw_dict = {str(k): (str(v) if pd.notna(v) else "") for k, v in row.items()}
            row_errs = []

            # 1. Date
            d_val = row.get("Transaction Date")
            try:
                date_str = validate_date(d_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid Transaction Date - {str(e)}")
                date_str = ""

            # 2. Kind / Type
            raw_type = str(row.get("Type", "")).strip().lower()
            if raw_type in ["charge", "sale", "payment"]:
                tx_type = "sale"
            elif raw_type in ["refund"]:
                tx_type = "refund"
            elif raw_type in ["fee"]:
                tx_type = "fee"
            elif raw_type in ["payout"]:
                tx_type = "payout"
            elif raw_type in ["dispute", "chargeback"]:
                tx_type = "chargeback"
            else:
                row_errs.append(f"Row {row_num}: Unsupported Shopify transaction type '{raw_type}'")
                tx_type = "UNKNOWN"

            # 3. Currency
            c_val = row.get("Payout Currency") or row.get("Currency")
            try:
                currency = validate_currency(c_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid currency - {str(e)}")
                currency = "USD"

            # 4. Gross Amount
            g_val = row.get("Amount")
            try:
                gross = parse_decimal_strict(g_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid Amount - {str(e)}")
                gross = Decimal("0.00")

            # 5. Fee
            has_fee = pd.notna(row.get("Fee")) and str(row.get("Fee")).strip() != ""
            fee = Decimal("0.00")
            if has_fee:
                try:
                    fee = parse_decimal_strict(row.get("Fee"))
                except Exception as e:
                    row_errs.append(f"Row {row_num}: Invalid Fee - {str(e)}")

            # 6. Net
            has_net = pd.notna(row.get("Net")) and str(row.get("Net")).strip() != ""
            net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
            if has_net:
                try:
                    net = parse_decimal_strict(row.get("Net"))
                except Exception as e:
                    row_errs.append(f"Row {row_num}: Invalid Net - {str(e)}")

            # References
            order_ref = str(row.get("Order")).strip() if pd.notna(row.get("Order")) and str(row.get("Order")).strip() != "" else None
            payout_ref = str(row.get("Payout Date")).strip() if pd.notna(row.get("Payout Date")) and str(row.get("Payout Date")).strip() != "" else None
            
            # Source Transaction ID (or synthetic order-scoped key if absent in raw CSV)
            src_tx_id = str(row.get("Transaction ID")).strip() if pd.notna(row.get("Transaction ID")) and str(row.get("Transaction ID")).strip() != "" else f"SP-{order_ref or idx+1}-{tx_type}-{idx+1}"

            if row_errs:
                errors.extend(row_errs)
                continue

            # Namespaced canonical ID
            namespaced_id = f"SHOPIFY:{src_tx_id}"

            event = CanonicalEvent(
                transaction_id=namespaced_id,
                order_id=order_ref,
                date=date_str,
                type=tx_type,
                gross_amount=gross,
                fee=fee,
                net_amount=net,
                currency=currency,
                has_source_fee=has_fee,
                has_source_net=has_net,
                provider=cls.PROVIDER,
                export_type=cls.EXPORT_TYPE,
                source_file_id=source_filename,
                source_row_number=row_num,
                source_transaction_id=src_tx_id,
                source_order_reference=order_ref,
                source_payout_reference=payout_ref,
                source_parent_reference=None,
                adapter_version=cls.VERSION,
                raw_data=raw_dict
            )
            events.append(event)

        if errors:
            return FileValidationResult(
                is_valid=False,
                errors=errors,
                row_error_count=len(errors),
                valid_row_count=len(events)
            ), []

        return FileValidationResult(
            is_valid=True,
            errors=[],
            valid_row_count=len(events)
        ), events
