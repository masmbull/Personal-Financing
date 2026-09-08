"""Indonesian receipt extraction benchmark.

Scores a scanner against the committed fixtures in tests/fixtures/receipts
(ground truth in each fixture's expected.json). Two modes:

  --engine tesseract   (default, offline) runs the Tesseract path.
  --engine ollama      (requires live Ollama + moondream) runs Vision.

Most-important-first metrics: TOTAL exact > DATE exact > MERCHANT accuracy
> ITEM accuracy > hallucination rate. A wrong total matters more than a
missing optional field.

Run:  python tools/receipt_benchmark.py --engine tesseract
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures" / "receipts"


def _norm(s):
    return "".join(c for c in (s or "").upper() if c.isalnum())


def score_fixture(result, expected, counts):
    if result.status != "processed":
        counts["failed"] += 1
        return
    counts["processed"] += 1

    # TOTAL exact (most important)
    if result.total_amount == expected.get("total_amount"):
        counts["total_match"] += 1
    # DATE exact
    if result.date == expected.get("date"):
        counts["date_match"] += 1
    # MERCHANT accuracy (normalized alphanumerics)
    if _norm(result.merchant) == _norm(expected.get("merchant")):
        counts["merchant_match"] += 1
    elif expected.get("merchant") and _norm(expected["merchant"]) in _norm(
            result.merchant):
        counts["merchant_match"] += 1
    # ITEM count + sum accuracy
    exp_n = expected.get("items_count")
    if exp_n is not None:
        if len(result.items or []) == exp_n:
            counts["item_count_match"] += 1
        got_sum = sum(i.total_price or 0 for i in (result.items or []))
        if got_sum == expected.get("items_total"):
            counts["item_sum_match"] += 1
    # Hallucination: a monetary field populated when ground truth is None
    for field in ("tax", "service_charge", "delivery_fee"):
        if expected.get(field) is None and getattr(result, field):
            counts["hallucinations"] += 1


def run(engine):
    from app.services.receipt_ocr import (  # noqa: F401
        build_scanner, get_scanner, set_scanner,
        TesseractReceiptScannerService, parse_receipt_text,
    )

    fixtures = sorted(p for p in FIXTURES.iterdir() if p.is_dir()) \
        if FIXTURES.exists() else []
    if not fixtures:
        print("No fixtures. Run tools/make_receipt_fixtures.py first.")
        return

    counts = dict(processed=0, failed=0, total_match=0, date_match=0,
                  merchant_match=0, item_count_match=0, item_sum_match=0,
                  hallucinations=0)

    # Tesseract path: single-pass OCR -> deterministic engine.
    use_vision = (engine == "ollama")
    t0 = time.time()
    for fx in fixtures:
        img = fx / "image.png"
        exp = json.loads((fx / "expected.json").read_text(encoding="utf-8"))
        if use_vision:
            svc = get_scanner()
            result = svc.scan(str(img))
        else:
            from app.services.receipt_ocr import extract_raw_text
            text = extract_raw_text(str(img))
            result = parse_receipt_text(text)
        score_fixture(result, exp, counts)
        name = fx.name
        mark = "OK" if result.status == "processed" else "FAIL"
        print(f"  [{mark}] {name}: total={result.total_amount} "
              f"merchant={result.merchant!r} items={len(result.items or [])}")

    elapsed = time.time() - t0
    n = len(fixtures)
    p = counts["processed"]
    print("\n=== BENCHMARK:", engine, "===")
    print(f"fixtures={n} processed={p} failed={counts['failed']} "
          f"time={elapsed:.1f}s ({elapsed/n:.1}s/fixture)")
    if p:
        print(f"TOTAL exact match   : {counts['total_match']}/{p}  "
              f"({counts['total_match']*100//p}%)")
        print(f"DATE  exact match   : {counts['date_match']}/{p}  "
              f"({counts['date_match']*100//p}%)")
        print(f"MERCHANT accuracy   : {counts['merchant_match']}/{p}  "
              f"({counts['merchant_match']*100//p}%)")
        print(f"ITEM count match    : {counts['item_count_match']}/{p}  "
              f"({counts['item_count_match']*100//p}%)")
        print(f"ITEM sum match      : {counts['item_sum_match']}/{p}  "
              f"({counts['item_sum_match']*100//p}%)")
        print(f"hallucination count : {counts['hallucinations']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="tesseract",
                    choices=["tesseract", "ollama"])
    run(ap.parse_args().engine)
