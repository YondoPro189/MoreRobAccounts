import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import app_storage
import launcher
import notifications
from security import SecurityError
from ui_families import FamilyManagerDialog

try:
    from secure_login import (
        LOGIN_WORKER_FLAG,
        get_login_result_path,
        is_browser_login_available,
        is_browser_login_worker_argv,
        login_via_browser,
        read_login_result,
        run_browser_login_worker,
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


class DarkTheme:
    BG = "#0a0a0a"
    SURFACE = "#141414"
    CARD = "#1a1a1a"
    BORDER = "#2a2a2a"
    TEXT = "#f2f2f2"
    MUTED = "#8a8a8a"
    ACCENT = "#e02c2c"
    ACCENT_HOVER = "#ff4444"
    ACCENT_DIM = "#3d1515"
    INPUT = "#0f0f0f"
    ERROR = "#ff5555"
    FONT = ("Segoe UI", 9)
    FONT_SM = ("Segoe UI", 8)
    FONT_TITLE = ("Segoe UI Semibold", 13)
    FONT_SECTION = ("Segoe UI Semibold", 10)


def load_accounts_ui() -> list[dict]:
    return launcher.load_accounts()


def save_accounts_ui(accounts: list[dict]) -> None:
    launcher.save_accounts(accounts)


def normalize_cookie(cookie: str) -> str:
    cookie = cookie.strip()
    if len(cookie) >= 2 and cookie[0] in ("'", '"') and cookie[-1] == cookie[0]:
        cookie = cookie[1:-1].strip()
    return cookie


class ScrollablePanel(ttk.Frame):
    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, bg=DarkTheme.BG, highlightthickness=0, borderwidth=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)
        self._wheel_bound = False

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window_id, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _bind_wheel(self, _event: tk.Event) -> None:
        if not self._wheel_bound:
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
            self._wheel_bound = True

    def _unbind_wheel(self, _event: tk.Event) -> None:
        if self._wheel_bound:
            self.canvas.unbind_all("<MouseWheel>")
            self._wheel_bound = False


class MoreRobAccountsUI(tk.Tk):
    PAD = 8
    CARD_PAD = 10

    def __init__(self) -> None:
        super().__init__()
        self.title("MoreRobAccounts 2.0")
        self.geometry("720x640")
        self.minsize(480, 520)
        self.configure(bg=DarkTheme.BG)

        self.accounts: list[dict] = load_accounts_ui()
        self._session_valid: dict[str, bool] = {}
        self._login_proc: subprocess.Popen | None = None
        self._login_result_path: str | None = None
        self._renew_target: str | None = None
        self._window_icon: tk.PhotoImage | None = None
        self.settings = app_storage.get_settings()

        self._setup_theme()
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

    def _setup_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=DarkTheme.BG, foreground=DarkTheme.TEXT, font=DarkTheme.FONT)
        style.configure("TFrame", background=DarkTheme.BG)
        style.configure("Card.TFrame", background=DarkTheme.CARD)
        style.configure("Card.TLabelframe", background=DarkTheme.CARD, foreground=DarkTheme.MUTED, bordercolor=DarkTheme.BORDER, relief="flat")
        style.configure("Card.TLabelframe.Label", background=DarkTheme.CARD, foreground=DarkTheme.TEXT, font=DarkTheme.FONT_SECTION)
        style.configure("TLabel", background=DarkTheme.BG, foreground=DarkTheme.TEXT)
        style.configure("Card.TLabel", background=DarkTheme.CARD, foreground=DarkTheme.TEXT)
        style.configure("CardMuted.TLabel", background=DarkTheme.CARD, foreground=DarkTheme.MUTED, font=DarkTheme.FONT_SM)
        style.configure("TEntry", fieldbackground=DarkTheme.INPUT, foreground=DarkTheme.TEXT, insertcolor=DarkTheme.TEXT, bordercolor=DarkTheme.BORDER)
        style.configure("TCombobox", fieldbackground=DarkTheme.INPUT, foreground=DarkTheme.TEXT)
        style.configure("TCheckbutton", background=DarkTheme.CARD, foreground=DarkTheme.MUTED, font=DarkTheme.FONT_SM)
        style.map("TCheckbutton", background=[("active", DarkTheme.CARD)])
        btn_pad = (10, 5)
        style.configure("TButton", background=DarkTheme.CARD, foreground=DarkTheme.TEXT, bordercolor=DarkTheme.BORDER, padding=btn_pad)
        style.map("TButton", background=[("active", DarkTheme.BORDER), ("disabled", DarkTheme.SURFACE)])
        style.configure("Accent.TButton", background=DarkTheme.ACCENT, foreground="#ffffff", bordercolor=DarkTheme.ACCENT, font=("Segoe UI Semibold", 9), padding=btn_pad)
        style.map("Accent.TButton", background=[("active", DarkTheme.ACCENT_HOVER), ("disabled", DarkTheme.ACCENT_DIM)])
        style.configure("Danger.TButton", background=DarkTheme.SURFACE, foreground="#ff6b6b", bordercolor=DarkTheme.BORDER, padding=btn_pad)
        style.configure("Horizontal.TProgressbar", troughcolor=DarkTheme.INPUT, background=DarkTheme.ACCENT, bordercolor=DarkTheme.BORDER)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=DarkTheme.SURFACE, height=44)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="MoreRobAccounts 2.0", bg=DarkTheme.SURFACE, fg=DarkTheme.TEXT, font=DarkTheme.FONT_TITLE).grid(row=0, column=0, sticky="w", padx=12, pady=8)
        self.status_var = tk.StringVar(value="0 cuentas")
        tk.Label(header, textvariable=self.status_var, bg=DarkTheme.SURFACE, fg=DarkTheme.ACCENT, font=("Segoe UI Semibold", 9)).grid(row=0, column=1, sticky="e", padx=12, pady=8)
        tk.Frame(self, bg=DarkTheme.ACCENT, height=2).grid(row=1, column=0, sticky="ew")

        body = ttk.Frame(self, padding=self.PAD)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        scroll = ScrollablePanel(body)
        scroll.grid(row=0, column=0, sticky="ew")
        top = scroll.inner
        top.columnconfigure(0, weight=1)

        cfg = ttk.LabelFrame(top, text=" Lanzamiento ", style="Card.TLabelframe", padding=self.CARD_PAD)
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, self.PAD))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="Place ID", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.place_var = tk.StringVar(value="0")
        self.place_combo = ttk.Combobox(cfg, textvariable=self.place_var, width=16)
        self.place_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.place_combo.bind("<<ComboboxSelected>>", lambda _e: None)

        ttk.Label(cfg, text="Delay (s)", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.delay_var = tk.StringVar(value=str(self.settings.get("launch_delay_sec", 3)))
        delay_entry = ttk.Entry(cfg, textvariable=self.delay_var, width=6)
        delay_entry.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(cfg, text="si hay >3 cuentas", style="CardMuted.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(6, 0))

        fam_row = ttk.Frame(cfg, style="Card.TFrame")
        fam_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        fam_row.columnconfigure(1, weight=1)
        ttk.Label(fam_row, text="Familia", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.family_var = tk.StringVar()
        self.family_combo = ttk.Combobox(fam_row, textvariable=self.family_var, state="readonly", width=22)
        self.family_combo.grid(row=0, column=1, sticky="ew", padx=(8, 4))
        ttk.Button(fam_row, text="Lanzar Familia", style="Accent.TButton", command=self.launch_family).grid(row=0, column=2, padx=2)
        ttk.Button(fam_row, text="Gestionar", command=self.manage_families).grid(row=0, column=3, padx=2)

        self.use_family_place_var = tk.BooleanVar(
            value=bool(self.settings.get("use_family_place_id", True))
        )
        self.family_place_switch = ttk.Checkbutton(
            cfg,
            text="Lanzar familia con Place ID de la familia",
            variable=self.use_family_place_var,
            command=self._on_family_place_switch_changed,
        )
        self.family_place_switch.grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._update_family_place_switch_label()

        self.debug_var = tk.BooleanVar(value=False)
        self.validate_before_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(cfg, text="Debug", variable=self.debug_var).grid(row=4, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(cfg, text="Validar antes de lanzar", variable=self.validate_before_var).grid(row=4, column=1, columnspan=2, sticky="w", pady=(6, 0))

        add_frame = ttk.LabelFrame(top, text=" Agregar cuenta ", style="Card.TLabelframe", padding=self.CARD_PAD)
        add_frame.grid(row=1, column=0, sticky="ew")
        add_frame.columnconfigure(1, weight=1)

        ttk.Label(add_frame, text="Alias", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.new_name_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_name_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(add_frame, text="Grupo", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.new_group_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_group_var, width=12).grid(row=0, column=3, sticky="w", padx=(8, 0))

        self.login_browser_btn = ttk.Button(add_frame, text="Iniciar sesion con Roblox", style="Accent.TButton", command=self.login_with_browser)
        self.login_browser_btn.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))

        if not launcher.is_frozen_app():
            self.manual_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(add_frame, text="Pegar cookie (avanzado)", variable=self.manual_var, command=self._toggle_manual_cookie).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
            self.manual_frame = ttk.Frame(add_frame, style="Card.TFrame")
            self.manual_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 0))
            self.manual_frame.columnconfigure(1, weight=1)
            ttk.Label(self.manual_frame, text="Cookie", style="Card.TLabel").grid(row=0, column=0, sticky="w")
            self.new_cookie_var = tk.StringVar()
            ttk.Entry(self.manual_frame, textvariable=self.new_cookie_var, show="*").grid(row=0, column=1, sticky="ew", padx=(8, 0))
            self.add_account_btn = ttk.Button(self.manual_frame, text="Guardar", command=self.add_account_manual)
            self.add_account_btn.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
            self.manual_frame.grid_remove()
        else:
            self.manual_var = tk.BooleanVar(value=False)
            self.new_cookie_var = tk.StringVar()
            ttk.Label(add_frame, text="Inicia sesion en la ventana que se abre.", style="CardMuted.TLabel", wraplength=560).grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        acc = ttk.LabelFrame(body, text=" Cuentas ", style="Card.TLabelframe", padding=self.CARD_PAD)
        acc.grid(row=1, column=0, sticky="nsew", pady=(self.PAD, 0))
        acc.rowconfigure(0, weight=1)
        acc.columnconfigure(0, weight=1)

        list_frame = tk.Frame(acc, bg=DarkTheme.CARD)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.accounts_list = tk.Listbox(
            list_frame, selectmode="extended", height=6, bg=DarkTheme.INPUT, fg=DarkTheme.TEXT,
            selectbackground=DarkTheme.ACCENT, selectforeground="#ffffff", activestyle="none",
            highlightthickness=1, highlightbackground=DarkTheme.BORDER, highlightcolor=DarkTheme.BORDER,
            borderwidth=0, font=DarkTheme.FONT, relief="flat",
        )
        self.accounts_list.grid(row=0, column=0, sticky="nsew")
        self.accounts_list.bind("<Delete>", lambda _e: self.delete_selected_account())

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.accounts_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.accounts_list.configure(yscrollcommand=sb.set)

        acc_btns = ttk.Frame(acc, style="Card.TFrame")
        acc_btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.delete_account_btn = ttk.Button(acc_btns, text="Eliminar", style="Danger.TButton", command=self.delete_selected_account)
        self.delete_account_btn.grid(row=0, column=0, sticky="w")
        self.check_accounts_btn = ttk.Button(acc_btns, text="Comprobar sesiones", command=self.check_all_sessions)
        self.check_accounts_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.renew_account_btn = ttk.Button(acc_btns, text="Renovar seleccionada", command=self.renew_selected_session)
        self.renew_account_btn.grid(row=0, column=2, sticky="w", padx=(8, 0))

        footer = ttk.Frame(self, padding=(self.PAD, 4, self.PAD, self.PAD))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="")
        ttk.Label(footer, textvariable=self.progress_label, style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        self.progress_bar = ttk.Progressbar(footer, variable=self.progress_var, maximum=100, mode="determinate")
        self.progress_bar.grid(row=1, column=0, sticky="ew", pady=(2, 6))

        btn_row = ttk.Frame(footer)
        btn_row.grid(row=2, column=0, sticky="ew")
        for c in range(4):
            btn_row.columnconfigure(c, weight=1)
        self.launch_all_btn = ttk.Button(btn_row, text="Lanzar todas", style="Accent.TButton", command=self.launch_all)
        self.launch_all_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.launch_selected_btn = ttk.Button(btn_row, text="Seleccionadas", command=self.launch_selected)
        self.launch_selected_btn.grid(row=0, column=1, sticky="ew", padx=4)
        self.reload_btn = ttk.Button(btn_row, text="Recargar", command=self.reload_accounts)
        self.reload_btn.grid(row=0, column=2, sticky="ew", padx=4)
        self.quit_btn = ttk.Button(btn_row, text="Salir", command=self.destroy)
        self.quit_btn.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    def _check_roblox_installed(self) -> None:
        ok, path = launcher.is_roblox_installed()
        if ok:
            self.status_var.set(f"{len(self.accounts)} cuenta(s) | Roblox OK")
        else:
            self.status_var.set("Roblox no detectado")
            if messagebox.askyesno(
                "Roblox no encontrado",
                "No se detecto Roblox en esta PC.\n\n"
                "Descargalo desde roblox.com/download e instalalo.\n\n"
                "¿Abrir la pagina de descarga?",
            ):
                import webbrowser
                webbrowser.open("https://www.roblox.com/download")

    def _refresh_place_history(self) -> None:
        history = app_storage.get_place_history()
        self.place_combo["values"] = history
        if history and self.place_var.get() in ("", "0"):
            self.place_var.set(history[0])

    def _refresh_families_combo(self) -> None:
        families = app_storage.get_families()
        names = [f["name"] for f in families]
        self.family_combo["values"] = names
        if names and not self.family_var.get():
            self.family_var.set(names[0])

    def _persist_delay_setting(self) -> None:
        try:
            sec = max(0, min(60, int(self.delay_var.get().strip() or "3")))
        except ValueError:
            sec = 3
        self.settings["launch_delay_sec"] = sec
        self.settings["use_family_place_id"] = bool(self.use_family_place_var.get())
        app_storage.save_settings(self.settings)

    def _on_family_place_switch_changed(self) -> None:
        self._update_family_place_switch_label()
        self.settings["use_family_place_id"] = bool(self.use_family_place_var.get())
        app_storage.save_settings(self.settings)

    def _update_family_place_switch_label(self) -> None:
        if self.use_family_place_var.get():
            text = "Lanzar familia: Place ID de la familia"
        else:
            text = "Lanzar familia: Place ID del campo superior"
        self.family_place_switch.configure(text=text)

    def _refresh_accounts_list(self) -> None:
        self.accounts_list.delete(0, tk.END)
        self.accounts = load_accounts_ui()
        for a in self.accounts:
            name = a.get("name", "?")
            group = a.get("group", "").strip()
            prefix = f"[{group}] " if group else ""
            label = f"  {prefix}{name}"
            self.accounts_list.insert(tk.END, label)
            idx = self.accounts_list.size() - 1
            if name in self._session_valid and not self._session_valid[name]:
                self.accounts_list.itemconfig(idx, fg=DarkTheme.ERROR)
        n = len(self.accounts)
        invalid = sum(1 for v in self._session_valid.values() if not v)
        extra = f" | {invalid} invalida(s)" if invalid else ""
        self.status_var.set(f"{n} cuenta(s){extra}")

    def reload_accounts(self) -> None:
        self._refresh_families_combo()
        self._refresh_place_history()
        self._refresh_accounts_list()

    def manage_families(self) -> None:
        names = [a["name"] for a in self.accounts]
        FamilyManagerDialog(self, names, on_saved=self._refresh_families_combo)

    def _toggle_manual_cookie(self) -> None:
        if launcher.is_frozen_app():
            return
        if self.manual_var.get():
            self.manual_frame.grid()
        else:
            self.manual_frame.grid_remove()
            self.new_cookie_var.set("")

    def _save_account(self, name: str, cookie: str, group: str = "") -> bool:
        if any(a.get("name") == name for a in self.accounts):
            messagebox.showwarning("Aviso", f"Ya existe una cuenta llamada '{name}'.")
            return False
        self.accounts.append({"name": name, "roblosecurity": cookie, "group": group.strip()})
        try:
            save_accounts_ui(self.accounts)
        except (OSError, SecurityError) as e:
            messagebox.showerror("Error", f"No se pudo guardar la cuenta:\n{e}")
            self.accounts.pop()
            return False
        self._session_valid[name] = True
        self.new_name_var.set("")
        self.new_cookie_var.set("")
        self.new_group_var.set("")
        self._refresh_accounts_list()
        return True

    def login_with_browser(self, *, renew_name: str | None = None) -> None:
        if not is_browser_login_available():
            messagebox.showerror("Login no disponible", "Descarga la version COMPLETA desde GitHub Releases.")
            return
        self._renew_target = renew_name
        browser_hint = "Microsoft Edge" if sys.platform == "win32" else "el navegador"
        self.status_var.set(f"Abriendo {browser_hint}...")
        self._set_buttons_running(True)
        if launcher.is_frozen_app():
            self._start_browser_login_subprocess()
        else:
            self._start_browser_login_thread()

    def _finish_browser_login(self, cookie: str | None, username: str | None, error: str | None) -> None:
        renew = self._renew_target
        self._renew_target = None
        if error or not cookie:
            messagebox.showerror("Inicio de sesion", error or "Sin sesion.")
            self.status_var.set("Error al iniciar sesion.")
            self._set_buttons_running(False)
            return

        if renew:
            if app_storage.update_account_cookie(renew, cookie):
                self._session_valid[renew] = True
                messagebox.showinfo("Listo", f"Sesion de '{renew}' renovada.")
                self._refresh_accounts_list()
            else:
                messagebox.showerror("Error", f"No se encontro la cuenta '{renew}'.")
        else:
            display_name = self.new_name_var.get().strip() or (username or "Cuenta")
            group = self.new_group_var.get().strip()
            if self._save_account(display_name, cookie, group):
                messagebox.showinfo("Listo", f"Cuenta '{display_name}' guardada cifrada.")
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
            self._finish_browser_login(None, None, f"No se pudo iniciar el login:\n{exc}")
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
            cookie, username, error = None, None, f"Error leyendo resultado:\n{exc}"
        self._login_proc = None
        self._login_result_path = None
        self._finish_browser_login(cookie, username, error)

    def add_account_manual(self) -> None:
        name = self.new_name_var.get().strip()
        cookie = normalize_cookie(self.new_cookie_var.get())
        group = self.new_group_var.get().strip()
        if not name:
            messagebox.showwarning("Aviso", "Nombre requerido.")
            return
        if not cookie or "TU_COOKIE" in cookie:
            messagebox.showwarning("Aviso", "Cookie invalida.")
            return
        if self._save_account(name, cookie, group):
            messagebox.showinfo("Listo", f"Cuenta '{name}' guardada.")

    def delete_selected_account(self) -> None:
        idxs = list(self.accounts_list.curselection())
        if not idxs:
            messagebox.showwarning("Aviso", "Selecciona una cuenta.")
            return
        names = [self.accounts[i].get("name", "?") for i in idxs if 0 <= i < len(self.accounts)]
        if not messagebox.askyesno("Confirmar", f"Eliminar:\n{', '.join(names)}?"):
            return
        for i in sorted(idxs, reverse=True):
            if 0 <= i < len(self.accounts):
                del self.accounts[i]
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
        self.status_var.set("Comprobando sesiones...")
        self._set_buttons_running(True)

        def worker() -> None:
            results = launcher.validate_accounts(self.accounts)
            self.after(0, lambda: self._on_sessions_checked(results))

        threading.Thread(target=worker, daemon=True).start()

    def _on_sessions_checked(self, results: dict[str, bool]) -> None:
        self._session_valid = results
        ok = sum(1 for v in results.values() if v)
        bad = len(results) - ok
        self._refresh_accounts_list()
        self._set_buttons_running(False)
        self.status_var.set(f"Comprobacion: {ok} OK, {bad} invalida(s)")
        if bad:
            messagebox.showwarning("Sesiones", f"{bad} cuenta(s) necesitan renovar sesion (marcadas en rojo).")
        else:
            messagebox.showinfo("Sesiones", "Todas las cuentas tienen sesion valida.")

    def renew_selected_session(self) -> None:
        selected = self._get_selected_accounts()
        if len(selected) != 1:
            messagebox.showwarning("Aviso", "Selecciona exactamente una cuenta para renovar.")
            return
        name = selected[0]["name"]
        if messagebox.askyesno("Renovar sesion", f"Iniciar sesion en Roblox para renovar '{name}'?"):
            self.login_with_browser(renew_name=name)

    def _get_selected_accounts(self) -> list[dict]:
        idxs = list(self.accounts_list.curselection())
        return [self.accounts[i] for i in idxs if 0 <= i < len(self.accounts)]

    def _set_buttons_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for attr in (
            "launch_selected_btn", "launch_all_btn", "reload_btn", "login_browser_btn",
            "delete_account_btn", "add_account_btn", "check_accounts_btn", "renew_account_btn",
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
            messagebox.showwarning(
                "Cuentas invalidas",
                "Se omitiran (sesion caducada):\n" + ", ".join(skipped),
            )
        return valid

    def _start_worker(self, accounts: list[dict], place_id: str | None = None) -> None:
        place_id = (place_id or self.place_var.get().strip() or "0")
        app_storage.add_place_to_history(place_id)
        self._refresh_place_history()
        self._persist_delay_setting()
        settings = app_storage.get_settings()
        debug = bool(self.debug_var.get())

        ok_roblox, roblox_exe = launcher.is_roblox_installed()
        if not ok_roblox or not roblox_exe:
            messagebox.showerror("Roblox no encontrado", "Instala Roblox desde roblox.com/download")
            return

        accounts = self._filter_valid_accounts(accounts)
        if not accounts:
            messagebox.showwarning("Aviso", "No hay cuentas para lanzar.")
            return

        total = len(accounts)
        self.progress_var.set(0)
        self.progress_label.set(f"Preparando 0/{total}...")

        def on_progress(done: int, tot: int, name: str, status: str) -> None:
            pct = (done / tot * 100) if tot else 0
            msg = f"{name}: {status} ({done}/{tot})"
            self.after(0, lambda: self._update_progress(pct, msg))

        def worker() -> None:
            try:
                accs = list(accounts)
                if self.validate_before_var.get():
                    self.after(0, lambda: self.progress_label.set("Validando sesiones..."))
                    results = launcher.validate_accounts(accs)
                    self.after(0, lambda r=results: setattr(self, "_session_valid", r))
                    self.after(0, self._refresh_accounts_list)
                    accs = [a for a in accs if results.get(a["name"], False)]
                    if not accs:
                        self.after(0, lambda: messagebox.showwarning("Aviso", "Ninguna cuenta tiene sesion valida."))
                        self.after(0, lambda: self._set_buttons_running(False))
                        return

                ok_names, fail_names = launcher.launch_accounts(
                    accs, roblox_exe, place_id=place_id, debug=debug,
                    settings=settings, on_progress=on_progress,
                )
                self.after(0, lambda: self._on_launch_done(ok_names, fail_names))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.after(0, lambda: self._set_buttons_running(False))

        self._set_buttons_running(True)
        threading.Thread(target=worker, daemon=True).start()

    def _update_progress(self, pct: float, msg: str) -> None:
        self.progress_var.set(pct)
        self.progress_label.set(msg)

    def _on_launch_done(self, ok_names: list[str], fail_names: list[str]) -> None:
        self.progress_var.set(100)
        self._set_buttons_running(False)
        ok_n, fail_n = len(ok_names), len(fail_names)
        self.progress_label.set(f"Listo: {ok_n} OK, {fail_n} fallidas")
        self.status_var.set(self.progress_label.get())

        if fail_n == 0:
            notifications.show_notification(
                "MoreRobAccounts",
                f"Se abrieron {ok_n} cuenta(s) correctamente.",
            )
            messagebox.showinfo("Listo", f"Se lanzaron {ok_n} cuenta(s).")
        else:
            notifications.show_notification(
                "MoreRobAccounts",
                f"{ok_n} OK. Fallaron: {', '.join(fail_names)}",
            )
            messagebox.showwarning(
                "Lanzamiento parcial",
                f"Exitosas: {ok_n}\nFallidas: {', '.join(fail_names)}",
            )

    def launch_selected(self) -> None:
        sel = self._get_selected_accounts()
        if not sel:
            messagebox.showwarning("Aviso", "Selecciona al menos una cuenta.")
            return
        self._start_worker(sel)

    def launch_all(self) -> None:
        if not self.accounts:
            messagebox.showwarning("Aviso", "No hay cuentas.")
            return
        self._start_worker(self.accounts)

    def launch_family(self) -> None:
        fam_name = self.family_var.get().strip()
        if not fam_name:
            messagebox.showwarning("Aviso", "Selecciona una familia.")
            return
        family = app_storage.get_family_by_name(fam_name)
        if not family:
            messagebox.showerror("Error", f"Familia '{fam_name}' no encontrada.")
            return
        accounts = app_storage.resolve_family_accounts(family, self.accounts)
        if not accounts:
            messagebox.showwarning("Aviso", f"La familia '{fam_name}' no tiene cuentas validas.")
            return

        if self.use_family_place_var.get():
            place_id = family.get("place_id", "0")
            source = "familia"
        else:
            place_id = self.place_var.get().strip() or "0"
            source = "campo Place ID"

        if place_id == "0":
            if not messagebox.askyesno(
                "Place ID 0",
                f"Place ID es 0 (origen: {source}).\n¿Continuar igual?",
            ):
                return

        self._start_worker(accounts, place_id=place_id)


if __name__ == "__main__":
    if is_browser_login_worker_argv():
        raise SystemExit(run_browser_login_worker(sys.argv[2]))
    app = MoreRobAccountsUI()
    app.mainloop()
