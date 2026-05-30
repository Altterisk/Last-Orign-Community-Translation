"""
GUI editor for for_review/*.json translation files.
"""

import asyncio
import json
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

try:
    from local_google_translate import GoogleTranslateV2
    _HAS_MTL = True
except ImportError:
    _HAS_MTL = False

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

REVIEW_DIR  = BASE_DIR / "for_review"
NO_TRANS_RE = re.compile(r"^No_Trans|^No_translation", re.IGNORECASE)

COLOR_MISSING = "#e74c3c"

DARK_BG     = "#1e1e1e"
DARK_PANEL  = "#252526"
DARK_WIDGET = "#3c3c3c"
DARK_FG     = "#d4d4d4"
DARK_DIM    = "#858585"
DARK_SEL    = "#094771"
DARK_SLFG   = "#ffffff"
DARK_BORDER = "#454545"
DARK_RO     = "#252526"


def _load(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _is_missing(english: str) -> bool:
    return not english.strip() or bool(NO_TRANS_RE.match(english))


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
    style.configure("TCombobox", fieldbackground=DARK_WIDGET, foreground=DARK_FG,
                    arrowcolor=DARK_FG, bordercolor=DARK_BORDER)
    style.map("TCombobox",
              fieldbackground=[("readonly", DARK_WIDGET)],
              selectbackground=[("readonly", DARK_SEL)],
              selectforeground=[("readonly", DARK_SLFG)])
    style.configure("TScrollbar", background=DARK_WIDGET, troughcolor=DARK_PANEL,
                    arrowcolor=DARK_FG, bordercolor=DARK_BORDER)
    style.configure("TPanedwindow", background=DARK_BG)
    root.configure(bg=DARK_BG)


# ---------------------------------------------------------------------------


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Review Editor")
        self.geometry("1100x640")
        self.minsize(800, 500)

        self._fill_path = REVIEW_DIR / "ko_kr_fill.json"
        self._show_fill = False
        self.files: list[Path] = [
            f for f in sorted(REVIEW_DIR.glob("*.json"))
            if f.name != self._fill_path.name
        ]
        self._search_job: str | None = None

        self.file_cache: dict[Path, dict] = {}

        self.codes:    list[str]              = []
        self.filtered: list[tuple[Path, str]] = []

        self.cur_code: str  | None = None
        self.cur_file: Path | None = None
        self._dirty   = False
        self._loading = False

        _apply_dark_style(self)
        self._build()

        if self.files:
            self.file_var.set(self.files[0].name)
            self._load_file(self.files[0])

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI

    def _build(self):
        # ── file bar ───────────────────────────────────────────────────────
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=(6, 0))

        ttk.Label(top, text="File:").pack(side=tk.LEFT, padx=(0, 4))
        self.file_var = tk.StringVar()
        self.file_cb = ttk.Combobox(
            top, textvariable=self.file_var,
            values=[f.name for f in self.files],
            state="readonly", width=32,
        )
        self.file_cb.pack(side=tk.LEFT)
        self.file_cb.bind("<<ComboboxSelected>>", self._on_file_select)

        ttk.Button(top, text="◀", width=2, command=lambda: self._step_file(-1)).pack(side=tk.LEFT, padx=(6, 1))
        ttk.Button(top, text="▶", width=2, command=lambda: self._step_file(1)).pack(side=tk.LEFT, padx=(1, 0))

        self.btn_fill = ttk.Button(top, text="Fill ▼", command=self._toggle_fill)
        self.btn_fill.pack(side=tk.LEFT, padx=(10, 0))

        self.lbl_info = ttk.Label(top, text="", foreground=DARK_DIM)
        self.lbl_info.pack(side=tk.LEFT, padx=10)

        # ── main split ─────────────────────────────────────────────────────
        pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # left: search + list + nav
        left = ttk.Frame(pane, width=310)
        left.pack_propagate(False)
        pane.add(left, weight=1)

        sr = ttk.Frame(left)
        sr.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(sr, text="Search:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_search())
        ttk.Entry(sr, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sr, text="×", width=2,
                   command=lambda: self.search_var.set("")).pack(side=tk.LEFT, padx=(2, 0))

        lf = ttk.Frame(left)
        lf.pack(fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(lf)
        self.entry_list = tk.Listbox(
            lf, yscrollcommand=sb.set, selectmode=tk.SINGLE,
            activestyle="none", font=("Consolas", 9), relief=tk.FLAT,
            bg=DARK_PANEL, fg=DARK_FG, selectbackground=DARK_SEL,
            selectforeground=DARK_SLFG, bd=0,
        )
        sb.config(command=self.entry_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.entry_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.entry_list.bind("<<ListboxSelect>>", self._on_list_select)

        nr = ttk.Frame(left)
        nr.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(nr, text="◀ Prev missing", command=lambda: self._jump_missing(-1)).pack(side=tk.LEFT)
        ttk.Button(nr, text="Next missing ▶", command=lambda: self._jump_missing(+1)).pack(side=tk.LEFT, padx=(4, 0))

        # right: edit form
        right = ttk.Frame(pane)
        pane.add(right, weight=2)

        form = ttk.Frame(right)
        form.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(3, weight=1)
        form.rowconfigure(5, weight=0)
        form.rowconfigure(7, weight=2)

        # Code row
        code_hdr = ttk.Frame(form)
        code_hdr.grid(row=0, column=0, sticky=tk.EW)
        ttk.Label(code_hdr, text="Code:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(code_hdr, text="Copy", width=6,
                   command=self._copy_code).pack(side=tk.RIGHT)

        self.lbl_code = ttk.Label(form, text="", font=("Consolas", 10))
        self.lbl_code.grid(row=1, column=0, sticky=tk.W, pady=(0, 8))

        # Korean row
        ko_hdr = ttk.Frame(form)
        ko_hdr.grid(row=2, column=0, sticky=tk.EW)
        ttk.Label(ko_hdr, text="Korean (reference):", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(ko_hdr, text="Copy", width=6,
                   command=self._copy_korean).pack(side=tk.RIGHT)

        self.txt_korean = tk.Text(
            form, font=("Segoe UI", 10), height=4, wrap=tk.WORD,
            relief=tk.FLAT, state=tk.DISABLED,
            bg=DARK_RO, fg=DARK_FG, insertbackground=DARK_FG,
            selectbackground=DARK_SEL, selectforeground=DARK_SLFG, bd=0,
        )
        self.txt_korean.grid(row=3, column=0, sticky=tk.NSEW, pady=(2, 8))

        # MTL row
        mtl_hdr = ttk.Frame(form)
        mtl_hdr.grid(row=4, column=0, sticky=tk.EW)
        ttk.Label(mtl_hdr, text="Machine Translation:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        self.btn_apply_mtl = ttk.Button(mtl_hdr, text="Apply", width=6,
                                        command=self._apply_mtl)
        self.btn_apply_mtl.pack(side=tk.RIGHT, padx=(4, 0))
        self.btn_translate = ttk.Button(mtl_hdr, text="Translate", width=9,
                                        command=self._run_translation,
                                        state=tk.NORMAL if _HAS_MTL else tk.DISABLED)
        self.btn_translate.pack(side=tk.RIGHT)

        self.txt_mtl = tk.Text(
            form, font=("Segoe UI", 10), height=3, wrap=tk.WORD,
            relief=tk.FLAT, state=tk.DISABLED,
            bg=DARK_RO, fg=DARK_FG, insertbackground=DARK_FG,
            selectbackground=DARK_SEL, selectforeground=DARK_SLFG, bd=0,
        )
        self.txt_mtl.grid(row=5, column=0, sticky=tk.EW, pady=(2, 8))

        # English row
        en_hdr = ttk.Frame(form)
        en_hdr.grid(row=6, column=0, sticky=tk.EW)
        ttk.Label(en_hdr, text="English:", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(en_hdr, text="Undo", width=6,
                   command=self._undo).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(en_hdr, text="↓ Below", width=8,
                   command=self._copy_from_below).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(en_hdr, text="↑ Above", width=8,
                   command=self._copy_from_above).pack(side=tk.RIGHT)

        self.txt_english = tk.Text(
            form, font=("Segoe UI", 10), height=5, wrap=tk.WORD,
            relief=tk.FLAT, undo=True,
            bg=DARK_WIDGET, fg=DARK_FG, insertbackground=DARK_FG,
            selectbackground=DARK_SEL, selectforeground=DARK_SLFG, bd=0,
        )
        self.txt_english.grid(row=7, column=0, sticky=tk.NSEW, pady=(2, 0))
        self.txt_english.bind("<KeyRelease>", self._on_english_key)

        # ── bottom bar ─────────────────────────────────────────────────────
        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=6, pady=(0, 6))
        self.var_status = tk.StringVar(value="Ready")
        ttk.Label(bar, textvariable=self.var_status, foreground=DARK_DIM).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Save", command=self._save, width=10).pack(side=tk.RIGHT, padx=4)

    # ---------------------------------------------------------------- file

    def _get_data(self, path: Path) -> dict:
        if path not in self.file_cache:
            self.file_cache[path] = _load(path)
        return self.file_cache[path]

    def _ensure_all_loaded(self) -> None:
        for path in self.files:
            if path not in self.file_cache:
                try:
                    self.file_cache[path] = _load(path)
                except Exception:
                    pass

    def _load_file(self, path: Path):
        if self._dirty and not self._confirm_discard():
            self.file_var.set(self.cur_file.name if self.cur_file else "")
            return
        self.cur_file = path
        data = self._get_data(path)
        self.codes = list(data.keys())
        self.cur_code = None
        self._dirty = False
        self.search_var.set("")
        self._apply_filter()
        missing = sum(1 for c in self.codes if _is_missing(data[c].get("english", "")))
        self.lbl_info.config(text=f"{len(self.codes)} entries  •  {missing} missing")
        self.var_status.set("Ready")
        self._clear_form()

    def _on_file_select(self, _event):
        self._load_file(REVIEW_DIR / self.file_var.get())

    def _toggle_fill(self):
        self._show_fill = not self._show_fill
        self.btn_fill.config(text="Fill ▲" if self._show_fill else "Fill ▼")
        all_files = sorted(REVIEW_DIR.glob("*.json"))
        if self._show_fill:
            self.files = all_files
        else:
            self.files = [f for f in all_files if f.name != self._fill_path.name]
        self.file_cb.config(values=[f.name for f in self.files])
        if not self._show_fill and self.cur_file == self._fill_path:
            if self.files:
                self.file_var.set(self.files[0].name)
                self._load_file(self.files[0])

    def _step_file(self, direction: int):
        if not self.files:
            return
        names = [f.name for f in self.files]
        cur = self.file_var.get()
        idx = names.index(cur) if cur in names else -1
        new_idx = (idx + direction) % len(self.files)
        self.file_var.set(names[new_idx])
        self._load_file(self.files[new_idx])

    # ---------------------------------------------------------------- list

    def _is_global_search(self) -> bool:
        return bool(self.search_var.get())

    def _schedule_search(self):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        delay = 400 if self.search_var.get() else 0
        self._search_job = self.after(delay, self._run_search)

    def _run_search(self):
        self._search_job = None
        self._apply_filter()

    def _apply_filter(self):
        q = self.search_var.get().lower()
        self.entry_list.delete(0, tk.END)

        if q:
            self._ensure_all_loaded()
            self.filtered = []
            for path in self.files:
                data = self.file_cache.get(path, {})
                for code, entry in data.items():
                    if (q in code.lower()
                            or q in entry.get("english", "").lower()
                            or q in entry.get("korean",  "").lower()):
                        self.filtered.append((path, code))
            for path, code in self.filtered:
                entry = self.file_cache[path][code]
                eng   = entry.get("english", "")
                label = f"[{path.name}]  {code}  {eng[:38]}"
                self.entry_list.insert(tk.END, label)
                if _is_missing(eng):
                    self.entry_list.itemconfigure(tk.END, foreground=COLOR_MISSING)
        else:
            if not self.cur_file:
                return
            data = self._get_data(self.cur_file)
            self.filtered = [(self.cur_file, c) for c in self.codes]
            for _, code in self.filtered:
                eng = data[code].get("english", "")
                self.entry_list.insert(tk.END, f"{code}  {eng[:50]}")
                if _is_missing(eng):
                    self.entry_list.itemconfigure(tk.END, foreground=COLOR_MISSING)

    def _refresh_row(self, path: Path, code: str):
        key = (path, code)
        if key not in self.filtered:
            return
        idx  = self.filtered.index(key)
        data = self._get_data(path)
        eng  = data[code].get("english", "")
        self.entry_list.delete(idx)
        if self._is_global_search():
            label = f"[{path.name}]  {code}  {eng[:38]}"
        else:
            label = f"{code}  {eng[:50]}"
        self.entry_list.insert(idx, label)
        if _is_missing(eng):
            self.entry_list.itemconfigure(idx, foreground=COLOR_MISSING)
        self.entry_list.selection_set(idx)

    def _select_index(self, idx: int):
        self._flush_current()
        path, code = self.filtered[idx]
        if path != self.cur_file:
            if self._dirty and not self._confirm_discard():
                return
            self.cur_file = path
            data = self._get_data(path)
            self.codes = list(data.keys())
            self._dirty = False
            self.file_var.set(path.name)
            missing = sum(1 for c in self.codes if _is_missing(data[c].get("english", "")))
            self.lbl_info.config(text=f"{len(self.codes)} entries  •  {missing} missing")
        self.entry_list.selection_clear(0, tk.END)
        self.entry_list.selection_set(idx)
        self.entry_list.see(idx)
        self._load_entry(path, code)

    def _on_list_select(self, _event):
        sel = self.entry_list.curselection()
        if not sel:
            return
        path, code = self.filtered[sel[0]]
        if code == self.cur_code and path == self.cur_file:
            return
        self._flush_current()
        if path != self.cur_file:
            self.cur_file = path
            data = self._get_data(path)
            self.codes = list(data.keys())
            self._dirty = False
            self.file_var.set(path.name)
            missing = sum(1 for c in self.codes if _is_missing(data[c].get("english", "")))
            self.lbl_info.config(text=f"{len(self.codes)} entries  •  {missing} missing")
        self._load_entry(path, code)

    def _jump_missing(self, direction: int):
        if not self.filtered:
            return
        cur_key = (self.cur_file, self.cur_code)
        start = self.filtered.index(cur_key) if cur_key in self.filtered else 0
        n = len(self.filtered)
        for step in range(1, n + 1):
            idx = (start + direction * step) % n
            path, code = self.filtered[idx]
            eng = self._get_data(path)[code].get("english", "")
            if _is_missing(eng):
                self._select_index(idx)
                return

    # ---------------------------------------------------------------- form

    def _load_entry(self, path: Path, code: str):
        self._loading = True
        entry = self._get_data(path)[code]
        self.cur_code = code
        self.lbl_code.config(text=code)

        self.txt_korean.config(state=tk.NORMAL)
        self.txt_korean.delete("1.0", tk.END)
        self.txt_korean.insert("1.0", entry.get("korean", ""))
        self.txt_korean.config(state=tk.DISABLED)

        self.txt_mtl.config(state=tk.NORMAL)
        self.txt_mtl.delete("1.0", tk.END)
        self.txt_mtl.config(state=tk.DISABLED)

        self.txt_english.delete("1.0", tk.END)
        self.txt_english.insert("1.0", entry.get("english", ""))
        self.txt_english.edit_reset()
        self._loading = False

    def _flush_current(self):
        if self.cur_code is None or self.cur_file is None:
            return
        new_en = self.txt_english.get("1.0", tk.END).rstrip("\n")
        data   = self._get_data(self.cur_file)
        if new_en != data[self.cur_code].get("english", ""):
            data[self.cur_code]["english"] = new_en
            self._mark_dirty()
            self._refresh_row(self.cur_file, self.cur_code)

    def _clear_form(self):
        self._loading = True
        self.lbl_code.config(text="")
        self.txt_korean.config(state=tk.NORMAL)
        self.txt_korean.delete("1.0", tk.END)
        self.txt_korean.config(state=tk.DISABLED)
        self.txt_english.delete("1.0", tk.END)
        self.txt_english.edit_reset()
        self._loading = False

    def _on_english_key(self, _event):
        if not self._loading:
            self._mark_dirty()

    # ----------------------------------------------------------- copy / undo

    def _copy_code(self):
        text = self.lbl_code.cget("text")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def _copy_korean(self):
        text = self.txt_korean.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def _run_translation(self):
        if not _HAS_MTL:
            return
        korean = self.txt_korean.get("1.0", tk.END).strip()
        if not korean:
            return
        self.btn_translate.config(state=tk.DISABLED)
        self.txt_mtl.config(state=tk.NORMAL)
        self.txt_mtl.delete("1.0", tk.END)
        self.txt_mtl.insert("1.0", "…")
        self.txt_mtl.config(state=tk.DISABLED)

        def _worker():
            async def _translate():
                async with GoogleTranslateV2() as tr:
                    return await tr.translate(korean, src="ko", dest="en")
            try:
                result = asyncio.run(_translate())
                if not result or result == korean:
                    result = "[Translation failed]"
            except Exception as exc:
                result = f"[Error: {exc}]"
            self.after(0, lambda: self._set_mtl(result))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_mtl(self, text: str):
        self.txt_mtl.config(state=tk.NORMAL)
        self.txt_mtl.delete("1.0", tk.END)
        self.txt_mtl.insert("1.0", text)
        self.txt_mtl.config(state=tk.DISABLED)
        self.btn_translate.config(state=tk.NORMAL)

    def _apply_mtl(self):
        mtl = self.txt_mtl.get("1.0", tk.END).strip()
        if mtl and not mtl.startswith("["):
            self.txt_english.delete("1.0", tk.END)
            self.txt_english.insert("1.0", mtl)
            self._mark_dirty()

    def _copy_from_above(self):
        self._copy_english_from_neighbor(-1)

    def _copy_from_below(self):
        self._copy_english_from_neighbor(+1)

    def _copy_english_from_neighbor(self, direction: int):
        if not self.cur_code or not self.cur_file:
            return
        key = (self.cur_file, self.cur_code)
        if key not in self.filtered:
            return
        idx = self.filtered.index(key)
        neighbor_idx = idx + direction
        if 0 <= neighbor_idx < len(self.filtered):
            n_path, n_code = self.filtered[neighbor_idx]
            english = self._get_data(n_path)[n_code].get("english", "")
            self.txt_english.delete("1.0", tk.END)
            self.txt_english.insert("1.0", english)
            self._mark_dirty()

    def _undo(self):
        try:
            self.txt_english.edit_undo()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- state

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            self.var_status.set("Unsaved changes")

    def _confirm_discard(self) -> bool:
        return messagebox.askyesno("Unsaved Changes", "Discard unsaved changes?", parent=self)

    def _save(self):
        self._flush_current()
        if not self.cur_file:
            return
        try:
            _save(self.cur_file, self._get_data(self.cur_file))
            self._dirty = False
            self.var_status.set(f"Saved — {self.cur_file.name}")
        except Exception as exc:
            messagebox.showerror("Save Error", str(exc), parent=self)

    def _on_close(self):
        if self._dirty:
            ans = messagebox.askyesnocancel("Unsaved Changes", "Save before closing?", parent=self)
            if ans is None:
                return
            if ans:
                self._save()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
