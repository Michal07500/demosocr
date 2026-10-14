"""Zlúčenie rovnakých dosiek zo všetkých vychystávacích listov."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .ocr import Item, PickList


@dataclass
class Allocation:
    """Koľko kusov danej dosky patrí ku ktorému listu / zákazke."""
    doklad: str
    zakazka: str
    zakaznik: str
    obj_zak: str
    expedicia: str
    umiestnenie: str
    mnozstvo: float
    page: int


@dataclass
class Line:
    kod: str
    nazov: str
    manipulacia: str
    umiestnenia: list[str]
    km: dict[str, float]          # umiestnenie -> KM
    mnozstvo: float
    allocations: list[Allocation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    order: int = 0                # poradie prvého výskytu na vychystávacích listoch


def _best(values: list[str]) -> str:
    """Najčastejšia hodnota; pri zhode tá, ktorá vyzerá najčistejšie."""
    values = [v for v in values if v]
    if not values:
        return ""
    counts = Counter(values)

    def score(v: str):
        junk = len(re.findall(r"[^\w\s./,()-]", v))
        return (counts[v], -junk, len(v))

    return max(counts, key=score)


def _location_key(loc: str):
    """Poradie pre trasu skladom: C04-0-01 < C08-0-01 < D01-0-01 ..."""
    m = re.match(r"([A-Z]+)(\d+)-(\d+)-(\d+)", loc)
    if m:
        return (0, m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return (1, loc, 0, 0, 0)


def drop_duplicates(lists: list[PickList]) -> tuple[list[PickList], list[PickList]]:
    """Odstráni listy naskenované viackrát (rovnaký doklad aj rovnaké položky)."""
    seen: set = set()
    kept, dropped = [], []
    for pl in lists:
        key = (pl.doklad, tuple((i.kod, i.umiestnenie, i.mnozstvo) for i in pl.items))
        if pl.doklad and key in seen:
            dropped.append(pl)
            continue
        seen.add(key)
        kept.append(pl)
    return kept, dropped


def merge(lists: list[PickList]) -> list[Line]:
    groups: dict[str, list[tuple[PickList, Item]]] = {}
    for pl in lists:
        for it in pl.items:
            # bez čitateľného kódu sa položky zlučujú aspoň podľa názvu
            key = it.kod if re.fullmatch(r"\d{4,7}", it.kod) else f"?{it.nazov}"
            groups.setdefault(key, []).append((pl, it))

    lines: list[Line] = []
    for order, entries in enumerate(groups.values()):
        items = [it for _, it in entries]
        locs: list[str] = []
        km: dict[str, float] = {}
        for it in items:
            if it.umiestnenie and it.umiestnenie not in locs:
                locs.append(it.umiestnenie)
            if it.km is not None and it.umiestnenie:
                km.setdefault(it.umiestnenie, it.km)
        locs.sort(key=_location_key)
        line = Line(
            kod=items[0].kod,
            nazov=_best([it.nazov for it in items]),
            manipulacia=_best([it.manipulacia for it in items]),
            umiestnenia=locs,
            km=km,
            mnozstvo=sum(it.mnozstvo for it in items),
            order=order,
        )
        for pl, it in entries:
            line.allocations.append(Allocation(
                doklad=pl.doklad, zakazka=pl.zakazka, zakaznik=pl.zakaznik,
                obj_zak=pl.obj_zak, expedicia=pl.expedicia,
                umiestnenie=it.umiestnenie, mnozstvo=it.mnozstvo, page=pl.page))
            line.warnings += [f"str. {pl.page}: {w}" for w in it.warnings]
        lines.append(line)

    return sort_lines(lines, "umiestnenie")


def _kod_key(kod: str):
    return (0, int(kod), "") if kod.isdigit() else (1, 0, kod)


def sort_lines(lines: list[Line], how: str) -> list[Line]:
    """Zoradenie riadkov kompletačného listu (možnosti v settings.SORTS)."""
    by_location = lambda l: (_location_key(l.umiestnenia[0]) if l.umiestnenia else (2,),  # noqa: E731
                             _kod_key(l.kod))
    keys = {
        "umiestnenie": by_location,
        "kod": lambda l: _kod_key(l.kod),
        "nazov": lambda l: (l.nazov.casefold(), _kod_key(l.kod)),
        "mnozstvo": lambda l: (-l.mnozstvo, by_location(l)),
        "poradie": lambda l: l.order,
    }
    return sorted(lines, key=keys.get(how, by_location))
