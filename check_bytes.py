"""Verify U+2019 apostrophe preservation in actual parse."""
from app.services.receipt_ocr import parse_receipt_text

APOS = chr(0x2019)
text = "eV, ANUGERAH\n\n10.05.25-12:22/3.0.26/FLO5-35372/HASAN/02\n\n" + \
       "VITACIMIN STRIP 2" + APOS + "S 2308 4,600\n\n" + \
       "TOTAL BELANJA : 98,700\n\nTUNAI : 100,000\n\nKEMBALI : 9,300\n\n" + \
       "ANDA HEMAT : 13,600\n\nPPN . : DPP= 73,333 PPN= 8,800\n\n" + \
       "HARGA JUAL : 95,500"

result = parse_receipt_text(text)
for i, item in enumerate(result.items):
    print("Item " + str(i+1) + ": " + repr(item.name))
    print("  hex: " + item.name.encode("utf-8").hex())
    if APOS in item.name:
        print("  APOS FOUND, hex=" + APOS.encode("utf-8").hex())
