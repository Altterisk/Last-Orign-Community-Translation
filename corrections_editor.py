"""
GUI editor for corrections/corrections.json
"""

import copy
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
DARK_SEARCH = "#2a2a3a"


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
        self.geometry("960x600")
        self.minsize(720, 460)

        self.data: list[dict] = _load()
        self.cur: int | None = None      # current DATA index
        self._loading = False
        self._dirty = False

        # Search
        self._filtered: list[int] = list(range(len(self.data)))  # data indices shown
        self._search_job: str | None = None   # pending after() id for debounce

        # Undo history: list of (deep copy of data, cur data-index)
        self._history: list[tuple[list, int | None]] = []

        _apply_dark_style(self)
        self._build()
        self._apply_filter()
        if self.data:
            self._select_index(0)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-z>", lambda _: self._undo())
        self.bind("<Control-Z>", lambda _: self._undo())
        self.bind("<Control-s>", lambda _: self._save())

    # ------------------------------------------------------------------ UI

    def _build(self):
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        # ── left: search + entry list ──────────────────────────────────────
        left = ttk.Frame(pane, width=260)
        left.pack_propagate(False)
        pane.add(left, weight=1)

        ttk.Label(left, text="Entries", font=("Segoe UI", 9, "bold")).pack(
            anchor=tk.W, padx=6, pady=(4, 2)
        )

        # Search bar
        sf = ttk.Frame(left)
        sf.pack(fill=tk.X, padx=6, pady=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._schedule_filter())
        search_entry = ttk.Entry(sf, textvariable=self._search_var,
                                 font=("Segoe UI", 9))
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sf, text="✕", width=2,
                   command=lambda: self._search_var.set("")).pack(side=tk.LEFT, padx=(2, 0))
        # placeholder behaviour via focus events
        self._search_placeholder = "Search…"
        search_entry.insert(0, self._search_placeholder)
        search_entry.config(foreground=DARK_DIM)
        search_entry.bind("<FocusIn>",  self._search_focus_in)
        search_entry.bind("<FocusOut>", self._search_focus_out)
        self._search_entry = search_entry

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

        # ── right: form ────────────────────────────────────────────────────
        right = ttk.Frame(pane)
        pane.add(right, weight=3)

        form = ttk.Frame(right)
        form.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)

        ttk.Label(form, text="Original (Korean):", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky=tk.W
        )
        self.var_original = tk.StringVar()
        self.var_original.trace_add("write", self._field_changed)
        self.ent_original = ttk.Entry(form, textvariable=self.var_original,
                                      font=("Segoe UI", 10))
        self.ent_original.grid(row=1, column=0, sticky=tk.EW, pady=(2, 10))

        ttk.Label(form, text="Correct Translation:", font=("Segoe UI", 9, "bold")).grid(
            row=2, column=0, sticky=tk.W
        )
        self.var_correct = tk.StringVar()
        self.var_correct.trace_add("write", self._field_changed)
        ttk.Entry(form, textvariable=self.var_correct,
                  font=("Segoe UI", 10)).grid(row=3, column=0, sticky=tk.EW, pady=(2, 10))

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

        ar = ttk.Frame(form)
        ar.grid(row=6, column=0, sticky=tk.EW, pady=(0, 4))
        self.var_new_mis = tk.StringVar()
        self.ent_new_mis = ttk.Entry(ar, textvariable=self.var_new_mis,
                                     font=("Segoe UI", 10))
        self.ent_new_mis.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ent_new_mis.bind("<Return>", lambda _: self._add_mis())
        ttk.Button(ar, text="Add", command=self._add_mis, width=8).pack(
            side=tk.LEFT, padx=(0, 6))
        ttk.Button(ar, text="Remove Selected",
                   command=self._remove_mis).pack(side=tk.LEFT)

        # ── bottom bar ─────────────────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=6)
        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.var_status,
                  foreground=DARK_DIM).pack(side=tk.LEFT, padx=4)
        self._undo_btn = ttk.Button(bar, text="Undo (Ctrl+Z)",
                                    command=self._undo, width=14)
        self._undo_btn.pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(bar, text="Save", command=self._save,
                   width=10).pack(side=tk.RIGHT, padx=4)

    # ---------------------------------------------------------------- search

    def _search_focus_in(self, _e):
        if self._search_entry.get() == self._search_placeholder:
            self._search_entry.delete(0, tk.END)
            self._search_entry.config(foreground=DARK_FG)

    def _search_focus_out(self, _e):
        if not self._search_entry.get():
            self._search_entry.insert(0, self._search_placeholder)
            self._search_entry.config(foreground=DARK_DIM)

    def _search_text(self) -> str:
        t = self._search_var.get()
        return "" if t == self._search_placeholder else t.lower()

    def _matches(self, entry: dict, query: str) -> bool:
        if not query:
            return True
        haystack = " ".join([
            entry.get("original", ""),
            entry.get("correctTranslation", ""),
            " ".join(entry.get("mistranslation", [])),
        ]).lower()
        return query in haystack

    def _schedule_filter(self):
        if not hasattr(self, "entry_list"):
            return
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        delay = 300 if self._search_text() else 0
        self._search_job = self.after(delay, self._apply_filter)

    def _apply_filter(self):
        """Rebuild the listbox to show only entries matching the current search."""
        self._search_job = None
        if not hasattr(self, "entry_list"):
            return
        query = self._search_text()
        # Flush current selection before repopulating
        if self.cur is not None:
            self._flush_form()

        self._filtered = [i for i, e in enumerate(self.data) if self._matches(e, query)]

        self.entry_list.delete(0, tk.END)
        for i in self._filtered:
            self.entry_list.insert(tk.END, self._entry_label(self.data[i]))

        # Re-select cur if still visible
        if self.cur is not None and self.cur in self._filtered:
            lb_idx = self._filtered.index(self.cur)
            self.entry_list.selection_set(lb_idx)
            self.entry_list.see(lb_idx)

        count = len(self._filtered)
        total = len(self.data)
        self.var_status.set(
            f"{count} of {total} entries" if query else f"{total} entr{'y' if total == 1 else 'ies'}"
        )

    # ------------------------------------------------------------------ list

    def _entry_label(self, entry: dict) -> str:
        ko = entry.get("original", "")[:28]
        en = entry.get("correctTranslation", "")[:22]
        n  = len(entry.get("mistranslation", []))
        return f"{ko}  →  {en}  ({n})"

    def _update_list_row(self, data_idx: int):
        if data_idx in self._filtered:
            lb_idx = self._filtered.index(data_idx)
            self.entry_list.delete(lb_idx)
            self.entry_list.insert(lb_idx, self._entry_label(self.data[data_idx]))
            self.entry_list.selection_set(lb_idx)

    # ------------------------------------------------------------------ form

    def _load_form(self, data_idx: int):
        e = self.data[data_idx]
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
        e["mistranslation"]     = list(self.mis_list.get(0, tk.END))
        self._update_list_row(self.cur)

    def _clear_form(self):
        self._loading = True
        self.var_original.set("")
        self.var_correct.set("")
        self.mis_list.delete(0, tk.END)
        self._loading = False

    # --------------------------------------------------------------- events

    def _select_index(self, data_idx: int):
        if self.cur is not None and self.cur != data_idx:
            self._flush_form()
        self.cur = data_idx
        self._load_form(data_idx)
        if data_idx in self._filtered:
            lb_idx = self._filtered.index(data_idx)
            self.entry_list.selection_clear(0, tk.END)
            self.entry_list.selection_set(lb_idx)
            self.entry_list.see(lb_idx)

    def _on_list_select(self, _event):
        sel = self.entry_list.curselection()
        if not sel:
            return
        data_idx = self._filtered[sel[0]]
        if data_idx == self.cur:
            return
        self._select_index(data_idx)

    def _field_changed(self, *_):
        if not self._loading:
            self._mark_dirty()

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.var_status.set("Unsaved changes")

    # --------------------------------------------------------------- undo

    def _push_history(self):
        self._history.append((copy.deepcopy(self.data), self.cur))
        # Cap history at 50 states
        if len(self._history) > 50:
            self._history.pop(0)

    def _undo(self):
        if not self._history:
            self.var_status.set("Nothing to undo")
            return
        if self.cur is not None:
            self._flush_form()
        self.data, prev_cur = self._history.pop()
        self._apply_filter()
        if prev_cur is not None and prev_cur < len(self.data):
            self._select_index(prev_cur)
        elif self.data:
            self._select_index(0)
        else:
            self.cur = None
            self._clear_form()
        self._mark_dirty()
        self.var_status.set(f"Undo — {len(self._history)} step(s) remaining")

    # -------------------------------------------------------------- actions

    def _new_entry(self):
        self._push_history()
        if self.cur is not None:
            self._flush_form()
        new = {"original": "", "correctTranslation": "", "mistranslation": []}
        self.data.append(new)
        new_idx = len(self.data) - 1
        # Refilter so the new entry appears if search is active
        self._apply_filter()
        self._select_index(new_idx)
        self.ent_original.focus_set()
        self._mark_dirty()

    def _delete_entry(self):
        if self.cur is None:
            return
        label = self.data[self.cur].get("original") or "(empty)"
        if not messagebox.askyesno("Delete", f'Delete entry for "{label}"?', parent=self):
            return
        self._push_history()
        self.data.pop(self.cur)
        old_cur = self.cur
        self.cur = None
        self._apply_filter()
        if self.data:
            new_idx = min(len(self.data) - 1, old_cur)
            # Pick next visible entry
            if self._filtered:
                lb_target = min(range(len(self._filtered)),
                                key=lambda i: abs(self._filtered[i] - new_idx))
                self._select_index(self._filtered[lb_target])
        else:
            self._clear_form()
        self._mark_dirty()

    def _add_mis(self):
        text = self.var_new_mis.get().strip()
        if not text or self.cur is None:
            return
        existing = list(self.mis_list.get(0, tk.END))
        if text not in existing:
            self._push_history()
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
        self._push_history()
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
            n = len(self.data)
            self.var_status.set(f"Saved  —  {n} entr{'y' if n == 1 else 'ies'}")
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
