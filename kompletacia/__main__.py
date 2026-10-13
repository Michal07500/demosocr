"""Použitie:  python -m kompletacia vychystavacie_listy.pdf [ďalšie.pdf ...] [-o vystup.pdf]"""
from __future__ import annotations

import argparse
import os
import sys

from .aggregate import drop_duplicates, merge
from .ocr import fmt, parse_pdf
from .report import build_pdf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="kompletacia",
        description="Zo skenu vychystávacích listov vytvorí jeden kompletačný list "
                    "(rovnaké dosky zlúčené, zoradené podľa umiestnenia).")
    ap.add_argument("pdf", nargs="+", help="naskenované vychystávacie listy (PDF)")
    ap.add_argument("-o", "--output", help="výstupné PDF (predvolene <vstup>_kompletacia.pdf)")
    args = ap.parse_args(argv)

    lists = []
    for path in args.pdf:
        print(f"Čítam {path} ...", file=sys.stderr)
        lists += parse_pdf(path, progress=lambda i, n: print(f"  strana {i}/{n}", file=sys.stderr))
    lists, dropped = drop_duplicates(lists)
    for pl in dropped:
        print(f"Pozor: list {pl.doklad} (strana {pl.page}) je naskenovaný dvakrát - započítaný raz.",
              file=sys.stderr)
    lines = merge(lists)

    out = args.output or os.path.splitext(args.pdf[0])[0] + "_kompletacia.pdf"
    build_pdf(out, lines, lists, source=", ".join(args.pdf))

    print(f"\n{'Umiestnenie':<12} {'Kód':<8} {'Ks':>6} {'KM':>7}  Názov")
    for l in lines:
        km = "/".join(fmt(l.km[u]) for u in l.umiestnenia if u in l.km)
        print(f"{','.join(l.umiestnenia):<12} {l.kod:<8} {fmt(l.mnozstvo):>6} {km:>7}  {l.nazov}"
              + ("   ⚠ SKONTROLUJ" if l.warnings else ""))
    warn = sum(bool(l.warnings) for l in lines) + sum(bool(p.warnings) for p in lists)
    print(f"\nHotovo: {out}")
    if warn:
        print(f"Pozor: {warn} miest treba skontrolovať (žlté riadky v PDF).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
