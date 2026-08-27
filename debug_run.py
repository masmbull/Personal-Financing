#!/usr/bin/env python3
"""Debug helper — quick interactive checks for receipt parsing."""
from app.services.receipt_ocr import parse_receipt_text, extract_items

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = """IDM KTG PLSTK IW BSR 1 \u2192 300 300
SFTX CLN MENST M-L2S 2 23300 46,600"""
    result = parse_receipt_text(text)
    print(f"merchant: {result.merchant!r}")
    print(f"total:    {result.total_amount!r}")
    print(f"tax:      {result.tax!r}")
    print(f"payment:  {result.payment_method!r}")
    print(f"items:    {len(result.items)}")
    for it in result.items:
        print(f"  {it.name!r} qty={it.quantity} up={it.unit_price} tp={it.total_price}")
