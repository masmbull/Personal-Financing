doc = """Category seed taxonomy - global Indonesian categories. Idempotent via slug."""
from sqlalchemy.orm import Session
from app.models.models import Category, TransactionType

TAXONOMY = {
    TransactionType.EXPENSE: [
        ("food", "Makanan & Minuman", "\U0001f35c", None, [
            ("food_dining", "Makan di Luar", "\U0001f373"),
            ("food_grocery", "Belanja Bahan Makanan", "\U0001f6d2"),
            ("food_coffee", "Kopi & Minuman", "\u2615"),
            ("food_delivery", "Pesan Antar", "\U0001f3cd"),
            ("food_hangout", "Nongkrong", "\U0001f46b"),
        ]),
        ("transport", "Transportasi", "\u26fd", None, [
            ("transport_fuel", "BBM", "\u26fd"),
            ("transport_parking", "Parkir", "\U0001f17f"),
            ("transport_toll", "Tol", "\U0001f6e1"),
            ("transport_online", "Transportasi Online", "\U0001f696"),
            ("transport_public", "Transportasi Umum", "\U0001f684"),
                        ("transport_service", "Servis & Perawatan Kendaraan", "\U0001f527"),
        ]),
        ("shopping", "Belanja", "\U0001f6d2", None, [
            ("shopping_home", "Kebutuhan Rumah", "\U0001f3de"),
            ("shopping_clothing", "Pakaian", "\U0001f45a"),
            ("shopping_electronics", "Elektronik", "\U0001f4bb"),
            ("shopping_personal", "Personal Care", "\U0001faa7"),
            ("shopping_hobby", "Hobi", "\U0001f3a8"),
        ]),
        ("bills", "Tagihan & Utilitas", "\U0001f4a1", None, [
            ("bills_electricity", "Listrik", "\U0001f4a1"),
            ("bills_water", "Air", "\U0001f6b0"),
            ("bills_internet", "Internet", "\U0001f310"),
            ("bills_pulsa", "Pulsa & Paket Data", "\U0001f4f1"),
            ("bills_digital", "Langganan Digital", "\U0001f4fd"),
        ]),
        ("housing", "Rumah & Tempat Tinggal", "\U0001f3e2", None, [
            ("housing_rent", "Sewa / Kos", "\U0001f3e1"),
            ("housing_kpr", "KPR", "\U0001f3eb"),
            ("housing_maintenance", "Perawatan Rumah", "\U0001f527"),
        ]),
        ("health", "Kesehatan", "\U0001f3e5", None, [
            ("health_medicine", "Obat", "\U0001f48a"),
            ("health_doctor", "Dokter", "\U0001f468\u200d\U0001f3eb"),
            ("health_hospital", "Rumah Sakit", "\U0001f3e5"),
            ("health_insurance", "Asuransi Kesehatan", "\U0001f6e1"),
        ]),
        ("education", "Pendidikan", "\U0001f4da", None, [
            ("education_school", "Sekolah / Kuliah", "\U0001f3eb"),
            ("education_course", "Kursus", "\U0001f468\u200d\U0001f4bb"),
            ("education_books", "Buku", "\U0001f4d6"),
        ]),
        ("family", "Keluarga", "\U0001f468\u200d\U0001f469\u200d\U0001f467", None, [
            ("family_parents", "Orang Tua", "\U0001f474"),
            ("family_children", "Anak", "\U0001f476"),
            ("family_partner", "Pasangan", "\U0001f491"),
        ]),
        ("finance", "Keuangan", "\U0001f4b3", None, [
            ("finance_bank_fee", "Biaya Admin Bank", "\U0001f3e6"),
            ("finance_transfer", "Biaya Transfer", "\U0001f4b8"),
            ("finance_interest", "Bunga / Finance Charge", "\U0001f4c8"),
            ("finance_tax", "Pajak", "\U0001f4ca"),
        ]),
        ("social", "Hiburan & Sosial", "\U0001f389", None, [
            ("social_entertainment", "Hiburan", "\U0001f3d7"),
            ("social_event", "Acara", "\U0001f3aa"),
            ("social_donation", "Donasi", "\U0001f942"),
            ("social_gift", "Hadiah", "\U0001f381"),
        ]),
        ("travel", "Perjalanan", "\u2708", None, [
            ("travel_ticket", "Tiket", "\U0001f39b"),
            ("travel_hotel", "Hotel / Penginapan", "\U0001f3e8"),
            ("travel_activity", "Aktivitas", "\U0001f5fa"),
        ]),
        ("vehicle", "Kendaraan", "\U0001f697", None, [
            ("vehicle_installment", "Cicilan Kendaraan", "\U0001f3f7"),
            ("vehicle_service", "Servis", "\U0001f527"),
            ("vehicle_tax", "Pajak Kendaraan", "\U0001f4ca"),
            ("vehicle_insurance", "Asuransi Kendaraan", "\U0001f6e1"),
        ]),
        ("other", "Lainnya", "\U0001f4c4", None, [
            ("other_expense", "Pengeluaran Lainnya", "\U0001f4c4"),
        ]),
        ],
    TransactionType.INCOME: [
        ("salary", "Gaji", "\U0001f4b0", None, [
            ("salary_base", "Gaji Utama", "\U0001f4b0"),
            ("salary_bonus", "Bonus", "\U0001f381"),
            ("salary_thr", "THR", "\U0001f911"),
        ]),
        ("freelance", "Freelance & Bisnis", "\U0001f4bc", None, [
            ("freelance_income", "Freelance", "\U0001f4bb"),
            ("freelance_sales", "Penjualan", "\U0001f4e6"),
            ("freelance_commission", "Komisi", "\U0001f4c8"),
        ]),
        ("investment", "Investasi", "\U0001f4c8", None, [
            ("investment_dividend", "Dividen", "\U0001f4b0"),
            ("investment_interest", "Bunga", "\U0001f4c8"),
            ("investment_capital_gain", "Capital Gain", "\U0001f4c8"),
        ]),
        ("gift", "Hadiah", "\U0001f381", None, [
            ("gift_income", "Hadiah", "\U0001f381"),
        ]),
        ("refund", "Refund", "\u21a9", None, [
            ("refund_income", "Refund", "\u21a9"),
        ]),
        ("other", "Pendapatan Lainnya", "\U0001f4c4", None, [
            ("other_income", "Pendapatan Lainnya", "\U0001f4c4"),
        ]),
        ("transfer_in", "Transfer Masuk", "\U0001f504", None, [
            ("transfer_in_income", "Transfer Masuk", "\U0001f504"),
        ]),
    ],
}


def _find(db, tx_type, slug):
    return db.query(Category).filter(
        Category.type == tx_type, Category.slug == slug
    ).first()


def seed_categories(db) -> int:
    """Idempotently seed the global category hierarchy.  Returns created count.

    - Match by (type, slug) so re-running never duplicates.
    - Existing categories without slug are left untouched (preserved).
    - Parent name/icon/slug updated in place; parent_id set to NULL for roots.
    - Children get parent_id pointing at their parent.
    """
    created = 0
    for tx_type, groups in TAXONOMY.items():
        for pslug, pname, picon, _pid, children in groups:
            parent = _find(db, tx_type, pslug)
            if parent is None:
                parent = Category(
                    name=pname, type=tx_type, icon=picon, slug=pslug,
                    parent_id=None, is_default=1, group=pname,
                )
                db.add(parent)
                created += 1
            else:
                if parent.name != pname or parent.icon != picon or parent.parent_id is not None:
                    parent.name = pname
                    parent.icon = picon
                    parent.parent_id = None
                    parent.group = pname
            db.flush()
            for cslug, cname, cicon in children:
                child = _find(db, tx_type, cslug)
                if child is None:
                    child = Category(
                        name=cname, type=tx_type, icon=cicon, slug=cslug,
                        parent_id=parent.id, is_default=1, group=pname,
                    )
                    db.add(child)
                    created += 1
                else:
                    if child.name != cname or child.icon != cicon or child.parent_id != parent.id:
                        child.name = cname
                        child.icon = cicon
                        child.parent_id = parent.id
                        child.group = pname
    db.commit()
    return created
