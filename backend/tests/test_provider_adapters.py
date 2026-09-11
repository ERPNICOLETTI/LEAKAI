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
        df_pp = pd.DataFrame([{"Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer", "Type": "Payment Received", "Status": "Completed", "Currency": "USD", "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123", "Item ID": "ITEM_555"}])

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "sp.csv")
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "pp.csv")

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 0)

    # -------------------------------------------------------------------------
    # NEW REGRESSION TESTS (Integration Safety Fix)
    # -------------------------------------------------------------------------

    def test_M_minimal_valid_generic_csv_processes_successfully(self):
        """A. minimal valid generic CSV with only required headers processes successfully."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_1",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "100.00",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertTrue(val.is_valid)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].transaction_id, "GENERIC:tx_min_1")

    def test_N_generic_csv_without_order_id_processes_successfully(self):
        """B. generic CSV without order_id processes successfully."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_2",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "100.00",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertTrue(val.is_valid)
        self.assertIsNone(events[0].order_id)

    def test_O_generic_csv_without_fee_sets_has_source_fee_false(self):
        """C. generic CSV without fee sets has_source_fee=False."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_3",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "100.00",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertTrue(val.is_valid)
        self.assertFalse(events[0].has_source_fee)

    def test_P_generic_csv_without_net_amount_sets_has_source_net_false(self):
        """D. generic CSV without net_amount sets has_source_net=False."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_4",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "100.00",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertTrue(val.is_valid)
        self.assertFalse(events[0].has_source_net)

    def test_Q_malformed_generic_gross_amount_blocks(self):
        """E. malformed generic gross amount blocks."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_5",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "abc",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertFalse(val.is_valid)
        self.assertEqual(len(events), 0)

    def test_R_decimal_survives_generic_registry_processing(self):
        """F. Decimal survives generic registry processing."""
        df_gen = pd.DataFrame([{
            "transaction_id": "tx_min_6",
            "date": "2026-01-01",
            "type": "sale",
            "gross_amount": "100.50",
            "currency": "USD"
        }])
        val, events = registry.process(df_gen, "min.csv")
        self.assertTrue(val.is_valid)
        self.assertIsInstance(events[0].gross_amount, Decimal)
        self.assertEqual(events[0].gross_amount, Decimal("100.50"))

    def test_S_linker_uses_decimal_matched_amount_and_explicit_link_semantics(self):
        """Test linker uses Decimal matched_amount and explicit link semantics."""
        df_sp = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}])
        df_pp = pd.DataFrame([{"Date": "01/05/2026", "Time": "12:00:00", "TimeZone": "PST", "Name": "Buyer", "Type": "Payment Received", "Status": "Completed", "Currency": "USD", "Gross": "100.00", "Fee": "-3.00", "Net": "97.00", "Transaction ID": "PP123", "Invoice Number": "#1001"}])

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "sp.csv")
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "pp.csv")

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 1)
        self.assertIsInstance(links[0].matched_amount, Decimal)
        self.assertEqual(links[0].matched_amount, Decimal("100.00"))
        self.assertEqual(links[0].link_method, "EXACT_MERCHANT_REFERENCE")
        self.assertEqual(links[0].link_status, "REFERENCE_MATCH")
        self.assertEqual(links[0].evidence_level, "DETERMINISTIC_REFERENCE")

    def test_T_shopify_missing_source_filename_blocks_normalization(self):
        """Test Shopify missing source_filename blocks normalization."""
        df_sp = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "USD"}])
        val, events = ShopifyAdapter.validate_and_normalize(df_sp, source_filename="")
        self.assertFalse(val.is_valid)
        self.assertTrue(any("source_filename" in err for err in val.errors))

    def test_U_shopify_currency_selection_priority(self):
        """Test Shopify currency selection priority (Payout Currency -> Currency -> fallback_currency)."""
        # Case 1: Payout Currency present
        df1 = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Payout Currency": "EUR", "Currency": "GBP"}])
        _, ev1 = ShopifyAdapter.validate_and_normalize(df1, "file1.csv", fallback_currency="USD")
        self.assertEqual(ev1[0].currency, "EUR")

        # Case 2: Payout Currency missing/NaN, Currency present
        df2 = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00", "Currency": "GBP"}])
        _, ev2 = ShopifyAdapter.validate_and_normalize(df2, "file2.csv", fallback_currency="USD")
        self.assertEqual(ev2[0].currency, "GBP")

        # Case 3: Both missing, fallback_currency present
        df3 = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00"}])
        _, ev3 = ShopifyAdapter.validate_and_normalize(df3, "file3.csv", fallback_currency="CAD")
        self.assertEqual(ev3[0].currency, "CAD")

        # Case 4: All missing -> block
        df4 = pd.DataFrame([{"Transaction Date": "2026-01-05", "Type": "charge", "Order": "#1001", "Amount": "100.00", "Fee": "3.00", "Net": "97.00"}])
        val4, _ = ShopifyAdapter.validate_and_normalize(df4, "file4.csv")
        self.assertFalse(val4.is_valid)

if __name__ == "__main__":
    unittest.main()
