# STANDARBENGKEL — Low-RAM Receipt Vision Runbook

ProdukSERVER: **STANDARBENGKEL** (Ubuntu, ~3.6 GiB RAM, CPU-only, no GPU).
This runbook is for the OPERATOR who has shell access to the box
(`systemctl`/`ollama`/`df`). Application code + tests live in this repo and
the docs below were updated in lockstep with the code commit for this change.

> Never expose Ollama beyond localhost (`127.0.0.1:11434` stays the only
> binding). No cloud AI, no API keys. If a step says `sudo`, run it on the
> server — nothing below is applied from the repo alone.

---

## 1. Goal

qwen2.5vl:3b pushed the box to ~99% RAM + swap pressure during inference.
Replace the *runtime default* vision model with the much lighter
**moondream:1.8b-v2-q4_K_S** and bound inference concurrency, so a single
receipt scan can never OOM/destabilize the app server. Tesseract fallback
stays intact.

## 2. Current (known-good) baseline

* Ollama running, bound to `127.0.0.1:11434`
* Finance app under systemd unit `finance.service`, served on `127.0.0.1:8000`
* App receipt chain: `Ollama -> Tesseract -> Offline` (see
  `app/services/receipt_ocr.py::build_scanner`), app-level inference lock
  preserved in `app/services/receipt_ollama.py::_ollama_lock`.
* Health endpoint: `GET http://127.0.0.1:8000/api/v1/health`

## 3. Phase A — Stop qwen inference & confirm idle RAM

```bash
ollama stop qwen2.5vl:3b   # may be a no-op if not loaded
free -h                    # record: idle_before
ollama ps                  # expect: empty
```

## 4. Phase B — Pull + first inference of moondream

```bash
ollama pull moondream:1.8b-v2-q4_K_S
ollama ps                  # model loaded after first request
free -h                    # record: loaded_idle
time ollama run moondream:1.8b-v2-q4_K_S "Reply only OK"
free -h                    # record: after_ok
```

Accept: inference completes, RSS stays far from total RAM, swap growth
controlled. If RAM still spikes toward 100%, do not enable AI in the app yet;
stop and check `OLLAMA_NUM_PARALLEL`/`OLLAMA_CONTEXT_LENGTH` (section 5).

## 5. Phase C — systemd memory safety (Ollama side)

Inspect the unit FIRST, then add a drop-in (never edit generated units):

```bash
systemctl cat ollama.service
sudo systemctl edit ollama.service
```

Drop-in content (`/etc/systemd/system/ollama.service.d/override.conf`):

```ini
[Service]
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Environment=OLLAMA_MAX_QUEUE=2
Environment=OLLAMA_KEEP_ALIVE=60s
Environment=OLLAMA_CONTEXT_LENGTH=2048
```

Apply:

```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama
systemctl status ollama --no-pager    # active
ollama ps                             # one model max, no parallel slots
curl -s http://127.0.0.1:11434/api/tags   # moondream listed
```

Notes:

* `OLLAMA_NUM_PARALLEL=1` + `OLLAMA_MAX_LOADED_MODELS=1` → serial inference,
  single resident model.
* `OLLAMA_MAX_QUEUE=2` → the 3rd concurrent request is rejected fast; the app
  treats it as a busy engine and falls through to Tesseract.
* `OLLAMA_CONTEXT_LENGTH=2048` bounds KV-cache RAM. The app also sends
  `options.num_ctx=2048` (`OLLAMA_NUM_CTX`) — keep both in sync.
## 6. Phase D — Application env (finance service)

Set on the finance unit (or its env file), DO NOT hardcode in Python:

```ini
RECEIPT_AI_ENABLED=true
RECEIPT_AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_VISION_MODEL=moondream:1.8b-v2-q4_K_S
OLLAMA_TIMEOUT_SECONDS=60
OLLAMA_NUM_CTX=2048
OLLAMA_MAX_IMAGE_BYTES=2097152
RECEIPT_AI_MAX_IMAGE_WIDTH=1280
RECEIPT_AI_JPEG_QUALITY=80
```
> `.env.example` in the repo matches this. The model name is config via env
> only; nothing in `app/` hardcodes a model.

```bash
sudo systemctl restart finance
curl -s http://127.0.0.1:8000/api/v1/health   # expect {"status":"ok",...}
```

## 7. Phase E — One real receipt through the app (acceptance)

```bash
# upload (web UI /receipts/upload or API):
#   POST /api/v1/receipts  (multipart image/jpeg)
# observe draft: merchant/total/items populated = VISION path used
# review + explicit confirm -> exactly ONE transaction
```

While scanning, from a second shell:

```bash
free -h      # record: during_inference
ollama ps    # one model, slot count stays 1
```

Then:

```bash
free -h      # record: after_inference (RAM must return down)
```

Acceptance criteria (all must hold):

| # | Check | Expected |
|---|---|---|
| A | Idle RAM after unload | back to baseline, no sustained ~99% |
| B | One vision request | no OOM, swap growth controlled |
| C | Two concurrent requests | 2nd queues or falls back — never 2 parallel inferences |
| D | `systemctl stop ollama` → scan | receipt still processed via Tesseract (fallback) |
| E | Accounting | AI never posts; confirm creates exactly one tx |

Measurement record (fill in):

```
model                    : moondream:1.8b-v2-q4_K_S
model_disk_size          : ~1.7 GB (ollama show <model>)
ram_idle_before          : ____
ram_loaded_idle          : ____
ram_during_inference     : ____
ram_after_inference      : ____
swap_increase            : ____
inference_duration       : ____ (from service access log / curl -w %{time_total})
model_load_duration      : ____ (first-request latency minus steady-state)
extraction_quality       : merchant/date/total correct? ____
```

## 8. Phase F — qwen2.5vl:3b disposition

```bash
ollama stop qwen2.5vl:3b    # unload from memory NOW (safe anytime)
ollama ps                   # confirm only moondream (or empty) resident
# after production is verified for a few days, free the disk:
#   ollama rm qwen2.5vl:3b
```
Do not `rm` until the app has been using moondream successfully in
production and acceptance is recorded.

## 9. Fallback verification (Tesseract path)

```bash
sudo systemctl stop ollama
# upload another receipt -> must still reach "ready" via Tesseract
sudo systemctl start ollama
```

## 10. Verify ollama never listens publicly

```bash
ss -tlnp | grep 11434        # must show 127.0.0.1:11434 only
sudo ufw status              # no 11434 rule
```
Also confirm port 11434 is absent from any Docker/compose/nginx/Tailscale
publish lines in this repo (`git grep -n "11434" .github deploy* docker*`).

## 11. Rollback (if ever needed)

```bash
# point the app back at qwen:
#   OLLAMA_VISION_MODEL=qwen2.5vl:3b   (finance env)
sudo systemctl restart finance
```
Moondream stays installed; nothing is deleted by a rollback.

## 12. Remaining risks

* First inference after idle unload pays model-load latency (RAM spikes once
  during load, not per token) — see `OLLAMA_KEEP_ALIVE=60s`.
* moondream is a small model: very faint/small-text receipts may OCR worse
  than qwen — that is the accepted trade-off for not OOMing a 3.6 GiB box;
  the user can always correct values in the review form.
* If swap rises on sustained load, reduce `OLLAMA_CONTEXT_LENGTH` / lower
  `RECEIPT_AI_MAX_IMAGE_WIDTH`; no code change required.