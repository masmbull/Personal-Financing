"""E2E workflow test."""
import re
from datetime import date
from fastapi.testclient import TestClient
from app.api.deps import get_current_user
from app.main import app
from tests.conftest import TEST_PASSWORD

TODAY = date.today().isoformat()

def _fresh_client():
    app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, follow_redirects=False)

def _csrf(client):
    r = client.get("/register")
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m
    return m.group(1)

def _api(client, method, path, **kw):
    r = getattr(client, method)(path, **kw)
    assert r.status_code < 400, f"{method} {path} -> {r.status_code}"
    return r.json() if r.content else None

def test_full_workflow():
    c = _fresh_client()
    token = _csrf(c)
    r = c.post("/register", data={
        "username": "integration_user", "password": TEST_PASSWORD,
        "password2": TEST_PASSWORD, "csrf_token": token,
    })
    assert r.status_code == 303 and "error=1" not in r.headers.get("location", "")

    cash = _api(c,"post","/api/v1/accounts",json={"name":"Cash","type":"CASH","initial_balance":0})["id"]
    bank = _api(c,"post","/api/v1/accounts",json={"name":"BCA","type":"BANK","initial_balance":0})["id"]
    ew = _api(c,"post","/api/v1/accounts",json={"name":"DANA","type":"E_WALLET","initial_balance":0})["id"]
    cc = _api(c,"post","/api/v1/accounts",json={"name":"Visa","type":"CREDIT_CARD","initial_balance":0})["id"]

    cats = _api(c,"get","/api/v1/categories")["items"]
    salary = next(x["id"] for x in cats if x["name"]=="Gaji")
    food = next(x["id"] for x in cats if x["name"]=="Makan & Minum")
    trans = next(x["id"] for x in cats if x["name"]=="Transportasi")

    # INCOME
    _api(c,"post","/api/v1/transactions",json={"type":"INCOME","amount":5000000,"account_id":bank,"category_id":salary,"date":TODAY})
    assert _api(c,"get",f"/api/v1/accounts/{bank}")["current_balance"]==5000000

    # EXPENSE
    _api(c,"post","/api/v1/transactions",json={"type":"EXPENSE","amount":300000,"account_id":cash,"category_id":food,"merchant":"Indomaret","date":TODAY})
    assert _api(c,"get",f"/api/v1/accounts/{cash}")["current_balance"]==-300000

    # TRANSFER
    _api(c,"post","/api/v1/transfers",json={"from_account_id":bank,"to_account_id":ew,"amount":500000,"date":TODAY})
    assert _api(c,"get",f"/api/v1/accounts/{bank}")["current_balance"]==4500000
    assert _api(c,"get",f"/api/v1/accounts/{ew}")["current_balance"]==500000

    # CC purchase: liability up, cash unchanged
    cb = _api(c,"get",f"/api/v1/accounts/{cash}")["current_balance"]
    _api(c,"post","/api/v1/transactions",json={"type":"EXPENSE","amount":250000,"account_id":cc,"category_id":trans,"date":TODAY})
    assert _api(c,"get",f"/api/v1/accounts/{cc}")["current_balance"]==-250000
    assert _api(c,"get",f"/api/v1/accounts/{cash}")["current_balance"]==cb

    # CC payment via transfer
    _api(c,"post","/api/v1/transfers",json={"from_account_id":bank,"to_account_id":cc,"amount":250000,"date":TODAY})
    assert _api(c,"get",f"/api/v1/accounts/{cc}")["current_balance"]==0
    assert _api(c,"get",f"/api/v1/accounts/{bank}")["current_balance"]==4250000

    # BUDGET
    _api(c,"post","/api/v1/budgets",json={"category_id":food,"amount":1000000,"month":date.today().month,"year":date.today().year})
    assert any(b["category"]["id"]==food for b in _api(c,"get","/api/v1/budgets")["items"])

    # SAVINGS
    gid = _api(c,"post","/api/v1/savings",json={"name":"Emergency","target_amount":10000000})["id"]
    _api(c,"post",f"/api/v1/savings/{gid}/deposit",json={"amount":1000000})
    assert _api(c,"get",f"/api/v1/savings/{gid}")["current_amount"]==1000000

    # DEBT + payment
    did = _api(c,"post","/api/v1/debts",json={"type":"PAYABLE","person_name":"Budi","principal_amount":2000000})["id"]
    _api(c,"post",f"/api/v1/debts/{did}/payments",json={"amount":500000,"account_id":bank,"payment_date":TODAY})
    d = _api(c,"get",f"/api/v1/debts/{did}")
    assert d["remaining_amount"]==1500000 and len(d["payments"])==1

    # BILL + scheduler
    _api(c,"post","/api/v1/bills",json={"name":"Listrik","amount":400000,"frequency":"MONTHLY","due_day":25,"account_id":bank,"category_id":food})
    _api(c,"post","/api/v1/bills/occurrences/run")

    # NET WORTH + snapshot
    nw = _api(c,"get","/api/v1/reports/net-worth")["current"]
    snap = _api(c,"post","/api/v1/reports/net-worth/snapshot")
    assert snap["net_worth"]==nw["net_worth"]
    _api(c,"post","/api/v1/reports/net-worth/snapshot")
    assert _api(c,"get","/api/v1/reports/net-worth/history")["count"]==1

    # REPORTS (transfers excluded)
    flow = _api(c,"get","/api/v1/reports/cash-flow")
    assert flow["income"]==5000000 and flow["expense"]==1050000

    # DASHBOARD
    assert _api(c,"get","/api/v1/dashboard")["net_worth"]==nw["net_worth"]

    # CSV EXPORT
    r = c.get("/transactions/export")
    assert r.status_code==200 and "text/csv" in r.headers["content-type"]
    assert "5.000.000" in r.text  # income present in the export
