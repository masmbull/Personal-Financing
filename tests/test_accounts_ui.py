"""Account UI balance-flow tests.

Covers the "add account" vs "set balance" split:
- create form has NO balance field (balance always starts at 0)
- balance entry happens on the edit form, parsed as IDR (20.000 -> 20000)
- created accounts show their formatted balance + sidebar total
"""
from app.models.models import Account, AccountType
from tests.conftest import client, get_test_db


def _html_create(client, name="Toko", type_="CASH") -> int:
    """Create an account through the HTML form (balance-free)."""
    r = client.post("/accounts/create", data={
        "name": name, "type": type_, "icon": "",
    })
    assert r.status_code == 200, r.text          # client auto-follows the 303
    assert r.history and r.history[0].status_code == 303, r.history
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == name).first()
    assert acc is not None
    rid = acc.id
    db.close()
    return rid


def test_create_form_has_no_balance_field():
    r = client.get("/accounts/create")
    assert r.status_code == 200
    assert "initial_balance" not in r.text
    assert "Saldo Awal" not in r.text
    assert "name" in r.text and "type" in r.text


def test_create_always_zero_balance():
    rid = _html_create(client, "Kios", "CASH")
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == rid).first()
    assert acc is not None
    assert acc.initial_balance == 0
    assert acc.current_balance == 0
    db.close()


def test_set_balance_idr_parsed():
    """POST balance as '20.000' -> stored as 20000 (dot thousands)."""
    rid = _html_create(client, "Warung", "CASH")
    r = client.post(f"/accounts/edit/{rid}", data={
        "name": "Warung", "type": "CASH", "initial_balance": "20.000", "icon": "",
    })
    assert r.status_code == 200, r.text
    assert r.history and r.history[0].status_code == 303, r.history
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == rid).first()
    assert acc is not None
    assert acc.initial_balance == 20000
    assert acc.current_balance == 20000
    db.close()


def test_set_balance_accepts_plain_integer():
    rid = _html_create(client, "TokoB", "CASH")
    r = client.post(f"/accounts/edit/{rid}", data={
        "name": "TokoB", "type": "CASH", "initial_balance": "15000", "icon": "",
    })
    assert r.status_code == 200, r.text
    assert r.history and r.history[0].status_code == 303, r.history
    db = get_test_db()
    acc = db.query(Account).filter(Account.id == rid).first()
    assert acc.initial_balance == 15000
    db.close()


def test_set_balance_rejects_malformed():
    rid = _html_create(client, "Salah", "CASH")
    r = client.post(f"/accounts/edit/{rid}", data={
        "name": "Salah", "type": "CASH", "initial_balance": "abc", "icon": "",
    })
    assert r.status_code == 400, r.text


def test_list_shows_balance_and_sidebar_total():
    rid = _html_create(client, "SideCash", "CASH")
    client.post(f"/accounts/edit/{rid}", data={
        "name": "SideCash", "type": "CASH", "initial_balance": "100.000", "icon": "",
    })
    r = client.get("/accounts")
    assert r.status_code == 200
    assert "Rp 100.000" in r.text
    # sidebar indicator only rendered on account pages
    assert "Saldo Akun" in r.text
    assert "sidebar-balance-value" in r.text


def test_edit_form_is_balance_focused():
    rid = _html_create(client, "Fokus", "BANK")
    r = client.get(f"/accounts/edit/{rid}")
    assert r.status_code == 200
    assert "Isi Saldo" in r.text          # new title
    assert "Saldo" in r.text
    assert "Nama &amp; tipe akun" in r.text


ICON_CASH = "\U0001f4b5"          # 💵 banknote
ICON_BANK = "\U0001f3e6"          # 🏦 bank
ICON_CARD = "\U0001f4b3"          # 💳 credit card


def test_create_form_renders_icon_picker():
    r = client.get("/accounts/create")
    assert r.status_code == 200
    # hidden text field + radio grid + pools keyed by type
    assert 'name="icon"' in r.text
    assert "icon-choice" in r.text
    assert 'data-type="CASH"' in r.text
    assert ICON_CASH in r.text
    assert ICON_BANK in r.text


def test_edit_form_renders_icon_picker():
    rid = _html_create(client, "IkonBank2", "BANK")
    r = client.get(f"/accounts/edit/{rid}")
    assert r.status_code == 200
    assert "icon-choice" in r.text
    assert ICON_BANK in r.text
    assert ICON_CASH in r.text


def test_create_with_icon_from_picker():
    """Picking the bank emoji on create stores it as the account icon."""
    r = client.post("/accounts/create", data={
        "name": "IkonBCA", "type": "BANK", "icon": ICON_BANK,
    })
    assert r.status_code == 200, r.text
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "IkonBCA").first()
    assert acc is not None
    assert acc.icon == ICON_BANK
    db.close()


def test_icon_pools_covered_by_model():
    """Every AccountType shown in the form has a pool."""
    from app.models.models import AccountType
    from app.account_icons import ACCOUNT_ICON_POOLS
    assert set(AccountType) == set(ACCOUNT_ICON_POOLS)
    for pool in ACCOUNT_ICON_POOLS.values():
        assert pool, "no empty pool"


def test_bank_brand_resolves_known_and_falls_back():
    """Bank/e-wallet accounts get a brand mark; cash stays emoji."""
    from app.account_icons import bank_brand
    from types import SimpleNamespace
    bca = SimpleNamespace(type=AccountType.BANK, institution="BCA", name="BCA")
    result = bank_brand(bca)
    assert result == {"mark": "BCA", "bg": "#0060af", "fg": "#ffffff", "logo": "bca.png"}
    # longest-key wins: "BCA Digital" -> blu, not generic BCA
    blu = SimpleNamespace(type=AccountType.BANK, institution="BCA Digital", name="Blu")
    blu_result = bank_brand(blu)
    assert blu_result["mark"] == "blu"
    assert blu_result["logo"] is None        # no bundled logo -> monogram fallback
    cash = SimpleNamespace(type=AccountType.CASH, institution=None, name="Cash")
    assert bank_brand(cash) is None


def test_list_renders_brand_badge_for_bank():
    """Accounts page shows the logo img + monogram fallback for seeded bank accounts."""
    r = client.get("/accounts")
    assert r.status_code == 200
    assert 'class="acc-icon acc-icon-brand"' in r.text
    # logo image renders (real logo, not just monogram text)
    assert 'src="/static/bank-logos/bca.png?v=1"' in r.text
    assert 'class="acc-brand-logo"' in r.text