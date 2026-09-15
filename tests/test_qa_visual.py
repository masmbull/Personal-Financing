"""Quick visual QA for /import and /insights pages."""


def test_import_page(client):
    r = client.get("/import")
    assert r.status_code == 200, r.status_code
    html = r.text
    assert "file" in html.lower()
    assert "delimiter" in html.lower() or "pemisah" in html.lower()


def test_insights_page(client):
    r = client.get("/insights")
    assert r.status_code == 200, r.status_code
    html = r.text
    assert "score" in html.lower()
    assert "insight" in html.lower()


def test_css_v29(client):
    r = client.get("/static/css/style.css?v=29")
    assert r.status_code == 200
    base = client.get("/").text
    assert "style.css?v=29" in base


def test_budgets_page(client):
    r = client.get("/budgets")
    assert r.status_code == 200
    assert "budget" in r.text.lower()


def test_recurring_page(client):
    r = client.get("/recurring")
    assert r.status_code == 200
    assert "transaksi berulang" in r.text.lower()


def test_reports_page(client):
    r = client.get("/reports")
    assert r.status_code == 200
    assert "laporan" in r.text.lower()


def test_import_preview_api(client):
    import io
    csv_data = "Tanggal;Keterangan;Jumlah\n15/01/2024;Indomaret;Rp 50.000\n"
    r = client.post(
        "/api/v1/import/preview",
        files={"file": ("stmt.csv", io.BytesIO(csv_data.encode()), "text/csv")},
        data={"delimiter": ";"},
    )
    assert r.status_code == 200, (r.status_code, r.text[:300])
    body = r.json()
    assert body.get("rows"), body


def test_health_score_api(client):
    r = client.get("/api/v1/health-score")
    assert r.status_code == 200, (r.status_code, r.text[:300])
    body = r.json()
    assert "score" in body, body


def test_insights_api(client):
    r = client.get("/api/v1/insights")
    assert r.status_code == 200, (r.status_code, r.text[:300])
