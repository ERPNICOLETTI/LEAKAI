import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
try:
    from models import TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, RuleBreakdown, EconomicLossItem
except ImportError:
    from .models import TransactionRecord, AnomalyFlag, AuditSummary, CategoryRisk, RuleBreakdown, EconomicLossItem

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
        "classification": "REVIEW_REQUIRED"  # Defaults to REVIEW_REQUIRED unless proven identical disbursement
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

    # DYNAMIC MEDIAN FEE BASELINE CALCULATION FROM NORMAL SALES
    sale_fee_percentages = []
    for r in records:
        if r["type"] == "sale" and r["gross_amount"] > 0:
            fee_pct = (r["fee"] / r["gross_amount"]) * 100.0
            sale_fee_percentages.append(fee_pct)

    median_fee_pct = float(np.median(sale_fee_percentages)) if sale_fee_percentages else 3.0
    # Flag threshold: fee percentage > 2x median baseline OR > median + 5%
    fee_threshold_pct = max(median_fee_pct * 2.0, median_fee_pct + 5.0)

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

    # RULE 1: DUPLICATE_TRANSACTION_ID (ALWAYS REVIEW_REQUIRED)
    for t_id, indices in tx_id_map.items():
        if len(indices) > 1:
            for idx in indices[1:]:
                rec = records[idx]
                flag = AnomalyFlag(
                    rule_id=RULE_DUP_TX,
                    rule_name=RULE_METADATA[RULE_DUP_TX]["name"],
                    severity=RULE_METADATA[RULE_DUP_TX]["severity"],
                    classification="REVIEW_REQUIRED",
                    description=f"Transaction ID '{t_id}' appears multiple times in raw export. Review gateway logs to confirm if settlement doubled.",
                    amount_at_risk=abs(rec["gross_amount"])
                )
                add_flag_if_missing(rec["flags"], flag)

    # ECONOMIC LOSS LEDGER & PROVEN FINANCIAL LOSS TRACKING
    economic_loss_ledger: List[EconomicLossItem] = []
    proven_loss_tracker: Dict[str, float] = {}  # key: order_id -> proven loss

    # RULE 7: UNMATCHED_REFUND / CHARGEBACK (ALWAYS REVIEW_REQUIRED)
    for rec in records:
        if rec["type"] in ["refund", "chargeback"]:
            o_id = rec["order_id"]
            has_sale = False
            if o_id and o_id in order_id_map:
                has_sale = any(records[i]["type"] == "sale" for i in order_id_map[o_id])
            
            if not has_sale:
                flag = AnomalyFlag(
                    rule_id=RULE_UNMATCHED_REFUND,
                    rule_name=RULE_METADATA[RULE_UNMATCHED_REFUND]["name"],
                    severity=RULE_METADATA[RULE_UNMATCHED_REFUND]["severity"],
                    classification="REVIEW_REQUIRED",
                    description=f"{rec['type'].upper()} of ${abs(rec['gross_amount']):,.2f} has no matching sale in dataset (may exist in prior statement).",
                    amount_at_risk=abs(rec["gross_amount"])
                )
                add_flag_if_missing(rec["flags"], flag)

    # RULE 2: POSSIBLE_DUPLICATED_REFUND & RULE 6: REFUND_EXCEEDS_SALE
    for o_id, indices in order_id_map.items():
        refund_indices = [i for i in indices if records[i]["type"] == "refund"]
        has_sale = any(records[i]["type"] == "sale" for i in indices)

        # RULE 2: POSSIBLE_DUPLICATED_REFUND
        # Strict rule: CONFIRMED_LOSS ONLY IF same order + EXACT same refund amount + separate transaction IDs within 7 days.
        # Otherwise: REVIEW_REQUIRED (could be legitimate partial refunds).
        if len(refund_indices) > 1:
            sorted_refunds = sorted(refund_indices, key=lambda i: records[i]["dt"] if pd.notna(records[i]["dt"]) else pd.Timestamp.min)
            for k in range(1, len(sorted_refunds)):
                r_prev = records[sorted_refunds[k-1]]
                r_curr = records[sorted_refunds[k]]
                
                days_gap = 999
                if pd.notna(r_prev["dt"]) and pd.notna(r_curr["dt"]):
                    days_gap = abs((r_curr["dt"] - r_prev["dt"]).days)
                
                if days_gap <= 7:
                    prev_amt = abs(r_prev["gross_amount"])
                    curr_amt = abs(r_curr["gross_amount"])
                    is_exact_amount = abs(curr_amt - prev_amt) < 0.01

                    if is_exact_amount:
                        classification = "CONFIRMED_LOSS"
                        loss_id = f"LOSS-DUP-REFUND-{o_id}-{r_curr['transaction_id']}"
                        
                        # Add to economic loss ledger
                        if not any(item.economic_loss_id == loss_id for item in economic_loss_ledger):
                            economic_loss_ledger.append(EconomicLossItem(
                                economic_loss_id=loss_id,
                                order_id=o_id,
                                transaction_id=r_curr["transaction_id"],
                                rule_id=RULE_DUP_REFUND,
                                description=f"Proven duplicate refund disbursement of ${curr_amt:,.2f} issued for Order '{o_id}' within {days_gap} day(s).",
                                proven_loss_amount=curr_amt
                            ))
                            proven_loss_tracker[o_id] = proven_loss_tracker.get(o_id, 0.0) + curr_amt

                        desc = f"Proven duplicate refund disbursement of ${curr_amt:,.2f} for Order '{o_id}' (identical amount to previous refund within {days_gap} day(s))."
                    else:
                        classification = "REVIEW_REQUIRED"
                        desc = f"Multiple refunds issued for Order '{o_id}' within {days_gap} day(s) (${prev_amt:,.2f} and ${curr_amt:,.2f}). Review to verify partial refund validity."

                    flag = AnomalyFlag(
                        rule_id=RULE_DUP_REFUND,
                        rule_name=RULE_METADATA[RULE_DUP_REFUND]["name"],
                        severity="HIGH" if classification == "CONFIRMED_LOSS" else "MEDIUM",
                        classification=classification,
                        description=desc,
                        amount_at_risk=curr_amt
                    )
                    add_flag_if_missing(r_curr["flags"], flag)

        # RULE 6: REFUND_EXCEEDS_SALE
        # Strictly CONFIRMED_LOSS ONLY WHEN matching sale exists AND total_refunds > total_sale.
        # Amount MUST BE ONLY total_refunds - total_sale (net excess).
        if has_sale and refund_indices:
            sale_total = sales_by_order.get(o_id, 0.0)
            total_refunds = sum(abs(records[i]["gross_amount"]) for i in refund_indices)
            
            if total_refunds > sale_total + 0.01:
                total_excess = total_refunds - sale_total
                already_proven_dup_loss = proven_loss_tracker.get(o_id, 0.0)
                
                # Deduplicate: Only add remaining un-proven excess to loss ledger
                remaining_excess_loss = max(0.0, total_excess - already_proven_dup_loss)
                
                if remaining_excess_loss > 0.01:
                    loss_id = f"LOSS-EXCESS-REFUND-{o_id}"
                    if not any(item.economic_loss_id == loss_id for item in economic_loss_ledger):
                        economic_loss_ledger.append(EconomicLossItem(
                            economic_loss_id=loss_id,
                            order_id=o_id,
                            transaction_id=records[refund_indices[-1]]["transaction_id"],
                            rule_id=RULE_REFUND_EXCEEDS,
                            description=f"Net refund excess over original sale price for Order '{o_id}' (${total_refunds:,.2f} total refunds vs ${sale_total:,.2f} sale).",
                            proven_loss_amount=round(remaining_excess_loss, 2)
                        ))

                for r_idx in refund_indices:
                    rec = records[r_idx]
                    flag = AnomalyFlag(
                        rule_id=RULE_REFUND_EXCEEDS,
                        rule_name=RULE_METADATA[RULE_REFUND_EXCEEDS]["name"],
                        severity="HIGH",
                        classification="CONFIRMED_LOSS",
                        description=f"Order '{o_id}' cumulative refunds (${total_refunds:,.2f}) exceed original sale (${sale_total:,.2f}) by ${total_excess:,.2f} net excess.",
                        amount_at_risk=round(total_excess, 2)
                    )
                    add_flag_if_missing(rec["flags"], flag)

    # ROW-BY-ROW ANOMALY CHECKS
    for rec in records:
        gross = rec["gross_amount"]
        fee = rec["fee"]
        net = rec["net_amount"]
        t_type = rec["type"]
        o_id = rec["order_id"]

        # RULE 3: MISSING_ORDER_ID (REVIEW_REQUIRED, 0 monetary risk)
        if not o_id and t_type in ["sale", "refund", "chargeback"]:
            flag = AnomalyFlag(
                rule_id=RULE_MISSING_ORDER,
                rule_name=RULE_METADATA[RULE_MISSING_ORDER]["name"],
                severity="LOW",
                classification="REVIEW_REQUIRED",
                description=f"Transaction of type '{t_type.upper()}' is missing order reference metadata.",
                amount_at_risk=0.0
            )
            add_flag_if_missing(rec["flags"], flag)

        # RULE 4: NET_AMOUNT_INCONSISTENCY (REVIEW_REQUIRED)
        expected_net = gross - fee
        if abs(net - expected_net) > 0.01:
            diff = round(abs(net - expected_net), 2)
            flag = AnomalyFlag(
                rule_id=RULE_NET_MATH,
                rule_name=RULE_METADATA[RULE_NET_MATH]["name"],
                severity="MEDIUM",
                classification="REVIEW_REQUIRED",
                description=f"Net settlement variance: Net (${net:,.2f}) != Gross (${gross:,.2f}) - Fee (${fee:,.2f}) [Variance: ${diff:,.2f}]. Review gateway accounting log.",
                amount_at_risk=diff
            )
            add_flag_if_missing(rec["flags"], flag)

        # RULE 5: HIGH_FEE_DETECTED (REVIEW_REQUIRED - Calculated relative to dynamic median baseline)
        if gross > 0 and fee > 0:
            fee_pct = (fee / gross) * 100.0
            if fee_pct > fee_threshold_pct:
                normal_fee = gross * (median_fee_pct / 100.0)
                excess_fee = fee - normal_fee
                flag = AnomalyFlag(
                    rule_id=RULE_HIGH_FEE,
                    rule_name=RULE_METADATA[RULE_HIGH_FEE]["name"],
                    severity="LOW",
                    classification="REVIEW_REQUIRED",
                    description=f"Gateway processing fee of ${fee:,.2f} ({fee_pct:.1f}%) is materially above dataset median sale baseline ({median_fee_pct:.1f}%). Excess: ${excess_fee:,.2f}.",
                    amount_at_risk=round(excess_fee, 2)
                )
                add_flag_if_missing(rec["flags"], flag)

        # RULE 8: INVALID_NEGATIVE_FEE (REVIEW_REQUIRED)
        if fee < 0:
            flag = AnomalyFlag(
                rule_id=RULE_NEG_FEE,
                rule_name=RULE_METADATA[RULE_NEG_FEE]["name"],
                severity="LOW",
                classification="REVIEW_REQUIRED",
                description=f"Transaction contains invalid negative fee of ${fee:,.2f}. Review gateway fee credit adjustment.",
                amount_at_risk=abs(fee)
            )
            add_flag_if_missing(rec["flags"], flag)

    # SUMMARIZE RESULTS & AGGREGATE LEDGER
    tx_list: List[TransactionRecord] = []
    total_gross_revenue = 0.0
    total_fees_paid = 0.0
    anomalous_tx_ids = set()

    # Confirmed loss is STRICTLY the sum of unique Economic Loss Ledger items
    confirmed_loss_amount = round(sum(item.proven_loss_amount for item in economic_loss_ledger), 2)

    potential_review_amount = 0.0
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
                potential_review_amount += rev_max

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
        confirmed_loss_amount=confirmed_loss_amount,
        potential_review_amount=round(potential_review_amount, 2),
        high_severity_count=high_severity_count,
        economic_loss_ledger=economic_loss_ledger,
        risk_by_type=risk_by_type,
        risk_by_rule=risk_by_rule
    )

    return summary, tx_list

def add_flag_if_missing(flag_list: List[AnomalyFlag], new_flag: AnomalyFlag):
    if not any(f.rule_id == new_flag.rule_id for f in flag_list):
        flag_list.append(new_flag)
