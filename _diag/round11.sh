cd /opt/finance
echo '===== A. SUDO MATRIX + SERVICE + PROCS ====='
sudo -n -l 2>&1 | head -20
systemctl show finance -p MainPID -p ExecMainStartTimestamp 2>/dev/null
echo '--- uvicorn procs ---'
ps -eo pid,ppid,lstart,user,cmd | grep -E '[u]vicorn app.main:app'
echo '--- unit EnvironmentFile ---'
systemctl cat finance 2>/dev/null | grep -E '^(EnvironmentFile|Environment|User|WorkingDirectory)='
echo '===== B. WORKER /proc ENVIRON: NAMES ONLY, rc tracked ====='
for pid in $(pgrep -f 'uvicorn app.main:app'); do
  echo "--- PID $pid | lstart: $(ps -o lstart= -p $pid 2>/dev/null) ---"
  sudo -n sh -c "tr '\0' '\n' < /proc/$pid/environ" > /tmp/_env.$$ 2>/tmp/_e.$$
  rc=$?
  echo "read rc=$rc | error=[$(cat /tmp/_e.$$ 2>/dev/null)]"
  if [ $rc -eq 0 ] && [ -s /tmp/_env.$$ ]; then
    echo "total vars: $(wc -l < /tmp/_env.$$)"
    echo "GEMINI-related var NAMES present:"
    grep -E '^GEMINI' /tmp/_env.$$ | cut -d= -f1 | sort
    echo "RECEIPT-related var NAMES present:"
    grep -E '^RECEIPT' /tmp/_env.$$ | cut -d= -f1 | sort
    echo "GEMINI_MODEL name present: $(grep -c '^GEMINI_MODEL=' /tmp/_env.$$)"
  else
    echo '(environ unreadable - need root)'
  fi
  rm -f /tmp/_env.$$ /tmp/_e.$$
done
echo '===== C. .env FORMAT (cat -A reveals CRLF/quoting) ====='
echo -n 'CR chars in .env: '; grep -cU $'\r' .env || echo 0
echo '--- .env file type ---'; file .env
echo '--- GEMINI_MODEL occurrence(s) cat -A ---'
grep -n 'GEMINI_MODEL' .env | cat -A
echo '--- RECEIPT_AI_* and GEMINI_BASE_URL lines cat -A ---'
grep -nE '^(RECEIPT_AI_ENABLED|RECEIPT_AI_PROVIDER|GEMINI_BASE_URL)=' .env | cat -A
echo '--- all GEMINI/OPENAI key lines (values redacted) cat -A ---'
grep -nE '^GEMINI|^OPENAI' .env | sed -E 's/(=.+)/=<redacted>/' | cat -A | head -20
echo '===== D. FRESH IMPORT (worker mechanism, no sourcing) ====='
venv/bin/python3.11 -u - <<'PYEOF'
from app.config import settings
print('provider=%s enabled=%s model=%r base=%s key_set=%s' % (
    settings.RECEIPT_AI_PROVIDER, settings.RECEIPT_AI_ENABLED,
    settings.GEMINI_MODEL, settings.GEMINI_BASE_URL, bool(settings.GEMINI_API_KEY)))
PYEOF
echo '===== E. IN-PROCESS CloudReceiptScannerService().scan() on RECEIPT 7 IMAGE (app payload+prompt, no DB write) ====='
venv/bin/python3.11 -u - <<'PYEOF'
import json, os, sqlite3
from app.config import settings
from app.services.receipt_ai import CloudReceiptScannerService, GeminiVisionProvider
print('provider object model:', GeminiVisionProvider().model)
print('provider object base_url:', GeminiVisionProvider().base_url)
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
row = con.execute('SELECT stored_path FROM receipts WHERE id=7').fetchone()
con.close()
p = row[0]
print('receipt7 image:', p, '| exists:', os.path.exists(p), '| bytes:', os.path.getsize(p) if os.path.exists(p) else 0)
sc = CloudReceiptScannerService()
print('engine:', sc.name)
import time
t0 = time.monotonic()
res = sc.scan(p)
dt = time.monotonic() - t0
d = res.to_dict()
print('scan elapsed: %.2fs' % dt)
print('result status=%s engine=%s error=%r' % (d.get('status'), d.get('engine'), d.get('error')))
print('merchant=%r date=%r total=%r items=%d' % (d.get('merchant'), d.get('date'), d.get('total_amount'), len(d.get('items') or [])))
print('all non-empty keys:', sorted(k for k, v in d.items() if v not in (None, [], ''))[:16])
PYEOF
echo '===== F. RECEIPT 7 DB ROW ====='
venv/bin/python3.11 -u - <<'PYEOF'
import sqlite3
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
print('ids:', con.execute('SELECT id FROM receipts ORDER BY id').fetchall())
print('receipt7:', con.execute('SELECT id,user_id,original_filename,stored_path,mime_type,size_bytes,file_hash,ocr_status,created_at FROM receipts WHERE id=7').fetchone())
con.close()
PYEOF
echo '===== G. JOURNAL RESTART + UPLOAD WINDOW ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 10:05:50' --until '2026-09-10 10:07:30' 2>/dev/null | tail -30
echo '===== DONE11 ====='