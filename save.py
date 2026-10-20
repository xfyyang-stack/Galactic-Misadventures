"""Validated local JSON saves, atomic replacement, and idempotent run settlement."""

from datetime import datetime
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile

from content import CONFIG, ENDINGS, ROOT
from game import GameState


class SaveError(OSError):
    pass


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def default_progress():
    return {"version": 1, "unlocked_endings": [], "total_runs": 0,
            "highest_day_reached": 0, "ending_unlock_count": 0,
            "preferred_language": "en", "completed_run_ids": []}


def validate_progress(progress):
    if progress["version"] != 1 or progress["preferred_language"] not in ("zh", "en"):
        raise ValueError("Unsupported progress format.")
    ids = progress["unlocked_endings"]
    if not isinstance(ids, list) or len(set(ids)) != len(ids) or any(i not in ENDINGS for i in ids):
        raise ValueError("Invalid unlocked endings.")
    if any(type(progress[k]) is not int or progress[k] < 0
           for k in ("total_runs", "highest_day_reached", "ending_unlock_count")):
        raise ValueError("Invalid progress counters.")
    if progress["highest_day_reached"] > CONFIG["max_days"] or progress["ending_unlock_count"] != len(ids):
        raise ValueError("Invalid progress counters.")
    completed = progress["completed_run_ids"]
    if not isinstance(completed, list) or any(not isinstance(i, str) for i in completed) or len(set(completed)) != len(completed):
        raise ValueError("Invalid run ledger.")
    if progress["total_runs"] != len(completed):
        raise ValueError("Inconsistent run ledger.")
    return progress


class SaveStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else ROOT / "save"
        self.warnings = []
        self.progress = self._read("progress.json", validate_progress) or default_progress()

    def _read(self, name, validate):
        path = self.directory / name
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as error:
            raise SaveError(str(error)) from error
        try:
            return validate(json.loads(raw))
        except (ValueError, TypeError, KeyError, AttributeError, StopIteration, OverflowError) as error:
            # Preserve the original before falling back; never silently erase it.
            backup = path.with_name(path.stem + ".invalid-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json")
            try:
                shutil.copy2(path, backup)
            except OSError as backup_error:
                raise SaveError(str(backup_error)) from backup_error
            self.warnings.append((name, backup.name, str(error)))
            return None

    def load_active(self):
        state = self._read("active_save.json", GameState.from_dict)
        if state is not None:
            # Recover a crash between writing ENDED and updating the progress ledger.
            self._record_progress(state)
        return state

    def _write(self, name, data):
        try:
            atomic_json(self.directory / name, data)
        except OSError as error:
            raise SaveError(str(error)) from error

    def _record_progress(self, state):
        progress = deepcopy(self.progress)
        changed = False
        if state.day > progress["highest_day_reached"]:
            progress["highest_day_reached"] = state.day
            changed = True
        if state.phase == "ENDED" and state.run_id not in progress["completed_run_ids"]:
            progress["completed_run_ids"].append(state.run_id)
            progress["total_runs"] += 1
            if state.ending not in progress["unlocked_endings"]:
                progress["unlocked_endings"].append(state.ending)
                progress["unlocked_endings"].sort()
            progress["ending_unlock_count"] = len(progress["unlocked_endings"])
            changed = True
        if changed:
            self._write("progress.json", progress)
            self.progress = progress

    def persist(self, state):
        self._write("active_save.json", state.to_dict())
        self._record_progress(state)

    def set_language(self, language):
        if language not in ("zh", "en"):
            raise ValueError("Unsupported language.")
        progress = dict(self.progress, preferred_language=language)
        self._write("progress.json", progress)
        self.progress = progress
