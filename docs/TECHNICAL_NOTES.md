# Technical notes

## Runtime and dependencies

The game uses Python's standard library only. Tkinter supplies the desktop interface and PNG decoding; no external graphics package is required. A graphical desktop and a Python installation with Tcl/Tk support are required. The Windows launcher delegates to `python main.py`.

The menu artwork is bundled in `assets/backgrounds/main-menu-v3.png`. Other backgrounds, controls, attribute bars, and ending borders are drawn by the interface. Image scaling uses nearest-neighbour sampling to preserve pixel edges. Optional installed title fonts have system-font fallbacks.

## Separation of responsibilities

`game.py` owns the state machine and enforces the legal actions for each phase. It contains no GUI or disk operations. `events.py` handles eligibility, weighted sampling, and risk rolls. `endings.py` resolves overlapping conditions in a fixed order. `main.py` presents this state through Tkinter widgets and calls the engine when the player acts.

The five JSON files in `data/` hold the game settings, bilingual content, and interface text. `content.py` loads and validates them. `localisation.py` formats translated history from structured records, allowing a language switch without changing game state.

## Random choices and event exclusions

The engine uses an explicit `random.Random` instance. Candidate events are filtered by day, attribute requirements, and the set of events already shown. Sampling first chooses an available polarity using the configured Luck band, then an event using its weight and applicable tag bonuses. Displayed cards are excluded even when the player chooses a different card. Forced events are also excluded after appearing.

Risky actions are rolled only on confirmation. Repeated or out-of-phase actions are rejected. Attribute updates are clamped to the configured range. Death resolves immediately; other endings resolve after completion of Day 7.

## Persistence and recovery

The state is represented by a dataclass and serialised to JSON, including the random generator state. Restoring a save resumes the same phase and random sequence. Structured event records retain IDs and outcomes rather than pretranslated prose.

`save.py` validates loaded data and writes through a temporary file followed by atomic replacement. A completed run has a unique ID, preventing repeated ending settlement after a restart. Corrupted files are preserved for recovery. Personal saves are excluded from the repository.

## Verification

Unit tests exercise event eligibility, probability boundaries, non-repetition, confirmation, ending priority, save restoration, migration, and write failures. A content checksum fixture records the verified game data and artwork so that submission cleanup cannot silently change text, settings, or assets. JSON checksums normalise Windows line endings to LF so that Git checkout conventions do not produce false failures on another computer. Artwork is checked byte for byte. Intentional future content changes should update that fixture after review.

The GUI check uses temporary saves and exercises both languages, aligned talent controls, next-day navigation, a complete journey, death, the ending collection, and a smaller window. Optional screenshot capture uses the Windows API and is not imported by the game.

The simulator runs three reproducible choice policies against the same engine. The directed policies can inspect hidden outcome effects and are intended for design analysis, not predictions of ordinary player behaviour.
