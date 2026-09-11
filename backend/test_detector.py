import unittest
import os
import sys

# Ensure backend path is importable
sys.path.append(os.path.dirname(__file__))

from normalizer import normalize_csv
from detector import analyze_transactions, RULE_DUP_TX, RULE_CONFLICTING_TX, RULE_DUP_REFUND, RULE_MISSING_ORDER, RULE_NET_MATH, RULE_HIGH_FEE, RULE_REFUND_EXCEEDS, RULE_UNMATCHED_REFUND, RULE_NEG_FEE

class TestLeakAIDetector(unittest.TestCase):
    
    def setUp(self):
        demo_path = os.path.join(os.path.dirname(__file__), "demo_transactions.csv")
        with open(demo_path, "rb") as f:
            self.csv_bytes = f.read()
        self.df = normalize_csv(self.csv_bytes)
        self.summary, self.txs = analyze_transactions(self.df)
        self.tx_map = {t.transaction_id: t for t in self.txs}

    def test_overall_financial_totals(self):
        self.assertEqual(self.summary.total_transactions, 15)
        self.assertEqual(self.summary.total_gross_revenue, 2795.00)
        self.assertEqual(self.summary.total_fees_paid, 107.38)
        self.assertEqual(self.summary.confirmed_loss_amount, 650.00)
        self.assertEqual(self.summary.potential_review_amount, 2263.58)
        self.assertEqual(self.summary.total_anomalous_transactions, 9)

    def test_regression_E_identical_transaction_id_duplicated(self):
        """
        TEST E: Same transaction ID duplicated identically
        -> one economic event
        -> REVIEW_REQUIRED duplicate
        -> no confirmed loss caused by duplicate row
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)
        
        self.assertEqual(summary.confirmed_loss_amount, 0.0)
        self.assertTrue(any(f.rule_id == RULE_DUP_TX and f.classification == "REVIEW_REQUIRED" for f in txs[1].flags))

    def test_regression_F_same_tx_id_different_amounts_conflicting(self):
        """
        TEST F: Same transaction ID but different amounts
        -> CONFLICTING_TRANSACTION_ID
        -> excluded from confirmed-loss reconciliation
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,200.00,6.00,194.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-150.00,0.00,-150.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertTrue(any(f.rule_id == RULE_CONFLICTING_TX for f in txs[0].flags))
        self.assertTrue(any(f.rule_id == RULE_CONFLICTING_TX for f in txs[1].flags))
        # Excluded from confirmed loss reconciliation because sale identity is ambiguous
        self.assertEqual(summary.confirmed_loss_amount, 0.0)

    def test_regression_G_two_diff_txs_same_order_refunds_do_not_exceed_sale(self):
        """
        TEST G: Two different transaction IDs, same order, same refund amount within 1 day,
        but total refunds do NOT exceed sale
        -> POSSIBLE_DUPLICATED_REFUND = REVIEW_REQUIRED
        -> confirmed loss = 0
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_1,2026-01-01,sale,500.00,15.00,485.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R2,ord_1,2026-01-03,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 0.0)
        self.assertTrue(any(f.rule_id == RULE_DUP_REFUND and f.classification == "REVIEW_REQUIRED" for f in txs[2].flags))

    def test_regression_H_two_diff_txs_same_order_refunds_exceed_sale_by_100(self):
        """
        TEST H: Two different transaction IDs, same order, same refund amount,
        and total unique refunds exceed sale by $100
        -> duplicate refund warning = REVIEW_REQUIRED
        -> REFUND_EXCEEDS_SALE confirmed loss = exactly $100
        -> never count the same $100 twice
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R2,ord_1,2026-01-03,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 100.0)
        self.assertTrue(any(f.rule_id == RULE_DUP_REFUND and f.classification == "REVIEW_REQUIRED" for f in txs[2].flags))
        self.assertTrue(any(f.rule_id == RULE_REFUND_EXCEEDS and f.classification == "CONFIRMED_LOSS" for f in txs[2].flags))

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 2)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 650.00)

if __name__ == "__main__":
    unittest.main()
