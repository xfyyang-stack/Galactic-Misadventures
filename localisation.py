"""Translate interface keys and structured history without altering game state."""

from content import EVENTS, TALENTS, load_data

UI = load_data("ui")


def text(key, language, **values):
    return UI[key][language].format(**values)


def effect_text(delta, language):
    if not delta:
        return text("no_change", language)
    return "  /  ".join(f"{text(stat, language)} {change:+d}" for stat, change in delta.items())


def history_text(record, language):
    if record["kind"] == "talent":
        item = TALENTS[record["id"]]
        return (text("log_talent", language, title=item["title"][language]),
                item["description"][language], effect_text(record["delta"], language))
    event = EVENTS[record["id"]]
    if record["kind"] == "forced":
        result = event["result"][language]
    else:
        option = next(o for o in event["options"] if o["id"] == record["option"])
        outcome = option if record["outcome"] == "fixed" else option[record["outcome"]]
        result = option["text"][language] + "\n" + outcome["result"][language]
    return (text("log_event", language, day=record["day"], title=event["title"][language]),
            result, effect_text(record["delta"], language))
