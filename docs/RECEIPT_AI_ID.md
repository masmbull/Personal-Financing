# Indonesian Receipt Understanding Engine

This document describes how Personal-Financing reads Indonesian receipts,
the official Indonesian references behind the rules, and the limits of the
system.

Production model: **moondream:1.8b-v2-q4_K_S** (CPU-only, ~3.6 GiB RAM).
Local-only Ollama at `127.0.0.1:11434`. No cloud AI. No API keys.

## 1. Goal

Make receipt recognition as accurate and *honest* as reasonably possible for
the wide variety of Indonesian receipts the app supports: supermarket,
minimarket (Indomaret/Alfamart/Alfamidi), warung, restoran, cafe, coffee
shop, SPBU fuel, bengkel, toko, apotek, hospital, hotel, parking, toll,
transport, e-commerce/marketplace screenshots, delivery, utility bills,
telco/top-up, e-wallet, QRIS and bank/terminal payment receipts — including
thermal prints, long/crumpled/poor-light/skewed photos and handwritten notes.

Classification and extraction are **informational only**. They never
determine accounting treatment — the user always picks the category, and
**AI never creates a transaction**. Only the explicit review+confirm step
posts, exactly once.

## 2. Architecture (no redesign of accounting)

```
uploaded receipt
  -> image validation / MIME / size / decode / path containment / SHA-256
  -> ReceiptScannerService (abstraction, unchanged)
  -> Ollama Vision (moondream, one-at-a-time inference lock)
  -> single-pass deterministic Indonesian engine   <-- this document
  -> [if Vision fails] Tesseract OCR + same engine
  -> [if Tesseract fails] Offline/manual placeholder
  -> structured draft (never auto-posting)
  -> user review / edit
  -> explicit confirmation -> transaction
```

The deterministic engine (`app/services/receipt_id.py`) is the only new
logic layer. It normalizes, classifies, reconciles and scores confidence —
it never calls a model and never invents values.

### Hybrid Vision + OCR

Vision understands layout/merchant/items/totals. Tesseract recovers raw
text and tiny/long-receipt text. When both are available their totals are
cross-checked:

- **agree** → `total_amount` confidence increases;
- **conflict** → warning `TOTAL_CONFLICT`, confidence drops, the Vision value
  is **kept but flagged** for the review UI.

Conflicting values are never silently chosen or merged.

## 3. Extraction schema (backward compatible)

All pre-existing fields keep their meaning. The schema is extended additively:

```json
{
  "document_type": "MINIMARKET_RECEIPT",
  "merchant": "INDOMARET",
  "merchant_address": "Jl. ...",
  "merchant_phone": "021...",
  "receipt_number": "AB12345",
  "invoice_number": null,
  "date": "2026-08-31",
  "time": "14:22",
  "currency": "IDR",
  "subtotal": 10000, "discount": 0, "tax": 0,
  "service_charge": 0, "delivery_fee": 0, "shipping_fee": 0,
  "rounding": 0, "other_fee": 0,
  "total_amount": 10000,
  "payment_method": "TUNAI",
  "payment_provider": null,
  "qris": { "detected": false, "merchant_name": null,
            "merchant_id": null, "reference_number": null },
  "fuel":  { "detected": false, "brand": null, "product": null,
             "quantity_liters": null, "price_per_liter": null, "total": null },
  "items": [
    { "name": "AQUA 600ML", "quantity": 1, "unit": "PCS",
      "unit_price": 3000, "discount": 0, "total_price": 3000 }
  ],
  "field_confidence": { "total_amount": 0.98, "merchant": 0.93, ... },
  "confidence_score": 0.91,
  "warnings": []
}
```

`document_type` is informational (Section 4). `confidence` string
(HIGH/MEDIUM/LOW) is preserved for backward compat; `field_confidence`
and `confidence_score` are computed **server-side only** — the model never
invents them.

## 4. Document classification (informational only)

Possible `document_type` values:

```
RETAIL_RECEIPT            SUPERMARKET_RECEIPT       MINIMARKET_RECEIPT
RESTAURANT_RECEIPT        CAFE_RECEIPT              FUEL_RECEIPT
WORKSHOP_RECEIPT          PHARMACY_RECEIPT          HOSPITAL_RECEIPT
HOTEL_RECEIPT             PARKING_RECEIPT           TOLL_RECEIPT
TRANSPORT_RECEIPT         UTILITY_RECEIPT           TELCO_RECEIPT
E_COMMERCE_RECEIPT        DELIVERY_RECEIPT          QRIS_PAYMENT_RECEIPT
BANK_PAYMENT_RECEIPT      E_WALLET_RECEIPT          OTHER_RECEIPT
UNKNOWN
```

A QRIS payment *confirmation* (no purchased items) is classified
`QRIS_PAYMENT_RECEIPT`; a retail receipt merely **paid with QRIS** keeps its
merchant class with `qris.detected=true`. Classification never drives
accounting.

## 5. Indonesian terminology recognized

Totals/labels: Subtotal, Sub Total, Jumlah, Total, Grand Total, Total
Belanja, Total Pembayaran, Bayar, Tunai, Cash, Kembalian, Kembali, Diskon,
Discount, Potongan, PPN, Pajak, Tax, Service, Service Charge, Biaya
Layanan, Biaya Admin, Ongkir, Pengiriman, Pembulatan, Dibayar, Terima Kasih.

Payment methods: Tunai, Cash, Debit, Kartu Debit, Kartu Kredit, Credit Card,
QRIS, GoPay, OVO, DANA, ShopeePay, LinkAja, Virtual Account, Transfer, EDC.

Fuel (official operator naming, prices never hardcoded): Pertalite, Pertamax,
Pertamax Turbo, Pertamina Dex, Dexlite, Solar, Bio Solar, RON 90/92/95/98;
brands Pertamina, Shell, BP, Vivo.

## 6. Critical money rules

Indonesian receipts use dots as thousands separators:

```
"12.500"   -> 12500
"125.000"  -> 125000
"1.250.000"-> 1250000
```

These are **never** interpreted as decimals. Values are integer rupiah, never
floating point. Missing digits are never invented. Explicit decimals the
integer schema cannot represent yield `null` + a warning. Uncertain money →
`null` + warning, never a guess.

## 7. Total reconciliation

The engine checks `subtotal - discount + tax + service_charge + delivery +
shipping + other_fee + rounding ≈ total` (small rounding tolerance). Item
sums are compared against the subtotal. Conflicts produce warnings, never a
silent choice:

- `TOTAL_MISMATCH` — components don't add up to the printed total.
- `ITEM_SUM_MISMATCH` — item sums disagree with the subtotal.
- `TOTAL_CONFLICT` — Vision and Tesseract totals disagree.

Affected fields get lower confidence and the review UI receives the warning.

## 8. QRIS handling (Bank Indonesia policy)

QRIS is a **payment standard**, not the user's payment application. The engine
never converts `QRIS -> GoPay`/`OVO`/etc. unless that provider name is
actually visible. Detected fields: merchant name, NMID (`merchant_id`),
reference number — each only when the printed pattern is present.

## 9. Anti-hallucination policy

**"If it is not visible, return null."** The model reads the document; it does
not reconstruct what the receipt "should" say. Never fabricate item prices,
receipt numbers, dates, tax, payment providers, merchants or quantities.
Product-name abbreviations are copied as printed (`"INDM GY"` stays
`"INDM GY"`). Merchant identity is the visible text, never the cashier or
payment provider.

## 10. Normalization (deterministic only)

Safe: `" Rp 12.500 " -> 12500`, `"12.500" -> 12500` when clearly monetary,
Indonesian date formats -> ISO, payment-term synonyms -> canonical method.

Unsafe (never done): inventing missing digits, expanding abbreviations,
guessing merchant/payment provider/tax/quantity.

## 11. Indonesian category mapping (BPS framework)

If category suggestion is enabled, mapping uses the BPS household-consumption
classification as its reference framework: makanan/minuman,
pakaian/alas kaki, perumahan/utilitas, perabot/perlengkapan rumah tangga,
kesehatan, transportasi, informasi/komunikasi, jasa keuangan/asuransi,
rekreasi/olahraga/budaya, pendidikan, restoran/hotel, and other relevant
groups. Suggestions never overwrite a user-selected category and never
auto-create categories.

Suggestions never overwrite a user-selected category and never
auto-create categories.

## 12. Official Indonesian references (source registry)

All domain interpretation prioritizes official Indonesian sources. Verified
2026-09-08 unless noted.

| Source | URL | Supports | Status |
|---|---|---|---|
| Bank Indonesia (BI) - Sistem Pembayaran | https://www.bi.go.id/id/fungsi-utama/pengaturan/sistem-pembayaran/ | QRIS as national QR payment standard; payment-system terminology | Main page reachable; deep QRIS pages are JS-gated (404 to scripted clients) |
| Otoritas Jasa Keuangan (OJK) | https://www.ojk.go.id/id/ | Financial-institution / payment / banking terminology | Verified |
| Direktorat Jenderal Pajak (DJP) | https://www.pajak.go.id/ | PPN (value-added tax) and tax terminology | Verified |
| Badan Pusat Statistik (BPS) | https://www.bps.go.id/ | Household consumption / expenditure classification (category mapping) | 403 to scripted clients; referenced as the classification framework |
| Pertamina (BBM products) | https://www.pertamina.com/id/produk-dan-layanan | Official fuel product naming (Pertalite/Pertamax/Dexlite/Solar/...) | Verified |

Do not use random blogs as authoritative references, and do not use foreign
receipt schemas as the primary Indonesian domain reference.

## 13. Validation pipeline (after model response)

1. JSON parse 2. schema validation 3. money validation 4. date validation
5. payment-method normalization 6. amount bounds 7. item arithmetic
8. subtotal reconciliation 9. total reconciliation 10. OCR cross-check
11. confidence calculation 12. warnings generation.

Invalid output → Tesseract fallback.

## 14. Benchmark methodology

Fixtures cover: thermal minimarket, supermarket, restaurant, cafe, SPBU,
bengkel, pharmacy, hotel, parking, QRIS, e-wallet, marketplace screenshot,
long receipt, low-light photo, skewed/crumpled/faded receipt, tiny text,
discount, PPN, service charge, multiple payment lines. Per-fixture metrics:
merchant (exact/normalized), date, total exact match, subtotal, tax,
discount, payment method, item count/amount accuracy, JSON validity,
hallucination count, warning correctness. Ranked importance: **TOTAL exact
match > DATE exact match > MERCHANT accuracy > ITEM accuracy > hallucination
rate**. A wrong total is more serious than a missing optional field. Changes
require baseline-vs-new comparison plus memory/time impact (current baseline:
moondream:1.8b-v2-q4_K_S).

## 15. Production safety

Never auto-post transactions, expose Ollama, send receipts to cloud, log
images/base64, or bypass review/ownership/amount validation. Fallback order
is always **Ollama → Tesseract → Offline**.

## 16. Known limitations

- moondream is a small model: faint/tiny/handwritten text may OCR worse than
  larger models — accepted trade-off for not OOMing a 3.6 GiB CPU box.
- First inference after idle pays model-load latency
  (`OLLAMA_KEEP_ALIVE=60s`).
- Very long receipts are processed whole (no cropping); if a future model
  needs it, overlapping vertical tiles with 10-15% overlap are the designed
  path.
- Swap under sustained load: reduce `OLLAMA_CONTEXT_LENGTH` /
  `RECEIPT_AI_MAX_IMAGE_WIDTH` (no code change).

Do **not** claim "accurate for all receipts" — report actual benchmark
results honestly.