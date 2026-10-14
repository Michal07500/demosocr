"""Vytvorenie kompletačného listu (PDF) zo zlúčených položiek."""
from __future__ import annotations

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)
from xml.sax.saxutils import escape

from .aggregate import Line
from .ocr import PickList, fmt

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("Sans", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-Bold")

BASE = ParagraphStyle("base", fontName="Sans", fontSize=9, leading=11)
SMALL = ParagraphStyle("small", parent=BASE, fontSize=7.5, leading=9)
WARN = ParagraphStyle("warn", parent=SMALL, textColor=colors.HexColor("#b00020"))
BIG = ParagraphStyle("big", parent=BASE, fontName="Sans-Bold", fontSize=13, leading=15,
                     alignment=TA_RIGHT)
LOC = ParagraphStyle("loc", parent=BASE, fontName="Sans-Bold", fontSize=11, leading=13)
TITLE = ParagraphStyle("title", parent=BASE, fontName="Sans-Bold", fontSize=18, leading=22)
H2 = ParagraphStyle("h2", parent=BASE, fontName="Sans-Bold", fontSize=12, leading=15)

GRID = colors.HexColor("#888888")
HEAD_BG = colors.HexColor("#e6e6e6")
WARN_BG = colors.HexColor("#fff3cd")


def P(text: str, style=BASE) -> Paragraph:
    return Paragraph(text, style)


def _allocation_text(line: Line) -> str:
    multi_loc = len(line.umiestnenia) > 1
    rows = []
    for a in line.allocations:
        parts = []
        if multi_loc:
            parts.append(f"<b>{escape(a.umiestnenie)}</b>")
        parts.append(f"<b>{fmt(a.mnozstvo)} ks</b>")
        parts.append(escape(a.zakazka or a.doklad or f"str. {a.page}"))
        if a.zakaznik:
            parts.append(escape(a.zakaznik[:32]))
        rows.append(" · ".join(parts))
    return "<br/>".join(rows)


def build_pdf(path: str, lines: list[Line], lists: list[PickList], source: str = "") -> None:
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=10 * mm,
                            rightMargin=10 * mm, topMargin=10 * mm, bottomMargin=12 * mm,
                            title="Kompletačný list")
    story = []
    total = sum(l.mnozstvo for l in lines)
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    story.append(P("KOMPLETAČNÝ LIST", TITLE))
    info = (f"Vytvorené: {now} &nbsp;·&nbsp; vychystávacích listov: <b>{len(lists)}</b> "
            f"&nbsp;·&nbsp; rôznych dosiek: <b>{len(lines)}</b> &nbsp;·&nbsp; "
            f"spolu kusov: <b>{fmt(total)}</b>")
    if source:
        info += f" &nbsp;·&nbsp; zdroj: {escape(os.path.basename(source))}"
    story += [P(info), Spacer(0, 1 * mm),
              P("Pripravil: ..................................... &nbsp;&nbsp;&nbsp; "
                "Skontroloval: ....................................."), Spacer(0, 3 * mm)]

    # --- hlavná tabuľka: čo kde zobrať -------------------------------------
    head = ["✓", "Umiestnenie", "Kód", "Názov", "Manip.", "Vychystať", "KM",
            "Rozpis (zákazka · zákazník)"]
    data = [[P(f"<b>{h}</b>", SMALL) for h in head]]
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]
    for i, l in enumerate(lines, 1):
        name = escape(l.nazov)
        if l.warnings:
            name += "".join(f"<br/><font size='7.5' color='#b00020'>⚠ skontroluj – {escape(w)}</font>"
                            for w in l.warnings)
            style.append(("BACKGROUND", (0, i), (-1, i), WARN_BG))
        km = " / ".join(fmt(l.km[u]) for u in l.umiestnenia if u in l.km)
        data.append([
            P("☐", ParagraphStyle("box", parent=BASE, fontSize=14, leading=16)),
            P("<br/>".join(escape(u) for u in l.umiestnenia) or "?", LOC),
            P(escape(l.kod) or "?"),
            P(name),
            P(escape(l.manipulacia), SMALL),
            P(f"{fmt(l.mnozstvo)} ks", BIG),
            P(km),
            P(_allocation_text(l), SMALL),
        ])
    data.append(["", "", "", P("<b>SPOLU</b>"), "", P(f"{fmt(total)} ks", BIG), "", ""])
    style.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), HEAD_BG))
    widths = [8 * mm, 27 * mm, 18 * mm, 80 * mm, 22 * mm, 27 * mm, 16 * mm, 79 * mm]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    story += [t, Spacer(0, 5 * mm)]

    # --- prehľad vychystávacích listov --------------------------------------
    story.append(P("Vychystávacie listy v tejto kompletácii", H2))
    story.append(Spacer(0, 2 * mm))
    head = ["Str.", "Doklad", "Zákazka", "Zákazník", "Obj. zák.", "Expedícia",
            "Pol.", "Ks", "Poznámka"]
    data = [[P(f"<b>{h}</b>", SMALL) for h in head]]
    style = [("GRID", (0, 0), (-1, -1), 0.5, GRID), ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
    for i, pl in enumerate(lists, 1):
        notes = list(pl.warnings)
        if pl.warnings:
            style.append(("BACKGROUND", (0, i), (-1, i), WARN_BG))
        data.append([
            P(str(pl.page), SMALL), P(escape(pl.doklad), SMALL),
            P(f"<b>{escape(pl.zakazka)}</b>", SMALL),
            P(escape(pl.zakaznik), SMALL), P(escape(pl.obj_zak), SMALL), P(escape(pl.expedicia), SMALL),
            P(str(len(pl.items)), SMALL),
            P(fmt(sum(it.mnozstvo for it in pl.items)), SMALL),
            P("<br/>".join(escape(n) for n in notes), WARN),
        ])
    widths = [10 * mm, 38 * mm, 24 * mm, 65 * mm, 30 * mm, 22 * mm, 11 * mm, 14 * mm, 63 * mm]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    story.append(t)


    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Sans", 7)
        canvas.drawString(10 * mm, 6 * mm, f"Kompletačný list · {now}")
        canvas.drawRightString(landscape(A4)[0] - 10 * mm, 6 * mm, f"Strana {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
