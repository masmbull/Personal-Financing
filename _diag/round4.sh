cd /opt/finance
echo '===== L. .ENV FIELD PRESENCE (counts only, no values) ====='
echo -n 'RECEIPT_AI_ENABLED=true lines: '; grep -cE '^RECEIPT_AI_ENABLED=true' .env || true
echo -n 'RECEIPT_AI_PROVIDER=gemini lines: '; grep -cE '^RECEIPT_AI_PROVIDER=gemini' .env || true
echo -n 'GEMINI_API_KEY non-empty lines: '; grep -cE '^GEMINI_API_KEY=.+' .env || true
echo -n 'GEMINI_MODEL=gemini-2.5-flash lines: '; grep -cE '^GEMINI_MODEL=gemini-2.5-flash' .env || true
echo -n 'OPENAI_API_KEY non-empty lines: '; grep -cE '^OPENAI_API_KEY=.+' .env || true
echo '===== M+Q+R. RUNTIME PROBES (env sourced exactly like systemd EnvironmentFile) ====='
set -a; . ./.env; set +a
venv/bin/python3.11 - <<'PYEOF'
import base64, struct, time, traceback, zlib
try:
    import app.config as c
    s = c.settings
    print('--- M. runtime config ---')
    print('provider:', s.RECEIPT_AI_PROVIDER, '| enabled:', s.RECEIPT_AI_ENABLED)
    print('gemini_model:', s.GEMINI_MODEL, '| gemini_base_url:', s.GEMINI_BASE_URL)
    print('GEMINI_API_KEY_set:', bool(s.GEMINI_API_KEY), '| len:', len(s.GEMINI_API_KEY or ''))
    print('log_level:', s.log_level)
    import app.services.receipt_ocr as o
    sc = o.build_scanner()
    def names(n):
        out = [getattr(n, 'name', type(n).__name__)]
        i = getattr(n, 'inner', None)
        if i is not None: out += names(i)
        for e in getattr(n, 'engines', None) or []: out += names(e)
        return out
    print('chain:', ' > '.join(names(sc)))

    print('--- Q. one controlled Gemini call (1x1 PNG, timed) ---')
    if s.RECEIPT_AI_PROVIDER == 'gemini' and s.GEMINI_API_KEY:
        from app.services.receipt_ai import GeminiVisionProvider
        sig = b'\x89PNG\r\n\x1a\n'
        def chunk(t, d):
            return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
        ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)
        png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b'')
        p = GeminiVisionProvider()
        print('class:', type(p).__name__)
        t0 = time.monotonic()
        try:
            data = p.extract('data:image/png;base64,' + base64.b64encode(png).decode())
            print('EXTRACT OK in %.1fs | type: %s' % (time.monotonic() - t0, type(data).__name__))
            if isinstance(data, dict):
                print('keys:', sorted(data.keys()))
        except Exception as e:
            print('EXTRACT FAILED after %.1fs | %s | %s' % (time.monotonic() - t0, type(e).__name__, str(e)[:300]))
    else:
        print('SKIP Q: provider=%r key_set=%s' % (s.RECEIPT_AI_PROVIDER, bool(s.GEMINI_API_KEY)))

    print('--- R. REAL receipt-8 image through CloudReceiptScannerService (NO db write) ---')
    import os
    p8 = 'data/receipts/2026/09/dd52c1c6204c4c36a38bc6ffe011c7dd.webp'
    print('image exists:', os.path.exists(p8), '| bytes:', os.path.getsize(p8) if os.path.exists(p8) else 0)
    from app.services.receipt_ai import CloudReceiptScannerService
    cs = CloudReceiptScannerService()
    print('engine:', cs.name)
    t0 = time.monotonic()
    try:
        res = cs.scan(p8)
        d = res.to_dict()
        print('scan done in %.1fs | status: %s | engine: %s | error: %s' % (
            time.monotonic() - t0, d.get('status'), d.get('engine'), str(d.get('error'))[:200]))
        print('merchant:', d.get('merchant'), '| date:', d.get('date'), '| total:', d.get('total_amount'))
        print('items:', len(d.get('items') or []))
        filled = sorted(k for k, v in d.items() if v not in (None, [], ''))
        print('non-empty fields:', filled[:16])
    except Exception as e:
        print('SCAN RAISED after %.1fs | %s | %s' % (time.monotonic() - t0, type(e).__name__, str(e)[:300]))
except Exception:
    traceback.print_exc()
PYEOF
echo '===== N. RECEIPT ROWS NOW ====='
venv/bin/python3.11 -c "import sqlite3; con=sqlite3.connect('file:data/finance.db?mode=ro',uri=True); print('rows:', con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]); print('ids:', [r[0] for r in con.execute('SELECT id FROM receipts ORDER BY id')])"
echo '===== O. JOURNAL 08:43:20-08:45:30 FULL ====='
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:43:20' --until '2026-09-10 08:45:30' 2>/dev/null
echo '===== P. HISTORIC app-log visibility ====='
echo -n 'receipt-scan-started lines in ALL journal: '
sudo -n journalctl -u finance --no-pager 2>/dev/null | grep -ac 'receipt scan started' || true
echo '===== DONE4 ====='