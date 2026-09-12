cd /opt/finance
echo '===== 0. PROCESS / SERVICE STATE ====='
systemctl show finance -p MainPID -p ExecMainStartTimestamp -p ActiveEnterTimestamp 2>/dev/null
echo '--- uvicorn procs (lstart = process start) ---'
ps -eo pid,ppid,lstart,cmd | grep -E '[u]vicorn app.main:app'
echo '--- .env mtime + model lines (counts only) ---'
stat -c 'env mtime: %y' .env
echo -n 'GEMINI_MODEL=gemini-3.6-flash lines: '; grep -cE '^GEMINI_MODEL=gemini-3.6-flash' .env || true
echo -n 'GEMINI_MODEL=gemini-2.5-flash lines: '; grep -cE '^GEMINI_MODEL=gemini-2.5-flash' .env || true
echo '===== 1. LIVE WORKER ENV (/proc/<pid>/environ, secrets redacted) ====='
for pid in $(pgrep -f 'uvicorn app.main:app'); do
  echo "--- PID $pid | started: $(ps -o lstart= -p $pid 2>/dev/null) ---"
  envout=$(sudo -n cat /proc/$pid/environ 2>/dev/null | tr '\0' '\n' | grep -E '^(RECEIPT_AI_ENABLED|RECEIPT_AI_PROVIDER|GEMINI_MODEL|GEMINI_BASE_URL|GEMINI_API_KEY)=' )
  if [ -n "$envout" ]; then
    echo "$envout" | sed -E 's/^GEMINI_API_KEY=.*/GEMINI_API_KEY=PRESENT/'
  else
    echo '(unreadable or not set)'
  fi
done
echo '===== 2. LATEST UPLOADS IN JOURNAL ====='
sudo -n journalctl -u finance --no-pager 2>/dev/null | grep -E 'POST /receipts/upload|GET /receipts/[0-9]+\?uploaded=1' | tail -14
echo '===== 2b-8. RECEIPTS DB (read-only) ====='
venv/bin/python3.11 -u - <<'PYEOF'
import json, sqlite3
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
cols = [r[1] for r in con.execute('PRAGMA table_info(receipts)')]
print('columns:', cols)
print('row count:', con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0])
rows = con.execute(
    'SELECT id, user_id, file_hash, ocr_status, created_at, ocr_data '
    'FROM receipts ORDER BY id DESC LIMIT 3').fetchall()
for rid, uid, fh, status, created, blob in rows:
    try:
        d = json.loads(blob or '{}')
    except Exception:
        d = {'raw': (blob or '')[:120]}
    items = d.get('items') or []
    print('--- receipt id=%s user=%s hash=%s status=%s created=%s ---' % (rid, uid, (fh or '')[:12], status, created))
    print('  ocr: engine=%s status=%s error=%r' % (d.get('engine'), d.get('status'), d.get('error')))
    print('  merchant=%r date=%r total=%r items=%d' % (d.get('merchant'), d.get('date'), d.get('total_amount'), len(items)))
# dedup: any earlier receipt sharing the latest hash
latest = rows[0] if rows else None
if latest:
    lhash = latest[2]
    if lhash:
        dups = con.execute('SELECT id, created_at, ocr_status FROM receipts WHERE file_hash=? AND id!=? ORDER BY id', (lhash, latest[0])).fetchall()
        print('DEDUP: earlier receipts with same file_hash as id=%s: %s' % (latest[0], dups))
    else:
        print('DEDUP: latest receipt has no file_hash')
con.close()
PYEOF
echo '===== DONE9 ====='