import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
try:
    from models import TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, RuleBreakdown
except ImportError:
    from .models import TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, RuleBreakdown

RULE_DUP_TX = "DUPLICATE_TRANSACTION_ID"
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
    RULE_DUP_REFUND: {
        "name": "Possible Duplicated Refund",
        "severity": "HIGH",
        "classification": "CONFIRMED_LOSS"
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
        "name": "High Gateway Processing Fee (>15%)",
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
    records: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        tx_id = str(row['transaction_id'])
        order_id = str(row['order_id']) if pd.notna(row['order_id']) and str(row['order_id']).lower() not in ['none', 'nan', ''] else None
        gross = float(row['gross_amount'])
        fee = float(row['fee'])
        net = float(row['net_amount'])
        tx_type = str(row['type']).lower()
        date_str = str(row['date'])
        dt = row['dt']
        curr = str(row['currency'])

        records.append({
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
            "flags": [],
            "raw_data": row['raw_data']
        })

    # Groupings & Indexing
    tx_id_map: Dict[str, List[int]] = {}
    order_id_map: Dict[str, List[int]] = {}
    sales_by_order: Dict[str, float] = {}

    for i, r in enumerate(records):
        t_id = r["transaction_id"]
        o_id = r["order_id"]
        
        tx_id_map.setdefault(t_id, []).append(i)
        if o_id:
            order_id_map.setdefault(o_id, []).append(i)
            if r["type"] == "sale":
                sales_by_order[o_id] = sales_by_order.get(o_id, 0.0) + abs(r["gross_amount"])

    # RULE 1: DUPLICATE_TRANSACTION_ID (REVIEW REQUIRED)
    for t_id, indices in tx_id_map.items():
        if len(indices) > 1:
            for idx in indices[1:]:
                rec = records[idx]
                flag = AnomalyFlag(
                    rule_id=RULE_DUP_TX,
                    rule_name=RULE_METADATA[RULE_DUP_TX]["name"],
                    severity=RULE_METADATA[RULE_DUP_TX]["severity"],
                    classification=RULE_METADATA[RULE_DUP_TX]["classification"],
                    description=f"Transaction ID '{t_id}' appears multiple times in raw export. Review to confirm if gateway double-settled.",
                    amount_at_risk=abs(rec["gross_amount"])
                )
                add_flag_if_missing(rec["flags"], flag)

    # ORDER-LEVEL AUDIT FOR REFUNDS & LOSSES
    # Order Level Confirmed Loss mapping to avoid double-counting across overlapping rules
    order_confirmed_loss: Dict[str, float] = {}

    for o_id, indices in order_id_map.items():
        refund_indices = [i for i in indices if records[i]["type"] in ["refund", "chargeback"]]
        has_sale = any(records[i]["type"] == "sale" for i in indices)
        
        # RULE 7: UNMATCHED_REFUND (REVIEW REQUIRED - sale could be in previous export window)
        if refund_indices and not has_sale:
            for r_idx in refund_indices:
                rec = records[r_idx]
                flag = AnomalyFlag(
                    rule_id=RULE_UNMATCHED_REFUND,
                    rule_name=RULE_METADATA[RULE_UNMATCHED_REFUND]["name"],
                    severity=RULE_METADATA[RULE_UNMATCHED_REFUND]["severity"],
                    classification=RULE_METADATA[RULE_UNMATCHED_REFUND]["classification"],
                    description=f"Refund/Chargeback of ${abs(rec['gross_amount']):,.2f} for Order '{o_id}' has no matching sale in current file. Review prior statement.",
                    amount_at_risk=abs(rec["gross_amount"])
                )
                add_flag_if_missing(rec["flags"], flag)

        # RULE 2: POSSIBLE_DUPLICATED_REFUND (CONFIRMED LOSS - Extra disbursements)
        dup_refund_loss_for_order = 0.0
        if len(refund_indices) > 1:
            sorted_refunds = sorted(refund_indices, key=lambda i: records[i]["dt"] if pd.notna(records[i]["dt"]) else pd.Timestamp.min)
            for k in range(1, len(sorted_refunds)):
                r_prev = records[sorted_refunds[k-1]]
                r_curr = records[sorted_refunds[k]]
                
                days_gap = 999
                if pd.notna(r_prev["dt"]) and pd.notna(r_curr["dt"]):
                    days_gap = abs((r_curr["dt"] - r_prev["dt"]).days)
                
                if days_gap <= 7:
                    dup_loss = abs(r_curr["gross_amount"])
                    dup_refund_loss_for_order += dup_loss
                    flag = AnomalyFlag(
                        rule_id=RULE_DUP_REFUND,
                        rule_name=RULE_METADATA[RULE_DUP_REFUND]["name"],
                        severity=RULE_METADATA[RULE_DUP_REFUND]["severity"],
                        classification=RULE_METADATA[RULE_DUP_REFUND]["classification"],
                        description=f"Duplicate refund disbursement of ${dup_loss:,.2f} issued for Order '{o_id}' within {days_gap} day(s) of previous refund.",
                        amount_at_risk=dup_loss
                    )
                    add_flag_if_missing(r_curr["flags"], flag)

        # RULE 6: REFUND_EXCEEDS_SALE (CONFIRMED LOSS - Only the net excess amount)
        excess_loss_for_order = 0.0
        if has_sale and refund_indices:
            sale_total = sales_by_order.get(o_id, 0.0)
            total_refunds = sum(abs(records[i]["gross_amount"]) for i in refund_indices)
            if total_refunds > sale_total + 0.01:
                excess_loss_for_order = total_refunds - sale_total
                for r_idx in refund_indices:
                    rec = records[r_idx]
                    flag = AnomalyFlag(
                        rule_id=RULE_REFUND_EXCEEDS,
                        rule_name=RULE_METADATA[RULE_REFUND_EXCEEDS]["name"],
                        severity=RULE_METADATA[RULE_REFUND_EXCEEDS]["severity"],
                        classification=RULE_METADATA[RULE_REFUND_EXCEEDS]["classification"],
                        description=f"Order '{o_id}' total refunds (${total_refunds:,.2f}) exceed original sale (${sale_total:,.2f}) by ${excess_loss_for_order:,.2f}.",
                        amount_at_risk=excess_loss_for_order
                    )
                    add_flag_if_missing(rec["flags"], flag)

        # Economic Loss Deduplication per Order:
        # Take the maximum of duplicate refund loss vs net excess loss so the same economic loss is never counted twice!
        order_confirmed_loss[o_id] = max(dup_refund_loss_for_order, excess_loss_for_order)

    # ROW BY ROW CHECKS FOR OTHER RULES
    for rec in records:
        gross = rec["gross_amount"]
        fee = rec["fee"]
        net = rec["net_amount"]
        t_type = rec["type"]
        o_id = rec["order_id"]

        # RULE 3: MISSING_ORDER_ID (REVIEW REQUIRED)
        if not o_id and t_type in ["sale", "refund", "chargeback"]:
            flag = AnomalyFlag(
                rule_id=RULE_MISSING_ORDER,
                rule_name=RULE_METADATA[RULE_MISSING_ORDER]["name"],
                severity=RULE_METADATA[RULE_MISSING_ORDER]["severity"],
                classification=RULE_METADATA[RULE_MISSING_ORDER]["classification"],
                description=f"Transaction of type '{t_type.upper()}' is missing order reference metadata.",
                amount_at_risk=0.0  # Metadata hygiene, 0 monetary risk
            )
            add_flag_if_missing(rec["flags"], flag)

        # RULE 4: NET_AMOUNT_INCONSISTENCY (REVIEW REQUIRED)
        expected_net = gross - fee
        if abs(net - expected_net) > 0.01:
            diff = abs(net - expected_net)
            flag = AnomalyFlag(
                rule_id=RULE_NET_MATH,
                rule_name=RULE_METADATA[RULE_NET_MATH]["name"],
                severity=RULE_METADATA[RULE_NET_MATH]["severity"],
                classification=RULE_METADATA[RULE_NET_MATH]["classification"],
                description=f"Net settlement math discrepancy: Net (${net:,.2f}) != Gross (${gross:,.2f}) - Fee (${fee:,.2f}). Variance: ${diff:,.2f}.",
                amount_at_risk=diff
            )
            add_flag_if_missing(rec["flags"], flag)

        # RULE 5: HIGH_FEE_DETECTED (REVIEW REQUIRED)
        if gross > 0 and fee > 0:
            fee_pct = (fee / gross) * 100
            if fee_pct > 15.0:
                excess_fee = fee - (gross * 0.15)
                flag = AnomalyFlag(
                    rule_id=RULE_HIGH_FEE,
                    rule_name=RULE_METADATA[RULE_HIGH_FEE]["name"],
                    severity=RULE_METADATA[RULE_HIGH_FEE]["severity"],
                    classification=RULE_METADATA[RULE_HIGH_FEE]["classification"],
                    description=f"Gateway processing fee of ${fee:,.2f} represents {fee_pct:.1f}% of gross (exceeds 15% cap).",
                    amount_at_risk=round(excess_fee, 2)
                )
                add_flag_if_missing(rec["flags"], flag)

        # RULE 8: INVALID_NEGATIVE_FEE (REVIEW REQUIRED)
        if fee < 0:
            flag = AnomalyFlag(
                rule_id=RULE_NEG_FEE,
                rule_name=RULE_METADATA[RULE_NEG_FEE]["name"],
                severity=RULE_METADATA[RULE_NEG_FEE]["severity"],
                classification=RULE_METADATA[RULE_NEG_FEE]["classification"],
                description=f"Transaction contains invalid negative fee of ${fee:,.2f}.",
                amount_at_risk=abs(fee)
            )
            add_flag_if_missing(rec["flags"], flag)

    # SUMMARIZE AUDIT METRICS ACCORDING TO STRICT AUDIT GUIDELINES
    tx_list: List[TransactionRecord] = []
    total_gross_revenue = 0.0
    total_fees_paid = 0.0
    anomalous_tx_ids = set()

    # Total confirmed loss is sum of order-level deduplicated confirmed losses
    confirmed_loss_amount = sum(order_confirmed_loss.values())

    potential_risk_amount = 0.0
    high_severity_count = 0

    type_risk_map: Dict[str, float] = {}
    type_count_map: Dict[str, int] = {}

    rule_risk_map: Dict[str, float] = {r: 0.0 for r in RULE_METADATA}
    rule_count_map: Dict[str, int] = {r: 0 for r in RULE_METADATA}

    for rec in records:
        gross = rec["gross_amount"]
        fee = rec["fee"]

        if rec["type"] == "sale":
            total_gross_revenue += gross
        total_fees_paid += fee

        flags = rec["flags"]
        has_anomaly = len(flags) > 0

        if has_anomaly:
            anomalous_tx_ids.add(rec["transaction_id"])

            review_flags = [f for f in flags if f.classification == "REVIEW_REQUIRED"]
            if review_flags:
                rev_max = max(f.amount_at_risk for f in review_flags)
                potential_risk_amount += rev_max

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
            gross_amount=gross,
            fee=fee,
            net_amount=rec["net_amount"],
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
        total_transactions=len(df),
        total_gross_revenue=round(total_gross_revenue, 2),
        total_fees_paid=round(total_fees_paid, 2),
        total_anomalous_transactions=len(anomalous_tx_ids),
        confirmed_loss_amount=round(confirmed_loss_amount, 2),
        potential_risk_amount=round(potential_risk_amount, 2),
        high_severity_count=high_severity_count,
        risk_by_type=risk_by_type,
        risk_by_rule=risk_by_rule
    )

    return summary, tx_list

def add_flag_if_missing(flag_list: List[AnomalyFlag], new_flag: AnomalyFlag):
    if not any(f.rule_id == new_flag.rule_id for f in flag_list):
        flag_list.append(new_flag)
