"""Account service - all account business logic lives here.

Both the Jinja HTML routes and the REST API call these functions; financial
calculations are never duplicated at the route layer.
"""
from sqlalchemy.orm import Session

from app.models.models import Account, AccountType, Debt, DebtStatus, DebtType
from app.services.finance import recalculate_account_balance

# Account classification used for net-worth / dashboard calculations.
ASSET_ACCOUNT_TYPES = [
    AccountType.CASH, AccountType.BANK, AccountType.E_WALLET,
    AccountType.SAVINGS, AccountType.INVESTMENT,
]
LIQUID_ACCOUNT_TYPES = [
    AccountType.CASH, AccountType.BANK, AccountType.E_WALLET, AccountType.SAVINGS,
]
LIABILITY_ACCOUNT_TYPES = [
    AccountType.CREDIT_CARD, AccountType.LOAN, AccountType.LIABILITY,
]

ACCOUNT_GROUPS = [
    ("Rekening & Kas", ASSET_ACCOUNT_TYPES),
    ("Kartu Kredit & Hutang", LIABILITY_ACCOUNT_TYPES),
    ("Investasi & Aset", [AccountType.INVESTMENT, AccountType.ASSET]),
    ("Lainnya", [AccountType.OTHER]),
]


class AccountNotFound(Exception):
    pass


class AccountInUse(Exception):
    """Deleting would break existing transaction references -> HTTP 409."""


def _visible_account_query(db: Session, user_id: int):
    """Own accounts + global master accounts (user_id NULL)."""
    return db.query(Account).filter(
        (Account.user_id == user_id) | (Account.user_id.is_(None))
    )


def get_account(db: Session, account_id: int, user_id: int) -> Account | None:
    return (
        _visible_account_query(db, user_id)
        .filter(Account.id == account_id)
        .first()
    )


def get_account_or_raise(db: Session, account_id: int, user_id: int) -> Account:
    acc = get_account(db, account_id, user_id)
    if not acc:
        raise AccountNotFound(f"Account {account_id} not found")
    return acc


def get_own_account(db: Session, account_id: int, user_id: int) -> Account | None:
    """Strictly OWN account - used by update/delete so master rows stay safe."""
    return db.query(Account).filter(
        Account.id == account_id, Account.user_id == user_id
    ).first()


def list_accounts(db: Session, user_id: int):
    return (
        _visible_account_query(db, user_id)
        .order_by(Account.name)
        .all()
    )


def create_account(db: Session, *, user_id: int, name: str, type_: AccountType,
                   initial_balance: int = 0, icon: str | None = None,
                   institution: str | None = None,
                   account_number: str | None = None,
                   color: str | None = None,
                   credit_limit: int | None = None,
                   statement_date: int | None = None,
                   payment_due_day: int | None = None,
                   interest_rate_pct: float | None = None,
                   annual_fee: int | None = None,
                   card_network: str | None = None) -> Account:
    if not name or not name.strip():
        raise ValueError("Account name required")
    acct = Account(
        user_id=user_id, name=name.strip(), type=type_,
        initial_balance=initial_balance, current_balance=initial_balance,
        icon=icon or None, institution=institution,
        account_number=account_number, color=color,
        credit_limit=credit_limit, statement_date=statement_date,
        payment_due_day=payment_due_day, interest_rate_pct=interest_rate_pct,
        annual_fee=annual_fee, card_network=card_network,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def get_available_credit(acc: Account) -> int | None:
    """Canonical available-credit calc: credit_limit - outstanding liability.

    Outstanding = the absolute value of the negative current_balance (how much
    is owed). When a credit card has been paid past zero (credit balance),
    available credit is credit_limit minus 0.
    """
    if acc.type != AccountType.CREDIT_CARD:
        return None
    if acc.credit_limit is None:
        return None
    outstanding = max(0, -acc.current_balance)
    return acc.credit_limit - outstanding


def update_account(db: Session, account_id: int, user_id: int, **fields) -> Account:
    """Update only OWN accounts; master/global accounts are immutable."""
    acc = get_own_account(db, account_id, user_id)
    if not acc:
        raise AccountNotFound(f"Account {account_id} not found")
    initial_changed = False
    for key, value in fields.items():
        if value is None:
            continue
        if key == "type" and hasattr(value, "value"):
            value = value  # enum instance is fine for SQLAlchemy Enum column
        if key == "initial_balance":
            acc.initial_balance = value
            initial_changed = True
        else:
            setattr(acc, key, value)
    db.commit()
    if initial_changed:
        recalculate_account_balance(db, account_id, user_id)
    db.refresh(acc)
    return acc


def delete_account(db: Session, account_id: int, user_id: int) -> None:
    from app.models.models import Transaction
    acc = get_own_account(db, account_id, user_id)
    if not acc:
        raise AccountNotFound(f"Account {account_id} not found")
    used = db.query(Transaction.id).filter(
        Transaction.user_id == user_id,
        (Transaction.account_id == account_id) |
        (Transaction.transfer_to_account_id == account_id)
    ).first()
    if used:
        raise AccountInUse(f"Account {account_id} still has transactions")
    db.delete(acc)
    db.commit()


def list_accounts_grouped(db: Session, user_id: int) -> list[dict]:
    """Group accounts by category with per-group totals (HTML accounts page)."""
    accounts = list_accounts(db, user_id)
    groups = []
    for group_name, types in ACCOUNT_GROUPS:
        members = [a for a in accounts if a.type in types]
        if members:
            groups.append({
                "name": group_name, "accounts": members,
                "total": sum(a.current_balance for a in members),
            })
    return groups


def compute_net_worth(db: Session, user_id: int) -> dict:
    """Single source of truth for net-worth math - strictly per-user.

    total_assets      = balances of asset-side accounts + asset records +
                        investment holdings
    total_liabilities = absolute negative balances of liability-side accounts
                        + remaining PAYABLE debts
    available_cash    = liquid money only
    """
    from sqlalchemy import func

    from app.models.models import AssetRecord, Investment

    accounts = db.query(Account).filter(Account.user_id == user_id).all()
    total_assets = sum(
        a.current_balance for a in accounts if a.type in ASSET_ACCOUNT_TYPES
    )
    total_assets += db.query(func.coalesce(func.sum(AssetRecord.current_value), 0)).filter(
        AssetRecord.user_id == user_id
    ).scalar()
    total_assets += db.query(func.coalesce(func.sum(Investment.current_value), 0)).filter(
        Investment.user_id == user_id
    ).scalar()

    unpaid_debt = db.query(func.coalesce(func.sum(Debt.remaining_amount), 0)).filter(
        Debt.user_id == user_id,
        Debt.type == DebtType.PAYABLE, Debt.status != DebtStatus.PAID,
    ).scalar()
    total_receivables = db.query(func.coalesce(func.sum(Debt.remaining_amount), 0)).filter(
        Debt.user_id == user_id,
        Debt.type == DebtType.RECEIVABLE, Debt.status != DebtStatus.PAID,
    ).scalar()

    total_liabilities = sum(
        abs(min(a.current_balance, 0))
        for a in accounts if a.type in LIABILITY_ACCOUNT_TYPES
    ) + unpaid_debt

    available_cash = sum(
        a.current_balance for a in accounts if a.type in LIQUID_ACCOUNT_TYPES
    )
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
        "available_cash": available_cash,
        "total_debt": unpaid_debt,
        "total_receivables": total_receivables,
    }
