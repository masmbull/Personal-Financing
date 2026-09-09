"""One-shot OCR diagnostic for the server.

Run from the app directory (where app/ lives), with the venv active:
    python diagnose_ocr.py [path_to_receipt_image]

If no image is given, it still checks config + Ollama + model match.
With an image, it runs the real scanner chain and prints the full result.
"""
import sys
import os

# Ensure the project root is importable.
HERE = os.path.dirname(os.path.abspath(__file__))
if not os.path.isdir(os.path.join(HERE, "app")):
    print("ERROR: run this script from the project root (the folder containing app/)")
    sys.exit(2)

from app.config import settings

def hr(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

hr("1. APP CONFIG")
print(f"  RECEIPT_AI_ENABLED      = {settings.RECEIPT_AI_ENABLED}")
print(f"  RECEIPT_AI_PROVIDER     = {settings.RECEIPT_AI_PROVIDER!r}")
print(f"  OLLAMA_BASE_URL         = {settings.OLLAMA_BASE_URL!r}")
print(f"  OLLAMA_VISION_MODEL     = {settings.OLLAMA_VISION_MODEL!r}")
print(f"  OLLAMA_TIMEOUT_SECONDS  = {settings.OLLAMA_TIMEOUT_SECONDS}")
print(f"  RECEIPT_AI_FALLBACK_TESSERACT = {settings.RECEIPT_AI_FALLBACK_TESSERACT}")

if not settings.RECEIPT_AI_ENABLED:
    print("\n  >>> AI IS DISABLED IN CONFIG. The scan will never use Ollama.")
    print("      Set RECEIPT_AI_ENABLED=true in your .env and restart the app.")

hr("2. OLLAMA REACHABILITY + MODEL MATCH")
try:
    import httpx
    r = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=10)
    print(f"  GET /api/tags  ->  HTTP {r.status_code}")
    if r.status_code != 200:
        print("  >>> Ollama did not answer 200. Is it running? (systemctl status ollama)")
        sys.exit(1)
    tags = r.json().get("models", [])
    names = [m.get("name") for m in tags]
    print(f"  Models Ollama reports ({len(names)}):")
    for n in names:
        marker = "  <-- EXPECTED" if n == settings.OLLAMA_VISION_MODEL else ""
        print(f"    - {n}{marker}")
    if settings.OLLAMA_VISION_MODEL in names:
        print(f"\n  >>> Model {settings.OLLAMA_VISION_MODEL!r} IS present. Good.")
    else:
        print(f"\n  >>> MODEL MISMATCH! App expects {settings.OLLAMA_VISION_MODEL!r}")
        print(f"      but Ollama only has the names above.")
        print(f"      Either pull the expected tag, or set OLLAMA_VISION_MODEL to a name above.")
except Exception as e:
    print(f"  >>> Cannot reach Ollama at {settings.OLLAMA_BASE_URL}: {e}")
    print("      Is Ollama running and bound to that address?")
    sys.exit(1)

hr("3. SCANNER CHAIN (what build_scanner() assembles)")
try:
    from app.services.receipt_ocr import build_scanner, get_scanner
    # Force a fresh build so we see current config.
    import app.services.receipt_ocr as _ocr_mod
    _ocr_mod._scanner = None
    chain = build_scanner()

    def describe(node, depth=0):
        pad = "  " + "  " * depth
        name = getattr(node, "name", type(node).__name__)
        inner = getattr(node, "inner", None)
        engines = getattr(node, "engines", None)
        print(f"{pad}- {name}  ({type(node).__name__})")
        if inner is not None:
            describe(inner, depth + 1)
        if engines:
            for e in engines:
                describe(e, depth + 1)

    describe(chain)
except Exception as e:
    print(f"  >>> Failed to build scanner: {e}")

hr("4. LIVE OLLAMA PING (via the app's OllamaClient)")
try:
    from app.services.receipt_ollama import OllamaClient
    c = OllamaClient()
    ok, reason = c.ping()
    print(f"  ping() -> available={ok}, reason={reason!r}")
    if not ok:
        print("  >>> The app's own client says Ollama/model is NOT available.")
        print("      Scans will fail and fall back to Tesseract/Offline.")
except Exception as e:
    print(f"  >>> OllamaClient.ping() raised: {e}")

# Optional: live scan with an image.
image_path = sys.argv[1] if len(sys.argv) > 1 else None
if image_path:
    hr(f"5. LIVE SCAN: {image_path}")
    if not os.path.isfile(image_path):
        print(f"  >>> File not found: {image_path}")
        sys.exit(2)
    try:
        from app.services.receipt_ocr import get_scanner as _gs
        _ocr_mod._scanner = None
        scanner = _gs()
        import time
        t0 = time.monotonic()
        result = scanner.scan(image_path)
        elapsed = time.monotonic() - t0
        print(f"  elapsed      = {elapsed:.1f}s")
        print(f"  status       = {result.status!r}")
        print(f"  engine       = {getattr(result, 'engine', None)!r}")
        print(f"  merchant     = {result.merchant!r}")
        print(f"  total_amount = {result.total_amount!r}")
        print(f"  date         = {result.date!r}")
        print(f"  confidence   = {result.confidence!r}")
        print(f"  items        = {len(result.items) if result.items else 0}")
        print(f"  error        = {result.error!r}")
        if result.status == "processed" and result.engine == "ollama":
            print("\n  >>> SUCCESS: Ollama vision read the receipt.")
        elif result.status == "failed":
            print("\n  >>> SCAN FAILED. Check the error above.")
        elif result.status == "processed":
            print(f"\n  >>> Read via fallback engine={result.engine!r}, not Ollama.")
    except Exception as e:
        print(f"  >>> Live scan raised: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\n  (No image supplied — skipping live scan. Pass a receipt image path to run one.)")

print("\nDone.")
