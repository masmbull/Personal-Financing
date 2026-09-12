cd /opt/finance
echo '===== F. CONFIG GREP (gemini, case-insensitive) ====='
grep -ni 'gemini' app/config.py | head -8
echo '===== G. PYDANTIC SANITY (python3.11 = worker interpreter) ====='
venv/bin/python3.11 -c "import sys; print(sys.executable, sys.version.split()[0])"
venv/bin/python3.11 -c "import pydantic_settings; print('pydantic_settings', pydantic_settings.__version__)"
echo '===== H. RECEIPTS >= 9 (DB, redacted) ====='
venv/bin/python3.11 - <<'PYEOF'
import sqlite3, json
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
for row in con.execute("SELECT id, ocr_status, ocr_data, created_at, original_filename, size_bytes, file_hash FROM receipts WHERE id >= 9 ORDER BY id"):
    d = json.loads(row[2] or '{}')
    print('--- receipt', row[0], '|', row[1], '|', row[3], '|', row[4], '|', row[5], 'bytes |', (row[6] or '')[:12])
    print('   engine:', d.get('engine'), '| status:', d.get('status'), '| error:', str(d.get('error'))[:200])
    print('   merchant:', d.get('merchant'), '| total:', d.get('total_amount'), '| items:', len(d.get('items') or d.get('line_items') or []))
PYEOF
echo '===== I. JOURNAL: receipt 8 scan window (pre-env-edit runtime) ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:39:40' --until '2026-09-10 08:40:20' 2>/dev/null | grep -av 'GET /' | head -30
echo '===== J. JOURNAL: receipt 11 window (post-restart runtime) ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:43:15' --until '2026-09-10 08:45:00' 2>/dev/null | head -60
echo '===== K. ALL scan/cloud lines since 08:00 UTC ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:00' 2>/dev/null | grep -aE 'receipt scan|cloud provider' | head -40
echo '===== DONE2 ====='