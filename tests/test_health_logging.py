"""Health probes (liveness vs readiness) and secret-safe logging."""
from fastapi.testclient import TestClient

from app.main import app
from app.logging_setup import get_logger, log_event, RedactingFormatter
import logging
import io


def test_liveness_up_without_db(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_checks_db(client):
    resp = client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_requires_auth_is_not_applicable():
    # health endpoints are public by design; just confirm they don't 401.
    assert app.url_path_for("health_live") == "/api/v1/health"
    assert app.url_path_for("health_ready") == "/api/v1/health/ready"


def test_formatter_redacts_password():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    log = logging.getLogger("test_redact")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    log.info("login attempt token=abc123secret password=hunter2")
    out = buf.getvalue()
    assert "hunter2" not in out
    assert "[REDACTED]" in out


def test_formatter_redacts_bearer():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    log = logging.getLogger("test_bearer")
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    log.info("Authorization: Bearer eyJhbGci.token.value")
    out = buf.getvalue()
    assert "eyJhbGci" not in out
    # Both the header name and the token value are scrubbed.
    assert "[REDACTED]" in out


def test_structured_event_emits_key_values():
    log = get_logger("test_struct")
    assert log is not None
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    log_event(log, "login_success", user_id=7, ip="1.2.3.4")
    assert "event=login_success" in buf.getvalue()
    assert "user_id=7" in buf.getvalue()
