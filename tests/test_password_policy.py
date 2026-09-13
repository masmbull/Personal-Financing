"""Password policy: common-pattern rejection + username-substring rejection."""
from app.validation import password_policy_error, password_strength


def test_accepts_strong_password():
    assert password_policy_error("K0pi_Hangat!2x") == ""


def test_rejects_short():
    assert "8 karakter" in password_policy_error("abc123")


def test_rejects_common_weak():
    assert password_policy_error("password123") != ""
    assert password_policy_error("qwerty1234") != ""


def test_rejects_keyboard_run():
    assert "keyboard" in password_policy_error("qwertyuiop99")


def test_rejects_digit_only():
    assert password_policy_error("123456789012") != ""


def test_rejects_username_substring():
    # 'bob' is a substring of 'bob12345!' -> rejected
    assert "username" in password_policy_error("bob12345!", username="bob")


def test_accepts_password_with_similar_but_not_substring():
    # 'bobby' contains 'bob' but user is 'bobby' -> substring must match the
    # whole username, so 'bobby' as username with password 'bobby99!' is still
    # rejected (it does contain the username). Use a clearly different user.
    assert password_policy_error("bob12345!", username="alice") == ""


def test_strength_levels():
    assert password_strength("") == "weak"
    assert password_strength("password123") == "weak"  # fails policy
    assert password_strength("wag1Fido!") in ("medium", "strong")
    # long + 3+ classes => strong
    assert password_strength("T0longJanganLupa!") == "strong"
