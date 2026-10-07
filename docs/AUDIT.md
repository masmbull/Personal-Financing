# Application Audit - Personal-Financing

Snapshot: **614 passed, 1 skipped** (serial run, 17:33). Head `3e7bb7a` -> recurring/insights/CSV-import/tags + credit-card account fields (limit / statement / due) wired end-to-end + `.gitattributes` line-ending normalization.

## A. Sudah benar (working, tested, secure)

- **Auth**: PBKDF2-HMAC-SHA256, server-side `user_sessions` (token = SHA-256, HttpOnly + SameSite=Lax), CSRF double-submit, login/register/logout, ownership-scoped `CurrentUser`.
- **Data isolation**: `user_id` FK on all financial tables, `_visible_account_query` excludes other users, IDOR protected.
- **REST API v1**: accounts / transactions / transfers / categories / debts / bills(+occurrences) / budgets / savings / assets / investments / reports / receipts / dashboard / health - semua ownership-checked.
- **Transactions**: EXPENSE/INCOME/TRANSFER; transfer TIDAK dihitung income/expense; saldo kedua account berubah benar (`recalculate_account_balance`).
- **Credit card accounting**: EXPENSE on credit card -> liability grows, cash untouched; TRANSFER cash->credit card = pay liability tanpa income/expense (tested).
- **Categories**: hierarchical parent/child, cycle guard, cross-type parent guard, in-use -> 409.
- **Receipt OCR**: upload -> validate (MIME/size) -> SHA-256 dedupe -> OCR (Tesseract + AI-vision Ollama + Offline fallback) -> review -> exactly-once confirm -> transaction. OCR TIDAK auto-post.
- **Reports**: net-worth history, expense by category, monthly trend, dashboard consolidated endpoint.
- **Net worth snapshot**: `record_daily_snapshot` supports historical dates + timezone-aware (`Asia/Jakarta` via `APP_TIMEZONE`); `run_daily_net_worth_snapshots` covers ALL active users; upsert on (user, date).
- **Bill auto-post scheduler**: `BillOccurrence` model (unique `bill_id + due_date`), `generate_bill_occurrences` (idempotent), API: `POST /bills/occurrences/run`, `GET /bills/occurrences/due`, `POST /bills/occurrences/{id}/pay`.
- **Scheduler architecture**: `app/services/jobs.py` (pure callable functions), `app/jobs_cli.py` (`python -m app.jobs_cli bills|networth|all`), documented production execution (cron / Task Scheduler).
- **UI**: mobile-first, dark/light theme, bottom-nav + sidebar, page transitions, skeleton, reveal anim, `prefers-reduced-motion`, modal/toast container, Indonesian copy.
- **Bank/e-wallet master**: 20 bank (umum/digital/syariah) + 6 e-wallet Indonesia + Cash, di-seed idempotent.

## B. Setengah jadi (ada tapi belum lengkap)

- **Savings goal contribution/withdrawal** - DONE: model + service `deposit`/`withdraw` + UI form, kini dengan selector akun sumber (`related_account_id`) + `required` amount.
- **Merchant as first-class entity** - DONE: `Merchant` + `MerchantAlias` models, `app/services/merchants.py`, `app/api/merchants.py`, + management UI `/merchants` (`app/routes/masters.py`).
- **PaymentMethod as first-class entity** - DONE: `PaymentMethod` model, service + `app/api/payment_methods.py`, + management UI `/payment-methods` (`app/routes/masters.py`). Txn HTML form now stores `merchant_id` / `payment_method_id`.
- **Optimistic UI / button loading** - DONE: guard submit global set `aria-busy` + `btn-loading` (`app.js` `initFormGuard`).

## C. Broken / masalah latent

- **Test pollution risk** - `test.db` bisa korup kalau pytest di-kill mid-run (SQLite WAL issue). Mitigasi: drop_all per-test (test-only, low impact).
- **Production DB drop_all-on-kill** - DONE: `backup_database` (stdlib `sqlite3` online-backup API, WAL-safe + consistent) snapshots the SQLite file to `data/backups/<stem>_<ts>.db.bak` at the start of every **production** lifespan, before `create_all`/any migration. Keeps newest 7 per file (`rotate_backups`); dev/test skip it. `.gitignore` already covers `data/*` + `*.db`.
- **`category.slug`** - DONE: unique index `uq_categories_type_slug` on `(type, slug)` in model + `run_category_slug_unique_migration` (skips safely on pre-existing duplicates).

## D. UI tanpa backend

- (tidak ada tombol mati yang ditemukan)

## E. Backend tanpa UI usable

- **API `/api/v1/reports/*`** - DONE: 7 endpoints (cash-flow/expenses/income-vs-expense/net-worth[/history|snapshot]/categories) covered by `test_api` + `test_feature_coverage`. HTML `/reports` intentionally uses its own `get_report_data` aggregate (expense-trend view); net-worth dashboard lives on `/`.
- **Bill occurrences** - HTML `/bills` menampilkan section "Jatuh Tempo" (generate idempotent + tombol Bayar via `POST /bills/occurrences/{id}/pay`).

## F. Security issue

- **DEBUG default = `True`** - production guard enforced via `_validate_production_config` (SECRET_KEY override required, DEBUG forced off).
- **CORS default** localhost only - OK; production CORS origins via env.
- **CSRF** - double-submit untuk HTML form; API JSON uses SameSite=Lax cookies.

## G. Data integrity issue

- **Account balance denormalized** - `recalculate_account_balance` di service. Low risk: single session.
- **Bill occurrence idempotency** - enforced di schema via `UNIQUE(bill_id, due_date)` + check sebelum INSERT.

## H. UX issue

- **Receipt dropzone / drag-drop / camera** - DONE: drag-drop di `initReceiptUpload` (dragover/drop → `input.files`), tombol kamera `capture="environment"`, kompresi async (`compressImage`).
- **Optimistic UI / button loading** - konsisten: `aria-busy` + `btn-loading` via `initFormGuard`.

## I. Backend completion status

| Feature | Model | Service | API | Tests | Status |
|---------|-------|---------|-----|-------|--------|
| Auth | done | done | done | test_auth | COMPLETE |
| Accounts | done | done | CRUD | test_api/finance | COMPLETE |
| Transactions | done | done | CRUD | test_api/finance | COMPLETE |
| Transfers | done | via finance | POST | test_api/finance | COMPLETE |
| Categories | done hierarchy | done | CRUD+tree | test_categories | COMPLETE |
| Budgets | done | done | CRUD | test_finance | COMPLETE |
| Savings Goals | done | done | CRUD+deposit | test_finance | COMPLETE |
| Debts + Payments | done | done | CRUD+pay | test_api | COMPLETE |
| Bills | done | done | CRUD+pay | test_finance | COMPLETE |
| Bill Occurrences | done Unique | done generate/due/pay | 3 endpoints | 13 tests | COMPLETE |
| Receipts + OCR | done | done | upload/confirm | test_api/ui | COMPLETE |
| AI (Ollama) | - | done | - | test_receipt_ai | COMPLETE |
| Reports | - | done | 7 endpoints | test_api | COMPLETE |
| Reports HTML | - | get_report_data | GET /reports | test_finance | COMPLETE |
| CSV Export | - | - | 2 routes | test_export | COMPLETE |
| XLSX Export | - | - | 2 routes | test_export | COMPLETE |
| Budget Alerts | - | alerts_from_rows | API+UI banner/badge | test_recurring_features | COMPLETE |
| Dashboard | - | done | GET | test_api | COMPLETE |
| Net Worth | done snapshot | compute+snapshot | GET+POST | 11 tests | COMPLETE |
| Net Worth Daily Job | - | done all-users | startup+CLI | test_networth_job | COMPLETE |
| Assets | done | done | CRUD | test_finance | COMPLETE |
| Investments | done | done | CRUD | test_finance | COMPLETE |
| Rate Limiting | - | done middleware | - | test_export | COMPLETE |

## Accounting invariant tests (test_accounting.py)

Verified on service layer (real business logic):
1. Income -> balance increases, income report increases
2. Expense -> balance decreases, expense report increases
3. Transfer -> source decreases, dest increases; income/expense unchanged
4. Credit card EXPENSE -> liability grows, cash unchanged
5. Credit card PAYMENT via TRANSFER -> cash decreases, liability decreases, income/expense unchanged
6. Refund -> income category, balance increases
7. Debt payment -> liability decreases, cash decreases, counts as expense
8. Savings deposit -> goal amount increases, NOT counted as expense

## Scheduler architecture

```
python -m app.jobs_cli bills           # generate bill occurrences (idempotent)
python -m app.jobs_cli networth        # daily net-worth snapshots (all users)
python -m app.jobs_cli all             # run every job once
python -m app.jobs_cli all --date 2026-09-01  # historical date
```

Production: add command(s) to Windows Task Scheduler or cron (once per day).
Jobs are pure functions - no APScheduler dependency. Occurrences are UNPAID
DUE work; the scheduler NEVER silently moves money. Paying an occurrence uses
the normal pay_bill path (real expense transaction) and marks it PAID.

## Remaining backend gaps (actual)

All previously-listed gaps are now shipped:

1. **Merchant as first-class entity** - DONE (`Merchant`/`MerchantAlias` + resolve)
2. **PaymentMethod as first-class entity** - DONE (QRIS / e-money / transfer distinct)
3. **Credit card statement-date / due-date / credit-limit / available-credit** - DONE (fields wired end-to-end in UI + list)
4. **BBM/fuel price reference catalog** - DONE (`app/api/fuel.py` + reference data)
5. **Master-data provenance fields** (source, source_url, verified_at, region) - DONE on Merchant / PaymentMethod / institutions

## UI Status

Backend + UI wiring mode COMPLETE. All section A/B/E/H gaps closed and
verified. Leftover items are latent risks (section C/G), not missing features.

## NEXT STEP

No remaining open gaps in sections A/B/C/E/H. All items closed. Remaining
section G items are informational (below). App is ship-ready.

Verified this session: `/api/v1/reports/*` (7 ep, all tested) + reports HTML
handler live; receipt dropzone/drag-drop/camera + async compression live;
category slug uniqueness enforced (model + idempotent migration + tests);
Production SQLite backup guard live (WAL-safe snapshot + rotation + tests).
Budget alerts surfaced in UI (dashboard + /budgets banner, sidebar badge, reusing
`budgets_service.alerts_from_rows`). Excel (.xlsx) export for transactions +
reports via `openpyxl` (shared row builders, in-memory StreamingResponse).

## Catatan arsitektural

- ORM: SQLAlchemy 2.0 raw; tidak pakai Alembic (migrasi manual idempotent di `app/migrations.py`).
- Auth: session-based + cookie. Tidak ada JWT.
- Template: Jinja2. Tidak ada SPA.
- Frontend: vanilla JS (no framework). Chart: pure SVG.
- OCR: pluggable engine via `ReceiptScannerService` abstraction.
- AI: env-driven (Ollama OpenAI-compatible).
- Decimal money: **integer Rupiah** (no float).
- Timezone: `Asia/Jakarta` default (configurable via `APP_TIMEZONE`).
- Scheduler: pure service functions, callable from CLI / cron. No background thread.

| Scheduler Arch | - | done jobs.py | CLI+cron | test_bill_scheduler | COMPLETE |
| Timezone | - | done time_utils | APP_TIMEZONE | test_networth_job | COMPLETE |
| Accounting Invariants | - | - | - | 8 tests | COMPLETE |
| Account Edit IDOR | - | - | - | 2 tests | COMPLETE |
| E2E Integration | - | - | - | 1 test | COMPLETE |

