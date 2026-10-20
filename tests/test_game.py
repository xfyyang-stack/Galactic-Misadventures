"""Rule, transition, probability, and deterministic restoration tests."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from content import CONFIG, ENDINGS, EVENTS, TALENTS, validate_catalogue
from endings import resolve_ending
from events import (draw_forced, draw_one, draw_optional, eligible, event_weight,
                    has_forced_event, meets_requirements, risk_probability)
from game import Game, GameState, InvalidAction


def snapshot(game):
    return json.loads(json.dumps(game.state.to_dict()))


def advance(game, strategy_rng):
    """Perform exactly one legal action, used by save and simulation tests."""
    state = game.state
    if state.phase == "TALENT_PICK":
        game.pick_talent(strategy_rng.choice(state.talent_candidates))
    elif state.phase == "OPTIONAL_CARDS":
        game.pick_event(strategy_rng.choice(state.optional_candidates))
    elif state.phase == "OPTIONAL_CHOICE":
        if state.selected_option is None:
            game.pick_option(strategy_rng.choice(EVENTS[state.selected_event]["options"])["id"])
        else:
            game.confirm_option()
    else:
        game.continue_phase()


class ContentTests(unittest.TestCase):
    def test_verified_game_content_is_preserved(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "tests" / "fixtures" / "release-content-sha256.json").read_text(encoding="utf-8"))
        for name, expected in manifest.items():
            with self.subTest(file=name):
                data = (root / name).read_bytes()
                if name.endswith(".json"):
                    data = data.replace(b"\r\n", b"\n")
                self.assertEqual(hashlib.sha256(data).hexdigest(), expected)

    def test_complete_catalogue(self):
        validate_catalogue()
        self.assertEqual(sum(e["type"] == "optional" for e in EVENTS.values()), 37)
        self.assertEqual(sum(e["type"] == "forced" for e in EVENTS.values()), 19)
        self.assertEqual(list(ENDINGS), [f"E{i:02}" for i in range(1, 13)])
        self.assertEqual(EVENTS["F08"]["weight"], .3)
        self.assertEqual(EVENTS["N01"]["options"][2]["effects"], {"vitality": -2, "fame": 3})
        self.assertEqual(EVENTS["N02"]["options"][1]["effects"]["luck"], 2)
        self.assertEqual(EVENTS["D02"]["options"][1]["effects"], {})

    def test_transcribed_risk_values(self):
        expected = {"D01": ({"luck": 4}, {"vitality": -5}),
                    "D02": ({"vitality": 5}, {"vitality": -4}),
                    "D03": ({"luck": 5}, {"luck": -4}),
                    "D05": ({"rationality": 3}, {"vitality": -4}),
                    "D08": ({"luck": 8}, {"luck": -8})}
        for event_id, (success, failure) in expected.items():
            with self.subTest(event=event_id):
                option = EVENTS[event_id]["options"][0]
                self.assertTrue(option["risky"])
                self.assertEqual(option["success"]["effects"], success)
                self.assertEqual(option["failure"]["effects"], failure)


class EventTests(unittest.TestCase):
    def setUp(self):
        self.stats = dict(CONFIG["initial_stats"])

    def test_requirement_boundaries(self):
        cases = [("D04", "fame", 8, True), ("D04", "fame", 9, False),
                 ("P03", "fame", 12, False), ("P03", "fame", 13, True),
                 ("D07", "fame", 16, False), ("D07", "fame", 17, True),
                 ("N05", "rationality", 13, False), ("N05", "rationality", 14, True),
                 ("N03", "rationality", 16, False), ("N03", "rationality", 17, True)]
        for event_id, stat, value, expected in cases:
            with self.subTest(event=event_id, value=value):
                self.stats[stat] = value
                self.assertEqual(eligible(EVENTS[event_id], self.stats, 1), expected)

    def test_late_expansion_event_starts_on_day_four(self):
        for day in range(1, 8):
            self.assertEqual(eligible(EVENTS["F19"], self.stats, day), day >= 4)

    def test_tag_weights_and_fame_not_a_weight(self):
        self.stats["rationality"] = 7
        self.assertEqual(event_weight(EVENTS["P08"], self.stats), 1.5)
        self.stats["rationality"] = 8
        self.assertEqual(event_weight(EVENTS["P08"], self.stats), 1)
        self.stats["rationality"] = 14
        self.assertEqual(event_weight(EVENTS["N05"], self.stats), 1.5)
        self.stats["fame"] = 30
        self.assertEqual(event_weight(EVENTS["P03"], self.stats), 1)

    def test_risk_formula_all_values(self):
        for rationality in range(31):
            self.assertAlmostEqual(risk_probability(rationality), max(.2, min(.85, .45 + .025 * (rationality - 12))))

    def test_forced_schedule_and_frequency(self):
        rng = random.Random(19)
        for day in (3, 7):
            self.assertTrue(all(has_forced_event(day, rng) for _ in range(100)))
        for day in (1, 2, 4, 5, 6):
            rate = sum(has_forced_event(day, rng) for _ in range(15000)) / 15000
            self.assertAlmostEqual(rate, .2, delta=.015)

    def test_polarity_distribution(self):
        # Test the first card, before no-replacement sampling changes the pool.
        # Its expected distribution is the configured polarity table.
        pool = [e for e in EVENTS.values() if e["type"] == "optional"]
        for luck, expected in [(0, (.2, .25, .55)), (8, (.3, .3, .4)),
                               (16, (.43, .3, .27)), (24, (.55, .3, .15))]:
            self.stats["luck"] = luck
            rng = random.Random(800 + luck)
            counts = Counter(EVENTS[draw_one(pool, self.stats, rng, "optional")]["polarity"] for _ in range(12000))
            for polarity, probability in zip(CONFIG["polarity_order"], expected):
                self.assertAlmostEqual(counts[polarity] / 12000, probability, delta=.022)

    def test_forced_distribution_and_black_hole_weight(self):
        self.stats["luck"] = 30
        rng = random.Random(721)
        counts = Counter(draw_forced(self.stats, 3, rng) for _ in range(22000))
        by_polarity = Counter()
        for event_id, count in counts.items():
            by_polarity[EVENTS[event_id]["polarity"]] += count
        for polarity, expected in [("positive", .5), ("neutral", .3), ("negative", .2)]:
            self.assertAlmostEqual(by_polarity[polarity] / 22000, expected, delta=.018)
        negative_weight = sum(event_weight(e, self.stats) for e in EVENTS.values()
                              if e["type"] == "forced" and e["polarity"] == "negative"
                              and eligible(e, self.stats, 3))
        self.assertAlmostEqual(counts["F08"] / by_polarity["negative"], .3 / negative_weight, delta=.018)

    def test_displayed_cards_excluded_for_entire_run(self):
        rng = random.Random(8)
        seen = ["P01", "N01", "D01"]
        for day in range(1, 8):
            for _ in range(60):
                hand = draw_optional(self.stats, day, seen, rng)
                self.assertEqual(len(hand), 3)
                self.assertEqual(len(set(hand)), 3)
                self.assertTrue(set(hand).isdisjoint(seen))
                self.assertTrue(all(eligible(EVENTS[e], self.stats, day) for e in hand))

    def test_sparse_pool_never_recycles_seen_cards(self):
        rng = random.Random(4)
        pool = [EVENTS["P01"], EVENTS["D04"]]
        self.assertEqual(draw_optional(self.stats, 2, ["P01"], rng, pool), [])
        self.assertEqual(draw_optional(self.stats, 2, [], rng, pool), ["P01"])
        self.assertEqual(draw_optional(self.stats, 2, [], rng, []), [])
        pool = [EVENTS["P01"], EVENTS["P02"], EVENTS["P04"]]
        self.assertEqual(draw_optional(self.stats, 2, ["P01", "P02"], rng, pool), ["P04"])
        self.assertEqual(draw_optional(self.stats, 2, [e["id"] for e in pool], rng, pool), [])

    def test_forced_events_do_not_repeat(self):
        rng, seen = random.Random(8), []
        expected = sum(e["type"] == "forced" and eligible(e, self.stats, 3) for e in EVENTS.values())
        for _ in range(expected):
            event_id = draw_forced(self.stats, 3, rng, seen)
            self.assertIsNotNone(event_id)
            self.assertNotIn(event_id, seen)
            seen.append(event_id)
        self.assertIsNone(draw_forced(self.stats, 3, rng, seen))

    def test_missing_polarity_renormalises(self):
        pool = [EVENTS["P01"], EVENTS["N01"]]
        rng = random.Random(2)
        self.stats["luck"] = 0
        counts = Counter(draw_one(pool, self.stats, rng, "optional") for _ in range(10000))
        self.assertAlmostEqual(counts["P01"] / 10000, .2 / .45, delta=.02)


class EndingTests(unittest.TestCase):
    def test_each_ending_and_priority(self):
        # Inputs are V, L, F, R, deliberately including overlapping conditions.
        examples = [(0, 30, 30, 0), (20, 21, 30, 8), (26, 16, 16, 16),
                    (19, 22, 23, 21), (19, 20, 13, 9), (19, 22, 12, 21),
                    (19, 21, 12, 12), (9, 12, 12, 12), (18, 12, 12, 13),
                    (18, 12, 12, 10), (18, 11, 12, 12), (18, 12, 12, 12)]
        for number, values in enumerate(examples, 1):
            with self.subTest(ending=number):
                self.assertEqual(resolve_ending(dict(zip(CONFIG["initial_stats"], values)), 7, True), f"E{number:02}")

    def test_immortal_needs_extreme_health_and_lead_over_every_other_stat(self):
        stats = dict(vitality=26, luck=16, fame=16, rationality=16)
        self.assertEqual(resolve_ending(stats, 7, True), "E03")
        for stat in ("vitality", "luck", "fame", "rationality"):
            below = dict(stats)
            below[stat] += -1 if stat == "vitality" else 1
            with self.subTest(stat=stat):
                self.assertNotEqual(resolve_ending(below, 7, True), "E03")
        self.assertEqual(resolve_ending(dict(vitality=30, luck=20, fame=20, rationality=0), 7, True), "E03")

    def test_only_death_before_completion(self):
        stats = dict(vitality=20, luck=30, fame=30, rationality=5)
        for day in range(1, 8):
            self.assertIsNone(resolve_ending(stats, day, False))
            if day < 7:
                self.assertIsNone(resolve_ending(stats, day, True))
        stats["vitality"] = 0
        self.assertEqual(resolve_ending(stats, 1), "E01")


class StateMachineTests(unittest.TestCase):
    def test_clamping_and_single_talent_application(self):
        game = Game(seed=6)
        game.pick_talent(game.state.talent_candidates[0])
        before = dict(game.state.stats)
        with self.assertRaises(InvalidAction):
            game.pick_talent(game.state.selected_talent)
        self.assertEqual(before, game.state.stats)
        game._apply({"vitality": 100, "luck": -100, "fame": 100, "rationality": -100})
        self.assertEqual(game.state.stats, dict(vitality=30, luck=0, fame=30, rationality=0))

    def test_no_roll_or_effect_until_confirmation(self):
        game = Game(seed=15)
        game.pick_talent(game.state.talent_candidates[0])
        if game.state.phase == "FORCED_RESOLVED":
            game.continue_phase()
        game.state.optional_candidates = ["D01", "P01", "N01"]
        before_stats = dict(game.state.stats)
        before_rng = game.rng.getstate()
        game.pick_event("D01")
        game.pick_option("A")
        self.assertEqual(before_stats, game.state.stats)
        self.assertEqual(before_rng, game.rng.getstate())
        game.confirm_option()
        before = snapshot(game)
        with self.assertRaises(InvalidAction):
            game.confirm_option()
        self.assertEqual(before, snapshot(game))

    def test_instant_death_stops_pipeline(self):
        game = Game(seed=15)
        game.pick_talent(game.state.talent_candidates[0])
        if game.state.phase == "FORCED_RESOLVED":
            game.continue_phase()
        game.state.stats["vitality"] = 1
        previous_fame = game.state.stats["fame"]
        game.state.optional_candidates = ["N01"]
        game.pick_event("N01")
        game.pick_option("C")
        game.confirm_option()
        self.assertEqual(game.state.phase, "ENDED")
        self.assertEqual(game.state.ending, "E01")
        self.assertEqual(game.state.death_event, "N01")
        self.assertEqual(game.state.stats["fame"], previous_fame + 3)  # simultaneous gains still apply
        with self.assertRaises(InvalidAction):
            game.continue_phase()

    def test_resume_every_phase_is_deterministic(self):
        phases = set()
        for seed in range(15):
            game = Game(seed=seed)
            choices = random.Random(seed + 100)
            for _ in range(70):
                phases.add(game.state.phase)
                saved = snapshot(game)
                restored = Game(GameState.from_dict(saved))
                self.assertEqual(saved, snapshot(restored))
                if game.state.phase == "ENDED":
                    break
                strategy_state = choices.getstate()
                advance(game, choices)
                choices.setstate(strategy_state)
                advance(restored, choices)
                self.assertEqual(snapshot(game), snapshot(restored))
            else:
                self.fail("A run did not finish within 70 transitions.")
        self.assertTrue({"TALENT_PICK", "FORCED_RESOLVED", "OPTIONAL_CARDS", "OPTIONAL_CHOICE",
                         "OPTIONAL_RESOLVED", "ENDED"} <= phases)

    def test_full_runs_have_exact_days_and_no_duplicate_rewards(self):
        endings = set()
        for seed in range(350):
            game, choices = Game(seed=seed), random.Random(seed + 99)
            for _ in range(70):
                if game.state.phase == "ENDED":
                    break
                advance(game, choices)
            self.assertEqual(game.state.phase, "ENDED")
            endings.add(game.state.ending)
            forced_days = [e["day"] for e in game.state.event_history if e["kind"] == "forced"]
            optional_days = [e["day"] for e in game.state.event_history if e["kind"] == "optional"]
            self.assertEqual(len(forced_days), len(set(forced_days)))
            self.assertEqual(optional_days, [h["day"] for h in game.state.optional_draw_history if h["ids"]])
            displayed = [e for h in game.state.optional_draw_history for e in h["ids"]]
            forced_ids = [e["id"] for e in game.state.event_history if e["kind"] == "forced"]
            self.assertEqual(len(displayed), len(set(displayed)))
            self.assertEqual(len(forced_ids), len(set(forced_ids)))
            self.assertEqual(set(game.state.seen_event_ids), set(displayed + forced_ids))
            self.assertTrue(all(0 <= value <= 30 for value in game.state.stats.values()))
            if game.state.ending != "E01":
                self.assertEqual(game.state.day, 7)
                self.assertTrue({3, 7} <= set(forced_days))
        self.assertEqual(endings, set(ENDINGS))

    def test_last_result_moves_directly_to_next_day(self):
        game = Game(seed=42)
        game.pick_talent(game.state.talent_candidates[0])
        self.assertEqual(game.state.phase, "OPTIONAL_CARDS")
        first_hand = list(game.state.optional_candidates)
        game.pick_event(first_hand[0])
        game.pick_option("A")
        game.confirm_option()
        self.assertEqual(game.state.phase, "OPTIONAL_RESOLVED")
        with patch("game.has_forced_event", return_value=False):
            game.continue_phase()
        self.assertEqual(game.state.day, 2)
        self.assertEqual(game.state.phase, "OPTIONAL_CARDS")
        self.assertTrue(set(first_hand).isdisjoint(game.state.optional_candidates))

    def test_forced_result_continues_same_day_before_optional(self):
        game = Game(seed=42)
        with patch("game.has_forced_event", return_value=True):
            game.pick_talent(game.state.talent_candidates[0])
        self.assertEqual(game.state.phase, "FORCED_RESOLVED")
        game.continue_phase()
        self.assertEqual(game.state.day, 1)
        self.assertEqual(game.state.phase, "OPTIONAL_CARDS")

    def test_empty_pool_does_not_block_journey(self):
        game = Game(seed=42)
        with patch("game.draw_optional", return_value=[]), patch("game.has_forced_event", return_value=False):
            game.pick_talent(game.state.talent_candidates[0])
            self.assertEqual(game.state.phase, "DAY_COMPLETE")
            game.continue_phase()
            self.assertEqual(game.state.day, 2)
        game.state.day = 7
        with patch("game.draw_optional", return_value=[]), patch("game.has_forced_event", return_value=True):
            game._begin_day()
            self.assertEqual(game.state.phase, "FORCED_RESOLVED")
            game.continue_phase()
            self.assertEqual(game.state.phase, "ENDED")

    def test_v1_save_migration_preserves_current_result_and_unselected_cards(self):
        game = Game(seed=42)
        game.pick_talent(game.state.talent_candidates[0])
        game.pick_event(game.state.optional_candidates[0])
        game.pick_option("A")
        game.confirm_option()
        old = snapshot(game)
        old["version"] = 1
        old.pop("seen_event_ids")
        old.pop("optional_draw_history")
        old["phase"] = "DAY_COMPLETE"
        restored = Game(GameState.from_dict(old))
        self.assertEqual(restored.state.version, 2)
        self.assertEqual(restored.state.phase, "OPTIONAL_RESOLVED")
        self.assertEqual(restored.state.resolved_result, old["resolved_result"])
        self.assertEqual(restored.state.stats, old["stats"])
        self.assertEqual(json.loads(json.dumps(restored.state.rng_state)), old["rng_state"])
        self.assertTrue(set(old["optional_candidates"]) <= set(restored.state.seen_event_ids))
        with patch("game.has_forced_event", return_value=False):
            restored.continue_phase()
        self.assertTrue(set(old["optional_candidates"]).isdisjoint(restored.state.optional_candidates))

    def test_all_displayed_cards_remain_excluded_after_restart(self):
        game = Game(seed=42)
        choices = random.Random(2)
        while game.state.day < 4:
            advance(game, choices)
        previous = set(game.state.seen_event_ids)
        restored = Game(GameState.from_dict(snapshot(game)))
        while restored.state.phase != "ENDED":
            old_days = len(restored.state.optional_draw_history)
            old_forced = len([r for r in restored.state.event_history if r["kind"] == "forced"])
            advance(restored, choices)
            for hand in restored.state.optional_draw_history[old_days:]:
                self.assertTrue(set(hand["ids"]).isdisjoint(previous))
            forced = [r for r in restored.state.event_history if r["kind"] == "forced"]
            for record in forced[old_forced:]:
                self.assertNotIn(record["id"], previous)

    def test_talent_sampling_is_uniform(self):
        counts = Counter(t for i in range(10000) for t in Game(seed=i).state.talent_candidates)
        for talent in TALENTS:
            self.assertAlmostEqual(counts[talent] / 10000, .3, delta=.025)

    def test_invalid_save_states_rejected(self):
        good = snapshot(Game(seed=1))
        for changes in [{"day": 8}, {"phase": "BOGUS"}, {"version": 99}, {"rng_state": [1]},
                        {"talent_candidates": ["T01"]}, {"stats": dict(vitality=-1)},
                        {"optional_candidates": ["P01", "P01"]}]:
            with self.subTest(changes=changes), self.assertRaises((ValueError, TypeError)):
                GameState.from_dict(dict(good, **changes))


if __name__ == "__main__":
    unittest.main()
