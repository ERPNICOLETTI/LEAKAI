import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP

try:
    from models import (
        TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, 
        RuleBreakdown, EconomicLossItem, ReviewIssueItem, CurrencyFinancialSummary
    )
except ImportError:
    from .models import (
        TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, 
        RuleBreakdown, EconomicLossItem, ReviewIssueItem, CurrencyFinancialSummary
    )

MONEY_QUANT = Decimal("0.01")

def money(val: Any) -> Decimal:
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    s_val = str(val).strip()
    return Decimal(s_val).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

RULE_DUP_TX = "DUPLICATE_TRANSACTION_ID"
RULE_CONFLICTING_TX = "CONFLICTING_TRANSACTION_ID"
RULE_DUP_REFUND = "POSSIBLE_DUPLICATED_REFUND"
RULE_MISSING_ORDER = "MISSING_ORDER_ID"
RULE_NET_MATH = "NET_AMOUNT_INCONSISTENCY"
RULE_HIGH_FEE = "HIGH_FEE_DETECTED"
RULE_REFUND_EXCEEDS = "REFUND_EXCEEDS_SALE"
RULE_UNMATCHED_REFUND = "UNMATCHED_REFUND"
RULE_NEG_FEE = "INVALID_NEGATIVE_FEE"

RULE_METADATA = {
    RULE_DUP_TX: {
        "name": "Duplicate Gateway Transaction ID",
        "severity": "MEDIUM",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_CONFLICTING_TX: {
        "name": "Conflicting Transaction ID Data",
        "severity": "HIGH",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_DUP_REFUND: {
        "name": "Possible Duplicated Refund",
        "severity": "MEDIUM",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_MISSING_ORDER: {
        "name": "Missing Order ID",
        "severity": "LOW",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_NET_MATH: {
        "name": "Net Amount Settlement Inconsistency",
        "severity": "MEDIUM",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_HIGH_FEE: {
        "name": "High Gateway Processing Fee",
        "severity": "LOW",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_REFUND_EXCEEDS: {
        "name": "Refund Amount Exceeds Sale Price",
        "severity": "HIGH",
        "classification": "CONFIRMED_LOSS"
    },
    RULE_UNMATCHED_REFUND: {
        "name": "Unmatched Refund / Orphan Chargeback",
        "severity": "MEDIUM",
        "classification": "REVIEW_REQUIRED"
    },
    RULE_NEG_FEE: {
        "name": "Invalid Negative Fee Discrepancy",
        "severity": "LOW",
        "classification": "REVIEW_REQUIRED"
    }
}

def analyze_transactions(df: pd.DataFrame) -> Tuple[AuditSummary, List[TransactionRecord]]:
    # -------------------------------------------------------------------------
    # 1. RAW RECORD LAYER: Ingest all rows & preserve raw export structure
    # -------------------------------------------------------------------------
    raw_records: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        tx_id = str(row['transaction_id']).strip()
        order_id = str(row['order_id']).strip() if pd.notna(row['order_id']) and str(row['order_id']).lower() not in ['none', 'nan', ''] else None
        gross = money(row['gross_amount'])
        fee = money(row['fee'])
        net = money(row['net_amount'])
        tx_type = str(row['type']).lower().strip()
        date_str = str(row['date']).strip()
        dt = row['dt']
        curr = str(row['currency']).strip().upper()

        has_source_fee = bool(row['has_source_fee']) if 'has_source_fee' in row else True
        has_source_net = bool(row['has_source_net']) if 'has_source_net' in row else True

        raw_records.append({
            "index": idx,
            "transaction_id": tx_id,
            "order_id": order_id,
            "date": date_str,
            "dt": dt,
            "type": tx_type,
            "gross_amount": gross,
            "fee": fee,
            "net_amount": net,
            "currency": curr,
            "has_source_fee": has_source_fee,
            "has_source_net": has_source_net,
            "flags": [],
            "raw_data": row['raw_data']
        })

    # REVIEW ISSUE LEDGER INITIALIZATION
    review_issue_ledger: List[ReviewIssueItem] = []

    def add_review_issue(
        issue_id: str, 
        rule_id: str, 
        desc: str, 
        amount: Decimal, 
        order_id: Optional[str] = None, 
        tx_id: Optional[str] = None, 
        exposure_key: Optional[str] = None,
        affected_rows: Optional[List[str]] = None
    ):
        rows_list = affected_rows if affected_rows is not None else []
        dec_amt = money(amount)
        if not any(item.review_issue_id == issue_id for item in review_issue_ledger):
            review_issue_ledger.append(ReviewIssueItem(
                review_issue_id=issue_id,
                rule_id=rule_id,
                order_id=order_id,
                transaction_id=tx_id,
                exposure_key=exposure_key,
                description=desc,
                amount_requiring_review=float(max(Decimal("0.00"), dec_amt)),
                affected_raw_rows=rows_list
            ))

    # RAW LAYER CHECK: DUPLICATE & CONFLICTING TRANSACTION IDs
    tx_id_raw_groups: Dict[str, List[int]] = {}
    for i, r in enumerate(raw_records):
        tx_id_raw_groups.setdefault(r["transaction_id"], []).append(i)

    conflicting_tx_ids = set()

    for t_id, indices in tx_id_raw_groups.items():
        if not t_id or len(indices) <= 1:
            continue

        first_rec = raw_records[indices[0]]
        has_conflict = False

        for idx in indices[1:]:
            rec = raw_records[idx]
            if (rec["order_id"] != first_rec["order_id"] or
                rec["type"] != first_rec["type"] or
                rec["gross_amount"] != first_rec["gross_amount"] or
                rec["fee"] != first_rec["fee"] or
                rec["net_amount"] != first_rec["net_amount"] or
                rec["currency"] != first_rec["currency"]):
                has_conflict = True
                break

        affected_row_ids = [str(raw_records[i]["index"]) for i in indices]

        if has_conflict:
            conflicting_tx_ids.add(t_id)
            conflict_amount = max(abs(raw_records[i]["gross_amount"]) for i in indices)
            desc = f"Transaction ID '{t_id}' has conflicting monetary or currency fields across {len(indices)} raw rows. Excluded from economic reconciliation."
            
            add_review_issue(
                issue_id=f"REVIEW-CONFLICTING-TX-{t_id}",
                rule_id=RULE_CONFLICTING_TX,
                desc=desc,
                amount=conflict_amount,
                tx_id=t_id,
                exposure_key=f"EXPOSURE-TX-{t_id}",
                affected_rows=affected_row_ids
            )

            for idx in indices:
                rec = raw_records[idx]
                flag = AnomalyFlag(
                    rule_id=RULE_CONFLICTING_TX,
                    rule_name=RULE_METADATA[RULE_CONFLICTING_TX]["name"],
                    severity="HIGH",
                    classification="REVIEW_REQUIRED",
                    description=desc,
                    amount_at_risk=float(abs(rec["gross_amount"]))
                )
                add_flag_if_missing(rec["flags"], flag)
        else:
            dup_amount = abs(first_rec["gross_amount"])
            desc = f"Transaction ID '{t_id}' appears {len(indices)} times in raw export. Review export to verify if gateway double-settled."
            
            add_review_issue(
                issue_id=f"REVIEW-DUP-TX-{t_id}",
                rule_id=RULE_DUP_TX,
                desc=desc,
                amount=dup_amount,
                tx_id=t_id,
                exposure_key=f"EXPOSURE-TX-{t_id}",
                affected_rows=affected_row_ids
            )

            for idx in indices[1:]:
                rec = raw_records[idx]
                flag = AnomalyFlag(
                    rule_id=RULE_DUP_TX,
                    rule_name=RULE_METADATA[RULE_DUP_TX]["name"],
                    severity="MEDIUM",
                    classification="REVIEW_REQUIRED",
                    description=desc,
                    amount_at_risk=float(dup_amount)
                )
                add_flag_if_missing(rec["flags"], flag)

    # -------------------------------------------------------------------------
    # 2. ECONOMIC EVENT LAYER: Deduplicate non-conflicting unique transaction_ids
    # -------------------------------------------------------------------------
    seen_tx_ids = set()
    economic_events: List[Dict[str, Any]] = []

    for r in raw_records:
        t_id = r["transaction_id"]
        if t_id and t_id in conflicting_tx_ids:
            continue
        if t_id and t_id in seen_tx_ids:
            continue
        if t_id:
            seen_tx_ids.add(t_id)
        economic_events.append(r)

    # DYNAMIC MEDIAN FEE BASELINE CALCULATION PER CURRENCY
    fee_thresholds_by_currency: Dict[str, float] = {}
    median_fee_by_currency: Dict[str, float] = {}

    sales_by_curr: Dict[str, List[float]] = {}
    for ev in economic_events:
        curr = ev["currency"]
        if ev["type"] == "sale" and ev["gross_amount"] > Decimal("0.00") and ev["fee"] >= Decimal("0.00"):
            pct = float((ev["fee"] / ev["gross_amount"]) * Decimal("100.00"))
            sales_by_curr.setdefault(curr, []).append(pct)

    for curr, pcts in sales_by_curr.items():
        med_pct = float(np.median(pcts)) if pcts else 3.0
        median_fee_by_currency[curr] = med_pct
        fee_thresholds_by_currency[curr] = max(med_pct * 2.0, med_pct + 5.0)

    # CURRENCY-SCOPED ORDER RECONCILIATION INDEX
    # Key: (order_id, currency)
    econ_order_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    sales_by_order_curr: Dict[Tuple[str, str], Decimal] = {}

    for ev in economic_events:
        o_id = ev["order_id"]
        curr = ev["currency"]
        if o_id:
            key = (o_id, curr)
            econ_order_map.setdefault(key, []).append(ev)
            if ev["type"] == "sale":
                sales_by_order_curr[key] = sales_by_order_curr.get(key, Decimal("0.00")) + abs(ev["gross_amount"])

    # RULE 7: UNMATCHED_REFUND / CHARGEBACK (ECONOMIC LAYER, REVIEW_REQUIRED)
    for ev in economic_events:
        if ev["type"] in ["refund", "chargeback"]:
            o_id = ev["order_id"]
            curr = ev["currency"]
            has_sale = False
            if o_id and (o_id, curr) in econ_order_map:
                has_sale = any(e["type"] == "sale" for e in econ_order_map[(o_id, curr)])
            
            if not has_sale:
                desc = f"{ev['type'].upper()} of {curr} ${abs(ev['gross_amount']):,.2f} has no matching sale in dataset for currency {curr}."
                add_review_issue(
                    issue_id=f"REVIEW-UNMATCHED-{ev['transaction_id']}",
                    rule_id=RULE_UNMATCHED_REFUND,
                    desc=desc,
                    amount=abs(ev["gross_amount"]),
                    order_id=o_id,
                    tx_id=ev["transaction_id"],
                    exposure_key=f"EXPOSURE-UNMATCHED-{ev['transaction_id']}",
                    affected_rows=[str(ev["index"])]
                )
                flag = AnomalyFlag(
                    rule_id=RULE_UNMATCHED_REFUND,
                    rule_name=RULE_METADATA[RULE_UNMATCHED_REFUND]["name"],
                    severity="MEDIUM",
                    classification="REVIEW_REQUIRED",
                    description=desc,
                    amount_at_risk=float(abs(ev["gross_amount"]))
                )
                add_flag_if_missing(ev["flags"], flag)

    # ORDER-LEVEL MONETARY RECONCILIATION & ECONOMIC LOSS LEDGER (CURRENCY SCOPED)
    economic_loss_ledger: List[EconomicLossItem] = []
    order_curr_confirmed_loss_map: Dict[Tuple[str, str], Decimal] = {}

    for (o_id, curr), events in econ_order_map.items():
        refund_events = [e for e in events if e["type"] == "refund"]
        has_sale = any(e["type"] == "sale" for e in events)

        # RULE 2: POSSIBLE_DUPLICATED_REFUND (ALWAYS REVIEW_REQUIRED IN GENERIC ENGINE)
        if len(refund_events) > 1:
            sorted_refunds = sorted(refund_events, key=lambda e: e["dt"] if pd.notna(e["dt"]) else pd.Timestamp.min)
            for k in range(1, len(sorted_refunds)):
                r_prev = sorted_refunds[k-1]
                r_curr = sorted_refunds[k]

                days_gap = 999
                if pd.notna(r_prev["dt"]) and pd.notna(r_curr["dt"]):
                    days_gap = abs((r_curr["dt"] - r_prev["dt"]).days)

                if days_gap <= 7:
                    prev_amt = abs(r_prev["gross_amount"])
                    curr_amt = abs(r_curr["gross_amount"])
                    desc = f"Multiple refund events for Order '{o_id}' ({curr}) within {days_gap} day(s) (${prev_amt:,.2f} and ${curr_amt:,.2f}). Review partial refund validity."
                    
                    add_review_issue(
                        issue_id=f"REVIEW-MULTI-REFUND-{o_id}-{curr}",
                        rule_id=RULE_DUP_REFUND,
                        desc=desc,
                        amount=curr_amt,
                        order_id=o_id,
                        tx_id=r_curr["transaction_id"],
                        exposure_key=f"EXPOSURE-ORDER-REFUND-{o_id}-{curr}",
                        affected_rows=[str(r_prev["index"]), str(r_curr["index"])]
                    )

                    flag = AnomalyFlag(
                        rule_id=RULE_DUP_REFUND,
                        rule_name=RULE_METADATA[RULE_DUP_REFUND]["name"],
                        severity="MEDIUM",
                        classification="REVIEW_REQUIRED",
                        description=desc,
                        amount_at_risk=float(curr_amt)
                    )
                    add_flag_if_missing(r_curr["flags"], flag)

        # RULE 6: REFUND_EXCEEDS_SALE (CURRENCY SCOPED CONFIRMED LOSS)
        if has_sale and refund_events:
            sale_total = sales_by_order_curr.get((o_id, curr), Decimal("0.00"))
            total_unique_refunds = sum((abs(e["gross_amount"]) for e in refund_events), Decimal("0.00"))

            if total_unique_refunds > sale_total + Decimal("0.01"):
                net_excess_loss = (total_unique_refunds - sale_total).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
                loss_id = f"LOSS-EXCESS-REFUND-{o_id}-{curr}"

                if not any(item.economic_loss_id == loss_id for item in economic_loss_ledger):
                    economic_loss_ledger.append(EconomicLossItem(
                        economic_loss_id=loss_id,
                        order_id=o_id,
                        transaction_id=refund_events[-1]["transaction_id"],
                        rule_id=RULE_REFUND_EXCEEDS,
                        description=f"Net refund excess over original sale price for Order '{o_id}' ({curr}) (${total_unique_refunds:,.2f} unique refunds vs ${sale_total:,.2f} sale).",
                        proven_loss_amount=float(net_excess_loss)
                    ))
                    order_curr_confirmed_loss_map[(o_id, curr)] = net_excess_loss

                for r_ev in refund_events:
                    flag = AnomalyFlag(
                        rule_id=RULE_REFUND_EXCEEDS,
                        rule_name=RULE_METADATA[RULE_REFUND_EXCEEDS]["name"],
                        severity="HIGH",
                        classification="CONFIRMED_LOSS",
                        description=f"Order '{o_id}' ({curr}) unique refunds (${total_unique_refunds:,.2f}) exceed sale (${sale_total:,.2f}) by ${net_excess_loss:,.2f} net excess.",
                        amount_at_risk=float(net_excess_loss)
                    )
                    add_flag_if_missing(r_ev["flags"], flag)

    # ROW-BY-ROW ANOMALY CHECKS FOR ALL RAW RECORDS
    for rec in raw_records:
        gross = rec["gross_amount"]
        fee = rec["fee"]
        net = rec["net_amount"]
        t_type = rec["type"]
        o_id = rec["order_id"]
        t_id = rec["transaction_id"]
        curr = rec["currency"]

        # RULE 3: MISSING_ORDER_ID (REVIEW_REQUIRED)
        if not o_id and t_type in ["sale", "refund", "chargeback"]:
            desc = f"Transaction of type '{t_type.upper()}' is missing order reference metadata."
            add_review_issue(
                issue_id=f"REVIEW-MISSING-ORDER-{t_id}",
                rule_id=RULE_MISSING_ORDER,
                desc=desc,
                amount=Decimal("0.00"),
                tx_id=t_id,
                exposure_key=None,
                affected_rows=[str(rec["index"])]
            )
            flag = AnomalyFlag(
                rule_id=RULE_MISSING_ORDER,
                rule_name=RULE_METADATA[RULE_MISSING_ORDER]["name"],
                severity="LOW",
                classification="REVIEW_REQUIRED",
                description=desc,
                amount_at_risk=0.0
            )
            add_flag_if_missing(rec["flags"], flag)

        has_source_fee = bool(rec.get("has_source_fee", True))
        has_source_net = bool(rec.get("has_source_net", True))

        # RULE 4: NET_AMOUNT_INCONSISTENCY (REVIEW_REQUIRED) - ONLY IF BOTH SOURCE NET AND SOURCE FEE WERE SUPPLIED
        if has_source_net and has_source_fee:
            expected_net = (gross - fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
            if abs(net - expected_net) > Decimal("0.01"):
                diff = abs(net - expected_net).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
                desc = f"Net settlement variance: Net ({curr} ${net:,.2f}) != Gross (${gross:,.2f}) - Fee (${fee:,.2f}) [Variance: ${diff:,.2f}]. Review gateway log."
                add_review_issue(
                    issue_id=f"REVIEW-NET-MATH-{t_id}",
                    rule_id=RULE_NET_MATH,
                    desc=desc,
                    amount=diff,
                    order_id=o_id,
                    tx_id=t_id,
                    exposure_key=f"EXPOSURE-TX-{t_id}",
                    affected_rows=[str(rec["index"])]
                )
                flag = AnomalyFlag(
                    rule_id=RULE_NET_MATH,
                    rule_name=RULE_METADATA[RULE_NET_MATH]["name"],
                    severity="MEDIUM",
                    classification="REVIEW_REQUIRED",
                    description=desc,
                    amount_at_risk=float(diff)
                )
                add_flag_if_missing(rec["flags"], flag)

        # RULE 5: HIGH_FEE_DETECTED (REVIEW_REQUIRED) - ONLY IF SOURCE FEE WAS SUPPLIED
        if has_source_fee and gross > Decimal("0.00") and fee > Decimal("0.00"):
            fee_pct = float((fee / gross) * Decimal("100.00"))
            curr_threshold = fee_thresholds_by_currency.get(curr, 8.0)
            curr_median = median_fee_by_currency.get(curr, 3.0)

            if fee_pct > curr_threshold:
                normal_fee = (gross * Decimal(str(curr_median / 100.0))).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
                excess_fee = (fee - normal_fee).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
                desc = f"Gateway fee of ${fee:,.2f} ({fee_pct:.1f}%) is materially above {curr} median baseline ({curr_median:.1f}%). Excess: ${excess_fee:,.2f}."
                add_review_issue(
                    issue_id=f"REVIEW-HIGH-FEE-{t_id}",
                    rule_id=RULE_HIGH_FEE,
                    desc=desc,
                    amount=excess_fee,
                    order_id=o_id,
                    tx_id=t_id,
                    exposure_key=f"EXPOSURE-TX-{t_id}",
                    affected_rows=[str(rec["index"])]
                )
                flag = AnomalyFlag(
                    rule_id=RULE_HIGH_FEE,
                    rule_name=RULE_METADATA[RULE_HIGH_FEE]["name"],
                    severity="LOW",
                    classification="REVIEW_REQUIRED",
                    description=desc,
                    amount_at_risk=float(excess_fee)
                )
                add_flag_if_missing(rec["flags"], flag)

        # RULE 8: INVALID_NEGATIVE_FEE (REVIEW_REQUIRED)
        if fee < Decimal("0.00"):
            desc = f"Transaction contains invalid negative fee of ${fee:,.2f}. Review fee credit adjustment."
            add_review_issue(
                issue_id=f"REVIEW-NEG-FEE-{t_id}",
                rule_id=RULE_NEG_FEE,
                desc=desc,
                amount=abs(fee),
                order_id=o_id,
                tx_id=t_id,
                exposure_key=f"EXPOSURE-TX-{t_id}",
                affected_rows=[str(rec["index"])]
            )
            flag = AnomalyFlag(
                rule_id=RULE_NEG_FEE,
                rule_name=RULE_METADATA[RULE_NEG_FEE]["name"],
                severity="LOW",
                classification="REVIEW_REQUIRED",
                description=desc,
                amount_at_risk=float(abs(fee))
            )
            add_flag_if_missing(rec["flags"], flag)

    # -------------------------------------------------------------------------
    # 3. FINANCIAL TOTALS BY CURRENCY & ISOLATION
    # -------------------------------------------------------------------------
    all_currencies = sorted(list(set(r["currency"] for r in raw_records)))
    financials_by_currency: List[CurrencyFinancialSummary] = []

    for curr in all_currencies:
        curr_events = [e for e in economic_events if e["currency"] == curr]
        curr_rev = sum((e["gross_amount"] for e in curr_events if e["type"] == "sale"), Decimal("0.00"))
        curr_fees = sum((e["fee"] for e in curr_events), Decimal("0.00"))

        curr_loss = sum(
            (Decimal(str(item.proven_loss_amount)) for item in economic_loss_ledger 
             if any(e["transaction_id"] == item.transaction_id and e["currency"] == curr for e in raw_records)),
            Decimal("0.00")
        )

        curr_exposure_groups: Dict[str, Decimal] = {}
        for item in review_issue_ledger:
            e_key = item.exposure_key
            if not e_key:
                continue
            # Filter exposure key to curr
            if e_key.endswith(f"-{curr}") or any(r["transaction_id"] == item.transaction_id and r["currency"] == curr for r in raw_records):
                curr_exposure_groups[e_key] = max(curr_exposure_groups.get(e_key, Decimal("0.00")), money(item.amount_requiring_review))

        curr_review = Decimal("0.00")
        for e_key, gross_exp in curr_exposure_groups.items():
            already_proven = Decimal("0.00")
            if e_key.startswith("EXPOSURE-ORDER-REFUND-"):
                # e_key format: EXPOSURE-ORDER-REFUND-{order_id}-{curr}
                parts = e_key.replace("EXPOSURE-ORDER-REFUND-", "").split("-")
                o_id_part = parts[0]
                already_proven = order_curr_confirmed_loss_map.get((o_id_part, curr), Decimal("0.00"))

            unproven = max(Decimal("0.00"), gross_exp - already_proven)
            curr_review += unproven

        financials_by_currency.append(CurrencyFinancialSummary(
            currency=curr,
            total_gross_revenue=float(curr_rev),
            total_fees_paid=float(curr_fees),
            confirmed_loss_amount=float(curr_loss),
            potential_review_amount=float(curr_review)
        ))

    # Overall summary values (for single currency, or primary aggregate)
    total_gross_revenue = float(sum((ev["gross_amount"] for ev in economic_events if ev["type"] == "sale"), Decimal("0.00")))
    total_fees_paid = float(sum((ev["fee"] for ev in economic_events), Decimal("0.00")))
    confirmed_loss_amount = float(sum((Decimal(str(item.proven_loss_amount)) for item in economic_loss_ledger), Decimal("0.00")))

    # Review exposure total across all currency exposure groups
    global_exposure_groups: Dict[str, Decimal] = {}
    for item in review_issue_ledger:
        e_key = item.exposure_key
        if not e_key:
            continue
        global_exposure_groups[e_key] = max(global_exposure_groups.get(e_key, Decimal("0.00")), money(item.amount_requiring_review))

    potential_review_amount_dec = Decimal("0.00")
    for e_key, gross_exp in global_exposure_groups.items():
        already_proven = Decimal("0.00")
        if e_key.startswith("EXPOSURE-ORDER-REFUND-"):
            parts = e_key.replace("EXPOSURE-ORDER-REFUND-", "").split("-")
            o_id_part = parts[0]
            curr_part = parts[1] if len(parts) > 1 else "USD"
            already_proven = order_curr_confirmed_loss_map.get((o_id_part, curr_part), Decimal("0.00"))

        unproven = max(Decimal("0.00"), gross_exp - already_proven)
        potential_review_amount_dec += unproven

    potential_review_amount = float(potential_review_amount_dec)

    tx_list: List[TransactionRecord] = []
    anomalous_tx_ids = set()
    high_severity_count = 0

    type_risk_map: Dict[str, float] = {}
    type_count_map: Dict[str, int] = {}
    rule_risk_map: Dict[str, float] = {r: 0.0 for r in RULE_METADATA}
    rule_count_map: Dict[str, int] = {r: 0 for r in RULE_METADATA}

    for rec in raw_records:
        flags = rec["flags"]
        has_anomaly = len(flags) > 0

        if has_anomaly:
            anomalous_tx_ids.add(rec["transaction_id"])
            t_type = rec["type"]
            max_risk_for_tx = max(f.amount_at_risk for f in flags)
            type_risk_map[t_type] = type_risk_map.get(t_type, 0.0) + max_risk_for_tx
            type_count_map[t_type] = type_count_map.get(t_type, 0) + 1

            for f in flags:
                if f.severity == "HIGH":
                    high_severity_count += 1
                rule_risk_map[f.rule_id] += f.amount_at_risk
                rule_count_map[f.rule_id] += 1

        tx_list.append(TransactionRecord(
            transaction_id=rec["transaction_id"],
            order_id=rec["order_id"],
            date=rec["date"],
            type=rec["type"],
            gross_amount=float(rec["gross_amount"]),
            fee=float(rec["fee"]),
            net_amount=float(rec["net_amount"]),
            currency=rec["currency"],
            flags=flags,
            has_anomaly=has_anomaly,
            raw_data=rec["raw_data"]
        ))

    risk_by_type = [
        CategoryRisk(category=tt.upper(), risk_amount=round(amt, 2), count=type_count_map[tt])
        for tt, amt in type_risk_map.items()
    ]
    risk_by_type.sort(key=lambda x: x.risk_amount, reverse=True)

    risk_by_rule = [
        RuleBreakdown(
            rule_id=rid,
            rule_name=RULE_METADATA[rid]["name"],
            classification=RULE_METADATA[rid]["classification"],
            count=rule_count_map[rid],
            risk_amount=round(rule_risk_map[rid], 2)
        )
        for rid in RULE_METADATA
    ]
    risk_by_rule.sort(key=lambda x: x.risk_amount, reverse=True)

    summary = AuditSummary(
        raw_record_count=len(raw_records),
        economic_event_count=len(economic_events),
        total_transactions=len(raw_records),
        total_gross_revenue=total_gross_revenue,
        total_fees_paid=total_fees_paid,
        total_anomalous_transactions=len(anomalous_tx_ids),
        confirmed_loss_amount=confirmed_loss_amount,
        potential_review_amount=potential_review_amount,
        high_severity_count=high_severity_count,
        economic_loss_ledger=economic_loss_ledger,
        review_issue_ledger=review_issue_ledger,
        financials_by_currency=financials_by_currency,
        risk_by_type=risk_by_type,
        risk_by_rule=risk_by_rule
    )

    return summary, tx_list

def add_flag_if_missing(flag_list: List[AnomalyFlag], new_flag: AnomalyFlag):
    if not any(f.rule_id == new_flag.rule_id for f in flag_list):
        flag_list.append(new_flag)
