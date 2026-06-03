"""
Update Editor — resolve for_review/updated_* and for_review/new_* files.

Version history per code:
  - Newest update file   = "update"
  - One before it        = "base"  (original json if only one update exists)

Categories:
  duplicate  for_review == update   → already up to date, remove silently
  safe       for_review == base     → untouched; hidden by default, toggle to review
  conflict   for_review != base AND != update → shown always

"Accept safe updates" applies the update to all unreviewed safe entries at once.
Toggle "Show safe" to review them individually instead.

Ctrl/Shift-click for multi-select; action buttons apply to all selected.
"""

import json
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    raise SystemExit("tkinter not available")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR   = Path(__file__).resolve().parent
REVIEW_DIR = BASE_DIR / "for_review"
ORIG_DIR   = BASE_DIR / "json"

sys.path.insert(0, str(BASE_DIR))
from fix_common_mistranslation import apply_corrections, load_corrections  # noqa

_CORRECTIONS = load_corrections(BASE_DIR / "corrections" / "corrections.json")

BG         = "#1e1e1e"
PANEL      = "#252526"
WIDGET     = "#3c3c3c"
FG         = "#d4d4d4"
DIM        = "#888888"
SEL_BG     = "#094771"
SEL_FG     = "#ffffff"
TEAL       = "#4ec9b0"
ORANGE     = "#ce9178"
YELLOW     = "#dcdcaa"
BLUE_LT    = "#9cdcfe"
PURPLE     = "#c586c0"
SAFE_FG    = "#6a9955"    # green-ish for safe entries in the list
TRIVIAL_FG = "#888800"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def _save(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _apply(korean: str, english: str) -> str:  # available for manual use
    return apply_corrections(korean, english, _CORRECTIONS) if english else ""

def _is_trivial(english: str) -> bool:
    return english.strip() in ("", "0")


# ---------------------------------------------------------------------------
# Data

class Diff:
    __slots__ = ("upd_file", "code", "korean", "orig_en", "base_en",
                 "cur_en", "upd_en", "trivial", "is_safe")

    def __init__(self, upd_file: Path, code: str, korean: str,
                 orig_en: str, base_en: str, cur_en: str, upd_en: str,
                 is_safe: bool = False):
        self.upd_file = upd_file
        self.code     = code
        self.korean   = korean
        self.orig_en  = orig_en
        self.base_en  = base_en
        self.cur_en   = cur_en
        self.upd_en   = upd_en
        self.trivial  = _is_trivial(upd_en)
        self.is_safe  = is_safe   # True when for_review == base (untouched)


_Dup = tuple[Path, str]


def collect() -> tuple[list[Diff], list[_Dup]]:
    """
    Returns (diffs, dups).
    diffs includes both conflicts (is_safe=False) and safe entries (is_safe=True).
    dups are exact matches (for_review == update) — remove without showing.
    """
    code_to_fname: dict[str, str]  = {}
    review_flat:   dict[str, dict] = {}
    for p in sorted(REVIEW_DIR.glob("localization_*.json")):
        try:
            chunk = _load(p)
            for code, entry in chunk.items():
                code_to_fname[code] = p.name
                review_flat[code]   = entry
        except Exception:
            pass

    orig_flat: dict[str, dict] = {}
    for p in sorted(ORIG_DIR.glob("localization_*.json")):
        try:
            orig_flat.update(_load(p))
        except Exception:
            pass

    history: dict[str, list] = {}
    for upd_path in sorted(
        list(REVIEW_DIR.glob("updated_*.json")) + list(REVIEW_DIR.glob("new_*.json")),
        key=lambda p: p.stat().st_mtime,
    ):
        mtime = upd_path.stat().st_mtime
        try:
            data = _load(upd_path)
        except Exception:
            continue
        for code, entry in data.items():
            if code not in code_to_fname:
                continue
            history.setdefault(code, []).append((
                mtime,
                entry.get("english", ""),
                entry.get("korean",  ""),
                upd_path,
            ))

    diffs: list[Diff] = []
    dups:  list[_Dup] = []

    for code, entries in sorted(history.items()):
        entries.sort(key=lambda x: x[0])

        _, upd_en_raw, upd_ko, upd_file = entries[-1]
        base_en_raw = entries[-2][1] if len(entries) >= 2 \
                      else orig_flat.get(code, {}).get("english", "")

        rev_entry  = review_flat[code]
        cur_en_raw = rev_entry.get("english", "")
        korean     = upd_ko or rev_entry.get("korean", "")
        orig_en    = orig_flat.get(code, {}).get("english", "")

        if upd_en_raw == base_en_raw:
            continue                     # no real change in this round

        if cur_en_raw == upd_en_raw:
            dups.append((upd_file, code))
            continue

        is_safe = (cur_en_raw == base_en_raw)

        diffs.append(Diff(
            upd_file=upd_file,
            code=code,
            korean=korean,
            orig_en=orig_en,
            base_en=base_en_raw,
            cur_en=cur_en_raw,
            upd_en=upd_en_raw,
            is_safe=is_safe,
        ))

    return diffs, dups


def remove_from_upd_files(pairs: list[tuple[Path, str]]) -> int:
    by_file: dict[Path, list[str]] = {}
    for upd_path, code in pairs:
        by_file.setdefault(upd_path, []).append(code)
    removed = 0
    for upd_path, codes in by_file.items():
        if not upd_path.exists():
            continue
        try:
            data = _load(upd_path)
            for code in codes:
                if code in data:
                    data.pop(code)
                    removed += 1
            if data:
                _save(upd_path, data)
            else:
                upd_path.unlink()
        except Exception as e:
            print(f"Warning: {upd_path.name}: {e}")
    return removed


# ---------------------------------------------------------------------------
# Range dialog

class RangeDialog(tk.Toplevel):
    def __init__(self, parent, total: int, callback):
        super().__init__(parent)
        self.title("Mass action on range")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._cb = callback

        tk.Label(self, text=f"Apply to entries  (1 – {total})",
                 bg=BG, fg=FG, font=("Consolas", 10)).grid(
            row=0, column=0, columnspan=4, padx=14, pady=(14, 6), sticky="w")

        tk.Label(self, text="From:", bg=BG, fg=FG).grid(row=1, column=0, padx=(14, 4), sticky="e")
        self._from = tk.Spinbox(self, from_=1, to=total, width=7,
                                bg=WIDGET, fg=FG, buttonbackground=WIDGET, insertbackground=FG)
        self._from.grid(row=1, column=1, padx=4)

        tk.Label(self, text="To:", bg=BG, fg=FG).grid(row=1, column=2, padx=4, sticky="e")
        self._to = tk.Spinbox(self, from_=1, to=total, width=7,
                              bg=WIDGET, fg=FG, buttonbackground=WIDGET, insertbackground=FG)
        self._to.delete(0, "end")
        self._to.insert(0, str(total))
        self._to.grid(row=1, column=3, padx=(4, 14))

        self._action = tk.StringVar(value="current")
        tk.Radiobutton(self, text="Keep current  (for_review)", variable=self._action,
                       value="current", bg=BG, fg=TEAL,
                       selectcolor=BG, activebackground=BG).grid(
            row=2, column=0, columnspan=4, padx=14, pady=(10, 2), sticky="w")
        tk.Radiobutton(self, text="Use incoming  (update)", variable=self._action,
                       value="incoming", bg=BG, fg=ORANGE,
                       selectcolor=BG, activebackground=BG).grid(
            row=3, column=0, columnspan=4, padx=14, pady=(2, 10), sticky="w")

        f = tk.Frame(self, bg=BG)
        f.grid(row=4, column=0, columnspan=4, pady=(0, 12))
        tk.Button(f, text="Apply",  command=self._apply,   bg="#0e639c", fg="white",  width=10).pack(side="left", padx=6)
        tk.Button(f, text="Cancel", command=self.destroy,  bg=WIDGET,    fg=FG,       width=10).pack(side="left", padx=6)

    def _apply(self):
        try:
            frm = int(self._from.get()) - 1
            to  = int(self._to.get())
        except ValueError:
            return
        self._cb(frm, to, self._action.get())
        self.destroy()


# ---------------------------------------------------------------------------
# Editor

class UpdateEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Update Editor  —  for_review/updated_* & new_*")
        self.geometry("1200x880")
        self.configure(bg=BG)

        self._diffs:      list[Diff]            = []
        self._dups:       list[_Dup]            = []
        self._choices:    dict[str, str | None] = {}
        self._show_safe   = False
        self._idx         = 0
        self._search_var  = tk.StringVar()
        self._search_job: str | None = None

        self._build()
        self._reload()

    # ── helpers ───────────────────────────────────────────────────────────

    def _visible(self) -> list[Diff]:
        """Diffs currently shown in the listbox (filtered by safe toggle + search)."""
        base = self._diffs if self._show_safe else [d for d in self._diffs if not d.is_safe]
        q = self._search_var.get().strip().lower()
        if not q:
            return base
        return [
            d for d in base
            if q in d.code.lower()
            or q in d.cur_en.lower()
            or q in d.upd_en.lower()
            or q in d.korean.lower()
        ]

    def _safe_diffs(self) -> list[Diff]:
        return [d for d in self._diffs if d.is_safe]

    def _schedule_search(self):
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(300, self._run_search)

    def _run_search(self):
        self._search_job = None
        self._idx = 0
        self._rebuild_list()
        self._show()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self):
        bar = tk.Frame(self, bg="#2d2d2d", pady=4)
        bar.pack(fill="x")
        self._lbl_status = tk.Label(bar, text="", font=("Consolas", 10),
                                    bg="#2d2d2d", fg=FG)
        self._lbl_status.pack(side="left", padx=10)
        tk.Button(bar, text="Reload",          command=self._reload,
                  bg=WIDGET, fg=FG).pack(side="right", padx=4)
        tk.Button(bar, text="Save & clean up", command=self._save_all,
                  bg="#0e639c", fg="white").pack(side="right", padx=4)

        abar = tk.Frame(self, bg="#252526", pady=4)
        abar.pack(fill="x")
        self._btn_safe = tk.Button(abar, text="Accept safe updates (0)",
                                   command=self._accept_safe,
                                   bg="#1a3a1a", fg="#80ff80")
        self._btn_safe.pack(side="left", padx=(8, 4))
        self._btn_toggle_safe = tk.Button(abar, text="Show safe  ▼",
                                          command=self._toggle_safe,
                                          bg="#1a2a1a", fg=SAFE_FG)
        self._btn_toggle_safe.pack(side="left", padx=4)
        tk.Button(abar, text="Remove all duplicates",
                  command=self._remove_all_dups,
                  bg="#2d3a2d", fg="#a0e8a0").pack(side="left", padx=4)
        tk.Button(abar, text="Auto-keep current for empty / 0",
                  command=self._auto_trivial,
                  bg="#3a3800", fg="#ffd966").pack(side="left", padx=4)
        tk.Button(abar, text="Mass action on range...",
                  command=self._open_range_dialog,
                  bg="#2d2d50", fg="#a0a0ff").pack(side="left", padx=4)

        pw = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        pw.pack(fill="both", expand=True, padx=6, pady=(4, 0))

        left = tk.Frame(pw, bg=BG, width=330)
        left.pack_propagate(False)
        pw.add(left, weight=1)

        tk.Label(left, text="Entries  (* = empty/0   ✓ = chosen)   Ctrl/Shift multi-select",
                 bg=BG, fg=DIM, font=("Consolas", 8)).pack(anchor="w", padx=6, pady=(4, 2))

        sr = tk.Frame(left, bg=BG)
        sr.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(sr, text="Search:", bg=BG, fg=DIM,
                 font=("Consolas", 9)).pack(side="left", padx=(0, 4))
        self._search_var.trace_add("write", lambda *_: self._schedule_search())
        tk.Entry(sr, textvariable=self._search_var, font=("Consolas", 9),
                 bg=WIDGET, fg=FG, insertbackground=FG, relief="flat").pack(
            side="left", fill="x", expand=True)
        tk.Button(sr, text="×", width=2, command=lambda: self._search_var.set(""),
                  bg=WIDGET, fg=DIM, relief="flat").pack(side="left", padx=(2, 0))

        lf = tk.Frame(left, bg=BG)
        lf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(lf)
        self._listbox = tk.Listbox(
            lf, yscrollcommand=sb.set, selectmode=tk.EXTENDED,
            font=("Consolas", 9), bg=PANEL, fg=FG, relief="flat", bd=0,
            selectbackground=SEL_BG, selectforeground=SEL_FG, activestyle="none",
        )
        sb.config(command=self._listbox.yview)
        sb.pack(side="right", fill="y")
        self._listbox.pack(side="left", fill="both", expand=True)
        self._listbox.bind("<ButtonRelease-1>", self._on_list_click)
        self._listbox.bind("<<ListboxSelect>>",  self._on_list_kbd)

        right = tk.Frame(pw, bg=BG)
        pw.add(right, weight=3)

        self._lbl_pos = tk.Label(right, text="", bg=BG, fg=DIM, font=("Consolas", 9))
        self._lbl_pos.pack(anchor="w", padx=8, pady=(4, 0))

        def _txt(label, color, height, editable=False):
            f = tk.LabelFrame(right, text=label, bg=BG, fg=color, font=("Consolas", 9))
            f.pack(fill="x", padx=8, pady=2)
            t = tk.Text(f, height=height, font=("Consolas", 10),
                        bg=PANEL, fg=FG, relief="flat", wrap="word",
                        insertbackground=FG,
                        state="normal" if editable else "disabled")
            t.pack(fill="x", padx=4, pady=2)
            return t

        self._txt_ko   = _txt("Korean",                                      BLUE_LT, 2)
        self._txt_orig = _txt("Original  (json baseline)",                   DIM,     2)
        self._txt_base = _txt("Base  (previous update / original if first)", PURPLE,  2)
        self._txt_cur  = _txt("Current  (for_review)",                       TEAL,    2)
        self._txt_upd  = _txt("Incoming  (newest update)",                   ORANGE,  2)
        self._txt_res  = _txt("Result  (editable)",                          YELLOW,  2, editable=True)

        btns = tk.Frame(right, bg=BG)
        btns.pack(fill="x", padx=8, pady=(4, 2))
        B = {"font": ("Consolas", 11), "pady": 5, "width": 20}
        tk.Button(btns, text="Keep current  [1]",   command=self._keep_cur,
                  bg="#1f4e79", fg="white", **B).pack(side="left", padx=2)
        tk.Button(btns, text="Use incoming  [2]",   command=self._keep_upd,
                  bg="#6b2d0e", fg="white", **B).pack(side="left", padx=2)
        tk.Button(btns, text="Use result  [Enter]", command=self._use_result,
                  bg="#1e4d1e", fg="white", **B).pack(side="left", padx=2)
        tk.Button(btns, text="Skip  [S]",           command=self._skip,
                  bg=WIDGET, fg=DIM, **B).pack(side="left", padx=2)

        nav = tk.Frame(right, bg=BG)
        nav.pack(fill="x", padx=8, pady=(0, 6))
        tk.Button(nav, text="◀ Prev", command=self._prev, bg=WIDGET, fg=FG).pack(side="left", padx=2)
        tk.Button(nav, text="Next ▶", command=self._next, bg=WIDGET, fg=FG).pack(side="left", padx=2)

        self.bind("<Control-Key-1>", lambda e: self._keep_cur())
        self.bind("<Control-Key-2>", lambda e: self._keep_upd())
        self.bind("<Return>",        lambda e: self._use_result())
        self.bind("<Control-Key-x>", lambda e: self._skip())
        self.bind("<Control-s>",     lambda e: self._save_all())
        self.bind("<Left>",          lambda e: self._prev())
        self.bind("<Right>",         lambda e: self._next())

    # ── data ──────────────────────────────────────────────────────────────

    def _reload(self):
        self._diffs, self._dups = collect()
        self._choices = {}
        self._idx = 0
        self._rebuild_list()
        self._show()
        n_safe = len(self._safe_diffs())
        self._btn_safe.config(text=f"Accept safe updates ({n_safe})")

    def _rebuild_list(self):
        vis = self._visible()
        self._listbox.delete(0, "end")
        for d in vis:
            if d.code in self._choices:
                marker = "✓" if self._choices[d.code] is not None else "-"
            elif d.trivial:
                marker = "*"
            elif d.is_safe:
                marker = "~"
            else:
                marker = " "
            label = f"{marker} {d.code}  {d.upd_en[:28]}"
            self._listbox.insert("end", label)
            if d.code in self._choices:
                self._listbox.itemconfig("end",
                    fg=TEAL if self._choices[d.code] is not None else DIM)
            elif d.is_safe:
                self._listbox.itemconfig("end", fg=SAFE_FG)
            elif d.trivial:
                self._listbox.itemconfig("end", fg=TRIVIAL_FG)
        self._update_status()

    def _update_status(self):
        vis     = self._visible()
        total   = len(vis)
        n_safe  = len(self._safe_diffs())
        chosen  = sum(1 for d in vis if self._choices.get(d.code) is not None)
        skipped = sum(1 for d in vis if d.code in self._choices and self._choices[d.code] is None)
        trivial = sum(1 for d in vis if d.trivial)
        sel     = list(self._listbox.curselection())
        sel_str = f"  ·  {len(sel)} selected" if len(sel) > 1 else ""
        self._lbl_status.config(
            text=f"{total} shown  ·  {chosen} chosen  ·  {skipped} skipped  ·  "
                 f"{trivial} empty/0  ·  {len(self._dups)} dups  ·  "
                 f"{n_safe} safe{sel_str}"
        )

    def _set_text(self, widget, value, editable=False):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if not editable:
            widget.config(state="disabled")

    def _show_detail(self):
        vis = self._visible()
        if not vis:
            self._lbl_pos.config(text="No entries to review.")
            for w in (self._txt_ko, self._txt_orig, self._txt_base,
                      self._txt_cur, self._txt_upd, self._txt_res):
                self._set_text(w, "")
            self._set_text(self._txt_res, "", editable=True)
            return

        d = vis[self._idx]
        sel = list(self._listbox.curselection())
        safe_tag = "  [safe]" if d.is_safe else ""
        sel_info = f"   [{len(sel)} selected]" if len(sel) > 1 else ""
        self._lbl_pos.config(
            text=f"{self._idx + 1} / {len(vis)}   "
                 f"code: {d.code}{safe_tag}   src: {d.upd_file.name}{sel_info}"
        )
        self._set_text(self._txt_ko,   d.korean)
        self._set_text(self._txt_orig, d.orig_en  or "(not in json baseline)")
        self._set_text(self._txt_base, d.base_en  or "(no previous update)")
        self._set_text(self._txt_cur,  d.cur_en   or "(not in for_review)")
        self._set_text(self._txt_upd,  d.upd_en   or "(empty)")
        default = self._choices.get(d.code, d.cur_en)
        self._set_text(self._txt_res, default or "", editable=True)

    def _show(self):
        self._show_detail()
        vis = self._visible()
        if vis:
            self._listbox.selection_clear(0, "end")
            self._listbox.selection_set(self._idx)
            self._listbox.see(self._idx)

    # ── per-entry actions ─────────────────────────────────────────────────

    def _current_diff(self) -> Diff:
        return self._visible()[self._idx]

    def _selected_indices(self) -> list[int]:
        return list(self._listbox.curselection())

    def _apply_pairs(self, pairs: list[tuple[int, str | None]]):
        """Apply (listbox_index, english) pairs. None = skip."""
        vis = self._visible()
        for i, english in pairs:
            d = vis[i]
            self._choices[d.code] = english
            marker = "✓" if english is not None else "-"
            self._listbox.delete(i)
            self._listbox.insert(i, f"{marker} {d.code}  {d.upd_en[:28]}")
            self._listbox.itemconfig(i, fg=TEAL if english is not None else DIM)
        self._update_status()

    def _record(self, english: str):
        """Apply the SAME english to all selected (used by Use Result)."""
        sel = self._selected_indices()
        targets = sel if len(sel) > 1 else [self._idx]
        self._apply_pairs([(i, english) for i in targets])
        self._advance_to_unchosen(max(targets) + 1)

    def _skip_selected(self):
        sel = self._selected_indices()
        targets = sel if len(sel) > 1 else [self._idx]
        self._apply_pairs([(i, None) for i in targets])
        self._advance_to_unchosen(max(targets) + 1)

    def _advance_to_unchosen(self, start: int):
        vis = self._visible()
        n = len(vis)
        for i in list(range(start, n)) + list(range(0, min(start, n))):
            if vis[i].code not in self._choices:
                self._idx = i
                self._show()
                return
        self._show()

    def _keep_cur(self):
        sel = self._selected_indices()
        vis = self._visible()
        targets = sel if len(sel) > 1 else [self._idx]
        self._apply_pairs([(i, vis[i].cur_en) for i in targets])
        self._advance_to_unchosen(max(targets) + 1)

    def _keep_upd(self):
        sel = self._selected_indices()
        vis = self._visible()
        targets = sel if len(sel) > 1 else [self._idx]
        self._apply_pairs([(i, vis[i].upd_en) for i in targets])
        self._advance_to_unchosen(max(targets) + 1)

    def _use_result(self):
        text = self._txt_res.get("1.0", "end").strip()
        if text:
            self._record(text)

    def _skip(self):
        self._skip_selected()

    def _next(self):
        vis = self._visible()
        if self._idx < len(vis) - 1:
            self._idx += 1
        self._show()

    def _prev(self):
        if self._idx > 0:
            self._idx -= 1
        self._show()

    def _on_list_click(self, event):
        idx = self._listbox.nearest(event.y)
        if 0 <= idx < len(self._visible()):
            self._idx = idx
            self._show_detail()
        self._update_status()

    def _on_list_kbd(self, _event):
        sel = list(self._listbox.curselection())
        if len(sel) == 1 and sel[0] != self._idx:
            self._idx = sel[0]
            self._show_detail()
        self._update_status()

    # ── bulk actions ──────────────────────────────────────────────────────

    def _toggle_safe(self):
        self._show_safe = not self._show_safe
        self._btn_toggle_safe.config(
            text="Hide safe  ▲" if self._show_safe else "Show safe  ▼"
        )
        # Keep _idx pointing at the same code if still visible
        vis_before = self._visible()
        cur_code = vis_before[self._idx].code if vis_before else None
        self._rebuild_list()
        vis_after = self._visible()
        if cur_code:
            for i, d in enumerate(vis_after):
                if d.code == cur_code:
                    self._idx = i
                    self._show()
                    return
        self._idx = 0
        self._show()

    def _accept_safe(self):
        pending_safe = [d for d in self._safe_diffs()
                        if d.code not in self._choices]
        if not pending_safe:
            messagebox.showinfo("Safe updates", "No unreviewed safe updates.")
            return
        if not messagebox.askyesno(
            "Accept safe updates",
            f"Apply {len(pending_safe)} updates where for_review == base?\n\n"
            "These entries have not been modified by the translator since the "
            "last update round, so the new update can be applied directly.",
        ):
            return

        code_to_fname: dict[str, str]  = {}
        review_files:  dict[str, dict] = {}
        for p in sorted(REVIEW_DIR.glob("localization_*.json")):
            try:
                chunk = _load(p)
                for code in chunk:
                    code_to_fname[code] = p.name
                review_files[p.name] = chunk
            except Exception:
                pass

        dirty: set[str] = set()
        for d in pending_safe:
            fname = code_to_fname.get(d.code)
            if fname:
                review_files[fname][d.code]["english"] = d.upd_en
                dirty.add(fname)

        for fname in dirty:
            _save(REVIEW_DIR / fname, review_files[fname])

        pairs = [(d.upd_file, d.code) for d in pending_safe]
        remove_from_upd_files(pairs)

        n = len(pending_safe)
        self._reload()
        messagebox.showinfo("Done", f"Applied {n} safe updates to for_review/.")

    def _remove_all_dups(self):
        if not self._dups:
            messagebox.showinfo("Duplicates", "No duplicates found.")
            return
        if not messagebox.askyesno(
            "Remove duplicates",
            f"Remove {len(self._dups)} duplicate entries from update files?",
        ):
            return
        n = remove_from_upd_files(self._dups)
        self._reload()
        messagebox.showinfo("Done", f"Removed {n} duplicate entries.")

    def _auto_trivial(self):
        vis = self._visible()
        trivials = [d for d in vis if d.trivial and d.code not in self._choices]
        if not trivials:
            messagebox.showinfo("Auto-keep", "No unchosen empty/0 entries visible.")
            return
        if not messagebox.askyesno(
            "Auto-keep current",
            f"Keep current for_review for {len(trivials)} empty/0 incoming entries?",
        ):
            return
        for d in trivials:
            self._choices[d.code] = d.cur_en
        self._rebuild_list()
        self._show()

    def _open_range_dialog(self):
        vis = self._visible()
        if not vis:
            return

        def _apply(frm: int, to: int, action: str):
            pairs = [
                (i, vis[i].cur_en if action == "current" else vis[i].upd_en)
                for i in range(max(0, frm), min(to, len(vis)))
                if vis[i].code not in self._choices
            ]
            self._apply_pairs(pairs)
            self._show()

        RangeDialog(self, len(vis), _apply)

    # ── save ──────────────────────────────────────────────────────────────

    def _save_all(self):
        actual = {code: en for code, en in self._choices.items() if en is not None}
        if not actual:
            messagebox.showinfo("Save", "No choices made yet.")
            return

        code_to_fname: dict[str, str]  = {}
        review_files:  dict[str, dict] = {}
        for p in sorted(REVIEW_DIR.glob("localization_*.json")):
            try:
                chunk = _load(p)
                for code in chunk:
                    code_to_fname[code] = p.name
                review_files[p.name] = chunk
            except Exception:
                pass

        dirty: set[str] = set()
        for code, english in actual.items():
            fname = code_to_fname.get(code)
            if fname:
                review_files[fname][code]["english"] = english
                dirty.add(fname)

        for fname in dirty:
            _save(REVIEW_DIR / fname, review_files[fname])

        # Remove resolved entries from update files
        all_diffs_by_code = {d.code: d for d in self._diffs}
        pairs = [(all_diffs_by_code[code].upd_file, code)
                 for code in actual if code in all_diffs_by_code]
        remove_from_upd_files(pairs)

        n = len(actual)
        self._reload()
        messagebox.showinfo("Saved",
                            f"Wrote {n} entries to for_review/.\n"
                            f"{len(self._visible())} entries still pending.")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = UpdateEditor()
    app.mainloop()
