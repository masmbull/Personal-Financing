cd /opt/finance
echo '===== A. PROCESS TREE + SERVICE ====='
systemctl show finance -p MainPID -p ExecMainStartTimestamp 2>/dev/null
echo '--- all python/uvicorn procs ---'
ps -eo pid,ppid,lstart,user,cmd | grep -E '[p]ython|[u]vicorn' | head -20
echo '--- any OLD uvicorn from pre-10:06 alive? (none expected) ---'
pgrep -af 'uvicorn app.main:app' | head
echo '--- unit file EnvironmentFile line ---'
sed -n 's/^EnvironmentFile=.*/EnvironmentFile=DETECTED/p' /etc/systemd/system/finance.service 2>/dev/null || grep -h EnvironmentFile /usr/lib/systemd/system/finance.service 2>/dev/null || systemctl cat finance 2>/dev/null | grep EnvironmentFile || echo 'unit file not found in standard paths'
echo '===== B. WORKER /proc/<pid>/environ: var NAMES ONLY (no values) ====='
for pid in $(sudo -n pgrep -f 'uvicorn app.main:app'); do
  echo "--- PID $pid | lstart: $(ps -o lstart= -p $pid 2>/dev/null) ---"
  sudo -n sh -c "tr '\0' '\n' < /proc/$pid/environ" 2>/dev/null > /tmp/_env.$$
  rc=$?
  echo "read rc=$rc | total vars: $(wc -l < /tmp/_env.$$ 2>/dev/null)"
  if [ -s /tmp/_env.$$ ]; then
    echo 'env var NAMES:'
    cut -d= -f1 /tmp/_env.$$ | sort | head -60
    echo '--- RECEIPT/GEMINI/OPENAI ranges:'
    grep -E '^(RECEIPT_AI|GEMINI|OPENAI)' /tmp/_env.$$ | sed -E 's/(KEY=).*/\1<redacted>/' | head -20
  fi
  rm -f /tmp/_env.$$
done
echo '===== C. .env GEMINI/RECEIPT LINES (key values redacted, model/provider shown) ====='
grep -nE '^(RECEIPT_AI|GEMINI|OPENAI)' .env | sed -E 's/((API_KEY|SECRET)[^=]*)=.*/\1=<redacted>/'
echo '--- exact GEMINI_MODEL / RECEIPT_AI_PROVIDER / RECEIPT_AI_ENABLED lines with visible formatting (cat -A) ---'
grep -nE '^(RECEIPT_AI_ENABLED|RECEIPT_AI_PROVIDER|GEMINI_MODEL|GEMINI_BASE_URL)[[:space:]]*=' .env | cat -A
echo '===== D. FRESH IMPORT WITHOUT SOURCING (exact worker mechanism: pydantic reads .env, cwd=/opt/finance) ====='
venv/bin/python3.11 -u - <<'PYEOF'
from app.config import settings
print('provider:', settings.RECEIPT_AI_PROVIDER)
print('enabled:', settings.RECEIPT_AI_ENABLED)
print('gemini_model:', settings.GEMINI_MODEL)
print('gemini_base_url:', settings.GEMINI_BASE_URL)
print('GEMINI_API_KEY_set:', bool(settings.GEMINI_API_KEY))
print('log_level:', settings.log_level)
import app.services.receipt_ocr as o
sc = o.build_scanner()
def names(n):
    out = [getattr(n, 'name', type(n).__name__)]
    i = getattr(n, 'inner', None)
    if i is not None: out += names(i)
    for e in getattr(n, 'engines', None) or []: out += names(e)
    return out
print('chain:', ' > '.join(names(sc)))
PYEOF
echo '===== E. RECEIPT 7 DETAIL + FULL ID LIST ====='
venv/bin/python3.11 -u - <<'PYEOF'
import json, os, sqlite3
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
print('all ids/created:', con.execute('SELECT id, created_at FROM receipts ORDER BY id').fetchall())
row = con.execute('SELECT id, user_id, original_filename, stored_path, mime_type, size_bytes, file_hash, ocr_status, created_at, transaction_id FROM receipts WHERE id=7').fetchone()
print('receipt 7:', row)
if row:
    print('stored_path exists:', os.path.exists(row[3]), '| bytes:', os.path.getsize(row[3]) if os.path.exists(row[3]) else 0)
try:
    print('sqlite_sequence:', con.execute("SELECT * FROM sqlite_sequence WHERE name='receipts'").fetchall())
except Exception as e:
    print('seq n/a:', e)
con.close()
PYEOF
echo '===== F. JOURNAL: restart window + receipt-7 window ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 10:05:50' --until '2026-09-10 10:07:30' 2>/dev/null | grep -vE '^\s*$' | tail -40
echo '===== DONE10 ====='