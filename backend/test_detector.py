import unittest
import os
import sys

# Ensure backend path is importable
sys.path.append(os.path.dirname(__file__))

from normalizer import normalize_csv
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
        self.df = normalize_csv(self.csv_bytes)
        self.summary, self.txs = analyze_transactions(self.df)
        self.tx_map = {t.transaction_id: t for t in self.txs}

    def test_overall_financial_totals(self):
        self.assertEqual(self.summary.raw_record_count, 15)
        self.assertEqual(self.summary.economic_event_count, 14)
        self.assertEqual(self.summary.total_gross_revenue, 2795.00)
        self.assertEqual(self.summary.total_fees_paid, 107.38)
        self.assertEqual(self.summary.confirmed_loss_amount, 650.00)
        self.assertEqual(self.summary.potential_review_amount, 1613.58)
        self.assertEqual(len(self.summary.financials_by_currency), 1)
        self.assertEqual(self.summary.financials_by_currency[0].currency, "USD")

    def test_regression_O_decimal_precision_no_false_net_math_error(self):
        """
        TEST O — Decimal precision:
        sale gross = 0.10, fee = 0.03, net = 0.07
        Expected: no false NET_AMOUNT_INCONSISTENCY.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_dec1,ord_dec1,2026-01-01,sale,0.10,0.03,0.07,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertFalse(txs[0].has_anomaly)
        self.assertEqual(summary.total_gross_revenue, 0.10)
        self.assertEqual(summary.total_fees_paid, 0.03)

    def test_regression_P_repeated_decimal_addition(self):
        """
        TEST P — repeated decimal addition:
        three amounts of 0.10
        Expected exact total: 0.30 (no 0.30000000000000004 float artifact).
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_a,ord_a,2026-01-01,sale,0.10,0.01,0.09,USD\n"
            "tx_b,ord_b,2026-01-01,sale,0.10,0.01,0.09,USD\n"
            "tx_c,ord_c,2026-01-01,sale,0.10,0.01,0.09,USD\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.total_gross_revenue, 0.30)
        self.assertEqual(summary.total_fees_paid, 0.03)

    def test_regression_Q_multi_currency_isolation(self):
        """
        TEST Q — multi-currency isolation:
        USD: sale = 100, refund = 120 (confirmed loss = 20 USD)
        EUR: sale = 100, refund = 50 (confirmed loss = 0 EUR)
        Expected: USD confirmed loss = 20 USD, EUR confirmed loss = 0 EUR.
        Never produce combined confirmed loss without currency context.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_u1,ord_u,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_u2,ord_u,2026-01-02,refund,-120.00,0.00,-120.00,USD\n"
            "tx_e1,ord_e,2026-01-01,sale,100.00,3.00,97.00,EUR\n"
            "tx_e2,ord_e,2026-01-02,refund,-50.00,0.00,-50.00,EUR\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(len(summary.financials_by_currency), 2)
        usd_fin = next(f for f in summary.financials_by_currency if f.currency == "USD")
        eur_fin = next(f for f in summary.financials_by_currency if f.currency == "EUR")

        self.assertEqual(usd_fin.confirmed_loss_amount, 20.00)
        self.assertEqual(eur_fin.confirmed_loss_amount, 0.00)

    def test_regression_R_same_order_id_across_currencies_no_cross_matching(self):
        """
        TEST R — same order ID across currencies:
        ord_1 sale 100 USD
        ord_1 refund 120 EUR
        Expected: they do NOT reconcile against each other. No confirmed loss caused by cross-currency matching.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_u1,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_e1,ord_1,2026-01-02,refund,-120.00,0.00,-120.00,EUR\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertEqual(summary.confirmed_loss_amount, 0.0)
        self.assertTrue(any(f.rule_id == RULE_UNMATCHED_REFUND for f in txs[1].flags))

    def test_regression_S_conflicting_transaction_currency(self):
        """
        TEST S — conflicting transaction currency:
        same transaction_id: one row USD, one row EUR
        Expected: CONFLICTING_TRANSACTION_ID, excluded from economic reconciliation.
        """
        csv_data = (
            "transaction_id,order_id,date,type,gross_amount,fee,net_amount,currency\n"
            "tx_x,ord_1,2026-01-01,sale,100.00,3.00,97.00,USD\n"
            "tx_x,ord_1,2026-01-01,sale,100.00,3.00,97.00,EUR\n"
        ).encode('utf-8')
        df = normalize_csv(csv_data)
        summary, txs = analyze_transactions(df)

        self.assertTrue(any(f.rule_id == RULE_CONFLICTING_TX for f in txs[0].flags))
        self.assertEqual(summary.economic_event_count, 0)
        self.assertEqual(summary.confirmed_loss_amount, 0.0)

    def test_economic_loss_ledger_deduplication(self):
        ledger = self.summary.economic_loss_ledger
        self.assertEqual(len(ledger), 2)
        total_ledger_loss = sum(item.proven_loss_amount for item in ledger)
        self.assertEqual(total_ledger_loss, self.summary.confirmed_loss_amount)
        self.assertEqual(total_ledger_loss, 650.00)

if __name__ == "__main__":
    unittest.main()
