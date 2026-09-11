import unittest
import os
import sys
import pandas as pd
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from adapters.shopify import ShopifyAdapter
from adapters.paypal import PayPalAdapter
from adapters.registry import registry
from linker import perform_conservative_cross_provider_linking

class TestProviderAdaptersReality(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    def test_A_import_registry_and_linker_succeeds(self):
        """A. importing registry and linker succeeds."""
        from adapters.registry import registry as reg
        from linker import perform_conservative_cross_provider_linking as link_fn
        self.assertIsNotNone(reg)
        self.assertIsNotNone(link_fn)

    def test_B_random_csv_does_not_fall_back_to_generic(self):
        """B. random CSV does NOT fall back to GENERIC (must be UNKNOWN / blocked)."""
        headers = ["Date", "Type", "Amount", "Fee", "Net"]
        res = registry.detect(headers)
        self.assertEqual(res.provider_detected, "UNKNOWN")
        self.assertEqual(res.export_type_detected, "UNSUPPORTED")

    def test_C_exact_canonical_csv_does_use_generic(self):
        """C. exact canonical CSV DOES use GENERIC."""
        headers = ["transaction_id", "date", "type", "gross_amount", "currency"]
        res = registry.detect(headers)
        self.assertEqual(res.provider_detected, "GENERIC")
        self.assertEqual(res.export_type_detected, "GENERIC_CANONICAL_CSV")

    def test_D_shopify_payout_csv_without_payout_currency_does_not_fail_header_detection(self):
        """D. current documented Shopify payout CSV without Payout Currency does not falsely fail because of an invented required header."""
        headers = ["Transaction Date", "Type", "Order", "Amount", "Fee", "Net"]
        res = ShopifyAdapter.detect(headers)
        self.assertEqual(res.provider_detected, "SHOPIFY")
        self.assertEqual(res.confidence, 1.0)

    def test_E_shopify_export_without_transaction_id_keeps_source_tx_id_none(self):
        """E. Shopify export without provider transaction ID keeps source_transaction_id = None."""
        df_sp = pd.DataFrame([{
            "Transaction Date": "2026-01-05",
            "Type": "charge",
            "Order": "#1001",
            "Amount": "150.00",
            "Fee": "4.35",
            "Net": "145.65",
            "Payout Currency": "USD"
        }])
        val, events = ShopifyAdapter.validate_and_normalize(df_sp, "test.csv")
        self.assertTrue(val.is_valid)
        self.assertIsNone(events[0].source_transaction_id)

    def test_F_internal_shopify_row_identity_remains_unique(self):
        """F. internal Shopify row identity remains unique."""
        df_sp = pd.DataFrame([
            {"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"},
            {"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}
        ])
        val, events = ShopifyAdapter.validate_and_normalize(df_sp, "test.csv")
        self.assertTrue(val.is_valid)
        self.assertNotEqual(events[0].transaction_id, events[1].transaction_id)
        self.assertIn("ROW_1", events[0].transaction_id)
        self.assertIn("ROW_2", events[1].transaction_id)

    def test_G_paypal_item_id_is_not_used_as_order_reference(self):
        """G. PayPal Item ID is NOT used as order reference."""
        df_pp = pd.DataFrame([{
            "Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer",
            "Type": "Payment Received", "Status": "Completed", "Currency": "USD",
            "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123",
            "Item ID": "ITEM_99999"
        }])
        val, events = PayPalAdapter.validate_and_normalize(df_pp, "test.csv")
        self.assertTrue(val.is_valid)
        self.assertIsNone(events[0].source_order_reference)

    def test_H_paypal_invoice_number_can_be_used_as_merchant_order_reference(self):
        """H. PayPal Invoice Number CAN be used as merchant order reference."""
        df_pp = pd.DataFrame([{
            "Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer",
            "Type": "Payment Received", "Status": "Completed", "Currency": "USD",
            "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123",
            "Invoice Number": "#1001"
        }])
        val, events = PayPalAdapter.validate_and_normalize(df_pp, "test.csv")
        self.assertTrue(val.is_valid)
        self.assertEqual(events[0].source_order_reference, "#1001")

    def test_I_payment_sent_is_not_automatically_classified_as_refund(self):
        """I. Payment Sent is NOT automatically classified as refund."""
        df_pp = pd.DataFrame([{
            "Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Vendor",
            "Type": "Payment Sent", "Status": "Completed", "Currency": "USD",
            "Gross": "-50.00", "Fee": "0.00", "Net": "-50.00", "Transaction ID": "PP999"
        }])
        val, events = PayPalAdapter.validate_and_normalize(df_pp, "test.csv")
        self.assertFalse(val.is_valid)
        self.assertTrue(any("Payment Sent" in err for err in val.errors))

    def test_J_different_currencies_do_not_cross_link(self):
        """J. different currencies do not cross-link."""
        df_sp = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}])
        df_pp = pd.DataFrame([{"Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer", "Type": "Payment Received", "Status": "Completed", "Currency": "EUR", "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123", "Invoice Number": "#1001"}])

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "sp.csv")
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "pp.csv")

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 0)

    def test_K_same_amount_without_explicit_valid_reference_does_not_link(self):
        """K. same amount without explicit valid reference does not link."""
        df_sp = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}])
        df_pp = pd.DataFrame([{"Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer", "Type": "Payment Received", "Status": "Completed", "Currency": "USD", "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123", "Invoice Number": "#9999"}])

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "sp.csv")
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "pp.csv")

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 0)

    def test_L_same_item_id_across_providers_does_not_link(self):
        """L. same Item ID across providers does not link."""
        df_sp = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "ITEM_555", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}])
        # PayPal row has Item ID = ITEM_555, but NO Invoice Number
        df_pp = pd.DataFrame([{"Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer", "Type": "Payment Received", "Status": "Completed", "Currency": "USD", "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123", "Item ID": "ITEM_555"}])

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "sp.csv")
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "pp.csv")

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 0)

if __name__ == "__main__":
    unittest.main()
