"""Rýchla skúška zabalenej aplikácie (používa sa pri zostavení .exe na GitHube).

Vytvorí malé testovacie PDF, spracuje ho celým postupom (vrátane viacerých procesov
a tesseractu) a výsledok zapíše do textového súboru.
"""
from __future__ import annotations

import os
import tempfile
import traceback

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def main(report_path: str) -> int:
    try:
        from .ocr import check_tesseract
        from .pipeline import run

        err = check_tesseract()
        if err:
            raise RuntimeError(err)
        tmp = tempfile.mkdtemp()
        pdf = os.path.join(tmp, "test.pdf")
        c = canvas.Canvas(pdf, pagesize=A4)
        for page in range(3):
            c.setFont("Helvetica", 14)
            c.drawString(60, 760, f"Vychystavaci list - test {page + 1}")
            c.drawString(60, 700, "Kod      Nazev      Manipulace      Umisteni")
            c.showPage()
        c.save()
        res = run([pdf], os.path.join(tmp, "out.pdf"), workers=2)
        ok = len(res.lists) == 3 and os.path.exists(res.output)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"{'OK' if ok else 'FAIL'} pages={len(res.lists)} output={res.output}\n")
        return 0 if ok else 1
    except Exception:  # noqa: BLE001 - všetko zapísať do správy
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("FAIL\n" + traceback.format_exc())
        return 1
