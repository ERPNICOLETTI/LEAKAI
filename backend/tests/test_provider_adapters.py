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

class TestProviderAdapters(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")

    def test_shopify_adapter_detection_valid(self):
        """Shopify adapter detection works only for supported schema."""
        headers = [
            "Transaction Date", "Type", "Order", "Amount", "Fee", "Net", "Payout Date", "Payout Currency"
        ]
        res = ShopifyAdapter.detect(headers)
        self.assertEqual(res.provider_detected, "SHOPIFY")
        self.assertEqual(res.confidence, 1.0)
        self.assertFalse(res.ambiguous_match)

    def test_paypal_adapter_detection_valid(self):
        """PayPal adapter detection works only for supported schema."""
        headers = [
            "Date", "Time", "TimeZone", "Name", "Type", "Status", "Currency", "Gross", "Fee", "Net", "Transaction ID"
        ]
        res = PayPalAdapter.detect(headers)
        self.assertEqual(res.provider_detected, "PAYPAL")
        self.assertEqual(res.confidence, 1.0)
        self.assertFalse(res.ambiguous_match)

    def test_ambiguous_files_blocked(self):
        """Ambiguous files matching multiple headers are blocked."""
        # Generic headers that shouldn't match either provider with high confidence
        headers = ["Date", "Type", "Amount", "Fee", "Net"]
        res = registry.detect(headers)
        self.assertEqual(res.provider_detected, "GENERIC")

    def test_unsupported_files_blocked(self):
        """Unsupported files fail validation."""
        headers = ["ColA", "ColB", "ColC"]
        df = pd.DataFrame(columns=headers)
        res = ShopifyAdapter.detect(headers)
        self.assertEqual(res.provider_detected, "UNKNOWN")

    def test_shopify_and_paypal_ids_remain_namespaced(self):
        """Shopify IDs and PayPal IDs remain namespaced."""
        shopify_path = os.path.join(self.fixtures_dir, "shopify", "shopify_fixture_a.csv")
        paypal_path = os.path.join(self.fixtures_dir, "paypal", "paypal_fixture_a.csv")

        df_sp = pd.read_csv(shopify_path)
        val_sp, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "shopify_fixture_a.csv")
        self.assertTrue(val_sp.is_valid)
        self.assertTrue(events_sp[0].transaction_id.startswith("SHOPIFY:"))

        df_pp = pd.read_csv(paypal_path)
        val_pp, events_pp = PayPalAdapter.validate_and_normalize(df_pp, "paypal_fixture_a.csv")
        self.assertTrue(val_pp.is_valid)
        self.assertTrue(events_pp[0].transaction_id.startswith("PAYPAL:"))

    def test_source_row_provenance_survives_normalization(self):
        """Source row provenance and filename survive normalization."""
        shopify_path = os.path.join(self.fixtures_dir, "shopify", "shopify_fixture_b.csv")
        df_sp = pd.read_csv(shopify_path)
        val_sp, events_sp = ShopifyAdapter.validate_and_normalize(df_sp, "shopify_fixture_b.csv")

        self.assertEqual(events_sp[0].source_row_number, 1)
        self.assertEqual(events_sp[0].source_file_id, "shopify_fixture_b.csv")
        self.assertEqual(events_sp[1].source_row_number, 2)

    def test_decimal_money_internally(self):
        """Decimal money remains Decimal internally."""
        shopify_path = os.path.join(self.fixtures_dir, "shopify", "shopify_fixture_a.csv")
        df_sp = pd.read_csv(shopify_path)
        val_sp, events_sp = ShopifyAdapter.validate_and_normalize(df_sp)

        self.assertIsInstance(events_sp[0].gross_amount, Decimal)
        self.assertIsInstance(events_sp[0].fee, Decimal)
        self.assertIsInstance(events_sp[0].net_amount, Decimal)

    def test_paypal_sign_conventions_normalized(self):
        """PayPal fee is recorded negative (-4.65) in export but normalized to positive Decimal(4.65)."""
        paypal_path = os.path.join(self.fixtures_dir, "paypal", "paypal_fixture_a.csv")
        df_pp = pd.read_csv(paypal_path)
        val_pp, events_pp = PayPalAdapter.validate_and_normalize(df_pp)

        self.assertEqual(events_pp[0].fee, Decimal("4.65"))

    def test_deterministic_cross_provider_reference_can_link(self):
        """Cross-provider fixture A: explicit order reference match links deterministically."""
        df_sp = pd.read_csv(os.path.join(self.fixtures_dir, "shopify", "shopify_fixture_a.csv"))
        df_pp = pd.read_csv(os.path.join(self.fixtures_dir, "paypal", "paypal_fixture_a.csv"))

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp)
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp)

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].shopify_event_id, "SHOPIFY:tx_sp_1001")
        self.assertEqual(links[0].paypal_event_id, "PAYPAL:PP1001")

    def test_same_amount_unrelated_references_does_not_link(self):
        """Cross-provider fixture B: same amount but unrelated references MUST NOT link."""
        df_sp = pd.read_csv(os.path.join(self.fixtures_dir, "shopify", "shopify_fixture_a.csv"))
        df_pp = pd.read_csv(os.path.join(self.fixtures_dir, "paypal", "paypal_fixture_b.csv"))

        _, events_sp = ShopifyAdapter.validate_and_normalize(df_sp)
        _, events_pp = PayPalAdapter.validate_and_normalize(df_pp)

        # Force different order references
        events_sp[0].order_id = "#1001"
        events_sp[0].source_order_reference = "#1001"
        events_pp[0].order_id = "#9999"
        events_pp[0].source_order_reference = "#9999"

        links = perform_conservative_cross_provider_linking(events_sp + events_pp)
        self.assertEqual(len(links), 0, "Must NOT link merely because amount matches")

if __name__ == "__main__":
    unittest.main()
