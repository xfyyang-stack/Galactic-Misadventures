# Entry point: run `python main.py` with Python 3.10+ and Tkinter on a desktop.
"""Tkinter desktop game. No third-party packages are required."""

import sys
import tkinter as tk
from tkinter import font as tkfont, messagebox

from content import CONFIG, ENDINGS, EVENTS, ROOT, STAT_KEYS, TALENTS
from events import risk_probability
from game import Game, InvalidAction
from localisation import effect_text, history_text, text
from save import SaveError, SaveStore

BLUE = "#E5F2FC"
YELLOW = "#FFF5D8"
INK = "#253D58"
MUTED = "#5D7084"
LINE = "#91A9BF"
ACCENT = "#416D9E"
COLORS = {"vitality": "#E97979", "luck": "#E5B747", "fame": "#B38ADC", "rationality": "#5AB8BA"}


def label(parent, value, size=11, bold=False, color=INK, bg=None, **kwargs):
    selected_font = kwargs.pop("font", (parent.winfo_toplevel().ui_font, size, "bold" if bold else "normal"))
    widget = tk.Label(parent, text=value, font=selected_font,
                      bg=bg or parent.cget("bg"), fg=color, bd=0, **kwargs)
    return widget


def wrapping_label(parent, value, size=11, bold=False, color=INK, **kwargs):
    kwargs.setdefault("justify", "left")
    kwargs.setdefault("anchor", "w")
    widget = label(parent, value, size, bold, color, **kwargs)
    widget.bind("<Configure>", lambda e: widget.configure(wraplength=max(80, e.width - 4)))
    return widget


class ScrollPanel(tk.Frame):
    """Width-tracking canvas with a local mouse wheel and no horizontal overflow."""

    def __init__(self, parent, bg=BLUE):
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, bd=0, highlightthickness=0, yscrollincrement=22)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._resize)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=max(1, event.width))

    def wheel(self, delta):
        if self.inner.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(delta, "units")


class MenuBackdrop(tk.Canvas):
    """Display the menu art with sharp nearest-neighbour scaling, using Tk only."""

    def __init__(self, parent):
        super().__init__(parent, bg=BLUE, highlightthickness=0, bd=0)
        source = tk.PhotoImage(master=self, file=str(ROOT / "assets" / "backgrounds" / "main-menu-v3.png"))
        self.source_width, self.source_height = source.width(), source.height()
        # Tk decodes PNG. Its binary PPM export lets us resize for display without
        # adding Pillow, changing the original PNG, or blurring the pixel edges.
        ppm = self.tk.call(str(source), "data", "-format", "ppm")
        header, dimensions, maximum, self.pixels = ppm.split(b"\n", 3)
        if header != b"P6" or maximum != b"255":
            raise ValueError("Unexpected Tk image format.")
        self.background_item = self.create_image(0, 0, anchor="nw")
        self.photo = None
        self.last_size = None
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        width, height = max(1, event.width), max(1, event.height)
        if self.last_size == (width, height):
            return
        self.last_size = (width, height)
        scale = max(width / self.source_width, height / self.source_height)
        left = (self.source_width - width / scale) / 2
        top = (self.source_height - height / scale) / 2
        columns = [min(self.source_width - 1, max(0, int(left + (x + .5) / scale))) * 3 for x in range(width)]
        rows = {}
        image_rows = []
        stride = self.source_width * 3
        for y in range(height):
            source_y = min(self.source_height - 1, max(0, int(top + (y + .5) / scale)))
            if source_y not in rows:
                start = source_y * stride
                line = self.pixels[start:start + stride]
                rows[source_y] = b"".join(line[x:x + 3] for x in columns)
            image_rows.append(rows[source_y])
        data = f"P6\n{width} {height}\n255\n".encode("ascii") + b"".join(image_rows)
        self.photo = tk.PhotoImage(master=self, data=data, format="ppm")
        self.itemconfigure(self.background_item, image=self.photo)
        self.tag_lower(self.background_item)


class PixelBar(tk.Canvas):
    def __init__(self, parent, value, color):
        super().__init__(parent, height=22, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.value, self.color = value, color
        self.bind("<Configure>", self._draw)

    def _draw(self, event):
        self.delete("all")
        width = max(30, event.width - 2)
        self.create_rectangle(1, 2, width, 20, fill=YELLOW, outline=INK, width=2)
        cell = (width - 6) / CONFIG["stat_max"]
        for index in range(CONFIG["stat_max"]):
            x = 4 + index * cell
            self.create_rectangle(x, 5, x + max(1, cell - 2), 17,
                                  fill=self.color if index < self.value else "#D4DFE5", outline="")


class OrnateFrame(tk.Frame):
    """A code-drawn, ending-specific double border; the interior stays solid."""

    PALETTES = ["#687A95", "#9870B5", "#4B967E", "#C9973C", "#B77A55", "#4D8FA0",
                "#B59B37", "#8194B8", "#7B9A95", "#8B73A4", "#A4787F", "#9C9176"]

    def __init__(self, parent, ending_id):
        super().__init__(parent, bg=YELLOW)
        self.edge = self.PALETTES[int(ending_id[1:]) - 1]
        self.canvas = tk.Canvas(self, bg=YELLOW, highlightthickness=0, bd=0)
        self.canvas.place(relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=YELLOW)
        self.inner.pack(fill="both", expand=True, padx=30, pady=30)
        self.bind("<Configure>", self._draw)

    def _draw(self, event):
        c, w, h = self.canvas, event.width, event.height
        c.delete("all")
        for inset, width, color in [(3, 3, self.edge), (10, 1, "#C5A455"), (15, 1, self.edge)]:
            c.create_rectangle(inset, inset, w - inset, h - inset, outline=color, width=width)
        for x, y in [(14, 14), (w - 14, 14), (14, h - 14), (w - 14, h - 14)]:
            c.create_polygon(x, y - 9, x + 9, y, x, y + 9, x - 9, y,
                             fill=YELLOW, outline=self.edge, width=2)
        for x in (w / 2 - 20, w / 2, w / 2 + 20):
            c.create_polygon(x, 4, x + 4, 10, x, 16, x - 4, 10,
                             fill="#D8B767", outline=self.edge)


class App(tk.Tk):
    def __init__(self, save_directory=None):
        super().__init__()
        self.withdraw()
        families = set(tkfont.families(self))
        self.ui_font = next((f for f in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Arial") if f in families), "TkDefaultFont")
        self.title_fonts = {"zh": "\u4f18\u8bbe\u6807\u9898\u9ed1" if "\u4f18\u8bbe\u6807\u9898\u9ed1" in families else self.ui_font,
                            "en": "Agency FB" if "Agency FB" in families else self.ui_font}
        self.option_add("*Font", (self.ui_font, 11))
        self.configure(bg=BLUE)
        self.title("Galactic Misadventures")
        width = min(1160, self.winfo_screenwidth() - 70)
        height = min(740, self.winfo_screenheight() - 90)
        self.geometry(f"{width}x{height}+{(self.winfo_screenwidth()-width)//2}+25")
        self.minsize(880, 600)
        self.store = SaveStore(save_directory)
        state = self.store.load_active()
        self.game = Game(state) if state is not None else None
        self.language = self.store.progress["preferred_language"]
        self.screen = "menu"
        self.epoch = 0
        self.positions = {}
        self.panels = {}
        self.save_failed = False
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<Button-4>", lambda e: self._wheel(e, -3), add="+")
        self.bind_all("<Button-5>", lambda e: self._wheel(e, 3), add="+")
        self.render()
        self.deiconify()
        if self.store.warnings:
            self.after(150, self._show_load_warning)

    def t(self, key, **values):
        return text(key, self.language, **values)

    def title_font(self, size, language=None):
        language = language or self.language
        return (self.title_fonts[language], size, "normal" if language == "zh" else "bold")

    def _show_load_warning(self):
        files = "\n".join(f"{name} → {backup}" for name, backup, _ in self.store.warnings)
        messagebox.showwarning(self.t("load_warning"), self.t("load_warning_text", files=files), parent=self)

    def _wheel(self, event, delta=None):
        widget = self.winfo_containing(event.x_root, event.y_root)
        units = delta if delta is not None else (-3 if event.delta > 0 else 3)
        while widget is not None:
            if isinstance(widget, ScrollPanel):
                widget.wheel(units)
                return "break"
            widget = widget.master

    def button(self, parent, value, command, primary=False, disabled=False, **kwargs):
        epoch = self.epoch

        def guarded():
            if epoch == self.epoch:
                command()

        kwargs.setdefault("padx", 16)
        kwargs.setdefault("pady", 9)
        widget = tk.Button(parent, text=value, command=guarded, bg=ACCENT if primary else YELLOW,
                           fg="#FFFFFF" if primary else INK, activebackground="#CCDFF0",
                           activeforeground=INK, relief="solid", bd=1, highlightthickness=0,
                           cursor="hand2", disabledforeground="#9AA5AC",
                           font=(self.ui_font, 11, "bold" if primary else "normal"), **kwargs)
        if disabled:
            widget.configure(state="disabled", cursor="arrow")
        return widget

    def _save(self):
        try:
            if self.game is not None:
                self.store.persist(self.game.state)
            self.save_failed = False
            return True
        except SaveError as error:
            self.save_failed = True
            messagebox.showerror(self.t("save_error"), self.t("save_error_text", error=str(error)), parent=self)
            return False

    def act(self, command):
        try:
            command()
        except InvalidAction:
            return
        self._save()
        self.positions["event"] = 0
        self.positions["log"] = 1
        if self.game.state.phase == "ENDED":
            self.screen = "ending"
        elif self.game.state.phase == "TALENT_PICK":
            self.screen = "talent"
        else:
            self.screen = "game"
        self.render(capture=False)

    def new_game(self):
        if self.game is not None and self.game.state.phase != "ENDED":
            if not messagebox.askyesno(self.t("overwrite_title"), self.t("overwrite_text"), parent=self):
                return
        self.game = Game()
        self.positions = {}
        self._save()
        self.screen = "talent"
        self.render(capture=False)

    def continue_game(self):
        if self.game is None or self.game.state.phase == "ENDED":
            return
        self.screen = "talent" if self.game.state.phase == "TALENT_PICK" else "game"
        self.render()

    def menu(self):
        if self._save():
            self.screen = "menu"
            self.render()

    def gallery(self):
        self.screen = "gallery"
        self.render()

    def close(self):
        if self._save():
            self.destroy()

    def switch_language(self):
        language = "en" if self.language == "zh" else "zh"
        try:
            self.store.set_language(language)
        except SaveError as error:
            messagebox.showerror(self.t("save_error"), str(error), parent=self)
            return
        self.language = language
        self.render()

    def scroll_panel(self, parent, key, bg=BLUE):
        panel = ScrollPanel(parent, bg)
        self.panels[key] = panel
        return panel

    def render(self, capture=True):
        if capture:
            for key, panel in self.panels.items():
                self.positions[key] = panel.canvas.yview()[0]
        previous_page = getattr(self, "page", None)
        self.panels = {}
        self.epoch += 1
        # Build underneath the visible page, keeping its pixels on screen until
        # the replacement has completed layout, wrapping, and background drawing.
        self.page = tk.Frame(self, bg=BLUE)
        self.page.place(x=0, y=0, relwidth=1, relheight=1)
        if previous_page is not None:
            self.page.lower(previous_page)
        self.title(self.t("title"))
        if self.screen == "menu":
            self.render_menu()
        else:
            header = tk.Frame(self.page, bg=BLUE)
            header.pack(fill="x", padx=24, pady=(16, 12))
            self.button(header, "English" if self.language == "zh" else "中文", self.switch_language).pack(side="right")
            self.button(header, self.t("back_menu"), self.menu).pack(side="right", padx=(0, 8))
            label(header, self.t("title"), 15, True).pack(side="left")
            self.body = tk.Frame(self.page, bg=BLUE)
            self.body.pack(fill="both", expand=True, padx=24, pady=(0, 20))
            getattr(self, "render_" + self.screen)()
        self.update_idletasks()
        for key, panel in self.panels.items():
            panel.canvas.yview_moveto(self.positions.get(key, 1 if key == "log" else 0))
        self.update_idletasks()
        self.page.lift()
        self.update_idletasks()
        if previous_page is not None:
            previous_page.destroy()

    def render_menu(self):
        canvas = MenuBackdrop(self.page)
        canvas.pack(fill="both", expand=True)
        self.menu_canvas = canvas
        title = canvas.create_text(0, 0, text=self.t("title"), fill=INK, justify="center")
        tagline = canvas.create_text(0, 0, text=self.t("tagline"), fill=INK,
                                     font=self.title_font(18), justify="center")
        language = self.button(canvas, "English" if self.language == "zh" else "中文", self.switch_language)
        language_item = canvas.create_window(0, 0, window=language, anchor="ne")
        buttons = []
        active = self.game is not None and self.game.state.phase != "ENDED"
        for key, command, primary, disabled in [
            ("new_game", self.new_game, True, False),
            ("continue_game", self.continue_game, False, not active),
            ("gallery", self.gallery, False, False),
            ("quit", self.close, False, False),
        ]:
            button = self.button(canvas, self.t(key), command, primary, disabled)
            buttons.append(canvas.create_window(0, 0, window=button, height=46))
        note = canvas.create_text(0, 0, text=self.t("menu_note"), fill=INK,
                                  font=(self.ui_font, 10), justify="center")
        p = self.store.progress
        progress = canvas.create_text(0, 0, text=self.t("menu_stats", runs=p["total_runs"], count=len(p["unlocked_endings"])),
                                      fill=INK, font=(self.ui_font, 10), justify="center")

        def arrange(event):
            width, height = event.width, event.height
            title_font = tkfont.Font(self, font=self.title_font(48))
            while title_font.measure(self.t("title")) > width * .84 and title_font.cget("size") > 24:
                title_font.configure(size=title_font.cget("size") - 1)
            title_size = title_font.cget("size")
            canvas.itemconfigure(title, font=self.title_font(title_size))
            canvas.coords(title, width / 2, height * .19)
            canvas.coords(tagline, width / 2, height * .30)
            canvas.itemconfigure(tagline, width=width * .82, font=self.title_font(round(title_size * 18 / 48)))
            canvas.coords(language_item, width - 24, 16)
            for i, item in enumerate(buttons):
                canvas.coords(item, width / 2, height * .43 + i * 58)
                canvas.itemconfigure(item, width=min(330, width * .29))
            canvas.coords(note, width / 2, height * .43 + 4 * 58 + 6)
            canvas.coords(progress, width / 2, height * .43 + 4 * 58 + 32)
            canvas.itemconfigure(progress, width=width * .65)

        canvas.bind("<Configure>", arrange, add="+")

    def render_talent(self):
        label(self.body, self.t("talent_heading"), 23, True).pack(anchor="w", pady=(10, 8))
        wrapping_label(self.body, self.t("talent_note"), 11, color=MUTED).pack(fill="x", pady=(0, 18))
        panel = self.scroll_panel(self.body, "talent")
        panel.pack(fill="both", expand=True)
        row = panel.inner
        for i, talent_id in enumerate(self.game.state.talent_candidates):
            row.columnconfigure(i, weight=1, uniform="talents")
            talent = TALENTS[talent_id]
            card = tk.Frame(row, bg=YELLOW, highlightbackground=LINE, highlightthickness=1, padx=18, pady=20)
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 7, 7))
            card.columnconfigure(0, weight=1)
            card.rowconfigure(3, weight=1)
            label(card, talent_id, 10, True, color=MUTED, anchor="center").grid(row=0, column=0, sticky="ew", pady=(0, 12))
            wrapping_label(card, talent["title"][self.language], 18, True, anchor="center", justify="center").grid(row=1, column=0, sticky="ew", pady=(0, 6))
            if self.language == "zh":
                wrapping_label(card, talent["title"]["en"], 12, color=MUTED, anchor="center", justify="center").grid(row=2, column=0, sticky="ew", pady=(0, 14))
            wrapping_label(card, talent["description"][self.language], 11, anchor="center", justify="center").grid(row=3, column=0, sticky="new", pady=(14, 20))
            wrapping_label(card, effect_text(talent["effects"], self.language), 11, color=ACCENT,
                           anchor="center", justify="center").grid(row=4, column=0, sticky="ew", pady=(0, 12))
            self.button(card, self.t("talent_choose"), lambda tid=talent_id: self.act(lambda: self.game.pick_talent(tid)), True,
                        wraplength=190).grid(row=5, column=0, sticky="ew", pady=(10, 0))

    def render_stats(self, parent, compact=False):
        for stat in STAT_KEYS:
            row = tk.Frame(parent, bg=parent.cget("bg"))
            row.pack(fill="x", pady=(6, 0) if compact else (12, 0))
            label(row, self.t(stat), 10 if compact else 12, True).pack(side="left")
            label(row, f"{self.game.state.stats[stat]} / {CONFIG['stat_max']}", 11, True).pack(side="right")
            PixelBar(parent, self.game.state.stats[stat], COLORS[stat]).pack(fill="x", pady=(4, 0))

    def render_game(self):
        self.body.columnconfigure(0, weight=35, uniform="game")
        self.body.columnconfigure(1, weight=65, uniform="game")
        self.body.rowconfigure(0, weight=1)
        left_panel = self.scroll_panel(self.body, "stats")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        left = left_panel.inner
        label(left, self.t("journey"), 12, True, color=MUTED).pack(anchor="w", pady=(12, 8))
        label(left, self.t("day", day=self.game.state.day, max=CONFIG["max_days"]), 25, True).pack(anchor="w", pady=(0, 14))
        self.render_stats(left)
        label(left, self.t("talent_label"), 10, color=MUTED).pack(anchor="w", pady=(30, 6))
        talent = TALENTS[self.game.state.selected_talent]
        wrapping_label(left, talent["title"][self.language], 13, True).pack(fill="x")
        wrapping_label(left, self.t("stats_note"), 10, color=MUTED).pack(fill="x", pady=(20, 16))
        label(left, self.t("days_caption"), 10, color=MUTED).pack(anchor="w", pady=(4, 8))
        timeline = tk.Frame(left, bg=BLUE)
        timeline.pack(fill="x")
        for day in range(1, CONFIG["max_days"] + 1):
            label(timeline, str(day), 11, True, bg=ACCENT if day <= self.game.state.day else YELLOW,
                  color="#FFFFFF" if day <= self.game.state.day else MUTED, width=3, pady=6).pack(side="left", padx=(0, 3))
        label(left, self.t("save_error" if self.save_failed else "saved"), 9, color=MUTED).pack(anchor="w", pady=(22, 8))
        right = tk.Frame(self.body, bg=BLUE)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=31, uniform="panels")
        right.rowconfigure(1, weight=69, uniform="panels")
        log_shell = tk.Frame(right, bg=BLUE, highlightbackground=LINE, highlightthickness=1)
        log_shell.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        label(log_shell, self.t("log"), 11, True).pack(anchor="w", padx=12, pady=6)
        log = self.scroll_panel(log_shell, "log")
        log.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        for record in self.game.state.event_history:
            title, result, delta = history_text(record, self.language)
            wrapping_label(log.inner, title, 10, True).pack(fill="x", pady=(4, 2))
            wrapping_label(log.inner, result, 10, color=MUTED).pack(fill="x", pady=(0, 3))
            wrapping_label(log.inner, delta, 10, color=ACCENT).pack(fill="x", pady=(0, 10))
        event_shell = tk.Frame(right, bg=YELLOW, highlightbackground=LINE, highlightthickness=1)
        event_shell.grid(row=1, column=0, sticky="nsew")
        panel = self.scroll_panel(event_shell, "event", YELLOW)
        panel.pack(fill="both", expand=True, padx=14, pady=14)
        self.render_event(panel.inner)

    def render_event(self, parent):
        state = self.game.state
        phase = state.phase
        if phase == "OPTIONAL_CARDS":
            wrapping_label(parent, self.t("cards_heading"), 18, True).pack(fill="x", pady=(0, 6))
            wrapping_label(parent, self.t("cards_note", count=len(state.optional_candidates)), 10, color=MUTED).pack(fill="x", pady=(0, 14))
            row = tk.Frame(parent, bg=YELLOW)
            row.pack(fill="x")
            for i, event_id in enumerate(state.optional_candidates):
                row.columnconfigure(i, weight=1, uniform="cards")
                event = EVENTS[event_id]
                card = tk.Frame(row, bg=BLUE, highlightbackground=LINE, highlightthickness=1, padx=10, pady=12)
                card.grid(row=0, column=i, sticky="nsew", padx=(0, 5))
                label(card, f"0{i + 1}", 10, True, color=MUTED).pack(anchor="w", pady=(0, 10))
                wrapping_label(card, event["title"][self.language], 12, True).pack(fill="x", pady=(0, 10))
                wrapping_label(card, event["description"][self.language], 10).pack(fill="x", pady=(0, 14))
                self.button(card, self.t("card_choose"), lambda eid=event_id: self.act(lambda: self.game.pick_event(eid)),
                            wraplength=130, padx=6).pack(side="bottom", fill="x", pady=(12, 0))
        elif phase == "OPTIONAL_CHOICE":
            event = EVENTS[state.selected_event]
            wrapping_label(parent, event["title"][self.language], 18, True).pack(fill="x", pady=(0, 10))
            wrapping_label(parent, event["description"][self.language], 11).pack(fill="x", pady=(0, 12))
            wrapping_label(parent, self.t("choice_note"), 10, color=MUTED).pack(fill="x", pady=(0, 12))
            self.option_variable = tk.StringVar(value=state.selected_option or "")
            for option in event["options"]:
                card = tk.Frame(parent, bg=BLUE, highlightbackground=ACCENT if state.selected_option == option["id"] else LINE,
                                highlightthickness=2 if state.selected_option == option["id"] else 1)
                card.pack(fill="x", pady=(0, 8))
                radio = tk.Radiobutton(card, text=option["id"] + "  " + option["text"][self.language],
                                       variable=self.option_variable, value=option["id"], anchor="w", justify="left",
                                       bg=BLUE, fg=INK, selectcolor=YELLOW, activebackground=BLUE,
                                       font=(self.ui_font, 11), padx=8, pady=10,
                                       command=lambda oid=option["id"]: self._select_option(oid))
                radio.pack(fill="x")
                radio.bind("<Configure>", lambda e, r=radio: r.configure(wraplength=max(100, e.width - 60)))
                if option["risky"]:
                    percent = round(risk_probability(state.stats["rationality"]) * 100, 1)
                    wrapping_label(card, self.t("risk_chance", percent=f"{percent:g}"), 10, color=ACCENT).pack(fill="x", padx=30, pady=(0, 10))
            self.confirm_button = self.button(parent, self.t("confirm"), lambda: self.act(self.game.confirm_option), True,
                                              disabled=state.selected_option is None)
            self.confirm_button.pack(anchor="e", pady=(8, 4))
        elif phase in ("FORCED_RESOLVED", "OPTIONAL_RESOLVED"):
            forced = phase == "FORCED_RESOLVED"
            event = EVENTS[state.current_forced_event if forced else state.selected_event]
            wrapping_label(parent, self.t("forced_heading" if forced else "result_heading"), 16, True).pack(fill="x", pady=(0, 10))
            if forced:
                wrapping_label(parent, self.t("forced_note"), 10, color=MUTED).pack(fill="x", pady=(0, 12))
            wrapping_label(parent, event["title"][self.language], 14, True).pack(fill="x", pady=(0, 8))
            if forced:
                wrapping_label(parent, event["description"][self.language], 11).pack(fill="x", pady=(0, 8))
                outcome = event
            else:
                option = next(o for o in event["options"] if o["id"] == state.selected_option)
                result = state.resolved_result["outcome"]
                outcome = option if result == "fixed" else option[result]
                label(parent, self.t(result), 10, True, color=ACCENT).pack(anchor="w", pady=(0, 10))
            wrapping_label(parent, outcome["result"][self.language], 12).pack(fill="x", pady=(0, 18))
            wrapping_label(parent, effect_text(state.resolved_result["delta"], self.language), 12, True, color=ACCENT).pack(fill="x", pady=(0, 16))
            last_event = not forced or not self.game.has_optional_events()
            next_label = ("see_ending" if state.day == CONFIG["max_days"] else "next_day") if last_event else "continue"
            self.button(parent, self.t(next_label), lambda: self.act(self.game.continue_phase), True).pack(anchor="e", pady=4)
        elif phase == "DAY_COMPLETE":
            wrapping_label(parent, self.t("no_events"), 11).pack(fill="x", pady=(12, 20))
            self.button(parent, self.t("see_ending" if state.day == CONFIG["max_days"] else "next_day"),
                        lambda: self.act(self.game.continue_phase), True).pack(anchor="e")

    def _select_option(self, option_id):
        # Keep the scroll position and radio controls in place; selecting is not rolling.
        self.game.pick_option(option_id)
        self._save()
        self.confirm_button.configure(state="normal", cursor="hand2")

    def render_ending(self):
        panel = self.scroll_panel(self.body, "ending")
        panel.pack(fill="both", expand=True)
        parent = panel.inner
        wrapping_label(parent, self.t("ending_heading"), 19, True, anchor="center").pack(fill="x", pady=(12, 18))
        state = self.game.state
        ending = ENDINGS[state.ending]
        frame = OrnateFrame(parent, ending["id"])
        frame.pack(fill="x", padx=36, pady=(0, 18))
        inner = frame.inner
        label(inner, ending["id"] + "  ·  ✦", 12, True, color=frame.edge).pack(pady=(2, 12))
        wrapping_label(inner, ending["title"][self.language], 48, True, anchor="center", justify="center", font=self.title_font(48)).pack(fill="x", pady=(0, 18))
        wrapping_label(inner, ending["description"][self.language], 12, anchor="center", justify="center").pack(fill="x", pady=(0, 16))
        label(inner, self.t("ending_unlocked"), 10, color=MUTED).pack(pady=4)
        if state.death_event:
            wrapping_label(parent, self.t("death", day=state.day, event=EVENTS[state.death_event]["title"][self.language]), 11, color=MUTED).pack(fill="x", padx=36, pady=(0, 12))
        label(parent, self.t("day", day=state.day, max=CONFIG["max_days"]), 12, True).pack(pady=(0, 8))
        stats = tk.Frame(parent, bg=BLUE)
        stats.pack(fill="x", padx=36, pady=(0, 16))
        for i, stat in enumerate(STAT_KEYS):
            stats.columnconfigure(i, weight=1, uniform="finalstats")
            col = tk.Frame(stats, bg=BLUE)
            col.grid(row=0, column=i, sticky="ew", padx=6)
            label(col, self.t(stat), 11, True).pack()
            label(col, f"{state.stats[stat]} / {CONFIG['stat_max']}", 12).pack(pady=4)
            PixelBar(col, state.stats[stat], COLORS[stat]).pack(fill="x")
        controls = tk.Frame(parent, bg=BLUE)
        controls.pack(pady=(6, 20))
        self.button(controls, self.t("new_game"), self.new_game, True).pack(side="left", padx=6)
        self.button(controls, self.t("back_menu"), self.menu).pack(side="left", padx=6)

    def render_gallery(self):
        unlocked = self.store.progress["unlocked_endings"]
        label(self.body, self.t("gallery_heading", count=len(unlocked)), 23, True).pack(anchor="w", pady=(10, 8))
        wrapping_label(self.body, self.t("gallery_note"), 11, color=MUTED).pack(fill="x", pady=(0, 18))
        panel = self.scroll_panel(self.body, "gallery")
        panel.pack(fill="both", expand=True)
        for col in range(3):
            panel.inner.columnconfigure(col, weight=1, uniform="gallery")
        for i, ending in enumerate(ENDINGS.values()):
            card = tk.Frame(panel.inner, bg=YELLOW, highlightbackground=LINE, highlightthickness=1, padx=16, pady=16)
            card.grid(row=i // 3, column=i % 3, sticky="nsew", padx=(0, 10), pady=(0, 12))
            label(card, ending["id"], 10, True, color=MUTED).pack(anchor="w", pady=(0, 10))
            if ending["id"] in unlocked:
                wrapping_label(card, ending["title"][self.language], 17, True).pack(fill="x", pady=(0, 6))
                if self.language == "zh":
                    wrapping_label(card, ending["title"]["en"], 12, True, color=ACCENT).pack(fill="x", pady=(0, 14))
                wrapping_label(card, ending["description"][self.language], 10).pack(fill="x", pady=(0, 10))
            else:
                mask = tk.Canvas(card, bg="#E3E7EA", height=142, bd=0, highlightthickness=0)
                mask.pack(fill="x", pady=(0, 12))
                mask.bind("<Configure>", self._draw_mask)
                label(card, self.t("locked"), 10, color=MUTED).pack(pady=8)

    @staticmethod
    def _draw_mask(event):
        canvas = event.widget
        canvas.delete("all")
        width, height = event.width, event.height
        for x in range(-height, width + height, 18):
            canvas.create_line(x, height, x + height, 0, fill="#C1CBD2", width=2)
        canvas.create_rectangle(width / 2 - 49, height / 2 - 27, width / 2 + 49, height / 2 + 27,
                                fill="#E3E7EA", outline="")
        canvas.create_text(width / 2, height / 2, text="???", font=("Courier New", 28, "bold"), fill=MUTED)


def main():
    try:
        app = App()
    except (SaveError, ValueError) as error:
        messagebox.showerror("Galactic Misadventures", str(error))
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
