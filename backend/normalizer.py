import pandas as pd
import io
import re
from typing import Any, Tuple, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

try:
    from models import SchemaMappingResult, FileValidationResult
except ImportError:
    from .models import SchemaMappingResult, FileValidationResult

MONEY_QUANT = Decimal("0.01")

# Explicit Column Aliases Only - Generic "id" matching removed!
COLUMN_ALIASES = {
    "transaction_id": ["transaction_id", "transaction id", "txn_id", "txn id", "tx_id", "tx id", "payment_id", "payment id"],
    "order_id": ["order_id", "order id", "order", "invoice_id", "invoice id"],
    "date": ["date", "created", "timestamp", "time", "created_at", "created at"],
    "type": ["type", "kind", "transaction_type", "transaction type", "event", "event_type"],
    "gross_amount": ["gross_amount", "gross amount", "gross", "amount", "total"],
    "fee": ["fee", "fees", "processing_fee", "processing fee", "gateway_fee", "gateway fee"],
    "net_amount": ["net_amount", "net amount", "net", "payout_amount", "payout amount", "settlement"],
    "currency": ["currency", "curr"]
}

REQUIRED_FIELDS = ["transaction_id", "type", "gross_amount", "currency"]

SUPPORTED_TYPES = {
    "sale": "sale",
    "refund": "refund",
    "fee": "fee",
    "payout": "payout",
    "withdrawal": "payout",
    "chargeback": "chargeback",
    "dispute": "chargeback"
}

ISO_CURRENCY_PATTERN = re.compile(r'^[A-Z]{3}$')

def parse_decimal_strict(val_str: Any) -> Decimal:
    """
    Parses a monetary string strictly into Decimal.
    Valid zeros ("0", "0.00", "$0.00") return Decimal("0.00").
    Malformed strings ("abc", "--", "N/A") raise ValueError.
    """
    if val_str is None or pd.isna(val_str):
        raise ValueError("Monetary amount is missing or null.")
    
    val_str = str(val_str).strip()
    if not val_str:
        raise ValueError("Monetary amount string is empty.")

    is_negative = False
    if val_str.startswith('(') and val_str.endswith(')'):
        is_negative = True
        val_str = val_str[1:-1]

    # Remove currency signs and commas
    cleaned = re.sub(r'[^\d.-]', '', val_str)
    if not cleaned or cleaned in ['-', '.', '-.']:
        raise ValueError(f"Malformed monetary string: '{val_str}'")

    try:
        dec_val = Decimal(cleaned)
        if is_negative:
            dec_val = -dec_val
        return dec_val.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except Exception:
        raise ValueError(f"Invalid monetary format: '{val_str}'")

def validate_currency(val: Any) -> str:
    if val is None or pd.isna(val):
        raise ValueError("Currency field is missing.")
    curr = str(val).strip().upper()
    if not ISO_CURRENCY_PATTERN.match(curr):
        raise ValueError(f"Invalid ISO 4217 currency code: '{val}'")
    return curr

def validate_type(val: Any) -> str:
    if val is None or pd.isna(val):
        raise ValueError("Transaction type field is missing.")
    raw = str(val).strip().lower()
    if raw in SUPPORTED_TYPES:
        return SUPPORTED_TYPES[raw]
    raise ValueError(f"Unsupported transaction type: '{val}'")

def validate_date(val: Any) -> str:
    if val is None or pd.isna(val):
        raise ValueError("Transaction date is missing.")
    date_str = str(val).strip()
    if not date_str:
        raise ValueError("Transaction date string is empty.")
    try:
        dt = pd.to_datetime(date_str, errors='coerce')
        if pd.isna(dt):
            raise ValueError(f"Invalid date format: '{date_str}'")
        return dt.strftime('%Y-%m-%d')
    except Exception:
        raise ValueError(f"Invalid date format: '{date_str}'")

def detect_and_map_schema(df: pd.DataFrame) -> SchemaMappingResult:
    source_columns = list(df.columns)
    col_clean_map = {c: c.strip().lower().replace('_', ' ').replace('-', ' ') for c in source_columns}

    mapped_fields: Dict[str, str] = {}
    ambiguous_fields: Dict[str, List[str]] = {}
    used_source_cols = set()

    for canonical, aliases in COLUMN_ALIASES.items():
        matching_cols = []
        for orig, clean in col_clean_map.items():
            if clean in aliases:
                matching_cols.append(orig)

        if len(matching_cols) == 1:
            col = matching_cols[0]
            if col not in used_source_cols:
                mapped_fields[canonical] = col
                used_source_cols.add(col)
        elif len(matching_cols) > 1:
            ambiguous_fields[canonical] = matching_cols

    missing_required = [f for f in REQUIRED_FIELDS if f not in mapped_fields]
    unused_cols = [c for c in source_columns if c not in used_source_cols]
    warnings = []

    if ambiguous_fields:
        for field, cols in ambiguous_fields.items():
            warnings.append(f"Ambiguous mapping for required field '{field}': matched multiple columns {cols}.")

    if missing_required:
        warnings.append(f"Missing required canonical fields: {missing_required}.")

    return SchemaMappingResult(
        source_columns=source_columns,
        mapped_fields=mapped_fields,
        missing_required_fields=missing_required,
        ambiguous_fields=ambiguous_fields,
        unused_columns=unused_cols,
        warnings=warnings
    )

def validate_and_normalize_csv(contents: bytes) -> Tuple[FileValidationResult, Optional[pd.DataFrame]]:
    """
    Ingests raw CSV bytes, runs strict validation boundary checks, and returns
    (FileValidationResult, DataFrame). If validation fails, is_valid is False and DF is None.
    """
    errors: List[str] = []
    warnings: List[str] = []

    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(contents), encoding='latin-1')
        except Exception as e:
            result = FileValidationResult(
                is_valid=False,
                errors=[f"Failed to parse CSV file structure: {str(e)}"]
            )
            return result, None

    if df.empty:
        result = FileValidationResult(
            is_valid=False,
            errors=["Uploaded CSV file is empty."]
        )
        return result, None

    schema_result = detect_and_map_schema(df)
    warnings.extend(schema_result.warnings)

    if schema_result.ambiguous_fields:
        for field, cols in schema_result.ambiguous_fields.items():
            errors.append(f"Analysis blocked: Ambiguous mapping for '{field}' (matches columns {cols}). Specify unambiguous header.")

    if schema_result.missing_required_fields:
        errors.append(f"Analysis blocked: Missing required canonical fields: {schema_result.missing_required_fields}.")

    if errors:
        result = FileValidationResult(
            is_valid=False,
            errors=errors,
            warnings=warnings,
            detected_columns=schema_result.source_columns,
            mapped_columns=schema_result.mapped_fields
        )
        return result, None

    mapped = schema_result.mapped_fields
    normalized_rows = []
    row_error_count = 0

    for idx, row in df.iterrows():
        row_num = idx + 1
        raw_dict = {str(k): (str(v) if pd.notna(v) else "") for k, v in row.items()}
        row_errs = []

        # 1. Transaction ID
        tx_id_val = row[mapped["transaction_id"]] if pd.notna(row[mapped["transaction_id"]]) else None
        if not tx_id_val or str(tx_id_val).strip() == "":
            row_errs.append(f"Row {row_num}: Transaction ID is missing.")
            tx_id = None
        else:
            tx_id = str(tx_id_val).strip()

        # 2. Type
        type_val = row[mapped["type"]] if pd.notna(row[mapped["type"]]) else None
        try:
            tx_type = validate_type(type_val)
        except ValueError as ve:
            row_errs.append(f"Row {row_num}: {str(ve)}")
            tx_type = "UNKNOWN"

        # 3. Currency
        curr_val = row[mapped["currency"]] if pd.notna(row[mapped["currency"]]) else None
        try:
            currency = validate_currency(curr_val)
        except ValueError as ve:
            row_errs.append(f"Row {row_num}: {str(ve)}")
            currency = "INVALID"

        # 4. Gross Amount
        gross_val = row[mapped["gross_amount"]] if pd.notna(row[mapped["gross_amount"]]) else None
        try:
            gross = parse_decimal_strict(gross_val)
        except ValueError as ve:
            row_errs.append(f"Row {row_num} (gross_amount): {str(ve)}")
            gross = Decimal("0.00")

        # 5. Fee (Optional)
        fee_col = mapped.get("fee")
        fee = Decimal("0.00")
        if fee_col and pd.notna(row[fee_col]):
            try:
                fee = parse_decimal_strict(row[fee_col])
            except ValueError as ve:
                row_errs.append(f"Row {row_num} (fee): {str(ve)}")

        # 6. Net Amount (Optional)
        net_col = mapped.get("net_amount")
        if net_col and pd.notna(row[net_col]):
            try:
                net = parse_decimal_strict(row[net_col])
            except ValueError as ve:
                row_errs.append(f"Row {row_num} (net_amount): {str(ve)}")
                net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        else:
            net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

        # 7. Order ID (Optional)
        order_col = mapped.get("order_id")
        order_id = str(row[order_col]).strip() if order_col and pd.notna(row[order_col]) and str(row[order_col]).strip().lower() not in ['nan', 'none', 'null', ''] else None

        # 8. Date
        date_col = mapped.get("date")
        date_val = row[date_col] if date_col and pd.notna(row[date_col]) else None
        try:
            parsed_date = validate_date(date_val)
        except ValueError as ve:
            row_errs.append(f"Row {row_num} (date): {str(ve)}")
            parsed_date = "INVALID_DATE"

        if row_errs:
            row_error_count += 1
            errors.extend(row_errs)

        normalized_rows.append({
            'transaction_id': tx_id,
            'order_id': order_id,
            'date': parsed_date,
            'type': tx_type,
            'gross_amount': gross,
            'fee': fee,
            'net_amount': net,
            'currency': currency,
            'raw_data': raw_dict
        })

    if row_error_count > 0:
        validation_result = FileValidationResult(
            is_valid=False,
            errors=[f"Analysis blocked: {row_error_count} row(s) contained validation errors."] + errors,
            warnings=warnings,
            detected_columns=schema_result.source_columns,
            mapped_columns=schema_result.mapped_fields,
            row_error_count=row_error_count,
            valid_row_count=len(df) - row_error_count
        )
        return validation_result, None

    norm_df = pd.DataFrame(normalized_rows)
    norm_df['dt'] = pd.to_datetime(norm_df['date'], errors='coerce')
    norm_df = norm_df.sort_values(by='dt').reset_index(drop=True)

    validation_result = FileValidationResult(
        is_valid=True,
        errors=[],
        warnings=warnings,
        detected_columns=schema_result.source_columns,
        mapped_columns=schema_result.mapped_fields,
        row_error_count=0,
        valid_row_count=len(df)
    )

    return validation_result, norm_df

def normalize_csv(contents: bytes) -> pd.DataFrame:
    val_result, df = validate_and_normalize_csv(contents)
    if not val_result.is_valid or df is None:
        raise ValueError(" | ".join(val_result.errors))
    return df
