# Finance

Aplikasi web pencatatan keuangan pribadi yang ringan, cepat, dan mobile-first. Dibangun dengan Python/FastAPI, SQLite, dan vanilla JS — tanpa framework frontend berat.

## Daftar Isi

- [Fitur](#fitur)
- [Arsitektur](#arsitektur)
- [Tech Stack](#tech-stack)
- [Persiapan](#persiapan)
- [Menjalankan Secara Lokal](#menjalankan-secara-lokal)
- [Menjalankan via Docker](#menjalankan-via-docker)
- [Variabel Lingkungan](#variabel-lingkungan)
- [Database & Seed Data](#database--seed-data)
- [Onboarding Pengguna Baru](#onboarding-pengguna-baru)
- [Navigasi](#navigasi)
- [Testing](#testing)
- [Deployment](#deployment)
- [Struktur Proyek](#struktur-proyek)
- [Aturan Akuntansi](#aturan-akuntansi)
- [Keamanan](#keamanan)
- [Status Pengembangan](#status-pengembangan)

## Fitur

### Autentikasi & Isolasi Data
- Register / login / logout dengan session berbasis cookie
- PBKDF2-HMAC-SHA256 untuk hashing password
- Session token di-hash SHA-256 di database; cookie HttpOnly + SameSite=Lax
- CSRF double-submit token pada semua form HTML
- Setiap user hanya melihat data miliknya sendiri (ownership-scoped queries, IDOR-protected)

### Dashboard
- Saldo tersedia (akumulasi semua akun)
- Pemasukan & pengeluaran periode aktif (harian/mingguan/bulanan)
- Cashflow (income − expense)
- Tingkat menabung (savings rate)
- Total aset, kewajiban (hutang), dan net worth
- Tren pemasukan vs pengeluaran 6 bulan terakhir
- Pengeluaran per kategori (top 5)
- Tabungan aktif dengan progress bar
- Transaksi terakhir

### Transaksi
- Tipe: `INCOME`, `EXPENSE`, `TRANSFER`
- CRUD lengkap dengan filter (tipe, kategori, akun, periode) dan pencarian
- Transfer antar akun — tidak dihitung sebagai income atau expense
- Kategori ber-hirarki (parent/child) dengan ikon emoji
- Lampiran struk per transaksi

### Akun Keuangan
- Tipe: Cash, Bank, E-Wallet, Credit Card
- Saldo dihitung: `initial_balance + income − expense − transfer_out + transfer_in`
- 20 bank Indonesia + 6 e-wallet + Cash di-seed otomatis
- Bisa edit nama, ikon, dan saldo awal (recalculasi)

### Hutang (Debt Tracker)
- Catat hutang dengan nama kreditor, jumlah, dan tanggal jatuh tempo
- Pembuatan transaksi pembayaran hutang terpisah dari expense biasa
- Status lunas/otomatis berubah saat hutang dilunasi

### Tagihan (Bills)
- Jadwal tagihan berulanan (harian/mingguan/bulanan/tahunan)
- Generator `BillOccurrence` idempoten — tidak duplikat saat re-run
- Scheduler CLI untuk generate occurrences harian
- Pembayaran via path biasa (expense transaksi) — tidak ada auto-debit tersembunyi

### Budget
- Budget per kategori dengan periode bulanan
- Tracking pengeluaran vs budget
- Indikator over-budget

### Tabungan (Savings Goals)
- Target tabungan dengan nama, ikon, dan nominal target
- Deposit dan withdraw tercatat sebagai transaksi
- Progress bar persentase tercapai

### Aset & Investasi
- Aset: nama, nilai beli, nilai sekarang, lokasi, foto
- Investasi: nama, tipe, jumlah, harga beli, harga sekarang, return calculation

### Kartu Kredit
- Akun tipe `CREDIT_CARD` — expense di kartu kredit menambah liabilitas, bukan mengurangi cash
- Pembayaran kartu kredit via transfer cash → credit card (liabilitas berkurang, bukan expense)
- Statement calculation: charges − refunds (floored at 0)
- Minimum payment calculation (integer math)

### Struk & OCR
- Upload struk (gambar/PDF) → validasi MIME & ukuran
- SHA-256 dedupe — struk yang sama tidak diproses dua kali
- OCR engine: Tesseract (lokal) atau AI-vision (Ollama, default moondream:1.8b-v2-q4_K_S / OpenAI-compatible)
- Review & konfirmasi manual sebelum jadi transaksi — OCR TIDAK auto-post
- Deteksi duplikat berdasarkan hash dan metadata

### Laporan
- Laporan harian, mingguan, bulanan
- Pengeluaran per kategori
- Tren 6 bulan
- Riwayat net worth harian (snapshot)
- Export CSV

### REST API (`/api/v1`)
- Semua endpoint di-prefix `/api/v1/`
- Interface bisnis utama — bisa dipakai web, PWA, atau mobile
- Endpoint: accounts, transactions, transfers, categories, debts, bills (+occurrences), budgets, savings, assets, investments, reports, receipts, dashboard, health
- Semua ownership-checked

### UI/UX
- Mobile-first, responsive
- Dark/light theme dengan toggle
- Bottom navigation (mobile) + sidebar (desktop)
- Page transitions & reveal animations
- Skeleton loading states
- Toast notifications & modal dialogs
- Bahasa Indonesia
- `prefers-reduced-motion` support

## Arsitektur

```
┌─────────────────────────────────────────────────────┐
│  Browser (HTML/CSS/JS, Jinja2 templates)            │
│         │                                           │
│         ▼                                           │
│  FastAPI / Starlette                                │
│   ├── app/auth      → session, CSRF, login/register │
│   ├── app/api       → REST API v1 (JSON)            │
│   ├── app/routes    → legacy UI web (Jinja)         │
│   ├── app/services  → business logic + seeders      │
│   ├── app/models    → SQLAlchemy ORM models         │
│   └── app/schemas   → Pydantic validation           │
│         │                                           │
│         ▼                                           │
│  SQLite (file-based, WAL-ready)                     │
└─────────────────────────────────────────────────────┘
```

- **Tidak ada SPA** — server-rendered Jinja2 templates
- **Tidak ada JWT** — session-based auth dengan cookie
- **Tidak ada background thread** — scheduler via CLI/cron
- **Tidak ada Alembic** — migrasi manual idempoten di `app/migrations.py`
- **Tidak ada float untuk uang** — semua jumlah dalam integer Rupiah

## Tech Stack

| Komponen | Teknologi |
|----------|-----------|
| Backend | Python 3.11+, FastAPI, Starlette, SQLAlchemy 2.0 |
| Database | SQLite (built-in) |
| Frontend | HTML5, CSS3 (mobile-first), vanilla JavaScript |
| Templates | Jinja2 |
| Validasi | Pydantic v2 |
| OCR | Tesseract + optional AI-vision (Ollama) |
| Deployment | Docker, Docker Compose |
| Testing | pytest, httpx |

## Persiapan

### Prasyarat

- Python 3.11 atau lebih baru
- pip
- (Opsional) Tesseract OCR — untuk fitur scan struk
- (Opsional) Docker & Docker Compose — untuk deployment

### Clone & Install

```bash
git clone <repo-url> finance
cd finance
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

## Menjalankan Secara Lokal

### 1. Environment Variables

```bash
copy .env.example .env    # Windows
# cp .env.example .env   # Linux/Mac
```

Edit `.env` jika perlu. Default sudah cocok untuk development.

### 2. Jalankan Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Buka http://localhost:8080

### 3. Database

Database SQLite otomatis dibuat di `./data/finance.db` saat pertama kali run. Tidak perlu setup tambahan.

## Menjalankan via Docker

```bash
docker compose up -d
```

Buka http://localhost:8080

Stop:
```bash
docker compose down
```

Database disimpan di `./data/finance.db` (persistent via bind mount `./data:/app/data`).

## Variabel Lingkungan

| Variable | Default | Deskripsi |
|----------|---------|-----------|
| `DATABASE_URL` | `sqlite:///./data/finance.db` | Database connection string |
| `APP_NAME` | `Finance` | Nama aplikasi |
| `APP_HOST` | `0.0.0.0` | Host untuk server |
| `APP_PORT` | `8080` | Port server |
| `APP_ENV` | `development` | `development` / `production` / `test` |
| `DEBUG` | `true` | Debug mode |
| `SECRET_KEY` | `change-me-in-production` | Secret key untuk session & CSRF |
| `APP_TIMEZONE` | `Asia/Jakarta` | Timezone aplikasi |
| `AUTH_BOOTSTRAP_USERNAME` | (kosong) | Username admin otomatis saat startup pertama |
| `AUTH_BOOTSTRAP_PASSWORD` | (kosong) | Password admin otomatis saat startup pertama |
| `TESSERACT_CMD` | `tesseract` | Path ke executable Tesseract |
| `RECEIPT_AI_ENABLED` | `true` | Enable AI-vision OCR |
| `RECEIPT_AI_PROVIDER` | `openai` | Provider AI (`openai` / `gemini` / `ollama` / `none`) |
| `OPENAI_API_KEY` | (kosong) | API key OpenAI vision — wajib jika provider=openai |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model vision OpenAI |
| `OPENAI_TIMEOUT_SECONDS` | `60` | Timeout inference OpenAI (detik) |
| `GEMINI_API_KEY` | (kosong) | API key Gemini vision — wajib jika provider=gemini |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model vision Gemini (2.0-flash sudah dimatikan Google) |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` | Endpoint kompatibel OpenAI untuk Gemini |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Timeout inference Gemini (detik) |
| `RECEIPT_AI_MAX_IMAGE_WIDTH` | `1280` | Resolusi maks gambar dikirim ke AI |
| `RECEIPT_AI_JPEG_QUALITY` | `80` | JPEG quality gambar inference temp |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | URL Ollama (localhost only) |
| `OLLAMA_VISION_MODEL` | `moondream:1.8b-v2-q4_K_S` | Model vision (env-configurable) |
| `OLLAMA_TIMEOUT_SECONDS` | `60` | Timeout inference (detik) |
| `OLLAMA_NUM_CTX` | `2048` | Context window (bounded for low RAM) |
| `OLLAMA_MAX_IMAGE_BYTES` | `2097152` | Max base64 gambar -> Tesseract |

Semua variabel opsional sudah punya default aman — cukup copy `.env.example` ke `.env` untuk development.

## Database & Seed Data

Seed otomatis berjalan saat startup (idempoten — tidak duplikat saat re-run):

- **20 bank Indonesia** (BCA, Mandiri, BNI, BRI, dll) + **6 e-wallet** (GoPay, OVO, DANA, LinkAja, ShopeePay, Dana) + Cash
- **11 payment methods** (Cash, Bank Transfer, QRIS, Debit Card, Credit Card, E-Wallet, dll)
- **70+ kategori ber-hirarki** untuk pengeluaran & pemasukan (Makanan, Transportasi, Belanja, Tagihan, Kesehatan, Pendidikan, dll)
- **Financial institutions** dengan tipe (Umum, Digital, Syariah)
- **Fuel brands & products** (reference data)

## Onboarding Pengguna Baru

Setelah register, pengguna **wajib** membuat minimal satu akun keuangan sebelum bisa mengakses dashboard:

1. **Register** → diarahkan ke halaman `/setup`
2. **Setup** → isi nama akun (mis: "BCA", "Cash"), tipe (Cash/Bank/E-Wallet/Credit Card), dan saldo awal
3. **Skip** → bisa skip, sistem otomatis buat akun "Cash" dengan saldo 0
4. **Dashboard** → baru bisa diakses setelah punya minimal 1 akun

Jika user mencoba mengakses `/` tanpa punya akun, akan di-redirect ke `/setup`.

## Navigasi

### Sidebar (Desktop)
- 🏠 Beranda
- 📋 Transaksi
- 📊 Laporan
- ─── (divider)
- 💳 Akun
- 🏦 Hutang
- 📄 Tagihan
- 🎯 Budget
- 🐷 Tabungan
- 🏠 Aset
- 📈 Investasi
- 🏷️ Kategori
- 🧾 Struk

### Bottom Navigation (Mobile)
- 🏠 Beranda
- 📋 Transaksi
- ＋ Scan (upload struk)
- 📊 Laporan
- ⋯ Lainnya (akun & pengelolaan)

## Testing

```bash
# Install test dependencies
pip install pytest httpx

# Jalankan semua test
pytest tests/ -v

# Jalankan test spesifik
pytest tests/test_auth.py -v
pytest tests/test_finance.py -v
pytest tests/test_api.py -v

# Jalankan dengan parallel (opsional)
pip install pytest-xdist
pytest tests/ -n auto
```

**275 tests** mencakup:
- Auth & session (register, login, logout, CSRF, IDOR)
- Accounting invariants (income, expense, transfer, credit card, debt, savings)
- Statement audit (credit card statement, refund netting, payment status)
- Atomicity (transfer all-or-nothing, balance invariant)
- Money edges (integer math, MAX boundary, zero-amount rejection)
- Migrations (schema idempotency)
- API endpoints (CRUD, ownership, validation)
- UI (template rendering, CSS classes, navigation)
- Receipt AI (OCR pipeline, dedupe)
- Bill scheduler (occurrence generation, idempotency)
- Net worth job (snapshot, timezone, all-users coverage)

## Deployment

### Docker (Recommended)

```bash
# Clone
git clone <repo-url> finance
cd finance

# Set environment
cp .env.example .env
# Edit .env: set SECRET_KEY, APP_ENV=production

# Run
docker compose up -d

# Update
git pull
docker compose up -d --build
```

### Ubuntu Server + Tailscale

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 2. Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# 3. Clone & Deploy
git clone <repo-url> finance
cd finance
docker compose up -d

# 4. Expose via Tailscale Serve
tailscale serve --bg 8080
```

Akses dari perangkat lain di tailnet: `https://<tailscale-hostname>`

### Backup Database

```bash
# Cukup copy file database
copy data\finance.db backup\finance_backup_%date:~-4%%date:~4,2%%date:~7,2%.db
```

### Scheduler Produksi

Jalankan sekali per hari via cron atau Windows Task Scheduler:

```bash
# Generate bill occurrences
python -m app.jobs_cli bills

# Daily net-worth snapshots
python -m app.jobs_cli networth

# Semua job sekaligus
python -m app.jobs_cli all

# Tanggal spesifik (historical)
python -m app.jobs_cli all --date 2026-09-01
```

## Struktur Proyek

```
FINANCE/
├── app/
│   ├── main.py            # FastAPI app, lifespan (migrate + seed), routers
│   ├── config.py          # Settings (pydantic-settings, baca .env)
│   ├── middleware.py      # Soft session context untuk template nav
│   ├── migrations.py      # Migrasi user-scope & kategori-hirarki (idempotent)
│   ├── rate_limit.py      # Rate limiting middleware
│   ├── time_utils.py      # Timezone-aware datetime helpers
│   ├── utils.py           # Utility functions (format_rupiah, dll)
│   ├── database/
│   │   └── db.py          # Engine, session, Base
│   ├── models/
│   │   └── models.py      # SQLAlchemy models (semua entitas keuangan)
│   ├── schemas/           # Pydantic schemas (input/output API)
│   │   ├── account.py, transaction.py, category.py, ...
│   ├── auth/              # Sessions + router login/register/logout (CSRF)
│   │   ├── router.py, sessions.py, security.py, errors.py
│   ├── api/               # REST API v1 — interface bisnis utama
│   │   ├── router.py      # Agregasi semua router di bawah /api/v1
│   │   ├── deps.py        # get_current_user, get_db
│   │   ├── errors.py      # Pemetaan exception -> JSON error
│   │   ├── health.py
│   │   └── accounts.py, transactions.py, categories.py, ... # per-domain
│   ├── routes/            # Legacy UI web (Jinja, backward-compat)
│   │   ├── dashboard.py, transactions.py, bills.py, ...
│   ├── services/          # Business logic + seeders
│   │   ├── finance.py     # Core: income, expense, transfer, refund
│   │   ├── accounts.py    # Account CRUD + recalculate
│   │   ├── credit_card.py # Statement & minimum payment
│   │   ├── debts.py, bills.py, savings.py, budgets.py, ...
│   │   ├── seed_categories.py  # 70+ kategori Indonesia
│   │   ├── seed_master.py      # Bank, e-wallet, payment methods, merchants
│   │   ├── receipt_ocr.py      # Tesseract OCR engine
│   │   ├── receipt_ai.py       # AI-vision OCR engine
│   │   ├── jobs.py             # Pure callable scheduler functions
│   │   └── reports.py, dashboard.py, ...
│   ├── templates/         # Jinja2 HTML templates
│   │   ├── base.html      # Layout utama (sidebar + bottom nav)
│   │   ├── dashboard.html # Halaman beranda
│   │   ├── auth/          # login, register, setup (onboarding)
│   │   ├── transactions/, accounts/, bills/, debts/, ...
│   │   └── receipts/      # upload, detail, list, form
│   └── static/
│       ├── css/style.css  # Mobile-first dark theme
│       ├── js/app.js      # Core JS (theme, modal, toast, navigation)
│       └── js/receipt_detail.js
├── data/                  # SQLite database (persistent, git-ignored)
├── tests/
│   ├── conftest.py        # Test client pre-auth, DB terisolasi
│   ├── test_auth.py       # Auth & session tests
│   ├── test_api.py        # REST API tests
│   ├── test_finance.py    # Core finance & UI tests
│   ├── test_accounting.py # Accounting invariant tests
│   ├── test_statement_audit.py  # Credit card statement tests
│   ├── test_atomicity.py  # Transaction atomicity tests
│   ├── test_money_edges.py # Money edge case tests
│   ├── test_migrations.py # Schema migration tests
│   ├── test_ui.py         # Template & CSS tests
│   ├── test_receipt_ai.py # OCR pipeline tests
│   ├── test_bill_scheduler.py # Bill occurrence tests
│   ├── test_networth_job.py   # Net worth snapshot tests
│   └── ...
├── docs/
│   └── AUDIT.md           # Audit keamanan & status fitur
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

## Aturan Akuntansi

Semua jumlah uang disimpan sebagai **integer dalam satuan Rupiah** (Rp 25.000 = 25000). Tidak ada floating point untuk perhitungan uang.

| Operasi | Income | Expense | Saldo Akun | Liabilitas |
|---------|--------|---------|------------|------------|
| Income (cash/bank) | + | − | + | − |
| Expense (cash/bank) | − | + | − | − |
| Transfer (A → B) | − | − | A: −, B: + | − |
| Expense (credit card) | − | + | − | + |
| Transfer (cash → CC) | − | − | cash: − | − |
| Debt payment | − | + | − | − |
| Savings deposit | − | − | − | − |
| Refund | + | − | + | − |

- **Transfer tidak dihitung sebagai income atau expense** — hanya memindahkan saldo
- **Saldo akun** = `initial_balance + income − expense − transfer_out + transfer_in`
- **Credit card expense** menambah liabilitas, bukan mengurangi cash
- **Pembayaran hutang** via transfer cash → credit card (liabilitas berkurang, bukan expense)
- **Tabungan** bukan expense — hanya memindahkan uang ke goal

## Keamanan

- **Password hashing**: PBKDF2-HMAC-SHA256 dengan salt acak
- **Session**: token SHA-256 di database, cookie HttpOnly + SameSite=Lax
- **CSRF**: double-submit token pada semua form HTML
- **IDOR protection**: semua query di-scope by `user_id`
- **Production guard**: `SECRET_KEY` wajib di-set, `DEBUG` forced off di production
- **CORS**: default localhost only; production via env
- **Rate limiting**: middleware tersedia untuk endpoint sensitif

## Status Pengembangan

### Sudah Lengkap ✅
- Auth & session
- Dashboard & transaksi
- Transfer antar akun
- Akun keuangan (Cash, Bank, E-Wallet, Credit Card)
- Kategori ber-hirarki
- Hutang, tagihan, budget, tabungan
- Aset & investasi
- Kartu kredit (statement, minimum payment)
- Receipt OCR (Tesseract + AI-vision)
- Laporan & export CSV
- REST API v1
- Net worth snapshot harian
- Bill scheduler (CLI)
- Onboarding flow
- Sidebar navigasi lengkap

### Sedang Dikerjakan 🚧
- Merchant sebagai first-class entity (normalized dengan aliases)
- PaymentMethod sebagai first-class entity
- Credit card statement-date / due-date / credit-limit
- BBM/fuel price reference catalog
- Master-data provenance fields

### Direncanakan 📋
- PWA support
- Multi-currency
- Recurring transactions
- Budget alerts/notifications
- Data export (PDF, Excel)

---

**Lisensi**: Private — hak cipta milik pembuat.
