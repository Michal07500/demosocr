"""Čítanie naskenovaných vychystávacích listov (Démos / VENTUS) pomocou OCR.

Každá strana PDF = jeden vychystávací list. Z hlavičky sa vyčíta číslo dokladu,
zákazník, dátum expedície a číslo zákazky, z tabuľky jednotlivé položky.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field

import cv2
import numpy as np
import pypdfium2 as pdfium
import pytesseract
from pytesseract import Output

LANG = "ces"
RENDER_DPI = 200

# Tesseract: 1) priečinok "tesseract" vedľa aplikácie (.exe), 2) TESSERACT_CMD,
# 3) PATH, 4) bežné miesto inštalácie na Windows.
def _find_tesseract() -> str | None:
    app_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else
                              os.path.dirname(os.path.abspath(__file__)))
    bundled = [os.path.join(app_dir, "tesseract", "tesseract.exe")]
    if getattr(sys, "_MEIPASS", None):
        bundled.append(os.path.join(sys._MEIPASS, "tesseract", "tesseract.exe"))
    for p in bundled:
        if os.path.exists(p):
            return p
    if os.environ.get("TESSERACT_CMD"):
        return os.environ["TESSERACT_CMD"]
    if shutil.which("tesseract"):
        return None
    for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
              r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
        if os.path.exists(p):
            return p
    return None


_tess = _find_tesseract()
if _tess:
    pytesseract.pytesseract.tesseract_cmd = _tess
    _tessdata = os.path.join(os.path.dirname(_tess), "tessdata")
    if os.path.isdir(_tessdata):
        os.environ.setdefault("TESSDATA_PREFIX", _tessdata)


def check_tesseract() -> str | None:
    """Vráti text chyby, ak OCR nie je pripravené, inak None."""
    try:
        langs = pytesseract.get_languages()
    except Exception:  # noqa: BLE001 - tesseract chýba alebo nejde spustiť
        return ("Nenašiel sa program Tesseract OCR.\n"
                "Nainštalujte ho z https://github.com/UB-Mannheim/tesseract/wiki "
                "(aj s jazykom Czech).")
    missing = [l for l in ("ces", "eng") if l not in langs]
    if missing:
        return f"Tesseract nemá nainštalované jazyky: {', '.join(missing)}."
    return None


# Stĺpce tabuľky na liste (poradie zľava):
# 0 Kód | 1 Název | 2 Manipulace | 3 Umístění | 4 Zóna | 5 Jakost
# 6 Hmotnost/mj | 7 Hmotnost/pol | 8 Množství k vychystání | 9 KM

# Záložné pozície hraníc stĺpcov (pri šírke strany 1600 px), ak sa zvislé
# čiary v hlavičke tabuľky nepodarí nájsť. Posúvajú sa podľa polohy slova "Kód".
FALLBACK_BOUNDS = [125, 540, 674, 809, 895, 947, 1050, 1186, 1429]
FALLBACK_KOD_X = 51

LOCATION_RE = re.compile(r"^[A-Z]\d{2}-\d-\d{2}$|^0-00-00$")


@dataclass
class Item:
    kod: str
    nazov: str
    manipulacia: str
    umiestnenie: str
    mnozstvo: float
    km: float | None
    hm_mj: float | None = None
    hm_pol: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class PickList:
    page: int
    doklad: str = ""
    zakazka: str = ""
    zakaznik: str = ""
    obj_zak: str = ""
    expedicia: str = ""
    skupina: str = ""
    mnozstvo_plosne: float | None = None
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Obrázky


def pdf_to_images(path: str, dpi: int = RENDER_DPI) -> list[np.ndarray]:
    pdf = pdfium.PdfDocument(path)
    images = []
    for page in pdf:
        pil = page.render(scale=dpi / 72).to_pil().convert("L")
        images.append(np.array(pil))
    return images


def deskew(gray: np.ndarray) -> np.ndarray:
    """Vyrovná mierne natočený sken podľa dlhých vodorovných čiar (tabuľka, rámčeky)."""
    h, w = gray.shape
    ink = np.where(gray < 160, 255, 0).astype(np.uint8)
    segs = cv2.HoughLinesP(ink, 1, np.pi / 1800, threshold=200, minLineLength=w // 5, maxLineGap=5)
    if segs is None:
        return gray
    angles = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in segs.reshape(-1, 4)]
    angles = [a for a in angles if abs(a) < 5]
    if len(angles) < 3:
        return gray
    angle = float(np.median(angles))
    if abs(angle) < 0.05:
        return gray
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def clean(gray: np.ndarray, blur: int = 3, threshold: int = 150) -> np.ndarray:
    """Odstráni sivé (rastrované) podfarbenie riadkov a nechá len text."""
    b = cv2.GaussianBlur(gray, (blur, blur), 0)
    return np.where(b > threshold, 255, 0).astype(np.uint8)


def keep_main_line(ink: np.ndarray) -> np.ndarray:
    """Nechá len hlavný riadok textu (odstráni zvyšky čiar nad/pod ním)."""
    rows = ink.sum(1) > 0
    runs, start = [], None
    for i, v in enumerate(list(rows) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start, i))
            start = None
    if len(runs) <= 1:
        return ink
    y0, y1 = max(runs, key=lambda r: ink[r[0]:r[1]].sum())
    n, lab, stats, cent = cv2.connectedComponentsWithStats(ink, connectivity=8)
    out = np.zeros_like(ink)
    for i in range(1, n):
        if y0 <= cent[i][1] <= y1:
            out[lab == i] = 1
    return out


def prep_cell(gray: np.ndarray, scale: float = 2.5, strip_lines: bool = False,
              single_line: bool = False, threshold: int = 150) -> np.ndarray:
    big = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    out = clean(big, blur=7, threshold=threshold)
    if strip_lines:
        ink = (out == 0).astype(np.uint8)
        # zahodí drobné škvrny (zvyšky rastra, prach) a ploché úlomky čiar
        n, lab, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            cw, ch = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            if area < 4 * scale * scale or (ch < 3 * scale and cw > 5 * scale):
                ink[lab == i] = 0
        if single_line:
            ink = keep_main_line(ink)
        ys, xs = np.nonzero(ink)
        if len(ys):
            ink = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        out = np.where(ink > 0, 0, 255).astype(np.uint8)
    return cv2.copyMakeBorder(out, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)


def ocr(img: np.ndarray, psm: int = 7, whitelist: str | None = None, lang: str = LANG) -> str:
    cfg = f"--psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(img, lang=lang, config=cfg).strip()


def ocr_number(img: np.ndarray, decimals: int, suffix: str = "") -> float | None:
    """Číslo zo stĺpca tabuľky; čísla číta lepšie anglický model."""
    return parse_number(ocr(img, whitelist="0123456789,." + suffix, lang="eng"), decimals)


# --------------------------------------------------------------------------
# Rozloženie strany


def find_words(cleaned: np.ndarray) -> list[dict]:
    d = pytesseract.image_to_data(cleaned, lang=LANG, config="--psm 11",
                                  output_type=Output.DICT)
    return [
        {"text": t.strip(), "x": d["left"][i], "y": d["top"][i],
         "w": d["width"][i], "h": d["height"][i]}
        for i, t in enumerate(d["text"]) if t.strip()
    ]


def _group(xs: np.ndarray, gap: int = 3) -> list[int]:
    groups: list[list[int]] = []
    for x in xs:
        if groups and x - groups[-1][-1] <= gap:
            groups[-1].append(int(x))
        else:
            groups.append([int(x)])
    return [int(np.mean(g)) for g in groups]


def column_bounds(gray: np.ndarray, kod: dict) -> list[int]:
    """Hranice stĺpcov podľa zvislých čiar v hlavičke tabuľky."""
    h, w = gray.shape
    scale = w / 1600
    y = kod["y"]
    band = gray[max(0, y - int(25 * scale)):y + int(45 * scale)]
    # 3 px široké okno - čiara po natočení/vyrovnaní nemusí byť v jednom stĺpci pixelov
    dark = cv2.dilate((band < 170).astype(np.uint8), np.ones((1, 3), np.uint8)).sum(0)
    xs = np.where(dark > band.shape[0] * 0.6)[0]
    found = _group(xs)
    inner = [x for x in found if kod["x"] + kod["w"] < x < w * 0.95]
    if len(inner) != len(FALLBACK_BOUNDS):
        shift = kod["x"] - FALLBACK_KOD_X * scale
        inner = [int(b * scale + shift) for b in FALLBACK_BOUNDS]
    # vonkajšie okraje tabuľky
    # (ak sa nenájdu, odhadnú sa podľa šírky stĺpcov Kód a KM)
    left = max([x for x in found if x < kod["x"] - 3],
               default=max(0, int(inner[0] - 117 * scale)))
    right = min([x for x in found if x > inner[-1] + 30 * scale],
                default=min(w, int(inner[-1] + 141 * scale)))
    return [left, *inner, right]


def line_mask(ink: np.ndarray, length: int, vertical: bool = False) -> np.ndarray:
    """Pixely patriace k rovným čiaram aspoň danej dĺžky."""
    k = (1, length) if vertical else (length, 1)
    return cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, k)) > 0


def header_bottom(gray: np.ndarray, kod: dict, bounds: list[int]) -> int:
    """Spodná čiara hlavičky tabuľky (hľadá sa v stĺpci Název)."""
    x0, x1 = bounds[1] + 5, bounds[2] - 5
    y0 = kod["y"] + kod["h"]
    lines = line_mask(gray[y0:y0 + 60, x0:x1] < 170, 40)
    rows = np.where(lines.sum(1) > (x1 - x0) * 0.3)[0]
    if not len(rows):
        return y0 + 25
    end = rows[0]
    while end + 1 in rows:
        end += 1
    return y0 + int(end) + 2


def text_lines(mask: np.ndarray, min_h: int = 6) -> list[tuple[int, int]]:
    """Riadky textu podľa vodorovnej projekcie (mask: True = atrament)."""
    prof = mask.sum(1) > 2
    lines, start = [], None
    for i, v in enumerate(prof):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_h:
                lines.append((start, i))
            start = None
    if start is not None and len(prof) - start >= min_h:
        lines.append((start, len(prof)))
    return lines


# --------------------------------------------------------------------------
# Čísla a oprava OCR


def parse_number(s: str, decimals: int) -> float | None:
    """Číslo s pevným počtom desatinných miest (napr. '9,000' alebo '291,0').

    OCR občas stratí desatinnú čiarku ('2910'), preto sa pri jej chýbaní
    desatinné miesta doplnia podľa známeho formátu stĺpca.
    """
    s = s.replace(" ", "").replace("O", "0").replace("o", "0")
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    txt = m.group(0)
    if "," in txt or "." in txt:
        return float(txt.replace(",", "."))
    if len(txt) > decimals:
        return int(txt) / 10 ** decimals
    return float(txt)


def fix_location(s: str) -> str:
    s = re.sub(r"[^A-Z0-9]", "", s.upper().replace("O", "0"))
    if not s:
        return ""
    head, rest = s[0], s[1:]
    if head == "0" and len(s) == 5:  # 0-00-00
        return f"0-{s[1:3]}-{s[3:5]}"
    if head == "0" and rest:
        head = "D"  # D a 0 si OCR rado zamieňa, umiestnenie vždy začína písmenom
    head = {"8": "B", "6": "C", "5": "S", "2": "Z", "1": "I"}.get(head, head)
    if len(rest) == 7 and rest[2] == "0" and rest[4] == "0":  # obe pomlčky prečítané ako 0
        rest = rest[:2] + rest[3] + rest[5:]
    if len(rest) == 6 and rest[2] == "0":  # pomlčka prečítaná ako 0
        rest = rest[:2] + rest[3:]
    if len(rest) == 5:
        return f"{head}{rest[0:2]}-{rest[2]}-{rest[3:5]}"
    return head + rest


# --------------------------------------------------------------------------
# Hlavička listu


def _strip(s: str) -> str:
    """Odstráni diakritiku, dĺžka textu ostane rovnaká (pozície sedia s originálom)."""
    return "".join(unicodedata.normalize("NFKD", c)[0] for c in s)


def parse_header(gray: np.ndarray, kod_y: int, words: list[dict]) -> dict:
    h, w = gray.shape
    info: dict = {}
    text = ocr(prep_cell(gray[int(h * 0.04):kod_y - 10, int(w * 0.41):], scale=2.0), psm=4)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    plain = _strip(text)

    m = re.search(r"VL\s*([0-9O]{10,16})\s*-\s*(\d+)", plain)
    if m:
        info["doklad"] = f"VL{m.group(1).replace('O', '0')}-{m.group(2)}"
    m = re.search(r"expedice\W*(\d{1,2}\.\d{1,2}\.\d{4})", plain, re.I)
    if m:
        info["expedicia"] = m.group(1)
    m = re.search(r"Obj\.?\s*zak\.?\W*(.+?)(?:\s+Pozn|$)", plain, re.M | re.I)
    if m:
        info["obj_zak"] = text[m.start(1):m.end(1)].strip()
    for i, l in enumerate(lines):
        if re.search(r"Doda\w*\s+adres", _strip(l), re.I):
            # zákazník je prvý ďalší riadok; vpravo od neho môže byť "Datum expedice ..."
            for nxt in lines[i + 1:i + 3]:
                name = re.split(r"\s*Datum\b", nxt)[0].strip(" |")
                if re.match(r"(Obj|I[ČC]|Pozn)", name):
                    break  # riadok so zákazníkom OCR vynechalo
                if name:
                    info["zakaznik"] = name
                    break
            break
    # skupina (B / C / KZ) - krátky text pred "Číslo dokladu"
    m = re.search(r"^\W*([A-Z]{1,3})\W+Cislo\s+dokladu", plain, re.M)
    if m:
        info["skupina"] = m.group(1)

    # spodná časť: číslo zákazky a množstvo plošného
    celk = [x for x in words if x["text"].startswith("Celkov") and x["y"] > kod_y]
    y0 = celk[0]["y"] - 10 if celk else kod_y
    y1 = min(h, y0 + int(h * 0.2))
    btext = _strip(ocr(prep_cell(gray[y0:y1], scale=2.0), psm=6))
    m = re.search(r"zakazky\W*(\d{6,12})", btext, re.I)
    if m:
        info["zakazka"] = m.group(1)
    rtext = _strip(ocr(prep_cell(gray[y0:y1, w // 2:], scale=2.0), psm=4))
    m = re.search(r"plosneho\W*(\d+)", rtext, re.I)
    if m:
        info["mnozstvo_plosne"] = float(m.group(1))
    return info


# --------------------------------------------------------------------------
# Tabuľka


def parse_items(gray: np.ndarray, words: list[dict], kod: dict) -> tuple[list[Item], list[str]]:
    h, w = gray.shape
    warnings: list[str] = []
    bounds = column_bounds(gray, kod)
    top = header_bottom(gray, kod, bounds)

    celkova = [x for x in words if x["text"].startswith("Celkov") and x["y"] > top]
    bottom = celkova[0]["y"] - 5 if celkova else min(h, top + int(h * 0.4))

    # odstránenie čiar tabuľky
    work = gray.copy()
    ink = clean(gray[top:bottom]) == 0
    remove = line_mask(ink, 40)
    # zvislé úseky dlhšie ako výška písmena sú vždy čiary tabuľky
    # (mierne rozšírené, aby sa zachytili aj šikmo naskenované čiary)
    wide = cv2.dilate(ink.astype(np.uint8), np.ones((1, 3), np.uint8)) > 0
    remove |= line_mask(wide, 22, vertical=True) & ink
    remove = cv2.dilate(remove.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    work[top:bottom][remove] = 255
    ink &= ~remove

    def cols(i):
        return bounds[i] + (6 if i == 0 else 3), bounds[i + 1] - 2

    nx0, nx1 = cols(1)
    lines = text_lines(ink[:, nx0 + 3:nx1 - 3])
    kx0, kx1 = cols(0)

    # zoskupenie riadkov do položiek: nová položka = riadok s kódom
    groups: list[list[tuple[int, int]]] = []
    for y0, y1 in lines:
        has_code = ink[y0:y1, kx0 + 3:kx1 - 3].sum() > 15
        if has_code or not groups:
            groups.append([(y0, y1)])
        else:
            groups[-1].append((y0, y1))

    items: list[Item] = []
    for gi, g in enumerate(groups):
        # riadok položky siaha až po začiatok ďalšej (hodnoty sú zvislo centrované)
        y0 = max(0, g[0][0] - 4) + top
        y1 = (groups[gi + 1][0][0] - 2 if gi + 1 < len(groups) else g[-1][1] + 12) + top

        def cell(ci):
            x0, x1 = cols(ci)
            return prep_cell(work[y0:y1, x0:x1], strip_lines=True, single_line=ci != 1,
                             threshold=130 if ci == 1 else 150)

        kod_txt = ocr(cell(0), whitelist="0123456789", lang="eng")
        nazov = " ".join(ocr(cell(1), psm=6).split())
        manip = ocr(cell(2))
        umiest = fix_location(ocr(cell(3), whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-", lang="eng"))
        hm_mj = ocr_number(cell(6), 1)
        hm_pol = ocr_number(cell(7), 1, "kg")
        mnoz = ocr_number(cell(8), 3, "ksm")
        km = ocr_number(cell(9), 1)

        it = Item(kod=re.sub(r"\D", "", kod_txt), nazov=cleanup_name(nazov),
                  manipulacia=cleanup_manip(manip), umiestnenie=umiest,
                  mnozstvo=mnoz or 0.0, km=km, hm_mj=hm_mj, hm_pol=hm_pol)
        if not it.kod and not it.mnozstvo and not umiest:
            continue  # zvyšky čiar / šumu pod tabuľkou, nie položka
        validate_item(it)
        items.append(it)
    if not items:
        warnings.append("Nenašla sa žiadna položka v tabuľke")
    return items, warnings


MANIPULACIE = ["Stáhnout", "Zvedat", "Proložit", "Ručně"]


def cleanup_manip(s: str) -> str:
    if not re.search(r"[A-Za-zÀ-ž]{3}", s):
        return ""
    best = difflib.get_close_matches(s.strip(" |"), MANIPULACIE, n=1, cutoff=0.4)
    return best[0] if best else s.strip(" |")


# Typické začiatky názvov - prvé slovo sa podľa nich opraví, ak ho OCR pokazí.
NAME_PREFIXES = ["DTDL", "DTD", "HDF", "MDF", "PerfectSense", "PT", "OSB", "LTD", "ABS",
                 "Kompakt", "Pracovná", "Hrana"]


def cleanup_name(s: str) -> str:
    s = re.sub(r"[|©“”„»«]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .-—_:;'")
    s = re.sub(r"(\s+[^\w\s]+|\s+[^\W\d])+$", "", s)  # osamotené znaky na konci
    s = re.sub(r"^([^\w\s]+\s+|[^\W\d]\s+)+", "", s)  # ...a na začiatku
    s = re.sub(r"[-—.]{2,}$", "", s)
    s = s.replace("STS ", "ST9 ")
    first, _, rest = s.partition(" ")
    if first not in NAME_PREFIXES:
        fixed = difflib.get_close_matches(first.strip("()[]{}"), NAME_PREFIXES, n=1, cutoff=0.5)
        if fixed and len(first) >= 3:
            s = f"{fixed[0]} {rest}".strip()
    return s


WEIGHT_MISMATCH = "množstvo nesedí s hmotnosťou"


def validate_item(it: Item) -> None:
    if not re.fullmatch(r"\d{4,7}", it.kod):
        it.warnings.append(f"nečitateľný kód '{it.kod}'")
    if not LOCATION_RE.match(it.umiestnenie):
        it.warnings.append(f"umiestnenie '{it.umiestnenie}'")
    if it.mnozstvo <= 0:
        it.warnings.append("chýba množstvo")
    # krížová kontrola: hmotnosť/pol ≈ hmotnosť/mj × množstvo
    if it.hm_mj and it.hm_pol and it.mnozstvo:
        exp = it.hm_mj * it.mnozstvo
        if abs(exp - it.hm_pol) > max(0.6, 0.02 * it.hm_pol):
            it.warnings.append(WEIGHT_MISMATCH)


def fmt(x: float | None) -> str:
    if x is None:
        return ""
    return str(int(x)) if float(x).is_integer() else f"{x:.3f}".rstrip("0").replace(".", ",")


# --------------------------------------------------------------------------


# Referenčné x pozície slov v hlavičke tabuľky (šírka strany 1600 px).
HEADER_WORDS = {"kod": 49, "nazev": 303, "manipulace": 553, "umisteni": 700}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if c.isalpha() and not unicodedata.combining(c)).lower()


def find_table_anchor(words: list[dict], width: int) -> dict | None:
    """Poloha hlavičky tabuľky - vráti pseudo-slovo 'Kód' (x, y, w, h)."""
    scale = width / 1600
    hits = []
    for wd in words:
        n = _norm(wd["text"])
        for key, ref_x in HEADER_WORDS.items():
            if n == key or (len(n) >= 5 and difflib.SequenceMatcher(None, n, key).ratio() > 0.8):
                hits.append((wd, wd["x"] - ref_x * scale))
    if not hits:
        return None
    # najčastejší riadok (slová hlavičky sú v jednej výške)
    ys = sorted(h[0]["y"] for h in hits)
    y = ys[len(ys) // 2]
    row = [h for h in hits if abs(h[0]["y"] - y) < 25 * scale]
    shift = float(np.median([s for _, s in row]))
    return {"x": int(HEADER_WORDS["kod"] * scale + shift), "y": int(np.median([w["y"] for w, _ in row])),
            "w": int(36 * scale), "h": int(17 * scale)}


def parse_page(gray: np.ndarray, page_no: int) -> PickList:
    pl = PickList(page=page_no)
    gray = deskew(gray)
    words = find_words(clean(gray))
    kod = find_table_anchor(words, gray.shape[1])
    if kod is None:
        pl.warnings.append("Nenašla sa tabuľka (hlavička 'Kód / Název')")
        return pl
    for k, v in parse_header(gray, kod["y"], words).items():
        setattr(pl, k, v)
    pl.items, warns = parse_items(gray, words, kod)
    pl.warnings += warns
    if pl.mnozstvo_plosne is not None:
        total = sum(i.mnozstvo for i in pl.items)
        if abs(total - pl.mnozstvo_plosne) > 0.01:
            pl.warnings.append(
                f"súčet množstiev {fmt(total)} ≠ 'Množství plošného' {fmt(pl.mnozstvo_plosne)}")
        else:
            # súčet sedí s listom -> množstvá sú isto správne, chyba je len v čítaní hmotnosti
            for it in pl.items:
                it.warnings = [w for w in it.warnings if w != WEIGHT_MISMATCH]
    return pl


def parse_pdf(path: str, progress=None) -> list[PickList]:
    out = []
    images = pdf_to_images(path)
    for i, img in enumerate(images, 1):
        if progress:
            progress(i, len(images))
        out.append(parse_page(img, i))
    return out
