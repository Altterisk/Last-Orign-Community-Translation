"""
GUI editor for corrections/corrections.json
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

CORRECTIONS_FILE = BASE_DIR / "corrections" / "corrections.json"

DARK_BG     = "#1e1e1e"
DARK_PANEL  = "#252526"
DARK_WIDGET = "#3c3c3c"
DARK_FG     = "#d4d4d4"
DARK_DIM    = "#858585"
DARK_SEL    = "#094771"
DARK_SLFG   = "#ffffff"
DARK_BORDER = "#454545"


def _load():
    if CORRECTIONS_FILE.exists():
        with open(CORRECTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(data):
    with open(CORRECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def _apply_dark_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=DARK_BG, foreground=DARK_FG,
                    fieldbackground=DARK_WIDGET, bordercolor=DARK_BORDER,
                    darkcolor=DARK_PANEL, lightcolor=DARK_PANEL,
                    troughcolor=DARK_PANEL, insertcolor=DARK_FG,
                    selectbackground=DARK_SEL, selectforeground=DARK_SLFG)
    style.configure("TFrame",  background=DARK_BG)
    style.configure("TLabel",  background=DARK_BG, foreground=DARK_FG)
    style.configure("TButton", background=DARK_WIDGET, foreground=DARK_FG,
                    bordercolor=DARK_BORDER, padding=4)
    style.map("TButton",
              background=[("active", "#505357"), ("pressed", "#505357")],
              relief=[("pressed", "flat"), ("!pressed", "flat")])
    style.configure("TEntry", fieldbackground=DARK_WIDGET, foreground=DARK_FG,
                    insertcolor=DARK_FG, bordercolor=DARK_BORDER)
    style.configure("TScrollbar", background=DARK_WIDGET, troughcolor=DARK_PANEL,
                    arrowcolor=DARK_FG, bordercolor=DARK_BORDER)
    style.configure("TPanedwindow", background=DARK_BG)
    root.configure(bg=DARK_BG)


# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Corrections Editor")
        self.geometry("960x580")
        self.minsize(720, 460)

        self.data: list[dict] = _load()
        self.cur: int | None = None
        self._loading = False
        self._dirty = False

        _apply_dark_style(self)
        self._build()
        self._repopulate_list()
        if self.data:
            self._select_index(0)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI

    def _build(self):
        # ── top split ──────────────────────────────────────────────────────
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        # left: entry list
        left = ttk.Frame(pane, width=230)
        left.pack_propagate(False)
        pane.add(left, weight=1)

        ttk.Label(left, text="Entries", font=("Segoe UI", 9, "bold")).pack(
            anchor=tk.W, padx=6, pady=(4, 2)
        )

        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True, padx=6)
        sb = ttk.Scrollbar(lf)
        self.entry_list = tk.Listbox(
            lf, yscrollcommand=sb.set, selectmode=tk.SINGLE,
            activestyle="none", font=("Segoe UI", 9), relief=tk.FLAT,
            bg=DARK_PANEL, fg=DARK_FG, selectbackground=DARK_SEL,
            selectforeground=DARK_SLFG, bd=0,
        )
        sb.config(command=self.entry_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.entry_list.bind("<<ListboxSelect>>", self._on_list_select)

        bf = ttk.Frame(left)
        bf.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(bf, text="+ New", command=self._new_entry).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3)
        )
        ttk.Button(bf, text="Delete", command=self._delete_entry).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # right: form
        right = ttk.Frame(pane)
        pane.add(right, weight=3)

        form = ttk.Frame(right)
        form.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)

        # Original
        ttk.Label(form, text="Original (Korean):", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W
        )
        self.var_original = tk.StringVar()
        self.var_original.trace_add("write", self._field_changed)
        self.ent_original = ttk.Entry(form, textvariable=self.var_original, font=("Segoe UI", 10))
        self.ent_original.grid(row=1, column=0, sticky=tk.EW, pady=(2, 10))

        # Correct translation
        ttk.Label(form, text="Correct Translation:", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky=tk.W
        )
        self.var_correct = tk.StringVar()
        self.var_correct.trace_add("write", self._field_changed)
        ttk.Entry(form, textvariable=self.var_correct, font=("Segoe UI", 10)).grid(
            row=3, column=0, sticky=tk.EW, pady=(2, 10)
        )

        # Mistranslations list
        ttk.Label(form, text="Mistranslations:", font=("Segoe UI", 9, "bold")).grid(
            row=4, column=0, sticky=tk.W
        )
        mf = ttk.Frame(form)
        mf.grid(row=5, column=0, sticky=tk.NSEW, pady=(2, 4))
        msb = ttk.Scrollbar(mf)
        self.mis_list = tk.Listbox(
            mf, yscrollcommand=msb.set, selectmode=tk.SINGLE,
            activestyle="none", font=("Segoe UI", 9), relief=tk.FLAT,
            bg=DARK_PANEL, fg=DARK_FG, selectbackground=DARK_SEL,
            selectforeground=DARK_SLFG, bd=0,
        )
        msb.config(command=self.mis_list.yview)
        msb.pack(side=tk.RIGHT, fill=tk.Y)
        self.mis_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Add / remove row
        ar = ttk.Frame(form)
        ar.grid(row=6, column=0, sticky=tk.EW, pady=(0, 4))
        self.var_new_mis = tk.StringVar()
        self.ent_new_mis = ttk.Entry(ar, textvariable=self.var_new_mis, font=("Segoe UI", 10))
        self.ent_new_mis.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ent_new_mis.bind("<Return>", lambda _: self._add_mis())
        ttk.Button(ar, text="Add", command=self._add_mis, width=8).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(ar, text="Remove Selected", command=self._remove_mis).pack(side=tk.LEFT)

        # ── bottom bar ────────────────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=6)
        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.var_status, foreground=DARK_DIM).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Save", command=self._save, width=10).pack(side=tk.RIGHT, padx=4)

    # ---------------------------------------------------------------- list

    def _entry_label(self, entry: dict) -> str:
        ko = entry.get("original", "")[:28]
        en = entry.get("correctTranslation", "")[:22]
        n  = len(entry.get("mistranslation", []))
        return f"{ko}  →  {en}  ({n})"

    def _repopulate_list(self):
        self.entry_list.delete(0, tk.END)
        for e in self.data:
            self.entry_list.insert(tk.END, self._entry_label(e))

    def _update_list_row(self, idx: int):
        self.entry_list.delete(idx)
        self.entry_list.insert(idx, self._entry_label(self.data[idx]))
        self.entry_list.selection_set(idx)

    # ---------------------------------------------------------------- form

    def _load_form(self, idx: int):
        e = self.data[idx]
        self._loading = True
        self.var_original.set(e.get("original", ""))
        self.var_correct.set(e.get("correctTranslation", ""))
        self.mis_list.delete(0, tk.END)
        for m in e.get("mistranslation", []):
            self.mis_list.insert(tk.END, m)
        self._loading = False

    def _flush_form(self):
        if self.cur is None:
            return
        e = self.data[self.cur]
        e["original"]           = self.var_original.get().strip()
        e["correctTranslation"] = self.var_correct.get().strip()
        e["mistranslation"] = list(self.mis_list.get(0, tk.END))
        self._update_list_row(self.cur)

    def _clear_form(self):
        self._loading = True
        self.var_original.set("")
        self.var_correct.set("")
        self.mis_list.delete(0, tk.END)
        self._loading = False

    # --------------------------------------------------------------- events

    def _select_index(self, idx: int):
        if self.cur is not None:
            self._flush_form()
        self.cur = idx
        self._load_form(idx)
        self.entry_list.selection_clear(0, tk.END)
        self.entry_list.selection_set(idx)
        self.entry_list.see(idx)

    def _on_list_select(self, _event):
        sel = self.entry_list.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx == self.cur:
            return
        self._select_index(idx)

    def _field_changed(self, *_):
        if not self._loading:
            self._mark_dirty()

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.var_status.set("Unsaved changes")

    # -------------------------------------------------------------- actions

    def _new_entry(self):
        if self.cur is not None:
            self._flush_form()
        new = {"original": "", "correctTranslation": "", "mistranslation": []}
        self.data.append(new)
        new_idx = len(self.data) - 1
        self.entry_list.insert(tk.END, self._entry_label(new))
        self.cur = new_idx
        self._load_form(new_idx)
        self.entry_list.selection_clear(0, tk.END)
        self.entry_list.selection_set(new_idx)
        self.entry_list.see(new_idx)
        self.ent_original.focus_set()
        self._mark_dirty()

    def _delete_entry(self):
        if self.cur is None:
            return
        label = self.data[self.cur].get("original") or "(empty)"
        if not messagebox.askyesno("Delete", f'Delete entry for "{label}"?', parent=self):
            return
        self.data.pop(self.cur)
        self.entry_list.delete(self.cur)
        self.cur = None
        self._clear_form()
        if self.data:
            new_idx = min(len(self.data) - 1, self.cur or 0)
            self._select_index(new_idx)
        self._mark_dirty()

    def _add_mis(self):
        text = self.var_new_mis.get().strip()
        if not text or self.cur is None:
            return
        existing = list(self.mis_list.get(0, tk.END))
        if text not in existing:
            self.mis_list.insert(tk.END, text)
            self.data[self.cur]["mistranslation"] = list(self.mis_list.get(0, tk.END))
            self._update_list_row(self.cur)
            self._mark_dirty()
        self.var_new_mis.set("")
        self.ent_new_mis.focus_set()

    def _remove_mis(self):
        sel = self.mis_list.curselection()
        if not sel or self.cur is None:
            return
        self.mis_list.delete(sel[0])
        self.data[self.cur]["mistranslation"] = list(self.mis_list.get(0, tk.END))
        self._update_list_row(self.cur)
        self._mark_dirty()

    def _save(self):
        if self.cur is not None:
            self._flush_form()
        try:
            _save(self.data)
            self._dirty = False
            self.var_status.set(f"Saved  —  {len(self.data)} entr{'y' if len(self.data) == 1 else 'ies'}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)

    def _on_close(self):
        if self._dirty:
            ans = messagebox.askyesnocancel(
                "Unsaved Changes", "Save before closing?", parent=self
            )
            if ans is None:
                return
            if ans:
                self._save()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
