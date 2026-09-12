cd /opt/finance
echo '===== R5. 404 RESPONSE BODY ====='
set -a; . ./.env; set +a
venv/bin/python3.11 - <<'PYEOF'
import base64, struct, traceback, zlib
from app.config import settings
from app.services.receipt_ai import _build_payload
import httpx
sig = b'\x89PNG\r\n\x1a\n'
def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)
png = sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b'')
b64 = 'data:image/png;base64,' + base64.b64encode(png).decode()
url = settings.GEMINI_BASE_URL.rstrip('/') + '/chat/completions'
headers = {'Authorization': 'Bearer ' + settings.GEMINI_API_KEY, 'Content-Type': 'application/json'}
print('url:', url)
print('model:', settings.GEMINI_MODEL)
try:
    with httpx.Client(timeout=20) as c:
        r = c.post(url, json=_build_payload(b64, settings.GEMINI_MODEL), headers=headers)
    print('POST status:', r.status_code)
    print('BODY:', r.text[:800] or '(empty)')
except Exception:
    traceback.print_exc()
# model list check (read-only)
try:
    with httpx.Client(timeout=20) as c:
        r2 = c.get(settings.GEMINI_BASE_URL.rstrip('/') + '/models',
                   headers={'Authorization': 'Bearer ' + settings.GEMINI_API_KEY})
    print('GET /models status:', r2.status_code)
    if r2.status_code == 200:
        ids = [m.get('id') for m in r2.json().get('data', [])]
        flash = [i for i in ids if i and 'flash' in i]
        print('flash models:', flash[:10])
        print('gemini-2.5-flash present:', 'gemini-2.5-flash' in ids)
    else:
        print('BODY:', r2.text[:400])
except Exception:
    traceback.print_exc()
PYEOF
echo '===== DONE5 ====='