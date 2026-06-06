"""Tema wireframe idéntico a los mockups: negro puro, bordes blancos, 0 radius."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#000000"
TABLE_HEAD = "#3a3a3a"
BORDER = "#ffffff"
TEXT = "#ffffff"
MUTED = "#aaaaaa"
INPUT = "#000000"
ERROR = "#ff6666"
TITLE_BAR = "#1e1e1e"
LINK = "#ffffff"
GREEN = "#00cc44"
BLUE_BTN = "#3366cc"
GEAR = "#8888cc"

FONT = ("Segoe UI", 10)
FONT_SM = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI", 11)
FONT_TABLE_HEAD = ("Segoe UI", 10)


def apply_ttk_style(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".",
        background=BG,
        foreground=TEXT,
        fieldbackground=INPUT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        troughcolor=BG,
        font=FONT,
    )
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure(
        "Treeview",
        background=BG,
        foreground=TEXT,
        fieldbackground=BG,
        borderwidth=0,
        rowheight=22,
    )
    style.configure(
        "Treeview.Heading",
        background=TABLE_HEAD,
        foreground=TEXT,
        bordercolor=BORDER,
        relief="flat",
        font=FONT_TABLE_HEAD,
        padding=(6, 4),
    )
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.map(
        "Treeview",
        background=[("selected", "#2a2a2a")],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "TCheckbutton",
        background=BG,
        foreground=TEXT,
        focuscolor=BG,
        indicatorcolor=BG,
        bordercolor=BORDER,
    )
    style.map("TCheckbutton", background=[("active", BG)])
    return style


def frame(parent, **kwargs) -> tk.Frame:
    return tk.Frame(parent, bg=BG, highlightbackground=BORDER, highlightthickness=1, **kwargs)


def label(parent, text: str = "", **kwargs) -> tk.Label:
    opts = {"bg": BG, "fg": TEXT, "font": FONT, "anchor": "w"}
    opts.update(kwargs)
    return tk.Label(parent, text=text, **opts)


def button(parent, text: str = "", command=None, *, width: int | None = None) -> tk.Button:
    opts = {
        "text": text,
        "command": command,
        "bg": BG,
        "fg": TEXT,
        "activebackground": "#111111",
        "activeforeground": TEXT,
        "font": FONT,
        "relief": "solid",
        "bd": 1,
        "highlightthickness": 0,
        "padx": 10,
        "pady": 2,
        "cursor": "hand2",
    }
    if width is not None:
        opts["width"] = width
    return tk.Button(parent, **opts)


def underlined_button(parent, text: str, command=None) -> tk.Label:
    lbl = tk.Label(
        parent,
        text=text,
        bg=BG,
        fg=TEXT,
        font=FONT,
        cursor="hand2",
        underline=True,
    )
    if command:
        lbl.bind("<Button-1>", lambda _e: command())
    return lbl


def arrow_button(parent, command=None) -> tk.Button:
    return tk.Button(
        parent,
        text="▼",
        command=command,
        bg=BLUE_BTN,
        fg=TEXT,
        activebackground=BLUE_BTN,
        activeforeground=TEXT,
        font=("Segoe UI", 8),
        relief="flat",
        bd=0,
        width=2,
        height=1,
        cursor="hand2",
    )


def entry(parent, textvariable=None, **kwargs) -> tk.Entry:
    opts = {
        "textvariable": textvariable,
        "bg": INPUT,
        "fg": TEXT,
        "insertbackground": TEXT,
        "font": FONT,
        "relief": "solid",
        "bd": 1,
        "highlightthickness": 1,
        "highlightbackground": BORDER,
        "highlightcolor": BORDER,
    }
    opts.update(kwargs)
    return tk.Entry(parent, **opts)


def text_area(parent, **kwargs) -> tk.Text:
    opts = {
        "bg": INPUT,
        "fg": MUTED,
        "insertbackground": TEXT,
        "font": FONT,
        "relief": "solid",
        "bd": 1,
        "highlightthickness": 1,
        "highlightbackground": BORDER,
        "highlightcolor": BORDER,
        "wrap": "word",
    }
    opts.update(kwargs)
    return tk.Text(parent, **opts)


class PlaceholderEntry(tk.Entry):
    def __init__(self, parent, placeholder: str, textvariable: tk.StringVar | None = None, **kwargs) -> None:
        self.placeholder = placeholder
        self.placeholder_color = MUTED
        self.default_fg = TEXT
        self._var = textvariable or tk.StringVar()
        super().__init__(
            parent,
            textvariable=self._var,
            bg=INPUT,
            fg=self.placeholder_color,
            insertbackground=TEXT,
            font=FONT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            **kwargs,
        )
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._var.trace_add("write", lambda *_: self._on_var_change())
        self._show_placeholder()

    def _on_var_change(self) -> None:
        if self.focus_get() == self:
            return
        if self._var.get():
            self.configure(fg=self.default_fg)
        else:
            self._show_placeholder()

    def _show_placeholder(self) -> None:
        if not self._var.get():
            self.configure(fg=self.placeholder_color)

    def _on_focus_in(self, _event) -> None:
        if not self._var.get():
            self.configure(fg=self.default_fg)

    def _on_focus_out(self, _event) -> None:
        if not self._var.get():
            self.configure(fg=self.placeholder_color)

    def get_value(self) -> str:
        return self._var.get().strip()


class PlaceholderText(tk.Text):
    def __init__(self, parent, placeholder: str, **kwargs) -> None:
        self.placeholder = placeholder
        super().__init__(
            parent,
            bg=INPUT,
            fg=MUTED,
            insertbackground=TEXT,
            font=FONT,
            relief="solid",
            bd=1,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            wrap="word",
            **kwargs,
        )
        self.insert("1.0", placeholder)
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, _event) -> None:
        if self.get("1.0", "end-1c") == self.placeholder:
            self.delete("1.0", tk.END)
            self.configure(fg=TEXT)

    def _on_focus_out(self, _event) -> None:
        if not self.get("1.0", "end-1c").strip():
            self.delete("1.0", tk.END)
            self.insert("1.0", self.placeholder)
            self.configure(fg=MUTED)

    def get_value(self) -> str:
        val = self.get("1.0", "end-1c")
        return "" if val == self.placeholder else val.strip()


class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, variable: tk.BooleanVar, command=None, width=44, height=20) -> None:
        super().__init__(parent, width=width, height=height, bg=BG, highlightthickness=1, highlightbackground=BORDER)
        self.variable = variable
        self.command = command
        self.w, self.h = width, height
        self.bind("<Button-1>", self._toggle)
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _toggle(self, _event=None) -> None:
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def _draw(self) -> None:
        self.delete("all")
        on = bool(self.variable.get())
        pad = 2
        track = "#555555" if on else "#222222"
        self.create_rectangle(1, 1, self.w - 1, self.h - 1, fill=track, outline=BORDER)
        knob_x = self.w - pad - 10 if on else pad + 1
        self.create_rectangle(knob_x, pad + 1, knob_x + 10, self.h - pad - 1, fill=TEXT, outline=BORDER)


def window_header(parent, title: str, on_close, on_settings=None) -> tk.Frame:
    bar = tk.Frame(parent, bg=BG, height=32)
    bar.grid_propagate(False)
    label(bar, text=title, font=FONT_TITLE).pack(side="left", padx=(4, 0), pady=4)
    right = tk.Frame(bar, bg=BG)
    right.pack(side="right", padx=4)
    if on_settings:
        gear = tk.Label(right, text="⚙", bg=BG, fg=GEAR, font=("Segoe UI", 14), cursor="hand2")
        gear.pack(side="left", padx=(0, 10))
        gear.bind("<Button-1>", lambda _e: on_settings())
    close = tk.Label(right, text="✕", bg=BG, fg=TEXT, font=("Segoe UI", 12), cursor="hand2")
    close.pack(side="left")
    close.bind("<Button-1>", lambda _e: on_close())
    return bar


def dialog_title_bar(parent, title: str, on_close) -> tk.Frame:
    bar = tk.Frame(parent, bg=TITLE_BAR, height=26)
    bar.grid_propagate(False)
    tk.Label(bar, text=title, bg=TITLE_BAR, fg=TEXT, font=FONT).pack(side="left", padx=8)
    close = tk.Label(bar, text="✕", bg=TITLE_BAR, fg=TEXT, font=("Segoe UI", 11), cursor="hand2")
    close.pack(side="right", padx=8)
    close.bind("<Button-1>", lambda _e: on_close())
    return bar


def inner_title_box(parent, text: str) -> tk.Frame:
    box = frame(parent)
    lbl = tk.Label(box, text=text, bg=BG, fg=TEXT, font=FONT, underline=True)
    lbl.pack(padx=20, pady=4)
    return box


def tab_box(parent, text: str) -> tk.Frame:
    box = frame(parent)
    tk.Label(box, text=text, bg=BG, fg=TEXT, font=FONT).pack(padx=12, pady=3)
    return box


def wire_checkbutton(parent, text: str, variable: tk.BooleanVar, command=None) -> tk.Frame:
    row = tk.Frame(parent, bg=BG)
    box = tk.Canvas(row, width=14, height=14, bg=BG, highlightthickness=1, highlightbackground=BORDER, cursor="hand2")
    box.pack(side="left")

    lbl = tk.Label(row, text=text, bg=BG, fg=TEXT, font=FONT, cursor="hand2")
    lbl.pack(side="left", padx=(6, 0))

    def draw() -> None:
        box.delete("all")
        if variable.get():
            box.create_rectangle(3, 3, 11, 11, fill=TEXT, outline=TEXT)

    def toggle(_event=None) -> None:
        variable.set(not variable.get())
        draw()
        if command:
            command()

    box.bind("<Button-1>", toggle)
    lbl.bind("<Button-1>", toggle)
    variable.trace_add("write", lambda *_: draw())
    draw()
    return row
