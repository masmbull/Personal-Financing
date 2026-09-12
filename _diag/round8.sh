cd /opt/finance
set -a; . ./.env; set +a
echo '===== STEP 3: DIRECT IMAGE TEST (receipt 8) ====='
venv/bin/python3.11 -u - <<'PYEOF'
import json, os, sqlite3, time
from app.config import settings
from app.services.receipt_ai import _image_to_b64
import httpx
head = {'Authorization': 'Bearer ' + settings.GEMINI_API_KEY, 'Content-Type': 'application/json'}
base = settings.GEMINI_BASE_URL.rstrip('/')
url = base + '/chat/completions'
try:
    with open('/tmp/_diag_models.json') as f:
        ids = json.load(f)
except Exception:
    ids = []
order = ['gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.8-flash',
         'gemini-2.5-flash', 'gemini-2.5-flash-lite']
candidate = next((m for m in order if m in ids), 'gemini-3.6-flash')
print('candidate:', candidate)
con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
row = con.execute("SELECT stored_path FROM receipts WHERE id=8").fetchone()
con.close()
image_path = row[0] if row else None
print('stored_path:', image_path)
print('exists:', os.path.exists(image_path), '| bytes:', os.path.getsize(image_path) if image_path and os.path.exists(image_path) else 0)
data_uri = _image_to_b64(image_path)
print('data uri prefix:', data_uri[:30], '| len:', len(data_uri))
payload = {
    'model': candidate,
    'messages': [{'role': 'user', 'content': [
        {'type': 'text',
         'text': 'Read this receipt. Return only the merchant name, '
                 'transaction date, total amount, and all visible line items.'},
        {'type': 'image_url', 'image_url': {'url': data_uri}},
    ]}],
}
t0 = time.monotonic()
try:
    with httpx.Client(timeout=25) as c:
        r = c.post(url, json=payload, headers=head)
    print('HTTP status:', r.status_code)
    print('latency: %.2fs' % (time.monotonic() - t0))
    if r.status_code == 200:
        content = r.json()['choices'][0]['message']['content']
        print('image processed: True')
        print('response:', (content or '')[:900])
    else:
        print('image processed: False')
        print('raw body:', r.text[:600])
except Exception as e:
    print('transport error:', type(e).__name__, str(e)[:200])
PYEOF