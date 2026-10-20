"""Seven-day game state machine. All mutating actions are phase-checked.

No GUI or disk I/O lives here. Snapshots contain RNG state and structured log
references, allowing deterministic resume and live translation of past events.
"""

from dataclasses import asdict, dataclass, field
import random
from uuid import uuid4

from content import CONFIG, ENDINGS, EVENTS, STAT_KEYS, TALENTS
from endings import resolve_ending
from events import draw_forced, draw_optional, has_forced_event, optional_pool, resolve_option

PHASES = {"TALENT_PICK", "FORCED_RESOLVED", "OPTIONAL_CARDS", "OPTIONAL_CHOICE",
          "OPTIONAL_RESOLVED", "DAY_COMPLETE", "ENDED"}


class InvalidAction(ValueError):
    """The requested action no longer matches the current phase."""


def tuple_tree(value):
    return tuple(tuple_tree(v) for v in value) if isinstance(value, (tuple, list)) else value


@dataclass
class GameState:
    version: int = 2
    run_id: str = field(default_factory=lambda: uuid4().hex)
    day: int = 0
    phase: str = "TALENT_PICK"
    stats: dict = field(default_factory=lambda: dict(CONFIG["initial_stats"]))
    talent_candidates: list = field(default_factory=list)
    selected_talent: str | None = None
    optional_candidates: list = field(default_factory=list)
    current_forced_event: str | None = None
    selected_event: str | None = None
    selected_option: str | None = None
    resolved_result: dict | None = None
    event_history: list = field(default_factory=list)
    recent_selected_events: list = field(default_factory=list)
    seen_event_ids: list = field(default_factory=list)
    optional_draw_history: list = field(default_factory=list)
    committed_actions: list = field(default_factory=list)
    ending: str | None = None
    death_event: str | None = None
    rng_state: object = None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        if data.get("version") == 1:
            # v1 never recorded older unchosen hands. Preserve everything it did
            # record without changing candidates, stats, results, or RNG state.
            known = [r["id"] for r in data["event_history"] if r["kind"] != "talent"]
            known.extend(data["optional_candidates"])
            known.extend(e for e in (data["current_forced_event"], data["selected_event"]) if e)
            data["seen_event_ids"] = list(dict.fromkeys(known))
            data["optional_draw_history"] = ([{"day": data["day"], "ids": list(data["optional_candidates"])}]
                                             if data["optional_candidates"] else [])
            if data["phase"] == "DAY_COMPLETE" and data["selected_option"] and data["resolved_result"]:
                data["phase"] = "OPTIONAL_RESOLVED"
            data["version"] = 2
        state = cls(**data)
        if state.version != 2 or state.phase not in PHASES:
            raise ValueError("Unsupported save version or phase.")
        if type(state.day) is not int or not 0 <= state.day <= CONFIG["max_days"]:
            raise ValueError("Invalid day.")
        if set(state.stats) != set(STAT_KEYS) or any(type(n) is not int or not 0 <= n <= CONFIG["stat_max"] for n in state.stats.values()):
            raise ValueError("Invalid attributes.")
        if not isinstance(state.run_id, str) or not state.run_id:
            raise ValueError("Invalid run ID.")
        if len(state.talent_candidates) != CONFIG["talent_choices"] or len(set(state.talent_candidates)) != len(state.talent_candidates):
            raise ValueError("Invalid talent candidates.")
        if any(t not in TALENTS for t in state.talent_candidates):
            raise ValueError("Unknown talent.")
        if len(set(state.optional_candidates)) != len(state.optional_candidates) or len(state.optional_candidates) > CONFIG["optional_choices"]:
            raise ValueError("Invalid optional candidates.")
        if any(e not in EVENTS or EVENTS[e]["type"] != "optional" for e in state.optional_candidates):
            raise ValueError("Unknown optional event.")
        if state.phase == "TALENT_PICK":
            if state.day != 0 or state.selected_talent is not None:
                raise ValueError("Invalid talent selection phase.")
        elif state.day < 1 or state.selected_talent not in state.talent_candidates:
            raise ValueError("Missing selected talent.")
        if state.current_forced_event is not None and (state.current_forced_event not in EVENTS or EVENTS[state.current_forced_event]["type"] != "forced"):
            raise ValueError("Invalid forced event.")
        if state.phase == "FORCED_RESOLVED" and (not state.current_forced_event or not state.resolved_result):
            raise ValueError("Missing forced result.")
        if state.phase in ("OPTIONAL_CHOICE", "OPTIONAL_RESOLVED"):
            if state.selected_event not in state.optional_candidates:
                raise ValueError("Invalid selected event.")
            valid_options = {o["id"] for o in EVENTS[state.selected_event]["options"]}
            if state.selected_option is not None and state.selected_option not in valid_options:
                raise ValueError("Invalid option.")
        if state.phase == "OPTIONAL_RESOLVED" and (not state.selected_option or not state.resolved_result):
            raise ValueError("Missing optional result.")
        if state.phase == "ENDED" and state.ending not in ENDINGS:
            raise ValueError("Invalid ending.")
        if state.phase == "ENDED":
            if resolve_ending(state.stats, state.day, completed=True) != state.ending:
                raise ValueError("Ending does not match the final attributes.")
            if state.ending == "E01" and state.death_event not in EVENTS:
                raise ValueError("Missing fatal event.")
        if state.phase != "ENDED" and (state.ending is not None or state.stats["vitality"] == 0):
            raise ValueError("Unsettled ending.")
        if len(set(state.committed_actions)) != len(state.committed_actions):
            raise ValueError("Duplicate committed actions.")
        if state.resolved_result is not None:
            result = state.resolved_result
            event = EVENTS[result["event"]]
            if set(result["delta"]) - set(STAT_KEYS) or any(type(n) is not int for n in result["delta"].values()):
                raise ValueError("Invalid result effects.")
            if event["type"] == "optional":
                option = next(o for o in event["options"] if o["id"] == result["option"])
                if result["outcome"] not in (("success", "failure") if option["risky"] else ("fixed",)):
                    raise ValueError("Invalid risk result.")
                if result["event"] != state.selected_event or result["option"] != state.selected_option:
                    raise ValueError("Result does not match the selected action.")
            elif result["outcome"] != "fixed" or result["event"] != state.current_forced_event:
                raise ValueError("Invalid forced result.")
        for record in state.event_history:
            if record["kind"] not in ("talent", "forced", "optional") or type(record["day"]) is not int or not 0 <= record["day"] <= state.day:
                raise ValueError("Invalid history entry.")
            if record["kind"] == "talent":
                if record["id"] not in TALENTS:
                    raise ValueError("Unknown talent in history.")
            else:
                event = EVENTS[record["id"]]
                if event["type"] != record["kind"]:
                    raise ValueError("Invalid event type in history.")
                if event["type"] == "optional":
                    option = next(o for o in event["options"] if o["id"] == record["option"])
                    if record["outcome"] not in (("success", "failure") if option["risky"] else ("fixed",)):
                        raise ValueError("Invalid recorded outcome.")
            if set(record["delta"]) - set(STAT_KEYS) or any(type(n) is not int for n in record["delta"].values()):
                raise ValueError("Invalid log effects.")
        for record in state.recent_selected_events:
            if record["id"] not in EVENTS or type(record["day"]) is not int:
                raise ValueError("Invalid cooldown.")
        if not isinstance(state.seen_event_ids, list) or any(e not in EVENTS for e in state.seen_event_ids) or len(set(state.seen_event_ids)) != len(state.seen_event_ids):
            raise ValueError("Invalid seen-event ledger.")
        known = {r["id"] for r in state.event_history if r["kind"] != "talent"}
        known.update(state.optional_candidates)
        if state.current_forced_event:
            known.add(state.current_forced_event)
        if not known <= set(state.seen_event_ids):
            raise ValueError("Seen-event ledger is missing displayed events.")
        drawn = []
        days = []
        for hand in state.optional_draw_history:
            if type(hand["day"]) is not int or not 1 <= hand["day"] <= state.day or len(hand["ids"]) > CONFIG["optional_choices"]:
                raise ValueError("Invalid candidate history.")
            if any(e not in EVENTS or EVENTS[e]["type"] != "optional" for e in hand["ids"]):
                raise ValueError("Invalid candidate history.")
            drawn.extend(hand["ids"])
            days.append(hand["day"])
        if len(set(days)) != len(days) or len(set(drawn)) != len(drawn) or not set(drawn) <= set(state.seen_event_ids):
            raise ValueError("Repeated or unrecorded candidate cards.")
        random.Random().setstate(tuple_tree(state.rng_state))
        return state


class Game:
    def __init__(self, state=None, seed=None):
        self.rng = random.Random(seed)
        self.state = state or GameState()
        if state is not None:
            self.rng.setstate(tuple_tree(state.rng_state))
        else:
            self.state.talent_candidates = self.rng.sample(list(TALENTS), CONFIG["talent_choices"])
            self._sync_rng()

    def _sync_rng(self):
        self.state.rng_state = self.rng.getstate()

    def _require(self, *phases):
        if self.state.phase not in phases:
            raise InvalidAction("Action is not available in phase " + self.state.phase)

    def _apply(self, effects):
        delta = {}
        for stat in STAT_KEYS:
            old = self.state.stats[stat]
            value = max(0, min(CONFIG["stat_max"], old + effects.get(stat, 0)))
            self.state.stats[stat] = value
            if value != old:
                delta[stat] = value - old
        return delta

    def _finish(self, completed=False, event_id=None):
        ending = resolve_ending(self.state.stats, self.state.day, completed)
        if ending:
            self.state.ending = ending
            self.state.phase = "ENDED"
            if ending == "E01":
                self.state.death_event = event_id
        return bool(ending)

    def pick_talent(self, talent_id):
        self._require("TALENT_PICK")
        if talent_id not in self.state.talent_candidates:
            raise InvalidAction("Talent is not in the offered hand.")
        self.state.selected_talent = talent_id
        delta = self._apply(TALENTS[talent_id]["effects"])
        self.state.event_history.append({"kind": "talent", "id": talent_id, "day": 0, "delta": delta})
        self.state.committed_actions.append("talent")
        self.state.day = 1
        self._begin_day()

    def _begin_day(self):
        state = self.state
        state.current_forced_event = None
        state.selected_event = state.selected_option = state.resolved_result = None
        state.optional_candidates = []
        if has_forced_event(state.day, self.rng):
            event_id = draw_forced(state.stats, state.day, self.rng, state.seen_event_ids)
            if event_id is not None:
                action = f"{state.day}:forced"
                if action in state.committed_actions:
                    raise InvalidAction("This forced event has already been settled.")
                state.current_forced_event = event_id
                state.seen_event_ids.append(event_id)
                delta = self._apply(EVENTS[event_id]["effects"])
                state.resolved_result = {"event": event_id, "outcome": "fixed", "delta": delta}
                state.event_history.append({"kind": "forced", "id": event_id, "day": state.day,
                                            "outcome": "fixed", "delta": delta})
                state.committed_actions.append(action)
                state.phase = "FORCED_RESOLVED"
                self._finish(event_id=event_id)
                self._sync_rng()
                return
        self._offer_cards()

    def _offer_cards(self):
        self.state.optional_candidates = draw_optional(self.state.stats, self.state.day,
                                                      self.state.seen_event_ids, self.rng)
        self.state.seen_event_ids.extend(self.state.optional_candidates)
        self.state.optional_draw_history.append({"day": self.state.day, "ids": list(self.state.optional_candidates)})
        self.state.resolved_result = None
        self.state.phase = "OPTIONAL_CARDS" if self.state.optional_candidates else "DAY_COMPLETE"
        self._sync_rng()

    def pick_event(self, event_id):
        self._require("OPTIONAL_CARDS")
        if event_id not in self.state.optional_candidates:
            raise InvalidAction("Event is not in the offered hand.")
        self.state.selected_event = event_id
        self.state.phase = "OPTIONAL_CHOICE"

    def pick_option(self, option_id):
        self._require("OPTIONAL_CHOICE")
        if option_id not in {o["id"] for o in EVENTS[self.state.selected_event]["options"]}:
            raise InvalidAction("Unknown option.")
        self.state.selected_option = option_id

    def confirm_option(self):
        self._require("OPTIONAL_CHOICE")
        state = self.state
        action = f"{state.day}:optional"
        if state.selected_option is None or action in state.committed_actions:
            raise InvalidAction("Select an uncommitted option first.")
        event = EVENTS[state.selected_event]
        option = next(o for o in event["options"] if o["id"] == state.selected_option)
        outcome, effects = resolve_option(option, state.stats, self.rng)
        delta = self._apply(effects)
        state.resolved_result = {"event": event["id"], "option": option["id"], "outcome": outcome, "delta": delta}
        state.event_history.append({"kind": "optional", "id": event["id"], "day": state.day,
                                    "option": option["id"], "outcome": outcome, "delta": delta})
        # Retained for v1 save compatibility; exclusions use seen_event_ids.
        state.recent_selected_events.append({"id": event["id"], "day": state.day})
        state.committed_actions.append(action)
        state.phase = "OPTIONAL_RESOLVED"
        self._finish(event_id=event["id"])
        self._sync_rng()

    def continue_phase(self):
        self._require("FORCED_RESOLVED", "OPTIONAL_RESOLVED", "DAY_COMPLETE")
        if self.state.phase == "FORCED_RESOLVED":
            self._offer_cards()
            if self.state.optional_candidates:
                return
        self._advance_day()

    def _advance_day(self):
        if not self._finish(completed=True):
            self.state.day += 1
            self._begin_day()

    def has_optional_events(self):
        return bool(optional_pool(self.state.stats, self.state.day, self.state.seen_event_ids))
