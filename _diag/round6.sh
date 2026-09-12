cd /opt/finance
set -a; . ./.env; set +a
echo '===== STEP 1: MODEL DISCOVERY (key not printed) ====='
venv/bin/python3.11 - <<'PYEOF'
import httpx, json, time
from app.config import settings
try:
    from app.services.receipt_ai import _image_to_b64
    HAVE_B64 = True
except Exception as e:
    HAVE_B64 = False
head = {'Authorization': 'Bearer ' + settings.GEMINI_API_KEY}
base = settings.GEMINI_BASE_URL.rstrip('/')
want = ['gemini-3.6-flash', 'gemini-3.7-flash', 'gemini-3.8-flash',
        'gemini-2.5-flash', 'gemini-2.5-flash-lite']
t0 = time.monotonic()
with httpx.Client(timeout=20) as c:
    r = c.get(base + '/models', headers=head)
dt = time.monotonic() - t0
print('GET /models status:', r.status_code, '| latency: %.2fs' % dt)
ids = []
if r.status_code == 200:
    raw = r.json().get('data', [])
    ids = [(m.get('id') or '').replace('models/', '') for m in raw]
    ids = [i for i in ids if i]
    print('total models returned:', len(ids))
else:
    print('BODY:', r.text[:300])
for w in want:
    exact = [i for i in ids if i == w]
    contains = [i for i in ids if w.split('-flash')[0] in i or w in i]
    print('  %-22s exact_available=%s matches=%s' % (w, bool(exact), contains[:4]))
allflash = [i for i in ids if 'flash' in i]
print('all *flash* IDs:')
for i in sorted(allflash):
    print('   ', i)
with open('/tmp/_diag_models.json', 'w') as f:
    json.dump(ids, f)
print('HAVE image tooling (receipt_ai):', HAVE_B64)
PYEOF
echo '===== STEP 2+3: TEXT THEN IMAGE TEST, FIRST AVAILABLE STABLE CANDIDATE ====='
venv/bin/python3.11 - <<'PYEOF'
import base64, json, time
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
candidate = next((m for m in order if m in ids), None)
print('candidate (first available in preferred order):', candidate)
if candidate is None:
    print('NO candidate in /models; trying gemini-3.6-flash directly anyway')
    candidate = 'gemini-3.6-flash'

# --- STEP 2: TEXT TEST ---
text_payload = {
    'model': candidate,
    'messages': [{'role': 'user', 'content': 'Reply with exactly OK'}],
}
t0 = time.monotonic()
try:
    with httpx.Client(timeout=30) as c:
        r = c.post(url, json=text_payload, headers=head)
    dt = time.monotonic() - t0
    print('--- TEXT TEST ---')
    print('model:', candidate)
    print('HTTP status:', r.status_code)
    print('latency: %.2fs' % dt)
    try:
        print('response text:', r.json()['choices'][0]['message']['content'][:300])
    except Exception:
        print('raw body:', r.text[:400])
except Exception as e:
    print('TEXT TEST transport error:', type(e).__name__, str(e)[:200])

# --- STEP 3: IMAGE TEST (actual receipt 8, data:image/jpeg;base64 mechanism) ---
print('--- IMAGE TEST ---')
import sqlite3
image_path = None
try:
    con = sqlite3.connect('file:data/finance.db?mode=ro', uri=True)
    row = con.execute(
        "SELECT stored_path, file_hash FROM receipts WHERE id=8").fetchone()
    if row:
        image_path, _ = row
        print('stored_path:', image_path)
    else:
        print('receipt 8 missing')
    con.close()
except Exception as e:
    print('db read error:', str(e)[:200])
if image_path:
    import os
    print('exists:', os.path.exists(image_path), '| bytes:', os.path.getsize(image_path) if os.path.exists(image_path) else 0)
    try:
        data_uri = _image_to_b64(image_path)
        print('data uri prefix:', data_uri[:30], '| len:', len(data_uri))
        img_payload = {
            'model': candidate,
            'messages': [{'role': 'user', 'content': [
                {'type': 'text',
                 'text': 'Read this receipt. Return only the merchant name, '
                         'transaction date, total amount, and all visible line items.'},
                {'type': 'image_url', 'image_url': {'url': data_uri}},
            ]}],
        }
        t0 = time.monotonic()
        with httpx.Client(timeout=60) as c:
            r = c.post(url, json=img_payload, headers=head)
        dt = time.monotonic() - t0
        print('HTTP status:', r.status_code)
        print('latency: %.2fs' % dt)
        if r.status_code == 200:
            content = r.json()['choices'][0]['message']['content']
            print('image processed: True')
            print('response:', (content or '')[:800])
        else:
            print('image processed: False')
            print('raw body:', r.text[:600])
    except Exception as e:
        print('IMAGE TEST error:', type(e).__name__, str(e)[:250])
print('===== DONE6 =====')
PYEOF