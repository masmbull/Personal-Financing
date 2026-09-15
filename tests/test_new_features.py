"""Tests for the 4 new features: Tags, CSV Import, Health Score, Insights."""
import pytest
from tests.conftest import default_user_id
from app.services.tags import (
    create_tag, list_tags, delete_tag, attach_tags,
    tags_for_transaction, tags_for_transactions, TagNotFound,
)
from app.services.csv_import import parse_csv, _parse_date, _parse_amount
from app.services.insights import _rp


# ── Tags ──────────────────────────────────────────────────

class TestTagsCRUD:
    def test_create_and_list(self, db):
        uid = default_user_id()
        t1 = create_tag(db, uid, "Makan")
        t2 = create_tag(db, uid, "Transport")
        assert t1["name"] == "Makan"
        tags = list_tags(db, uid)
        assert len(tags) == 2

    def test_create_duplicate_returns_existing(self, db):
        uid = default_user_id()
        t1 = create_tag(db, uid, "Makan")
        t2 = create_tag(db, uid, "Makan")
        assert t1["id"] == t2["id"]

    def test_delete_tag(self, db):
        uid = default_user_id()
        t = create_tag(db, uid, "Hapus")
        delete_tag(db, t["id"], uid)
        assert list_tags(db, uid) == []

    def test_delete_nonexistent_raises(self, db):
        uid = default_user_id()
        with pytest.raises(TagNotFound):
            delete_tag(db, 99999, uid)

    def test_attach_and_fetch_tags(self, db):
        uid = default_user_id()
        t1 = create_tag(db, uid, "Tag A")
        t2 = create_tag(db, uid, "Tag B")
        attach_tags(db, 1, [t1["id"], t2["id"]], uid)
        tags = tags_for_transaction(db, 1)
        assert len(tags) == 2

    def test_bulk_fetch(self, db):
        uid = default_user_id()
        t = create_tag(db, uid, "Bulk")
        attach_tags(db, 10, [t["id"]], uid)
        result = tags_for_transactions(db, [10, 11], uid)
        assert 10 in result
        assert 11 in result


# ── CSV Import ─────────────────────────────────────────────

class TestCSVImport:
    def test_parse_date_formats(self):
        assert _parse_date("2024-01-15") is not None
        assert _parse_date("15/01/2024") is not None
        assert _parse_date("15/01/24") is not None
        assert _parse_date("invalid") is None
        assert _parse_date("") is None

    def test_parse_amount_rupiah(self):
        assert _parse_amount("Rp 1.234.567") == 1234567
        assert _parse_amount("-50000") == -50000
        assert _parse_amount("1234567") == 1234567
        assert _parse_amount("Rp50.000") == 50000
        assert _parse_amount("") is None

    def test_parse_csv_basic(self):
        csv = "Tanggal,Keterangan,Jumlah\n2024-01-15,Indomaret,50000\n16/01/2024,Gaji,5000000\n"
        r = parse_csv(csv)
        assert len(r["rows"]) == 2
        assert r["errors"] == []
        assert r["rows"][0]["amount"] == 50000
        assert r["rows"][1]["amount"] == 5000000

    def test_parse_csv_empty(self):
        r = parse_csv("")
        assert r["rows"] == []
        assert len(r["errors"]) > 0

    def test_parse_csv_bad_date_skips(self):
        csv = "date,description,amount\nbad-date,desc,100\n2024-01-01,ok,200\n"
        r = parse_csv(csv)
        assert len(r["rows"]) == 1
        assert r["rows"][0]["amount"] == 200

    def test_parse_csv_semicolon_delimiter(self):
        csv = "date;description;amount\n2024-01-01;test;1000\n"
        r = parse_csv(csv, delimiter=";")
        assert len(r["rows"]) == 1

    def test_detect_columns_indonesian(self):
        csv = "Tanggal,Keterangan,Jumlah\n2024-01-01,test,100\n"
        r = parse_csv(csv)
        assert r["column_map"]["date"] is not None
        assert r["column_map"]["description"] is not None
        assert r["column_map"]["amount"] is not None


# ── Rupiah formatter ──────────────────────────────────────

class TestInsightsRp:
    def test_rp_formatting(self):
        assert _rp(50000) == "Rp 50.000"
        assert _rp(1500000) == "Rp 1.500.000"
        assert _rp(-100000) == "-Rp 100.000"
        assert _rp(0) == "Rp 0"
