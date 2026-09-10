"""build_scanner() must degrade gracefully when no cloud API key is set.

Regression guard for the production deployment: the server's .env may not
carry OPENAI_API_KEY/GEMINI_API_KEY, and building the scanner must skip the
cloud engine instead of raising, so uploads keep working via the local chain.
"""
import app.config as cfg
import app.services.receipt_ocr as ocr_mod


def _chain_names(root):
    names = []

    def walk(node):
        names.append(getattr(node, "name", type(node).__name__))
        inner = getattr(node, "inner", None)
        if inner is not None:
            walk(inner)
        for e in getattr(node, "engines", None) or []:
            walk(e)

    walk(root)
    return names


def test_build_scanner_skips_cloud_engine_without_openai_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_ENABLED", True)
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_PROVIDER", "openai")
    monkeypatch.setattr(cfg.settings, "OPENAI_API_KEY", "")
    scanner = ocr_mod.build_scanner()
    assert not any(n.startswith("cloud-") for n in _chain_names(scanner))


def test_build_scanner_skips_cloud_engine_without_gemini_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_ENABLED", True)
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_PROVIDER", "gemini")
    monkeypatch.setattr(cfg.settings, "GEMINI_API_KEY", "")
    scanner = ocr_mod.build_scanner()
    assert not any(n.startswith("cloud-") for n in _chain_names(scanner))


def test_build_scanner_includes_cloud_engine_with_openai_key(monkeypatch):
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_ENABLED", True)
    monkeypatch.setattr(cfg.settings, "RECEIPT_AI_PROVIDER", "openai")
    monkeypatch.setattr(cfg.settings, "OPENAI_API_KEY", "sk-test-placeholder")
    scanner = ocr_mod.build_scanner()
    assert "cloud-openai" in _chain_names(scanner)
