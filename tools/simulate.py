"""Reproducible offline balance simulations using the production game engine.

The non-random policies inspect numeric effects for analysis, even though those
effects are hidden in the GUI. Frequencies describe these policies, not fixed
ending probabilities or an exact reproduction of the Word document's model.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content import CONFIG, ENDINGS, EVENTS, TALENTS
from events import risk_probability
from game import Game

STRATEGIES = {
    "random": None,
    "conservative": {"vitality": 4, "luck": .5, "fame": .2, "rationality": .5},
    "high_luck": {"vitality": .6, "luck": 4, "fame": .1, "rationality": .1},
}


def effect_score(effects, weights, stats):
    return sum((max(0, min(CONFIG["stat_max"], stats[k] + effects.get(k, 0))) - stats[k]) * weights[k]
               for k in weights)


def option_score(option, state, weights, strategy):
    if not option["risky"]:
        return effect_score(option["effects"], weights, state.stats)
    probability = risk_probability(state.stats["rationality"])
    score = sum(p * effect_score(option[outcome]["effects"], weights, state.stats)
                for outcome, p in [("success", probability), ("failure", 1 - probability)])
    if strategy == "conservative":
        score -= 2
        if state.stats["vitality"] + option["failure"]["effects"].get("vitality", 0) <= 0:
            score -= 50
    return score


def choose(items, score, rng):
    values = [score(item) for item in items]
    best = max(values)
    return rng.choice([item for item, value in zip(items, values) if abs(value - best) < 1e-9])


def simulate(runs, seed, strategy):
    policy = random.Random(seed)
    counts, deaths, forced_count, survivors = Counter(), 0, 0, 0
    weights = STRATEGIES[strategy]
    for _ in range(runs):
        game = Game(seed=policy.getrandbits(64))
        for step in range(75):
            state = game.state
            if state.phase == "ENDED":
                break
            if state.phase == "TALENT_PICK":
                talent = (policy.choice(state.talent_candidates) if weights is None else
                          choose(state.talent_candidates, lambda t: effect_score(TALENTS[t]["effects"], weights, state.stats), policy))
                game.pick_talent(talent)
            elif state.phase == "OPTIONAL_CARDS":
                event = (policy.choice(state.optional_candidates) if weights is None else
                         choose(state.optional_candidates,
                                lambda e: max(option_score(o, state, weights, strategy) for o in EVENTS[e]["options"]), policy))
                game.pick_event(event)
            elif state.phase == "OPTIONAL_CHOICE":
                options = EVENTS[state.selected_event]["options"]
                option = (policy.choice(options) if weights is None else
                          choose(options, lambda o: option_score(o, state, weights, strategy), policy))
                game.pick_option(option["id"])
                game.confirm_option()
            else:
                game.continue_phase()
        else:
            raise AssertionError("Run failed to terminate.")
        counts[state.ending] += 1
        deaths += state.ending == "E01"
        assert len(state.committed_actions) == len(set(state.committed_actions))
        assert all(0 <= value <= CONFIG["stat_max"] for value in state.stats.values())
        if state.ending != "E01":
            assert state.day == CONFIG["max_days"]
            optional_days = [h["day"] for h in state.optional_draw_history if h["ids"]]
            assert [r["day"] for r in state.event_history if r["kind"] == "optional"] == optional_days
            forced = [r for r in state.event_history if r["kind"] == "forced"]
            assert {3, 7} <= {r["day"] for r in forced}
            assert len(forced) == len({r["day"] for r in forced})
            assert len(forced) == len({r["id"] for r in forced})
            displayed = [e for h in state.optional_draw_history for e in h["ids"]]
            assert len(displayed) == len(set(displayed))
            forced_count += len(forced)
            survivors += 1
    return {"runs": runs, "seed": seed, "strategy": strategy, "deaths": deaths,
            "mean_forced_events_among_survivors": round(forced_count / max(1, survivors), 4),
            "ending_counts": {e: counts[e] for e in ENDINGS},
            "ending_percentages": {e: round(100 * counts[e] / runs, 3) for e in ENDINGS}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "simulation-results.json")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    results = {s: simulate(args.runs, args.seed, s) for s in STRATEGIES}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Ending        Random   Conservative   High luck")
    for ending in ENDINGS:
        print(ending + "        " + "        ".join(f"{results[s]['ending_percentages'][ending]:6.2f}%" for s in STRATEGIES))
    print("Saved", args.output)


if __name__ == "__main__":
    main()
