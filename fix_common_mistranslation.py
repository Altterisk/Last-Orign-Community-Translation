from pathlib import Path
import argparse
import json
import re

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

CORRECTIONS_FILE = BASE_DIR / "corrections" / "corrections.json"
REVIEW_DIR       = BASE_DIR / "for_review"
MTL_DIR          = BASE_DIR / "mtl"


def load_corrections(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _wrong_pattern(wrong: str) -> re.Pattern:
    """
    Build a regex for `wrong` with word boundaries on whichever ends are word
    characters.  This prevents e.g. "Felis" from matching inside "Feliss".
    All-caps `wrong` (e.g. "MOVE" as a stat) is matched case-sensitively so it
    doesn't collide with the lowercase action word.
    """
    pat = re.escape(wrong)
    if re.match(r"\w", wrong):
        pat = r"\b" + pat
    if re.search(r"\w$", wrong):
        pat = pat + r"\b"
    flags = 0 if wrong.isupper() else re.IGNORECASE
    return re.compile(pat, flags)


def apply_corrections(korean: str, english: str, corrections: list[dict]) -> str:
    """Apply corrections.json rules: check Korean context, fix English mistranslations."""
    for entry in corrections:
        if entry["original"] not in korean:
            continue
        correct = entry["correctTranslation"]
        for wrong in sorted(entry["mistranslation"], key=len, reverse=True):
            present = wrong in english if wrong.isupper() else wrong.lower() in english.lower()
            if present:
                english = _wrong_pattern(wrong).sub(correct, english)
    return english


def fix_chunk(chunk: dict[str, dict], corrections: list[dict]) -> tuple[dict, int]:
    """Fix all entries in a chunk. Returns (fixed_chunk, change_count)."""
    fixed = {}
    changes = 0
    for code, entry in chunk.items():
        korean  = entry.get("korean",  "")
        english = entry.get("english", "")
        fixed_english = apply_corrections(korean, english, corrections)
        fixed[code] = {"english": fixed_english, "korean": korean}
        if fixed_english != english:
            changes += 1
    return fixed, changes


def process_dir(directory: Path, corrections: list[dict], dry: bool) -> tuple[int, int]:
    """Apply corrections to every *.json in `directory`. Returns (entries, changes)."""
    json_files = sorted(directory.glob("*.json"))
    if not json_files:
        print(f"  No JSON files in {directory}")
        return 0, 0
    print(f"Processing {len(json_files)} file(s) in {directory.name}/")
    total_entries = total_changes = 0
    for src in json_files:
        try:
            chunk = json.loads(src.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Skipping {src.name}: {e}")
            continue
        fixed, changes = fix_chunk(chunk, corrections)
        if changes and not dry:
            src.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")
        total_entries += len(fixed)
        total_changes += changes
        if changes:
            print(f"  {src.name}: {len(fixed)} entries, {changes} fixed")
    return total_entries, total_changes


def main():
    ap = argparse.ArgumentParser(description="Apply corrections.json to translation JSONs.")
    ap.add_argument("--review", action="store_true", help="process for_review/ (default)")
    ap.add_argument("--mtl", action="store_true", help="process mtl/")
    ap.add_argument("--all", action="store_true", help="process both for_review/ and mtl/")
    ap.add_argument("--dry", action="store_true", help="report changes without writing")
    args = ap.parse_args()

    if not CORRECTIONS_FILE.exists():
        print(f"corrections.json not found at {CORRECTIONS_FILE}")
        return
    corrections = load_corrections(CORRECTIONS_FILE)
    print(f"Loaded {len(corrections)} correction rules from {CORRECTIONS_FILE.name}\n")

    # choose target dirs
    dirs = []
    if args.all or (args.review and args.mtl):
        dirs = [REVIEW_DIR, MTL_DIR]
    elif args.mtl:
        dirs = [MTL_DIR]
    else:
        dirs = [REVIEW_DIR]   # default

    grand_entries = grand_changes = 0
    for d in dirs:
        if not d.is_dir():
            print(f"  {d} not found, skipping")
            continue
        e, c = process_dir(d, corrections, args.dry)
        grand_entries += e
        grand_changes += c
        print()

    tag = " (dry run, nothing written)" if args.dry else ""
    print(f"Done. {grand_changes} corrections across {grand_entries} entries{tag}.")


if __name__ == "__main__":
    main()
