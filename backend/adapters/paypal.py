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

# Official PayPal Activity Download CSV header signature
# Reference: https://www.paypal.com/us/smarthelp/article/how-do-i-download-a-history-log-of-my-paypal-transactions-ts1417
PAYPAL_ACTIVITY_REQUIRED_HEADERS = [
    "Date",
    "Time",
    "TimeZone",
    "Name",
    "Type",
    "Status",
    "Currency",
    "Gross",
    "Fee",
    "Net",
    "Transaction ID"
]

class PayPalAdapter:
    PROVIDER = "PAYPAL"
    EXPORT_TYPE = "PAYPAL_ACTIVITY"
    VERSION = "1.0.0"

    @classmethod
    def detect(cls, headers: List[str]) -> DetectionResult:
        clean_headers = [h.strip() for h in headers]
        matched_required = [h for h in PAYPAL_ACTIVITY_REQUIRED_HEADERS if h in clean_headers]
        missing = [h for h in PAYPAL_ACTIVITY_REQUIRED_HEADERS if h not in clean_headers]

        confidence = len(matched_required) / len(PAYPAL_ACTIVITY_REQUIRED_HEADERS)
        is_exact = len(missing) == 0

        return DetectionResult(
            provider_detected=cls.PROVIDER if is_exact else ("PAYPAL" if confidence >= 0.75 else "UNKNOWN"),
            export_type_detected=cls.EXPORT_TYPE,
            confidence=confidence,
            required_columns_present=matched_required,
            missing_columns=missing,
            ambiguous_match=not is_exact and confidence >= 0.75,
            details="PayPal Activity Log export format"
        )

    @classmethod
    def validate_and_normalize(cls, df: pd.DataFrame, source_filename: str = "") -> Tuple[FileValidationResult, List[CanonicalEvent]]:
        detection = cls.detect(list(df.columns))
        if detection.missing_columns:
            return FileValidationResult(
                is_valid=False,
                errors=[f"PayPal adapter error: Missing required headers {detection.missing_columns}"]
            ), []

        events: List[CanonicalEvent] = []
        errors: List[str] = []

        for idx, row in df.iterrows():
            row_num = idx + 1
            raw_dict = {str(k): (str(v) if pd.notna(v) else "") for k, v in row.items()}
            row_errs = []

            # 1. Transaction ID
            src_tx_id = str(row.get("Transaction ID")).strip() if pd.notna(row.get("Transaction ID")) else ""
            if not src_tx_id:
                row_errs.append(f"Row {row_num}: PayPal Transaction ID is missing")

            # 2. Date
            d_val = row.get("Date")
            try:
                date_str = validate_date(d_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid Date - {str(e)}")
                date_str = ""

            # 3. Type / Event Status
            raw_type = str(row.get("Type", "")).strip().lower()
            status = str(row.get("Status", "")).strip().lower()

            if "payment received" in raw_type or "express checkout payment" in raw_type or "mobile payment" in raw_type or "general payment" in raw_type:
                tx_type = "sale"
            elif "refund" in raw_type or "payment sent" in raw_type:
                tx_type = "refund" if "refund" in raw_type else ("refund" if parse_decimal_strict(row.get("Gross", "0.00")) < Decimal("0.00") else "sale")
            elif "partner fee" in raw_type or "fee" in raw_type:
                tx_type = "fee"
            elif "withdrawal" in raw_type or "bank deposit" in raw_type or "payout" in raw_type:
                tx_type = "payout"
            elif "dispute" in raw_type or "chargeback" in raw_type or "reversal" in raw_type:
                tx_type = "chargeback"
            else:
                row_errs.append(f"Row {row_num}: Unsupported PayPal event type '{raw_type}'")
                tx_type = "UNKNOWN"

            # 4. Currency
            c_val = row.get("Currency")
            try:
                currency = validate_currency(c_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid Currency - {str(e)}")
                currency = "USD"

            # 5. Gross
            g_val = row.get("Gross")
            try:
                gross = parse_decimal_strict(g_val)
            except Exception as e:
                row_errs.append(f"Row {row_num}: Invalid Gross amount - {str(e)}")
                gross = Decimal("0.00")

            # 6. Fee
            has_fee = pd.notna(row.get("Fee")) and str(row.get("Fee")).strip() != ""
            fee = Decimal("0.00")
            if has_fee:
                try:
                    fee = parse_decimal_strict(row.get("Fee"))
                    # PayPal fee is usually recorded as negative, e.g. -0.30. Normalize to positive fee expense.
                    if fee < Decimal("0.00"):
                        fee = abs(fee)
                except Exception as e:
                    row_errs.append(f"Row {row_num}: Invalid Fee amount - {str(e)}")

            # 7. Net
            has_net = pd.notna(row.get("Net")) and str(row.get("Net")).strip() != ""
            net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
            if has_net:
                try:
                    net = parse_decimal_strict(row.get("Net"))
                except Exception as e:
                    row_errs.append(f"Row {row_num}: Invalid Net amount - {str(e)}")

            # References
            order_ref = str(row.get("Item ID")).strip() if pd.notna(row.get("Item ID")) and str(row.get("Item ID")).strip() != "" else None
            if not order_ref and pd.notna(row.get("Invoice Number")) and str(row.get("Invoice Number")).strip() != "":
                order_ref = str(row.get("Invoice Number")).strip()
            if not order_ref and pd.notna(row.get("Custom Number")) and str(row.get("Custom Number")).strip() != "":
                order_ref = str(row.get("Custom Number")).strip()

            parent_ref = str(row.get("Reference Txn ID")).strip() if pd.notna(row.get("Reference Txn ID")) and str(row.get("Reference Txn ID")).strip() != "" else None

            if row_errs:
                errors.extend(row_errs)
                continue

            namespaced_id = f"PAYPAL:{src_tx_id}"

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
                source_payout_reference=None,
                source_parent_reference=parent_ref,
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
