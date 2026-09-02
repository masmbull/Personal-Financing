# Application Audit — Personal-Financing

Snapshot: 123 tests green, baseline = commit `6592931` (+ cleanup `b7bd4b0`).

## A. Sudah benar (working, tested, secure)

- **Auth**: PBKDF2-HMAC-SHA256, server-side `user_sessions` (token = SHA-256, HttpOnly + SameSite=Lax), CSRF double-submit, login/register/logout, ownership-scoped `CurrentUser`.
- **Data isolation**: `user_id` FK on all financial tables, `_visible_account_query` excludes other users, IDOR protected.
- **REST API v1**: accounts / transactions / transfers / categories / debts / bills / budgets / savings / assets / investments / reports / receipts / dashboard / health, semua ownership-checked.
- **Transactions**: EXPENSE/INCOME/TRANSFER; transfer TIDAK dihitung income/expense; saldo kedua account berubah benar (`recalculate_account_balance`).
- **Categories**: hierarchical parent/child, cycle guard, cross-type parent guard, in-use → 409.
- **Receipt OCR**: upload → validate (MIME/size) → SHA-256 dedupe → OCR (Tesseract + AI-vision Ollama + Offline fallback) → review → exactly-once confirm → transaction. OCR TIDAK auto-post.
- **Reports**: net-worth history, expense by category, monthly trend, dashboard consolidated endpoint.
- **UI**: mobile-first, dark/light theme, bottom-nav + sidebar, page transitions, skeleton, reveal anim, `prefers-reduced-motion`, modal/toast container, Indonesian copy.
- **Deploy**: GitHub Actions test→deploy, Tailscale + SSH, Tesseract fallback offline, AI probe stubbed in tests.
- **Bank/e-wallet master**: 20 bank (umum/digital/syariah) + 6 e-wallet Indonesia + Cash, di-seed idempotent.

## B. Setengah jadi (ada tapi belum lengkap)

- **Dashboard period filter** — endpoint ada, UI tidak expose minggu/bulan-lalu/tahun/custom.
- **CSV export** — belum ada endpoint / tombol.
- **Savings goal contribution/withdrawal** — model ada (`SavingsGoalTransaction`), UI form belum eksplisit.
- **Debt payment history** — model `DebtPayment` ada, list view belum menampilkan timeline.
- **Net worth snapshot** — `NetWorthSnapshot` table ada tapi belum ada scheduler untuk snapshot harian.
- **Optimistic UI / button loading** — toast/modal ada, tapi `aria-busy` + spinner inline belum konsisten.

## C. Broken / masalah latent

- **`datetime.utcnow()` deprecated** (Python 3.12+) — 2791 warnings. Tidak break tapi akan rusak di 3.12+ runtime. Perlu migrasi ke `datetime.now(timezone.utc)`.
- **Test pollution risk** — `test.db` bisa korup kalau pytest di-kill mid-run (SQLite WAL issue). Sudah mitigasi: drop_all per-test. Belum: `PRAGMA journal_mode=WAL` di test engine.
- **Bank "DBS" / "UOB" belum di-seed** — README klaim ada, tapi seed list tidak include.
- **No `pytest.ini` / `pyproject.toml` test config** — `pytest tests/` jalan, tapi `addopts` (warnings=error, junit-xml) belum di-set.

## D. UI tanpa backend

- (tidak ada tombol mati yang ditemukan dalam audit awal)

## E. Backend tanpa UI usable

- **API `POST /api/v1/transfers`** — endpoint ada, UI form mungkin tanpa validasi feedback inline.
- **API `/api/v1/reports/*`** — multi-endpoint, reports page mungkin belum pakai semua.
- **Bill `auto_create`** — flag ada tapi scheduler belum jalan.

## F. Security issue

- **DEBUG default = `True`** di config.py — harus `False` di production. Belum enforced.
- **`SECRET_KEY` default = `"change-me-in-production"`** — boleh tapi tidak fail-fast.
- **CORS default** localhost only — OK, production CORS origins perlu di-set.
- **Cookie secure flag** — di-hardcode `secure=False` di auth; harus ENV-driven untuk production HTTPS.
- **No rate limiting** — login/register/receipt upload belum throttle.
- **CSRF** — double-submit untuk HTML form; API JSON belum (acceptable karena SameSite=Lax).

## G. Data integrity issue

- **Account balance denormalized** — `recalculate_account_balance` di service. Risiko: bug skip recalc → drift. (Likely OK karena single session.)
- **Category `slug` indexed tapi tidak unique** — risk duplikat nama per-parent.

## H. UX issue

- **Dashboard period filter** (PHASE 3) — belum ada UI.
- **Receipt dropzone / drag-drop / camera** — perlu verifikasi.
- **Empty state** — semua sudah ada (test_ui.py covers). Bagus.
- **No skeleton untuk transaction list** — `chart-skeleton` ada di dashboard, list belum.

## I. Missing feature (vs spec)

| Spec | Status |
|------|--------|
| Period filter (minggu/bulan-lalu/tahun/custom) | ❌ UI missing |
| CSV / XLSX export | ❌ |
| Savings contribution/withdraw form | ⚠ partial |
| Debt payment history view | ⚠ partial |
| Bill auto-post scheduler | ❌ |
| Net worth daily snapshot job | ❌ |
| Bank DBS/UOB seed | ❌ |
| Budget progress on dashboard | ⚠ data ada, belum render |
| Optimistic UI / button loading | ❌ |
| Production cookie secure flag | ❌ ENV-driven |
| Rate limiting | ❌ |
| `datetime.now(tz=utc)` migration | ❌ |
| `pytest` strict warnings | ❌ |

## Prioritas eksekusi (dari 25 phase user)

1. **Quick wins (low risk, high value)**:
   - datetime.utcnow migration
   - Seed DBS/UOB (data only)
   - Pyproject pytest config (warnings as errors, junit)
   - Production cookie secure flag + DEBUG fail-fast
2. **Dashboard upgrade** (PHASE 3): period filter, budget usage tile
3. **Export** (PHASE 15): CSV endpoint + button per list page
4. **UI polish** (PHASE 2): button loading states, optimistic feedback, list skeletons
5. **Receipt UX** (PHASE 11): dropzone/drag-drop/camera + confidence indicator
6. **Indonesian master data audit** (PHASE 14)
7. **Rate limiting** (PHASE 17): in-memory limiter
8. **Net worth snapshot** (PHASE 16): daily job
9. **Mobile UX verify** (PHASE 19)
10. **Final QA** (PHASE 25)

## Catatan arsitektural

- ORM: SQLAlchemy 2.0 raw; tidak pakai Alembic (migrasi manual idempotent di `app/migrations.py`).
- Auth: session-based + cookie. Tidak ada JWT.
- Template: Jinja2. Tidak ada SPA.
- Frontend: vanilla JS (no framework). Chart: pure SVG.
- OCR: pluggable engine via `ReceiptScannerService` abstraction.
- AI: env-driven (Ollama OpenAI-compatible).
- Decimal money: **integer Rupiah** (no float) — excellent for correctness.