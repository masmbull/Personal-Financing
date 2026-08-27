#!/usr/bin/env python3
"""Test new OCR parser with real receipt text."""
from app.services.receipt_ocr import parse_receipt_text

text = """eV, ANUGERAH

JL.RAYA WALIKUKUN NO.9. Ss
r0aRN:03 HALIKUKUN, i Gadomanet) a
WIOCOAREN NCAT -AMA TIMUR QRS

MPNP:0025862640646000

GORANG GARENG MAGETAN
JL. BHAYANGKARA NO.68 KEL REJOSARI
KEC KAWEDANAN, KAB MAGETAN, 63382

10.05.25-12:22/3.0.26/FLO5-35372/HASAN/02

IDM KTG PLSTK IW BSR 1 \u2192 300 300
SFTX CLN MENST M-L2S 2 23300 46,600

Vo PT STX : (13,600)
POCART SWEAT Se@ML 1 7988 \u2192 7,900
You C1886 DRK ORG140 7908 \u2192 7,900
MLKITA CNDY BTES 246 5200 \u2192 5.200
ULTRA SLIM COKLAT200 6600 \u2192 6,600
ROMA WFR CHO BLS97.6 9700 (9,700
VITACIMIN STRIP 2\u2019S 2308 4,600
PISANG CAVENDISH WHL 658 24 \u2192 15,500

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
print(f"PARSED MERCHANT: {result.merchant}")
print(f"PARSED DATE:     {result.date}")
print(f"PARSED TOTAL:    {result.total_amount}")
print(f"PARSED TAX:      {result.tax}")
print(f"PARSED PAYMENT:  {result.payment_method}")
print(f"ITEM COUNT:      {len(result.items)} / ~{result.estimated_items}")
print(f"CONFIDENCE:      {result.confidence}")
print("=" * 60)
for i, item in enumerate(result.items, 1):
    print(f"  {i}. {item.name}")
    print(f"     qty={item.quantity}  up={item.unit_price}  tp={item.total_price}")
print("=" * 60)
item_sum = sum(it.total_price for it in result.items if it.total_price)
print(f"SUM ITEMS: {item_sum}  RECEIPT TOTAL: {result.total_amount}")
