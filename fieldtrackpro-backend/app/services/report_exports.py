"""
Server-side report exports: one table model, two renderers (Excel + PDF).

* Excel (.xlsx, openpyxl): header block (report, generated-at IST, row count,
  data-source note, EVERY applied filter), frozen header row, autofilter,
  real date cells (dd-mmm-yyyy, IST), numeric cells with number formats
  (Indian digit grouping for money), totals row, sensible column widths.
* PDF (reportlab): landscape A4, real table with a repeating header row, wrapped
  cells, proportional column widths, totals row, "Page x of y" footer.
  The rupee sign is rendered when a TTF containing U+20B9 is available on the
  host (Windows Arial/Segoe, Linux DejaVu/Noto/Liberation...); otherwise the
  text "Rs." is used consistently (reportlab's built-in Helvetica / the bundled
  Vera font have no rupee glyph).
"""
from __future__ import annotations

import io
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional, Sequence

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.services.report_filters import IST, ist_now, to_ist

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MIME = "application/pdf"

# Indian digit grouping (12,34,56,789.50) as an Excel number format.
EXCEL_INR = r"[>=10000000]##\,##\,##\,##0.00;[>=100000]##\,##\,##0.00;##,##0.00"
EXCEL_INT = "#,##0"
EXCEL_DATE = "dd-mmm-yyyy"
EXCEL_DATETIME = "dd-mmm-yyyy hh:mm"
EXCEL_PCT = '0.0"%"'
EXCEL_NUM1 = "#,##0.0"


# --------------------------------------------------------------------------- formatting
def fmt_inr(value: Any, decimals: int = 2) -> str:
    """Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    d = Decimal(str(value if value is not None else 0))
    d = d.quantize(Decimal(1).scaleb(-decimals)) if decimals else d.quantize(Decimal(1))
    sign = "-" if d < 0 else ""
    s = f"{abs(d):f}"
    ip, _, fp = s.partition(".")
    if len(ip) > 3:
        head, tail = ip[:-3], ip[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        ip = ",".join(groups) + "," + tail
    return f"{sign}{ip}.{fp}" if decimals else f"{sign}{ip}"


def fmt_date(d: Optional[date]) -> str:
    return d.strftime("%d-%b-%Y") if d else ""


def fmt_datetime_ist(dt: Optional[datetime]) -> str:
    local = to_ist(dt)
    return local.strftime("%d-%b-%Y %H:%M") if local else ""


def parse_iso_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


# --------------------------------------------------------------------------- model
@dataclass
class Col:
    header: str
    kind: str = "text"      # text | int | money | date | datetime | pct | number
    weight: float = 1.0     # relative PDF width for text columns
    total: bool = False     # sum into the totals row


@dataclass
class ReportTable:
    title: str
    sheet_name: str
    columns: list[Col]
    rows: list[list[Any]]
    filters: list[tuple[str, str]] = field(default_factory=list)
    note: Optional[str] = None
    kpis: list[tuple[str, str]] = field(default_factory=list)
    totals: bool = True
    totals_label: str = "TOTAL"
    # overrides for the totals row, e.g. {col_index: value} (pct columns)
    totals_override: dict[int, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=ist_now)

    def totals_row(self) -> Optional[list[Any]]:
        if not self.totals or not self.rows:
            return None
        out: list[Any] = [None] * len(self.columns)
        out[0] = self.totals_label
        for i, c in enumerate(self.columns):
            if c.total:
                out[i] = sum((Decimal(str(r[i] or 0)) for r in self.rows), Decimal(0))
        for i, v in self.totals_override.items():
            out[i] = v
        return out

    def filters_line(self) -> str:
        return " | ".join(f"{k}: {v}" for k, v in self.filters) if self.filters else "None"


def report_filename(prefix: str, ext: str, filtered: bool, now: Optional[datetime] = None) -> str:
    now = now or ist_now()
    return f"{prefix}_{now:%Y%m%d_%H%M}{'_filtered' if filtered else ''}.{ext}"


def content_disposition(filename: str) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]', "_", filename)
    return f'attachment; filename="{safe}"'


# --------------------------------------------------------------------------- Excel
def _excel_value(kind: str, v: Any) -> Any:
    if v is None or v == "":
        return None
    if kind in ("money", "number", "pct"):
        return float(v)
    if kind == "int":
        return int(v)
    if kind == "date":
        if isinstance(v, datetime):
            local = to_ist(v)
            return local.date() if local else None
        return v
    if kind == "datetime":
        dt = parse_iso_dt(v)
        local = to_ist(dt)
        return local.replace(tzinfo=None) if local else None
    return str(v)


_NUMFMT = {
    "money": EXCEL_INR, "int": EXCEL_INT, "date": EXCEL_DATE,
    "datetime": EXCEL_DATETIME, "pct": EXCEL_PCT, "number": EXCEL_NUM1,
}


def _write_sheet(ws, t: ReportTable) -> None:
    ncols = max(len(t.columns), 4)
    title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    meta_font = Font(name="Calibri", size=9, color="374151")
    hdr_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    hdr_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    tot_fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
    tot_font = Font(name="Calibri", size=10, bold=True)
    border = Border(*(Side(style="thin", color="D1D5DB"),) * 4)
    last_col = get_column_letter(ncols)

    def merged(row: int, text: str, font: Font, height: Optional[float] = None):
        ws.cell(row=row, column=1, value=text).font = font
        ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(f"A{row}:{last_col}{row}")
        if height:
            ws.row_dimensions[row].height = height

    gen = t.generated_at.strftime("%d-%b-%Y %H:%M")
    merged(1, f"FieldTrack Pro - {t.title}", title_font, 22)
    meta = f"Generated (IST): {gen} | Rows: {len(t.rows)}"
    if t.note:
        meta += f" | {t.note}"
    # width in chars of the merged region approximates the sum of column widths
    est_chars = max(60, ncols * 14)
    merged(2, meta, meta_font, 13 * max(1, -(-len(meta) // est_chars)))
    filt = "Filters applied -> " + t.filters_line()
    merged(3, filt, meta_font, 13 * max(1, -(-len(filt) // est_chars)))
    kpi_line = " | ".join(f"{k}: {v}" for k, v in t.kpis)
    merged(4, kpi_line or " ", Font(name="Calibri", size=10, bold=True, color="1E3A8A"),
           (13 * max(1, -(-len(kpi_line) // est_chars))) if kpi_line else None)
    hdr_row = 6
    for i, c in enumerate(t.columns, start=1):
        cell = ws.cell(row=hdr_row, column=i, value=c.header.replace("(INR)", f"({_RUPEE})"))
        cell.fill, cell.font, cell.border = hdr_fill, hdr_font, border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[hdr_row].height = 30

    widths = [max(10, min(len(c.header) + 2, 40)) for c in t.columns]
    for r_idx, row in enumerate(t.rows, start=hdr_row + 1):
        for i, c in enumerate(t.columns):
            v = _excel_value(c.kind, row[i])
            cell = ws.cell(row=r_idx, column=i + 1, value=v)
            cell.border = border
            fmt = _NUMFMT.get(c.kind)
            if fmt:
                cell.number_format = fmt
            if c.kind in ("money", "int", "number", "pct"):
                cell.alignment = Alignment(horizontal="right")
            width_chars = 11 if c.kind in ("date",) else 17 if c.kind == "datetime" else (
                len(fmt_inr(v)) + 2 if c.kind == "money" and v is not None else len(str(v)) if v is not None else 0
            )
            widths[i] = max(widths[i], min(width_chars + 2, 48))
    last_data = hdr_row + len(t.rows)

    tot = t.totals_row()
    if tot is not None:
        tr = last_data + 1
        for i, c in enumerate(t.columns):
            val = tot[i]
            if val is not None and c.kind in ("money", "int", "number", "pct"):
                val = float(val)
            cell = ws.cell(row=tr, column=i + 1, value=val)
            cell.font, cell.fill, cell.border = tot_font, tot_fill, border
            fmt = _NUMFMT.get(c.kind)
            if fmt and val is not None and not isinstance(val, str):
                cell.number_format = fmt
                cell.alignment = Alignment(horizontal="right")
            if val is not None and c.kind == "money":
                widths[i] = max(widths[i], len(fmt_inr(val)) + 4)

    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=hdr_row + 1, column=1)
    ws.auto_filter.ref = f"A{hdr_row}:{get_column_letter(len(t.columns))}{max(last_data, hdr_row)}"
    ws.sheet_view.zoomScale = 100


def to_xlsx(tables: Sequence[ReportTable]) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for t in tables:
        ws = wb.active if first else wb.create_sheet()
        first = False
        ws.title = re.sub(r"[\[\]\*\?/\\:]", "-", t.sheet_name)[:31]
        _write_sheet(ws, t)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- PDF
_RUPEE = "\u20b9"
_font_lock = threading.Lock()
_font_cache: Optional[tuple[str, str, str]] = None  # (regular, bold, currency symbol)

_FONT_CANDIDATES: list[tuple[str, str]] = [
    # (regular, bold) - first one containing U+20B9 wins
    (os.environ.get("REPORT_PDF_FONT", ""), os.environ.get("REPORT_PDF_FONT_BOLD", "")),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]


def pdf_fonts() -> tuple[str, str, str]:
    """Return (regular font name, bold font name, currency symbol) - cached, thread-safe."""
    global _font_cache
    with _font_lock:
        if _font_cache is not None:
            return _font_cache
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        for regular, bold in _FONT_CANDIDATES:
            if not regular or not os.path.exists(regular):
                continue
            try:
                font = TTFont("FTReport", regular)
                if ord(_RUPEE) not in font.face.charToGlyph:
                    continue
                pdfmetrics.registerFont(font)
                bold_name = "FTReport"
                if bold and os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("FTReport-Bold", bold))
                    bold_name = "FTReport-Bold"
                _font_cache = ("FTReport", bold_name, _RUPEE)
                return _font_cache
            except Exception:
                continue
        _font_cache = ("Helvetica", "Helvetica-Bold", "Rs.")
        return _font_cache


def _xml(s: Any) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_cell_text(kind: str, v: Any) -> str:
    if v is None or v == "":
        return ""
    if kind == "money":
        return fmt_inr(v, 2)
    if kind == "int":
        return fmt_inr(v, 0)
    if kind == "number":
        return fmt_inr(v, 1)
    if kind == "pct":
        return f"{float(v):.1f}%"
    if kind == "date":
        d = to_ist(v).date() if isinstance(v, datetime) else v
        return fmt_date(d)
    if kind == "datetime":
        return fmt_datetime_ist(parse_iso_dt(v))
    return str(v)


def _currency_text(s: str, symbol: str) -> str:
    """Header text uses the rupee sign marker '(INR)' -> '(<symbol>)'."""
    return s.replace("(INR)", f"({symbol})").replace(_RUPEE, symbol)


def to_pdf(tables: Sequence[ReportTable]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    reg, bold, sym = pdf_fonts()
    page_w, page_h = landscape(A4)
    margin = 26
    avail = page_w - 2 * margin
    gen_label = tables[0].generated_at.strftime("%d-%b-%Y %H:%M") if tables else ""
    footer_title = tables[0].title if tables else "Report"

    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._saved: list[dict] = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self.setFont(reg, 7)
                self.setFillColor(colors.HexColor("#6B7280"))
                self.drawString(margin, 14, f"FieldTrack Pro - {footer_title} - generated {gen_label} IST")
                self.drawRightString(page_w - margin, 14, f"Page {self._pageNumber} of {total}")
                super().showPage()
            super().save()

    title_style = ParagraphStyle("t", fontName=bold, fontSize=15, leading=18, textColor=colors.HexColor("#1E3A8A"))
    meta_style = ParagraphStyle("m", fontName=reg, fontSize=8, leading=10.5, textColor=colors.HexColor("#374151"))
    kpi_style = ParagraphStyle("k", fontName=bold, fontSize=9, leading=12, textColor=colors.HexColor("#1E3A8A"))

    story: list = []
    for ti, t in enumerate(tables):
        if ti:
            story.append(PageBreak())
        ncols = len(t.columns)
        font_size = 7.2 if ncols <= 9 else 6.6 if ncols <= 12 else 6.0 if ncols <= 15 else 5.6
        pad = 2.5
        head_style = ParagraphStyle("h", fontName=bold, fontSize=font_size, leading=font_size + 1.8,
                                    textColor=colors.white, alignment=1)
        cell_style = ParagraphStyle("c", fontName=reg, fontSize=font_size, leading=font_size + 1.8)
        cell_right = ParagraphStyle("cr", parent=cell_style, alignment=TA_RIGHT)
        tot_style = ParagraphStyle("tot", parent=cell_style, fontName=bold)
        tot_right = ParagraphStyle("totr", parent=tot_style, alignment=TA_RIGHT)

        story.append(Paragraph(_xml(t.title), title_style))
        story.append(Spacer(1, 3))
        meta = f"Generated (IST): {gen_label} &nbsp;|&nbsp; Rows: {len(t.rows)}"
        story.append(Paragraph(meta, meta_style))
        story.append(Paragraph("<b>Filters applied:</b> " + _xml(_currency_text(t.filters_line(), sym)), meta_style))
        if t.note:
            story.append(Paragraph("<b>Data:</b> " + _xml(t.note), meta_style))
        if t.kpis:
            story.append(Spacer(1, 3))
            story.append(Paragraph(
                " &nbsp;|&nbsp; ".join(f"{_xml(k)}: {_xml(_currency_text(v, sym))}" for k, v in t.kpis), kpi_style))
        story.append(Spacer(1, 6))

        texts = [[_pdf_cell_text(c.kind, r[i]) for i, c in enumerate(t.columns)] for r in t.rows]
        tot = t.totals_row()
        tot_texts = [(_pdf_cell_text(c.kind, tot[i]) if tot[i] is not None else "") for i, c in enumerate(t.columns)] if tot else None

        # column widths: numeric/date columns get their natural width, text columns share the rest
        natural: list[float] = []
        for i, c in enumerate(t.columns):
            candidates = [c.header] if c.kind == "text" else [max(c.header.split(" "), key=len)]
            if c.kind == "date":
                candidates.append("00-Mon-0000")
            if c.kind != "text":
                col_cells = [row[i] for row in texts] + ([tot_texts[i]] if tot_texts else [])
                candidates += col_cells[:2000]
            hdr_words = set(c.header.split(" "))
            w = max((stringWidth(_currency_text(s, sym), bold if (s == c.header or s in hdr_words) else reg, font_size) for s in candidates), default=20)
            natural.append(w + 2 * pad + 1)
        num_idx = [i for i, c in enumerate(t.columns) if c.kind != "text"]
        txt_idx = [i for i, c in enumerate(t.columns) if c.kind == "text"]
        widths = [0.0] * ncols
        for i in num_idx:
            widths[i] = natural[i]
        remaining = avail - sum(widths[i] for i in num_idx)
        weights = sum(t.columns[i].weight for i in txt_idx) or 1
        min_text = 38.0
        if txt_idx and remaining < min_text * len(txt_idx):
            # too wide: shrink numeric columns proportionally to make room for text
            need = min_text * len(txt_idx)
            scale = max((avail - need) / max(sum(widths[i] for i in num_idx), 1), 0.55)
            for i in num_idx:
                widths[i] *= scale
            remaining = avail - sum(widths[i] for i in num_idx)
        for i in txt_idx:
            widths[i] = max(min_text, remaining * t.columns[i].weight / weights)
        scale = avail / sum(widths)
        if scale < 1:
            widths = [w * scale for w in widths]

        def cell(i: int, text: str, tot_row: bool = False):
            right = t.columns[i].kind != "text"
            st = (tot_right if right else tot_style) if tot_row else (cell_right if right else cell_style)
            return Paragraph(_xml(text), st)

        data = [[Paragraph(_xml(_currency_text(c.header, sym)), head_style) for c in t.columns]]
        for r in texts:
            data.append([cell(i, s) for i, s in enumerate(r)])
        if tot_texts:
            data.append([cell(i, s, True) for i, s in enumerate(tot_texts)])
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2 if tot_texts else -1), [colors.white, colors.HexColor("#F3F4F6")]),
        ]
        if tot_texts:
            style += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5E7EB")),
                      ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#1E3A8A"))]
        story.append(Table(data, colWidths=widths, repeatRows=1, style=TableStyle(style)))
        if not t.rows:
            story.append(Spacer(1, 6))
            story.append(Paragraph("No rows match the selected filters.", meta_style))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin, topMargin=26, bottomMargin=28,
        title=footer_title, author="FieldTrack Pro",
    )
    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()
