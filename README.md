# LeakAI MVP - Deterministic Financial Anomaly Auditor

LeakAI is a local MVP that lets users upload transaction CSV files and receive a 100% deterministic, auditable report of financial anomalies and potential money at risk.

---

## Architecture & Features

- **No AI Non-determinism**: Pure deterministic mathematical rules engine (no random model hallucination or math errors).
- **Flexible Schema Normalization**: Parses dates, vendor names, and currency formats (handling `$`, `,`, and negative parentheses like `(100.00)` to `-100.00`).
- **4 Core Rule Engines**:
  1. `DUPLICATE_PAYMENT`: Identical Vendor + Amount paid within 3 days.
  2. `SPLIT_TRANSACTION`: Multiple transactions to same vendor on same day avoiding approval threshold ($2,500).
  3. `VENDOR_PRICE_SPIKE`: Sudden amount increase >1.5x vendor median.
  4. `ROUND_HIGH_VALUE`: Round thousand payments requiring manual receipt check.
- **Unique Money-at-Risk Deduplication**: Deduplicates multi-flagged transactions so risk totals reflect exact financial exposure.

---

## Quickstart Instructions

### 1. Start Backend (FastAPI)

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

The backend API will run locally at `http://localhost:8000`.

### 2. Start Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## Demo Mode

Click **"Load Demo Dataset"** directly in the UI to run the audit engine against `demo_transactions.csv` and inspect instant summary metrics, anomaly table, and risk breakdowns!
