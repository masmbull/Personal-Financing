# Clone dan Setup

Dokumen ini adalah checklist agar proyek dapat dijalankan kembali dari clone baru.

## Prasyarat

- Git
- Python **3.11+** (Python 3.12 direkomendasikan untuk Docker image yang tersedia)
- Akses internet saat menjalankan bootstrap, untuk mengunduh paket Python
- Opsional: Docker Desktop / Docker Engine untuk menjalankan container
- Opsional: Tesseract OCR bila ingin OCR lokal tanpa layanan AI

## Setup lokal: satu perintah

```powershell
git clone <repo-url> finance
cd finance
python bootstrap.py
```

`bootstrap.py` membuat `.venv`, memperbarui `pip`, memasang seluruh paket dari
`requirements.txt` (termasuk dependency test), dan membuat `.env` dari
`.env.example` bila belum ada. File `.env` yang telah ada tidak pernah ditimpa.

Jalankan aplikasi setelah bootstrap:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

Untuk Linux/macOS, gunakan `.venv/bin/python` sebagai gantinya. Buka
`http://localhost:8080`. Database dan folder upload akan dibuat otomatis di
`data/`.

## Pengaturan manual

Untuk development biasa, `.env` hasil bootstrap sudah cukup. Sebelum production,
ubah minimal nilai berikut di `.env`:

| Variabel | Yang harus dilakukan |
| --- | --- |
| `APP_ENV` | Set ke `production`. |
| `DEBUG` | Set ke `false`. |
| `SECRET_KEY` | Buat nilai acak unik, misalnya `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Jangan gunakan nilai contoh. |
| `AUTH_BOOTSTRAP_USERNAME` / `AUTH_BOOTSTRAP_PASSWORD` | Isi hanya untuk membuat admin pertama pada database kosong; gunakan password unik dan kuat. |
| `CORS_ORIGINS` | Isi origin HTTPS aplikasi yang benar, dipisahkan koma. Jangan gunakan `*`. |

Pengaturan OCR/AI bersifat opsional:

- Cloud OpenAI: `RECEIPT_AI_PROVIDER=openai` dan `OPENAI_API_KEY=...`.
- Cloud Gemini: `RECEIPT_AI_PROVIDER=gemini` dan `GEMINI_API_KEY=...`.
- Lokal: `RECEIPT_AI_PROVIDER=ollama`, siapkan Ollama serta model vision sesuai
  `OLLAMA_VISION_MODEL`.
- Tanpa AI: set `RECEIPT_AI_PROVIDER=none`. OCR Tesseract tetap dapat digunakan
  bila program Tesseract tersedia pada `TESSERACT_CMD`.

Rahasia tidak boleh dimasukkan ke Git. `.env`, database SQLite, upload receipt,
dan backup sudah diabaikan oleh `.gitignore`.

## Docker

```bash
cp .env.example .env
# edit .env: isi SECRET_KEY, APP_ENV=production, DEBUG=false, dan admin bootstrap
docker compose up -d --build
```

Compose membaca `.env` ke dalam container. Data persisten berada pada bind mount
`./data:/app/data`. Image Docker sudah menyertakan Tesseract dengan data bahasa
Indonesia dan Inggris; tetap konfigurasi provider AI secara terpisah bila ingin
memakai OCR cloud. Untuk melihat log: `docker compose logs -f finance`.

### GitHub Actions deployment (opsional)

Workflow deploy hanya berjalan setelah test lulus di branch `main`. Jika ingin
memakainya, simpan nilai server di **GitHub Actions Secrets**, bukan di file
workflow atau `.env` yang di-commit: `DEPLOY_HOST`, `DEPLOY_USERNAME`,
`SSH_PRIVATE_KEY`, `TS_OAUTH_CLIENT_ID`, dan `TS_OAUTH_SECRET`.

## Scheduler harian

Jalankan berikut sekali sehari melalui cron atau Windows Task Scheduler. Semua
job idempoten, sehingga aman dijalankan ulang jika scheduler retry.

```powershell
# Buat tagihan jatuh tempo (tidak memindahkan uang otomatis)
.\.venv\Scripts\python.exe -m app.jobs_cli bills

# Posting transaksi berulang yang telah jatuh tempo
.\.venv\Scripts\python.exe -m app.jobs_cli recurring

# Simpan snapshot net worth harian
.\.venv\Scripts\python.exe -m app.jobs_cli networth

# Jalankan semua job di atas
.\.venv\Scripts\python.exe -m app.jobs_cli all
```

## Verifikasi

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Jika test dihentikan paksa di Windows, SQLite dapat meninggalkan `test*.db` atau
`test*.db-journal` yang diabaikan Git. Tutup semua proses test, hapus file test
tersebut, lalu ulangi command test. File aplikasi sebenarnya berada di
`data/finance.db`, jadi jangan hapus file tersebut kecuali memang ingin reset
data lokal.
