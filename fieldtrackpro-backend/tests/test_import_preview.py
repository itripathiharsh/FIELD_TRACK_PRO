"""
Unit tests for the column-agnostic Excel import preview (app/services/import_service.py).
"""
from __future__ import annotations

import io

import openpyxl
import pytest

from app.exceptions.custom import BaseAPIException
from app.services.import_service import preview_excel_file


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_preview_returns_detected_headers_and_rows():
    data = _make_xlsx(
        ["Outlet Name", "Invoice No", "Amount"],
        [["Balaji Enterprises", "INV-1", 1000], ["Singer Traders", "INV-2", 2000]],
    )
    result = preview_excel_file(data, "sample.xlsx")
    assert result["columns"] == ["Outlet Name", "Invoice No", "Amount"]
    assert result["total_data_rows"] == 2
    assert result["sample_rows"][0] == ["Balaji Enterprises", "INV-1", "1000"]
    assert result["truncated"] is False


def test_preview_marks_truncated_beyond_limit():
    data = _make_xlsx(["A"], [[i] for i in range(25)])
    result = preview_excel_file(data, "big.xlsx")
    assert result["total_data_rows"] == 25
    assert len(result["sample_rows"]) == 20
    assert result["truncated"] is True


def test_preview_rejects_empty_file():
    with pytest.raises(BaseAPIException) as exc_info:
        preview_excel_file(b"", "empty.xlsx")
    assert exc_info.value.status_code == 400


def test_preview_rejects_non_xlsx_extension():
    with pytest.raises(BaseAPIException) as exc_info:
        preview_excel_file(b"not really excel", "data.csv")
    assert exc_info.value.status_code == 415


def test_preview_rejects_unreadable_file():
    with pytest.raises(BaseAPIException) as exc_info:
        preview_excel_file(b"this is not a real xlsx file", "fake.xlsx")
    assert exc_info.value.status_code == 400
    assert exc_info.value.error_code == "IMPORT_UNREADABLE_FILE"


def test_preview_handles_blank_column_headers():
    data = _make_xlsx(["Name", None, "Amount"], [["X", "skip", 5]])
    result = preview_excel_file(data, "gaps.xlsx")
    assert result["columns"][1] == "(blank column 2)"
