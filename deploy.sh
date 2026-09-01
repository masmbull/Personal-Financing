#!/bin/bash
# =====================================================================
# Finance App - Ubuntu Server Deploy Script
# Usage:  bash deploy.sh
# Requires: sudo, internet, domain DNS already pointed to this server
# =====================================================================
set -e

# ---- CONFIG (edit if needed) ----
DOMAIN="guepunya.my.id"
APP_DIR="/opt/finance"
APP_PORT="8000"
SERVICE_NAME="finance"
REPO_URL="https://github.com/masmbull/Personal-Financing.git"
# Kalau repo PRIVATE, set ini ke token lo: https://<TOKEN>@github.com/...
# Kosongkan kalau repo public.
GIT_TOKEN=""
# Minimum Python version. App butuh 3.9+ (Pydantic 2.10).
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=9

echo "🚀 Finance App Deploy"
echo "====================="
echo "Domain : $DOMAIN"
echo "App dir: $APP_DIR"
echo "Port   : $APP_PORT"
echo ""

# 0. Cloudflare warning
echo "⚠️  CLOUDFLARE NOTE:"
echo "   Domain ada di Cloudflare. Agar certbot (Let's Encrypt) berhasil"
echo "   via HTTP-01 challenge, set DNS record A ke 'DNS only' (gray cloud)"
echo "   DULU di dashboard Cloudflare. Setelah SSL jalan, boleh balik ke"
echo "   'Proxied' (orange cloud) + SSL mode: Full (strict)."
echo "   Lanjut dalam 5 detik... (Ctrl+C untuk batal)"
sleep 5
echo ""

# 1. Check Python
echo "📋 Checking Python..."

pick_python() {
    # Prefer newest 3.x available on PATH
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v $cand &> /dev/null; then
            local ver=$($cand -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            local major=$(echo $ver | cut -d. -f1)
            local minor=$(echo $ver | cut -d. -f2)
            if [ "$major" -gt "$MIN_PYTHON_MAJOR" ] || \
               { [ "$major" -eq "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; }; then
                echo $cand
                return 0
            fi
        fi
    done
    return 1
}

PYTHON_BIN=$(pick_python || true)

if [ -z "$PYTHON_BIN" ]; then
    echo "⚠️  No Python >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} found. Installing python3.11..."
    sudo apt update
    sudo apt install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
    sudo apt update
    sudo apt install -y python3.11 python3.11-venv python3.11-distutils
    PYTHON_BIN=python3.11
fi

echo "✅ Using $($PYTHON_BIN --version) at $(command -v $PYTHON_BIN)"

# Ensure venv + pip available for the chosen Python
PYV=$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYPKG="python${PYV}-venv"
if ! dpkg -s $PYPKG &> /dev/null; then
    echo "📦 Installing $PYPKG..."
    sudo apt install -y $PYPKG
fi

# 1b. Ensure git installed (needed for clone)
if ! command -v git &> /dev/null; then
    echo "📦 Installing git..."
    sudo apt install -y git
fi
git --version

# 2. Create app directory
echo "📁 Creating app directory..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

# 3. Clone / pull repo
echo "📥 Cloning / updating repository..."
cd $APP_DIR
if [ -d .git ]; then
    sudo -u $USER git pull origin main || true
else
    if [ -n "$GIT_TOKEN" ]; then
        AUTH_URL=$(echo "$REPO_URL" | sed "s|https://|https://${GIT_TOKEN}@|")
        sudo -u $USER git clone "$AUTH_URL" .
    else
        sudo -u $USER git clone "$REPO_URL" .
    fi
fi

# 4. Setup venv
echo "🐍 Setting up Python venv (using $PYTHON_BIN)..."
# Clean broken venv from previous failed run
if [ -d venv ] && [ ! -x venv/bin/python3 ]; then
    echo "🧹 Removing broken venv from previous attempt..."
    rm -rf venv
fi
sudo -u $USER $PYTHON_BIN -m venv venv

# 5. Install deps
echo "📦 Installing dependencies..."
sudo -u $USER venv/bin/pip install --upgrade pip
sudo -u $USER venv/bin/pip install -r requirements.txt
# 6. Create .env
echo "⚙️ Creating .env..."
if [ ! -f .env ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sudo -u $USER tee .env > /dev/null << EOF
# ===== Application =====
DATABASE_URL=sqlite:///./data/finance.db
APP_NAME=Finance
APP_HOST=0.0.0.0
APP_PORT=$APP_PORT

# production
APP_ENV=production
DEBUG=false

# ===== Security =====
SECRET_KEY=$SECRET_KEY

# ===== Authentication =====
AUTH_BOOTSTRAP_USERNAME=admin
AUTH_BOOTSTRAP_PASSWORD=change-this-password-immediately
AUTH_SESSION_TTL_DAYS=30

# ===== CORS =====
CORS_ORIGINS=https://$DOMAIN,https://www.$DOMAIN

# ===== Receipt uploads =====
RECEIPT_UPLOAD_DIR=data/receipts
RECEIPT_MAX_SIZE_MB=5
EOF
    echo "✅ .env created — CHANGE AUTH_BOOTSTRAP_PASSWORD!"
else
    echo "✅ .env already exists"
fi

# 7. Create data dirs
echo "📂 Creating data directories..."
sudo -u $USER mkdir -p data/receipts
sudo chmod 755 data

# 8. DB auto-created on startup via lifespan
echo "🗄️ DB akan auto-create saat app start"

# 9. Create systemd service
echo "⚙️ Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Finance Application
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $APP_PORT --workers 2 --proxy-headers --forwarded-allow-ips='*'
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME
echo "✅ Systemd service: $SERVICE_NAME"

sleep 4
if curl -s http://localhost:$APP_PORT/ > /dev/null 2>&1; then
    echo "✅ App running on port $APP_PORT"
else
    echo "⚠️ App belum respon. Cek: sudo journalctl -u $SERVICE_NAME -n 50"
fi

# 10. Setup Nginx (HTTP first; certbot adds HTTPS)
echo "🌐 Setting up Nginx..."
if ! command -v nginx &> /dev/null; then
    sudo apt update
    sudo apt install -y nginx
fi

sudo tee /etc/nginx/sites-available/$DOMAIN > /dev/null << NGINXEOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    client_max_body_size 10M;

    location /static/ {
        alias $APP_DIR/app/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
NGINXEOF

sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
echo "✅ Nginx HTTP config done"

# 11. Let's Encrypt
echo "🔐 Setting up Let's Encrypt..."
if ! command -v certbot &> /dev/null; then
    sudo apt install -y certbot python3-certbot-nginx
fi

echo "🔑 Requesting SSL cert (HTTP-01 challenge)..."
echo "   Pastikan DNS '$DOMAIN' sudah resolve ke server ini (gray cloud dulu)."
sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos \
    -m "noreply@$DOMAIN" --redirect || {
    echo "⚠️ Certbot gagal. Kemungkinan DNS belum resolve atau Cloudflare proxy on."
    echo "   Coba: set DNS ke 'DNS only' (gray cloud) di Cloudflare, lalu:"
    echo "   sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
}

sudo systemctl reload nginx
sudo systemctl enable certbot.timer 2>/dev/null || true

echo ""
echo "========================================"
echo "✅ SETUP SELESAI"
echo "========================================"
echo "📍 Akses    : https://$DOMAIN"
echo "🔑 Admin    : admin  /  (lihat $APP_DIR/.env → AUTH_BOOTSTRAP_PASSWORD)"
echo "             ↑ GANTI password setelah login pertama!"
echo ""
echo "📋 Logs app : sudo journalctl -u $SERVICE_NAME -f"
echo "🔄 Restart  : sudo systemctl restart $SERVICE_NAME"
echo "🛑 Stop     : sudo systemctl stop $SERVICE_NAME"
echo "📝 Edit env : sudo nano $APP_DIR/.env  (lalu restart service)"
echo ""
echo "🔄 Update kode (lain kali):"
echo "   cd $APP_DIR && git pull && sudo systemctl restart $SERVICE_NAME"
echo ""
echo "🔒 CLOUDFLARE (setelah SSL jalan):"
echo "   1. Dashboard Cloudflare → DNS"
echo "   2. Edit record A '$DOMAIN' → ubah ke 'Proxied' (orange cloud)"
echo "   3. SSL/TLS → Overview → mode: 'Full (strict)'"
echo "   4. Edge Certificates → Always Use HTTPS: ON"

