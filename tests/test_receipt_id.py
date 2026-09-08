"""Deterministic Indonesian receipt understanding engine - unit tests.

Covers money parsing, date normalization, payment normalization, document
classification, QRIS/fuel detection, reconciliation warnings, field
confidence, and the enrich entry point (parse_receipt_text integration).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import receipt_id as rid
from app.services.receipt_ocr import ReceiptScanResult, parse_receipt_text
from app.services.receipt_ollama import OllamaVisionReceiptScannerService


class FakeClient:
    def __init__(self, chat_result):
        self.chat_result = chat_result

    def chat(self, image_b64):
        return self.chat_result


def _result(**kw):
    return ReceiptScanResult(**kw)


# ------------------------------------------------------------- money
def test_money_thousands_dots():
    assert rid.parse_id_money("12.500") == (12500, None)
    assert rid.parse_id_money("125.000") == (125000, None)
    assert rid.parse_id_money("1.250.000") == (1250000, None)
    assert rid.parse_id_money("Rp 12.500") == (12500, None)
    assert rid.parse_id_money("Rp12.500") == (12500, None)
    assert rid.parse_id_money(" 10.900 ") == (10900, None)


def test_money_plain_and_zero_decimal():
    assert rid.parse_id_money("25000") == (25000, None)
    assert rid.parse_id_money("12.500,00") == (12500, None)
    assert rid.parse_id_money("73,333") == (73333, None)   # comma thousands
    assert rid.parse_id_money(12500) == (12500, None)


def test_money_decimals_rejected_not_guessed():
    assert rid.parse_id_money("12.500,50") == (None, "MONEY_DECIMAL_UNSUPPORTED")
    assert rid.parse_id_money("25.50") == (None, "MONEY_DECIMAL_UNSUPPORTED")
    assert rid.parse_id_money("12,50") == (None, "MONEY_DECIMAL_UNSUPPORTED")
    assert rid.parse_id_money(25000.5)[0] is None
    val, warn = rid.parse_id_money("12.5000")
    assert val is None and warn == "MONEY_AMBIGUOUS_SEPARATOR"


def test_money_nullish():
    assert rid.parse_id_money(None) == (None, None)
    assert rid.parse_id_money("") == (None, None)
    assert rid.parse_id_money(True) == (None, None)


# ------------------------------------------------------------- dates
def test_date_formats():
    assert rid.normalize_id_date("2026-08-31") == ("2026-08-31", None)
    assert rid.normalize_id_date("31/08/2026") == ("2026-08-31", None)
    assert rid.normalize_id_date("31-08-2026") == ("2026-08-31", None)
    assert rid.normalize_id_date("31.08.2026") == ("2026-08-31", None)
    assert rid.normalize_id_date("08 Sep 2026") == ("2026-09-08", None)
    assert rid.normalize_id_date("8 September 2026") == ("2026-09-08", None)
    assert rid.normalize_id_date("05/03/26") == ("2026-03-05", None)  # dd/mm/yy


def test_date_invalid_and_unconventional():
    val, warn = rid.normalize_id_date("2026-02-30")
    assert val is None and warn == "DATE_INVALID"
    val, warn = rid.normalize_id_date("09/23/2026")     # MM/DD-looking
    assert val == "2026-09-23" and warn == "DATE_MDY_INTERPRETED"
    assert rid.normalize_id_date("32/13/2026") == (None, "DATE_INVALID")
    assert rid.normalize_id_date("bukan tanggal")[1] == "DATE_UNPARSED"
    assert rid.normalize_id_date(None) == (None, None)


def test_time_normalization():
    assert rid.normalize_id_time("14:22") == ("14:22", None)
    assert rid.normalize_id_time("14.22.03") == ("14:22:03", None)
    assert rid.normalize_id_time("25:00")[1] == "TIME_INVALID"
    assert rid.normalize_id_time("1422")[1] == "TIME_UNPARSED"


# ------------------------------------------------------------- payment
def test_payment_synonyms():
    assert rid.normalize_payment_method("Tunai") == "TUNAI"
    assert rid.normalize_payment_method("CASH") == "TUNAI"
    assert rid.normalize_payment_method("Kartu Debit") == "DEBIT"
    assert rid.normalize_payment_method("Kredit") == "KREDIT"
    assert rid.normalize_payment_method("Virtual Account") == "TRANSFER"
    assert rid.normalize_payment_method("GoPay") == "E_WALLET"
    assert rid.normalize_payment_method("QRIS") == "QRIS"
    assert rid.normalize_payment_method("DEBIT") == "DEBIT"  # canonical pass-through


def test_payment_unknown_is_never_invented():
    assert rid.normalize_payment_method("BITCOIN") is None
    assert rid.normalize_payment_method(None) is None
    assert rid.normalize_payment_method("") is None


def test_provider_only_when_visible():
    assert rid.detect_payment_provider("BAYAR VIA GOPAY SUKSES") == "GOPAY"
    assert rid.detect_payment_provider("SHOPEEPAY") == "SHOPEEPAY"
    assert rid.detect_payment_provider("Pembayaran DANA") == "DANA"  # caps only
    # lowercase "dana" is the word 'funds' - must NOT become a provider
    assert rid.detect_payment_provider("pengembalian dana") is None
    assert rid.detect_payment_provider(None) is None


# ------------------------------------------------------------- classification
def test_classify_document_types():
    assert rid.classify_document(
        "INDOMARET\nSUSU 10.000\nTOTAL 10.000") == "MINIMARKET_RECEIPT"
    assert rid.classify_document(
        "SPBU PERTAMINA PERTAMAX 12.5 LITER") == "FUEL_RECEIPT"
    assert rid.classify_document("WARUNG BU SRI NASI GORENG") == "RESTAURANT_RECEIPT"
    assert rid.classify_document("KOPI KENANGAN CAFE LATTE") == "CAFE_RECEIPT"
    assert rid.classify_document("APOTEK KIMIA FARMA OBAT") == "PHARMACY_RECEIPT"
    assert rid.classify_document("HOTEL SANTika 1 MALAM") == "HOTEL_RECEIPT"
    assert rid.classify_document("KARCIS PARKIR MOTOR") == "PARKING_RECEIPT"
    assert rid.classify_document("E-TOLL GERBANG TOL") == "TOLL_RECEIPT"
    assert rid.classify_document("PLN TOKEN LISTRIK 20.000") == "UTILITY_RECEIPT"
    assert rid.classify_document("TELKOMSEL PULSA 25.000") == "TELCO_RECEIPT"
    assert rid.classify_document("BENGKEL SENTER GANTI OLI") == "WORKSHOP_RECEIPT"
    assert rid.classify_document("SHOPEE ORDER ID 123 INVOICE") == "E_COMMERCE_RECEIPT"
    assert rid.classify_document("GOFOOD ONGKIR 5.000") == "E_COMMERCE_RECEIPT" or \
        rid.classify_document("GOFOOD ONGKIR 5.000") == "DELIVERY_RECEIPT"


def test_classify_qris_slip_vs_qris_paid_retail():
    # QRIS payment confirmation (no items) -> QRIS_PAYMENT_RECEIPT
    slip = "QRIS\nMERCHANT: WARUNG X\nREF 12345AB\nSTATUS BERHASIL"
    assert rid.classify_document(slip) == "QRIS_PAYMENT_RECEIPT"
    # Retail receipt merely PAID with QRIS keeps its merchant class.
    retail = "INDOMARET\nAQUA 3.000\nTOTAL 3.000\nQRIS"
    r = _result(items=[type("I", (), {"total_price": 3000})()])
    assert rid.classify_document(retail, r) == "MINIMARKET_RECEIPT"
    assert rid.classify_document("") is None


def test_classify_unknown_text():
    assert rid.classify_document("XYZ ABC 123") == "UNKNOWN"


# ------------------------------------------------------------- qris / fuel
def test_detect_qris_fields():
    text = "QRIS BERHASIL\nNMID: ID1026000123456\nREF NO 20260908XXXX"
    q = rid.detect_qris(text, merchant="WARUNG X")
    assert q["detected"] is True
    assert q["merchant_id"] == "ID1026000123456"
    assert q["reference_number"] == "20260908XXXX"
    assert q["merchant_name"] == "WARUNG X"
    assert rid.detect_qris("struk minimarket biasa tanpa pembayaran digital")["detected"] is False
    # QRIS mention without printed NMID/ref -> detected, fields stay null
    q2 = rid.detect_qris("QRIS payment")
    assert q2["detected"] is True and q2["merchant_id"] is None


def test_detect_fuel():
    text = ("SPBU PERTAMINA 34.101\nPERTAMAX\n12.5 LITER x Rp 13.900/LITER\n"
            "TOTAL RP 173.750")
    f = rid.detect_fuel(text, total_amount=173750)
    assert f["detected"] is True
    assert f["brand"] == "PERTAMINA"
    assert f["product"] == "PERTAMAX"
    assert f["quantity_liters"] == 12.5
    assert f["price_per_liter"] == 13900
    assert f["total"] == 173750
    assert rid.detect_fuel("struk minimarket biasa")["detected"] is False


def test_fuel_prices_not_hardcoded():
    # Different visible price must be extracted as-is (never assumed).
    f = rid.detect_fuel("SPBU PERTALITE 5 LITER Rp 10.000/LITER", 50000)
    assert f["product"] == "PERTALITE" and f["price_per_liter"] == 10000


# ------------------------------------------------------------- qty/unit
def test_parse_qty_unit():
    assert rid.parse_qty_unit("2 x 5.000") == (2.0, None, 5000)
    assert rid.parse_qty_unit("2 @ 5.000") == (2.0, None, 5000)
    assert rid.parse_qty_unit("2PCS") == (2.0, "PCS", None)
    assert rid.parse_qty_unit("0.5KG") == (0.5, "KG", None)
    assert rid.parse_qty_unit("1.2 L") == (1.2, "L", None)
    assert rid.parse_qty_unit("tanpa angka") == (None, None, None)


# ------------------------------------------------------- reconciliation
def test_reconcile_consistent_receipt_no_warning():
    r = _result(total_amount=21000, subtotal=21000,
                items=[type("I", (), {"total_price": 21000})()])
    assert rid.reconcile(r) == []


def test_reconcile_total_mismatch():
    # subtotal 48.000 - 0 + tax 0 != total 50.000 -> TOTAL_MISMATCH
    r = _result(total_amount=50000, subtotal=48000)
    assert "TOTAL_MISMATCH" in rid.reconcile(r)


def test_reconcile_full_components_ok():
    r = _result(total_amount=61500, subtotal=55000, tax=6050, rounding=450)
    assert rid.reconcile(r) == []


def test_reconcile_item_sum_mismatch():
    items = [type("I", (), {"total_price": t})()
             for t in (10000, 20000, 30000)]   # sums 60000
    r = _result(total_amount=60000, subtotal=55000, items=items)
    assert "ITEM_SUM_MISMATCH" in rid.reconcile(r)


def test_reconcile_skipped_when_components_missing():
    # total present but no subtotal -> cannot reconcile, no false warning
    assert rid.reconcile(_result(total_amount=50000)) == []


def test_reconcile_ocr_conflict():
    r = _result(total_amount=125000)
    assert "TOTAL_CONFLICT" in rid.reconcile(r, ocr_total=128000)
    assert rid.reconcile(r, ocr_total=125000) == []


# ------------------------------------------------------- field confidence
def test_field_confidence_bounds_and_agreement():
    r = _result(merchant="INDOMARET", date="2026-08-31",
                total_amount=21000, subtotal=21000, payment_method="TUNAI")
    fc = rid.compute_field_confidence(r)
    assert all(0.0 <= v <= 1.0 for v in fc.values())
    assert fc["total_amount"] >= 0.85
    assert fc["merchant"] >= 0.9
    assert fc["date"] >= 0.85
    # OCR agreement raises, conflict lowers
    assert rid.compute_field_confidence(r, ocr_total=21000)["total_amount"] > \
        rid.compute_field_confidence(r)["total_amount"]
    conflict = rid.compute_field_confidence(r, ocr_total=99999)
    assert conflict["total_amount"] < 0.6


def test_field_confidence_missing_fields_are_zero():
    fc = rid.compute_field_confidence(_result())
    assert fc["merchant"] == 0.0 and fc["total_amount"] == 0.0


def test_confidence_score_weighted():
    r = _result(merchant="INDOMARET", date="2026-08-31", total_amount=21000)
    enriched = rid.enrich_scan_result(r)
    assert 0.0 < enriched.confidence_score <= 1.0


# ------------------------------------------------------- enrich integration
def test_enrich_via_parse_receipt_text_indomaret():
    text = ("INDOMARET\nJl. Mawar No 1\nNo. Struk: AB12345\n"
            "AQUA 600ML 1 3.000 3.000\nINDOMIE GOR AYAM 2 3.500 7.000\n"
            "SUBTOTAL 10.000\nTUNAI 10.000\nKEMBALI 0\n")
    res = parse_receipt_text(text)
    assert res.document_type == "MINIMARKET_RECEIPT"
    assert res.warnings is not None
    assert res.field_confidence["merchant"] > 0
    assert res.confidence_score > 0
    assert res.receipt_number == "AB12345"
    assert res.merchant_address == "Mawar No 1"
    assert res.payment_method == "TUNAI"
    assert res.qris["detected"] is False
    assert res.confidence in ("HIGH", "MEDIUM", "LOW")  # backward compat


def test_enrich_fuel_receipt_via_parse():
    text = ("SPBU PERTAMINA 34.101\nJl. Raya No 2\nPERTAMAX\n"
            "12.5 LITER @ Rp 13.900/LITER\nTOTAL RP 173.750\n")
    res = parse_receipt_text(text)
    assert res.document_type == "FUEL_RECEIPT"
    assert res.fuel["detected"] is True
    assert res.fuel["brand"] == "PERTAMINA"
    assert res.fuel["product"] == "PERTAMAX"
    assert res.fuel["total"] == res.total_amount


def test_enrich_qris_slip():
    text = ("QRIS\nMERCHANT WARUNG X\nNMID ID1026000123456\n"
            "REF 20260908ABC\nSTATUS: BERHASIL\n")
    res = parse_receipt_text(text)
    assert res.document_type == "QRIS_PAYMENT_RECEIPT"
    assert res.qris["detected"] is True
    assert res.qris["merchant_id"] == "ID1026000123456"


def test_enrich_does_not_expand_abbreviations():
    text = ("INDOMARET\nINDM GY 1 3.000 3.000\nTOTAL 3.000\n")
    res = parse_receipt_text(text)
    assert "INDM GY" in [i.name for i in res.items]


def test_enrich_date_normalization_warning():
    r = _result(merchant="TOKO X", date="31/08/2026", total_amount=5000)
    rid.enrich_scan_result(r, ocr_text="TOKO X TOTAL 5.000")
    assert r.date == "2026-08-31"
    assert "DATE_MDY_INTERPRETED" not in (r.warnings or [])
    r2 = _result(merchant="TOKO X", date="09/23/2026", total_amount=5000)
    rid.enrich_scan_result(r2, ocr_text="TOKO X TOTAL 5.000")
    assert r2.date == "2026-09-23"
    assert "DATE_MDY_INTERPRETED" in (r2.warnings or [])


def test_enrich_total_mismatch_downgrades_confidence():
    r = _result(merchant="TOKO", date="2026-08-31", total_amount=50000,
                subtotal=48000, confidence="HIGH")
    rid.enrich_scan_result(r, ocr_text="TOKO TOTAL 50.000")
    assert "TOTAL_MISMATCH" in r.warnings
    assert r.confidence == "MEDIUM"


def test_enrich_payment_normalization():
    r = _result(merchant="TOKO", total_amount=5000, payment_method="Cash")
    rid.enrich_scan_result(r, ocr_text="TOKO CASH 5.000")
    assert r.payment_method == "TUNAI"
    r2 = _result(merchant="TOKO", total_amount=5000, payment_method="QRIS")
    rid.enrich_scan_result(r2, ocr_text="TOKO QRIS 5.000")
    assert r2.payment_method == "QRIS"
    assert r2.payment_provider is None      # QRIS logo is not a provider
    assert r2.qris["detected"] is True


def test_enrich_provider_kept_only_when_visible():
    r = _result(merchant="TOKO", total_amount=5000, payment_method="QRIS",
                payment_provider="GOPAY")   # model claim, NOT visible in text
    rid.enrich_scan_result(r, ocr_text="TOKO QRIS 5.000")
    # QRIS -> provider conversion forbidden without visible provider name
    assert r.payment_provider is None


# ------------------------------------------------------- ollama scan level
def test_ollama_scan_normalizes_indonesian_outputs():
    import tempfile
    from PIL import Image
    svc = OllamaVisionReceiptScannerService(client=FakeClient(chat_result={
        "merchant": "Indomaret", "date": "31/08/2026", "time": "14.22",
        "total_amount": "12.500", "subtotal": 12500,
        "payment_method": "Tunai", "payment_provider": "GoPay",
        "document_type": "MINIMARKET_RECEIPT",
        "service_charge": 0, "rounding": -500,
        "items": [{"name": "SUSU", "quantity": 1, "unit": "PCS",
                   "unit_price": 12500, "total_price": 12500}],
    }))
    import tempfile as _t
    with _t.NamedTemporaryFile(suffix=".png", delete=False) as f:
        Image.new("RGB", (40, 40), "white").save(f, format="PNG")
        path = f.name
    res = svc.scan(path)
    assert res.status == "processed"
    assert res.date == "2026-08-31"                       # DD/MM normalized
    assert res.time == "14:22"                            # dot-time normalized
    assert res.total_amount == 12500                      # "12.500" -> 12500
    assert res.payment_method == "TUNAI"                  # Tunai -> TUNAI
    assert res.payment_provider == "GOPAY"                # whitelist-accepted
    assert res.document_type == "MINIMARKET_RECEIPT"
    assert res.service_charge == 0
    assert res.rounding == -500                           # negative rounding ok
    assert res.items[0].unit == "PCS"
    assert res.currency == "IDR"

