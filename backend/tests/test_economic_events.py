import unittest
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv
from detector import analyze_transactions, RULE_DUP_TX, RULE_CONFLICTING_TX

class TestEconomicEvents(unittest.TestCase):
    def test_A_identical_duplicate_transaction_ids(self):
        """
        TEST A — Identical duplicate transaction IDs
        tx_10010 appears twice with identical details ($550.00).
        Expected: Raw records = 2, Economic events = 1, Gross revenue = $550.00.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_10010,ord_1,2026-01-01,sale,550.00,16.50,533.50,USD\n"
            "tx_10010,ord_1,2026-01-01,sale,550.00,16.50,533.50,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.raw_record_count, 2)
        self.assertEqual(summary.economic_event_count, 1)
        self.assertEqual(summary.total_gross_revenue, 550.00)
        self.assertEqual(summary.total_fees_paid, 16.50)

    def test_E_conflicting_transaction_ids(self):
        """
        TEST E — Conflicting transaction IDs
        tx_999 has conflicting amounts across raw records.
        Expected: Excluded from economic reconciliation, review flag raised.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_999,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_999,ord_1,2026-01-01,sale,200.00,6.00,194.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.raw_record_count, 2)
        self.assertEqual(summary.economic_event_count, 0)
        self.assertEqual(summary.total_gross_revenue, 0.00)
        
        has_conflict_rule = any(item.rule_id == RULE_CONFLICTING_TX for item in summary.review_issue_ledger)
        self.assertTrue(has_conflict_rule)

    def test_F_duplicate_export_row_excluded_from_reconciliation(self):
        """
        TEST F — Duplicate export row excluded from reconciliation
        One sale, one exact duplicate sale export row.
        Expected: Sale counted only once in economic revenue.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_100,2026-01-01,sale,300.00,9.00,291.00,USD\n"
            "tx_1,ord_100,2026-01-01,sale,300.00,9.00,291.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.economic_event_count, 1)
        self.assertEqual(summary.total_gross_revenue, 300.00)

    def test_I_duplicate_refund_counted_once_economically(self):
        """
        TEST I — Duplicate refund counted once economically if same transaction ID
        Two export rows with tx_ref_1 (refund $50.00).
        Expected: Refund counted once economically.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_sale,ord_20,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_ref_1,ord_20,2026-01-02,refund,-50.00,0.00,-50.00,USD\n"
            "tx_ref_1,ord_20,2026-01-02,refund,-50.00,0.00,-50.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.economic_event_count, 2)
        self.assertEqual(summary.confirmed_loss_amount, 0.00)

if __name__ == "__main__":
    unittest.main()
