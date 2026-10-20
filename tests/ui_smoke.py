"""Exercise real Tk widgets using temporary saves; optionally export previews.

python -m tests.ui_smoke --screenshots docs/previews
Needs a working desktop display, unlike the ordinary unit tests.
"""

import argparse
from pathlib import Path
import random
import re
from tempfile import TemporaryDirectory
import tkinter as tk

from content import ENDINGS, EVENTS, TALENTS
from game import Game
from main import App, ScrollPanel
from localisation import effect_text
from tests.test_game import snapshot
from tools.capture_window import capture_window


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    errors, phases = [], set()
    with TemporaryDirectory() as directory:
        app = App(directory)
        app.report_callback_exception = lambda *error: errors.append(error)

        def check(name):
            app.update()
            assert not errors, errors
            for panel in app.panels.values():
                assert panel.inner.winfo_width() <= panel.canvas.winfo_width() + 1, (name, "horizontal overflow")
            if app.language == "en":
                for widget in descendants(app):
                    if isinstance(widget, (tk.Label, tk.Button, tk.Radiobutton)):
                        value = widget.cget("text")
                        if isinstance(widget, tk.Button) and value == "\u4e2d\u6587":
                            continue  # the language-switch control names its target language
                        assert not re.search(r"[\u3400-\u9fff]", value), (name, value)
            if app.screen == "talent":
                cards = app.panels["talent"].inner.grid_slaves()
                choose_buttons = [w for w in descendants(app) if isinstance(w, tk.Button) and w.cget("text") == app.t("talent_choose")]
                assert len(choose_buttons) == 3
                assert len({w.winfo_rooty() for w in choose_buttons}) == 1, "Talent buttons must align"
                assert len({w.winfo_height() for w in choose_buttons}) == 1
                for card in cards:
                    for heading in (w for w in card.grid_slaves() if int(w.grid_info()["row"]) <= 2):
                        assert heading.cget("anchor") == "center", "Talent headings must be centred"
                    bonus = next(w for w in card.grid_slaves() if int(w.grid_info()["row"]) == 4)
                    assert bonus.cget("anchor") == "center"
                values = {w.cget("text") for w in descendants(app) if isinstance(w, tk.Label)}
                assert all(effect_text(TALENTS[t]["effects"], app.language) in values for t in app.game.state.talent_candidates)
            if args.screenshots is not None:
                capture_window(app, args.screenshots / (name + ".png"))

        assert app.language == "en", "First launch should use English"
        app.switch_language()
        check("01-menu-zh")
        buttons = [w for w in descendants(app) if isinstance(w, tk.Button)]
        assert next(w for w in buttons if w.cget("text") == app.t("continue_game")).cget("state") == "disabled"
        app.switch_language()
        check("02-menu-en")
        app.switch_language()
        app.new_game()
        check("03-talents-zh")
        app.switch_language()
        check("04-talents-en")
        # A fixed game seed makes preview selection repeatable while preserving real callbacks.
        app.game = Game(seed=42)
        app.act(lambda: app.game.pick_talent(app.game.state.talent_candidates[0]))
        check("05-game-cards-en")
        before = snapshot(app.game)
        app.switch_language()
        assert before == snapshot(app.game)
        check("06-game-cards-zh")
        app.menu()
        app.continue_game()
        assert before == snapshot(app.game)
        strategy = random.Random(42)
        captured_choice = captured_forced = False
        while app.game.state.phase != "ENDED":
            state = app.game.state
            phases.add(state.phase)
            if state.phase == "OPTIONAL_CARDS":
                event_id = strategy.choice(state.optional_candidates)
                app.act(lambda: app.game.pick_event(event_id))
            elif state.phase == "OPTIONAL_CHOICE":
                app.update()
                radio = next(w for w in descendants(app) if isinstance(w, tk.Radiobutton))
                before_stats, before_rng = dict(state.stats), app.game.rng.getstate()
                radio.invoke()
                assert before_stats == state.stats and before_rng == app.game.rng.getstate()
                assert app.confirm_button.cget("state") == "normal"
                if not captured_choice:
                    check("07-event-choice-zh")
                    app.switch_language()
                    check("08-event-choice-en")
                    app.switch_language()
                    captured_choice = True
                old_confirm = app.confirm_button
                old_confirm.invoke()
                # The old control has been destroyed. The engine rejects replay too.
                app.update()
            else:
                before_day = state.day
                last_event = state.phase != "FORCED_RESOLVED" or not app.game.has_optional_events()
                expected = ("see_ending" if before_day == 7 else "next_day") if last_event else "continue"
                actions = [w for w in descendants(app.panels["event"].inner) if isinstance(w, tk.Button)]
                assert len(actions) == 1 and actions[0].cget("text") == app.t(expected)
                if state.phase == "FORCED_RESOLVED" and not captured_forced:
                    check("09-forced-result-zh")
                    captured_forced = True
                # Use the real result button, checking there is no extra rest page.
                actions[0].invoke()
                if last_event and app.game.state.phase != "ENDED":
                    assert app.game.state.day == before_day + 1
                elif not last_event:
                    assert app.game.state.day == before_day
            app.update()
            assert not errors, errors
            hands = [e for h in app.game.state.optional_draw_history for e in h["ids"]]
            assert len(hands) == len(set(hands))
        check("10-ending-zh")
        app.switch_language()
        check("11-ending-en")
        app.menu()
        app.gallery()
        for count in (0, 8, 12):
            app.store.progress["unlocked_endings"] = list(ENDINGS)[:count]
            app.positions["gallery"] = 0
            app.render(capture=False)
            check(f"12-gallery-{count}-en")
            assert len(app.panels["gallery"].inner.grid_slaves()) == 12
            app.panels["gallery"].canvas.yview_moveto(.5)
            app.update()
            position = app.panels["gallery"].canvas.yview()[0]
            app.switch_language()
            app.update()
            # Language changes card heights; compare a fractional scroll position.
            assert abs(app.panels["gallery"].canvas.yview()[0] - position) < .12
            app.switch_language()
            app.update()
        app.geometry("900x640")
        app.positions["gallery"] = 0
        app.render(capture=False)
        check("13-gallery-small-en")
        app.game = Game(seed=42)
        app.screen = "talent"
        app.render()
        check("16-talents-small-en")
        app.switch_language()
        check("17-talents-small-zh")
        app.switch_language()
        # Confirm long English choices fit a scrollable panel on a small screen.
        app.game = Game(seed=42)
        app.game.pick_talent(app.game.state.talent_candidates[0])
        if app.game.state.phase == "FORCED_RESOLVED":
            app.game.continue_phase()
        app.game.state.optional_candidates = ["D08", "D02", "N01"]
        app.game.state.seen_event_ids = list(set(app.game.state.seen_event_ids) | {"D08", "D02", "N01"})
        app.game.pick_event("D08")
        app.screen = "game"
        app.render()
        check("14-long-choice-small-en")
        # A fatal event opens the ending page immediately with the event name.
        app.game.state.stats["vitality"] = 1
        app.game.state.selected_event = "N01"
        app.game.pick_option("C")
        app.act(app.game.confirm_option)
        assert app.screen == "ending" and app.game.state.ending == "E01"
        check("15-death-small-en")
        app.destroy()
    assert {"FORCED_RESOLVED", "OPTIONAL_CARDS", "OPTIONAL_CHOICE", "OPTIONAL_RESOLVED"} <= phases
    print("GUI checks passed: English without Chinese content, centred talent headings and bonuses,")
    print("aligned talent buttons, direct next-day controls, no repeated cards, seven-day journey,")
    print("menu/resume, death, gallery 0/8/12, scrolling, and 900x640 layout.")


if __name__ == "__main__":
    main()
