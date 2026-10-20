# Galactic Misadventures

A bilingual Python desktop game about a seven-day journey through an absurd universe. Choose a talent, take risks, shape four attributes, and discover one of twelve endings.

## Run

Use **Python 3.10+ with Tkinter** on a graphical desktop:

```sh
python main.py
```

On Windows, double-click `start.bat`. Keep `data/` and `assets/` beside the Python files. No third-party packages, network access, or API keys are required.

**For the marker:** `main.py` is the entry point. This is a **Tkinter GUI application** and must run locally, outside the Ed code runner. See [README.txt](README.txt) for complete setup instructions. Custom title fonts are optional; installed system fonts provide a fallback.

## Play

1. Select **New Game**, then choose one of three randomly offered talents.
2. Read each day's forced encounter, if one occurs. Day 3 and Day 7 always have one.
3. Select one of the offered event cards, choose an action, and confirm it. Risky actions show a success chance; their outcome is revealed after confirmation.
4. Continue to the next encounter or day. Reach Day 7 to discover your ending, or become Space Dust if Vitality reaches zero.
5. Browse **Unlocked Endings** from the main menu and try a different route.

There are **10 talents, 56 events (37 optional and 19 forced), and 12 endings**. Vitality, Luck, Fame, and Rationality influence encounters and outcomes. Every event displayed in a run is excluded from later draws in that run, including cards you did not select.

English is the first-launch default. Switch between English and Chinese at any time; the selected language is remembered. Switching languages translates the history without rerolling encounters or outcomes.

## Project structure

```text
Galactic-Misadventures/
|-- main.py                  Desktop GUI and entry point
|-- game.py                  State, actions, and seven-day progression
|-- events.py                Eligibility, weighted draws, and risk rolls
|-- endings.py               Ordered ending selection
|-- save.py                  Validated, atomic local saves
|-- localisation.py          UI translation and history formatting
|-- content.py               JSON loading and content validation
|-- start.bat                Windows launcher
|-- README.txt               Plain-text setup and marking instructions
|-- data/
|   |-- config.json          Rules and probabilities
|   |-- talents.json         Bilingual talents and effects
|   |-- events.json          Bilingual encounters, choices, and effects
|   |-- endings.json         Bilingual endings and ordered conditions
|   `-- ui.json              Bilingual interface text
|-- assets/backgrounds/
|   `-- main-menu-v3.png      Menu artwork
|-- docs/
|   `-- TECHNICAL_NOTES.md    Design and implementation notes
|-- tests/                   Logic, save, content, and GUI checks
`-- tools/                   Optional simulation and screenshot utilities
```

The game loads resources relative to `main.py`, so launching from another working directory is supported. Keep the directory structure intact when submitting or copying the project.

## Saves

Local progress is stored in `save/`, which is excluded from Git:

- `active_save.json` contains the current journey, displayed event IDs, structured history, and random generator state.
- `progress.json` contains unlocked endings, completed journeys, and the language preference.

Closing the game or returning to the menu saves progress. **Continue Game** resumes the current phase. Starting a new game retains the ending collection. To reset everything, close the game and delete `save/`.

Save files use atomic replacement. Unreadable files are preserved as recovery copies rather than silently discarded. Earlier supported saves are migrated when loaded.

## Verification

Run logic and save tests without a desktop window:

```sh
python -m unittest discover -s tests -v
```

Run actual GUI checks with temporary saves:

```sh
python -m tests.ui_smoke
```

Optional screenshots on Windows:

```sh
python -m tests.ui_smoke --screenshots docs/previews
```

Optional reproducible balance simulations:

```sh
python tools/simulate.py --runs 20000 --seed 42
```

Simulation results describe the chosen policies, rather than fixed ending drop rates. The two directed policies inspect hidden numeric effects for design analysis. See [technical notes](docs/TECHNICAL_NOTES.md) for the implementation details.
