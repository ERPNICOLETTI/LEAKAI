import unittest
import os
import sys

# Ensure backend path is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv
from detector import analyze_transactions

class TestDemoGolden(unittest.TestCase):
    def test_demo_transactions_golden_benchmark(self):
        demo_path = os.path.join(os.path.dirname(__file__), "..", "demo_transactions.csv")
        with open(demo_path, "rb") as f:
            csv_bytes = f.read()

        val_result, df = validate_and_normalize_csv(csv_bytes)
        self.assertTrue(val_result.is_valid, "demo_transactions.csv must pass validation")

        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.raw_record_count, 15, "Raw records must equal 15")
        self.assertEqual(summary.economic_event_count, 14, "Economic events must equal 14")
        self.assertEqual(summary.total_gross_revenue, 2795.00, "Gross revenue USD must equal 2795.00")
        self.assertEqual(summary.total_fees_paid, 107.38, "Fees USD must equal 107.38")
        self.assertEqual(summary.confirmed_loss_amount, 650.00, "Confirmed loss USD must equal 650.00")
        self.assertEqual(summary.potential_review_amount, 1613.58, "Potential review USD must equal 1613.58")

        # Economic Loss Ledger exact items check
        self.assertEqual(len(summary.economic_loss_ledger), 2, "Must contain exactly 2 economic loss items")
        loss_ids = {item.economic_loss_id for item in summary.economic_loss_ledger}
        self.assertIn("LOSS-EXCESS-REFUND-ord_8803-USD", loss_ids)
        self.assertIn("LOSS-EXCESS-REFUND-ord_8806-USD", loss_ids)

        loss_amounts = {item.proven_loss_amount for item in summary.economic_loss_ledger}
        self.assertIn(550.00, loss_amounts)
        self.assertIn(100.00, loss_amounts)

if __name__ == "__main__":
    unittest.main()
