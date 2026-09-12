cd /opt/finance
echo '===== CONTROL: malformed (=gemini-3.6-flash) vs corrected (gemini-3.6-flash) via CloudReceiptScannerService' =
venv/bin/python3.11 -u - <<'PYEOF'
import json, os, sqlite3, time
from app.services.receipt_ai import GeminiVisionProvider, _image_to_b64
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
p = con.execute('SELECT stored_path FROM receipts WHERE id=7').fetchone()[0]
con.close()
b64 = _image_to_b64(p)

def run(tag, model, payload_src=None):
    prov = GeminiVisionProvider()
    prov.model = model
    import httpx
    from app.services.receipt_ai import _build_payload
    url = prov.base_url + '/chat/completions'
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=prov.timeout) as c:
            r = c.post(url, json=_build_payload(b64, model), headers=prov._headers(prov.api_key))
        dt = time.monotonic() - t0
        print('[%s] model=%r | HTTP %s | %.2fs' % (tag, model, r.status_code, dt))
        if r.status_code != 200:
            print('   body snippet:', r.text[:220].replace('\n', ' '))
    except Exception as e:
        print('[%s] exception: %s (%.2fs)' % (tag, type(e).__name__, time.monotonic() - t0))

run('A-MALFORMED  ', '=gemini-3.6-flash')
run('B-CORRECTED  ', 'gemini-3.6-flash')
run('C-NO-PREFIX-2', 'gemini-3.6-flash')
PYEOF
echo '===== DONE12 ====='