"""PDF reports. Team PDFs show only counts; the boss's PDF also shows amounts."""

import io
from xml.sax.saxutils import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core import services

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"

_registered = False


def _register_fonts():
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont(FONT, str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)
        _registered = True


def money(value):
    return f"{value:,}".replace(",", " ") + " so'm"


def fmt_date(day):
    return day.strftime("%d.%m.%Y")


TITLE = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=14, leading=18, spaceAfter=4)
SUBTITLE = ParagraphStyle("subtitle", fontName=FONT, fontSize=10, leading=13, textColor=colors.grey)
HEADING = ParagraphStyle("heading", fontName=FONT_BOLD, fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)


def _table(rows, widths, numeric_from):
    table = Table(rows, colWidths=widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B0B7C3")),
        ("ALIGN", (numeric_from, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")]),
    ]
    table.setStyle(TableStyle(style))
    return table


def _build(story):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm
    )
    doc.build(story)
    return buf.getvalue()


def team_daily_pdf(team, day):
    """Daily report for a team's Telegram group: who made how many of what. No amounts."""
    _register_fonts()
    entries = services.approved_entries(day, day, team=team)
    if not entries:
        return None
    rows = [["№", "Ishchi", "Mahsulot", "Ish turi", "Soni", "Brak"]]
    for i, e in enumerate(entries, 1):
        rows.append(
            [str(i), e.worker.full_name, e.operation.product.name, e.operation.name, str(e.quantity), str(e.defect_quantity)]
        )
    rows.append(["", "Jami", "", "", str(sum(e.quantity for e in entries)), str(sum(e.defect_quantity for e in entries))])
    table = _table(rows, [10 * mm, 45 * mm, 35 * mm, 55 * mm, 18 * mm, 17 * mm], numeric_from=4)
    table.setStyle(TableStyle([("FONTNAME", (0, -1), (-1, -1), FONT_BOLD)]))
    story = [
        Paragraph(f"{escape(team.name)}: kunlik hisobot", TITLE),
        Paragraph(f"{fmt_date(day)} · faqat tasdiqlangan ishlar", SUBTITLE),
        Spacer(1, 6 * mm),
        table,
    ]
    return _build(story)


def summary_pdf(start, end, team=None):
    """Report for the boss: totals and amounts per worker and per operation."""
    _register_fonts()
    data = services.range_summary(start, end, team=team)
    period = fmt_date(start) if start == end else f"{fmt_date(start)} – {fmt_date(end)}"
    story = [
        Paragraph("Ishlab chiqarish va ish haqi hisoboti", TITLE),
        Paragraph(
            f"{period}{' · ' + escape(team.name) if team else ''} · jami {data['total_quantity']} dona, "
            f"brak {data['total_defect']}, ish haqi {money(data['total_amount'])}",
            SUBTITLE,
        ),
        Paragraph("Ishchilar bo'yicha", HEADING),
    ]
    rows = [["№", "Ishchi", "Guruh", "Soni", "Brak", "Ish haqi"]]
    for i, w in enumerate(data["workers"], 1):
        rows.append([str(i), w.name, w.team, str(w.quantity), str(w.defect), money(w.amount)])
    if len(rows) == 1:
        rows.append(["", "Ma'lumot yo'q", "", "", "", ""])
    story.append(_table(rows, [10 * mm, 55 * mm, 35 * mm, 20 * mm, 18 * mm, 42 * mm], numeric_from=3))
    story.append(Paragraph("Mahsulot va ish turlari bo'yicha", HEADING))
    rows = [["Mahsulot", "Ish turi", "Soni", "Brak", "Ish haqi"]]
    for o in data["operations"]:
        rows.append([o.product, o.operation, str(o.quantity), str(o.defect), money(o.amount)])
    if len(rows) == 1:
        rows.append(["Ma'lumot yo'q", "", "", "", ""])
    story.append(_table(rows, [40 * mm, 65 * mm, 20 * mm, 18 * mm, 37 * mm], numeric_from=2))
    return _build(story)
