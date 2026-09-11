# LeakAI Provider Adapters Documentation

## Overview
The `backend/adapters/` module provides isolated, schema-authoritative ingestion adapters for e-commerce and payment gateway export files. Provider adapters translate raw export files into LeakAI `CanonicalEvent` structures while preserving full source provenance.

---

## 1. Shopify Adapter (`SHOPIFY`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `SHOPIFY_PAYMENTS_TRANSACTIONS`
- **Official Schema Standard**: [Shopify Payments Transactions Export Documentation](https://help.shopify.com/en/manual/shopify-payments/reporting/payouts#export-payouts-or-transactions)
- **Required Columns**:
  - `Transaction Date`
  - `Type`
  - `Order`
  - `Amount`
  - `Fee`
  - `Net`
  - `Payout Date`
  - `Payout Currency`
- **Optional Columns**: `Transaction ID`, `Currency`
- **Sign Conventions**:
  - `Amount`: Positive for sales/charges, negative for refunds/chargebacks.
  - `Fee`: Positive expense deduction.
  - `Net`: Gross amount minus fee.
- **Supported Event Types**:
  - `charge`, `sale`, `payment` -> Canonical `sale`
  - `refund` -> Canonical `refund`
  - `fee` -> Canonical `fee`
  - `payout` -> Canonical `payout`
  - `dispute`, `chargeback` -> Canonical `chargeback`
- **Unsupported Cases**:
  - Unstructured generic CSV without Shopify Payments headers.
  - Ambiguous headers overlapping with other providers.

---

## 2. PayPal Adapter (`PAYPAL`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `PAYPAL_ACTIVITY`
- **Official Schema Standard**: [PayPal Activity Download Log Specification](https://www.paypal.com/us/smarthelp/article/how-do-i-download-a-history-log-of-my-paypal-transactions-ts1417)
- **Required Columns**:
  - `Date`
  - `Time`
  - `TimeZone`
  - `Name`
  - `Type`
  - `Status`
  - `Currency`
  - `Gross`
  - `Fee`
  - `Net`
  - `Transaction ID`
- **Optional Columns**: `Item ID`, `Invoice Number`, `Custom Number`, `Reference Txn ID`
- **Sign Conventions**:
  - `Gross`: Positive for payments received, negative for refunds and fees sent.
  - `Fee`: Recorded as negative e.g. `-0.30` (normalized to positive fee expense `0.30` in canonical event).
  - `Net`: Gross minus fee.
- **Supported Event Types**:
  - `Payment Received`, `Express Checkout Payment`, `General Payment` -> Canonical `sale`
  - `Refund`, `Payment Sent` (negative gross) -> Canonical `refund`
  - `Partner Fee`, `Fee` -> Canonical `fee`
  - `Withdrawal`, `Bank Deposit` -> Canonical `payout`
  - `Dispute`, `Chargeback`, `Reversal` -> Canonical `chargeback`
- **Unsupported Cases**:
  - PayPal Monthly Financial Summary PDF transcripts (only CSV Activity exports supported).
  - Custom custom-column reports lacking standard transaction ID and type headers.

---

## 3. Generic Canonical CSV Mode (`GENERIC`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `GENERIC_CANONICAL_CSV`
- **Description**: Fallback mode for internal benchmark CSV files (e.g. `demo_transactions.csv`). Used when no provider-specific schema signature matches.
