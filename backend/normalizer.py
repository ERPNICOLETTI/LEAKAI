import pandas as pd
import io
import re
from typing import Any
from decimal import Decimal, ROUND_HALF_UP

MONEY_QUANT = Decimal("0.01")

def parse_decimal_clean(val_str: Any) -> Decimal:
    if val_str is None or pd.isna(val_str):
        return Decimal("0.00")
    
    val_str = str(val_str).strip()
    if not val_str:
        return Decimal("0.00")

    is_negative = False
    if val_str.startswith('(') and val_str.endswith(')'):
        is_negative = True
        val_str = val_str[1:-1]

    cleaned = re.sub(r'[^\d.-]', '', val_str)
    if not cleaned or cleaned == '-' or cleaned == '.':
        return Decimal("0.00")
    
    try:
        dec_val = Decimal(cleaned)
        if is_negative:
            dec_val = -dec_val
        return dec_val.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

def normalize_csv(contents: bytes) -> pd.DataFrame:
    """
    Parses raw CSV bytes into a clean DataFrame with canonical ecommerce schema:
    ['date', 'transaction_id', 'order_id', 'type', 'gross_amount', 'fee', 'net_amount', 'currency', 'raw_data']
    Monetary columns store Decimal objects internally.
    """
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except Exception:
        df = pd.read_csv(io.BytesIO(contents), encoding='latin-1')

    if df.empty:
        raise ValueError("The uploaded CSV file is empty.")

    orig_columns = list(df.columns)
    col_map = {col: col.strip().lower().replace('_', ' ').replace('-', ' ') for col in orig_columns}

    date_col = None
    tx_id_col = None
    order_id_col = None
    type_col = None
    gross_col = None
    fee_col = None
    net_col = None
    currency_col = None

    for orig, clean in col_map.items():
        if not tx_id_col and any(k in clean for k in ['transaction id', 'tx id', 'txn id', 'id']):
            tx_id_col = orig
        elif not order_id_col and any(k in clean for k in ['order id', 'order_id', 'order', 'invoice']):
            order_id_col = orig
        elif not date_col and any(k in clean for k in ['date', 'created', 'timestamp', 'time']):
            date_col = orig
        elif not type_col and any(k in clean for k in ['type', 'kind', 'transaction type', 'event']):
            type_col = orig
        elif not gross_col and any(k in clean for k in ['gross', 'gross amount', 'amount', 'total']):
            gross_col = orig
        elif not fee_col and any(k in clean for k in ['fee', 'fees', 'gateway fee', 'processing fee']):
            fee_col = orig
        elif not net_col and any(k in clean for k in ['net', 'net amount', 'payout amount', 'settlement']):
            net_col = orig
        elif not currency_col and any(k in clean for k in ['currency', 'curr']):
            currency_col = orig

    normalized_rows = []

    for idx, row in df.iterrows():
        raw = {str(k): (str(v) if pd.notna(v) else "") for k, v in row.items()}

        tx_id = str(row[tx_id_col]).strip() if tx_id_col and pd.notna(row[tx_id_col]) else f"TXN-{idx+1:05d}"
        order_id = str(row[order_id_col]).strip() if order_id_col and pd.notna(row[order_id_col]) and str(row[order_id_col]).strip().lower() not in ['nan', 'none', 'null', ''] else None
        raw_date = str(row[date_col]).strip() if date_col and pd.notna(row[date_col]) else ""
        parsed_date = parse_date_clean(raw_date)

        raw_type = str(row[type_col]).strip().lower() if type_col and pd.notna(row[type_col]) else "sale"
        tx_type = map_tx_type(raw_type)

        gross = parse_decimal_clean(str(row[gross_col])) if gross_col and pd.notna(row[gross_col]) else Decimal("0.00")
        fee = parse_decimal_clean(str(row[fee_col])) if fee_col and pd.notna(row[fee_col]) else Decimal("0.00")
        
        if net_col and pd.notna(row[net_col]):
            net = parse_decimal_clean(str(row[net_col]))
        else:
            net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

        currency = str(row[currency_col]).strip().upper() if currency_col and pd.notna(row[currency_col]) else "USD"

        normalized_rows.append({
            'transaction_id': tx_id,
            'order_id': order_id,
            'date': parsed_date,
            'type': tx_type,
            'gross_amount': gross,
            'fee': fee,
            'net_amount': net,
            'currency': currency,
            'raw_data': raw
        })

    norm_df = pd.DataFrame(normalized_rows)
    norm_df['dt'] = pd.to_datetime(norm_df['date'], errors='coerce')
    norm_df = norm_df.sort_values(by='dt').reset_index(drop=True)
    return norm_df

def map_tx_type(val: str) -> str:
    if 'refund' in val:
        return 'refund'
    elif 'chargeback' in val or 'dispute' in val:
        return 'chargeback'
    elif 'fee' in val:
        return 'fee'
    elif 'payout' in val or 'withdrawal' in val:
        return 'payout'
    return 'sale'

def parse_date_clean(date_str: str) -> str:
    if not date_str:
        return "2026-01-01"
    try:
        dt = pd.to_datetime(date_str, errors='coerce')
        if pd.isna(dt):
            return date_str
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return date_str
