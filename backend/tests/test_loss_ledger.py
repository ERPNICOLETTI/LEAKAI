import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv
from detector import analyze_transactions, RULE_DUP_REFUND, RULE_REFUND_EXCEEDS

class TestLossLedger(unittest.TestCase):
    def test_B_refund_exceeds_sale(self):
        """
        TEST B — Refund exceeds sale
        Sale = $100.00, Refund = $600.00.
        Expected: Confirmed loss = $500.00 (exact net excess only).
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_8803,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_2,ord_8803,2026-01-02,refund,-600.00,0.00,-600.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 500.00)
        self.assertEqual(len(summary.economic_loss_ledger), 1)
        self.assertEqual(summary.economic_loss_ledger[0].proven_loss_amount, 500.00)

    def test_C_exact_net_excess_only(self):
        """
        TEST C — Exact net excess only
        Sale = $200.00, Refund = $350.00.
        Expected: Confirmed loss = $150.00 (not $350.00).
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_8805,2026-01-01,sale,200.00,6.00,194.00,USD\n"
            "tx_2,ord_8805,2026-01-02,refund,-350.00,0.00,-350.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 150.00)

    def test_D_duplicate_looking_refunds_remain_review_required(self):
        """
        TEST D — Duplicate-looking refunds remain REVIEW_REQUIRED
        Sale = $100.00, Refund 1 = $50.00, Refund 2 = $50.00 (different TX IDs, total $100.00).
        Expected: Confirmed loss = $0.00 (not exceeded), POSSIBLE_DUPLICATED_REFUND flag present under review.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_sale,ord_8806,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_ref1,ord_8806,2026-01-02,refund,-50.00,0.00,-50.00,USD\n"
            "tx_ref2,ord_8806,2026-01-03,refund,-50.00,0.00,-50.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 0.00)
        has_dup_refund_issue = any(item.rule_id == RULE_DUP_REFUND for item in summary.review_issue_ledger)
        self.assertTrue(has_dup_refund_issue)

    def test_G_no_confirmed_loss_from_heuristics(self):
        """
        TEST G — No confirmed loss from heuristics alone
        Two $50.00 refunds for a $100.00 sale. Total refunds = $100.00.
        Expected: Confirmed loss = $0.00.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_sale,ord_10,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_r1,ord_10,2026-01-02,refund,-50.00,0.00,-50.00,USD\n"
            "tx_r2,ord_10,2026-01-03,refund,-50.00,0.00,-50.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 0.00)

    def test_H_economic_loss_ledger_deduplication(self):
        """
        TEST H — Economic Loss Ledger deduplication
        Repeated evaluation for same order must produce a single clean EconomicLossItem per order/currency.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_99,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_2,ord_99,2026-01-02,refund,-300.00,0.00,-300.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(len(summary.economic_loss_ledger), 1)
        self.assertEqual(summary.economic_loss_ledger[0].order_id, "ord_99")
        self.assertEqual(summary.economic_loss_ledger[0].proven_loss_amount, 200.00)

if __name__ == "__main__":
    unittest.main()
