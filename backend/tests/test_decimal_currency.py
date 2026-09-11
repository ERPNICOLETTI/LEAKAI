import unittest
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv, parse_decimal_strict
from detector import analyze_transactions

class TestDecimalCurrency(unittest.TestCase):
    def test_O_decimal_exact_subtraction(self):
        """
        TEST O — 0.10 - 0.03 = exact expected value Decimal("0.07")
        """
        val1 = parse_decimal_strict("0.10")
        val2 = parse_decimal_strict("0.03")
        diff = val1 - val2
        self.assertEqual(diff, Decimal("0.07"))
        self.assertNotEqual(float(diff), 0.07000000000000002)

    def test_P_repeated_decimal_additions(self):
        """
        TEST P — repeated 0.10 additions = exact Decimal("0.30")
        """
        total = Decimal("0.00")
        tenth = parse_decimal_strict("0.10")
        for _ in range(3):
            total += tenth
        self.assertEqual(total, Decimal("0.30"))

    def test_Q_multi_currency_usd_and_eur_summaries_isolated(self):
        """
        TEST Q — Multi-currency: USD and EUR summaries isolated
        USD sale = $100.00, EUR sale = 200.00 EUR.
        Expected: Separate currency breakdown items, isolated summaries.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_usd,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_eur,ord_2,2026-01-01,sale,200.00,6.00,194.00,EUR\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        curr_map = {c.currency: c for c in summary.financials_by_currency}
        self.assertIn("USD", curr_map)
        self.assertIn("EUR", curr_map)

        self.assertEqual(curr_map["USD"].total_gross_revenue, 100.00)
        self.assertEqual(curr_map["EUR"].total_gross_revenue, 200.00)

    def test_R_same_order_id_across_currencies_does_not_reconcile(self):
        """
        TEST R — Same order ID across currencies does not reconcile
        Order ord_100 has sale in USD ($100) and refund in EUR (100 EUR).
        Expected: EUR refund is treated as UNMATCHED refund in EUR, does NOT reduce USD sale.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_sale,ord_100,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_ref,ord_100,2026-01-02,refund,-100.00,0.00,-100.00,EUR\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        curr_map = {c.currency: c for c in summary.financials_by_currency}
        self.assertEqual(curr_map["USD"].total_gross_revenue, 100.00)
        self.assertEqual(curr_map["USD"].confirmed_loss_amount, 0.00)
        self.assertEqual(curr_map["EUR"].total_gross_revenue, 0.00)
        self.assertEqual(curr_map["EUR"].potential_review_amount, 100.00)

    def test_S_same_transaction_id_with_conflicting_currencies_rejected(self):
        """
        TEST S — Same transaction ID with conflicting currencies is rejected from reconciliation
        tx_500 appears in USD and EUR.
        Expected: Flagged as CONFLICTING_TRANSACTION_ID, excluded from economic events.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_500,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_500,ord_1,2026-01-01,sale,100.00,3.00,97.00,EUR\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.economic_event_count, 0)
        has_conflict = any(item.rule_id == "CONFLICTING_TRANSACTION_ID" for item in summary.review_issue_ledger)
        self.assertTrue(has_conflict)

if __name__ == "__main__":
    unittest.main()
