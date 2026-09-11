# LeakAI Provider Adapters & Cross-Provider Linker Specification

## Overview
The `backend/adapters/` module provides isolated, schema-authoritative ingestion adapters for Shopify Payments and PayPal Activity exports. All provider adapters normalize source files into `CanonicalEvent` models with full source provenance tracking.

---

## 1. Shopify Adapter (`SHOPIFY`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `SHOPIFY_PAYMENTS_TRANSACTIONS`
- **Official Documentation**: [Shopify Payments Payout Details Export Documentation](https://help.shopify.com/en/manual/payments/shopify-payments/payouts/view-details)
- **Required Header Signature**:
  - `Transaction Date`, `Type`, `Order`, `Amount`, `Fee`, `Net`
- **Optional / Metadata Columns**: `Payout Date`, `Payout Currency`, `Currency`, `Transaction ID`
- **Internal File Identity Policy**:
  - `source_filename` must be non-empty for adapter processing.
  - Internal event identity (`transaction_id`) is generated as: `SHOPIFY:<source_filename>:ROW_<num>:V1.0.0`.
  - Prevents anonymous file processing from producing duplicate internal row identities.
- **Currency Selection Priority**:
  1. Valid `Payout Currency` column in CSV
  2. Valid `Currency` column in CSV
  3. Explicit trusted upload/session metadata (`fallback_currency`)
  - If currency cannot be determined from file or metadata, **analysis is blocked**.

---

## 2. PayPal Adapter (`PAYPAL`)

- **Adapter Version**: `1.0.0`
- **Supported Export Type**: `PAYPAL_ACTIVITY`
- **Official Documentation**: [PayPal Activity Download Log Report Specification](https://developer.paypal.com/reports/activity-download/)
- **Required Header Signature**:
  - `Date`, `Time`, `TimeZone`, `Name`, `Type`, `Status`, `Currency`, `Gross`, `Fee`, `Net`, `Transaction ID`
- **Order Reference Priority**:
  1. `Invoice Number`
  2. `Invoice Number Text`
  3. `Original Invoice ID`
  4. `Custom Number`
  - **`Item ID` is NEVER used as an order reference.**

---

## 3. Generic Canonical CSV Mode (`GENERIC`)

- **Required Header Signature**:
  - `transaction_id`, `date`, `type`, `gross_amount`, `currency`
- **Strict Generic Normalization Pipeline Integration**:
  - `AdapterRegistry.process()` converts the input DataFrame into a BytesIO CSV buffer and executes the strict `validate_and_normalize_csv()` pipeline.
  - Reuses all strict Decimal parsing, validation error reporting, missing column tracking, and `has_source_fee` / `has_source_net` provenance flags.

---

## 4. Conservative V1 Cross-Provider Linker (`backend/linker.py`)

- **Link Semantics**:
  - `matched_amount`: **Decimal** (no floating point arithmetic in linking/proof structures).
  - `link_method`: `"EXACT_MERCHANT_REFERENCE"`
  - `link_status`: `"REFERENCE_MATCH"`
  - `evidence_level`: `"DETERMINISTIC_REFERENCE"`
  - `confidence`: `0.85` (models deterministic merchant reference relationship, **never** 1.0 guaranteed economic identity).
