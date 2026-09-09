"""Comprehensive numeric validation tests."""
import pytest
from fastapi.testclient import TestClient
from app.validation import (
    parse_idr_input, parse_optional_idr, parse_int_input, parse_float_input,
    validate_amount, MAX_MONEY,
)


class TestParseIdrInput:
    def test_plain_integer(self):
        assert parse_idr_input("10000") == 10000
    def test_thousand_separator_dots(self):
        assert parse_idr_input("10.000") == 10000
    def test_multi_thousand(self):
        assert parse_idr_input("1.000.000") == 1000000
    def test_rp_prefix(self):
        assert parse_idr_input("Rp 10.000") == 10000
    def test_rp_no_space(self):
        assert parse_idr_input("Rp10000") == 10000
    def test_comma_thousands_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("25,000")
    def test_dot_comma_european_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("10.000,50")
    def test_single_dot_decimal_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("25.50")
    def test_plus_prefix_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("+10000")
    def test_large_value(self):
        assert parse_idr_input("10.000.000.000") == 10_000_000_000
    def test_small_value(self):
        assert parse_idr_input("1") == 1
    def test_zero_rejected(self):
        with pytest.raises(ValueError, match="lebih dari 0"):
            parse_idr_input("0")
    def test_negative_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("-10000")
    def test_none_rejected(self):
        with pytest.raises(ValueError, match="harus diisi"):
            parse_idr_input(None)
    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="harus diisi"):
            parse_idr_input("")
    def test_letters_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("abc")
    def test_mixed_alpha_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("10abc")
    def test_trailing_letters_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("10000abc")
    def test_leading_letters_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("abc10000")
    def test_scientific_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("1e5")
    def test_infinity_rejected(self):
        with pytest.raises(ValueError):
            parse_idr_input(float("inf"))
    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            parse_idr_input(float("nan"))
    def test_string_nan_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("NaN")
    def test_dollar_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("$10000")
    def test_too_large_rejected(self):
        with pytest.raises(ValueError, match="terlalu besar"):
            parse_idr_input(str(MAX_MONEY + 1))
    def test_float_non_whole_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input(10000.5)
    def test_float_whole_accepted(self):
        assert parse_idr_input(10000.0) == 10000
    def test_malformed_dots_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("10..000")
    def test_malformed_multi_dot_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("1.2.3.4")
    def test_non_rupiah_prefix_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_idr_input("USD 10000")
    def test_field_name_error(self):
        with pytest.raises(ValueError, match="Jumlah"):
            parse_idr_input("abc", "Jumlah")



class TestParseOptionalIdr:
    def test_none_returns_none(self):
        assert parse_optional_idr(None) is None
    def test_empty_returns_none(self):
        assert parse_optional_idr("") is None
    def test_valid(self):
        assert parse_optional_idr("10.000") == 10000


class TestParseIntInput:
    def test_valid(self):
        assert parse_int_input("12") == 12
    def test_boundary_min(self):
        assert parse_int_input("1", min_val=1, max_val=12) == 1
    def test_boundary_max(self):
        assert parse_int_input("12", min_val=1, max_val=12) == 12
    def test_below_min_rejected(self):
        with pytest.raises(ValueError, match="antara"):
            parse_int_input("0", min_val=1, max_val=12)
    def test_decimal_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_int_input("1.5")
    def test_letters_rejected(self):
        with pytest.raises(ValueError, match="berupa angka"):
            parse_int_input("abc")
    def test_empty_rejected(self):
        with pytest.raises(ValueError, match="harus diisi"):
            parse_int_input("")
    def test_scientific_rejected(self):
        with pytest.raises(ValueError, match="angka bulat"):
            parse_int_input("1e3")


class TestParseFloatInput:
    def test_valid(self):
        assert parse_float_input("1.5") == 1.5
    def test_comma_decimal(self):
        assert parse_float_input("1,5") == 1.5
    def test_zero_disallowed(self):
        with pytest.raises(ValueError, match="lebih dari"):
            parse_float_input("0", allow_zero=False)
    def test_letters_rejected(self):
        with pytest.raises(ValueError, match="berupa angka"):
            parse_float_input("abc")
    def test_scientific_rejected(self):
        with pytest.raises(ValueError, match="tidak valid"):
            parse_float_input("1e5")
    def test_nan_rejected(self):
        with pytest.raises(ValueError):
            parse_float_input(float("nan"))
    def test_inf_rejected(self):
        with pytest.raises(ValueError):
            parse_float_input(float("inf"))


class TestValidateAmountLegacy:
    def test_valid_string(self):
        assert validate_amount("10000") == (10000, "")
    def test_idr_formatted(self):
        assert validate_amount("10.000") == (10000, "")
    def test_rp_prefixed(self):
        assert validate_amount("Rp 25.000") == (25000, "")
    def test_invalid_string(self):
        val, err = validate_amount("abc")
        assert val == 0 and err != ""
    def test_empty(self):
        assert validate_amount("") == (0, "")
    def test_none(self):
        assert validate_amount(None) == (0, "")



class TestFormRouteBypass:
    def test_tx_add_letters(self, client):
        accs = client.get("/api/v1/accounts").json()["items"]
        if not accs:
            pytest.skip("No accounts")
        resp = client.post("/transactions/add", data={
            "type": "EXPENSE", "amount": "abc",
            "account_id": str(accs[0]["id"]),
            "category_id": "1", "date_val": "2025-01-15",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_tx_add_idr_formatted(self, client):
        accs = client.get("/api/v1/accounts").json()["items"]
        if not accs:
            pytest.skip("No accounts")
        resp = client.post("/transactions/add", data={
            "type": "EXPENSE", "amount": "10.000",
            "account_id": str(accs[0]["id"]),
            "category_id": "1", "date_val": "2025-01-15",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_tx_add_rp_prefix(self, client):
        accs = client.get("/api/v1/accounts").json()["items"]
        if not accs:
            pytest.skip("No accounts")
        resp = client.post("/transactions/add", data={
            "type": "INCOME", "amount": "Rp 25.000",
            "account_id": str(accs[0]["id"]),
            "category_id": "5", "date_val": "2025-01-15",
        }, follow_redirects=False)
        assert resp.status_code == 303

    def test_transfer_scientific(self, client):
        accs = client.get("/api/v1/accounts").json()["items"]
        if len(accs) < 2:
            pytest.skip("Need 2 accounts")
        resp = client.post("/transfer", data={
            "from_account_id": str(accs[0]["id"]),
            "to_account_id": str(accs[1]["id"]),
            "amount": "1e5", "date_val": "2025-01-15",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_debt_mixed_alpha(self, client):
        resp = client.post("/debts/create", data={
            "type": "PAYABLE", "person_name": "Test",
            "principal_amount": "10000abc",
        }, follow_redirects=False)
        assert resp.status_code == 400

    def test_debt_idr_formatted(self, client):
        resp = client.post("/debts/create", data={
            "type": "PAYABLE", "person_name": "Test",
            "principal_amount": "1.000.000",
        }, follow_redirects=False)
        assert resp.status_code == 303


class TestApiBypass:
    def test_tx_nan(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": "NaN",
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_tx_infinity(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": "Infinity",
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_tx_letters(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": "abc",
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_tx_mixed(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": "100abc",
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_bill_infinity(self, client):
        resp = client.post("/api/v1/bills", json={
            "name": "Test", "amount": "Infinity",
        })
        assert resp.status_code in (400, 422)

    def test_budget_letters(self, client):
        resp = client.post("/api/v1/budgets", json={
            "category_id": 1, "amount": "abc",
            "month": 1, "year": 2025,
        })
        assert resp.status_code in (400, 422)

    def test_savings_letters(self, client):
        resp = client.post("/api/v1/savings", json={
            "name": "Test", "target_amount": "abc",
        })
        assert resp.status_code in (400, 422)


class TestExtremeValues:
    def test_max_tx_amount_accepted(self, client):
        from app.services.finance import MAX_TX_AMOUNT
        accs = client.get("/api/v1/accounts").json()["items"]
        if not accs:
            pytest.skip("No accounts")
        resp = client.post("/api/v1/transactions", json={
            "type": "INCOME", "amount": MAX_TX_AMOUNT,
            "account_id": accs[0]["id"], "category_id": 5,
        })
        assert resp.status_code == 201

    def test_over_max_rejected(self, client):
        from app.services.finance import MAX_TX_AMOUNT
        resp = client.post("/api/v1/transactions", json={
            "type": "INCOME", "amount": MAX_TX_AMOUNT + 1,
            "account_id": 1, "category_id": 5,
        })
        assert resp.status_code in (400, 422)

    def test_negative_rejected(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": -1000,
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_zero_rejected(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": 0,
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)

    def test_empty_body_rejected(self, client):
        resp = client.post("/api/v1/transactions", json={})
        assert resp.status_code == 422

    def test_rp_string_in_api(self, client):
        resp = client.post("/api/v1/transactions", json={
            "type": "EXPENSE", "amount": "Rp 10.000",
            "account_id": 1, "category_id": 1,
        })
        assert resp.status_code in (400, 422)
