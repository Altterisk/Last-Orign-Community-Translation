from pathlib import Path
import json
import re

try:
    BASE_DIR = Path(__file__).resolve().parent
except NameError:
    BASE_DIR = Path.cwd()

CORRECTIONS_FILE = BASE_DIR / "corrections" / "corrections.json"
REVIEW_DIR       = BASE_DIR / "for_review"


def load_corrections(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _wrong_pattern(wrong: str) -> re.Pattern:
    """
    Build a case-insensitive regex for `wrong` with word boundaries on whichever
    ends are word characters.  This prevents e.g. "Felis" from matching inside
    "Feliss" and turning it into "Felisss".
    """
    pat = re.escape(wrong)
    if re.match(r"\w", wrong):
        pat = r"\b" + pat
    if re.search(r"\w$", wrong):
        pat = pat + r"\b"
    return re.compile(pat, re.IGNORECASE)


def apply_corrections(korean: str, english: str, corrections: list[dict]) -> str:
    """Apply corrections.json rules: check Korean context, fix English mistranslations."""
    for entry in corrections:
        if entry["original"] not in korean:
            continue
        correct = entry["correctTranslation"]
        for wrong in entry["mistranslation"]:
            if wrong.lower() in english.lower():
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


def main():
    if not CORRECTIONS_FILE.exists():
        print(f"corrections.json not found at {CORRECTIONS_FILE}")
        return

    corrections = load_corrections(CORRECTIONS_FILE)
    print(f"Loaded {len(corrections)} correction rules from {CORRECTIONS_FILE.name}")

    json_files = sorted(REVIEW_DIR.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {REVIEW_DIR}")
        return

    print(f"Processing {len(json_files)} file(s) in {REVIEW_DIR.name}/\n")

    total_entries = 0
    total_changes = 0

    for src in json_files:
        try:
            with open(src, "r", encoding="utf-8") as f:
                chunk = json.load(f)
        except Exception as e:
            print(f"  Skipping {src.name}: {e}")
            continue

        fixed, changes = fix_chunk(chunk, corrections)

        if changes:
            with open(src, "w", encoding="utf-8") as f:
                json.dump(fixed, f, ensure_ascii=False, indent=2)

        total_entries += len(fixed)
        total_changes += changes
        print(f"  {src.name}: {len(fixed)} entries, {changes} fixed")

    print(f"\nDone. {total_changes} corrections across {total_entries} entries.")


if __name__ == "__main__":
    main()
