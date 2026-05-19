import pytest


# ── /health ──────────────────────────────────────────────────────────────────

async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ── /stats ────────────────────────────────────────────────────────────────────

async def test_stats_has_expected_keys(client):
    r = await client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"tax_records", "eic_credits", "withholding_brackets"}
    for section in body.values():
        assert "total" in section and "by_year" in section
        assert section["total"] > 0


# ── /tax-records ──────────────────────────────────────────────────────────────

async def test_tax_records_returns_single_bracket(client):
    r = await client.get("/tax-records", params={"income": 50000, "filing_status": "single"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["amount"] < 0                   # tax owed is negative
    assert data[0]["income_from"] <= 50000 < data[0]["income_to"]


async def test_tax_records_invalid_filing_status(client):
    r = await client.get("/tax-records", params={"income": 50000, "filing_status": "invalid"})
    assert r.status_code == 422


# ── /eic-credits ──────────────────────────────────────────────────────────────

async def test_eic_credits_returns_positive_amount(client):
    r = await client.get("/eic-credits", params={
        "income": 20000, "filing_status": "single_mfs_hh",
        "qualifying_children": "2", "year": "2025",
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["amount"] > 0                   # EIC credit is positive
    assert data[0]["qualifying_children"] == 2


async def test_eic_credits_invalid_year(client):
    r = await client.get("/eic-credits", params={
        "income": 20000, "filing_status": "single_mfs_hh",
        "qualifying_children": "1", "year": "2023",
    })
    assert r.status_code == 422


# ── /withholding-brackets ─────────────────────────────────────────────────────

async def test_withholding_returns_bracket(client):
    r = await client.get("/withholding-brackets", params={
        "income": 1000, "filing_status": "Single or Married Filing Separately",
        "pay_period": "WEEKLY", "withholding_type": "standard", "year": "2025",
    })
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["withholding_amount"] >= 0
    assert data[0]["income_from"] <= 1000 < data[0]["income_to"]


async def test_withholding_income_above_table_returns_empty(client):
    # WEEKLY max is $1,925 — $9,999 is above the table
    r = await client.get("/withholding-brackets", params={
        "income": 9999, "filing_status": "Single or Married Filing Separately",
        "pay_period": "WEEKLY", "withholding_type": "standard", "year": "2025",
    })
    assert r.status_code == 200
    assert r.json() == []


async def test_withholding_invalid_pay_period(client):
    r = await client.get("/withholding-brackets", params={
        "income": 1000, "filing_status": "Single or Married Filing Separately",
        "pay_period": "QUARTERLY", "withholding_type": "standard", "year": "2025",
    })
    assert r.status_code == 422
