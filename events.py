"""Eligibility, weighted event sampling, run-wide exclusions, and risk rolls.

The module takes an explicit random.Random instance so simulation and save/resume
use the same rules without depending on Tkinter or global random state.
"""

from content import CONFIG, EVENTS


def meets_requirements(stats, requirements):
    for key, limit in requirements.items():
        bound, stat = key.split("_", 1)
        if bound == "min" and stats[stat] < limit:
            return False
        if bound == "max" and stats[stat] > limit:
            return False
    return True


def eligible(event, stats, day):
    return (event["min_day"] <= day <= event["max_day"]
            and meets_requirements(stats, event["requirements"]))


def polarity_probabilities(luck, event_type="optional"):
    band = next(b for b in CONFIG["luck_bands"] if luck <= b["max"])
    return dict(zip(CONFIG["polarity_order"], band[event_type]))


def event_weight(event, stats):
    weight = event["weight"]
    for bonus in CONFIG["tag_bonuses"]:
        if bonus["tag"] in event["tags"] and meets_requirements(stats, bonus["requirements"]):
            weight *= bonus["multiplier"]
    return weight


def draw_one(pool, stats, rng, event_type):
    """Renormalise only across available polarities; never relax stat limits."""
    if not pool:
        return None
    probabilities = polarity_probabilities(stats["luck"], event_type)
    polarities = [p for p in probabilities if any(e["polarity"] == p for e in pool)]
    polarity = rng.choices(polarities, [probabilities[p] for p in polarities])[0]
    candidates = [e for e in pool if e["polarity"] == polarity]
    return rng.choices(candidates, [event_weight(e, stats) for e in candidates])[0]["id"]


def optional_pool(stats, day, seen_event_ids, catalogue=None):
    all_events = EVENTS.values() if catalogue is None else catalogue
    seen = set(seen_event_ids)
    return [e for e in all_events if e["type"] == "optional"
            and e["id"] not in seen and eligible(e, stats, day)]


def draw_optional(stats, day, seen_event_ids, rng, catalogue=None):
    """Never recycle a displayed card, even when fewer than three remain."""
    available = optional_pool(stats, day, seen_event_ids, catalogue)
    chosen = []
    for _ in range(min(CONFIG["optional_choices"], len(available))):
        event_id = draw_one(available, stats, rng, "optional")
        chosen.append(event_id)
        available = [e for e in available if e["id"] != event_id]
    return chosen


def draw_forced(stats, day, rng, seen_event_ids=()):
    seen = set(seen_event_ids)
    pool = [e for e in EVENTS.values() if e["type"] == "forced"
            and e["id"] not in seen and eligible(e, stats, day)]
    return draw_one(pool, stats, rng, "forced")


def has_forced_event(day, rng):
    return day in CONFIG["forced_days"] or rng.random() < CONFIG["forced_chance"]


def risk_probability(rationality):
    risk = CONFIG["risk"]
    return max(risk["min"], min(risk["max"], risk["base"] + risk["slope"] * (rationality - risk["pivot"])))


def resolve_option(option, stats, rng):
    result = "fixed"
    if option["risky"]:
        result = "success" if rng.random() < risk_probability(stats["rationality"]) else "failure"
    outcome = option if result == "fixed" else option[result]
    return result, dict(outcome["effects"])
