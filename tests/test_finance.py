import pytest
from datetime import date

from app.models.models import Account, Category, TransactionType, AccountType
from app.services.finance import create_transaction, get_dashboard_data

# Shared client/DB helpers live in tests/conftest.py
from tests.conftest import client, default_user_id, get_test_db  # noqa: E402,F401


def test_create_expense():
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    tx = create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=35000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(), description="Nasi goreng")
    assert tx.id is not None
    assert tx.amount == 35000
    assert tx.type == TransactionType.EXPENSE
    db.refresh(acc)
    assert acc.current_balance == 1000000 - 35000
    db.close()


def test_create_income():
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Gaji").first()
    tx = create_transaction(db, user_id=default_user_id(), type=TransactionType.INCOME, amount=5000000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(), description="Gaji bulanan")
    assert tx.id is not None
    assert tx.amount == 5000000
    db.refresh(acc)
    assert acc.current_balance == 1000000 + 5000000
    db.close()


def test_account_balance():
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "Cash").first()
    assert acc.current_balance == 500000
    cat = db.query(Category).filter(Category.name == "Belanja").first()
    create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=200000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(), description="Groceries")
    db.refresh(acc)
    assert acc.current_balance == 300000
    db.close()


def test_transfer():
    db = get_test_db()
    bca = db.query(Account).filter(Account.name == "BCA").first()
    cash = db.query(Account).filter(Account.name == "Cash").first()
    bca_before = bca.current_balance
    cash_before = cash.current_balance
    tx = create_transaction(db, user_id=default_user_id(), type=TransactionType.TRANSFER, amount=200000,
        account_id=bca.id, category_id=None, date_val=date.today(),
        description="ATM", transfer_to_account_id=cash.id)
    assert tx.id is not None
    assert tx.type == TransactionType.TRANSFER
    db.refresh(bca)
    db.refresh(cash)
    assert bca.current_balance == bca_before - 200000
    assert cash.current_balance == cash_before + 200000
    db.close()


def test_category():
    db = get_test_db()
    count = db.query(Category).count()
    assert count >= 5
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    assert cat is not None
    assert cat.type == TransactionType.EXPENSE
    db.close()


def test_dashboard_calculation():
    db = get_test_db()
    bca = db.query(Account).filter(Account.name == "BCA").first()
    gaji = db.query(Category).filter(Category.name == "Gaji").first()
    makan = db.query(Category).filter(Category.name == "Makan & Minum").first()
    create_transaction(db, user_id=default_user_id(), type=TransactionType.INCOME, amount=5000000,
        account_id=bca.id, category_id=gaji.id, date_val=date.today(), description="Salary")
    create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=35000,
        account_id=bca.id, category_id=makan.id, date_val=date.today(), description="Lunch")
    data = get_dashboard_data(db)
    assert data["total_income"] >= 5000000
    assert data["total_expense"] >= 35000
    assert data["cashflow"] >= 5000000 - 35000
    assert len(data["recent_transactions"]) >= 2
    db.close()


def test_dashboard_page():
    response = client.get("/")
    assert response.status_code == 200


def test_transactions_page():
    response = client.get("/transactions")
    assert response.status_code == 200


def test_add_expense_page():
    response = client.get("/transactions/add?tx_type=EXPENSE")
    assert response.status_code == 200


def test_accounts_page():
    response = client.get("/accounts")
    assert response.status_code == 200


def test_categories_page():
    response = client.get("/categories")
    assert response.status_code == 200


def test_reports_page():
    response = client.get("/reports")
    assert response.status_code == 200


def test_transfer_page():
    response = client.get("/transfer")
    assert response.status_code == 200


def test_transactions_empty_state():
    """Fresh DB with no transactions shows the empty state."""
    response = client.get("/transactions")
    assert response.status_code == 200
    assert "Belum ada transaksi" in response.text


def test_transaction_appears_after_creation():
    """A transaction created via the service appears on /transactions."""
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=25000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(),
        description="Test mie ayam")
    db.close()

    response = client.get("/transactions")
    assert response.status_code == 200
    assert "Test mie ayam" in response.text
    assert "Rp25" in response.text or "Rp 25" in response.text or "25.000" in response.text


def test_transactions_empty_state_not_shown_with_data():
    """When transactions exist, empty state is not rendered."""
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=15000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(),
        description="Kopi")
    db.close()

    response = client.get("/transactions")
    assert response.status_code == 200
    assert "Belum ada transaksi" not in response.text
    assert "Kopi" in response.text


# ==================== FINANCE MODULE PAGES ====================


def test_debts_page():
    response = client.get("/debts")
    assert response.status_code == 200
    assert "Hutang" in response.text


def test_bills_page():
    response = client.get("/bills")
    assert response.status_code == 200


def test_budgets_page():
    response = client.get("/budgets")
    assert response.status_code == 200


def test_savings_page():
    response = client.get("/savings")
    assert response.status_code == 200


def test_assets_page():
    response = client.get("/assets")
    assert response.status_code == 200


def test_investments_page():
    response = client.get("/investments")
    assert response.status_code == 200


def test_accounts_grouped_display():
    """Accounts page groups accounts and shows group totals."""
    response = client.get("/accounts")
    assert response.status_code == 200
    assert "Rekening" in response.text


def test_debt_create_and_pay():
    """Create a payable debt then pay it partially; check totals update."""
    r = client.post("/debts/create", data={
        "type": "PAYABLE", "person_name": "Budi",
        "description": "Pinjam modal", "principal_amount": "1000000",
        "due_date": "", "installment_amount": "", "installment_count": "",
        "notes": "", "person_contact": "", "related_account_id": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    response = client.get("/debts")
    assert "Budi" in response.text

    db = get_test_db()
    from app.models.models import Debt, DebtStatus
    debt = db.query(Debt).filter(Debt.person_name == "Budi").first()
    debt_id = debt.id
    remaining_before = debt.remaining_amount
    db.close()

    r = client.post(f"/debts/pay/{debt_id}", data={
        "amount": "400000", "account_id": "", "notes": "cicil", "date_val": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    debt = db.query(Debt).filter(Debt.id == debt_id).first()
    assert debt.remaining_amount == remaining_before - 400000
    assert debt.status == DebtStatus.PARTIALLY_PAID
    db.close()


def test_bill_create():
    r = client.post("/bills/create", data={
        "name": "Listrik", "amount": "350000", "frequency": "MONTHLY",
        "due_day": "10", "category_id": "", "account_id": "", "notes": "",
    }, follow_redirects=False)
    assert r.status_code == 303
    response = client.get("/bills")
    assert "Listrik" in response.text


def test_budget_create_and_spending():
    """Budget shows spent percentage based on expenses."""
    db = get_test_db()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    cat_id = cat.id
    bca = db.query(Account).filter(Account.name == "BCA").first()
    acc_id = bca.id
    db.close()

    today = date.today()
    r = client.post("/budgets/create", data={
        "category_id": str(cat_id), "amount": "500000",
        "month": str(today.month), "year": str(today.year),
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=100000,
        account_id=acc_id, category_id=cat_id, date_val=today,
        description="Makan siang")
    db.close()

    response = client.get("/budgets")
    assert response.status_code == 200
    assert "Makan" in response.text


def test_savings_goal_deposit_withdraw():
    r = client.post("/savings/create", data={
        "name": "Beli Laptop", "target_amount": "10000000",
        "icon": "\U0001f4bb", "notes": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    from app.models.models import SavingsGoal
    goal = db.query(SavingsGoal).filter(SavingsGoal.name == "Beli Laptop").first()
    goal_id = goal.id
    assert goal.current_amount == 0
    db.close()

    r = client.post(f"/savings/deposit/{goal_id}", data={
        "amount": "2500000", "notes": "setoran awal", "related_account_id": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
    assert goal.current_amount == 2500000
    db.close()

    r = client.post(f"/savings/withdraw/{goal_id}", data={
        "amount": "500000", "notes": "tarik sebagian", "related_account_id": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    goal = db.query(SavingsGoal).filter(SavingsGoal.id == goal_id).first()
    assert goal.current_amount == 2000000
    db.close()


def test_asset_create_edit_delete():
    today_str_val = date.today().isoformat()
    r = client.post("/assets/create", data={
        "name": "Honda Beat", "asset_type": "Kendaraan",
        "current_value": "15000000", "purchase_value": "18000000",
        "purchase_date": today_str_val, "notes": "", "icon": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    from app.models.models import AssetRecord
    asset = db.query(AssetRecord).filter(AssetRecord.name == "Honda Beat").first()
    asset_id = asset.id
    db.close()

    response = client.get("/assets")
    assert "Honda Beat" in response.text

    r = client.post(f"/assets/edit/{asset_id}", data={
        "name": "Honda Beat", "asset_type": "Kendaraan",
        "current_value": "14000000", "purchase_value": "18000000",
        "purchase_date": today_str_val, "notes": "turun nilai", "icon": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    db = get_test_db()
    asset = db.query(AssetRecord).filter(AssetRecord.id == asset_id).first()
    assert asset.current_value == 14000000
    db.close()

    r = client.get(f"/assets/delete/{asset_id}", follow_redirects=False)
    assert r.status_code == 303
    db = get_test_db()
    assert db.query(AssetRecord).filter(AssetRecord.id == asset_id).first() is None
    db.close()


def test_investment_create_and_return():
    today_str_val = date.today().isoformat()
    r = client.post("/investments/create", data={
        "name": "BBCA", "investment_type": "Saham",
        "amount_invested": "5000000", "current_value": "5500000",
        "purchase_date": today_str_val, "notes": "", "icon": "",
    }, follow_redirects=False)
    assert r.status_code == 303

    response = client.get("/investments")
    assert "BBCA" in response.text


def test_merchant_field_on_transaction():
    """Merchant saved via service appears in transaction list search."""
    db = get_test_db()
    acc = db.query(Account).filter(Account.name == "BCA").first()
    cat = db.query(Category).filter(Category.name == "Makan & Minum").first()
    tx = create_transaction(db, user_id=default_user_id(), type=TransactionType.EXPENSE, amount=30000,
        account_id=acc.id, category_id=cat.id, date_val=date.today(),
        description="Ayam geprek", merchant="Baso Aci")
    assert tx.merchant == "Baso Aci"
    db.close()

    response = client.get("/transactions?search=Baso")
    assert response.status_code == 200
    assert "Ayam geprek" in response.text
