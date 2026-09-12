"""Feature-by-feature end-to-end coverage of every web (HTML) route.

Each test has a descriptive name of the shape ``test_<feature>_<action>_<outcome>``
so a CI failure reads like a sentence. Routes already covered in dedicated
modules (auth, receipts, admin, help, statement audit, ...) are not repeated
here; this module completes the gap analysis:

    dashboard / more / reports   -> smoke renders
    accounts                     -> create/edit/delete + validation guards
    transactions                 -> add income/expense, edit, delete, list
    transfer                     -> dedicated transfer page flow
    categories                   -> create/edit/delete
    budgets                      -> create/delete + validation
    bills                        -> create/pay/delete + validation
    debts                        -> create/pay/delete + validation
    savings                      -> goal create/deposit/withdraw/delete
    investments                  -> create/edit/delete + 404
    assets                       -> create/edit/delete
    exports                      -> CSV transactions + reports export
"""

from tests.conftest import get_test_db


def _acc_id(name: str) -> int:
    db = get_test_db()
    try:
        return db.query(
            __import__("app.models.models", fromlist=["Account"]).Account
        ).filter_by(name=name).first().id
    finally:
        db.close()


def _acc_balance(name: str) -> int:
    from app.models.models import Account
    db = get_test_db()
    try:
        return db.query(Account).filter_by(name=name).first().current_balance
    finally:
        db.close()


def _cat_id(name: str) -> int:
    from app.models.models import Category
    db = get_test_db()
    try:
        return db.query(Category).filter_by(name=name).first().id
    finally:
        db.close()


# =====================================================================
# Dashboard / More / Reports  (smoke: the pages must render with data)
# =====================================================================

def test_dashboard_home_renders_with_seeded_accounts(client):
    """GET / must render 200 for the seeded user (accounts + categories)."""
    resp = client.get("/")
    assert resp.status_code == 200


def test_more_menu_page_renders_200(client):
    """GET /more (the extra-menu hub) must render 200."""
    assert client.get("/more").status_code == 200


def test_reports_page_renders_200(client):
    """GET /reports must render 200 even with no transactions yet."""
    assert client.get("/reports").status_code == 200


# =====================================================================
# Accounts
# =====================================================================

def test_account_create_page_renders_200(client):
    """GET /accounts/create must render the form."""
    assert client.get("/accounts/create").status_code == 200


def test_account_create_adds_account_to_list(client):
    """POST /accounts/create must persist a new account and list it."""
    resp = client.post("/accounts/create", data={
        "name": "Mandiri", "type": "BANK", "icon": "🏦",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/accounts")
    assert page.status_code == 200 and "Mandiri" in page.text


def test_account_create_invalid_type_returns_400(client):
    """POST /accounts/create with an unknown type must be rejected 400."""
    resp = client.post("/accounts/create", data={
        "name": "Jelek", "type": "SALAH", "icon": "",
    })
    assert resp.status_code == 400


def test_account_edit_renames_account(client):
    """POST /accounts/edit/<id> must rename the account."""
    aid = _acc_id("BCA")
    resp = client.post(f"/accounts/edit/{aid}", data={
        "name": "BCA Utama", "type": "BANK",
        "initial_balance": "1000000", "icon": "🏦",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "BCA Utama" in client.get("/accounts").text


def test_account_edit_missing_account_returns_404(client):
    """POST /accounts/edit/<bogus> must 404, never create anything."""
    assert client.post("/accounts/edit/99999", data={
        "name": "X", "type": "BANK", "initial_balance": "0",
    }).status_code == 404


def test_account_delete_removes_account_from_list(client):
    """GET /accounts/delete/<id> (no transactions) must remove it."""
    resp = client.post("/accounts/create", data={
        "name": "Sementara", "type": "CASH",
    }, follow_redirects=False)
    assert resp.status_code == 303
    aid = _acc_id("Sementara")
    assert client.get(f"/accounts/delete/{aid}", follow_redirects=False).status_code == 303
    page = client.get("/accounts")
    assert page.status_code == 200 and "Sementara" not in page.text


def test_account_delete_used_by_transaction_returns_409(client):
    """Deleting an account that has transactions must be blocked 409."""
    aid = _acc_id("BCA")
    resp = client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "10000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")), "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "ngetes", "merchant": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert client.get(f"/accounts/delete/{aid}", follow_redirects=False).status_code == 409


# =====================================================================
# Transactions
# =====================================================================

def test_transaction_add_page_renders_200(client):
    """GET /transactions/add must render the form."""
    assert client.get("/transactions/add").status_code == 200


def test_transaction_add_expense_decreases_account_balance(client):
    """POST /transactions/add EXPENSE must reduce the account balance."""
    aid = _acc_id("BCA")
    resp = client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "25000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")),
        "transfer_to_account_id": "", "date_val": "2026-09-12",
        "description": "Kopi", "merchant": "Kopi Kenangan",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert _acc_balance("BCA") == 1_000_000 - 25_000


def test_transaction_add_income_increases_account_balance(client):
    """POST /transactions/add INCOME must increase the account balance."""
    aid = _acc_id("BCA")
    resp = client.post("/transactions/add", data={
        "type": "INCOME", "amount": "2000000", "account_id": str(aid),
        "category_id": str(_cat_id("Gaji")),
        "transfer_to_account_id": "", "date_val": "2026-09-01",
        "description": "Gaji bulanan", "merchant": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert _acc_balance("BCA") == 1_000_000 + 2_000_000


def test_transaction_add_invalid_amount_returns_400(client):
    """Non-numeric amount must be rejected 400 (no transaction created)."""
    resp = client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "bukan-angka", "account_id": "1",
        "category_id": "", "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "", "merchant": "",
    })
    assert resp.status_code == 400


def test_transaction_add_unknown_account_returns_400(client):
    """Referencing a non-existent account must be rejected 400."""
    resp = client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "5000", "account_id": "99999",
        "category_id": "", "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "", "merchant": "",
    })
    assert resp.status_code == 400


def test_transactions_list_shows_added_transaction(client):
    """GET /transactions must list the transaction just added."""
    aid = _acc_id("BCA")
    client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "25000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")),
        "transfer_to_account_id": "", "date_val": "2026-09-12",
        "description": "Sarapan Padang", "merchant": "",
    })
    page = client.get("/transactions")
    assert page.status_code == 200 and "Sarapan Padang" in page.text


def test_transaction_edit_page_renders_200(client):
    """GET /transactions/edit/<id> must render the prefilled form."""
    aid = _acc_id("BCA")
    client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "10000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")), "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "edit-ku", "merchant": "",
    })
    from app.models.models import Transaction
    db = get_test_db()
    try:
        tx_id = db.query(Transaction).filter_by(description="edit-ku").first().id
    finally:
        db.close()
    assert client.get(f"/transactions/edit/{tx_id}").status_code == 200


def test_transaction_edit_updates_amount_and_balance(client):
    """POST /transactions/edit/<id> must apply the new amount to balances."""
    aid = _acc_id("BCA")
    client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "25000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")), "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "makan", "merchant": "",
    })
    from app.models.models import Transaction
    db = get_test_db()
    try:
        tx_id = db.query(Transaction).filter_by(description="makan").first().id
    finally:
        db.close()
    resp = client.post(f"/transactions/edit/{tx_id}", data={
        "type": "EXPENSE", "amount": "30000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")), "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "makan", "merchant": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert _acc_balance("BCA") == 1_000_000 - 30_000


def test_transaction_delete_restores_account_balance(client):
    """GET /transactions/delete/<id> must remove the tx and refund balance."""
    aid = _acc_id("BCA")
    client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "25000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")), "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "hapus-ku", "merchant": "",
    })
    from app.models.models import Transaction
    db = get_test_db()
    try:
        tx_id = db.query(Transaction).filter_by(description="hapus-ku").first().id
    finally:
        db.close()
    assert client.get(f"/transactions/delete/{tx_id}", follow_redirects=False).status_code == 303
    assert _acc_balance("BCA") == 1_000_000


def test_transaction_edit_missing_transaction_returns_404(client):
    """Editing a transaction owned by nobody must 404."""
    assert client.post("/transactions/edit/99999", data={
        "type": "EXPENSE", "amount": "1000", "account_id": "1",
        "category_id": "", "transfer_to_account_id": "",
        "date_val": "2026-09-12", "description": "", "merchant": "",
    }).status_code == 404


# =====================================================================
# Transfer (dedicated page)
# =====================================================================

def test_transfer_page_renders_200(client):
    """GET /transfer must render the form with the user's accounts."""
    page = client.get("/transfer")
    assert page.status_code == 200 and "BCA" in page.text


def test_transfer_moves_money_between_accounts(client):
    """POST /transfer must debit the source and credit the destination."""
    src, dst = _acc_id("BCA"), _acc_id("Cash")
    resp = client.post("/transfer", data={
        "from_account_id": str(src), "to_account_id": str(dst),
        "amount": "100000", "date_val": "2026-09-12",
        "description": "isi cash",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert _acc_balance("BCA") == 900_000
    assert _acc_balance("Cash") == 600_000


def test_transfer_invalid_amount_returns_400(client):
    """POST /transfer with garbage amount must be rejected 400."""
    resp = client.post("/transfer", data={
        "from_account_id": "1", "to_account_id": "2",
        "amount": "x", "date_val": "2026-09-12", "description": "",
    })
    assert resp.status_code == 400


# =====================================================================
# Categories
# =====================================================================

def test_categories_page_renders_200(client):
    """GET /categories must render seeded categories."""
    page = client.get("/categories")
    assert page.status_code == 200 and "Transportasi" in page.text


def test_category_create_adds_to_list(client):
    """POST /categories/create must persist and list the new category."""
    resp = client.post("/categories/create", data={
        "name": "Hiburan", "type": "EXPENSE", "icon": "🎬",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/categories")
    assert "Hiburan" in page.text


def test_category_create_blank_name_returns_400(client):
    """POST /categories/create with a blank name must 400."""
    assert client.post("/categories/create", data={
        "name": "   ", "type": "EXPENSE",
    }).status_code == 400


def test_category_edit_renames_category(client):
    """POST /categories/edit/<id> must rename and relist it."""
    cid = _cat_id("Transportasi")
    resp = client.post(f"/categories/edit/{cid}", data={
        "name": "Transport Online", "type": "EXPENSE", "icon": "🛵",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/categories")
    assert "Transport Online" in page.text


def test_category_edit_missing_returns_404(client):
    """Editing a non-existent category must 404."""
    assert client.post("/categories/edit/99999", data={
        "name": "X", "type": "EXPENSE",
    }).status_code == 404


def test_category_delete_removes_category(client):
    """GET /categories/delete/<id> must remove it from the list."""
    client.post("/categories/create", data={
        "name": "Buang", "type": "EXPENSE",
    })
    cid = _cat_id("Buang")
    assert client.get(f"/categories/delete/{cid}", follow_redirects=False).status_code == 303
    assert "Buang" not in client.get("/categories").text


# =====================================================================
# Budgets
# =====================================================================

def test_budgets_page_renders_200(client):
    """GET /budgets must render even with no budgets."""
    assert client.get("/budgets").status_code == 200


def test_budget_create_then_delete_roundtrip(client):
    """POST /budgets/create persists; GET /budgets/delete removes it."""
    from app.models.models import Budget
    resp = client.post("/budgets/create", data={
        "category_id": str(_cat_id("Makan & Minum")),
        "amount": "1500000", "month": "9", "year": "2026",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db = get_test_db()
    try:
        budget = db.query(Budget).filter_by(amount=1_500_000).first()
        assert budget is not None and budget.month == 9
        budget_id = budget.id
    finally:
        db.close()
    assert client.get("/budgets").status_code == 200
    assert client.get(f"/budgets/delete/{budget_id}", follow_redirects=False).status_code == 303
    db = get_test_db()
    try:
        assert db.query(Budget).filter_by(id=budget_id).first() is None
    finally:
        db.close()


def test_budget_create_invalid_month_returns_400(client):
    """month=13 must be rejected 400 by input validation."""
    resp = client.post("/budgets/create", data={
        "category_id": "1", "amount": "500000",
        "month": "13", "year": "2026",
    })
    assert resp.status_code == 400


# =====================================================================
# Bills
# =====================================================================

def test_bills_page_renders_200(client):
    """GET /bills must render even with no bills."""
    assert client.get("/bills").status_code == 200


def test_bill_create_adds_bill_to_list(client):
    """POST /bills/create must persist and list the new bill."""
    resp = client.post("/bills/create", data={
        "name": "Netflix", "amount": "54000", "frequency": "MONTHLY",
        "due_day": "10", "category_id": "", "account_id": "", "notes": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/bills")
    assert page.status_code == 200 and "Netflix" in page.text


def test_bill_create_invalid_frequency_returns_400(client):
    """Unknown frequency must be rejected 400."""
    resp = client.post("/bills/create", data={
        "name": "Aneh", "amount": "1000", "frequency": "HARIAN",
    })
    assert resp.status_code == 400


def test_bill_pay_creates_expense_and_payment_record(client):
    """POST /bills/pay/<id> must create an expense tx + BillPayment row."""
    from app.models.models import Bill, BillPayment, Transaction
    client.post("/bills/create", data={
        "name": "Listrik", "amount": "300000", "frequency": "MONTHLY",
        "due_day": "5", "category_id": "", "account_id": "", "notes": "",
    })
    db = get_test_db()
    try:
        bill_id = db.query(Bill).filter_by(name="Listrik").first().id
    finally:
        db.close()
    aid = _acc_id("BCA")
    resp = client.post(f"/bills/pay/{bill_id}", data={
        "amount": "", "account_id": str(aid), "date_val": "2026-09-10",
    }, follow_redirects=False)
    assert resp.status_code == 303
    # Empty amount pays the bill's nominal (300000) from BCA.
    assert _acc_balance("BCA") == 1_000_000 - 300_000
    db = get_test_db()
    try:
        payment = db.query(BillPayment).filter_by(bill_id=bill_id).first()
        assert payment is not None and payment.amount == 300_000
        assert payment.transaction_id is not None
        tx = db.query(Transaction).filter_by(id=payment.transaction_id).first()
        assert tx is not None and tx.amount == 300_000
    finally:
        db.close()


def test_bill_pay_missing_bill_returns_404(client):
    """Paying a non-existent bill must 404."""
    resp = client.post("/bills/pay/99999", data={"amount": "1000"})
    assert resp.status_code == 404


def test_bill_delete_removes_bill_from_list(client):
    """GET /bills/delete/<id> must remove the bill."""
    from app.models.models import Bill
    client.post("/bills/create", data={
        "name": "Buang-ku", "amount": "10000", "frequency": "MONTHLY",
    })
    db = get_test_db()
    try:
        bill_id = db.query(Bill).filter_by(name="Buang-ku").first().id
    finally:
        db.close()
    assert client.get(f"/bills/delete/{bill_id}", follow_redirects=False).status_code == 303
    page = client.get("/bills")
    assert page.status_code == 200 and "Buang-ku" not in page.text


# =====================================================================
# Debts
# =====================================================================

def test_debts_page_renders_200(client):
    """GET /debts must render even with no debts."""
    assert client.get("/debts").status_code == 200


def test_debt_create_adds_debt_to_list(client):
    """POST /debts/create must persist and list the new payable."""
    resp = client.post("/debts/create", data={
        "type": "PAYABLE", "person_name": "Budi", "description": "utang makan",
        "principal_amount": "200000", "due_date": "2026-10-01",
        "installment_amount": "", "installment_count": "", "notes": "",
        "person_contact": "", "related_account_id": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/debts")
    assert page.status_code == 200 and "Budi" in page.text


def test_debt_create_invalid_type_returns_400(client):
    """Unknown debt type must be rejected 400."""
    resp = client.post("/debts/create", data={
        "type": "SALAH", "person_name": "X", "principal_amount": "1000",
    })
    assert resp.status_code == 400


def test_debt_pay_form_renders_200(client):
    """GET /debts/pay/<id> must render the payment form."""
    from app.models.models import Debt
    client.post("/debts/create", data={
        "type": "PAYABLE", "person_name": "Citra",
        "principal_amount": "500000",
    })
    db = get_test_db()
    try:
        debt_id = db.query(Debt).filter_by(person_name="Citra").first().id
    finally:
        db.close()
    assert client.get(f"/debts/pay/{debt_id}").status_code == 200


def test_debt_pay_reduces_remaining_and_account_balance(client):
    """POST /debts/pay/<id> must book DEBT_REPAYMENT and lower remaining."""
    from app.models.models import Debt
    client.post("/debts/create", data={
        "type": "PAYABLE", "person_name": "Dedi", "principal_amount": "200000",
    })
    db = get_test_db()
    try:
        debt_id = db.query(Debt).filter_by(person_name="Dedi").first().id
    finally:
        db.close()
    resp = client.post(f"/debts/pay/{debt_id}", data={
        "amount": "50000", "account_id": str(_acc_id("BCA")),
        "notes": "cicil 1", "date_val": "2026-09-12",
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert _acc_balance("BCA") == 950_000
    db = get_test_db()
    try:
        debt = db.query(Debt).filter_by(id=debt_id).first()
        assert debt.remaining_amount == 150_000
    finally:
        db.close()


def test_debt_pay_over_remaining_returns_400(client):
    """Paying more than the remaining amount must be rejected 400."""
    from app.models.models import Debt
    client.post("/debts/create", data={
        "type": "PAYABLE", "person_name": "Eka", "principal_amount": "50000",
    })
    db = get_test_db()
    try:
        debt_id = db.query(Debt).filter_by(person_name="Eka").first().id
    finally:
        db.close()
    resp = client.post(f"/debts/pay/{debt_id}", data={
        "amount": "999999", "account_id": "", "notes": "", "date_val": "",
    })
    assert resp.status_code == 400


def test_debt_delete_removes_debt_from_list(client):
    """GET /debts/delete/<id> must remove the debt."""
    from app.models.models import Debt
    client.post("/debts/create", data={
        "type": "RECEIVABLE", "person_name": "Buang-utang",
        "principal_amount": "1000",
    })
    db = get_test_db()
    try:
        debt_id = db.query(Debt).filter_by(person_name="Buang-utang").first().id
    finally:
        db.close()
    assert client.get(f"/debts/delete/{debt_id}", follow_redirects=False).status_code == 303
    page = client.get("/debts")
    assert page.status_code == 200 and "Buang-utang" not in page.text


# =====================================================================
# Savings goals
# =====================================================================

def test_savings_page_renders_200(client):
    """GET /savings must render even with no goals."""
    assert client.get("/savings").status_code == 200


def test_saving_goal_create_adds_goal_to_list(client):
    """POST /savings/create must persist and list the new goal."""
    resp = client.post("/savings/create", data={
        "name": "Liburan Bali", "target_amount": "5000000",
        "icon": "🏝️", "notes": "desember",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/savings")
    assert page.status_code == 200 and "Liburan Bali" in page.text


def test_saving_goal_deposit_then_withdraw_updates_current_amount(client):
    """Deposit adds and withdraw subtracts from goal.current_amount."""
    from app.models.models import SavingsGoal
    client.post("/savings/create", data={
        "name": "Dana Darurat", "target_amount": "10000000",
    })
    db = get_test_db()
    try:
        goal_id = db.query(SavingsGoal).filter_by(name="Dana Darurat").first().id
    finally:
        db.close()
    assert client.post(f"/savings/deposit/{goal_id}", data={
        "amount": "300000", "notes": "setor",
        "related_account_id": str(_acc_id("BCA")),
    }, follow_redirects=False).status_code == 303
    assert client.post(f"/savings/withdraw/{goal_id}", data={
        "amount": "100000", "notes": "tarik darurat", "related_account_id": "",
    }, follow_redirects=False).status_code == 303
    db = get_test_db()
    try:
        goal = db.query(SavingsGoal).filter_by(id=goal_id).first()
        assert goal.current_amount == 200_000
    finally:
        db.close()


def test_saving_withdraw_more_than_saved_returns_400(client):
    """Withdrawing more than saved must be rejected 400."""
    from app.models.models import SavingsGoal
    client.post("/savings/create", data={"name": "Kecil", "target_amount": "1000"})
    db = get_test_db()
    try:
        goal_id = db.query(SavingsGoal).filter_by(name="Kecil").first().id
    finally:
        db.close()
    resp = client.post(f"/savings/withdraw/{goal_id}", data={
        "amount": "999999", "notes": "", "related_account_id": "",
    })
    assert resp.status_code == 400


def test_saving_goal_delete_removes_goal_from_list(client):
    """GET /savings/delete/<id> must remove the goal."""
    from app.models.models import SavingsGoal
    client.post("/savings/create", data={"name": "Buang-ku", "target_amount": "1000"})
    db = get_test_db()
    try:
        goal_id = db.query(SavingsGoal).filter_by(name="Buang-ku").first().id
    finally:
        db.close()
    assert client.get(f"/savings/delete/{goal_id}", follow_redirects=False).status_code == 303
    page = client.get("/savings")
    assert page.status_code == 200 and "Buang-ku" not in page.text


# =====================================================================
# Investments
# =====================================================================

def test_investments_page_renders_200(client):
    """GET /investments must render even with no holdings."""
    assert client.get("/investments").status_code == 200


def test_investment_create_adds_investment_to_list(client):
    """POST /investments/create must persist and list the holding."""
    resp = client.post("/investments/create", data={
        "name": "BBCA", "investment_type": "Saham",
        "amount_invested": "5000000", "current_value": "5500000",
        "purchase_date": "2026-01-15", "notes": "blue chip", "icon": "📈",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/investments")
    assert page.status_code == 200 and "BBCA" in page.text


def test_investment_edit_form_renders_200_and_updates_value(client):
    """GET then POST /investments/edit/<id> must update current_value."""
    from app.models.models import Investment
    client.post("/investments/create", data={
        "name": "Emas Antum", "investment_type": "Emas",
        "amount_invested": "2000000", "current_value": "2200000",
    })
    db = get_test_db()
    try:
        inv_id = db.query(Investment).filter_by(name="Emas Antum").first().id
    finally:
        db.close()
    assert client.get(f"/investments/edit/{inv_id}").status_code == 200
    resp = client.post(f"/investments/edit/{inv_id}", data={
        "name": "Emas Antum", "investment_type": "Emas",
        "amount_invested": "2000000", "current_value": "2500000",
        "purchase_date": "", "notes": "", "icon": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db = get_test_db()
    try:
        assert db.query(Investment).filter_by(id=inv_id).first().current_value == 2_500_000
    finally:
        db.close()


def test_investment_edit_missing_returns_404(client):
    """Editing a non-existent investment must 404."""
    assert client.post("/investments/edit/99999", data={
        "name": "X", "investment_type": "Saham",
        "amount_invested": "1", "current_value": "1",
    }).status_code == 404


def test_investment_delete_removes_investment_from_list(client):
    """GET /investments/delete/<id> must remove the holding."""
    from app.models.models import Investment
    client.post("/investments/create", data={
        "name": "Buang-ku", "investment_type": "Crypto",
        "amount_invested": "100000", "current_value": "90000",
    })
    db = get_test_db()
    try:
        inv_id = db.query(Investment).filter_by(name="Buang-ku").first().id
    finally:
        db.close()
    assert client.get(f"/investments/delete/{inv_id}", follow_redirects=False).status_code == 303
    page = client.get("/investments")
    assert page.status_code == 200 and "Buang-ku" not in page.text


# =====================================================================
# Assets
# =====================================================================

def test_assets_page_renders_200(client):
    """GET /assets must render even with no assets."""
    assert client.get("/assets").status_code == 200


def test_asset_create_adds_asset_to_list(client):
    """POST /assets/create must persist and list the asset."""
    resp = client.post("/assets/create", data={
        "name": "Motor Matic", "asset_type": "Kendaraan",
        "current_value": "18000000", "purchase_value": "22000000",
        "purchase_date": "2024-06-01", "notes": "honda", "icon": "🏍️",
    }, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/assets")
    assert page.status_code == 200 and "Motor Matic" in page.text


def test_asset_edit_form_renders_200_and_updates_value(client):
    """GET then POST /assets/edit/<id> must update current_value."""
    from app.models.models import AssetRecord
    client.post("/assets/create", data={
        "name": "Laptop", "asset_type": "Elektronik", "current_value": "8000000",
    })
    db = get_test_db()
    try:
        asset_id = db.query(AssetRecord).filter_by(name="Laptop").first().id
    finally:
        db.close()
    assert client.get(f"/assets/edit/{asset_id}").status_code == 200
    resp = client.post(f"/assets/edit/{asset_id}", data={
        "name": "Laptop", "asset_type": "Elektronik",
        "current_value": "7000000", "purchase_value": "",
        "purchase_date": "", "notes": "", "icon": "",
    }, follow_redirects=False)
    assert resp.status_code == 303
    db = get_test_db()
    try:
        assert db.query(AssetRecord).filter_by(id=asset_id).first().current_value == 7_000_000
    finally:
        db.close()


def test_asset_delete_removes_asset_from_list(client):
    """GET /assets/delete/<id> must remove the asset."""
    from app.models.models import AssetRecord
    client.post("/assets/create", data={
        "name": "Buang-ku", "asset_type": "Lainnya", "current_value": "1000",
    })
    db = get_test_db()
    try:
        asset_id = db.query(AssetRecord).filter_by(name="Buang-ku").first().id
    finally:
        db.close()
    assert client.get(f"/assets/delete/{asset_id}", follow_redirects=False).status_code == 303
    page = client.get("/assets")
    assert page.status_code == 200 and "Buang-ku" not in page.text


# =====================================================================
# Exports
# =====================================================================

def test_transactions_export_contains_added_transaction(client):
    """GET /transactions/export must include the tx added beforehand."""
    aid = _acc_id("BCA")
    client.post("/transactions/add", data={
        "type": "EXPENSE", "amount": "25000", "account_id": str(aid),
        "category_id": str(_cat_id("Makan & Minum")),
        "transfer_to_account_id": "", "date_val": "2026-09-12",
        "description": "Kopi Export", "merchant": "",
    })
    resp = client.get("/transactions/export")
    assert resp.status_code == 200
    assert "Kopi Export" in resp.text


def test_reports_export_renders_200(client):
    """GET /reports/export must render 200."""
    assert client.get("/reports/export").status_code == 200
