import unittest
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv, parse_decimal_strict
from detector import analyze_transactions, RULE_HIGH_FEE, RULE_NET_MATH

class TestProvenanceAndLocale(unittest.TestCase):
    def test_strict_locale_money_safety_valid_us_formats(self):
        """
        Valid US formats must parse strictly to correct Decimal.
        """
        self.assertEqual(parse_decimal_strict("1234.56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal_strict("1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal_strict("$1,234.56"), Decimal("1234.56"))
        self.assertEqual(parse_decimal_strict("-1234.56"), Decimal("-1234.56"))
        self.assertEqual(parse_decimal_strict("(1234.56)"), Decimal("-1234.56"))

    def test_strict_locale_money_safety_ambiguous_formats_fail(self):
        """
        Ambiguous formats like European "1,23" or "1.234,56" must fail validation.
        """
        with self.assertRaises(ValueError):
            parse_decimal_strict("1,23")
        with self.assertRaises(ValueError):
            parse_decimal_strict("1.234,56")
        with self.assertRaises(ValueError):
            parse_decimal_strict("1234,56")

    def test_absent_fee_column_prevents_high_fee_detected(self):
        """
        If fee column is absent from CSV:
        HIGH_FEE_DETECTED must NOT run.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,1000.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertFalse(df.iloc[0]['has_source_fee'])
        summary, txs = analyze_transactions(df)

        has_high_fee = any(item.rule_id == RULE_HIGH_FEE for item in summary.review_issue_ledger)
        self.assertFalse(has_high_fee, "HIGH_FEE_DETECTED must not run when fee column is absent")

    def test_absent_net_column_prevents_net_amount_inconsistency(self):
        """
        If net_amount column is absent from CSV:
        NET_AMOUNT_INCONSISTENCY must NOT run against derived net value.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,currency\n"
            "tx_1,ord_1,2026-01-01,sale,100.00,50.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertFalse(df.iloc[0]['has_source_net'])
        summary, txs = analyze_transactions(df)

        has_net_math = any(item.rule_id == RULE_NET_MATH for item in summary.review_issue_ledger)
        self.assertFalse(has_net_math, "NET_AMOUNT_INCONSISTENCY must not run when net column is absent")

    def test_absent_fee_with_present_net_prevents_net_amount_inconsistency(self):
        """
        TEST PROVENANCE — source net present, fee column absent
        Expected: validation succeeds, has_source_net = True, has_source_fee = False,
        NET_AMOUNT_INCONSISTENCY does NOT run, HIGH_FEE_DETECTED does NOT run.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,100.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertTrue(df.iloc[0]['has_source_net'])
        self.assertFalse(df.iloc[0]['has_source_fee'])

        summary, txs = analyze_transactions(df)
        has_net_math = any(item.rule_id == RULE_NET_MATH for item in summary.review_issue_ledger)
        has_high_fee = any(item.rule_id == RULE_HIGH_FEE for item in summary.review_issue_ledger)

        self.assertFalse(has_net_math, "NET_AMOUNT_INCONSISTENCY must not run when fee column is absent")
        self.assertFalse(has_high_fee, "HIGH_FEE_DETECTED must not run when fee column is absent")

if __name__ == "__main__":
    unittest.main()
