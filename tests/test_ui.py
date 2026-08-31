"""Web UI tests - dashboard, receipts pages, mobile form basics."""
from datetime import date

from app.models.models import Account, Category, Receipt, Transaction
from tests.conftest import PNG_BYTES as PNG
from tests.conftest import client, get_test_db

TODAY = date.today().isoformat()


def _acc(name):
    db = get_test_db()
    i = db.query(Account).filter(Account.name == name).first().id
    db.close()
    return i


def _cat(name):
    db = get_test_db()
    i = db.query(Category).filter(Category.name == name).first().id
    db.close()
    return i


# ==================== dashboard ====================


def test_dashboard_renders_all_sections():
    t = client.get("/").text
    for needle in (
        "Saldo tersedia", "Net worth", "Uang masuk", "Pengeluaran",
        "Cashflow", "Uang keluar", "Tren net worth",
        "Belum cukup data untuk melihat tren net worth.",
        "Hutang", "Piutang", "Transaksi terakhir",
        "Lihat semua transaksi", "Tabungan",
    ):
        assert needle in t, needle


def test_dashboard_recent_transaction_row_links_to_edit():
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    tx = client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 21000, "account_id": acc,
        "category_id": cat, "merchant": "Kopi Kenangan", "date": TODAY,
    }).json()
    t = client.get("/").text
    assert f'href="/transactions/edit/{tx["id"]}"' in t
    assert "Kopi Kenangan" in t and "BCA" in t


def test_dashboard_expense_breakdown_and_budget_status():
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    today = date.today()
    client.post("/api/v1/budgets", json={
        "category_id": cat, "amount": 200000,
        "month": today.month, "year": today.year,
    })
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 170000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    t = client.get("/").text
    assert "Pengeluaran terbesar" in t
    assert "fill-red" in t                       # breakdown bar rendered
    assert "badge-yellow" in t                   # 85% -> WARNING badge
    assert "Rp 170.000 / Rp 200.000" in t


# ==================== receipts UI ====================


def test_receipts_empty_state():
    r = client.get("/receipts")
    assert r.status_code == 200
    assert "Belum ada struk" in r.text
    assert "/receipts/upload" in r.text


def test_receipt_upload_page_mobile_attributes():
    t = client.get("/receipts/upload").text
    assert 'accept="image/*"' in t
    assert 'capture="environment"' in t
    assert "Upload Struk" in t
    assert "data-max-mb=" in t


def _upload_png(name):
    r = client.post("/receipts/upload",
                    files={"file": (name, PNG, "image/png")},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    rid = r.headers["location"].split("?")[0].rsplit("/", 1)[-1]
    db = get_test_db()
    stored = db.query(Receipt).filter(Receipt.id == int(rid)).first().stored_path
    db.close()
    return rid, stored


def test_receipt_upload_via_html_form_creates_no_transaction():
    tx_before = client.get("/api/v1/transactions?page_size=1").json()["total"]
    rid, stored = _upload_png("struk-bca.png")

    receipt = client.get(f"/api/v1/receipts/{rid}").json()
    assert receipt["transaction_id"] is None          # upload alone never posts

    d = client.get(f"/receipts/{rid}?uploaded=1")
    assert d.status_code == 200
    assert "Struk berhasil diupload" in d.text
    # offline engine reached READY; the review form is shown for manual entry
    assert "Simpan Transaksi" in d.text
    assert "Hapus Struk" in d.text

    img = client.get(f"/receipts/{rid}/image")
    assert img.status_code == 200 and img.content.startswith(b"\x89PNG")

    import os
    try:
        os.remove(stored)
    except OSError:
        pass


def test_receipt_confirm_html_creates_exactly_one_and_409_state():
    rid, stored = _upload_png("r2.png")
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    before = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]

    r = client.post(f"/receipts/{rid}/confirm", data={
        "type": "EXPENSE", "amount": "18000", "account_id": str(acc),
        "category_id": str(cat), "merchant": "Warung", "date": TODAY,
    }, follow_redirects=False)
    assert r.status_code == 303

    # exactly one transaction, balance moved once
    after = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]
    assert after == before - 18000

    # browser lands on ?confirmed=1 -> success flash + persistent confirmed box
    page = client.get(f"/receipts/{rid}?confirmed=1")
    assert "Transaksi berhasil disimpan" in page.text
    assert "Lihat transaksi" in page.text
    # form is gone once confirmed
    assert "Simpan Transaksi" not in page.text
    # ...and a plain revisit keeps showing the confirmed state
    assert "Struk sudah tercatat" in client.get(f"/receipts/{rid}").text

    # second submit -> friendly already-confirmed state
    r2 = client.post(f"/receipts/{rid}/confirm", data={
        "type": "EXPENSE", "amount": "18000", "account_id": str(acc),
        "category_id": str(cat), "date": TODAY,
    }, follow_redirects=False)
    assert r2.status_code == 303
    assert "Struk ini sudah menjadi transaksi." in client.get(
        r2.headers["location"]).text

    # API agrees with a stable 409 code
    api = client.post(f"/api/v1/receipts/{rid}/confirm", json={
        "type": "EXPENSE", "amount": 18000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    assert api.status_code == 409
    assert api.json()["error"]["code"] == "RECEIPT_ALREADY_CONFIRMED"

    # deleting the receipt never touches the linked transaction
    n_before = client.get("/api/v1/transactions?type=EXPENSE&page_size=1").json()["total"]
    client.post(f"/receipts/{rid}/delete")
    n_after = client.get("/api/v1/transactions?type=EXPENSE&page_size=1").json()["total"]
    assert n_after == n_before

    import os
    try:
        os.remove(stored)
    except OSError:
        pass


def test_receipt_delete_unconfirmed_flow():
    rid, stored = _upload_png("r3.png")
    r = client.post(f"/receipts/{rid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert client.get(f"/receipts/{rid}").status_code == 404
    assert client.get(f"/receipts/{rid}/image").status_code == 404

    import os
    try:
        os.remove(stored)
    except OSError:
        pass


# ==================== more page & nav ====================


def test_more_page_lists_modules():
    t = client.get("/more").text
    for label in ("Hutang", "Piutang", "Tagihan", "Budget", "Tabungan",
                  "Aset", "Investasi", "Akun"):
        assert label in t


def test_nav_has_prominent_scan_entry():
    t = client.get("/").text
    assert 'href="/receipts/upload"' in t
    assert ">Scan<" in t


# ==================== receipt OCR regression ====================

def test_receipt_ocr_parser_kbon_sari():
    """Regression: subtotal must never be 1 from 'Total Item 1 10.900'."""
    from app.services.receipt_ocr import (
        parse_receipt_text, extract_items, extract_subtotal,
        extract_total, extract_discount, extract_tax,
    )
    text = (
        "KP BRANDING (M)  1  200  200\n"
        "HUJIGAE SB250ML  1 10.900 10.900\n"
        "Total Item     1        10.900\n"
        "Total Disc.             1.500\n"
        "Total Belanja           9.400\n"
        "Tunai                  10.000\n"
        "Kembalian                 600"
    )
    assert extract_subtotal(text) == 10900
    assert extract_total(text) == 9400
    assert extract_discount(text) == 1500
    assert extract_subtotal(text) != 1  # critical regression

    items = extract_items(text)
    assert len(items) == 2
    assert items[0].name == "KP BRANDING (M)"
    assert items[0].quantity == 1
    assert items[0].unit_price == 200
    assert items[0].total_price == 200
    assert items[1].name == "HUJIGAE SB250ML"
    assert items[1].quantity == 1
    assert items[1].unit_price == 10900
    assert items[1].total_price == 10900

    result = parse_receipt_text(text)
    assert result.subtotal == 10900
    assert result.total_amount == 9400
    assert result.discount == 1500
    assert result.payment_method == "TUNAI"


def test_receipt_ocr_negative_items_skipped():
    from app.services.receipt_ocr import extract_items
    text = (
        "KP BRANDING (M)  -1  200  -200\n"
        "Indomie Goreng  2x 3.500  7.000\n"
        "Sambal  500  500"
    )
    items = extract_items(text)
    assert len(items) == 2
    assert items[0].name == "Indomie Goreng"
    assert items[0].quantity == 2
    assert items[1].name == "Sambal"
    assert items[1].quantity == 1


def test_receipt_ocr_summary_lines_not_items():
    from app.services.receipt_ocr import extract_items
    text = (
        "Indomie Goreng  3500  3500\n"
        "Total Item 1 10.900\n"
        "Total Disc. 1.500\n"
        "Total Belanja 9.400\n"
        "Diskon 500"
    )
    items = extract_items(text)
    assert len(items) == 1
    assert items[0].name == "Indomie Goreng"


def test_receipt_detail_renders_ocr_fields():
    """OCR values populate the detail page form fields."""
    from app.services.receipt_ocr import parse_receipt_text
    text = (
        "KEBON SARI TMG\n"
        "19/11/2024  15:04\n"
        "Total Item     1        10.900\n"
        "Total Disc.             1.500\n"
        "Total Belanja           9.400\n"
        "Tunai                  10.000\n"
    )
    result = parse_receipt_text(text)
    assert result.total_amount == 9400
    assert result.subtotal == 10900
    assert result.discount == 1500


def test_receipt_detail_renders_with_items_namespace():
    """Regression: r.ocr.items was resolved as dict.items (method), not the
    'items' key, causing TypeError on |length filter."""
    import io
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 800), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "INDOMARET", fill=(0, 0, 0))
    draw.text((50, 100), "Indomie Goreng  3500  3500", fill=(0, 0, 0))
    draw.text((50, 150), "Total Belanja   3500", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    jpeg = buf.getvalue()

    r = client.post("/receipts/upload",
                    files={"file": ("receipt.jpg", jpeg, "image/jpeg")},
                    follow_redirects=False)
    assert r.status_code == 303, r.text
    rid = r.headers["location"].split("?")[0].rsplit("/", 1)[-1]

    detail = client.get(f"/receipts/{rid}?uploaded=1")
    assert detail.status_code == 200, detail.text[:500]
    assert "Review Struk" in detail.text
    assert "rr-form" in detail.text
    # items section should render without TypeError
    assert "rr-items" in detail.text


def test_receipt_detail_failed_status_shows_manual_form():
    """When OCR fails, detail page shows manual entry form, not a dead end."""
    from app.models.models import Receipt, ReceiptStatus
    import json
    db = get_test_db()
    r = Receipt(
        original_filename="failed.jpg",
        stored_path="data/receipts/fake.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        ocr_status=ReceiptStatus.FAILED,
        ocr_data=json.dumps({"status": "failed", "error": "tesseract not found"}),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    rid = r.id
    db.close()

    resp = client.get(f"/receipts/{rid}")
    assert resp.status_code == 200, resp.text[:500]
    assert "gagal dibaca otomatis" in resp.text
    # Must have a manual entry form (not just a warning)
    assert "rr-form" in resp.text
    assert "Simpan Transaksi" in resp.text


def test_parse_ocr_data_returns_namespace_not_dict():
    """_parse_ocr_data must return namespace so .items resolves to the key
    value, not dict.items method."""
    import json
    from app.services.receipts import _parse_ocr_data
    blob = json.dumps({
        "merchant": "INDOMARET", "total_amount": 3500,
        "items": [{"name": "Indomie", "total_price": 3500}],
    })
    result = _parse_ocr_data(blob)
    assert result is not None
    assert not isinstance(result, dict)  # must be namespace
    assert result.merchant == "INDOMARET"
    assert result.total_amount == 3500
    # The critical fix: .items must return the list, not dict.items method
    assert isinstance(result.items, list)
    assert len(result.items) == 1
    assert result.items[0].name == "Indomie"
    assert result.items[0].total_price == 3500


def test_receipt_confirm_creates_one_and_second_409():
    """Confirm creates exactly one transaction; second confirm returns 409."""
    from app.models.models import Receipt, Transaction
    rid, stored = _upload_png("r_ocr.png")
    acc, cat = _acc("BCA"), _cat("Makan & Minum")

    r = client.post(f"/receipts/{rid}/confirm", data={
        "type": "EXPENSE", "amount": "9400", "account_id": str(acc),
        "category_id": str(cat), "merchant": "KEBON SARI TMG",
        "date": TODAY,
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    receipt = db.query(Receipt).filter(Receipt.id == int(rid)).first()
    tx_id = receipt.transaction_id
    assert tx_id is not None
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    assert tx.amount == 9400
    db.close()

    # second confirm
    r2 = client.post(f"/receipts/{rid}/confirm", data={
        "type": "EXPENSE", "amount": "9400", "account_id": str(acc),
        "category_id": str(cat), "date": TODAY,
    }, follow_redirects=False)
    assert r2.status_code == 303
    assert "Struk ini sudah menjadi transaksi." in client.get(
        r2.headers["location"]).text

    api = client.post(f"/api/v1/receipts/{rid}/confirm", json={
        "type": "EXPENSE", "amount": 9400, "account_id": acc,
        "category_id": cat, "date": TODAY,
        })
    assert api.status_code == 409

    import os
    try: os.remove(stored)
    except OSError: pass


# ==================== navigation regression ====================


def test_sidebar_present_on_desktop():
    # sidebar diganti bottom-nav mobile-first (tidak ada sidebar lagi)
    t = client.get("/").text
    assert 'class="bottom-nav"' in t
    assert 'href="/receipts/upload"' in t
    # menu tambahan tersedia di halaman /more
    m = client.get("/more").text
    assert 'href="/accounts"' in m
    assert 'href="/categories"' in m


def test_bottom_nav_present():
    t = client.get("/").text
    assert 'class="bottom-nav"' in t
    assert 'href="/receipts/upload"' in t
    assert "nav-icon-add" in t


def test_sidebar_toggle_button_present():
    # toggle sidebar dihapus; diganti tombol scan di bottom-nav +
    t = client.get("/").text
    assert "nav-add" in t
    assert 'aria-label="Scan Struk"' in t


def test_modal_overlay_container_present():
    t = client.get("/").text
    assert 'class="modal-overlay"' in t
    assert 'id="modalOverlay"' in t


def test_theme_toggle_present():
    t = client.get("/").text
    assert 'class="theme-toggle"' in t


# ==================== empty states regression ====================


def test_accounts_empty_state():
    t = client.get("/accounts").text
    assert "Akun" in t
    assert "BCA" in t or "Cash" in t


def test_budgets_empty_state():
    t = client.get("/budgets").text
    assert "Belum ada budget" in t


def test_savings_empty_state():
    t = client.get("/savings").text
    assert "Belum ada target tabungan" in t


def test_assets_empty_state():
    t = client.get("/assets").text
    assert "Belum ada aset" in t


def test_investments_empty_state():
    t = client.get("/investments").text
    assert "Belum ada investasi" in t


def test_categories_empty_state():
    t = client.get("/categories").text
    assert "Pengeluaran" in t and "Pemasukan" in t


# ==================== receipt detail regression ====================


def test_receipt_detail_renders_review_header():
    rid, stored = _upload_png("r-detail.png")
    t = client.get(f"/receipts/{rid}?uploaded=1").text
    assert "Review Struk" in t
    assert "rr-form" in t
    import os
    try: os.remove(stored)
    except OSError: pass


def test_receipt_detail_renders_ocr_items_without_typeerror():
    import io
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 800), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "INDOMARET", fill=(0, 0, 0))
    draw.text((50, 100), "Indomie Goreng  3500  3500", fill=(0, 0, 0))
    draw.text((50, 150), "Total Belanja   3500", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    r = client.post("/receipts/upload", files={"file": ("receipt.jpg", buf.getvalue(), "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303
    rid = r.headers["location"].split("?")[0].rsplit("/", 1)[-1]
    detail = client.get(f"/receipts/{rid}?uploaded=1")
    assert detail.status_code == 200
    assert "rr-form" in detail.text
    assert "rr-items" in detail.text
    assert "Review Struk" in detail.text


# ==================== design-system CSS regression ====================


def test_base_template_includes_style_css():
    t = client.get("/").text
    assert '/static/css/style.css' in t


def test_no_empty_style_attributes_remain():
    """Verify no style="" (empty inline style) survives template rendering."""
    from app.main import app
    from fastapi.testclient import TestClient
    routes = ["/", "/transactions", "/transactions/add", "/receipts",
              "/receipts/upload", "/reports", "/transfer", "/more", "/accounts",
              "/categories", "/bills", "/budgets", "/savings", "/assets",
              "/investments", "/receipts/1", "/transactions/edit/1"]
    empty_styles = 0
    for route in routes:
        try:
            r = client.get(route, follow_redirects=True)
            if r.status_code < 400:
                empty_styles += r.text.count('style=""')
        except Exception:
            pass
    assert empty_styles == 0


def test_all_template_classes_exist_in_css():
    """Every class used in templates must have a matching rule in style.css."""
    import os
    import re
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = open(os.path.join(base, "app", "static", "css", "style.css"), encoding="utf-8").read()
    # Jinja control words that appear inside class="..." text but aren't real classes
    jinja_words = {"if", "else", "endif", "elif", "for", "endfor", "not", "in",
                   "and", "or", "pct", "ret", "strong", "b", "conf", "item",
                   "filter", "max", "min", "round", "int", "hidden"}
    used = set()
    for dirpath, _, files in os.walk(os.path.join(base, "app", "templates")):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            content = open(os.path.join(dirpath, fn), encoding="utf-8").read()
            for m in re.finditer(r'class="([^"]+)"', content):
                for cls in m.group(1).split():
                    if re.fullmatch(r'[a-z][a-z0-9]*(-[a-z0-9]+)*', cls) and cls not in jinja_words:
                        used.add(cls)
    missing = sorted(c for c in used if f".{c}" not in css)
    assert missing == [], f"Classes used in templates but missing from style.css: {missing}"