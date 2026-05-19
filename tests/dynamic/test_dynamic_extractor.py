from pathlib import Path
from unittest.mock import MagicMock

import pdfplumber
import pytest

from app.dynamic_pdf.dynamic_pdf_extractor import _extract_page_text, _process_page

BASE = Path(__file__).parent.parent.parent
PDF_PATH = BASE / "data/pdfs/tablas_impuestos_federales_2026.pdf"


def test_extract_page_text_respects_cap():
    with pdfplumber.open(PDF_PATH) as pdf:
        text = _extract_page_text(pdf.pages[1])
    assert isinstance(text, str)
    assert 0 < len(text) <= 3_000


def test_process_page_parses_table():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = (
        '{"table_type": "tax_bracket_single", '
        '"records": [{"marginal_rate": 10, "lower_limit": 0, "upper_limit": 11925}]}'
    )

    result = _process_page(mock_client, "page text", [])

    assert result["table_type"] == "tax_bracket_single"
    assert len(result["records"]) == 1
    assert result["records"][0]["marginal_rate"] == 10


def test_process_page_no_table_returns_null():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = (
        '{"table_type": null, "records": []}'
    )

    result = _process_page(mock_client, "cover page text", [])

    assert result["table_type"] is None
    assert result["records"] == []


def test_process_page_uses_page_text_in_user_message():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = (
        '{"table_type": "tax_bracket_single", "records": []}'
    )

    _process_page(mock_client, "my page content", [])

    user_msg = mock_client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "my page content" in user_msg
