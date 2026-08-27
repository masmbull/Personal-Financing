"""REST API tests - /api/v1/*."""
from datetime import date

# Shared client/DB helpers live in tests/conftest.py
from tests.conftest import PNG_BYTES, client  # noqa: E402,F401

TODAY = date.today().isoformat()


def _acc(name):
    r = client.get("/api/v1/accounts").json()
    return next(a["id"] for a in r["items"] if a["name"] == name)


def _cat(name):
    r = client.get("/api/v1/categories").json()
    return next(c["id"] for c in r["items"] if c["name"] == name)


# ==================== health ====================


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ==================== accounts ====================


def test_account_crud():
    r = client.post("/api/v1/accounts", json={
        "name": "DANA", "type": "E_WALLET", "initial_balance": 25000,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["current_balance"] == 25000
    aid = body["id"]

    assert client.get(f"/api/v1/accounts/{aid}").status_code == 200

    r = client.put(f"/api/v1/accounts/{aid}", json={"name": "DANA Baru"})
    assert r.status_code == 200 and r.json()["name"] == "DANA Baru"

    assert client.delete(f"/api/v1/accounts/{aid}").status_code == 204

    r = client.get(f"/api/v1/accounts/{aid}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_account_delete_in_use_conflict():
    aid = _acc("BCA")
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 1000, "account_id": aid,
        "category_id": _cat("Makan & Minum"), "date": TODAY,
    })
    r = client.delete(f"/api/v1/accounts/{aid}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ACCOUNT_IN_USE"


# ==================== transactions ====================


def test_transaction_full_lifecycle():
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    r = client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 35000, "account_id": acc,
        "category_id": cat, "merchant": "Indomaret",
        "description": "Bensin", "notes": "kantor", "date": TODAY,
    })
    assert r.status_code == 201
    tx = r.json()
    assert tx["merchant"] == "Indomaret" and tx["account_name"] == "BCA"
    tid = tx["id"]

    r = client.get(f"/api/v1/transactions/{tid}")
    assert r.status_code == 200 and r.json()["amount"] == 35000
    assert client.get(f"/api/v1/accounts/{acc}").json()["current_balance"] == 965000

    r = client.put(f"/api/v1/transactions/{tid}", json={"amount": 40000})
    assert r.status_code == 200 and r.json()["amount"] == 40000
    assert client.get(f"/api/v1/accounts/{acc}").json()["current_balance"] == 960000

    body = client.get("/api/v1/transactions?page=1&page_size=10&search=Bensin").json()
    assert body["total"] == 1 and len(body["items"]) == 1
    assert {"items", "total", "page", "page_size"} <= set(body)

    assert client.get("/api/v1/transactions?merchant=indom").json()["total"] == 1
    assert client.get("/api/v1/transactions?type=INCOME").json()["total"] == 0

    assert client.delete(f"/api/v1/transactions/{tid}").status_code == 204
    assert client.get(f"/api/v1/transactions/{tid}").status_code == 404
    assert client.get(f"/api/v1/accounts/{acc}").json()["current_balance"] == 1000000


def test_transaction_validation_errors():
    acc = _acc("BCA")
    r = client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 0, "account_id": acc, "date": TODAY,
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"

    r = client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 1000, "account_id": acc,
        "date": TODAY,
    })
    assert r.status_code == 400


def test_transaction_type_is_case_insensitive():
    """Spec accepts 'income' / 'expense' in any case."""
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    r = client.post("/api/v1/transactions", json={
        "type": "income", "amount": 5000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "INCOME"


# ==================== transfers ====================


def test_transfer_moves_money_not_income():
    bca, cash = _acc("BCA"), _acc("Cash")
    before = client.get("/api/v1/dashboard").json()

    r = client.post("/api/v1/transfers", json={
        "from_account_id": bca, "to_account_id": cash,
        "amount": 500000, "date": TODAY,
        "description": "Transfer BCA ke Cash",
    })
    assert r.status_code == 201, r.text

    assert client.get(f"/api/v1/accounts/{bca}").json()["current_balance"] == 500000
    assert client.get(f"/api/v1/accounts/{cash}").json()["current_balance"] == 1000000

    after = client.get("/api/v1/dashboard").json()
    assert after["monthly_income"] == before["monthly_income"]
    assert after["monthly_expense"] == before["monthly_expense"]
    assert client.get("/api/v1/transactions?type=TRANSFER").json()["total"] == 1

    r = client.post("/api/v1/transfers", json={
        "from_account_id": bca, "to_account_id": bca, "amount": 1,
    })
    assert r.status_code == 400


# ==================== debts ====================


def test_debt_payment_reduces_and_creates_transaction():
    r = client.post("/api/v1/debts", json={
        "type": "PAYABLE", "person_name": "Budi",
        "principal_amount": 1_000_000, "due_date": "2026-12-31",
    })
    assert r.status_code == 201
    debt = r.json()
    did = debt["id"]
    assert debt["remaining_amount"] == 1_000_000
    assert debt["status"] == "OPEN"

    acc = _acc("BCA")
    before = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]

    r = client.post(f"/api/v1/debts/{did}/payments", json={
        "amount": 400000, "account_id": acc, "notes": "cicil 1",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["remaining_amount"] == 600000
    assert body["status"] == "PARTIALLY_PAID"
    assert len(body["payments"]) == 1
    assert body["payments"][0]["transaction_id"] is not None

    after = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]
    assert after == before - 400000

    r = client.post(f"/api/v1/debts/{did}/payments", json={"amount": 999999999})
    assert r.status_code == 400

    final = client.post(f"/api/v1/debts/{did}/payments", json={"amount": 600000})
    assert final.json()["status"] == "PAID"


# ==================== bills ====================


def test_bill_crud_and_pay():
    acc = _acc("BCA")
    r = client.post("/api/v1/bills", json={
        "name": "Listrik", "amount": 350000, "frequency": "MONTHLY",
        "due_day": 10, "account_id": acc,
    })
    assert r.status_code == 201
    bid = r.json()["id"]
    assert r.json()["next_due_date"] is not None

    r = client.put(f"/api/v1/bills/{bid}", json={"amount": 400000})
    assert r.json()["amount"] == 400000

    before = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]
    r = client.post(f"/api/v1/bills/{bid}/pay", json={})
    assert r.status_code == 201 and r.json()["transaction_id"] is not None
    after = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]
    assert after == before - 400000

    assert client.delete(f"/api/v1/bills/{bid}").status_code == 204


# ==================== budgets ====================


def test_budget_spent_calculation_and_status():
    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    today = date.today()
    client.post("/api/v1/budgets", json={
        "category_id": cat, "amount": 500000,
        "month": today.month, "year": today.year,
    })
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 450000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })

    row = client.get("/api/v1/budgets").json()["items"][0]
    assert row["budget_amount"] == 500000
    assert row["spent"] == 450000
    assert row["remaining"] == 50000
    assert abs(row["percentage"] - 90.0) < 0.01
    assert row["status"] == "WARNING"

    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 100000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    row = client.get("/api/v1/budgets").json()["items"][0]
    assert row["spent"] == 550000 and row["status"] == "EXCEEDED"


# ==================== savings ====================


def test_savings_goal_deposit_withdraw():
    gid = client.post("/api/v1/savings", json={
        "name": "Laptop", "target_amount": 10_000_000,
    }).json()["id"]

    body = client.post(f"/api/v1/savings/{gid}/deposit",
                       json={"amount": 2_500_000}).json()
    assert body["current_amount"] == 2_500_000
    assert abs(body["progress_percentage"] - 25.0) < 0.01

    body = client.post(f"/api/v1/savings/{gid}/withdraw",
                       json={"amount": 500_000}).json()
    assert body["current_amount"] == 2_000_000

    r = client.post(f"/api/v1/savings/{gid}/withdraw",
                    json={"amount": 99_999_999})
    assert r.status_code == 400

    # internal movements are never expenses
    dash = client.get("/api/v1/dashboard").json()
    assert dash["monthly_expense"] == 0


# ==================== assets / investments ====================


def test_assets_crud_with_gain_loss():
    aid = client.post("/api/v1/assets", json={
        "name": "Honda Beat", "asset_type": "Kendaraan",
        "current_value": 15_000_000, "purchase_value": 18_000_000,
        "purchase_date": TODAY,
    }).json()["id"]
    assert client.get("/api/v1/assets").json()["total_value"] == 15_000_000

    r = client.put(f"/api/v1/assets/{aid}", json={"current_value": 14_000_000})
    assert r.json()["gain_loss"] == -4_000_000
    assert client.delete(f"/api/v1/assets/{aid}").status_code == 204


def test_investments_crud_with_return():
    iid = client.post("/api/v1/investments", json={
        "name": "BBCA", "investment_type": "Saham",
        "amount_invested": 5_000_000, "current_value": 5_500_000,
        "purchase_date": TODAY,
    }).json()["id"]
    assert abs(client.get(
        f"/api/v1/investments/{iid}").json()["return_percentage"] - 10.0) < 0.01

    lst = client.get("/api/v1/investments").json()
    assert lst["total_invested"] == 5_000_000
    assert lst["total_current_value"] == 5_500_000
    assert lst["total_gain_loss"] == 500_000
    assert client.delete(f"/api/v1/investments/{iid}").status_code == 204


# ==================== dashboard ====================


def test_dashboard_consolidated_reflects_activity():
    acc, cat, gaji = _acc("BCA"), _cat("Makan & Minum"), _cat("Gaji")
    client.post("/api/v1/transactions", json={
        "type": "INCOME", "amount": 5_000_000, "account_id": acc,
        "category_id": gaji, "date": TODAY,
    })
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 35_000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    client.post("/api/v1/assets", json={
        "name": "Motor", "asset_type": "Kendaraan",
        "current_value": 10_000_000,
    })
    client.post("/api/v1/debts", json={
        "type": "PAYABLE", "person_name": "Cici", "principal_amount": 200_000,
    })

    d = client.get("/api/v1/dashboard").json()
    for key in ("net_worth", "total_assets", "total_liabilities",
                "available_cash", "monthly_income", "monthly_expense",
                "monthly_cashflow", "total_debt", "total_receivables",
                "budget_summary", "upcoming_bills", "recent_transactions"):
        assert key in d, key

    assert d["monthly_income"] == 5_000_000
    assert d["monthly_expense"] == 35_000
    assert d["monthly_cashflow"] == 4_965_000
    assert d["total_debt"] == 200_000
    # BCA balance after txns = 1,000,000 + 5,000,000 - 35,000 = 5,965,000
    # assets = BCA 5,965,000 + Cash 500,000 + asset record 10,000,000
    assert d["total_assets"] == 16_465_000
    assert d["available_cash"] == 6_465_000
    assert d["total_liabilities"] == 200_000
    assert d["net_worth"] == d["total_assets"] - d["total_liabilities"]
    assert len(d["recent_transactions"]) >= 2


# ==================== reports ====================


def test_reports_endpoints():
    acc, cat, gaji = _acc("BCA"), _cat("Makan & Minum"), _cat("Gaji")
    client.post("/api/v1/transactions", json={
        "type": "INCOME", "amount": 3_000_000, "account_id": acc,
        "category_id": gaji, "date": TODAY,
    })
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 300_000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })

    cf = client.get("/api/v1/reports/cash-flow").json()
    assert (cf["income"], cf["expense"], cf["net"]) == (3_000_000, 300_000, 2_700_000)

    exp = client.get("/api/v1/reports/expenses").json()
    assert exp["total"] == 300_000
    assert any(c["category_id"] == cat for c in exp["by_category"])

    assert len(client.get(
        "/api/v1/reports/income-vs-expense?months=3").json()["months"]) == 3

    nw = client.get("/api/v1/reports/net-worth").json()["current"]
    assert nw["net_worth"] == nw["total_assets"] - nw["total_liabilities"]

    cats = client.get("/api/v1/reports/categories?type=EXPENSE").json()
    assert cats["total"] == 300_000


# ==================== receipts ====================


def test_receipt_upload_validates_and_stores():
    png = PNG_BYTES
    r = client.post("/api/v1/receipts",
                    files={"file": ("struk.png", png, "image/png")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "ready"          # OCR ran synchronously (offline engine)
    assert body["ocr_status"] == "processed"
    assert body["receipt_id"] > 0
    assert body["file_hash"]
    assert body["ocr"] is not None

    r = client.post("/api/v1/receipts",
                    files={"file": ("evil.exe", b"MZ...", "application/x-msdownload")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"

    # a fake 'png' MIME with undecodable bytes is rejected by decode validation
    r = client.post("/api/v1/receipts",
                    files={"file": ("fake.png", b"\x89PNG\r\nbroken", "image/png")})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "RECEIPT_INVALID"


def test_receipt_confirm_flow_creates_exactly_one_transaction():
    png = PNG_BYTES
    rid = client.post("/api/v1/receipts",
                      files={"file": ("kwitansi.png", png, "image/png")}
                      ).json()["receipt_id"]

    # GET single shows processed/ready + unlinked
    got = client.get(f"/api/v1/receipts/{rid}").json()
    assert got["ocr_status"] == "processed"
    assert got["transaction_id"] is None

    acc, cat = _acc("BCA"), _cat("Makan & Minum")
    before = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]

    r = client.post(f"/api/v1/receipts/{rid}/confirm", json={
        "type": "EXPENSE", "amount": 21000, "account_id": acc,
        "category_id": cat, "merchant": "Warung Bu Sri",
        "description": "Makan siang", "date": TODAY,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    tx_id = body["transaction_id"]
    assert tx_id is not None
    assert body["ocr_status"] == "confirmed"

    # the confirmed transaction exists and moved the balance
    tx = client.get(f"/api/v1/transactions/{tx_id}").json()
    assert tx["amount"] == 21000 and tx["merchant"] == "Warung Bu Sri"
    after = client.get(f"/api/v1/accounts/{acc}").json()["current_balance"]
    assert after == before - 21000

    # double confirmation is rejected -> no duplicate transaction
    r = client.post(f"/api/v1/receipts/{rid}/confirm", json={
        "type": "EXPENSE", "amount": 21000, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "RECEIPT_ALREADY_CONFIRMED"

    # invalid payload on confirm -> 400, receipt stays unconfirmed
    rid2 = client.post("/api/v1/receipts",
                       files={"file": ("x.png", PNG_BYTES, "image/png")}
                       ).json()["receipt_id"]
    r = client.post(f"/api/v1/receipts/{rid2}/confirm", json={
        "type": "EXPENSE", "amount": -5, "account_id": acc,
        "category_id": cat, "date": TODAY,
    })
    assert r.status_code == 422
    assert client.get(f"/api/v1/receipts/{rid2}").json()["transaction_id"] is None

    # list contains both receipts
    ids = [r["receipt_id"] for r in client.get("/api/v1/receipts").json()]
    assert {rid, rid2} <= set(ids)

    # unknown receipt
    assert client.get("/api/v1/receipts/99999").status_code == 404


def test_net_worth_history_snapshot_upsert():
    # No snapshots yet (lifespan startup hook only runs on a real server)
    assert client.get("/api/v1/reports/net-worth/history").json()["count"] == 0

    snap = client.post("/api/v1/reports/net-worth/snapshot")
    assert snap.status_code == 201
    snap = snap.json()
    assert set(snap) >= {"date", "net_worth", "total_assets", "total_liabilities"}

    first = client.get("/api/v1/reports/net-worth/history").json()
    assert first["count"] == 1

    # Same-day re-post must UPSERT (still exactly one point for today),
    # refreshing values rather than appending a duplicate row.
    client.post("/api/v1/reports/net-worth/snapshot")
    second = client.get("/api/v1/reports/net-worth/history").json()
    assert second["count"] == 1

    nw = client.get("/api/v1/reports/net-worth").json()["current"]
    today_point = next(p for p in second["points"] if p["date"] == str(date.today()))
    assert today_point["net_worth"] == nw["net_worth"]
    assert today_point["total_assets"] == nw["total_assets"]
    assert today_point["total_liabilities"] == nw["total_liabilities"]

    # date filter narrows results
    empty = client.get(
        "/api/v1/reports/net-worth/history?date_from=2000-01-01&date_to=2000-01-02"
    ).json()
    assert empty["count"] == 0