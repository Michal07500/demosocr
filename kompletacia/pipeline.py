"""Celý postup: skeny -> OCR -> zlúčenie -> PDF. Spoločné pre príkazový riadok aj aplikáciu."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from .aggregate import Line, drop_duplicates, merge
from .ocr import PickList, pdf_to_images, parse_page
from .report import build_pdf


@dataclass
class Result:
    output: str
    lines: list[Line]
    lists: list[PickList]
    dropped: list[PickList]

    @property
    def warning_count(self) -> int:
        return sum(bool(l.warnings) for l in self.lines) + sum(bool(p.warnings) for p in self.lists)


def default_output(first_input: str) -> str:
    return os.path.splitext(first_input)[0] + "_kompletacia.pdf"


def run(paths: list[str], output: str | None = None, progress=None) -> Result:
    """progress(hotovo, spolu, text) sa volá pred každou stranou."""
    images = []
    for path in paths:
        images += pdf_to_images(path)

    lists = []
    for i, img in enumerate(images, 1):
        if progress:
            progress(i - 1, len(images), f"Čítam stranu {i} z {len(images)} …")
        lists.append(parse_page(img, i))
    if progress:
        progress(len(images), len(images), "Vytváram kompletačný list …")

    lists, dropped = drop_duplicates(lists)
    lines = merge(lists)

    output = output or default_output(paths[0])
    source = ", ".join(os.path.basename(p) for p in paths)
    try:
        build_pdf(output, lines, lists, source=source)
    except PermissionError:
        # súbor je otvorený v prehliadači PDF (Windows ho zamkne) -> nový názov
        stem = os.path.splitext(output)[0]
        output = f"{stem}_{datetime.now():%H%M%S}.pdf"
        build_pdf(output, lines, lists, source=source)
    return Result(output, lines, lists, dropped)
