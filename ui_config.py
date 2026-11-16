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
        self.geometry("340x360")
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
        self.delay_var = tk.StringVar(value=str(self.settings.get("launch_delay_sec", 6)))
        theme.entry(delay_row, textvariable=self.delay_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(delay_row, text="seconds").pack(side="left")

        self.validate_var = tk.BooleanVar(value=bool(self.settings.get("validate_before_launch", True)))
        theme.wire_checkbutton(body, "Validate Sessions", self.validate_var).pack(anchor="w", pady=(12, 0))

        theme.tab_box(body, "Auto-Join").pack(anchor="w", pady=(14, 10))
        self.auto_join_enabled_var = tk.BooleanVar(value=bool(self.settings.get("auto_join_enabled", False)))
        theme.wire_checkbutton(body, "Enable smart auto-join", self.auto_join_enabled_var).pack(anchor="w")

        max_row = tk.Frame(body, bg=theme.BG)
        max_row.pack(anchor="w", pady=(8, 0))
        theme.label(max_row, text="Max players").pack(side="left")
        self.auto_join_max_players_var = tk.StringVar(value=str(self.settings.get("auto_join_max_players", 0)))
        theme.entry(max_row, textvariable=self.auto_join_max_players_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(max_row, text="(0 = any)").pack(side="left")

        top_row = tk.Frame(body, bg=theme.BG)
        top_row.pack(anchor="w", pady=(8, 0))
        theme.label(top_row, text="Random from top").pack(side="left")
        self.auto_join_top_n_var = tk.StringVar(value=str(self.settings.get("auto_join_top_n", 3)))
        theme.entry(top_row, textvariable=self.auto_join_top_n_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(top_row, text="lowest-pop servers").pack(side="left")

        wait_row = tk.Frame(body, bg=theme.BG)
        wait_row.pack(anchor="w", pady=(8, 0))
        theme.label(wait_row, text="Wait up to").pack(side="left")
        self.auto_join_wait_sec_var = tk.StringVar(value=str(self.settings.get("auto_join_wait_sec", 60)))
        theme.entry(wait_row, textvariable=self.auto_join_wait_sec_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(wait_row, text="seconds").pack(side="left")

        poll_row = tk.Frame(body, bg=theme.BG)
        poll_row.pack(anchor="w", pady=(8, 0))
        theme.label(poll_row, text="Retry every").pack(side="left")
        self.auto_join_poll_sec_var = tk.StringVar(value=str(self.settings.get("auto_join_poll_sec", 5)))
        theme.entry(poll_row, textvariable=self.auto_join_poll_sec_var, width=4).pack(side="left", padx=(8, 6))
        theme.label(poll_row, text="seconds").pack(side="left")

    def _close(self) -> None:
        try:
            sec = max(0, min(60, int(self.delay_var.get().strip() or "6")))
            max_players = max(0, min(200, int(self.auto_join_max_players_var.get().strip() or "0")))
            top_n = max(1, min(10, int(self.auto_join_top_n_var.get().strip() or "3")))
            wait_sec = max(0, min(600, int(self.auto_join_wait_sec_var.get().strip() or "60")))
            poll_sec = max(2, min(20, int(self.auto_join_poll_sec_var.get().strip() or "5")))
        except ValueError:
            messagebox.showwarning("Configuration", "Review numeric values.", parent=self)
            return
        self.settings["launch_delay_sec"] = sec
        self.settings["validate_before_launch"] = bool(self.validate_var.get())
        self.settings["auto_join_enabled"] = bool(self.auto_join_enabled_var.get())
        self.settings["auto_join_max_players"] = max_players
        self.settings["auto_join_top_n"] = top_n
        self.settings["auto_join_wait_sec"] = wait_sec
        self.settings["auto_join_poll_sec"] = poll_sec
        app_storage.save_settings(self.settings)
        self.on_saved(self.settings)
        self.destroy()
