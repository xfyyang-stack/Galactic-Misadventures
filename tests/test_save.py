"""Atomic save behaviour, corrupted-file recovery, and exactly-once settlement."""

import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from game import Game
from localisation import history_text
from save import SaveError, SaveStore
from tests.test_game import advance, snapshot


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.store = SaveStore(self.path)

    def ended_game(self, seed=10):
        game, choices = Game(seed=seed), random.Random(seed)
        while game.state.phase != "ENDED":
            advance(game, choices)
        return game

    def test_round_trip_at_each_phase(self):
        game, choices = Game(seed=7), random.Random(7)
        while True:
            self.store.persist(game.state)
            resumed = SaveStore(self.path).load_active()
            self.assertEqual(snapshot(game), json.loads(json.dumps(resumed.to_dict())))
            if game.state.phase == "ENDED":
                break
            advance(game, choices)

    def test_progress_survives_new_game_and_language(self):
        game = self.ended_game()
        self.store.persist(game.state)
        self.store.set_language("en")
        self.store.persist(Game(seed=3).state)
        store = SaveStore(self.path)
        self.assertEqual(store.progress["unlocked_endings"], [game.state.ending])
        self.assertEqual(store.progress["preferred_language"], "en")
        self.assertEqual(store.progress["total_runs"], 1)

    def test_ending_settlement_is_idempotent(self):
        game = self.ended_game()
        for _ in range(3):
            self.store.persist(game.state)
            self.store = SaveStore(self.path)
            self.store.load_active()
        self.assertEqual(self.store.progress["total_runs"], 1)
        self.assertEqual(self.store.progress["ending_unlock_count"], 1)
        another = self.ended_game()
        self.store.persist(another.state)
        self.assertEqual(self.store.progress["total_runs"], 2)
        self.assertEqual(self.store.progress["ending_unlock_count"], 1)

    def test_crash_between_active_and_progress_recovers(self):
        game = self.ended_game()
        with patch.object(self.store, "_record_progress", side_effect=SaveError("interrupted")):
            with self.assertRaises(SaveError):
                self.store.persist(game.state)
        resumed = SaveStore(self.path)
        resumed.load_active()
        self.assertEqual(resumed.progress["total_runs"], 1)
        resumed.load_active()
        self.assertEqual(resumed.progress["total_runs"], 1)

    def test_failed_progress_write_can_be_retried(self):
        game = self.ended_game()
        with patch.object(self.store, "_write", side_effect=SaveError("disk full")):
            with self.assertRaises(SaveError):
                self.store._record_progress(game.state)
        self.assertEqual(self.store.progress["total_runs"], 0)
        self.store._record_progress(game.state)
        self.assertEqual(self.store.progress["total_runs"], 1)

    def test_atomic_write_failure_preserves_previous_active(self):
        first, second = Game(seed=1), Game(seed=2)
        self.store.persist(first.state)
        with patch("save.os.replace", side_effect=PermissionError("in use")):
            with self.assertRaises(SaveError):
                self.store.persist(second.state)
        self.assertEqual(self.store.load_active().run_id, first.state.run_id)
        self.assertFalse(list(self.path.glob("*.tmp")))

    def test_corrupt_save_is_preserved(self):
        (self.path / "active_save.json").write_text('{"day":', encoding="utf-8")
        self.assertIsNone(self.store.load_active())
        self.assertEqual(len(self.store.warnings), 1)
        backups = list(self.path.glob("active_save.invalid-*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"day":')

    def test_corrupt_progress_is_preserved(self):
        (self.path / "progress.json").write_text('{"unlocked_endings":["E99"]}', encoding="utf-8")
        store = SaveStore(self.path)
        self.assertEqual(store.progress["unlocked_endings"], [])
        self.assertTrue(list(self.path.glob("progress.invalid-*.json")))

    def test_history_retranslates_after_resume(self):
        game = self.ended_game()
        self.store.persist(game.state)
        state = self.store.load_active()
        for record in state.event_history:
            zh = history_text(record, "zh")
            en = history_text(record, "en")
            self.assertTrue(all(zh) and all(en))
            self.assertNotEqual(zh, en)


if __name__ == "__main__":
    unittest.main()
