"""One ordered resolver: death at any time; other endings only after day seven."""

from content import CONFIG, ENDINGS
from events import meets_requirements


def resolve_ending(stats, day, completed=False):
    if stats["vitality"] == 0:
        return "E01"
    if day < CONFIG["max_days"] or not completed:
        return None
    for ending in ENDINGS.values():
        rules = dict(ending["requirements"])
        lead = rules.pop("vitality_lead", None)
        if lead is not None and stats["vitality"] < max(stats[k] for k in stats if k != "vitality") + lead:
            continue
        if meets_requirements(stats, rules):
            return ending["id"]
    raise ValueError("The catalogue must include a default ending.")
