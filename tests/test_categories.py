"""Dedicated tests for category hierarchy: list/create/tree/parent rules/in-use."""
from tests.conftest import client  # noqa: E402,F401

EXPENSE = "Makan & Minum"      # seeded EXPENSE root, has no parent
INCOME = "Gaji"                # seeded INCOME root


def _cat(name):
    data = client.get("/api/v1/categories").json()
    return next(c["id"] for c in data["items"] if c["name"] == name)


def _post(name, type_, parent_id=None):
    payload = {"name": name, "type": type_}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    return client.post("/api/v1/categories", json=payload)


# ==================== list ====================


def test_list_categories_structure():
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    body = r.json()
    assert {"items", "total"} <= set(body)
    assert body["total"] == len(body["items"])
    # every item carries the hierarchy fields
    for item in body["items"]:
        assert "parent_id" in item and "has_children" in item


def test_list_categories_by_type_filter():
    for t in ("EXPENSE", "INCOME", "expense", "income"):
        r = client.get("/api/v1/categories?type=" + t)
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["type"] == t.upper()


# ==================== create ====================


def test_create_root_category_without_parent():
    parent_before = client.get("/api/v1/categories/tree").json()
    r = _post("Pajak", "EXPENSE")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Pajak"
    assert body["type"] == "EXPENSE"
    assert body["parent_id"] is None


def test_create_child_category_under_parent():
    pid = _cat(EXPENSE)
    r = _post("Makan Ringan", "EXPENSE", parent_id=pid)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["parent_id"] == pid
    # parent should now report having children
    parent = client.get(f"/api/v1/categories/{pid}").json()
    assert parent["has_children"] is True


def _make_child() -> tuple[int, int]:
    """Helper: parent + one EXPENSE child. Returns (parent_id, child_id)."""
    pid = _cat(EXPENSE)
    child = client.post("/api/v1/categories", json={
        "name": "Makanan Campuran", "type": "EXPENSE", "parent_id": pid,
    }).json()
    return pid, child["id"]


# ==================== tree ====================


def test_tree_returns_nested_structure():
    pid, cid = _make_child()
    r = client.get("/api/v1/categories/tree")
    assert r.status_code == 200
    tree = r.json()
    # find parent node among roots
    parent_node = next(n for n in tree if n["id"] == pid)
    child_nodes = parent_node["children"]
    assert any(n["id"] == cid for n in child_nodes)
    # child node must carry the nesting key
    assert all("children" in n for n in child_nodes)


def test_tree_filters_by_type():
    _make_child()
    r = client.get("/api/v1/categories/tree?type=INCOME")
    assert r.status_code == 200
    for node in r.json():
        assert node["type"] == "INCOME"


# ==================== cycle rejection ====================


def test_cycle_rejected_on_update():
    pid, cid = _make_child()
    # moving the parent under its own child would create a cycle
    r = client.put(f"/api/v1/categories/{pid}", json={"parent_id": cid})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CATEGORY_INVALID_PARENT"


# ==================== cross-type parent rejection ====================


def test_cross_type_parent_rejected_on_create():
    expense_parent = _cat(EXPENSE)
    r = _post("Gaji Anak", "INCOME", parent_id=expense_parent)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "CATEGORY_INVALID_PARENT"


def test_cross_type_parent_rejected_when_changing_type():
    pid, cid = _make_child()
    # child has an EXPENSE parent; renaming child type to INCOME conflicts with parent
    r = client.put(f"/api/v1/categories/{cid}", json={"type": "INCOME"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CATEGORY_INVALID_PARENT"


def test_nonexistent_parent_rejected():
    r = _post("Anak", "EXPENSE", parent_id=99999)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CATEGORY_INVALID_PARENT"


# ==================== in-use deletion -> 409 ====================


def test_in_use_category_returns_409():
    from datetime import date
    today = date.today().isoformat()
    acc = next(a["id"] for a in client.get("/api/v1/accounts").json()["items"]
               if a["name"] == "BCA")
    cat = _cat(EXPENSE)
    client.post("/api/v1/transactions", json={
        "type": "EXPENSE", "amount": 1000, "account_id": acc,
        "category_id": cat, "date": today,
    })
    r = client.delete(f"/api/v1/categories/{cat}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CATEGORY_IN_USE"
