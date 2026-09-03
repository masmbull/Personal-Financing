import enum
from datetime import datetime, timezone, date
from sqlalchemy import (
    Column, Integer, String, Enum, Date, DateTime, ForeignKey, Text, Float,
    Boolean, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database.db import Base
from datetime import timezone


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AccountType(str, enum.Enum):
    CASH = "CASH"
    BANK = "BANK"
    E_WALLET = "E_WALLET"
    SERVER_EMONEY = "SERVER_EMONEY"      # server-based electronic money
    CARD_EMONEY = "CARD_EMONEY"          # card-based electronic money (Flazz, e-Money)
    CREDIT_CARD = "CREDIT_CARD"
    PAY_LATER = "PAY_LATER"              # PayLater / BNPL
    SAVINGS = "SAVINGS"
    LOAN = "LOAN"
    INVESTMENT = "INVESTMENT"
    GOLD = "GOLD"
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    OTHER = "OTHER"


class MerchantType(str, enum.Enum):
    RETAIL = "RETAIL"
    GROCERY = "GROCERY"
    FOOD_BEVERAGE = "FOOD_BEVERAGE"
    TRANSPORT = "TRANSPORT"
    DIGITAL = "DIGITAL"
    TELECOM = "TELECOM"
    FINANCIAL = "FINANCIAL"
    UTILITIES = "UTILITIES"
    HEALTHCARE = "HEALTHCARE"
    EDUCATION = "EDUCATION"
    ENTERTAINMENT = "ENTERTAINMENT"
    GOVERNMENT = "GOVERNMENT"
    MARKETPLACE = "MARKETPLACE"
    OTHER = "OTHER"


class InstitutionType(str, enum.Enum):
    """Indonesian financial-institution classifications (OJK-recognised).
    Values only describe institutional category; specific licensing claims
    belong in FinancialInstitution.notes, never in this enum.
    """
    COMMERCIAL_BANK = "COMMERCIAL_BANK"
    SHARIA_BANK = "SHARIA_BANK"
    DIGITAL_BANK = "DIGITAL_BANK"
    RURAL_BANK = "RURAL_BANK"          # BPR
    SHARIA_RURAL_BANK = "SHARIA_RURAL_BANK"  # BPRS
    E_MONEY_ISSUER = "E_MONEY_ISSUER"  # uang elektronik berizin BI
    E_WALLET_OPERATOR = "E_WALLET_OPERATOR"
    PAYMENT_SERVICE = "PAYMENT_SERVICE"
    INSURANCE = "INSURANCE"
    SECURITIES = "SECURITIES"
    P2P_LENDING = "P2P_LENDING"
    OTHER_LICENSED = "OTHER_LICENSED"


class PaymentMethodType(str, enum.Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    VIRTUAL_ACCOUNT = "VIRTUAL_ACCOUNT"
    DEBIT_CARD = "DEBIT_CARD"
    CREDIT_CARD = "CREDIT_CARD"
    QRIS = "QRIS"
    EWALLET = "EWALLET"
    DIRECT_DEBIT = "DIRECT_DEBIT"
    AUTO_DEBIT = "AUTO_DEBIT"
    PAYLATER = "PAYLATER"
    OTHER = "OTHER"


class TransactionType(str, enum.Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    TRANSFER = "TRANSFER"
    # Principal repayment of a Debt (PAYABLE). Cash decreases, debt liability
    # decreases; NOT counted as expense in income/expense totals.
    DEBT_REPAYMENT = "DEBT_REPAYMENT"
    # Collection of a Debt (RECEIVABLE). Cash increases, debt receivable
    # decreases; NOT counted as income in income/expense totals.
    DEBT_COLLECTION = "DEBT_COLLECTION"
    # Refund of a prior purchase back to an account (e.g. credit-card charge
    # reversal). Increases the account balance (liability down) but is NOT
    # counted as income.
    REFUND = "REFUND"


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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class UserSession(Base):
    """Server-side session record; the cookie only carries an opaque token
    whose SHA-256 hash is stored here. Logout revokes the row."""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
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
    institution_id = Column(Integer, ForeignKey("financial_institutions.id"), nullable=True,
                             index=True, comment="Optional FK to master financial_institutions row")
    # Credit-card specific fields (only meaningful when type=CREDIT_CARD)
    credit_limit = Column(Integer, nullable=True, comment="Max credit in rupiah")
    statement_date = Column(Integer, nullable=True, comment="Day of month for statement close (1-28)")
    payment_due_day = Column(Integer, nullable=True, comment="Day of month payment is due (1-28)")
    interest_rate_pct = Column(Float, nullable=True, comment="Annual interest rate %")
    annual_fee = Column(Integer, nullable=True, comment="Annual fee in rupiah")
    card_network = Column(String(20), nullable=True, comment="Visa, Mastercard, JCB, GPN")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    transactions = relationship("Transaction", back_populates="account", foreign_keys="Transaction.account_id")
    dest_transfers = relationship("Transaction", foreign_keys="Transaction.transfer_to_account_id", overlaps="transfer_to_account")
    institution_ref = relationship("FinancialInstitution", back_populates="accounts",
                                    foreign_keys=[institution_id])


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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=True, index=True,
                         comment="Canonical merchant entity (nullable for legacy)")
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True, index=True)
    fuel_product_id = Column(Integer, ForeignKey("fuel_products.id"), nullable=True)
    quantity_liters = Column(Float, nullable=True)
    price_per_liter = Column(Integer, nullable=True, comment="Snapshot at time of transaction")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    account = relationship("Account", back_populates="transactions", foreign_keys=[account_id])
    category = relationship("Category", back_populates="transactions")
    transfer_to_account = relationship("Account", foreign_keys=[transfer_to_account_id], overlaps="dest_transfers")
    merchant_ref = relationship("Merchant")
    payment_method_ref = relationship("PaymentMethod")
    fuel_product_ref = relationship("FuelProduct")


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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)

    bill = relationship("Bill")
    transaction = relationship("Transaction")


class BillOccurrenceStatus(str, enum.Enum):
    DUE = "DUE"          # generated by the scheduler, not yet paid
    PAID = "PAID"        # settled (links to a bill payment)
    SKIPPED = "SKIPPED"  # explicitly skipped / disabled


class BillOccurrence(Base):
    """One scheduled occurrence of a recurring bill, generated by the
    bill auto-post job.

    Idempotency key: (bill_id, due_date). The scheduler only inserts a row
    when that (bill, date) pair does not already exist, so running it twice
    can never create a duplicate occurrence. An occurrence is UNPAID work -
    the scheduler NEVER silently moves money; a real expense transaction is
    only made when the user pays the occurrence through the normal flow.
    """
    __tablename__ = "bill_occurrences"
    __table_args__ = (
        # Deterministic idempotency - one occurrence per (bill, due date).
        UniqueConstraint("bill_id", "due_date", name="uq_bill_occurrence"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    status = Column(Enum(BillOccurrenceStatus), nullable=False,
                    default=BillOccurrenceStatus.DUE)
    # Set when this occurrence is paid (links the corresponding bill payment).
    bill_payment_id = Column(Integer, ForeignKey("bill_payments.id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    bill = relationship("Bill")
    bill_payment = relationship("BillPayment")


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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


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
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


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
    created_at = Column(DateTime, default=_utcnow)

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
    created_at = Column(DateTime, default=_utcnow)


# ── Merchant domain ──────────────────────────────────────────────────

class Merchant(Base):
    """Global master merchants (user_id=NULL) and user-custom merchants."""
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment="NULL = global master merchant")
    canonical_name = Column(String(200), nullable=False)
    display_name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), nullable=False, index=True,
                             comment="lowercased + stripped for matching")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    merchant_type = Column(Enum(MerchantType), nullable=False, default=MerchantType.OTHER)
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    category = relationship("Category")
    aliases = relationship("MerchantAlias", back_populates="merchant", cascade="all, delete-orphan")


class MerchantAlias(Base):
    """Alternate spellings / OCR variants that resolve to a merchant."""
    __tablename__ = "merchant_aliases"

    id = Column(Integer, primary_key=True, index=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    alias = Column(String(200), nullable=False)
    normalized_alias = Column(String(200), nullable=False, index=True)
    source = Column(String(100), nullable=True)

    merchant = relationship("Merchant", back_populates="aliases")


# ── Payment Method domain ────────────────────────────────────────────

class PaymentMethod(Base):
    """Payment method: separate from Account and Merchant.
    Global seed (user_id=NULL) for common Indonesian payment methods."""
    __tablename__ = "payment_methods"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment="NULL = global master payment method")
    name = Column(String(100), nullable=False)
    method_type = Column(Enum(PaymentMethodType), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ── Fuel / BBM domain ───────────────────────────────────────────────

class FuelBrand(Base):
    """Fuel operator brand (Pertamina, Shell, BP, Vivo, etc.)."""
    __tablename__ = "fuel_brands"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    country = Column(String(50), nullable=False, default="ID")
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    products = relationship("FuelProduct", back_populates="brand")


class FuelProduct(Base):
    """Specific fuel product (Pertamax, Pertalite, Shell V-Power, etc.)."""
    __tablename__ = "fuel_products"

    id = Column(Integer, primary_key=True, index=True)
    brand_id = Column(Integer, ForeignKey("fuel_brands.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    product_code = Column(String(50), nullable=True)
    fuel_type = Column(String(50), nullable=True, comment="gasoline, diesel")
    ron = Column(Integer, nullable=True, comment="Research Octane Number")
    cn = Column(Integer, nullable=True, comment="Cetane Number (diesel)")
    specification = Column(String(100), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    brand = relationship("FuelBrand", back_populates="products")
    prices = relationship("FuelPrice", back_populates="product")


class FuelPrice(Base):
    """Historical fuel price reference. Never mutated; old rows stay correct."""
    __tablename__ = "fuel_prices"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("fuel_products.id"), nullable=False, index=True)
    region = Column(String(100), nullable=False)
    price_per_liter = Column(Integer, nullable=False, comment="IDR per liter")
    currency = Column(String(3), nullable=False, default="IDR")
    effective_from = Column(Date, nullable=False, index=True)
    effective_until = Column(Date, nullable=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    product = relationship("FuelProduct", back_populates="prices")


# ── Financial Institution / E-Wallet Provider domain ────────────────

class FinancialInstitution(Base):
    """Master-data catalog of Indonesian financial institutions.

    user_id NULL = global master (seeded). Normal users may READ and
    REFERENCE (via Account.institution_id) but may NOT modify or delete.
    Stable attributes (legal_name, short_name, institution_type) reflect
    the institution as a whole, not its current account products.
    """
    __tablename__ = "financial_institutions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment="NULL = global master institution")
    code = Column(String(40), nullable=False,
                  comment="Stable short code (BCA, MANDIRI, BSI, GOPAY, ...)")
    legal_name = Column(String(200), nullable=False)
    short_name = Column(String(80), nullable=False)
    aliases = Column(Text, nullable=True,
                     comment="Comma-separated alternate names (legacy free-text inputs)")
    institution_type = Column(Enum(InstitutionType), nullable=False,
                              default=InstitutionType.OTHER_LICENSED)
    swift_bic = Column(String(11), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    __table_args__ = (
        UniqueConstraint("code", "user_id", name="uq_financial_institution_code"),
    )

    accounts = relationship("Account", back_populates="institution_ref",
                           foreign_keys="Account.institution_id")


class EWalletProvider(Base):
    """Master catalog of e-wallet / e-money operators (separate from
    FinancialInstitution because the product surface differs: an e-wallet
    is a stored-value account held at the operator, not a deposit account
    at a licensed bank).

    user_id NULL = global master. Aliases stored as a single text column
    (comma-separated) — provider aliases are short, normalised by lookup.
    """
    __tablename__ = "ewallet_providers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True,
                     comment="NULL = global master provider")
    code = Column(String(40), nullable=False,
                  comment="Stable short code (GOPAY, OVO, DANA, SHOPEEPAY, ...)")
    legal_name = Column(String(200), nullable=False)
    short_name = Column(String(80), nullable=False)
    aliases = Column(Text, nullable=True)
    operator_type = Column(String(40), nullable=True,
                           comment="e-money | e-wallet | paylater | qris-only")
    active = Column(Boolean, nullable=False, default=True)
    source = Column(String(100), nullable=True)
    source_url = Column(String(500), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    effective_from = Column(Date, nullable=True)
    effective_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    __table_args__ = (
        UniqueConstraint("code", "user_id", name="uq_ewallet_provider_code"),
    )

