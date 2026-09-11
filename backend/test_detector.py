import unittest
import os
import sys
import pandas as pd

# Ensure backend path is importable
sys.path.append(os.path.dirname(__file__))

from normalizer import normalize_csv
from detector import analyze_transactions, RULE_DUP_TX, RULE_DUP_REFUND, RULE_MISSING_ORDER, RULE_NET_MATH, RULE_HIGH_FEE, RULE_REFUND_EXCEEDS, RULE_UNMATCHED_REFUND, RULE_NEG_FEE

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
        self.assertEqual(self.summary.potential_review_amount, 1713.58)
        self.assertEqual(self.summary.total_anomalous_transactions, 9)

    def test_regression_A_two_identical_rows_same_tx_id(self):
        """
        TEST A: Two identical rows with same transaction_id
        -> DUPLICATE_TRANSACTION_ID = REVIEW_REQUIRED
        -> confirmed loss = $0
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

    def test_regression_B_one_sale_one_refund_one_duplicate_raw_row(self):
        """
        TEST B: One sale $100, refund tx_A $100, duplicate row tx_A $100
        -> confirmed loss = $0
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 0.0)

    def test_regression_C_one_sale_two_distinct_refund_txs(self):
        """
        TEST C: One sale $100, refund tx_A $100, refund tx_B $100
        -> confirmed excess loss = $100
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

    def test_regression_D_sale_refund_txA_dup_raw_txA_refund_txB(self):
        """
        TEST D: One sale $100, refund tx_A $100, duplicate tx_A row, refund tx_B $100
        -> confirmed loss must still equal $100, NOT $200.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_S1,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R1,ord_1,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_R2,ord_1,2026-01-03,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 100.0)

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 2)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 650.00)

if __name__ == "__main__":
    unittest.main()
