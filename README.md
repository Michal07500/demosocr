# Kompletačný list z vychystávacích listov

Program zoberie **naskenované vychystávacie listy** (PDF zo skenera, každá strana = jeden
list z VENTUS / Démos) a vytvorí z nich **jeden kompletačný list**:

- rovnaké dosky (rovnaký **Kód**) z rôznych listov sa **zlúčia** a množstvá sa sčítajú,
- riadky sú zoradené podľa **umiestnenia** (C04-0-01, C08-0-01, D01-0-01, …), aby sa dalo
  ísť skladom po poradí,
- pri každej doske ostáva **Názov, Umiestnenie, Množstvo k vychystaniu, KM, Manipulácia**
  a rozpis, koľko kusov patrí ku ktorej **zákazke / zákazníkovi**,
- na konci je prehľad všetkých vychystávacích listov (doklad, zákazka, zákazník,
  obj. zák., dátum expedície).

Počet listov aj počet položiek na liste môže byť ľubovoľný.

## Kontroly

Sken sa číta cez OCR, preto program sám kontroluje, či čítanie sedí:

- súčet množstiev na liste sa porovná s riadkom **„Množství plošného“**,
- množstvo sa porovná s hmotnosťou (*Hmotnost/mj × množstvo ≈ Hmotnost/pol*),
- kód musí byť číslo, umiestnenie v tvare `X00-0-00`,
- ten istý list naskenovaný dvakrát sa započíta len raz.

Ak niečo nesedí, riadok je v PDF **žltý** s textom „⚠ skontroluj“ — vtedy treba hodnotu
overiť na pôvodnom liste.

## Aplikácia pre Windows (odporúčané)

Hotová aplikácia nič nepotrebuje inštalovať – OCR (Tesseract s češtinou) je pribalený.

1. Na GitHube otvorte **Actions → „Windows aplikácia“** → posledný úspešný beh a stiahnite
   artefakt **KompletacnyList-Windows** (alebo ZIP z **Releases**, ak je vydaná verzia).
2. ZIP rozbaľte napr. do `C:\KompletacnyList` (celý priečinok, nie len .exe).
3. Spustite **`KompletacnyList.exe`** (pre pohodlie: pravým tlačidlom → *Odoslať na → Pracovná
   plocha (vytvoriť zástupcu)*).

Ovládanie:

1. **Vybrať naskenované PDF** – jedno alebo viac PDF zo skenera.
2. **Vytvoriť kompletačný list** – priebeh ukazuje, ktorá strana sa číta.
3. Výsledok sa zobrazí v okne (sporné riadky žlto) a PDF sa samo otvorí;
   tlačidlá **Otvoriť PDF / Vytlačiť / Otvoriť priečinok**.

PDF sa uloží vedľa skenu ako `<názov skenu>_kompletacia.pdf`. PDF sa dá pretiahnuť aj
priamo na ikonu `KompletacnyList.exe` – spracuje sa hneď.

Nová verzia aplikácie sa zostaví automaticky po každom pushi; vydanie do *Releases* vznikne
po pridaní tagu, napr. `git tag v1.0 && git push --tags`.

## Spustenie zo zdrojového kódu

Potrebný je Python 3.10+ a OCR program **Tesseract** s češtinou.

**Windows:** Python z <https://www.python.org/downloads/> (*Add to PATH*), Tesseract z
<https://github.com/UB-Mannheim/tesseract/wiki> (v *Additional language data* zaškrtnúť
**Czech**), potom `pip install -r requirements.txt`.

**Linux:** `sudo apt install tesseract-ocr tesseract-ocr-ces python3-tk` a
`pip install -r requirements.txt`.

```bash
python KompletacnyList.py                 # okno aplikácie
python -m kompletacia sken.pdf            # bez okna, vznikne sken_kompletacia.pdf
python -m kompletacia rano.pdf obed.pdf -o kompletacia_dnes.pdf
```

Spracovanie trvá približne 5 sekúnd na stranu.

## Testy

```bash
python -m pytest
# aj s reálnym skenom:
KOMPLETACIA_SAMPLE_PDF=cesta/k/skenu.pdf python -m pytest
```
