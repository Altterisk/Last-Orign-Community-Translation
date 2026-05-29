import re

# Common mistranslations: {wrong: correct}
# Add entries here as new mistranslations are discovered.
MISTRANSLATION_DICT = {
    "Jim": "I",
    "Jima": "I",
    "Jimm": "I",
    "myself Jim": "myself",
    "I'm Jim": "I'm",
    "I am Jim": "I am",
}


def fix_bracket(raw_kr: str, trans: str) -> str:
    """Fix bracket/placeholder mismatches introduced by machine translation."""
    if ("{2}%" in raw_kr) and ("(2)%" in trans):
        trans = trans.replace("(2)%", "{2}%")
    if ("{1}%" in raw_kr) and ("(1)%" in trans):
        trans = trans.replace("(1)%", "{1}%")
    if ("{0}%" in raw_kr) and ("{0%)" in trans):
        trans = trans.replace("{0%)", "{0}%")
    if ("{0}%" in raw_kr) and ("{0%}%" in trans):
        trans = trans.replace("{0%}%", "{0}%")
    if ("{0}%" in raw_kr) and ("{0%" in trans):
        trans = trans.replace("{0%", "{0}%")
    if ("{0}%" in raw_kr) and ("10-0%" in trans):
        trans = trans.replace("10-0%", "{0}%")
    if ("{0}%" in raw_kr) and ("0.0%" in trans):
        trans = trans.replace("0.0%", "{0}%")
    if ("{0}%" in raw_kr) and ("(0)%" in trans):
        trans = trans.replace("(0)%", "{0}%")
    if ("{0}" in raw_kr) and ("{0)" in trans):
        trans = trans.replace("{0)", "{0}")
    if ("{0}" in raw_kr) and ("(0}" in trans):
        trans = trans.replace("(0}", "{0}")
    if ("{0}" in raw_kr) and ("(0)" in trans):
        trans = trans.replace("(0)", "{0}")
    if ("{0}%" in raw_kr) and ("(0%" in trans):
        trans = trans.replace("(0%", "{0}%")
    if ("{0}%" in raw_kr) and ("{0}0%" in trans):
        trans = trans.replace("{0}0%", "{0}%")
    if ("{0}" in raw_kr) and trans.endswith("{0"):
        trans = trans + "}"
    if ("{2}" not in raw_kr) and ("{1}" not in raw_kr) and trans.endswith("{2}"):
        trans = trans[:-4] + "{0}"
    if ("{2}" not in raw_kr) and ("{1}" not in raw_kr) and trans.endswith("{200%)"):
        trans = trans[:-6] + "{0}"
    return trans


def apply_mistranslation(trans: str, mistranslation_dict: dict = None) -> str:
    """
    Apply mistranslation corrections using a word-replacement dict.

    mistranslation_dict maps wrong strings to their correct replacements.
    Matching is case-insensitive; replacement preserves the correct casing.
    Defaults to MISTRANSLATION_DICT if not provided.
    """
    if mistranslation_dict is None:
        mistranslation_dict = MISTRANSLATION_DICT
    for wrong, correct in mistranslation_dict.items():
        trans = re.compile(r'\b' + re.escape(wrong) + r'\b', re.IGNORECASE).sub(correct, trans)
    return trans
