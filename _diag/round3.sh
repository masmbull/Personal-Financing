cd /opt/finance
echo '===== L. .ENV FIELD PRESENCE (counts only, no values) ====='
echo -n 'RECEIPT_AI_ENABLED=true lines: '; grep -cE '^RECEIPT_AI_ENABLED=true' .env || true
echo -n 'RECEIPT_AI_PROVIDER=gemini lines: '; grep -cE '^RECEIPT_AI_PROVIDER=gemini' .env || true
echo -n 'GEMINI_API_KEY non-empty lines: '; grep -cE '^GEMINI_API_KEY=.+' .env || true
echo -n 'GEMINI_MODEL=gemini-2.5-flash lines: '; grep -cE '^GEMINI_MODEL=gemini-2.5-flash' .env || true
echo -n 'OPENAI_API_KEY non-empty lines: '; grep -cE '^OPENAI_API_KEY=.+' .env || true
echo '===== M. RUNTIME CONFIG VIA python3.11 (fresh import, same as workers) ====='
venv/bin/python3.11 - <<'PYEOF'
import traceback
try:
    import app.config as c
    s = c.settings
    print('provider:', s.RECEIPT_AI_PROVIDER)
    print('enabled:', s.RECEIPT_AI_ENABLED)
    print('gemini_model:', s.GEMINI_MODEL)
    print('gemini_base_url:', s.GEMINI_BASE_URL)
    print('GEMINI_API_KEY_set:', bool(s.GEMINI_API_KEY))
    print('OPENAI_API_KEY_set:', bool(s.OPENAI_API_KEY))
    import app.services.receipt_ocr as o
    sc = o.build_scanner()
    def names(n):
        out = [getattr(n, 'name', type(n).__name__)]
        i = getattr(n, 'inner', None)
        if i is not None: out += names(i)
        for e in getattr(n, 'engines', None) or []: out += names(e)
        return out
    print('chain:', ' > '.join(names(sc)))
except Exception:
    traceback.print_exc()
PYEOF
echo '===== N. RECEIPT ROWS NOW ====='
venv/bin/python3.11 - <<'PYEOF'
import sqlite3
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
print('rows:', con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0])
print('ids:', [r[0] for r in con.execute('SELECT id FROM receipts ORDER BY id')])
try:
    print('seq:', con.execute("SELECT * FROM sqlite_sequence WHERE name='receipts'").fetchall())
except Exception as e:
    print('seq: n/a')
PYEOF
echo '===== O. JOURNAL 08:43:20-08:45:30 FULL (all lines) ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:43:20' --until '2026-09-10 08:45:30' 2>/dev/null
echo '===== P. HISTORIC app-log visibility ====='
echo -n 'receipt-scan-started lines in ALL journal: '
sudo -n journalctl -u finance --no-pager 2>/dev/null | grep -ac 'receipt scan started' || true
echo -n 'cloud-provider lines in ALL journal: '
sudo -n journalctl -u finance --no-pager 2>/dev/null | grep -ac 'cloud provider' || true
echo '===== DONE3 ====='