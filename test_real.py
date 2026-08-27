#!/usr/bin/env python3
"""Regression tests for OCR parser with real Indonesian receipt text.

Run: python test_real.py
"""
import sys

from app.services.receipt_ocr import parse_receipt_text

ARROW = "\u2192"

text = f"""eV, ANUGERAH

JL.RAYA WALIKUKUN NO.9. Ss
r0aRN:03 HALIKUKUN, i Gadomanet) a
WIOCOAREN NCAT -AMA TIMUR QRS

MPNP:0025862640646000

GORANG GARENG MAGETAN
JL. BHAYANGKARA NO.68 KEL REJOSARI
KEC KAWEDANAN, KAB MAGETAN, 63382

10.05.25-12:22/3.0.26/FLO5-35372/HASAN/02

IDM KTG PLSTK IW BSR 1 {ARROW} 300 300
SFTX CLN MENST M-L2S 2 23300 46,600

Vo PT STX : (13,600)
POCART SWEAT Se@ML 1 7988 {ARROW} 7,900
You C1886 DRK ORG140 7908 {ARROW} 7,900
MLKITA CNDY BTES 246 5200 {ARROW} 5.200
ULTRA SLIM COKLAT200 6600 {ARROW} 6,600
ROMA WFR CHO BLS97.6 9700 (9,700
VITACIMIN STRIP 2'S 2308 4,600
PISANG CAVENDISH WHL 658 24 {ARROW} 15,500

TOTAL BELANJA : 98,700

TUNAE : 100,000

KEMBALI : 9,300
ANDA HEMAT : 13,600
PPN . : DPP= 73,333 PPN= 8,800
PPN DIBEBASKAN : DPP= 14,208
PPN= 1,705

HARGA JUAL : 95,500
"""

result = parse_receipt_text(text)


def _print_result():
    print(f"MERCHANT:  {result.merchant!r}")
    print(f"DATE:      {result.date!r}")
    print(f"TOTAL:     {result.total_amount!r}")
    print(f"TAX:       {result.tax!r}")
    print(f"PAYMENT:   {result.payment_method!r}")
    print(f"ITEMS:     {len(result.items)} / ~{result.estimated_items}")
    print(f"CONF:      {result.confidence!r}")
    print("=" * 60)
    for i, item in enumerate(result.items, 1):
        print(f"  {i}. {item.name!r}  qty={item.quantity} up={item.unit_price} tp={item.total_price}")
    print("=" * 60)
    item_sum = sum(it.total_price for it in result.items if it.total_price)
    print(f"SUM ITEMS: {item_sum}  RECEIPT TOTAL: {result.total_amount}")


_passed = 0
_failed = 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS {label}")
    else:
        _failed += 1
        print(f"  FAIL {label} -- {detail}")


def main():
    _print_result()
    print("\n--- Tests A-N ---")

    # A. Merchant extracted (OCR noise tolerated)
    check("A merchant", result.merchant is not None and "ANUGERAH" in result.merchant,
          f"got {result.merchant!r}")

    # B. Date parsed as ISO
    check("B date", result.date == "2025-05-10", f"got {result.date!r}")

    # C. Total amount
    check("C total", result.total_amount == 98700, f"got {result.total_amount!r}")

    # D. Tax = PPN value (1,705), NOT the DPP (73,333)
    check("D tax", result.tax == 1705, f"got {result.tax!r}")

    # E. Tax must NOT be the DPP value
    check("E tax != DPP", result.tax != 73333, f"got {result.tax!r}")

    # F. Tax must NOT be the 79939 guard value
    check("F tax != 79939", result.tax != 79939, f"got {result.tax!r}")

    # G. Payment method detected (TUNAE -> TUNAI fuzzy)
    check("G payment", result.payment_method == "TUNAI", f"got {result.payment_method!r}")

    # H. Nine items parsed
    check("H item count", len(result.items) == 9, f"got {len(result.items)}")

        # I. Estimated items ~10
    check("I estimated", result.estimated_items == 10, f"got {result.estimated_items}")

    # J. Confidence is HIGH
    check("J confidence", result.confidence == "HIGH", f"got {result.confidence!r}")

    # K. First item name
    check("K item1 name", result.items[0].name == "IDM KTG PLSTK IW BSR",
          f"got {result.items[0].name!r}")

    # L. First item qty/price
    check("L item1 qty",
          result.items[0].quantity == 1 and result.items[0].total_price == 300,
          f"got qty={result.items[0].quantity} tp={result.items[0].total_price}")

    # M. Second item qty=2, total=46600
    check("M item2 qty",
          result.items[1].quantity == 2 and result.items[1].total_price == 46600,
          f"got qty={result.items[1].quantity} tp={result.items[1].total_price}")

    # N. No negative item leaked (Vo PT STX line has (13,600) refund)
    neg_items = [it for it in result.items if (it.total_price or 0) < 0]
    check("N no neg items", len(neg_items) == 0, f"got {len(neg_items)} negative items")

    # O. Time extracted from timestamp line
    check("O time", result.time == "12:22", f"got {result.time!r}")

    # P. Third item (arrow-split) has correct values
    check("P item3 total",
          result.items[2].quantity == 1 and result.items[2].total_price == 7900,
          f"got qty={result.items[2].quantity} tp={result.items[2].total_price}")

    # Q. Item with parenthesized price skipped properly (ROMA line)
    roma = [it for it in result.items if "ROMA" in (it.name or "")]
    check("Q roma parsed", len(roma) == 1 and roma[0].total_price == 9700,
          f"got {roma[0].name if roma else None}")

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {_passed} passed, {_failed} failed (of {_passed + _failed} checks)")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
