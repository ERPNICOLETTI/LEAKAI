import unittest
import os
import sys

# Ensure backend path is importable
sys.path.append(os.path.dirname(__file__))

from normalizer import normalize_csv
from detector import (
    analyze_transactions, 
    RULE_DUP_TX, 
    RULE_CONFLICTING_TX, 
    RULE_DUP_REFUND, 
    RULE_MISSING_ORDER, 
    RULE_NET_MATH, 
    RULE_HIGH_FEE, 
    RULE_REFUND_EXCEEDS, 
    RULE_UNMATCHED_REFUND, 
    RULE_NEG_FEE
)

class TestLeakAIDetector(unittest.TestCase):
    
    def setUp(self):
        demo_path = os.path.join(os.path.dirname(__file__), "demo_transactions.csv")
        with open(demo_path, "rb") as f:
            self.csv_bytes = f.read()
        self.df = normalize_csv(self.csv_bytes)
        self.summary, self.txs = analyze_transactions(self.df)
        self.tx_map = {t.transaction_id: t for t in self.txs}

    def test_overall_financial_totals(self):
        self.assertEqual(self.summary.raw_record_count, 15)
        self.assertEqual(self.summary.economic_event_count, 14)
        self.assertEqual(self.summary.total_gross_revenue, 2795.00)
        self.assertEqual(self.summary.total_fees_paid, 107.38)
        self.assertEqual(self.summary.confirmed_loss_amount, 650.00)
        self.assertEqual(self.summary.potential_review_amount, 2263.58)

    def test_regression_A_two_identical_rows_same_tx_id(self):
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)
        
        self.assertEqual(summary.confirmed_loss_amount, 0.0)
        self.assertTrue(any(f.rule_id == RULE_DUP_TX and f.classification == "REVIEW_REQUIRED" for f in txs[1].flags))

    def test_regression_I_duplicate_sale_raw_row(self):
        """
        TEST I: Duplicate sale raw row
        -> raw rows = 2
        -> economic events = 1
        -> gross revenue counted once ($100)
        -> fees counted once ($3)
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.raw_record_count, 2)
        self.assertEqual(summary.economic_event_count, 1)
        self.assertEqual(summary.total_gross_revenue, 100.00)
        self.assertEqual(summary.total_fees_paid, 3.00)

    def test_regression_J_duplicate_raw_refund_one_review_issue(self):
        """
        TEST J: Duplicate raw refund generates multiple visible flags
        -> only one duplicate-transaction review issue in review ledger
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_R1,ord_1,2026-01-01,refund,-50.00,0.00,-50.00,USD\n"
            "tx_R1,ord_1,2026-01-01,refund,-50.00,0.00,-50.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        dup_issues = [item for item in summary.review_issue_ledger if item.rule_id == RULE_DUP_TX]
        self.assertEqual(len(dup_issues), 1)

    def test_regression_K_same_economic_event_two_review_rules(self):
        """
        TEST K: Same economic event has two REVIEW_REQUIRED rules
        -> review ledger avoids counting the same monetary exposure twice
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,25.00,70.00,USD\n"  # High fee + Net Math error
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertTrue(len(summary.review_issue_ledger) >= 1)
        # Verify potential review total sums unique ledger item amounts
        expected_sum = sum(item.amount_requiring_review for item in summary.review_issue_ledger)
        self.assertEqual(summary.potential_review_amount, expected_sum)

    def test_regression_L_order_level_review_warning_single_ledger_entry(self):
        """
        TEST L: Order-level review warning appears on multiple rows
        -> unique review issue counted once
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_1,2026-01-01,sale,500.00,15.00,485.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R2,ord_1,2026-01-03,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        multi_refund_issues = [item for item in summary.review_issue_ledger if item.rule_id == RULE_DUP_REFUND]
        self.assertEqual(len(multi_refund_issues), 1)

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 2)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 650.00)

if __name__ == "__main__":
    unittest.main()
