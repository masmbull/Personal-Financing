# PRD — Finance (Personal Finance Tracker)

Product requirements for the FINANCE app. Companion docs:
[README.md](../README.md) (setup/usage), [AUDIT.md](./AUDIT.md) (audit snapshot).

## 1. Problem & goal

Personal finance in Indonesia is spread across cash, many banks, e-wallets, and
credit cards. Off-the-shelf apps either upload your data to a third party, force
a heavy SPA, or ignore local realities (Rupiah formatting, PayLater, e-money).

**Goal:** a self-hosted, mobile-first web app that records and reconciles
personal finances locally, in integer Rupiah, with no external accounts required.

## 2. Who it's for

- Indonesian individuals tracking daily spending and net worth.
- A single operator's household, or a small self-hosted deployment.
- Users who want their financial data to stay on their own machine.

Non-goals: multi-tenant SaaS, real bank API sync, investment trading, tax filing.

## 3. Success criteria (acceptance)

- New user can register → create account → record a transaction in under 2 min.
- Balances always reconcile: `initial_balance + income − expense − transfer_out + transfer_in`.
- Net worth = assets − liabilities, computed live and snapshotted daily.
- Every financial row is ownership-scoped; no cross-user leak (IDOR-tested).
- Full test suite green (`pytest tests/`), money math never uses float.
- Runs locally with one command, or via Docker Compose.

## 4. Scope — features

### 4.1 Authentication & isolation (v1, done)
- Register / login / logout, session cookie (HttpOnly, SameSite=Lax).
- PBKDF2-HMAC-SHA256 password hashing; server-side session store (token SHA-256).
- CSRF double-submit token on all HTML forms.
- Ownership-scoped queries on every financial entity.

### 4.2 Accounts (v1, done)
- Types: `CASH`, `BANK`, `E_WALLET`, `SERVER_EMONEY`, `CARD_EMONEY`,
  `CREDIT_CARD`, `PAY_LATER`, `SAVINGS`, `LOAN`, `INVESTMENT`, `GOLD`,
  `ASSET`, `LIABILITY`, `OTHER`.
- Create (name, type, icon; balance starts at 0); "Isi Saldo" edits the
  balance on the edit form. Balance is recalculated from transactions.
- Grouped list (Rekening & Kas / Kartu Kredit & Hutang / Investasi & Aset /
  Lainnya) with a single grand total.
- **Credit-card fields** on create/edit: `credit_limit`, `statement_date`,
  `payment_due_day` (1–28), shown only when type = `CREDIT_CARD`.
  `available_credit = credit_limit − max(0, −current_balance)`.

### 4.3 Transactions (v1, done)
- Types: `INCOME`, `EXPENSE`, `TRANSFER`, `REFUND`.
- Transfer never counts as income/expense; both balances move together
  (all-or-nothing, atomicity-tested).
- Credit-card expense grows liability, cash untouched; payment is a transfer
  to the card (liability down, not an expense).
- Over-limit charge and over-payment are rejected deterministically.

### 4.4 Supporting domains (v1, done)
- Categories (hierarchical parent/child, cycle-guarded).
- Debts, Bills (+ idempotent `BillOccurrence` generator), Budgets, Savings goals.
- Assets, Investments (with return tracking).
- Receipt OCR: upload → validate → SHA-256 dedupe → OCR (Tesseract /
  AI-vision / offline) → manual review → exactly-once transaction. OCR never auto-posts.
- Reports: net-worth history, expense-by-category, 6-month trend, CSV export.

### 4.5 REST API (`/api/v1`, done)
- JSON interface, the primary business surface (web/PWA/mobile clients).
- Domains: accounts, transactions, transfers, categories, debts, bills,
  budgets, savings, assets, investments, reports, receipts, credits, dashboard,
  health. All ownership-checked.

### 4.6 Platform (done)
- Mobile-first UI: sidebar (desktop) + bottom nav (mobile), dark/light theme,
  reveal animations, toast/modal, `prefers-reduced-motion`.
- Scheduler via CLI (`python -m app.jobs_cli bills|networth|all`); no background threads.
- Idempotent startup migrations + seeders (banks, e-wallets, payment methods,
  70+ categories, institutions, fuel data).

## 5. Out of scope (v1)

- Email delivery (password reset is admin-processed, no email).
- Bank/e-wallet API aggregation.
- Positive credit balance on a credit card (over-refund/over-payment rejected).
- Automated credit-card interest/fee posting (fields stored, informational only).
- Multi-currency (Rupiah only).

## 6. Non-functional requirements

| Area | Requirement |
|------|-------------|
| Money | Integer Rupiah only; no float in money math |
| Data | SQLite, WAL-ready; ownership-scoped rows |
| Auth | Session cookie + CSRF; password hashed, never logged |
| Deploy | One-command local run; Docker Compose for prod |
| Tests | pytest suite must stay green (currently 614 passed, 1 skipped) |
| Timezone | `Asia/Jakarta` via `APP_TIMEZONE` |
| Migrations | Manual, idempotent (`app/migrations.py`), no Alembic |

## 7. Metrics

- Suite green count (regression gate).
- Time-to-first-transaction for a new user.
- Balance reconciliation holds after every operation (invariant tests).

## 8. Milestones

1. **Baseline** — auth, accounts, transactions, transfers, categories. ✅
2. **Domain expansion** — debts, bills, budgets, savings, assets, investments,
   credit card, receipts/OCR, reports, REST API. ✅
3. **Hardening** — atomicity, IDOR, money-edge, migration, statement audits. ✅
4. **Credit-card fields UI** — limit/statement/due on create/edit + list.
   ✅ (this iteration)
5. **Next** — savings contribution UI polish, Merchant/PaymentMethod as
   first-class entities (see [AUDIT.md](./AUDIT.md) §B).