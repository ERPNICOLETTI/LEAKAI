import unittest
import os
import sys
from decimal import Decimal

# Ensure backend path is importable
sys.path.append(os.path.dirname(__file__))

from normalizer import validate_and_normalize_csv, parse_decimal_strict, normalize_csv
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
        self.val_result, self.df = validate_and_normalize_csv(self.csv_bytes)
        self.summary, self.txs = analyze_transactions(self.df)
        self.tx_map = {t.transaction_id: t for t in self.txs}

    def test_overall_financial_totals(self):
        self.assertTrue(self.val_result.is_valid)
        self.assertEqual(self.summary.raw_record_count, 15)
        self.assertEqual(self.summary.economic_event_count, 14)
        self.assertEqual(self.summary.total_gross_revenue, 2795.00)
        self.assertEqual(self.summary.total_fees_paid, 107.38)
        self.assertEqual(self.summary.confirmed_loss_amount, 650.00)
        self.assertEqual(self.summary.potential_review_amount, 1613.58)

    def test_regression_T_order_id_before_transaction_id_columns(self):
        """
        TEST T — order_id before transaction_id columns
        CSV column order: order_id,transaction_id,...
        Expected: correct mapping, transaction_id must NOT accidentally map to order_id.
        """
        csv_data = (
            "order_id,transaction_id,date,type,gross_amount,fee,net_amount,currency\n"
            "ord_8801,tx_999,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertEqual(df.iloc[0]['transaction_id'], "tx_999")
        self.assertEqual(df.iloc[0]['order_id'], "ord_8801")

    def test_regression_U_malformed_amount(self):
        """
        TEST U — malformed amount
        gross_amount = "abc"
        Expected: validation error, NOT Decimal("0.00"), NO financial analysis.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,abc,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("gross_amount" in err for err in val_res.errors))

    def test_regression_V_missing_currency(self):
        """
        TEST V — missing currency
        Expected: validation error, NO automatic USD assumption.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,100.00,3.00,97.00,\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Currency" in err for err in val_res.errors))

    def test_regression_W_unknown_transaction_type(self):
        """
        TEST W — unknown transaction type
        type = "mystery_event"
        Expected: must NOT become sale, validation error.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,mystery_event,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Unsupported transaction type" in err for err in val_res.errors))

    def test_regression_X_invalid_date(self):
        """
        TEST X — invalid date
        Expected: must NOT become 2026-01-01, validation error.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,not_a_date,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("date" in err.lower() for err in val_res.errors))

    def test_regression_Y_missing_transaction_id(self):
        """
        TEST Y — missing transaction ID
        Expected: no synthetic authoritative transaction ID used for reconciliation.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            ",ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Transaction ID is missing" in err for err in val_res.errors))

    def test_regression_Z_valid_zero_amount(self):
        """
        TEST Z — valid zero amount
        gross_amount = "0.00"
        Expected: valid Decimal zero, distinguishable from parsing failure.
        """
        dec = parse_decimal_strict("0.00")
        self.assertEqual(dec, Decimal("0.00"))
        
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,0.00,0.00,0.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertEqual(df.iloc[0]['gross_amount'], Decimal("0.00"))

if __name__ == "__main__":
    unittest.main()
