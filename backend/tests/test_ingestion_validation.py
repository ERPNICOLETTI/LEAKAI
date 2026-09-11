import unittest
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from normalizer import validate_and_normalize_csv, parse_decimal_strict

class TestIngestionValidation(unittest.TestCase):
    def test_T_order_id_before_transaction_id_columns(self):
        """
        TEST T — order_id before transaction_id columns
        """
        csv_data = (
            "order_id,transaction_id,date,type,gross_amount,fee,net_amount,currency\n"
            "ord_8801,tx_999,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertTrue(val_res.is_valid)
        self.assertEqual(df.iloc[0]['transaction_id'], "tx_999")
        self.assertEqual(df.iloc[0]['order_id'], "ord_8801")

    def test_U_malformed_amount(self):
        """
        TEST U — malformed amount
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,abc,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("gross_amount" in err for err in val_res.errors))

    def test_V_missing_currency(self):
        """
        TEST V — missing currency
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,sale,100.00,3.00,97.00,\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Currency" in err for err in val_res.errors))

    def test_W_unknown_transaction_type(self):
        """
        TEST W — unknown transaction type
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,2026-01-01,mystery_event,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Unsupported transaction type" in err for err in val_res.errors))

    def test_X_invalid_date(self):
        """
        TEST X — invalid date
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_1,ord_1,not_a_date,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("date" in err.lower() for err in val_res.errors))

    def test_Y_missing_transaction_id(self):
        """
        TEST Y — missing transaction ID
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            ",ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
        ).encode('utf-8')
        val_res, df = validate_and_normalize_csv(csv_data)
        self.assertFalse(val_res.is_valid)
        self.assertIsNone(df)
        self.assertTrue(any("Transaction ID is missing" in err for err in val_res.errors))

    def test_Z_valid_zero_amount(self):
        """
        TEST Z — valid zero amount
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
