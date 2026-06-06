import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_storage
import launcher
import notifications
import roblox_fps
import ui_theme as theme
from security import SecurityError
from ui_config import ConfigurationDialog
from ui_families import FamilyManagerDialog, pick_family_dialog

try:
    from secure_login import (
        LOGIN_WORKER_FLAG,
        get_login_result_path,
        is_browser_login_available,
        is_browser_login_worker_argv,
        login_via_browser,
        read_login_result,
        run_browser_login_worker,
        verify_roblox_session,
    )
except ImportError:

    LOGIN_WORKER_FLAG = "--browser-login-worker"

    def is_browser_login_available() -> bool:
        return False

    def login_via_browser(**kwargs):
        return None, None, "Modulo secure_login no disponible."

    def is_browser_login_worker_argv(argv=None) -> bool:
        return False

    def get_login_result_path() -> str:
        return os.path.join(launcher.get_app_dir(), "_login_result.json")

    def run_browser_login_worker(result_path: str) -> int:
        return 1

    def read_login_result(result_path: str):
        return None, None, "Modulo secure_login no disponible."

    def verify_roblox_session(cookie: str) -> str | None:
        return None


def load_accounts_ui() -> list[dict]:
    return launcher.load_accounts()


def save_accounts_ui(accounts: list[dict]) -> None:
    launcher.save_accounts(accounts)


def normalize_cookie(cookie: str) -> str:
    cookie = cookie.strip()
    if len(cookie) >= 2 and cookie[0] in ("'", '"') and cookie[-1] == cookie[0]:
        cookie = cookie[1:-1].strip()
    return cookie


class MoreRobAccountsUI(tk.Tk):
    PAD = 14

    def __init__(self) -> None:
        super().__init__()
        self.title("Multiple Roblox Accounts")
        self.geometry("940x520")
        self.minsize(860, 480)
        self.configure(bg=theme.BG)

        self.accounts: list[dict] = load_accounts_ui()
        self._session_valid: dict[str, bool] = {}
        self._login_proc: subprocess.Popen | None = None
        self._login_result_path: str | None = None
        self._renew_target: str | None = None
        self._readd_target: str | None = None
        self._window_icon: tk.PhotoImage | None = None
        self._context_iid: str | None = None
        self._progress_label = tk.StringVar(value="")
        self.settings = app_storage.get_settings()

        theme.apply_ttk_style(self)
        self._set_window_icon()
        self._build_ui()
        self._refresh_place_history()
        self._refresh_families_combo()
        self._refresh_accounts_list()
        self.after(300, self._check_roblox_installed)

    def _set_window_icon(self) -> None:
        icon_ico = launcher.get_icon_path("ico")
        if icon_ico and sys.platform == "win32":
            try:
                self.iconbitmap(default=icon_ico)
            except tk.TclError:
                pass
        icon_png = launcher.get_icon_path("png")
        if icon_png:
            try:
                self._window_icon = tk.PhotoImage(file=icon_png)
                self.iconphoto(True, self._window_icon)
            except tk.TclError:
                pass

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        theme.window_header(
            self,
            "Multiple Roblox Accounts",
            on_close=self.destroy,
            on_settings=self.open_configuration,
        ).grid(row=0, column=0, sticky="ew", padx=self.PAD, pady=(8, 0))

        body = tk.Frame(self, bg=theme.BG)
        body.grid(row=1, column=0, sticky="nsew", padx=self.PAD, pady=(6, self.PAD))
        body.grid_columnconfigure(0, weight=62)
        body.grid_columnconfigure(1, weight=38)
        body.grid_rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

        self.validate_before_var = tk.BooleanVar(value=bool(self.settings.get("validate_before_launch", True)))
        self.debug_var = tk.BooleanVar(value=bool(self.settings.get("debug", False)))

    def _build_left_panel(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=theme.BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        refresh_row = tk.Frame(left, bg=theme.BG)
        refresh_row.grid(row=0, column=0, sticky="e", pady=(0, 4))
        theme.underlined_button(refresh_row, "Refresh", command=self.reload_accounts).pack(side="left")
        tk.Label(refresh_row, text="↻", bg=theme.BG, fg=theme.GREEN, font=("Segoe UI", 13)).pack(side="left", padx=(4, 0))

        table_wrap = theme.frame(left)
        table_wrap.grid(row=1, column=0, sticky="nsew")
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)

        cols = ("username", "alias", "description")
        self.accounts_tree = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="extended")
        self.accounts_tree.heading("username", text="Username")
        self.accounts_tree.heading("alias", text="Alias")
        self.accounts_tree.heading("description", text="Description")
        self.accounts_tree.column("username", width=130, stretch=True, anchor="w")
        self.accounts_tree.column("alias", width=110, stretch=True, anchor="w")
        self.accounts_tree.column("description", width=160, stretch=True, anchor="w")
        self.accounts_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.accounts_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.accounts_tree.configure(yscrollcommand=sb.set)

        self.accounts_tree.bind("<<TreeviewSelect>>", self._on_account_select)
        self.accounts_tree.bind("<Delete>", lambda _e: self.delete_selected_account())
        self.accounts_tree.bind("<Button-3>", self._show_account_context_menu)

        bottom = tk.Frame(left, bg=theme.BG)
        bottom.grid(row=2, column=0, pady=(10, 0))
        self.add_account_btn = theme.button(bottom, text="Add Account", command=self.add_account)
        self.add_account_btn.pack(side="left", padx=(0, 8))
        self.delete_account_btn = theme.button(bottom, text="Remove", command=self.delete_selected_account)
        self.delete_account_btn.pack(side="left", padx=(0, 16))
        self.hide_username_var = tk.BooleanVar(value=bool(self.settings.get("hide_usernames", False)))
        theme.wire_checkbutton(bottom, "Hide Username", self.hide_username_var, command=self._toggle_hide_usernames).pack(side="left")

        self.status_var = tk.StringVar(value="")
        theme.label(left, textvariable=self.status_var, fg=theme.MUTED, font=theme.FONT_SM).grid(row=3, column=0, sticky="w", pady=(4, 0))

        self._account_menu = tk.Menu(self, tearoff=0, bg=theme.BG, fg=theme.TEXT, activebackground="#222222")
        self._account_menu.add_command(label="Launch", command=self.launch_selected)
        self._account_menu.add_command(label="Launch all", command=self.launch_all)
        self._account_menu.add_separator()
        self._account_menu.add_command(label="Add to family...", command=self.context_add_to_family)
        self._account_menu.add_command(label="Re-add account", command=self.context_readd_account)
        self._account_menu.add_command(label="Renew session", command=self.renew_selected_session)
        self._account_menu.add_command(label="Check session", command=self.context_check_session)
        self._account_menu.add_command(label="Check all sessions", command=self.check_all_sessions)
        self._account_menu.add_separator()
        self._account_menu.add_command(label="Follow user...", command=self.context_follow_user)
        self._account_menu.add_command(label="Remove", command=self.delete_selected_account)

    def _build_right_panel(self, parent: tk.Frame) -> None:
        right = tk.Frame(parent, bg=theme.BG)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        row0 = tk.Frame(right, bg=theme.BG)
        row0.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        row0.grid_columnconfigure(1, weight=1)
        theme.label(row0, text="Place ID:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        place_inner = tk.Frame(row0, bg=theme.BG)
        place_inner.grid(row=0, column=1, sticky="ew")
        place_inner.grid_columnconfigure(0, weight=1)
        self.place_var = tk.StringVar(value="0")
        self.place_combo = ttk.Combobox(place_inner, textvariable=self.place_var)
        self.place_combo.grid(row=0, column=0, sticky="ew")
        theme.arrow_button(place_inner, command=self._show_place_history).grid(row=0, column=1, padx=(4, 0))

        row1 = tk.Frame(right, bg=theme.BG)
        row1.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        theme.label(row1, text="Family ID").pack(side="left")
        self.use_family_place_var = tk.BooleanVar(value=bool(self.settings.get("use_family_place_id", True)))
        theme.ToggleSwitch(row1, self.use_family_place_var, command=self._on_family_toggle).pack(side="left", padx=(10, 0))
        self.family_var = tk.StringVar()
        self.join_server_btn = theme.button(row1, text="Join Server", command=self.launch_selected)
        self.join_server_btn.pack(side="right")

        row2 = tk.Frame(right, bg=theme.BG)
        row2.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        row2.grid_columnconfigure(1, weight=1)
        theme.label(row2, text="Username:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        follow_inner = tk.Frame(row2, bg=theme.BG)
        follow_inner.grid(row=0, column=1, sticky="ew")
        follow_inner.grid_columnconfigure(0, weight=1)
        self.follow_username_var = tk.StringVar()
        theme.entry(follow_inner, textvariable=self.follow_username_var).grid(row=0, column=0, sticky="ew")
        self.follow_btn = theme.button(follow_inner, text="Follow", command=self.follow_user_selected)
        self.follow_btn.grid(row=0, column=1, padx=(4, 0))

        row3 = tk.Frame(right, bg=theme.BG)
        row3.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        row3.grid_columnconfigure(0, weight=1)
        self.alias_var = tk.StringVar()
        self.alias_entry = theme.PlaceholderEntry(row3, "Alias", textvariable=self.alias_var)
        self.alias_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        theme.button(row3, text="Set Alias", command=self.set_alias).grid(row=0, column=1)

        self.description_text = theme.PlaceholderText(right, "Account Description", height=10)
        self.description_text.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        self.description_text.bind("<FocusOut>", lambda _e: self._save_description())
        right.grid_rowconfigure(4, weight=1)

        row5 = tk.Frame(right, bg=theme.BG)
        row5.grid(row=5, column=0, sticky="ew")
        row5.grid_columnconfigure(1, weight=1)
        theme.button(row5, text="Families", command=self.manage_families).grid(row=0, column=0, padx=(0, 4))
        self.launch_family_btn = theme.button(row5, text="Launch Family", command=self.launch_family)
        self.launch_family_btn.grid(row=0, column=1, sticky="ew", padx=4)
        theme.arrow_button(row5, command=self._show_family_picker).grid(row=0, column=2, padx=(4, 0))

    def _on_family_toggle(self) -> None:
        self.settings["use_family_place_id"] = bool(self.use_family_place_var.get())
        app_storage.save_settings(self.settings)

    def _show_family_picker(self) -> None:
        families = app_storage.get_families()
        names = [f["name"] for f in families]
        if not names:
            messagebox.showinfo("Family", "No families yet. Open Families to create one.")
            return
        menu = tk.Menu(self, tearoff=0, bg=theme.BG, fg=theme.TEXT, activebackground="#222222")
        for name in names:
            menu.add_command(label=name, command=lambda n=name: self.family_var.set(n))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def open_configuration(self) -> None:
        ConfigurationDialog(self, on_saved=self._apply_settings)

    def _apply_settings(self, settings: dict) -> None:
        self.settings = settings
        self.validate_before_var.set(bool(settings.get("validate_before_launch", True)))

    def _show_place_history(self) -> None:
        self.place_combo.event_generate("<Down>")

    def _toggle_hide_usernames(self) -> None:
        self.settings["hide_usernames"] = bool(self.hide_username_var.get())
        app_storage.save_settings(self.settings)
        self._refresh_accounts_list()

    def _display_username(self, acc: dict) -> str:
        username = acc.get("roblox_username") or acc.get("name", "")
        if self.hide_username_var.get() and username:
            return "••••••••"
        return username

    def _on_account_select(self, _event=None) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            return
        self.alias_var.set(acc.get("name", ""))
        self._set_description_field(acc.get("description", ""))

    def _set_description_field(self, text: str) -> None:
        self.description_text.delete("1.0", tk.END)
        if text.strip():
            self.description_text.insert("1.0", text)
            self.description_text.configure(fg=theme.TEXT)
        else:
            self.description_text.insert("1.0", self.description_text.placeholder)
            self.description_text.configure(fg=theme.MUTED)

    def _show_account_context_menu(self, event: tk.Event) -> None:
        row = self.accounts_tree.identify_row(event.y)
        if row:
            if row not in self.accounts_tree.selection():
                self.accounts_tree.selection_set(row)
            self._context_iid = row
            self._account_menu.tk_popup(event.x_root, event.y_root)

    def context_add_to_family(self) -> None:
        selected = self._get_selected_accounts()
        if not selected:
            messagebox.showwarning("Family", "Select at least one account.")
            return
        families = app_storage.get_families()
        family_name = pick_family_dialog(self, families)
        if not family_name:
            return
        names = [a["name"] for a in selected]
        app_storage.add_accounts_to_family(family_name, names)
        self._refresh_families_combo()
        messagebox.showinfo("Family", f"Added to family '{family_name}'.")

    def context_readd_account(self) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            messagebox.showwarning("Account", "Select one account.")
            return
        if messagebox.askyesno("Re-add account", f"Log in again to refresh '{acc['name']}'?"):
            self._readd_target = acc["name"]
            self.login_with_browser(renew_name=acc["name"])

    def context_check_session(self) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            return
        ok, username = launcher.validate_account_session(acc)
        self._session_valid[acc["name"]] = ok
        if ok and username:
            app_storage.update_account_fields(acc["name"], roblox_username=username)
        self._refresh_accounts_list()
        state = "valid" if ok else "invalid"
        messagebox.showinfo("Session", f"{acc['name']}: session {state}.")

    def context_follow_user(self) -> None:
        username = simpledialog.askstring("Follow", "Roblox username to follow:", parent=self)
        if username:
            self.follow_username_var.set(username.strip())
            self.follow_user_selected()

    def set_alias(self) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            messagebox.showwarning("Alias", "Select one account.")
            return
        new_alias = self.alias_entry.get_value()
        if not new_alias:
            messagebox.showwarning("Alias", "Alias cannot be empty.")
            return
        if new_alias != acc["name"] and any(a.get("name") == new_alias for a in self.accounts):
            messagebox.showwarning("Alias", f"Alias '{new_alias}' already exists.")
            return
        old_name = acc["name"]
        if app_storage.update_account_fields(old_name, name=new_alias):
            app_storage.rename_account_references(old_name, new_alias)
            for a in self.accounts:
                if a["name"] == old_name:
                    a["name"] = new_alias
            if old_name in self._session_valid:
                self._session_valid[new_alias] = self._session_valid.pop(old_name)
            self._save_description()
            self._refresh_accounts_list()
            self._refresh_families_combo()

    def _save_description(self) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            return
        desc = self.description_text.get_value()
        app_storage.update_account_fields(acc["name"], description=desc)
        for a in self.accounts:
            if a["name"] == acc["name"]:
                a["description"] = desc

    def add_account(self) -> None:
        if not is_browser_login_available():
            messagebox.showerror("Login", "Download the FULL version from GitHub Releases.")
            return
        self._renew_target = None
        self._readd_target = None
        self.login_with_browser()

    def _check_roblox_installed(self) -> None:
        ok, _path = launcher.is_roblox_installed()
        n = len(self.accounts)
        if ok:
            self.status_var.set(f"{n} account(s) · Roblox OK")
        else:
            self.status_var.set("Roblox not detected")
            if messagebox.askyesno(
                "Roblox not found",
                "Roblox was not detected on this PC.\n\nOpen download page?",
            ):
                import webbrowser
                webbrowser.open("https://www.roblox.com/download")

    def _refresh_place_history(self) -> None:
        history = app_storage.get_place_history()
        self.place_combo["values"] = history if history else [""]
        if history and self.place_var.get() in ("", "0"):
            self.place_var.set(history[0])

    def _refresh_families_combo(self) -> None:
        families = app_storage.get_families()
        names = [f["name"] for f in families]
        if names and not self.family_var.get():
            self.family_var.set(names[0])

    def _persist_launch_settings(self) -> None:
        self.settings["use_family_place_id"] = bool(self.use_family_place_var.get())
        self.settings["validate_before_launch"] = bool(self.validate_before_var.get())
        self.settings["debug"] = bool(self.debug_var.get())
        self.settings["hide_usernames"] = bool(self.hide_username_var.get())
        app_storage.save_settings(self.settings)

    def _refresh_accounts_list(self) -> None:
        selected = self.accounts_tree.selection()
        self.accounts_tree.delete(*self.accounts_tree.get_children())
        self.accounts = load_accounts_ui()
        for a in self.accounts:
            alias = a.get("name", "?")
            username = self._display_username(a)
            desc = a.get("description", "")
            tags = ()
            if alias in self._session_valid and not self._session_valid[alias]:
                tags = ("invalid",)
            self.accounts_tree.insert("", "end", iid=alias, values=(username, alias, desc), tags=tags)
        self.accounts_tree.tag_configure("invalid", foreground=theme.ERROR)
        if selected:
            keep = [i for i in selected if i in self.accounts_tree.get_children()]
            if keep:
                self.accounts_tree.selection_set(keep)
        n = len(self.accounts)
        invalid = sum(1 for v in self._session_valid.values() if not v)
        extra = f" · {invalid} invalid" if invalid else ""
        self.status_var.set(f"{n} account(s){extra}")

    def reload_accounts(self) -> None:
        self._refresh_families_combo()
        self._refresh_place_history()
        self._refresh_accounts_list()

    def manage_families(self) -> None:
        FamilyManagerDialog(self, self.accounts, on_saved=self._refresh_families_combo)

    def _save_account(
        self,
        name: str,
        cookie: str,
        *,
        description: str = "",
        roblox_username: str = "",
    ) -> bool:
        if any(a.get("name") == name for a in self.accounts):
            messagebox.showwarning("Account", f"Account '{name}' already exists.")
            return False
        self.accounts.append(
            {
                "name": name,
                "roblosecurity": cookie,
                "group": "",
                "description": description.strip(),
                "roblox_username": roblox_username.strip(),
            }
        )
        try:
            save_accounts_ui(self.accounts)
        except (OSError, SecurityError) as e:
            messagebox.showerror("Error", f"Could not save account:\n{e}")
            self.accounts.pop()
            return False
        self._session_valid[name] = True
        self._refresh_accounts_list()
        return True

    def login_with_browser(self, *, renew_name: str | None = None) -> None:
        if not is_browser_login_available():
            messagebox.showerror("Login", "Download the FULL version from GitHub Releases.")
            return
        self._renew_target = renew_name
        browser_hint = "Microsoft Edge" if sys.platform == "win32" else "browser"
        self.status_var.set(f"Opening {browser_hint}...")
        self._set_buttons_running(True)
        if launcher.is_frozen_app():
            self._start_browser_login_subprocess()
        else:
            self._start_browser_login_thread()

    def _finish_browser_login(self, cookie: str | None, username: str | None, error: str | None) -> None:
        renew = self._renew_target
        self._renew_target = None
        if error or not cookie:
            messagebox.showerror("Login", error or "No session.")
            self.status_var.set("Login failed.")
            self._set_buttons_running(False)
            return

        roblox_user = (username or "").strip()
        if renew:
            if app_storage.update_account_cookie(renew, cookie, roblox_username=roblox_user or None):
                self._session_valid[renew] = True
                if roblox_user:
                    app_storage.update_account_fields(renew, roblox_username=roblox_user)
                messagebox.showinfo("Done", f"Session for '{renew}' renewed.")
                self._refresh_accounts_list()
            else:
                messagebox.showerror("Error", f"Account '{renew}' not found.")
        else:
            alias = self.alias_entry.get_value() or roblox_user or "Account"
            desc = self.description_text.get_value()
            if self._save_account(alias, cookie, description=desc, roblox_username=roblox_user):
                messagebox.showinfo("Done", f"Account '{alias}' saved.")
        self._set_buttons_running(False)

    def _start_browser_login_thread(self) -> None:
        def worker() -> None:
            cookie, username, error = login_via_browser(timeout_sec=300)
            self.after(0, lambda: self._finish_browser_login(cookie, username, error))

        threading.Thread(target=worker, daemon=True).start()

    def _start_browser_login_subprocess(self) -> None:
        result_path = get_login_result_path()
        self._login_result_path = result_path
        try:
            if os.path.isfile(result_path):
                os.remove(result_path)
        except OSError:
            pass
        try:
            self._login_proc = subprocess.Popen(
                [sys.executable, LOGIN_WORKER_FLAG, result_path],
                cwd=launcher.get_app_dir(),
            )
        except OSError as exc:
            self._finish_browser_login(None, None, f"Could not start login:\n{exc}")
            return
        self.after(400, self._poll_browser_login_subprocess)

    def _poll_browser_login_subprocess(self) -> None:
        if self._login_proc is not None and self._login_proc.poll() is None:
            self.after(400, self._poll_browser_login_subprocess)
            return
        result_path = self._login_result_path or get_login_result_path()
        try:
            cookie, username, error = read_login_result(result_path)
        except (OSError, json.JSONDecodeError) as exc:
            cookie, username, error = None, None, f"Error reading result:\n{exc}"
        self._login_proc = None
        self._login_result_path = None
        self._finish_browser_login(cookie, username, error)

    def delete_selected_account(self) -> None:
        selected = self._get_selected_accounts()
        if not selected:
            messagebox.showwarning("Remove", "Select account(s).")
            return
        names = [a.get("name", "?") for a in selected]
        if not messagebox.askyesno("Confirm", f"Remove:\n{', '.join(names)}?"):
            return
        names_set = set(names)
        self.accounts = [a for a in self.accounts if a.get("name") not in names_set]
        try:
            save_accounts_ui(self.accounts)
        except (OSError, SecurityError) as e:
            messagebox.showerror("Error", str(e))
            self._refresh_accounts_list()
            return
        for n in names:
            self._session_valid.pop(n, None)
        self._refresh_accounts_list()

    def check_all_sessions(self) -> None:
        if not self.accounts:
            return
        self.status_var.set("Checking sessions...")
        self._set_buttons_running(True)

        def worker() -> None:
            results = launcher.validate_accounts(self.accounts)
            for acc in self.accounts:
                if results.get(acc["name"]):
                    ok, username = launcher.validate_account_session(acc)
                    if username:
                        app_storage.update_account_fields(acc["name"], roblox_username=username)
            self.after(0, lambda: self._on_sessions_checked(results))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sessions_checked(self, results: dict[str, bool]) -> None:
        self._session_valid = results
        ok = sum(1 for v in results.values() if v)
        bad = len(results) - ok
        self._refresh_accounts_list()
        self._set_buttons_running(False)
        self.status_var.set(f"Sessions: {ok} OK, {bad} invalid")
        if bad:
            messagebox.showwarning("Sessions", f"{bad} account(s) need session renewal (red).")
        else:
            messagebox.showinfo("Sessions", "All accounts have valid sessions.")

    def renew_selected_session(self) -> None:
        acc = self._get_single_selected_account()
        if not acc:
            messagebox.showwarning("Renew", "Select exactly one account.")
            return
        if messagebox.askyesno("Renew session", f"Log in to renew '{acc['name']}'?"):
            self.login_with_browser(renew_name=acc["name"])

    def follow_user_selected(self) -> None:
        sel = self._get_selected_accounts()
        if not sel:
            messagebox.showwarning("Follow", "Select at least one account.")
            return
        self._start_follow_worker(sel)

    def follow_user_all(self) -> None:
        if not self.accounts:
            messagebox.showwarning("Follow", "No accounts saved.")
            return
        self._start_follow_worker(self.accounts)

    def _start_follow_worker(self, accounts: list[dict]) -> None:
        username = self.follow_username_var.get().strip()
        if not username:
            messagebox.showwarning("Follow", "Enter a Roblox username.")
            return

        if self.validate_before_var.get() and self._session_valid:
            accounts = [a for a in accounts if self._session_valid.get(a["name"], True)]
            if not accounts:
                messagebox.showwarning("Follow", "Selected accounts have invalid sessions.")
                return

        total = len(accounts)
        self._update_progress(0, f"Looking up @{username}...")
        debug = bool(self.debug_var.get())

        def on_progress(done: int, tot: int, name: str, status: str) -> None:
            pct = (done / tot * 100) if tot else 0
            if status == "done":
                msg = f"Follow @{username}: done"
            elif status == "following":
                msg = f"Following with {name}..."
            elif status == "already":
                msg = f"{name}: already following ({done}/{tot})"
            elif status == "failed":
                msg = f"{name}: failed ({done}/{tot})"
            else:
                msg = f"{name}: OK ({done}/{tot})"
            self.after(0, lambda p=pct, m=msg: self._update_progress(p, m))

        def worker() -> None:
            ok, already, fail, err = launcher.follow_accounts_to_user(
                accounts, username, debug=debug, on_progress=on_progress
            )
            self.after(0, lambda: self._on_follow_done(username, ok, already, fail, err))

        self._set_buttons_running(True)
        threading.Thread(target=worker, daemon=True).start()

    def _on_follow_done(
        self,
        username: str,
        ok_names: list[str],
        already_names: list[str],
        fail_names: list[str],
        global_error: str | None,
    ) -> None:
        self._set_buttons_running(False)
        if global_error:
            self._update_progress(0, global_error)
            messagebox.showerror("Follow", global_error)
            return
        ok_n, already_n, fail_n = len(ok_names), len(already_names), len(fail_names)
        summary = f"@{username}: {ok_n} new, {already_n} already, {fail_n} failed"
        self._update_progress(100, summary)
        if fail_n == 0:
            messagebox.showinfo("Follow", summary)
        else:
            messagebox.showwarning("Follow", summary + (f"\n\nFailed: {', '.join(fail_names)}" if fail_names else ""))

    def _get_single_selected_account(self) -> dict | None:
        sel = self._get_selected_accounts()
        return sel[0] if len(sel) == 1 else None

    def _get_selected_accounts(self) -> list[dict]:
        iids = self.accounts_tree.selection()
        by_name = {a["name"]: a for a in self.accounts}
        return [by_name[i] for i in iids if i in by_name]

    def _set_buttons_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for attr in (
            "add_account_btn",
            "delete_account_btn",
            "follow_btn",
            "join_server_btn",
            "launch_family_btn",
        ):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.configure(state=state)

    def _filter_valid_accounts(self, accounts: list[dict]) -> list[dict]:
        if not self.validate_before_var.get():
            return accounts
        if not self._session_valid:
            return accounts
        valid = [a for a in accounts if self._session_valid.get(a["name"], True)]
        skipped = [a["name"] for a in accounts if not self._session_valid.get(a["name"], True)]
        if skipped:
            messagebox.showwarning("Invalid accounts", "Skipped (expired session):\n" + ", ".join(skipped))
        return valid

    def _start_worker(self, accounts: list[dict], place_id: str | None = None, fps_limit: int = 0) -> None:
        place_id = place_id or self.place_var.get().strip() or "0"
        app_storage.add_place_to_history(place_id)
        self._refresh_place_history()
        self._persist_launch_settings()
        settings = app_storage.get_settings()
        debug = bool(self.debug_var.get())

        ok_roblox, roblox_exe = launcher.is_roblox_installed()
        if not ok_roblox or not roblox_exe:
            messagebox.showerror("Roblox", "Install Roblox from roblox.com/download")
            return

        accounts = self._filter_valid_accounts(accounts)
        if not accounts:
            messagebox.showwarning("Launch", "No accounts to launch.")
            return

        total = len(accounts)
        fps_limit = roblox_fps.normalize_fps_limit(fps_limit)
        fps_note = f" · {roblox_fps.fps_label(fps_limit)}" if fps_limit > 0 else ""
        self._update_progress(0, f"Preparing 0/{total}{fps_note}...")

        def on_progress(done: int, tot: int, name: str, status: str) -> None:
            pct = (done / tot * 100) if tot else 0
            msg = f"{name}: {status} ({done}/{tot})"
            self.after(0, lambda p=pct, m=msg: self._update_progress(p, m))

        def worker() -> None:
            try:
                accs = list(accounts)
                if self.validate_before_var.get():
                    self.after(0, lambda: self._update_progress(0, "Validating sessions..."))
                    results = launcher.validate_accounts(accs)
                    self.after(0, lambda r=results: setattr(self, "_session_valid", r))
                    self.after(0, self._refresh_accounts_list)
                    accs = [a for a in accs if results.get(a["name"], False)]
                    if not accs:
                        self.after(0, lambda: messagebox.showwarning("Launch", "No valid sessions."))
                        self.after(0, lambda: self._set_buttons_running(False))
                        return

                ok_names, fail_names = launcher.launch_accounts(
                    accs,
                    roblox_exe,
                    place_id=place_id,
                    fps_limit=fps_limit,
                    debug=debug,
                    settings=settings,
                    on_progress=on_progress,
                )
                self.after(0, lambda: self._on_launch_done(ok_names, fail_names))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self._set_buttons_running(False))

        self._set_buttons_running(True)
        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str) -> None:
        self._progress_label.set(msg)
        self.status_var.set(msg)

    def _on_launch_done(self, ok_names: list[str], fail_names: list[str]) -> None:
        self._set_buttons_running(False)
        ok_n, fail_n = len(ok_names), len(fail_names)
        summary = f"Done: {ok_n} OK, {fail_n} failed"
        self._update_progress(100, summary)

        if fail_n == 0:
            notifications.show_notification("MoreRobAccounts", f"Opened {ok_n} account(s).")
            messagebox.showinfo("Launch", f"Launched {ok_n} account(s).")
        else:
            notifications.show_notification("MoreRobAccounts", f"{ok_n} OK. Failed: {', '.join(fail_names)}")
            messagebox.showwarning("Launch", f"OK: {ok_n}\nFailed: {', '.join(fail_names)}")

    def launch_selected(self) -> None:
        sel = self._get_selected_accounts()
        if not sel:
            messagebox.showwarning("Launch", "Select at least one account.")
            return
        self._start_worker(sel)

    def launch_all(self) -> None:
        if not self.accounts:
            messagebox.showwarning("Launch", "No accounts.")
            return
        self._start_worker(self.accounts)

    def launch_family(self) -> None:
        fam_name = self.family_var.get().strip()
        if not fam_name:
            messagebox.showwarning("Family", "Select a family.")
            return
        family = app_storage.get_family_by_name(fam_name)
        if not family:
            messagebox.showerror("Family", f"Family '{fam_name}' not found.")
            return
        accounts = app_storage.resolve_family_accounts(family, self.accounts)
        if not accounts:
            messagebox.showwarning("Family", f"Family '{fam_name}' has no valid accounts.")
            return

        if self.use_family_place_var.get():
            place_id = family.get("place_id", "0")
            source = "family"
        else:
            place_id = self.place_var.get().strip() or "0"
            source = "Place ID field"

        if place_id == "0":
            if not messagebox.askyesno("Place ID 0", f"Place ID is 0 (from {source}). Continue?"):
                return

        fps_limit = int(family.get("fps_limit", 0) or 0)
        self._start_worker(accounts, place_id=place_id, fps_limit=fps_limit)


if __name__ == "__main__":
    if is_browser_login_worker_argv():
        raise SystemExit(run_browser_login_worker(sys.argv[2]))
    app = MoreRobAccountsUI()
    app.mainloop()
