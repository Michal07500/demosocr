"""Okno aplikácie: vybrať skeny -> vytvoriť kompletačný list -> otvoriť / vytlačiť."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import settings as cfg
from .aggregate import sort_lines
from .ocr import check_tesseract, fmt
from .pipeline import Result, default_output, rebuild, run

APP_TITLE = "Kompletačný list"


def open_file(path: str, action: str = "open") -> None:
    if sys.platform == "win32":
        os.startfile(path, action)  # noqa: S606 - otvorenie PDF v predvolenom programe
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class App(ttk.Frame):
    def __init__(self, root: tk.Tk, files: list[str]):
        super().__init__(root, padding=12)
        self.root = root
        self.files: list[str] = []
        self.result: Result | None = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        root.title(APP_TITLE)
        root.geometry("1100x650")
        root.minsize(800, 450)
        self.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        style = ttk.Style()
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))

        # --- 1. výber súborov
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, columnspan=2,
                                                                    sticky="w", pady=(0, 8))
        self.settings_btn = ttk.Button(top, text="⚙ Nastavenia", command=self.open_settings)
        self.settings_btn.grid(row=0, column=2, sticky="ne")
        self.pick_btn = ttk.Button(top, text="1. Vybrať naskenované PDF …", command=self.pick,
                                   style="Big.TButton")
        self.pick_btn.grid(row=1, column=0, sticky="w")
        self.files_var = tk.StringVar(value="Nie je vybraný žiadny súbor.")
        ttk.Label(top, textvariable=self.files_var, wraplength=600).grid(row=1, column=1, sticky="w",
                                                                         padx=12)
        self.run_btn = ttk.Button(top, text="2. Vytvoriť kompletačný list", command=self.start,
                                  style="Big.TButton", state="disabled")
        self.run_btn.grid(row=1, column=2, sticky="e")

        # --- priebeh
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 4))
        status = ttk.Frame(self)
        status.grid(row=2, column=0, sticky="ew")
        status.columnconfigure(1, weight=1)
        # točiace sa koliesko - ukazuje, že program pracuje
        bg = ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        self.spinner = tk.Canvas(status, width=26, height=26, highlightthickness=0, bg=bg)
        self.spinner.grid(row=0, column=0, padx=(0, 6))
        self.spinner_arc = self.spinner.create_arc(3, 3, 23, 23, start=0, extent=0,
                                                   style="arc", width=4, outline="#2563eb")
        self.spinner_angle = 0
        self.status_var = tk.StringVar(value="Vyberte PDF so skenom vychystávacích listov "
                                             "(môže ich byť aj viac naraz).")
        ttk.Label(status, textvariable=self.status_var).grid(row=0, column=1, sticky="w")
        self.time_var = tk.StringVar()
        ttk.Label(status, textvariable=self.time_var, foreground="#555").grid(row=0, column=2,
                                                                             sticky="e")
        self.started_at = 0.0

        # --- výsledok
        table = ttk.Frame(self)
        table.grid(row=3, column=0, sticky="nsew", pady=8)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        cols = ("umiestnenie", "kod", "nazov", "ks", "km", "rozpis")
        self.tree = ttk.Treeview(table, columns=cols, show="headings")
        for c, title, width, anchor in (
                ("umiestnenie", "Umiestnenie", 100, "w"), ("kod", "Kód", 70, "w"),
                ("nazov", "Názov", 380, "w"), ("ks", "Vychystať", 80, "e"),
                ("km", "KM", 60, "e"), ("rozpis", "Zákazky", 330, "w")):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor=anchor, stretch=c in ("nazov", "rozpis"))
        self.tree.tag_configure("warn", background="#fff3cd")
        self.tree.tag_configure("total", font=("Segoe UI", 10, "bold"))
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        # --- 3. akcie s hotovým PDF
        bottom = ttk.Frame(self)
        bottom.grid(row=4, column=0, sticky="ew")
        self.open_btn = ttk.Button(bottom, text="Otvoriť PDF", style="Big.TButton",
                                   command=lambda: self.open_output("open"), state="disabled")
        self.print_btn = ttk.Button(bottom, text="Vytlačiť", style="Big.TButton",
                                    command=lambda: self.open_output("print"), state="disabled")
        self.folder_btn = ttk.Button(bottom, text="Otvoriť priečinok", command=self.open_folder,
                                     state="disabled")
        self.open_btn.pack(side="left")
        if sys.platform == "win32":
            self.print_btn.pack(side="left", padx=8)
        self.folder_btn.pack(side="left", padx=8)
        self.out_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.out_var, foreground="#555").pack(side="left", padx=8)

        self.after(100, self.poll)
        if files:
            self.set_files(files)
            self.after(300, self.start)

    # ------------------------------------------------------------------ akcie
    def pick(self):
        files = filedialog.askopenfilenames(
            title="Vyberte naskenované vychystávacie listy",
            filetypes=[("PDF", "*.pdf"), ("Všetky súbory", "*.*")])
        if files:
            self.set_files(list(files))

    def set_files(self, files: list[str]):
        self.files = files
        names = ", ".join(os.path.basename(f) for f in files)
        self.files_var.set(f"{len(files)} súbor(y): {names}")
        self.run_btn.configure(state="normal")
        self.status_var.set("Kliknite na „2. Vytvoriť kompletačný list“.")

    def start(self):
        if self.busy or not self.files:
            return
        self.busy = True
        self.result = None
        for b in (self.pick_btn, self.run_btn, self.open_btn, self.print_btn, self.folder_btn,
                  self.settings_btn):
            b.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.out_var.set("")
        # kým sa nedočíta prvá strana, beží "neurčitý" pruh
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(15)
        self.status_var.set("Spúšťam čítanie skenov …")
        self.root.configure(cursor="watch")
        self.started_at = time.monotonic()
        self.animate()
        threading.Thread(target=self.work, args=(list(self.files),), daemon=True).start()

    def animate(self):
        """Otáča koliesko a ukazuje uplynulý čas, kým program pracuje."""
        if not self.busy:
            self.spinner.itemconfigure(self.spinner_arc, extent=0)
            self.root.configure(cursor="")
            return
        self.spinner_angle = (self.spinner_angle - 12) % 360
        self.spinner.itemconfigure(self.spinner_arc, start=self.spinner_angle, extent=270)
        self.time_var.set(f"{int(time.monotonic() - self.started_at)} s")
        self.after(40, self.animate)

    def work(self, files: list[str]):
        try:
            err = check_tesseract()
            if err:
                self.events.put(("error", err))
                return
            res = run(files, default_output(files[0]), settings=cfg.load(),
                      progress=lambda i, n, text: self.events.put(("progress", i, n, text)))
            self.events.put(("done", res))
        except Exception as e:  # noqa: BLE001 - chybu treba ukázať používateľovi
            traceback.print_exc()
            self.events.put(("error", f"{type(e).__name__}: {e}"))

    def poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    _, i, n, text = ev
                    if i > 0 and str(self.progress["mode"]) == "indeterminate":
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                    if str(self.progress["mode"]) == "determinate":
                        self.progress.configure(maximum=max(n, 1), value=i)
                    self.status_var.set(text)
                elif ev[0] == "done":
                    self.finish(ev[1])
                elif ev[0] == "error":
                    self.busy = False
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    for b in (self.pick_btn, self.run_btn, self.settings_btn):
                        b.configure(state="normal")
                    self.status_var.set("Chyba pri spracovaní.")
                    messagebox.showerror(APP_TITLE, f"Spracovanie zlyhalo:\n\n{ev[1]}")
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def finish(self, res: Result):
        self.busy = False
        self.result = res
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=1, value=1)
        self.time_var.set(f"{int(time.monotonic() - self.started_at)} s")
        for b in (self.pick_btn, self.run_btn, self.open_btn, self.print_btn, self.folder_btn,
                  self.settings_btn):
            b.configure(state="normal")

        self.show_lines()
        total = sum(l.mnozstvo for l in res.lines)

        msg = (f"Hotovo: {len(res.lists)} vychystávacích listov → {len(res.lines)} rôznych dosiek, "
               f"spolu {fmt(total)} ks.")
        if res.dropped:
            msg += f"  {len(res.dropped)} list(y) boli naskenované dvakrát – započítané raz."
        if res.warning_count:
            msg += f"  ⚠ {res.warning_count}× treba skontrolovať (žlté riadky)."
        self.status_var.set(msg)
        self.out_var.set(res.output)
        self.open_output("open")

    def show_lines(self):
        """Náhľad v okne - rovnaké poradie riadkov ako v PDF."""
        self.tree.delete(*self.tree.get_children())
        if not self.result:
            return
        lines = sort_lines(self.result.lines, cfg.load().sort)
        for l in lines:
            km = " / ".join(fmt(l.km[u]) for u in l.umiestnenia if u in l.km)
            rozpis = ", ".join(f"{fmt(a.mnozstvo)} ks {a.zakazka or a.doklad}" for a in l.allocations)
            name = ("⚠ " if l.warnings else "") + l.nazov
            self.tree.insert("", "end", tags=("warn",) if l.warnings else (), values=(
                ", ".join(l.umiestnenia), l.kod, name, f"{fmt(l.mnozstvo)} ks", km, rozpis))
        total = sum(l.mnozstvo for l in lines)
        self.tree.insert("", "end", tags=("total",),
                         values=("", "", "SPOLU", f"{fmt(total)} ks", "", ""))

    def open_settings(self):
        if self.busy:
            return
        SettingsDialog(self.root, on_save=self.settings_saved)

    def settings_saved(self):
        if not self.result:
            return
        try:
            rebuild(self.result, cfg.load())
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"PDF sa nepodarilo uložiť:\n{e}")
            return
        self.show_lines()
        self.out_var.set(self.result.output)
        self.status_var.set("Kompletačný list bol upravený podľa nových nastavení.")
        self.open_output("open")

    def open_output(self, action: str):
        if self.result:
            try:
                open_file(self.result.output, action)
            except OSError as e:  # napr. žiadny program na PDF / tlač
                messagebox.showerror(APP_TITLE, str(e))

    def open_folder(self):
        if self.result:
            open_file(os.path.dirname(os.path.abspath(self.result.output)))


class SettingsDialog(tk.Toplevel):
    """Poradie a výber stĺpcov, zoradenie, formát strany, presnosť, prehľad listov."""

    def __init__(self, parent: tk.Tk, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title("Nastavenia kompletačného listu")
        self.transient(parent)
        self.resizable(False, False)
        current = cfg.load()
        # viditeľné stĺpce v ich poradí, za nimi skryté
        self.order = current.columns + [c for c in cfg.COLUMNS if c not in current.columns]
        self.visible = set(current.columns)

        body = ttk.Frame(self, padding=14)
        body.grid(sticky="nsew")
        ttk.Label(body, text="Stĺpce v kompletačnom liste (zhora = zľava):",
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Dvojklik = zobraziť / skryť stĺpec", foreground="#555").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.listbox = tk.Listbox(body, height=len(self.order), width=34, activestyle="none",
                                  font=("Segoe UI", 11), exportselection=False)
        self.listbox.grid(row=2, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda e: self.toggle())

        btns = ttk.Frame(body)
        btns.grid(row=2, column=1, sticky="n", padx=(10, 0))
        for text, cmd in (("▲ Vyššie", lambda: self.move(-1)), ("▼ Nižšie", lambda: self.move(1)),
                          ("Zobraziť / skryť", self.toggle), ("Predvolené", self.reset)):
            ttk.Button(btns, text=text, command=cmd, width=16).pack(fill="x", pady=2)

        ttk.Label(body, text="Zoradenie riadkov:", font=("Segoe UI", 10, "bold")).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(14, 4))
        self.sort_keys = list(cfg.SORTS)
        self.sort_box = ttk.Combobox(body, state="readonly", width=44,
                                     values=[cfg.SORTS[k] for k in self.sort_keys])
        self.sort_box.current(self.sort_keys.index(current.sort))
        self.sort_box.grid(row=4, column=0, columnspan=2, sticky="w")

        ttk.Label(body, text="Formát strany:", font=("Segoe UI", 10, "bold")).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(14, 4))
        self.orient_keys = list(cfg.ORIENTATIONS)
        self.orient_box = ttk.Combobox(body, state="readonly", width=44,
                                       values=[cfg.ORIENTATIONS[k] for k in self.orient_keys])
        self.orient_box.current(self.orient_keys.index(current.orientation))
        self.orient_box.grid(row=6, column=0, columnspan=2, sticky="w")

        self.overview = tk.BooleanVar(value=current.lists_overview)
        ttk.Checkbutton(body, text="Na konci pridať prehľad vychystávacích listov",
                        variable=self.overview).grid(row=7, column=0, columnspan=2, sticky="w",
                                                     pady=(12, 0))
        self.thorough = tk.BooleanVar(value=current.thorough)
        ttk.Checkbutton(body, text="Presnejšie čítanie pri slabších skenoch (pomalšie)",
                        variable=self.thorough).grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Presnejšie čítanie sa prejaví až pri ďalšom spracovaní skenu.",
                  foreground="#555").grid(row=9, column=0, columnspan=2, sticky="w")

        bottom = ttk.Frame(body)
        bottom.grid(row=10, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(bottom, text="Zrušiť", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Uložiť", command=self.save, style="Big.TButton").pack(
            side="right", padx=8)

        self.refresh(0)
        # do stredu hlavného okna
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.focus_set()

    def refresh(self, select: int | None = None):
        self.listbox.delete(0, "end")
        for i, key in enumerate(self.order):
            mark = "☑" if key in self.visible else "☐"
            self.listbox.insert("end", f"  {mark}  {cfg.COLUMNS[key][1]}")
            if key not in self.visible:
                self.listbox.itemconfigure(i, foreground="#999")
        if select is not None:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(select)
            self.listbox.see(select)

    def selected(self) -> int | None:
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def move(self, step: int):
        i = self.selected()
        if i is None or not 0 <= i + step < len(self.order):
            return
        self.order[i], self.order[i + step] = self.order[i + step], self.order[i]
        self.refresh(i + step)

    def toggle(self):
        i = self.selected()
        if i is None:
            return
        key = self.order[i]
        if key in self.visible:
            if len(self.visible) == 1:
                messagebox.showinfo(APP_TITLE, "Aspoň jeden stĺpec musí ostať zobrazený.", parent=self)
                return
            self.visible.discard(key)
        else:
            self.visible.add(key)
        self.refresh(i)

    def reset(self):
        default = cfg.Settings()
        self.order = list(default.columns)
        self.visible = set(default.columns)
        self.sort_box.current(self.sort_keys.index(default.sort))
        self.orient_box.current(self.orient_keys.index(default.orientation))
        self.overview.set(default.lists_overview)
        self.thorough.set(default.thorough)
        self.refresh(0)

    def save(self):
        new = cfg.Settings(columns=[c for c in self.order if c in self.visible],
                           sort=self.sort_keys[self.sort_box.current()],
                           lists_overview=self.overview.get(),
                           orientation=self.orient_keys[self.orient_box.current()],
                           thorough=self.thorough.get())
        try:
            cfg.save(new)
        except OSError as e:
            messagebox.showerror(APP_TITLE, f"Nastavenia sa nepodarilo uložiť:\n{e}", parent=self)
            return
        self.destroy()
        self.on_save()


def main(argv: list[str] | None = None) -> None:
    files = [f for f in (sys.argv[1:] if argv is None else argv) if f.lower().endswith(".pdf")]
    if sys.platform == "win32":
        try:  # ostré písmo na monitoroch so zväčšením
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    icon = os.path.join(base, "assets", "icon.ico")
    if sys.platform == "win32" and os.path.exists(icon):
        root.iconbitmap(icon)
    App(root, files)
    root.mainloop()


if __name__ == "__main__":
    main()
