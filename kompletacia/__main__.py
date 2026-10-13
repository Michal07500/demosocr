"""Použitie:  python -m kompletacia vychystavacie_listy.pdf [ďalšie.pdf ...] [-o vystup.pdf]

Bez parametrov (alebo s --gui) sa otvorí okno aplikácie.
"""
from __future__ import annotations

import argparse
import sys

from .ocr import fmt
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] == "--gui":
        from .gui import main as gui_main
        gui_main(argv[1:])
        return 0

    ap = argparse.ArgumentParser(
        prog="kompletacia",
        description="Zo skenu vychystávacích listov vytvorí jeden kompletačný list "
                    "(rovnaké dosky zlúčené, zoradené podľa umiestnenia).")
    ap.add_argument("pdf", nargs="+", help="naskenované vychystávacie listy (PDF)")
    ap.add_argument("-o", "--output", help="výstupné PDF (predvolene <vstup>_kompletacia.pdf)")
    args = ap.parse_args(argv)

    res = run(args.pdf, args.output, progress=lambda i, n, text: print(text, file=sys.stderr))
    for pl in res.dropped:
        print(f"Pozor: list {pl.doklad} (strana {pl.page}) je naskenovaný dvakrát - započítaný raz.",
              file=sys.stderr)

    print(f"\n{'Umiestnenie':<12} {'Kód':<8} {'Ks':>6} {'KM':>7}  Názov")
    for l in res.lines:
        km = "/".join(fmt(l.km[u]) for u in l.umiestnenia if u in l.km)
        print(f"{','.join(l.umiestnenia):<12} {l.kod:<8} {fmt(l.mnozstvo):>6} {km:>7}  {l.nazov}"
              + ("   ⚠ SKONTROLUJ" if l.warnings else ""))
    print(f"\nHotovo: {res.output}")
    if res.warning_count:
        print(f"Pozor: {res.warning_count} miest treba skontrolovať (žlté riadky v PDF).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
