"""Repro: GET /receipts 500 after deleting one receipt."""
import io

from PIL import Image, ImageDraw


def _jpeg_bytes(text: str) -> bytes:
    img = Image.new("RGB", (400, 800), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), text, fill=(0, 0, 0))
    draw.text((50, 150), "Total Belanja   9400", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _upload_and_wait(client, text: str) -> int:
    from tests.test_ui import _wait_ocr
    r = client.post("/receipts/upload",
                    files={"file": ("repro.jpg", _jpeg_bytes(text), "image/jpeg")},
                    follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    rid = int(r.headers["location"].split("?")[0].rsplit("/", 1)[-1])
    _wait_ocr(rid)
    return rid


def test_list_ok_after_delete(client):
    rid1 = _upload_and_wait(client, "REPRO ONE")
    rid2 = _upload_and_wait(client, "REPRO TWO")

    lst = client.get("/receipts")
    assert lst.status_code == 200, f"pre-delete list broke: {lst.status_code}"

    d = client.post(f"/receipts/{rid1}/delete", follow_redirects=False)
    assert d.status_code == 303, f"delete failed: {d.status_code} {d.text[:300]}"

    lst = client.get("/receipts")
    assert lst.status_code == 200, f"POST-DELETE LIST 500: {lst.status_code}\n{lst.text[:800]}"


def test_list_ok_after_delete_confirmed(client):
    from tests.test_ui import get_test_db
    rid = _upload_and_wait(client, "REPRO CONFIRMED")
    db = get_test_db()
    from app.models.models import Account, Category
    acc = db.query(Account).first()
    cat = db.query(Category).first()
    acc_id, cat_id = acc.id, cat.id
    db.close()
    c = client.post(f"/receipts/{rid}/confirm",
                    data={"type": "EXPENSE", "amount": "9400", "date": "2026-09-12",
                          "account_id": str(acc_id), "category_id": str(cat_id),
                          "merchant": "REPRO", "description": ""},
                    follow_redirects=False)
    assert c.status_code == 303, f"confirm failed: {c.status_code} {c.text[:300]}"

    d = client.post(f"/receipts/{rid}/delete", follow_redirects=False)
    assert d.status_code == 303, f"delete confirmed failed: {d.status_code}"

    lst = client.get("/receipts")
    assert lst.status_code == 200, f"POST-DELETE-CONFIRMED LIST 500: {lst.status_code}\n{lst.text[:800]}"
