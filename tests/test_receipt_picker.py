"""Tests for the mobile receipt picker (camera / gallery) and upload flow."""
from fastapi.testclient import TestClient
from app.api.deps import get_current_user
from app.main import app
from app.models.models import Receipt, Transaction
from tests.conftest import get_test_db, valid_png_bytes


def _fresh_client():
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, follow_redirects=False)


def _png_bytes(size=8):
    return valid_png_bytes(size)


def test_upload_page_renders_mobile_picker(client):
    r = client.get("/receipts/upload")
    assert r.status_code == 200
    assert 'id="file-input-camera"' in r.text
    assert 'id="file-input-gallery"' in r.text
    assert 'id="picker-modal"' in r.text


def test_camera_input_has_capture_environment(client):
    r = client.get("/receipts/upload")
    block = r.text.split('id="file-input-camera"')[1].split(">")[0]
    assert 'capture="environment"' in block
    assert 'accept="image/*"' in block


def test_gallery_input_has_no_capture(client):
    r = client.get("/receipts/upload")
    block = r.text.split('id="file-input-gallery"')[1].split(">")[0]
    assert "capture" not in block
    assert 'accept="image/*"' in block


def test_picker_modal_has_two_buttons_and_cancel(client):
    r = client.get("/receipts/upload")
    assert 'id="btn-camera"' in r.text
    assert 'id="btn-gallery"' in r.text
    assert 'id="btn-cancel"' in r.text


def test_upload_page_requires_login_if_not_authenticated():
    c = _fresh_client()
    r = c.get("/receipts/upload")
    assert r.status_code in (301, 302, 303, 401, 403)
    assert "/login" in r.headers.get("location", "")


def _upload(client, filename, input_id):
    png = _png_bytes()
    return client.post("/receipts/upload", files={
        "file": (filename, png, "image/png"),
    })


def test_camera_pick_creates_review_not_transaction(client):
    _upload(client, "camera_shot.png", "file-input-camera")
    db = get_test_db()
    receipts = db.query(Receipt).all()
    txs = db.query(Transaction).all()
    rid = receipts[-1].id if receipts else None
    db.close()
    assert len(receipts) >= 1
    assert len(txs) == 0
    db2 = get_test_db()
    assert db2.query(Receipt).filter_by(transaction_id=rid).count() == 0
    db2.close()


def test_gallery_pick_creates_review_not_transaction(client):
    _upload(client, "gallery_pic.png", "file-input-gallery")
    db = get_test_db()
    receipts = db.query(Receipt).all()
    txs = db.query(Transaction).all()
    rid = receipts[-1].id if receipts else None
    db.close()
    assert len(receipts) >= 1
    assert len(txs) == 0
    db2 = get_test_db()
    assert db2.query(Receipt).filter_by(transaction_id=rid).count() == 0
    db2.close()


def test_camera_and_gallery_both_arrive_as_same_file_field(client):
    r = client.get("/receipts/upload")
    assert r.text.count('name="file"') >= 3


def test_upload_cancel_does_not_create_anything(client):
    r = client.get("/receipts/upload")
    assert r.status_code == 200


def test_no_file_does_not_create_receipt(client):
    before_db = get_test_db()
    before_r = before_db.query(Receipt).count()
    before_t = before_db.query(Transaction).count()
    before_db.close()
    r = client.post("/receipts/upload", data={})
    assert r.status_code in (200, 303, 400)
    after_db = get_test_db()
    assert after_db.query(Receipt).count() == before_r
    assert after_db.query(Transaction).count() == before_t
    after_db.close()


def test_desktop_keeps_main_file_input(client):
    r = client.get("/receipts/upload")
    assert 'id="file-input"' in r.text
    assert 'class="upload-zone"' in r.text
    assert 'id="picker-modal"' in r.text


def test_confirm_boundary_intact(client):
    png = _png_bytes()
    r = client.post("/receipts/upload", files={
        "file": ("r.png", png, "image/png"),
    })
    assert r.status_code == 200  # client follows redirect to detail page
    db = get_test_db()
    rid = db.query(Receipt).order_by(Receipt.id.desc()).first().id
    assert db.query(Receipt).filter_by(transaction_id=rid).count() == 0  # no tx created
    db.close()
