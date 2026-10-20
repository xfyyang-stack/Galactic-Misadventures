"""Load the editable, bilingual JSON catalogue using paths relative to this file."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_data(name):
    return json.loads((ROOT / "data" / (name + ".json")).read_text(encoding="utf-8"))


CONFIG = load_data("config")
TALENTS = {item["id"]: item for item in load_data("talents")}
EVENTS = {item["id"]: item for item in load_data("events")}
ENDINGS = {item["id"]: item for item in load_data("endings")}
STAT_KEYS = tuple(CONFIG["initial_stats"])


def validate_catalogue():
    """Fail early on missing translations, bad effects, or invalid event structure."""
    def bilingual(value):
        assert set(value) == {"zh", "en"} and all(isinstance(s, str) and s for s in value.values())

    def effect(value):
        assert set(value) <= set(STAT_KEYS)
        assert all(type(n) is int and abs(n) <= 8 for n in value.values())

    assert (len(TALENTS), len(EVENTS), len(ENDINGS)) == (10, 56, 12)
    for item in [*TALENTS.values(), *EVENTS.values(), *ENDINGS.values()]:
        bilingual(item["title"])
        bilingual(item["description"])
        if item["id"] in TALENTS:
            effect(item["effects"])
            assert sum(item["effects"].values()) == 2
        elif item["id"] in EVENTS:
            assert item["polarity"] in CONFIG["polarity_order"] and item["weight"] > 0
            assert 1 <= item["min_day"] <= item["max_day"] <= CONFIG["max_days"]
            for key, limit in item["requirements"].items():
                bound, stat = key.split("_", 1)
                assert bound in ("min", "max") and stat in STAT_KEYS and type(limit) is int
            if item["type"] == "forced":
                assert "options" not in item
                effect(item["effects"])
                bilingual(item["result"])
            else:
                options = item["options"]
                assert 2 <= len(options) <= 3
                assert len({o["id"] for o in options}) == len(options)
                for option in options:
                    bilingual(option["text"])
                    for outcome in ([option["success"], option["failure"]] if option["risky"] else [option]):
                        effect(outcome["effects"])
                        bilingual(outcome["result"])


validate_catalogue()
