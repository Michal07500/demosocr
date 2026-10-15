"""Nastavenia kompletačného listu (poradie a výber stĺpcov, zoradenie riadkov).

Ukladajú sa do súboru nastavenia.json v priečinku používateľa
(Windows: %APPDATA%\\KompletacnyList).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field

# kľúč -> (nadpis v PDF, názov v nastaveniach, základná šírka v mm)
COLUMNS: dict[str, tuple[str, str, float]] = {
    "check": ("✓", "Políčko na odškrtnutie ☐", 8),
    "umiestnenie": ("Umiestnenie", "Umiestnenie", 27),
    "kod": ("Kód", "Kód", 18),
    "nazov": ("Názov", "Názov", 80),
    "manipulacia": ("Manip.", "Manipulácia", 22),
    "mnozstvo": ("Vychystať", "Množstvo k vychystaniu", 27),
    "km": ("KM", "KM", 16),
    "rozpis": ("Rozpis (zákazka · zákazník)", "Rozpis po zákazkách", 79),
}
DEFAULT_COLUMNS = list(COLUMNS)

SORTS: dict[str, str] = {
    "umiestnenie": "podľa umiestnenia (trasa skladom)",
    "kod": "podľa kódu",
    "nazov": "podľa názvu",
    "mnozstvo": "podľa množstva (najviac kusov hore)",
    "poradie": "v poradí ako na vychystávacích listoch",
}


ORIENTATIONS = {"landscape": "na šírku", "portrait": "na výšku"}


@dataclass
class Settings:
    columns: list[str] = field(default_factory=lambda: list(DEFAULT_COLUMNS))  # viditeľné, v poradí
    sort: str = "umiestnenie"
    lists_overview: bool = True   # tabuľka vychystávacích listov na konci
    orientation: str = "landscape"  # formát strany PDF
    thorough: bool = True         # viac času na rozoznanie (presnejšie, pomalšie)

    def normalized(self) -> "Settings":
        cols = [c for c in dict.fromkeys(self.columns) if c in COLUMNS] or list(DEFAULT_COLUMNS)
        sort = self.sort if self.sort in SORTS else "umiestnenie"
        orient = self.orientation if self.orientation in ORIENTATIONS else "landscape"
        return Settings(cols, sort, bool(self.lists_overview), orient, bool(self.thorough))


def config_path() -> str:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        folder = os.path.join(base, "KompletacnyList")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        folder = os.path.join(base, "kompletacia")
    return os.path.join(folder, "nastavenia.json")


def load(path: str | None = None) -> Settings:
    path = path or config_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return Settings(columns=list(data.get("columns", DEFAULT_COLUMNS)),
                        sort=str(data.get("sort", "umiestnenie")),
                        lists_overview=bool(data.get("lists_overview", True)),
                        orientation=str(data.get("orientation", "landscape")),
                        thorough=bool(data.get("thorough", True))).normalized()
    except (OSError, ValueError, TypeError, AttributeError):
        return Settings()


def save(settings: Settings, path: str | None = None) -> None:
    path = path or config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(settings.normalized()), f, ensure_ascii=False, indent=2)
