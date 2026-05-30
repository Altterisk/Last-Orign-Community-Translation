# LO Translation — Community Contribution

Translation correction project for **Last Origin** (라스트 오리진 / ラストオリジン) — Global server.  
The goal is to improve the machine-translated English text by reviewing and correcting entries in `for_review/`.

---

## Workflow

### 1 — Edit translations

```
python review_editor.py
```

Opens the **Review Editor** — a GUI for browsing and editing every entry in `for_review/`.

- Pick a file from the dropdown (◀ ▶ to step between files).
- The **Korean** field is read-only for reference; edit the **English** field.
- Missing / placeholder entries (`No_Trans_*`) are highlighted in red.
- Use **Next missing ▶** / **◀ Prev missing** to jump straight to untranslated entries.
- Search filters by code, Korean, or English text.
- Press **Save** when done with a file.

### 2 — Edit correction rules

```
python corrections_editor.py
```

Opens the **Corrections Editor** — a GUI for managing `corrections/corrections.json`.  
Each rule defines:
- a **Korean context phrase** to match the right entries
- the **correct English term**
- a list of known **mistranslations** to auto-replace everywhere

### 3 — Apply corrections

```
python fix_common_mistranslation.py
```

Applies all rules from `corrections/corrections.json` across every file in `for_review/`, fixing mistranslations in-place.

---

## Getting the patch

> **Note:** Modifying game files is against the game's Terms of Service. The patching method and the patch itself will not be shared in this repository.

The patch can be downloaded from the community Discord (not the official discord):  
**https://discord.com/invite/PS3pAMF6FZ**

If you want to learn how to make the patch, or want to try adapting it for another language, contact **Altter** in the Discord.

---

## Contributing

All translation work lives in `for_review/`.  
Each JSON file contains up to 1 000 entries:

```json
{
  "1000100001": {
    "korean":  "네이팜 미사일 : 추가 화염 피해",
    "english": "Napalm Missile: Additional fire damage"
  }
}
```

To contribute:
1. Edit the `"english"` value for any entry that looks wrong or unnatural.
2. If you spot a recurring mistranslation, add a rule in `corrections_editor.py` so it gets fixed everywhere automatically.
3. Submit a pull request with your changes to `for_review/` and/or `corrections/corrections.json`.

---

## Directory reference

| Path | Description |
|---|---|
| `for_review/` | Working JSONs — **edit these to correct translations** |
| `for_review/ko_kr_fill.json` | Entries filled from the KR-server Korean asset — lowest priority, only applied when a translation is otherwise missing |
| `json/` | Original extracted JSONs — backup / source of truth, do not edit |
| `corrections/corrections.json` | Mistranslation correction rules |
