echo '===== A. DEPLOYED CODE ====='
cd /opt/finance || exit 1
git log -1 --format='%h %s (%ci)'
git status -sb | head -3
echo '--- Gemini code markers ---'
grep -n 'class GeminiVisionProvider' app/services/receipt_ai.py || echo 'MISSING GeminiVisionProvider'
grep -n 'GEMINI_MODEL = \|GEMINI_BASE_URL = ' app/config.py || echo 'MISSING GEMINI settings'
grep -n '"gemini"' app/services/receipt_ocr.py | head -4 || echo 'MISSING gemini dispatch'
grep -n 'cloud-gemini' app/services/receipt_ai.py | head -2
grep -n 'skipping engine' app/services/receipt_ocr.py | head -2
grep -n 'cloud provider failed' app/services/receipt_ai.py | head -4

echo '===== B. SERVICE / WORKERS / ENV MTIME ====='
systemctl show finance -p ActiveEnterTimestamp -p ExecMainStartTimestamp -p MainPID 2>/dev/null
pgrep -af uvicorn
PIDS=$(pgrep -f uvicorn | tr '\n' ',' | sed 's/,$//')
[ -n "$PIDS" ] && ps -o pid,lstart,etime,args -p "$PIDS" | cut -c1-140
stat -c '%y %n' /opt/finance/.env
systemctl cat finance --no-pager 2>/dev/null | grep -E 'EnvironmentFile|Environment=|ExecStart|WorkingDirectory|User='

echo '===== C. WORKER OS-ENV (redacted) ====='
for p in $PIDS; do
  echo "--- PID $p start: $(ps -o lstart= -p $p)"
  sudo -n cat /proc/$p/environ 2>/dev/null | tr '\0' '\n' | grep -E '^(RECEIPT_AI|GEMINI_|OPENAI_|OLLAMA_|DATABASE_URL)' | sed -E 's/(API_KEY|SECRET[^=]*)=.*/\1=<SET-REDACTED>/' || echo "(environ unreadable without root)"
done

echo '===== D. FRESH-IMPORT CONFIG + CHAIN (what a restarted worker loads) ====='
venv/bin/python - <<'PYEOF'
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
        if i is not None:
            out += names(i)
        for e in getattr(n, 'engines', None) or []:
            out += names(e)
        return out
    print('chain:', ' > '.join(names(sc)))
except Exception:
    traceback.print_exc()
PYEOF

echo '===== E. JOURNAL ====='
echo '--- filtered (last 70) ---'
sudo -n journalctl -u finance --no-pager -n 800 2>/dev/null | grep -aiE 'POST /receipts|gemini|cloud provider|ocr|scan|error|traceback|exception' | tail -70 || echo '(journal read failed)'
echo '--- upload window 08:38-08:45 ---'
sudo -n journalctl -u finance --no-pager --since '2026-09-10 08:38' --until '2026-09-10 08:45' 2>/dev/null | tail -50 || true
echo '--- raw tail 15 ---'
sudo -n journalctl -u finance --no-pager -n 30 2>/dev/null | tail -15 || true
echo '===== DONE ====='