import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv
from detector import analyze_transactions, RULE_DUP_TX, RULE_NET_MATH, RULE_DUP_REFUND

class TestReviewExposure(unittest.TestCase):
    def test_J_review_issue_ledger_uniqueness(self):
        """
        TEST J — Review Issue Ledger uniqueness
        Every unique diagnostic issue must be recorded without dropping diagnostic detail.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        issue_ids = [item.review_issue_id for item in summary.review_issue_ledger]
        self.assertEqual(len(issue_ids), len(set(issue_ids)))
        self.assertIn("REVIEW-DUP-TX-tx_100", issue_ids)

    def test_K_overlapping_review_rules_do_not_double_count(self):
        """
        TEST K — Overlapping review rules do not double-count money
        tx_100 has duplicate TX flag ($100) and net math flag ($5.00).
        Exposure key EXPOSURE-TX-tx_100 must use conservative MAX ($100.00), not sum ($105.00).
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,90.00,USD\n"
            "tx_100,ord_1,2026-01-01,sale,100.00,3.00,90.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.potential_review_amount, 100.00)

    def test_M_order_level_exposure_deduplication(self):
        """
        TEST M — Order-level exposure deduplication
        Order ord_50 has multiple refund issues.
        Exposure key EXPOSURE-ORDER-REFUND-ord_50-USD aggregates under single exposure key.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_s,ord_50,2026-01-01,sale,200.00,6.00,194.00,USD\n"
            "tx_r1,ord_50,2026-01-02,refund,-100.00,0.00,-100.00,USD\n"
            "tx_r2,ord_50,2026-01-03,refund,-100.00,0.00,-100.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.potential_review_amount, 100.00)

    def test_N_confirmed_loss_is_not_counted_again_as_potential_review(self):
        """
        TEST N — Confirmed loss is not counted again as potential review
        Order ord_8803: Sale $100, Refund $600 -> Confirmed loss = $500.
        Refund issue exposure ($600) minus already proven loss ($500) = $100 potential review.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_8803,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_2,ord_8803,2026-01-02,refund,-300.00,0.00,-300.00,USD\n"
            "tx_3,ord_8803,2026-01-03,refund,-300.00,0.00,-300.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        # Total unique refunds = $600. Sale = $100. Confirmed loss = $500.
        # REVIEW-MULTI-REFUND issue amount is $300 (the duplicate refund).
        # Since already proven loss ($500) > gross exposure ($300), unproven review exposure = $0.00.
        self.assertEqual(summary.confirmed_loss_amount, 500.00)
        self.assertEqual(summary.potential_review_amount, 0.00)

if __name__ == "__main__":
    unittest.main()
