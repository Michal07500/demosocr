"""Okno aplikácie: vybrať skeny -> vytvoriť kompletačný list -> otvoriť / vytlačiť."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from .ocr import check_tesseract, fmt
from .pipeline import Result, default_output, run

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
        ttk.Label(top, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, columnspan=3,
                                                                    sticky="w", pady=(0, 8))
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
        self.status_var = tk.StringVar(value="Vyberte PDF so skenom vychystávacích listov "
                                             "(môže ich byť aj viac naraz).")
        ttk.Label(self, textvariable=self.status_var).grid(row=2, column=0, sticky="w")

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
        err = check_tesseract()
        if err:
            messagebox.showerror(APP_TITLE, err)
            return
        self.busy = True
        self.result = None
        for b in (self.pick_btn, self.run_btn, self.open_btn, self.print_btn, self.folder_btn):
            b.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.out_var.set("")
        self.progress.configure(value=0, maximum=1)
        self.status_var.set("Načítavam PDF …")
        threading.Thread(target=self.work, args=(list(self.files),), daemon=True).start()

    def work(self, files: list[str]):
        try:
            res = run(files, default_output(files[0]),
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
                    self.progress.configure(maximum=max(n, 1), value=i)
                    self.status_var.set(text)
                elif ev[0] == "done":
                    self.finish(ev[1])
                elif ev[0] == "error":
                    self.busy = False
                    self.pick_btn.configure(state="normal")
                    self.run_btn.configure(state="normal")
                    self.status_var.set("Chyba pri spracovaní.")
                    messagebox.showerror(APP_TITLE, f"Spracovanie zlyhalo:\n\n{ev[1]}")
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def finish(self, res: Result):
        self.busy = False
        self.result = res
        for b in (self.pick_btn, self.run_btn, self.open_btn, self.print_btn, self.folder_btn):
            b.configure(state="normal")
        self.progress.configure(value=self.progress["maximum"])

        for l in res.lines:
            km = " / ".join(fmt(l.km[u]) for u in l.umiestnenia if u in l.km)
            rozpis = ", ".join(f"{fmt(a.mnozstvo)} ks {a.zakazka or a.doklad}" for a in l.allocations)
            name = ("⚠ " if l.warnings else "") + l.nazov
            self.tree.insert("", "end", tags=("warn",) if l.warnings else (), values=(
                ", ".join(l.umiestnenia), l.kod, name, f"{fmt(l.mnozstvo)} ks", km, rozpis))
        total = sum(l.mnozstvo for l in res.lines)
        self.tree.insert("", "end", tags=("total",),
                         values=("", "", "SPOLU", f"{fmt(total)} ks", "", ""))

        msg = (f"Hotovo: {len(res.lists)} vychystávacích listov → {len(res.lines)} rôznych dosiek, "
               f"spolu {fmt(total)} ks.")
        if res.dropped:
            msg += f"  {len(res.dropped)} list(y) boli naskenované dvakrát – započítané raz."
        if res.warning_count:
            msg += f"  ⚠ {res.warning_count}× treba skontrolovať (žlté riadky)."
        self.status_var.set(msg)
        self.out_var.set(res.output)
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
