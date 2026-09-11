import unittest
import os
import sys

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
        self.assertEqual(self.summary.confirmed_loss_amount, 1200.00)
        self.assertEqual(self.summary.potential_review_amount, 1713.58)
        self.assertEqual(self.summary.total_anomalous_transactions, 9)

    def test_high_fee_detected_tx_10004(self):
        tx = self.tx_map["tx_10004"]
        self.assertTrue(tx.has_anomaly)
        rules = [f.rule_id for f in tx.flags]
        self.assertIn(RULE_HIGH_FEE, rules)
        flag = next(f for f in tx.flags if f.rule_id == RULE_HIGH_FEE)
        self.assertEqual(flag.classification, "REVIEW_REQUIRED")
        self.assertEqual(flag.amount_at_risk, 17.48)

    def test_missing_order_tx_10005(self):
        tx = self.tx_map["tx_10005"]
        self.assertTrue(tx.has_anomaly)
        rules = [f.rule_id for f in tx.flags]
        self.assertIn(RULE_MISSING_ORDER, rules)
        self.assertIn(RULE_UNMATCHED_REFUND, rules)
        flag = next(f for f in tx.flags if f.rule_id == RULE_MISSING_ORDER)
        self.assertEqual(flag.classification, "REVIEW_REQUIRED")
        self.assertEqual(flag.amount_at_risk, 0.0)

    def test_refund_exceeds_sale_ord_8803(self):
        # tx_10006 ($600) and tx_10007 ($700) for ord_8803 ($1200 sale)
        tx7 = self.tx_map["tx_10007"]
        self.assertTrue(tx7.has_anomaly)
        rules = [f.rule_id for f in tx7.flags]
        self.assertIn(RULE_REFUND_EXCEEDS, rules)
        flag = next(f for f in tx7.flags if f.rule_id == RULE_REFUND_EXCEEDS)
        self.assertEqual(flag.classification, "CONFIRMED_LOSS")
        self.assertEqual(flag.amount_at_risk, 100.00)

    def test_net_amount_inconsistency_tx_10008(self):
        tx = self.tx_map["tx_10008"]
        self.assertTrue(tx.has_anomaly)
        rules = [f.rule_id for f in tx.flags]
        self.assertIn(RULE_NET_MATH, rules)
        flag = next(f for f in tx.flags if f.rule_id == RULE_NET_MATH)
        self.assertEqual(flag.classification, "REVIEW_REQUIRED")
        self.assertEqual(flag.amount_at_risk, 11.10)

    def test_duplicate_refund_and_tx_id_ord_8806(self):
        # tx_10010 ($550 duplicate) and tx_10011 ($550 3rd refund) for ord_8806 ($550 sale)
        tx10 = [t for t in self.txs if t.transaction_id == "tx_10010"][1]  # duplicate row
        rules = [f.rule_id for f in tx10.flags]
        self.assertIn(RULE_DUP_TX, rules)
        self.assertIn(RULE_DUP_REFUND, rules)
        self.assertIn(RULE_REFUND_EXCEEDS, rules)
        
        dup_flag = next(f for f in tx10.flags if f.rule_id == RULE_DUP_REFUND)
        self.assertEqual(dup_flag.classification, "CONFIRMED_LOSS")
        self.assertEqual(dup_flag.amount_at_risk, 550.00)

    def test_unmatched_chargeback_tx_10012(self):
        tx = self.tx_map["tx_10012"]
        self.assertTrue(tx.has_anomaly)
        rules = [f.rule_id for f in tx.flags]
        self.assertIn(RULE_UNMATCHED_REFUND, rules)
        flag = next(f for f in tx.flags if f.rule_id == RULE_UNMATCHED_REFUND)
        self.assertEqual(flag.classification, "REVIEW_REQUIRED")
        self.assertEqual(flag.amount_at_risk, 180.00)

    def test_invalid_negative_fee_tx_10013(self):
        tx = self.tx_map["tx_10013"]
        self.assertTrue(tx.has_anomaly)
        rules = [f.rule_id for f in tx.flags]
        self.assertIn(RULE_NEG_FEE, rules)
        flag = next(f for f in tx.flags if f.rule_id == RULE_NEG_FEE)
        self.assertEqual(flag.classification, "REVIEW_REQUIRED")
        self.assertEqual(flag.amount_at_risk, 5.00)

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 3)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 1200.00)

if __name__ == "__main__":
    unittest.main()
