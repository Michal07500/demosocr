import os

import pytest

from kompletacia.aggregate import drop_duplicates, merge
from kompletacia.ocr import (Item, PickList, cleanup_name, fix_location, parse_number,
                             validate_item)

SAMPLE = os.environ.get("KOMPLETACIA_SAMPLE_PDF", "")


def test_parse_number_with_and_without_comma():
    assert parse_number("9,000 ks", 3) == 9
    assert parse_number("115,000ks", 3) == 115
    assert parse_number("291,0", 1) == 291
    assert parse_number("2910", 1) == 291  # stratená čiarka
    assert parse_number("12.2", 1) == 12.2
    assert parse_number("", 1) is None


def test_fix_location():
    assert fix_location("C08-0-01") == "C08-0-01"
    assert fix_location("D120005") == "D12-0-05"  # pomlčka prečítaná ako 0
    assert fix_location("D12005") == "D12-0-05"
    assert fix_location("012-0-05") == "D12-0-05"
    assert fix_location("0-00-00") == "0-00-00"


def test_cleanup_name():
    assert cleanup_name("DTDL 164 PE BU Anthracite 2800/2070/18 a") == \
        "DTDL 164 PE BU Anthracite 2800/2070/18"
    assert cleanup_name("© grrootSense DTD W1000").startswith("PerfectSense DTD")
    assert cleanup_name("DTODL 164 PE").startswith("DTDL ")


def test_validate_item_weight_check():
    ok = Item("235859", "x", "", "C08-0-01", 9, 291, hm_mj=73.0, hm_pol=657.3)
    validate_item(ok)
    assert ok.warnings == []
    bad = Item("235859", "x", "", "C08-0-01", 6, 291, hm_mj=73.0, hm_pol=657.3)
    validate_item(bad)
    assert any("hmotnos" in w for w in bad.warnings)


def _pl(page, doklad, zakazka, items):
    return PickList(page=page, doklad=doklad, zakazka=zakazka, zakaznik=f"Z{page}", items=items)


def test_merge_same_boards():
    a = _pl(1, "VL1-1", "100", [Item("307960", "DTDL U216", "Stáhnout", "C14-0-02", 3, 51),
                                Item("59678", "HDF LAK", "Stáhnout", "D01-0-01", 1, 655)])
    b = _pl(2, "VL2-1", "200", [Item("307960", "DTDL U216", "Stáhnout", "C14-0-02", 2, 51)])
    c = _pl(3, "VL3-1", "300", [Item("235859", "DTDL U702", "Stáhnout", "C08-0-01", 9, 291)])
    lines = merge([a, b, c])
    assert [l.kod for l in lines] == ["235859", "307960", "59678"]  # podľa umiestnenia
    u216 = lines[1]
    assert u216.mnozstvo == 5
    assert [(x.zakazka, x.mnozstvo) for x in u216.allocations] == [("100", 3), ("200", 2)]
    assert u216.km == {"C14-0-02": 51}


def test_merge_same_board_two_locations():
    a = _pl(1, "VL1-1", "100", [Item("307960", "DTDL U216", "", "C14-0-02", 3, 51)])
    b = _pl(2, "VL2-1", "200", [Item("307960", "DTDL U216", "", "B02-0-01", 2, 10)])
    (line,) = merge([a, b])
    assert line.umiestnenia == ["B02-0-01", "C14-0-02"]
    assert line.mnozstvo == 5


def test_drop_duplicate_scans():
    items = [Item("307960", "DTDL U216", "", "C14-0-02", 3, 51)]
    a = _pl(1, "VL1-1", "100", items)
    dup = _pl(2, "VL1-1", "100", list(items))
    other_page = _pl(3, "VL1-1", "100", [Item("59678", "HDF", "", "D01-0-01", 1, 655)])
    kept, dropped = drop_duplicates([a, dup, other_page])
    assert kept == [a, other_page]
    assert dropped == [dup]


@pytest.mark.skipif(not os.path.exists(SAMPLE), reason="nastav KOMPLETACIA_SAMPLE_PDF")
def test_sample_pdf():
    from kompletacia.ocr import parse_pdf
    lists = parse_pdf(SAMPLE)
    lines = merge(lists)
    for pl in lists:
        assert pl.items, pl.warnings
    assert all(not l.warnings for l in lines), [l.warnings for l in lines]


def test_settings_roundtrip_and_cleanup(tmp_path):
    from kompletacia import settings as cfg
    path = str(tmp_path / "x" / "nastavenia.json")
    assert cfg.load(path) == cfg.Settings()  # chýbajúci súbor -> predvolené
    cfg.save(cfg.Settings(columns=["mnozstvo", "kod", "neznamy", "kod"], sort="nazov",
                          lists_overview=False), path)
    loaded = cfg.load(path)
    assert loaded.columns == ["mnozstvo", "kod"]
    assert loaded.sort == "nazov" and loaded.lists_overview is False
    with open(path, "w", encoding="utf-8") as f:
        f.write("{pokazené")
    assert cfg.load(path) == cfg.Settings()


def test_sort_lines():
    from kompletacia.aggregate import sort_lines
    a = _pl(1, "VL1-1", "100", [Item("500", "Zeta", "", "D01-0-01", 1, 1),
                                Item("40", "Alfa", "", "C02-0-01", 5, 1)])
    b = _pl(2, "VL2-1", "200", [Item("1000", "Beta", "", "B09-0-01", 2, 1)])
    lines = merge([a, b])
    assert [l.kod for l in sort_lines(lines, "umiestnenie")] == ["1000", "40", "500"]
    assert [l.kod for l in sort_lines(lines, "kod")] == ["40", "500", "1000"]
    assert [l.nazov for l in sort_lines(lines, "nazov")] == ["Alfa", "Beta", "Zeta"]
    assert [l.kod for l in sort_lines(lines, "mnozstvo")] == ["40", "1000", "500"]
    assert [l.kod for l in sort_lines(lines, "poradie")] == ["500", "40", "1000"]


def test_pdf_with_custom_columns(tmp_path):
    from pypdf import PdfReader
    from kompletacia.report import build_pdf
    from kompletacia.settings import Settings
    it = Item("307960", "DTDL U216", "Stáhnout", "C14-0-02", 3, 51)
    it.warnings.append("umiestnenie 'C14'")
    lines = merge([_pl(1, "VL1-1", "261073189", [it])])
    out = str(tmp_path / "k.pdf")
    build_pdf(out, lines, [], settings=Settings(columns=["mnozstvo", "umiestnenie", "kod"],
                                                 lists_overview=False))
    text = PdfReader(out).pages[0].extract_text()
    assert "Vychystať" in text and "C14-0-02" in text and "307960" in text
    assert "DTDL U216" not in text            # skrytý stĺpec Názov
    assert "skontroluj" in text               # upozornenie ostane viditeľné
    assert "Vychystávacie listy" not in text  # vypnutý prehľad
    assert text.index("Vychystať") < text.index("Umiestnenie") < text.index("Kód")
