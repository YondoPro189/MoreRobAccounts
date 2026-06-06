"""Ventana Configuration — mockup exacto."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

import app_storage
import ui_theme as theme


class ConfigurationDialog(tk.Toplevel):
    def __init__(self, parent, on_saved) -> None:
        super().__init__(parent)
        self.title("Configuration")
        self.geometry("340x180")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.on_saved = on_saved
        self.settings = app_storage.get_settings()
        self._build()
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        theme.apply_ttk_style(self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        theme.dialog_title_bar(self, "Configuration", on_close=self._close).grid(row=0, column=0, sticky="ew")

        body = tk.Frame(self, bg=theme.BG)
        body.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)

        theme.tab_box(body, "General").pack(anchor="w", pady=(0, 14))

        delay_row = tk.Frame(body, bg=theme.BG)
        delay_row.pack(anchor="w")
        theme.label(delay_row, text="Delay").pack(side="left")
        self.delay_var = tk.StringVar(value=str(self.settings.get("launch_delay_sec", 3)))
        theme.entry(delay_row, textvariable=self.delay_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(delay_row, text="seconds").pack(side="left")

        self.validate_var = tk.BooleanVar(value=bool(self.settings.get("validate_before_launch", True)))
        theme.wire_checkbutton(body, "Validate Sessions", self.validate_var).pack(anchor="w", pady=(12, 0))

    def _close(self) -> None:
        try:
            sec = max(0, min(60, int(self.delay_var.get().strip() or "3")))
        except ValueError:
            messagebox.showwarning("Configuration", "Delay must be a number.", parent=self)
            return
        self.settings["launch_delay_sec"] = sec
        self.settings["validate_before_launch"] = bool(self.validate_var.get())
        app_storage.save_settings(self.settings)
        self.on_saved(self.settings)
        self.destroy()
