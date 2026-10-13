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

## Inštalácia

Potrebný je Python 3.10+ a OCR program **Tesseract** s češtinou.

**Windows**

1. Python: <https://www.python.org/downloads/> (pri inštalácii zaškrtnúť *Add to PATH*).
2. Tesseract: <https://github.com/UB-Mannheim/tesseract/wiki> – pri inštalácii v časti
   *Additional language data* zaškrtnúť **Czech**. Program ho hľadá v
   `C:\Program Files\Tesseract-OCR\`, inak nastavte premennú `TESSERACT_CMD`.
3. V priečinku projektu: `pip install -r requirements.txt`

**Linux (Ubuntu/Debian)**

```bash
sudo apt install tesseract-ocr tesseract-ocr-ces
pip install -r requirements.txt
```

## Použitie

```bash
python -m kompletacia sken.pdf
```

Vznikne `sken_kompletacia.pdf` vedľa pôvodného súboru. Viac súborov naraz a vlastný názov
výstupu:

```bash
python -m kompletacia rano.pdf obed.pdf -o kompletacia_dnes.pdf
```

Na Windows stačí PDF **pretiahnuť myšou na `kompletacia.bat`** – kompletačný list sa
vytvorí a otvorí.

Spracovanie trvá približne 5 sekúnd na stranu.

## Testy

```bash
python -m pytest
# aj s reálnym skenom:
KOMPLETACIA_SAMPLE_PDF=cesta/k/skenu.pdf python -m pytest
```
