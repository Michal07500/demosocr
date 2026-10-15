"""Celý postup: skeny -> OCR -> zlúčenie -> PDF. Spoločné pre príkazový riadok aj aplikáciu."""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

from .aggregate import Line, drop_duplicates, merge
from .ocr import PickList, page_count, parse_pdf_page
from .report import build_pdf
from .settings import Settings, load as load_settings


@dataclass
class Result:
    output: str
    lines: list[Line]
    lists: list[PickList]
    dropped: list[PickList]
    source: str = ""

    @property
    def warning_count(self) -> int:
        return sum(bool(l.warnings) for l in self.lines) + sum(bool(p.warnings) for p in self.lists)


def default_output(first_input: str) -> str:
    return os.path.splitext(first_input)[0] + "_kompletacia.pdf"


def write_pdf(output: str, lines: list[Line], lists: list[PickList], source: str,
              settings: Settings) -> str:
    """Zapíše PDF; ak je súbor otvorený v prehliadači (Windows ho zamkne), použije nový názov."""
    try:
        build_pdf(output, lines, lists, source=source, settings=settings)
    except PermissionError:
        stem = os.path.splitext(output)[0]
        output = f"{stem}_{datetime.now():%H%M%S}.pdf"
        build_pdf(output, lines, lists, source=source, settings=settings)
    return output


def rebuild(res: Result, settings: Settings) -> Result:
    """Nové PDF z už prečítaných listov (napr. po zmene nastavení) - bez nového OCR."""
    res.output = write_pdf(res.output, res.lines, res.lists, res.source, settings)
    return res


def run(paths: list[str], output: str | None = None, progress=None,
        workers: int | None = None, settings: Settings | None = None) -> Result:
    """progress(hotovo, spolu, text) sa volá po každej prečítanej strane.

    Strany sa čítajú v samostatných procesoch (viac naraz), takže okno aplikácie
    medzitým nezamŕza a celé spracovanie je rýchlejšie.
    """
    pages = []  # (súbor, index strany v súbore, poradové číslo strany)
    for path in paths:
        for i in range(page_count(path)):
            pages.append((path, i, len(pages) + 1))
    total = len(pages)
    if progress:
        progress(0, total, f"Čítam {total} strán …")

    settings = (settings or load_settings()).normalized()
    workers = workers or max(1, min(4, (os.cpu_count() or 2) - 1, total))
    results: dict[int, PickList] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(parse_pdf_page, *p, thorough=settings.thorough) for p in pages]
        for done, fut in enumerate(as_completed(futures), 1):
            pl = fut.result()
            results[pl.page] = pl
            if progress:
                progress(done, total, f"Prečítaných {done} z {total} strán …")
    lists = [results[n] for n in sorted(results)]
    if progress:
        progress(total, total, "Vytváram kompletačný list …")

    lists, dropped = drop_duplicates(lists)
    lines = merge(lists)

    output = output or default_output(paths[0])
    source = ", ".join(os.path.basename(p) for p in paths)
    output = write_pdf(output, lines, lists, source, settings)
    return Result(output, lines, lists, dropped, source)
