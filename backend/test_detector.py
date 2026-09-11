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
        self.assertEqual(self.summary.potential_review_amount, 1613.58)

    def test_regression_K_same_economic_event_two_review_rules_no_double_counting(self):
        """
        TEST K: Real anti-double-counting test
        One transaction: gross = $100, fee anomaly = $20 exposure, net inconsistency = $20 exposure
        Both review issues must exist.
        Expected: review issue count = 2, potential review exposure = $20 (NOT $40)
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_0a,ord_0a,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_0b,ord_0b,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_0c,ord_0c,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,23.00,57.00,USD\n"  # Fee 23 (excess $20 over 3% baseline), Net 57 vs 77 (math diff $20)
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(len(summary.review_issue_ledger), 2)
        # Potential review amount must NOT double-count the $20 exposure (must equal $20, not $40)
        self.assertEqual(summary.potential_review_amount, 20.00)

    def test_regression_M_ord_8806_scenario_no_double_reporting_confirmed_and_potential(self):
        """
        TEST M: Scenario similar to ord_8806
        sale = $550, refund tx_A = $550, duplicate raw tx_A row, refund tx_B = $550
        Expected:
        - duplicate transaction review exists
        - multiple refund review exists
        - confirmed loss = $550 from refund excess
        - review issues remain visible
        - potential review must NOT count the same $550 twice
        - confirmed loss and potential review must not double-report exact same proven exposure
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_8806,2026-01-01,sale,550.00,16.25,533.75,USD\n"
            "tx_R1,ord_8806,2026-01-02,refund,-550.00,0.00,-550.00,USD\n"
            "tx_R1,ord_8806,2026-01-02,refund,-550.00,0.00,-550.00,USD\n"
            "tx_R2,ord_8806,2026-01-04,refund,-550.00,0.00,-550.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 550.00)
        self.assertTrue(any(item.rule_id == RULE_DUP_TX for item in summary.review_issue_ledger))
        self.assertTrue(any(item.rule_id == RULE_DUP_REFUND for item in summary.review_issue_ledger))
        # Potential review exposure for tx_R1 duplicate row ($550) + ord_8806 refund pool ($550 - $550 proven = $0) = $550
        self.assertEqual(summary.potential_review_amount, 550.00)

    def test_regression_N_high_fee_15_and_net_math_10_same_tx_max_exposure(self):
        """
        TEST N: One transaction has:
        - HIGH_FEE_DETECTED = $15 exposure
        - NET_AMOUNT_INCONSISTENCY = $10 exposure
        Same transaction
        Expected: two review issues, one transaction exposure group, potential review = MAX($15, $10) = $15
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_0a,ord_0a,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_0b,ord_0b,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_0c,ord_0c,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_1,ord_1,2026-01-01,sale,100.00,18.00,72.00,USD\n"  # Fee 18 (excess $15 over 3% baseline), Net 72 vs 82 (math diff $10)
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(len(summary.review_issue_ledger), 2)
        self.assertEqual(summary.potential_review_amount, 15.00)

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 2)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 650.00)

if __name__ == "__main__":
    unittest.main()
