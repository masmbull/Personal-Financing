"""Production-config guard tests.

The guard lives in ``app.main._validate_production_config``. We instantiate
``Settings`` directly so we never mutate the lru_cache'd singleton and don't
have to spin up TestClient lifespan to exercise the checks.
"""
import pytest

from app.config import Settings
from app.main import _validate_production_config


def _settings(**over) -> Settings:
    """Fresh Settings instance (bypasses the get_settings() cache)."""
    defaults = dict(APP_ENV="production", DEBUG=True,
                   SECRET_KEY="change-me-in-production")
    defaults.update(over)
    return Settings(**defaults)


def test_production_guard_raises_on_default_secret():
    with pytest.raises(RuntimeError, match="SECRET_KEY must be overridden"):
        _validate_production_config(_settings())


def test_production_guard_forces_debug_off():
    s = _settings(SECRET_KEY="a-real-secret-here-32chars-long-xx", DEBUG=True)
    assert s.DEBUG is True
    _validate_production_config(s)
    assert s.DEBUG is False


def test_production_guard_passes_with_safe_config():
    s = _settings(SECRET_KEY="a-real-secret-here-32chars-long-xx", DEBUG=False)
    _validate_production_config(s)  # must not raise
    assert s.DEBUG is False


def test_production_guard_skipped_in_development():
    s = _settings(APP_ENV="development",
                  SECRET_KEY="change-me-in-production", DEBUG=True)
    _validate_production_config(s)  # must not raise
    assert s.DEBUG is True  # untouched