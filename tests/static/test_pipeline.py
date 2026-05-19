from pathlib import Path

import pytest

from app.data_pipeline import extract_p1040, extract_p596, extract_p15t

BASE = Path(__file__).parent.parent.parent

VALID_PAY_PERIODS = {"WEEKLY", "BIWEEKLY", "SEMIMONTHLY", "MONTHLY", "DAILY"}
VALID_P15T_STATUSES = {
    "Married Filing Jointly",
    "Head of Household",
    "Single or Married Filing Separately",
}


def test_extract_p1040():
    records = extract_p1040(str(BASE / "data/pdfs/p1040_2025.pdf"))

    assert len(records) > 0

    filing_statuses = {r["filing_status"] for r in records}
    assert filing_statuses == {
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
    }

    for r in records:
        assert r["income_from"] < r["income_to"]
        assert isinstance(r["tax_amount"], int)
        assert r["table_type"] == "tax_table"


def test_extract_p596():
    records = extract_p596(str(BASE / "data/pdfs/p596_2025.pdf"))

    assert len(records) > 0

    filing_statuses = {r["filing_status"] for r in records}
    assert "single_mfs_hh" in filing_statuses
    assert "married_filing_jointly" in filing_statuses

    children_values = {r["qualifying_children"] for r in records}
    assert children_values == {0, 1, 2, 3}

    for r in records:
        assert r["income_from"] < r["income_to"]
        assert isinstance(r["credit_amount"], int)
        assert r["table_type"] == "eic"


def test_extract_p15t():
    records = extract_p15t(str(BASE / "data/pdfs/p15t_2025.pdf"))

    assert len(records) > 0

    pay_periods = {r["pay_period"] for r in records}
    assert pay_periods == VALID_PAY_PERIODS

    statuses = {r["filing_status"] for r in records}
    assert statuses == VALID_P15T_STATUSES

    for r in records:
        assert r["income_from"] < r["income_to"]
        assert isinstance(r["withholding_amount"], float)
