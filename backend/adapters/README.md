# LeakAI Provider Adapters & Cross-Provider Linker Specification

## Overview
The `backend/adapters/` module provides isolated, schema-authoritative ingestion adapters for Shopify Payments and PayPal Activity exports. All provider adapters normalize source files into `CanonicalEvent` models with full source provenance tracking.

---

## 1. Shopify Adapter (`SHOPIFY`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `SHOPIFY_PAYMENTS_TRANSACTIONS`
- **Official Documentation**: [Shopify Payments Payout Details Export Documentation](https://help.shopify.com/en/manual/payments/shopify-payments/payouts/view-details)
- **Required Header Signature**:
  - `Transaction Date`
  - `Type`
  - `Order`
  - `Amount`
  - `Fee`
  - `Net`
- **Optional / Metadata Columns**: `Payout Date`, `Payout Currency`, `Currency`, `Transaction ID`
- **Currency Provenance Policy**:
  - Shopify payout CSVs respect store/payout currency filtering and may omit explicit currency columns.
  - The adapter inspects `Payout Currency` or `Currency` columns first. If absent, it accepts explicit upload/session metadata (`fallback_currency`).
  - If currency cannot be determined from either the file or trusted metadata, **analysis is blocked** to prevent silent USD fabrication.
- **Identity Policy**:
  - If `Transaction ID` is present in the raw CSV, `source_transaction_id` preserves it.
  - If `Transaction ID` is absent (common in payout transaction exports), `source_transaction_id = None`.
  - Internal event identity (`transaction_id`) is generated as a unique internal provenance string: `SHOPIFY:<filename>:ROW_<num>:V1.0.0`. It is **never** treated as a synthetic authoritative provider transaction ID.
- **Supported Event Types**:
  - `charge`, `sale`, `payment` -> Canonical `sale`
  - `refund` -> Canonical `refund`
  - `fee` -> Canonical `fee`
  - `payout` -> Canonical `payout`
  - `dispute`, `chargeback` -> Canonical `chargeback`
- **Unsupported Event Behavior**:
  - Event types such as `adjustment` or unknown strings are blocked with explicit validation errors because their financial settlement semantics cannot be deterministically verified without provider disbursement logs.

---

## 2. PayPal Adapter (`PAYPAL`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `PAYPAL_ACTIVITY`
- **Official Documentation**: [PayPal Activity Download Log Report Specification](https://developer.paypal.com/reports/activity-download/)
- **Required Header Signature**:
  - `Date`, `Time`, `TimeZone`, `Name`, `Type`, `Status`, `Currency`, `Gross`, `Fee`, `Net`, `Transaction ID`
- **Order Reference Priority**:
  1. `Invoice Number` (merchant invoice reference)
  2. `Invoice Number Text`
  3. `Original Invoice ID`
  4. `Custom Number`
  - **Item ID is NEVER used as an order reference.** `Item ID` represents item/product-level metadata and is stored strictly under provenance `raw_data["_item_id_provenance"]`.
- **Supported Event Types**:
  - `Payment Received`, `Express Checkout Payment`, `General Payment`, `Mobile Payment` -> Canonical `sale`
  - `Refund` -> Canonical `refund`
  - `Partner Fee`, `Fee` -> Canonical `fee`
  - `Withdrawal`, `Bank Deposit` -> Canonical `payout`
  - `Dispute`, `Chargeback`, `Reversal` -> Canonical `chargeback`
- **Unsupported Event Behavior**:
  - `Payment Sent` and unverified transaction types are **NOT** assumed to be refunds simply because `Gross` is negative. They are classified as unsupported/unresolved with validation errors.

---

## 3. Generic Canonical CSV Mode (`GENERIC`)

- **Required Header Signature**:
  - `transaction_id`, `date`, `type`, `gross_amount`, `currency`
- **Generic Fallback Policy**:
  - `GENERIC_CANONICAL_CSV` mode is selected **ONLY** when an input file strictly contains all required generic canonical headers.
  - Partial matches, random CSVs, or malformed provider exports are **BLOCKED** (`provider_detected = "UNKNOWN"`).

---

## 4. Conservative V1 Cross-Provider Linker (`backend/linker.py`)

- **Linking Rules**:
  - Links `SHOPIFY` and `PAYPAL` events **ONLY** when both have non-empty matching normalized merchant order/invoice references (`source_order_reference`).
  - Requires exact matching currencies.
  - Requires compatible canonical event types (`sale` to `sale`, `refund` to `refund`).
- **Explicit Exclusions**:
  - Does **NOT** link by `Item ID`.
  - Does **NOT** link by transaction amount alone.
  - Does **NOT** link across different currencies.
  - Does **NOT** merge or delete multiple PayPal events sharing the same order reference (preserves all events for multi-refund auditing).
