import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Enum, Date, DateTime, ForeignKey, Text, Float, Boolean
)
from sqlalchemy.orm import relationship
from app.database.db import Base


class AccountType(str, enum.Enum):
    CASH = "CASH"
    BANK = "BANK"
    E_WALLET = "E_WALLET"
    CREDIT_CARD = "CREDIT_CARD"
    SAVINGS = "SAVINGS"
    LOAN = "LOAN"
    INVESTMENT = "INVESTMENT"
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    OTHER = "OTHER"


class TransactionType(str, enum.Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"


class DebtType(str, enum.Enum):
    RECEIVABLE = "RECEIVABLE"
    PAYABLE = "PAYABLE"


class DebtStatus(str, enum.Enum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"


class BillFrequency(str, enum.Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"
    CUSTOM = "CUSTOM"


class BillStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PAID = "PAID"


class User(Base):
    """Application user. Plaintext passwords are NEVER stored here."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), nullable=False, unique=True, index=True)
    password_hash = Column(String(256), nullable=False)  # PBKDF2 string
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSession(Base):
    """Server-side session record; the cookie only carries an opaque token
    whose SHA-256 hash is stored here. Logout revokes the row."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)

    user = relationship("User")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment="NULL = global master data (seeded banks/e-wallets)")
    name = Column(String(100), nullable=False)
    type = Column(Enum(AccountType), nullable=False, default=AccountType.OTHER)
    institution = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)
    color = Column(String(7), nullable=True)
    initial_balance = Column(Integer, nullable=False, default=0)
    current_balance = Column(Integer, nullable=False, default=0)
    icon = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="account", foreign_keys="Transaction.account_id")
    dest_transfers = relationship("Transaction", foreign_keys="Transaction.transfer_to_account_id", overlaps="transfer_to_account")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(Enum(TransactionType), nullable=False)
    slug = Column(String(100), nullable=True, index=True)
    group = Column(String(50), nullable=True)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True, index=True)
    icon = Column(String(10), nullable=True)
    is_default = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("Transaction", back_populates="category")
    parent = relationship('Category', remote_side='Category.id', back_populates='children')
    children = relationship('Category', back_populates='parent', order_by='Category.name')


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Integer, nullable=False)  # in rupiah, integer
    description = Column(Text, nullable=True)
    merchant = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    date = Column(Date, nullable=False, default=date.today)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    transfer_to_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="transactions", foreign_keys=[account_id])
    category = relationship("Category", back_populates="transactions")
    transfer_to_account = relationship("Account", foreign_keys=[transfer_to_account_id], overlaps="dest_transfers")


class Debt(Base):
    __tablename__ = "debts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(Enum(DebtType), nullable=False)
    person_name = Column(String(100), nullable=False)
    person_contact = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    principal_amount = Column(Integer, nullable=False)
    remaining_amount = Column(Integer, nullable=False)
    interest_rate = Column(Float, nullable=True)
    start_date = Column(Date, nullable=False, default=date.today)
    due_date = Column(Date, nullable=True)
    installment_amount = Column(Integer, nullable=True)
    installment_count = Column(Integer, nullable=True)
    status = Column(Enum(DebtStatus), nullable=False, default=DebtStatus.OPEN)
    notes = Column(Text, nullable=True)
    related_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    related_account = relationship("Account")
    payments = relationship("DebtPayment", back_populates="debt", order_by="DebtPayment.payment_date.desc()")


class DebtPayment(Base):
    __tablename__ = "debt_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    debt_id = Column(Integer, ForeignKey("debts.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    payment_date = Column(Date, nullable=False, default=date.today)
    notes = Column(Text, nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    debt = relationship("Debt", back_populates="payments")
    transaction = relationship("Transaction")


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    amount = Column(Integer, nullable=False)
    frequency = Column(Enum(BillFrequency), nullable=False, default=BillFrequency.MONTHLY)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    due_day = Column(Integer, nullable=True)
    auto_create = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("Category")
    account = relationship("Account")


class BillPayment(Base):
    __tablename__ = "bill_payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    paid_date = Column(Date, nullable=False, default=date.today)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bill = relationship("Bill")
    transaction = relationship("Transaction")


class SavingsGoal(Base):
    __tablename__ = "savings_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    target_amount = Column(Integer, nullable=False)
    current_amount = Column(Integer, nullable=False, default=0)
    icon = Column(String(10), nullable=True)
    color = Column(String(7), nullable=True)
    active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = relationship("SavingsGoalTransaction", back_populates="goal",
                               order_by="SavingsGoalTransaction.created_at.desc()")


class SavingsGoalTransaction(Base):
    __tablename__ = "savings_goal_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    goal_id = Column(Integer, ForeignKey("savings_goals.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    notes = Column(Text, nullable=True)
    related_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    goal = relationship("SavingsGoal", back_populates="transactions")
    related_account = relationship("Account")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("Category")


class AssetRecord(Base):
    __tablename__ = "asset_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    asset_type = Column(String(50), nullable=False)
    current_value = Column(Integer, nullable=False)
    purchase_value = Column(Integer, nullable=True)
    purchase_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    icon = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Investment(Base):
    __tablename__ = "investments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    investment_type = Column(String(50), nullable=False)
    amount_invested = Column(Integer, nullable=False)
    current_value = Column(Integer, nullable=False)
    purchase_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    icon = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ReceiptStatus(str, enum.Enum):
    PENDING = "PENDING"      # UPLOADED, waiting for OCR
    PROCESSING = "PROCESSING"  # OCR running
    PROCESSED = "PROCESSED"  # READY - OCR produced structured data (never auto-posted)
    FAILED = "FAILED"        # OCR processing failed
    CONFIRMED = "CONFIRMED"  # user confirmed -> may be turned into a transaction


class Receipt(Base):
    """Uploaded receipt image. OCR results are stored separately and NEVER
    automatically create financial transactions without user confirmation."""
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=True)
    stored_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    ocr_status = Column(Enum(ReceiptStatus), nullable=False, default=ReceiptStatus.PENDING)
    ocr_data = Column(Text, nullable=True)  # JSON blob of structured OCR output when available
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True,
                            comment="Set only when the USER confirms -> explicit transaction")
    file_hash = Column(String(64), nullable=True, index=True,
                       comment="SHA-256 of original upload for duplicate detection")
    created_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction")


class NetWorthSnapshot(Base):
    """Daily net-worth point so reports can show trends over time."""
    __tablename__ = "net_worth_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    total_assets = Column(Integer, nullable=False)
    total_liabilities = Column(Integer, nullable=False)
    net_worth = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

