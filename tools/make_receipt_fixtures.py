"""Generate deterministic Indonesian receipt fixtures + ground truth.

Produces tests/fixtures/receipts/<name>/{image.png,expected.json} using only
PIL (no model needed). Each fixture is a synthetically rendered receipt whose
ground truth is known exactly, so the benchmark harness can score extraction
accuracy. Fixtures are committed so the benchmark is reproducible offline.

Run:  python tools/make_receipt_fixtures.py
"""
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "receipts"
OUT.mkdir(parents=True, exist_ok=True)


def _font(size=18):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _render(lines, path, width=420, rotate=0.0, light=1.0, font_size=18):
    font = _font(font_size)
    tmp = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(tmp)
    line_h = max((d.textbbox((0, 0), l, font=font)[3] -
                  d.textbbox((0, 0), l, font=font)[1]) for l in lines) + 6
    img = Image.new("RGB", (width, line_h * len(lines) + 24), "white")
    d = ImageDraw.Draw(img)
    y = 12
    for l in lines:
        d.text((12, y), l, fill="black", font=font)
        y += line_h
    if light != 1.0:
        from PIL import ImageEnhance
        img = ImageEnhance.Brightness(img).enhance(light)
    if rotate:
        img = img.rotate(rotate, expand=False, fillcolor="white")
    img.save(path, format="PNG")


def write(name, lines, expected, **kw):
    d = OUT / name
    d.mkdir(exist_ok=True)
    _render(lines, d / "image.png", **kw)
    with open(d / "expected.json", "w", encoding="utf-8") as f:
        json.dump(expected, f, ensure_ascii=False, indent=2)


# 1) Thermal minimarket
write("minimarket_thermal", [
    "INDOMARET", "Jl. Mawar No 1 Telp 021-5551234",
    "No. Struk : AB12345  31/08/2026 14:22",
    "AQUA 600ML        1   3.000   3.000",
    "INDOMIE GOR AYAM  2   3.500   7.000",
    "SABUN MANDI       1   5.000   5.000",
    "SUBTOTAL         15.000", "TUNAI            20.000", "KEMBALI          5.000",
    "TERIMA KASIH",
], {"merchant": "INDOMARET", "date": "2026-08-31", "time": "14:22",
    "total_amount": 15000, "subtotal": 15000, "payment_method": "TUNAI",
    "items_count": 3, "items_total": 15000, "document_type": "MINIMARKET_RECEIPT",
    "merchant_address": "Mawar No 1", "receipt_number": "AB12345"})

# 2) Supermarket with PPN + discount
write("supermarket_ppn_discount", [
    "SUPERINDO", "PAJAK  : PPN",
    "SUSU UHT 1L      2  12.500  25.000",
    "BERAS 5KG        1  60.000  60.000",
    "SUBTOTAL        85.000", "DISCOUNT        -5.000",
    "PPN (11%)        8.800", "TOTAL           88.800",
    "KARTU DEBIT     88.800",
], {"merchant": "SUPERINDO", "total_amount": 88800, "subtotal": 85000,
    "tax": 8800, "discount": 5000, "payment_method": "DEBIT",
    "items_count": 2, "items_total": 85000, "document_type": "SUPERMARKET_RECEIPT"})

# 3) Restaurant with service charge
write("restaurant_service", [
    "WARUNG BU SRI", "Meja 5",
    "NASI GORENG     1  18.000  18.000",
    "ES TEH          2   5.000  10.000",
    "SUBTOTAL       28.000", "SERVICE CHRG  10%  2.800",
    "TOTAL          30.800", "QRIS           30.800",
], {"merchant": "WARUNG BU SRI", "total_amount": 30800, "subtotal": 28000,
    "service_charge": 2800, "payment_method": "QRIS",
    "items_count": 2, "items_total": 28000, "document_type": "RESTAURANT_RECEIPT"})

# 4) Cafe
write("cafe", [
    "KOPI KENANGAN", "LATTE HANGAT   1  25.000  25.000",
    "ROTBAKAR       1  15.000  15.000",
    "SUBTOTAL      40.000", "GOPAY         40.000",
], {"merchant": "KOPI KENANGAN", "total_amount": 40000, "subtotal": 40000,
    "payment_method": "E_WALLET", "payment_provider": "GOPAY",
    "items_count": 2, "items_total": 40000, "document_type": "CAFE_RECEIPT"})

# 5) SPBU fuel
write("spbu_fuel", [
    "SPBU PERTAMINA 34.101", "Jl. Raya No 2",
    "PERTAMAX    12.5 LITER  @ Rp 13.900/LITER",
    "TOTAL RP 173.750", "DEBIT  173.750",
], {"merchant": "SPBU PERTAMINA 34.101", "total_amount": 173750,
    "payment_method": "DEBIT", "document_type": "FUEL_RECEIPT",
    "fuel_product": "PERTAMAX", "fuel_brand": "PERTAMINA",
    "fuel_liters": 12.5, "fuel_ppl": 13900})

# 6) Bengkel
write("bengkel", [
    "BENGKEL MOTOR JAYA", "GANTI OLI       1  45.000  45.000",
    "FILTER OLI      1  25.000  25.000",
    "SUBTOTAL       70.000", "CASH           70.000",
], {"merchant": "BENGKEL MOTOR JAYA", "total_amount": 70000, "subtotal": 70000,
    "payment_method": "TUNAI", "items_count": 2, "items_total": 70000,
    "document_type": "WORKSHOP_RECEIPT"})

# 7) Pharmacy
write("pharmacy", [
    "APOTEK KIMIA FARMA", "PARACETAMOL     1  5.000  5.000",
    "VITAMIN C       1  12.000 12.000",
    "SUBTOTAL       17.000", "CASH           17.000",
], {"merchant": "APOTEK KIMIA FARMA", "total_amount": 17000, "subtotal": 17000,
    "payment_method": "TUNAI", "items_count": 2, "items_total": 17000,
    "document_type": "PHARMACY_RECEIPT"})

# 8) Hotel
write("hotel", [
    "HOTEL SANTIKA", "1 KAMAR x 1 MALAM  450.000",
    "SUBTOTAL      450.000", "SERVICE CHARGE  45.000",
    "TOTAL         495.000", "KREDIT        495.000",
], {"merchant": "HOTEL SANTIKA", "total_amount": 495000, "subtotal": 450000,
    "service_charge": 45000, "payment_method": "KREDIT",
    "items_count": 1, "items_total": 450000, "document_type": "HOTEL_RECEIPT"})

# 9) Parking
write("parking", [
    "KARCIS PARKIR MOTOR", "RODA 2  1x  5.000",
    "TOTAL  5.000", "CASH   5.000",
], {"merchant": "KARCIS PARKIR MOTOR", "total_amount": 5000,
    "payment_method": "TUNAI", "items_count": 1, "items_total": 5000,
    "document_type": "PARKING_RECEIPT"})

# 10) QRIS payment confirmation
write("qris_payment", [
    "QRIS", "NMID: ID1026000123456", "MERCHANT WARUNG X",
    "REF 20260908ABC", "STATUS: BERHASIL", "RP 30.800",
], {"total_amount": 30800, "payment_method": "QRIS",
    "document_type": "QRIS_PAYMENT_RECEIPT", "qris_merchant_id": "ID1026000123456",
    "qris_reference": "20260908ABC"})

# 11) E-wallet top-up
write("ewallet_topup", [
    "TOP UP GO SALDO", "SALDO GO  100.000",
    "TOTAL  100.000", "CASH 100.000",
], {"merchant": "TOP UP GO SALDO", "total_amount": 100000,
    "payment_method": "TUNAI", "document_type": "E_WALLET_RECEIPT"})

# 12) E-commerce / marketplace
write("marketplace", [
    "TOKOPEDIA", "ORDER ID INV/2026/001",
    "SEPATU SPORT    1  250.000  250.000",
    "SUBTOTAL       250.000", "VOUCHER        -20.000",
    "ONGKIR          12.000", "TOTAL         242.000",
], {"merchant": "TOKOPEDIA", "total_amount": 242000, "subtotal": 250000,
    "discount": 20000, "delivery_fee": 12000, "items_count": 1,
    "items_total": 250000, "document_type": "E_COMMERCE_RECEIPT"})

# 13) Long receipt
long_items = [f"PRODUK-{i:02d}  1  {1000+i*100:>6}  {1000+i*100:>6}" for i in range(1, 16)]
write("long_receipt", ["MINIMARKET XYZ"] + long_items +
      [f"SUBTOTAL  {sum(1000+i*100 for i in range(1,16))}", "TUNAI  100.000",
       "KEMBALI  X"], {"merchant": "MINIMARKET XYZ", "items_count": 15,
    "document_type": "MINIMARKET_RECEIPT"})

# 14) Low-light (simulated dimmer)
write("low_light", [
    "INDOMARET", "AQUA 600ML  1  3.000  3.000",
    "TOTAL  3.000", "TUNAI  5.000", "KEMBALI 2.000",
], {"merchant": "INDOMARET", "total_amount": 3000, "subtotal": 3000,
    "payment_method": "TUNAI", "items_count": 1, "items_total": 3000,
    "document_type": "MINIMARKET_RECEIPT"}, light=0.55)

# 15) Skewed
write("skewed", [
    "WARUNG PADANG", "NASI RENDANG  1  35.000  35.000",
    "TOTAL  35.000", "CASH  50.000", "KEMBALI 15.000",
], {"merchant": "WARUNG PADANG", "total_amount": 35000, "subtotal": 35000,
    "payment_method": "TUNAI", "items_count": 1, "items_total": 35000,
    "document_type": "RESTAURANT_RECEIPT"}, rotate=3.0)

print("Fixtures written to", OUT)

