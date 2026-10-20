GALACTIC MISADVENTURES
COMP9001 Python Project

START HERE
==========
Entry point: main.py

1. Keep the project folder intact, including data/ and assets/.
2. Install Python 3.10 or newer with Tkinter (Tcl/Tk support).
3. Open a terminal in this folder and run:

   python main.py

On Windows, you can also double-click start.bat.

DESKTOP GUI NOTICE
==================
This is a Tkinter desktop GUI application. It needs a graphical desktop
and should be run locally by the tutor, outside the Ed code runner.
It uses only Python's standard library. No pip packages, network access,
API keys, audio/video software, or separately installed game engine are
required. Tkinter is included with the standard Windows Python installer
when Tcl/Tk support is enabled. If Tkinter is missing on another system,
use a Python installation that includes it.

The menu artwork is included. Custom title fonts are optional: the game
uses an installed font when available and falls back to a system font.

HOW TO PLAY
===========
Choose New Game, select one of three talents, and make decisions during
a seven-day space journey. Choose an event card, select an action, then
confirm it. Risky actions display their success chance. Vitality reaching
zero ends the journey immediately. Otherwise, your final attributes
determine one of twelve endings after Day 7.

The game contains 10 talents, 37 optional events and 19 forced events.
An event shown during a run cannot appear again in that run, including
cards you did not choose. Day 3 and Day 7 always include a forced event.

English is the default on first launch. The language button switches
between English and Chinese, and your preference is remembered.

SAVES
=====
Progress is stored in save/ beside main.py. Continue Game resumes an
unfinished journey. New Game retains the ending collection.

For a completely fresh start, close the game and delete save/.
Do not include personal save files when submitting or distributing it.

FILES TO INCLUDE
================
Include all seven Python files in the project root, all five JSON files
in data/, and assets/backgrounds/main-menu-v3.png. Preserve their relative
paths. README.md provides a file map; tests/ and tools/ contain optional
verification utilities. All Python source files are supplied in the folder.

TESTS
=====
Logic and save tests:
   python -m unittest discover -s tests -v

Desktop GUI checks (use temporary saves):
   python -m tests.ui_smoke

Further implementation details are in docs/TECHNICAL_NOTES.md.
