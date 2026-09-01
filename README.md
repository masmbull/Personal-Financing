# Finance

Aplikasi web pencatatan keuangan pribadi yang ringan, cepat, dan mobile-first.

## Features

- **Autentikasi & isolasi data per user** — login/register/logout (CSRF double-submit, session HttpOnly + SameSite=Lax), setiap user hanya melihat datanya sendiri
- **REST API `/api/v1`** — interface bisnis utama (bisa dipakai web/PWA/mobile)
- **Dashboard**: total saldo, pemasukan/pengeluaran bulan ini, cashflow, transaksi terbaru, snapshot net worth harian
- **Transaksi**: CRUD lengkap, filter, search
- **Transfer antar akun**
- **Akun** (Cash, Bank, E-Wallet, dll) — 20 bank & 6 e-wallet yang di-seed
- **Kategori ber-hirarki** (parent/child) — tree, dengan guard siklus & tipe silang
- **Debt tracker**, **tagihan (bills)**, **budget**, **tabungan (savings goals)**, **aset**, **investasi**
- **Laporan**: harian, mingguan, bulanan, per kategori, trend 6 bulan
- **Receipt scanner (OCR)** — upload struk, baca otomatis via Tesseract atau AI-vision (Ollama), review & konfirmasi jadi transaksi, deteksi duplikat

## Requirements

- Python 3.11+
- Docker & Docker Compose (untuk deployment)
- SQLite (built-in, tidak perlu install tambahan)
- Tesseract OCR (untuk scan struk; wajib di Windows, set `TESSERACT_CMD`)
- Ollama + model vision (opsional, untuk AI OCR yang lebih akurat)

## Tech Stack

- **Backend:** Python, FastAPI/Starlette, SQLAlchemy, Jinja2, Pydantic
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript (mobile-first, no framework)
- **OCR:** Tesseract + optional AI-vision (Ollama, OpenAI-compatible), pillow-heif
- **Deployment:** Docker, Docker Compose

## Local Development

### 1. Clone & Setup

```bash
git clone <repo-url> finance
cd finance
python -m venv venv
venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Environment Variables

```bash
copy .env.example .env    # Windows
# cp .env.example .env   # Linux/Mac
```

Edit `.env` jika perlu. Default sudah cocok untuk development.

### 3. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Buka http://localhost:8080

### 4. Database

Database SQLite otomatis dibuat di `./data/finance.db` saat pertama kali run.

Default data yang di-seed (idempotent, match by slug — tidak duplikat saat re-run):
- 20 bank + 6 e-wallet + Cash
- >70 kategori ber-hirarki (parent/child) untuk pengeluaran & pemasukan

> **Login**: buat user via `/register`, atau set `AUTH_BOOTSTRAP_USERNAME`/`AUTH_BOOTSTRAP_PASSWORD` di `.env` untuk membuat admin otomatis saat startup pertama (row legacy di-claim ke admin ini).

## Docker Development

```bash
docker compose up -d
```

Buka http://localhost:8080

Stop:
```bash
docker compose down
```

## Database Location

Database disimpan di `./data/finance.db` (persistent).

Untuk Docker, volume bind mount `./data:/app/data` memastikan data tidak hilang saat container dibuat ulang.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/finance.db` | Database connection string |
| `APP_NAME` | `Finance` | Nama aplikasi |
| `APP_HOST` | `0.0.0.0` | Host untuk server |
| `APP_PORT` | `8080` | Port server |
| `APP_ENV` | `development` | `development` \| `production` \| `test` |
| `DEBUG` | `true` | Debug mode |
| `SECRET_KEY` | `change-me-in-production` | Ganti di produksi |
| `AUTH_BOOTSTRAP_USERNAME` | *(kosong)* | Bootstrap admin dibuat saat startup pertama |
| `AUTH_BOOTSTRAP_PASSWORD` | *(kosong)* | Password admin (jangan di-commit) |
| `AUTH_SESSION_TTL_DAYS` | `30` | Umur sesi (hari) |
| `CORS_ORIGINS` | `http://localhost:8080,...` | Origin yang diizinkan (jangan `*` di prod) |
| `RECEIPT_UPLOAD_DIR` | `data/receipts` | Folder simpan struk |
| `RECEIPT_MAX_SIZE_MB` | `5` | Ukuran maks upload (MB) |
| `TESSERACT_CMD` | *(deteksi otomatis)* | Path `tesseract.exe` |
| `RECEIPT_OCR_LANG` | `ind+eng` | Bahasa OCR |
| `RECEIPT_AI_BASE_URL` | `http://localhost:11434/v1` | Endpoint Ollama (opsional) |
| `RECEIPT_AI_MODEL` | `llama3.2-vision` | Model vision AI |
| `RECEIPT_AI_TIMEOUT_SEC` | `120` | Timeout AI (detik) |
| `RECEIPT_AI_FALLBACK_TESSERACT` | `1` | Fallback ke Tesseract bila AI gagal |
| `RECEIPT_AI_MAX_IMAGE_WIDTH` | `1600` | Resolusi maks gambar dikirim ke AI |

Semua variabel opsional sudah punya default aman — cukup copy `.env.example` ke `.env` untuk development.

## Testing

```bash
# Pastikan test dependencies terinstall
pip install pytest httpx

# Jalankan test
pytest tests/ -v
```

## Backup Database

```bash
# Cukup copy file database
copy data\finance.db backup\finance_backup_%date:~-4%%date:~4,2%%date:~7,2%.db
```

## Deployment ke Ubuntu Server

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

### 2. Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### 3. Clone & Deploy

```bash
git clone <repo-url> finance
cd finance
docker compose up -d
```

### 4. Expose via Tailscale Serve

```bash
tailscale serve --bg 8080
```

Akses dari perangkat lain di tailnet: `https://<tailscale-hostname>`

## Update Aplikasi

```bash
cd finance
git pull
docker compose up -d --build
```

Database tidak terpengaruh karena sudah di volume terpisah.

## Project Structure

```
FINANCE/
├── app/
│   ├── main.py            # FastAPI app, lifespan (migrate + seed), routers
│   ├── config.py          # Settings (pydantic-settings, baca .env)
│   ├── middleware.py      # Soft session context untuk template nav
│   ├── migrations.py      # Migrasi user-scope & kategori-hirarki (idempotent)
│   ├── database/
│   │   └── db.py          # Engine, session, Base
│   ├── models/
│   │   └── models.py      # SQLAlchemy models (semua entitas keuangan)
│   ├── schemas/           # Pydantic schemas (input/output API)
│   ├── auth/              # Sessions + router login/register/logout (CSRF)
│   ├── api/               # REST API v1 — interface bisnis utama
│   │   ├── router.py      # Agregasi semua router di bawah /api/v1
│   │   ├── deps.py        # get_current_user, get_db
│   │   ├── errors.py      # Pemetaan exception -> JSON error
│   │   ├── health.py
│   │   └── accounts.py, transactions.py, categories.py, ... # per-domain
│   ├── routes/            # Legacy UI web (Jinja, backward-compat)
│   ├── services/          # Business logic + seed_categories.py
│   ├── templates/         # Jinja2 HTML templates
│   └── static/
│       ├── css/style.css  # Mobile-first dark theme
│       └── js/app.js, receipt_detail.js
├── data/                  # SQLite database (persistent, git-ignored)
├── tests/
│   ├── conftest.py        # Test client pre-auth, DB terisolasi
│   ├── test_auth.py, test_api.py, test_finance.py, test_ui.py,
│   ├── test_categories.py # Unit & integration tests
│   └── test_receipt_ai.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Notes

- Semua jumlah uang disimpan sebagai **integer dalam satuan Rupiah** (Rp 25.000 = 25000)
- Tidak ada floating point untuk perhitungan uang
- Balance akun dihitung dari: `initial_balance + income - expense - transfer_out + transfer_in`
- Transfer tidak dihitung sebagai income atau expense
- Kategori tidak bisa dihapus jika masih digunakan transaksi
