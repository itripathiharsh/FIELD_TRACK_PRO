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


def test_preview_skips_title_and_total_rows():
    # Row 1: Company title banner
    # Row 2: Totals summary
    # Row 3: Actual table headers
    # Row 4+: Data
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["SGRG SERVICES PRIVATE LIMITED - OS Report (VU)", None, None, None, None, "Date :-", "2026-08-21"])
    ws.append(["Total", None, 87, 87, 87, 9933698.29, 754264])
    ws.append(["DMS Code", "OUTLET_NAME", "ZONE", "AREA", "FOS NAME", "MARKET_OS", "(< 15 days )"])
    ws.append(["SGRGVU101", "Pihu Electronics", "KANPUR", "MANGLA VIHAR", "RAUNAK", 26590, 26590])
    ws.append(["SGRGVU102", "Luxmi Electronics", "FARRUKHABAD", "TIRWA", "YOGESH", 49980, 49980])
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()

    result = preview_excel_file(data, "vu_format.xlsx")
    assert result["header_row_index"] == 3
    assert result["columns"] == ["DMS Code", "OUTLET_NAME", "ZONE", "AREA", "FOS NAME", "MARKET_OS", "(< 15 days )"]
    assert result["total_data_rows"] == 2
    assert result["is_confident"] is True
    assert result["matched_columns_count"] == 7
    assert result["suggested_mapping"]["DMS Code"] == "dms_code"
    assert result["suggested_mapping"]["OUTLET_NAME"] == "outlet_name"
    assert result["suggested_mapping"]["MARKET_OS"] == "market_outstanding"

