#!/usr/bin/env python3
"""Debug item extraction."""
from app.services.receipt_ocr import extract_items

text = """POCART SWEAT Se@ML 1 7988 7,900
You C1886 DRK ORG140 7908 7,900
MLKITA CNDY BTES 246 5200 5.200
ULTRA SLIM COKLAT200 6600 6,600
ROMA WFR CHO BLS97.6 9700 (9,700
VITACIMIN STRIP 2'S 2308 4,600
PISANG CAVENDISH WHL 658 24 15,500"""

items = extract_items(text)
print(f'Items: {len(items)}')
for it in items:
    print(f'  {it.name} | qty={it.quantity} up={it.unit_price} tp={it.total_price}')