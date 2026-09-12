cd /opt/finance
set -a; . ./.env; set +a
echo '===== STEP 2: DIRECT TEXT TEST ====='
venv/bin/python3.11 -u - <<'PYEOF'
import json, time
from app.config import settings
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
payload = {'model': candidate,
           'messages': [{'role': 'user', 'content': 'Reply with exactly OK'}]}
t0 = time.monotonic()
try:
    with httpx.Client(timeout=25) as c:
        r = c.post(url, json=payload, headers=head)
    print('HTTP status:', r.status_code)
    print('latency: %.2fs' % (time.monotonic() - t0))
    try:
        print('response text:', r.json()['choices'][0]['message']['content'][:200])
    except Exception:
        print('raw body:', r.text[:400])
except Exception as e:
    print('transport error:', type(e).__name__, str(e)[:200])
PYEOF