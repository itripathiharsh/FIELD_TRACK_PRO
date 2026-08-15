"""
PDF export for a form submission - one section per heading, one line per
question/answer pair, built from the same SubmissionDetailRead the admin
review UI renders, so the PDF and the on-screen review can never disagree.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.form_template import SubmissionDetailRead

# FieldTrack Pro brand palette (tailwind.config.js: primary / secondary-container)
_NAVY = colors.HexColor("#14213D")
_AMBER = colors.HexColor("#FCA311")
_GRAY = colors.HexColor("#E5E5E5")


def render_submission_pdf(detail: SubmissionDetailRead) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("FTPTitle", parent=styles["Title"], textColor=_NAVY, fontSize=18, spaceAfter=2)
    meta_style = ParagraphStyle("FTPMeta", parent=styles["Normal"], textColor=colors.HexColor("#45464d"), fontSize=9)
    section_style = ParagraphStyle("FTPSection", parent=styles["Heading2"], textColor=_NAVY, fontSize=13, spaceBefore=14, spaceAfter=6)
    question_style = ParagraphStyle("FTPQuestion", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#1b1b1e"))
    answer_style = ParagraphStyle("FTPAnswer", parent=styles["Normal"], fontSize=10, textColor=_NAVY, leftIndent=10)

    elements: list = [
        Paragraph(detail.form_name, title_style),
        Paragraph(
            f"Submission #{str(detail.id)[:8]} &middot; Version {detail.form_version} &middot; "
            f"Status: {detail.status.value if hasattr(detail.status, 'value') else detail.status}",
            meta_style,
        ),
        Paragraph(f"Employee: {detail.employee_name or detail.submitted_by}", meta_style),
        Paragraph(f"Visit: {detail.visit_id}", meta_style),
        Paragraph(
            f"Submitted: {detail.submitted_at.strftime('%Y-%m-%d %H:%M') if detail.submitted_at else 'Not yet submitted'}",
            meta_style,
        ),
        Spacer(1, 6 * mm),
    ]

    answers_by_question = {a.question_id: a for a in detail.answers}

    for section in detail.sections:
        elements.append(Paragraph(section.title, section_style))
        if section.description:
            elements.append(Paragraph(section.description, meta_style))

        rows = []
        for question in section.questions:
            answer = answers_by_question.get(question.id)
            value = (answer.answer_value if answer and answer.answer_value else "—")
            required_mark = " *" if question.required else ""
            rows.append([
                Paragraph(f"{question.question_text}{required_mark}", question_style),
                Paragraph(str(value), answer_style),
            ])

        if rows:
            table = Table(rows, colWidths=[95 * mm, 75 * mm])
            table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, _GRAY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f3f6")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]))
            elements.append(table)
        elements.append(Spacer(1, 4 * mm))

    doc.build(elements)
    return buffer.getvalue()
