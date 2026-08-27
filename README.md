# Finance

Aplikasi web pencatatan keuangan pribadi yang ringan, cepat, dan mobile-first.

## Features

- Dashboard: total saldo, pemasukan/pengeluaran bulan ini, cashflow, transaksi terbaru
- Transaksi: CRUD lengkap, filter, search
- Transfer antar akun
- Kelola akun (Cash, Bank, E-Wallet, dll)
- Kelola kategori (Pengeluaran & Pemasukan)
- Laporan: harian, mingguan, bulanan, per kategori, trend 6 bulan

## Requirements

- Python 3.11+
- Docker & Docker Compose (untuk deployment)
- SQLite (built-in, tidak perlu install tambahan)

## Tech Stack

- **Backend:** Python, FastAPI, SQLAlchemy, Jinja2
- **Database:** SQLite
- **Frontend:** HTML, CSS, JavaScript (mobile-first, no framework)
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

Default data yang di-seed:
- 5 akun (Cash, BCA, Mandiri, DANA, GoPay)
- 14 kategori (9 pengeluaran, 5 pemasukan)

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
| `DEBUG` | `true` | Debug mode |

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
│   ├── main.py           # FastAPI app, startup, seed data
│   ├── config.py          # Settings dari .env
│   ├── utils.py           # Helper functions
│   ├── database/
│   │   └── db.py          # Engine, session, Base
│   ├── models/
│   │   └── models.py      # SQLAlchemy models
│   ├── routes/
│   │   ├── dashboard.py   # Dashboard & Account routes
│   │   ├── transactions.py # Transaction CRUD
│   │   ├── categories.py   # Category CRUD
│   │   ├── reports.py      # Reports
│   │   └── transfer.py     # Transfer
│   ├── services/
│   │   └── finance.py     # Business logic
│   ├── templates/          # Jinja2 HTML templates
│   └── static/
│       ├── css/style.css   # Mobile-first dark theme
│       └── js/app.js       # Minimal JS
├── data/                   # SQLite database (persistent)
├── tests/
│   └── test_finance.py    # Unit & integration tests
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
