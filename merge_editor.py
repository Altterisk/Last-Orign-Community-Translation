"""
Merge Editor — compare for_review/ against any JSON folder in the same format
(default: merge_review/) and pick entries one by one.

Only shows entries where the source (merge_review) differs from BOTH:
  - the original baseline in json/  (meaning merge_review changed something)
  - the current for_review          (meaning there is still a diff to resolve)

Choices are recorded in memory.  On Save:
  - Chosen entries are written to for_review/
  - Chosen entries are removed from the source folder (merge_review)
  - Skipped / unvisited entries stay untouched in merge_review

Usage:
    python merge_editor.py
    python merge_editor.py --source my_corrections
"""

import argparse
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

BASE_DIR    = Path(__file__).resolve().parent
REVIEW_DIR  = BASE_DIR / "for_review"
ORIG_DIR    = BASE_DIR / "json"

sys.path.insert(0, str(BASE_DIR))
from fix_common_mistranslation import apply_corrections, load_corrections  # noqa: E402

_CORRECTIONS = load_corrections(BASE_DIR / "corrections" / "corrections.json")


# ---------------------------------------------------------------------------
# Data loading

def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def collect_diffs(source_dir: Path) -> list[tuple]:
    """
    Returns (fname, eid, korean, orig_en, rev_en, src_en) for every entry where,
    after applying corrections to both sides:
      - src_en != orig_en  (merge_review changed something from baseline)
      - src_en != rev_en   (still unresolved after corrections)
    Displayed rev_en / src_en are the correction-applied versions.
    """
    diffs = []
    for src_path in sorted(source_dir.glob("*.json")):
        rev_path  = REVIEW_DIR / src_path.name
        orig_path = ORIG_DIR   / src_path.name
        if not rev_path.exists():
            continue
        src_data  = load_json(src_path)
        rev_data  = load_json(rev_path)
        orig_data = load_json(orig_path) if orig_path.exists() else {}
        for eid, src_entry in src_data.items():
            # merge_review values are plain english strings ({eid: english}); tolerate
            # the legacy {eid: {english, korean}} dict format too.
            if isinstance(src_entry, dict):
                src_en  = src_entry.get("english", "")
                src_kor = src_entry.get("korean", "")
            else:
                src_en  = src_entry or ""
                src_kor = ""
            rev_en  = rev_data.get(eid,  {}).get("english", "")
            orig_en = orig_data.get(eid, {}).get("english", "")
            korean  = src_kor or rev_data.get(eid, {}).get("korean", "")
            if not src_en or not rev_en:
                continue
            # Apply corrections to both sides before comparing
            src_fixed = apply_corrections(korean, src_en, _CORRECTIONS)
            rev_fixed = apply_corrections(korean, rev_en, _CORRECTIONS)
            if src_fixed != orig_en and src_fixed != rev_fixed:
                diffs.append((src_path.name, eid, korean, orig_en, rev_fixed, src_fixed))
    return diffs


# ---------------------------------------------------------------------------
# Editor GUI

class MergeEditor(tk.Tk):
    def __init__(self, source_dir: Path):
        super().__init__()
        self.source_dir = source_dir
        self.title(f"Merge Editor  ·  for_review  ←→  {source_dir.name}")
        self.geometry("1100x780")
        self.configure(bg="#1e1e1e")

        self._review_cache: dict[str, dict] = {}   # fname -> for_review data
        self._source_cache: dict[str, dict] = {}   # fname -> merge_review data
        # pending[(fname, eid)] = chosen english string
        self._pending:      dict[tuple, str] = {}
        self._diffs:        list[tuple]      = []
        self._idx:          int              = 0

        self._build_ui()
        self._reload_diffs()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        C   = {"bg": "#1e1e1e", "fg": "#d4d4d4"}
        BAR = {"bg": "#2d2d2d"}

        # Top bar
        top = tk.Frame(self, **BAR, pady=4)
        top.pack(fill="x")
        self._status = tk.Label(top, text="", font=("Consolas", 10), **{**C, **BAR})
        self._status.pack(side="left", padx=10)
        tk.Button(top, text="Reload", command=self._reload_diffs,
                  bg="#3c3c3c", fg="#d4d4d4").pack(side="right", padx=4)
        tk.Button(top, text="Save & clean up", command=self._save_all,
                  bg="#0e639c", fg="white").pack(side="right", padx=4)

        # File / entry progress
        mid = tk.Frame(self, **BAR, pady=2)
        mid.pack(fill="x")
        self._file_label = tk.Label(mid, text="", font=("Consolas", 9),
                                    fg="#888", bg="#2d2d2d")
        self._file_label.pack(side="left", padx=10)
        self._pos_label = tk.Label(mid, text="", font=("Consolas", 9),
                                   fg="#888", bg="#2d2d2d")
        self._pos_label.pack(side="right", padx=10)

        # Korean
        kr_frame = tk.LabelFrame(self, text="Korean", bg="#1e1e1e", fg="#888",
                                  font=("Consolas", 9))
        kr_frame.pack(fill="x", padx=8, pady=(6, 2))
        self._kr_text = tk.Text(kr_frame, height=2, font=("Consolas", 10),
                                 bg="#252526", fg="#9cdcfe", relief="flat",
                                 wrap="word", state="disabled")
        self._kr_text.pack(fill="x", padx=4, pady=2)

        # Original (json baseline)
        orig_frame = tk.LabelFrame(self, text="Original  (json baseline)",
                                    bg="#1e1e1e", fg="#888", font=("Consolas", 9))
        orig_frame.pack(fill="x", padx=8, pady=(0, 2))
        self._orig_text = tk.Text(orig_frame, height=2, font=("Consolas", 10),
                                   bg="#1a1a2e", fg="#888888", relief="flat",
                                   wrap="word", state="disabled")
        self._orig_text.pack(fill="x", padx=4, pady=2)

        # Two-column: for_review vs source
        cols = tk.Frame(self, bg="#1e1e1e")
        cols.pack(fill="both", expand=True, padx=8, pady=4)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        lf = tk.LabelFrame(cols, text="for_review  (current)",
                            bg="#1e1e1e", fg="#4ec9b0", font=("Consolas", 9))
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self._rev_text = tk.Text(lf, font=("Consolas", 11), bg="#1e1e1e",
                                  fg="#d4d4d4", relief="flat", wrap="word",
                                  state="disabled")
        self._rev_text.pack(fill="both", expand=True, padx=4, pady=4)

        rf = tk.LabelFrame(cols, text=f"{self.source_dir.name}  (incoming)",
                            bg="#1e1e1e", fg="#ce9178", font=("Consolas", 9))
        rf.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        self._src_text = tk.Text(rf, font=("Consolas", 11), bg="#1e1e1e",
                                  fg="#d4d4d4", relief="flat", wrap="word",
                                  state="disabled")
        self._src_text.pack(fill="both", expand=True, padx=4, pady=4)

        # Result
        res_frame = tk.LabelFrame(self, text="Result  (editable)",
                                   bg="#1e1e1e", fg="#dcdcaa", font=("Consolas", 9))
        res_frame.pack(fill="x", padx=8, pady=(0, 4))
        self._res_text = tk.Text(res_frame, height=3, font=("Consolas", 11),
                                  bg="#252526", fg="#dcdcaa", relief="flat",
                                  wrap="word")
        self._res_text.pack(fill="x", padx=4, pady=4)

        # Per-entry buttons
        btn = tk.Frame(self, bg="#1e1e1e")
        btn.pack(fill="x", padx=8, pady=(4, 1))

        BTN = {"font": ("Consolas", 11), "width": 18, "pady": 6}
        tk.Button(btn, text="◀ Prev", command=self._prev,
                  bg="#3c3c3c", fg="#d4d4d4", **BTN).pack(side="left", padx=2)
        tk.Button(btn, text="Keep current  ←", command=self._keep_review,
                  bg="#1f4e79", fg="white", **BTN).pack(side="left", padx=2)
        tk.Button(btn, text="Use incoming  →", command=self._keep_source,
                  bg="#6b2d0e", fg="white", **BTN).pack(side="left", padx=2)
        tk.Button(btn, text="Use result  ✓", command=self._use_result,
                  bg="#1e4d1e", fg="white", **BTN).pack(side="left", padx=2)
        tk.Button(btn, text="Skip", command=self._skip,
                  bg="#3c3c3c", fg="#888", **BTN).pack(side="left", padx=2)
        tk.Button(btn, text="Next ▶", command=self._next,
                  bg="#3c3c3c", fg="#d4d4d4", **BTN).pack(side="right", padx=2)

        # Bulk action buttons
        bulk = tk.Frame(self, bg="#1e1e1e")
        bulk.pack(fill="x", padx=8, pady=(1, 4))

        BULK = {"font": ("Consolas", 10), "pady": 4}
        tk.Button(bulk, text="Accept ALL current  ◀◀",
                  command=self._accept_all_review,
                  bg="#163352", fg="#a0c8e8", **BULK).pack(side="left", padx=2)
        tk.Button(bulk, text="Accept ALL incoming  ▶▶",
                  command=self._accept_all_source,
                  bg="#3d1a07", fg="#e8b090", **BULK).pack(side="left", padx=2)

        self.bind("<Left>",      lambda e: self._prev())
        self.bind("<Right>",     lambda e: self._next())
        self.bind("<Return>",    lambda e: self._use_result())
        self.bind("1",           lambda e: self._keep_review())
        self.bind("2",           lambda e: self._keep_source())
        self.bind("<Control-s>", lambda e: self._save_all())

    # ── Data helpers ───────────────────────────────────────────────────────

    def _reload_diffs(self):
        self._diffs = collect_diffs(self.source_dir)
        self._idx   = 0
        self._pending.clear()
        self._review_cache.clear()
        self._source_cache.clear()
        self._update_status()
        self._show_current()

    def _get_review_data(self, fname: str) -> dict:
        if fname not in self._review_cache:
            self._review_cache[fname] = load_json(REVIEW_DIR / fname)
        return self._review_cache[fname]

    def _get_source_data(self, fname: str) -> dict:
        if fname not in self._source_cache:
            p = self.source_dir / fname
            self._source_cache[fname] = load_json(p) if p.exists() else {}
        return self._source_cache[fname]

    def _set_text(self, widget: tk.Text, value: str, editable: bool = False):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        if not editable:
            widget.config(state="disabled")

    def _update_status(self):
        total   = len(self._diffs)
        chosen  = len(self._pending)
        remaining = total - chosen
        self._status.config(
            text=f"{total} diffs  ·  {chosen} chosen  ·  {remaining} remaining"
        )

    def _show_current(self):
        if not self._diffs:
            self._status.config(text="No differences to review.")
            for w in (self._kr_text, self._orig_text, self._rev_text,
                      self._src_text, self._res_text):
                self._set_text(w, "", editable=(w is self._res_text))
            self._file_label.config(text="")
            self._pos_label.config(text="")
            return

        fname, eid, korean, orig_en, rev_en, src_en = self._diffs[self._idx]
        self._pos_label.config(text=f"{self._idx + 1} / {len(self._diffs)}")
        self._file_label.config(text=f"{fname}  ·  {eid}")
        self._set_text(self._kr_text,   korean)
        self._set_text(self._orig_text, orig_en or "(not in json baseline)")
        self._set_text(self._rev_text,  rev_en)
        self._set_text(self._src_text,  src_en)

        # Result: show already-chosen value if revisiting, else default to current
        key = (fname, eid)
        default = self._pending.get(key, rev_en)
        self._set_text(self._res_text, default, editable=True)

        self._update_status()

    # ── Navigation / actions ───────────────────────────────────────────────

    def _record(self, english: str):
        """Record a choice for the current entry and advance."""
        fname, eid, *_ = self._diffs[self._idx]
        self._pending[(fname, eid)] = english
        self._update_status()
        self._next()

    def _keep_review(self):
        _, _, _, _, rev_en, _ = self._diffs[self._idx]
        self._record(rev_en)

    def _keep_source(self):
        _, _, _, _, _, src_en = self._diffs[self._idx]
        self._record(src_en)

    def _use_result(self):
        text = self._res_text.get("1.0", "end").strip()
        if text:
            self._record(text)

    def _skip(self):
        self._next()

    def _next(self):
        if self._idx < len(self._diffs) - 1:
            self._idx += 1
        self._show_current()

    def _prev(self):
        if self._idx > 0:
            self._idx -= 1
        self._show_current()

    def _accept_all_review(self):
        remaining = [d for d in self._diffs if (d[0], d[1]) not in self._pending]
        if not remaining:
            messagebox.showinfo("Nothing to do", "No unchosen entries remaining.")
            return
        if not messagebox.askyesno(
            "Accept all current",
            f"Keep for_review text for all {len(remaining)} unchosen entries and save?\n\n"
            "This will also remove them from the source folder.",
        ):
            return
        for fname, eid, _, _, rev_en, _ in remaining:
            self._pending[(fname, eid)] = rev_en
        self._save_all()

    def _accept_all_source(self):
        remaining = [d for d in self._diffs if (d[0], d[1]) not in self._pending]
        if not remaining:
            messagebox.showinfo("Nothing to do", "No unchosen entries remaining.")
            return
        if not messagebox.askyesno(
            "Accept all incoming",
            f"Use incoming text for all {len(remaining)} unchosen entries and save?\n\n"
            "This will also remove them from the source folder.",
        ):
            return
        for fname, eid, _, _, _, src_en in remaining:
            self._pending[(fname, eid)] = src_en
        self._save_all()

    def _save_all(self):
        if not self._pending:
            messagebox.showinfo("Save", "No choices made yet.")
            return

        # Group chosen entries by file
        by_file: dict[str, dict] = {}
        for (fname, eid), english in self._pending.items():
            by_file.setdefault(fname, {})[eid] = english

        # Write chosen entries to for_review and remove them from merge_review
        for fname, choices in by_file.items():
            # Update for_review
            rev_data = self._get_review_data(fname)
            for eid, english in choices.items():
                if eid in rev_data:
                    rev_data[eid]["english"] = english
            save_json(REVIEW_DIR / fname, rev_data)

            # Remove chosen entries from merge_review source file
            src_data = self._get_source_data(fname)
            for eid in choices:
                src_data.pop(eid, None)
            src_path = self.source_dir / fname
            if src_data:
                save_json(src_path, src_data)
            else:
                src_path.unlink(missing_ok=True)   # empty file — delete it

        saved = len(self._pending)
        self._pending.clear()
        self._review_cache.clear()
        self._source_cache.clear()
        self._reload_diffs()
        messagebox.showinfo(
            "Saved",
            f"Wrote {saved} entries to for_review/\n"
            f"Removed them from {self.source_dir.name}/\n\n"
            f"{len(self._diffs)} entries still pending review."
        )


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="merge_review",
                        help="Folder to merge from (default: merge_review)")
    args = parser.parse_args()

    source_dir = BASE_DIR / args.source
    if not source_dir.is_dir():
        raise SystemExit(f"Source folder not found: {source_dir}")

    app = MergeEditor(source_dir)
    app.mainloop()


if __name__ == "__main__":
    main()
