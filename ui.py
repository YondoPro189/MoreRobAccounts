import threading
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import launcher
from security import SecurityError

try:
    from secure_login import is_browser_login_available, login_via_browser
except ImportError:

    def is_browser_login_available() -> bool:
        return False

    def login_via_browser(**kwargs):
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
    """Panel con scroll vertical; el ancho sigue al contenedor."""

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(
            self,
            bg=DarkTheme.BG,
            highlightthickness=0,
            borderwidth=0,
        )
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
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
        self.title("MoreRobAccounts")
        self.geometry("640x520")
        self.minsize(420, 380)
        self.configure(bg=DarkTheme.BG)

        self.accounts: list[dict] = load_accounts_ui()
        self._worker_thread: threading.Thread | None = None

        self._setup_theme()
        self._build_ui()
        self._refresh_accounts_list()

    def _setup_theme(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background=DarkTheme.BG, foreground=DarkTheme.TEXT, font=DarkTheme.FONT)
        style.configure("TFrame", background=DarkTheme.BG)
        style.configure("Card.TFrame", background=DarkTheme.CARD)

        style.configure(
            "Card.TLabelframe",
            background=DarkTheme.CARD,
            foreground=DarkTheme.MUTED,
            bordercolor=DarkTheme.BORDER,
            relief="flat",
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=DarkTheme.CARD,
            foreground=DarkTheme.TEXT,
            font=DarkTheme.FONT_SECTION,
        )

        style.configure("TLabel", background=DarkTheme.BG, foreground=DarkTheme.TEXT)
        style.configure("Card.TLabel", background=DarkTheme.CARD, foreground=DarkTheme.TEXT)
        style.configure("CardMuted.TLabel", background=DarkTheme.CARD, foreground=DarkTheme.MUTED, font=DarkTheme.FONT_SM)

        style.configure(
            "TEntry",
            fieldbackground=DarkTheme.INPUT,
            foreground=DarkTheme.TEXT,
            insertcolor=DarkTheme.TEXT,
            bordercolor=DarkTheme.BORDER,
        )
        style.configure("TCheckbutton", background=DarkTheme.CARD, foreground=DarkTheme.MUTED, font=DarkTheme.FONT_SM)
        style.map("TCheckbutton", background=[("active", DarkTheme.CARD)])

        btn_pad = (10, 5)
        style.configure("TButton", background=DarkTheme.CARD, foreground=DarkTheme.TEXT, bordercolor=DarkTheme.BORDER, padding=btn_pad)
        style.map("TButton", background=[("active", DarkTheme.BORDER), ("disabled", DarkTheme.SURFACE)])

        style.configure(
            "Accent.TButton",
            background=DarkTheme.ACCENT,
            foreground="#ffffff",
            bordercolor=DarkTheme.ACCENT,
            font=("Segoe UI Semibold", 9),
            padding=btn_pad,
        )
        style.map("Accent.TButton", background=[("active", DarkTheme.ACCENT_HOVER), ("disabled", DarkTheme.ACCENT_DIM)])

        style.configure("Danger.TButton", background=DarkTheme.SURFACE, foreground="#ff6b6b", bordercolor=DarkTheme.BORDER, padding=btn_pad)
        style.map("Danger.TButton", background=[("active", DarkTheme.ACCENT_DIM)])

        style.configure("Vertical.TScrollbar", background=DarkTheme.SURFACE, troughcolor=DarkTheme.BG, bordercolor=DarkTheme.BG, arrowcolor=DarkTheme.MUTED)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Header compacto
        header = tk.Frame(self, bg=DarkTheme.SURFACE, height=44)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="MoreRobAccounts",
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.TEXT,
            font=DarkTheme.FONT_TITLE,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=8)

        self.status_var = tk.StringVar(value="0 cuentas")
        tk.Label(
            header,
            textvariable=self.status_var,
            bg=DarkTheme.SURFACE,
            fg=DarkTheme.ACCENT,
            font=("Segoe UI Semibold", 9),
        ).grid(row=0, column=1, sticky="e", padx=12, pady=8)

        tk.Frame(self, bg=DarkTheme.ACCENT, height=2).grid(row=1, column=0, sticky="ew")

        # Cuerpo principal (grid responsive)
        body = ttk.Frame(self, padding=self.PAD)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)  # lista de cuentas crece

        # Zona superior con scroll (config + agregar)
        scroll = ScrollablePanel(body)
        scroll.grid(row=0, column=0, sticky="ew")
        top = scroll.inner
        top.columnconfigure(0, weight=1)

        cfg = ttk.LabelFrame(top, text=" Lanzamiento ", style="Card.TLabelframe", padding=self.CARD_PAD)
        cfg.grid(row=0, column=0, sticky="ew", pady=(0, self.PAD))
        cfg.columnconfigure(1, weight=1)

        ttk.Label(cfg, text="Place ID", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.place_var = tk.StringVar(value="0")
        ttk.Entry(cfg, textvariable=self.place_var, width=14).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.debug_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cfg, text="Debug", variable=self.debug_var).grid(row=0, column=2, sticky="w", padx=(12, 0))

        add_frame = ttk.LabelFrame(top, text=" Agregar cuenta ", style="Card.TLabelframe", padding=self.CARD_PAD)
        add_frame.grid(row=1, column=0, sticky="ew")
        add_frame.columnconfigure(1, weight=1)

        ttk.Label(add_frame, text="Alias", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        self.new_name_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_name_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self.login_browser_btn = ttk.Button(
            add_frame,
            text="Iniciar sesion con Roblox",
            style="Accent.TButton",
            command=self.login_with_browser,
        )
        self.login_browser_btn.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        if not launcher.is_frozen_app():
            self.manual_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                add_frame,
                text="Pegar cookie (avanzado)",
                variable=self.manual_var,
                command=self._toggle_manual_cookie,
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

            self.manual_frame = ttk.Frame(add_frame, style="Card.TFrame")
            self.manual_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            self.manual_frame.columnconfigure(1, weight=1)

            ttk.Label(self.manual_frame, text="Cookie", style="Card.TLabel").grid(row=0, column=0, sticky="w")
            self.new_cookie_var = tk.StringVar()
            ttk.Entry(self.manual_frame, textvariable=self.new_cookie_var, show="*").grid(
                row=0, column=1, sticky="ew", padx=(8, 0)
            )
            self.add_account_btn = ttk.Button(self.manual_frame, text="Guardar", command=self.add_account_manual)
            self.add_account_btn.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
            self.manual_frame.grid_remove()
        else:
            self.manual_var = tk.BooleanVar(value=False)
            self.new_cookie_var = tk.StringVar()
            ttk.Label(
                add_frame,
                text="Inicia sesion en la ventana que se abre. No cierres el navegador hasta ver el mensaje de exito.",
                style="CardMuted.TLabel",
                wraplength=560,
            ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # Lista de cuentas (expandible)
        acc = ttk.LabelFrame(body, text=" Cuentas ", style="Card.TLabelframe", padding=self.CARD_PAD)
        acc.grid(row=1, column=0, sticky="nsew", pady=(self.PAD, 0))
        acc.rowconfigure(0, weight=1)
        acc.columnconfigure(0, weight=1)

        list_frame = tk.Frame(acc, bg=DarkTheme.CARD)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.accounts_list = tk.Listbox(
            list_frame,
            selectmode="extended",
            height=4,
            bg=DarkTheme.INPUT,
            fg=DarkTheme.TEXT,
            selectbackground=DarkTheme.ACCENT,
            selectforeground="#ffffff",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=DarkTheme.BORDER,
            highlightcolor=DarkTheme.BORDER,
            borderwidth=0,
            font=DarkTheme.FONT,
            relief="flat",
        )
        self.accounts_list.grid(row=0, column=0, sticky="nsew")
        self.accounts_list.bind("<Delete>", lambda _e: self.delete_selected_account())

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.accounts_list.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.accounts_list.configure(yscrollcommand=sb.set)

        acc_btns = ttk.Frame(acc, style="Card.TFrame")
        acc_btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        acc_btns.columnconfigure(0, weight=1)

        self.delete_account_btn = ttk.Button(
            acc_btns,
            text="Eliminar",
            style="Danger.TButton",
            command=self.delete_selected_account,
        )
        self.delete_account_btn.grid(row=0, column=0, sticky="w")
        ttk.Label(acc_btns, text="Supr", style="CardMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(6, 0))

        # Footer fijo (siempre visible)
        footer = ttk.Frame(self, padding=(self.PAD, 4, self.PAD, self.PAD))
        footer.grid(row=3, column=0, sticky="ew")
        for c in range(4):
            footer.columnconfigure(c, weight=1)

        self.launch_all_btn = ttk.Button(footer, text="Lanzar todas", style="Accent.TButton", command=self.launch_all)
        self.launch_all_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.launch_selected_btn = ttk.Button(footer, text="Seleccionadas", command=self.launch_selected)
        self.launch_selected_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.reload_btn = ttk.Button(footer, text="Recargar", command=self.reload_accounts)
        self.reload_btn.grid(row=0, column=2, sticky="ew", padx=4)

        self.quit_btn = ttk.Button(footer, text="Salir", command=self.destroy)
        self.quit_btn.grid(row=0, column=3, sticky="ew", padx=(4, 0))

    def _refresh_accounts_list(self) -> None:
        self.accounts_list.delete(0, tk.END)
        self.accounts = load_accounts_ui()
        for a in self.accounts:
            self.accounts_list.insert(tk.END, f"  {a.get('name', '<sin nombre>')}")
        n = len(self.accounts)
        self.status_var.set(f"{n} cuenta{'s' if n != 1 else ''}")

    def reload_accounts(self) -> None:
        self._refresh_accounts_list()

    def _toggle_manual_cookie(self) -> None:
        if launcher.is_frozen_app():
            return
        if self.manual_var.get():
            self.manual_frame.grid()
        else:
            self.manual_frame.grid_remove()
            self.new_cookie_var.set("")

    def _save_account(self, name: str, cookie: str) -> bool:
        if any(a.get("name") == name for a in self.accounts):
            messagebox.showwarning("Aviso", f"Ya existe una cuenta llamada '{name}'.")
            return False

        self.accounts.append({"name": name, "roblosecurity": cookie})
        try:
            save_accounts_ui(self.accounts)
        except (OSError, SecurityError) as e:
            messagebox.showerror("Error", f"No se pudo guardar la cuenta:\n{e}")
            self.accounts.pop()
            return False

        self.new_name_var.set("")
        self.new_cookie_var.set("")
        self._refresh_accounts_list()
        return True

    def login_with_browser(self) -> None:
        if not is_browser_login_available():
            if launcher.is_frozen_app():
                messagebox.showerror(
                    "Login no disponible",
                    "Esta es la version LITE sin login por navegador.\n\n"
                    "Descarga la version COMPLETA desde GitHub Releases:\n"
                    "MoreRobAccounts-v1.0-win64.zip",
                )
            else:
                messagebox.showinfo(
                    "Instalar Playwright",
                    "pip install -r requirements-browser.txt\n"
                    "python -m playwright install chromium",
                )
            return

        browser_hint = "Microsoft Edge" if sys.platform == "win32" else "el navegador"
        self.status_var.set(f"Abriendo {browser_hint}...")

        def worker() -> None:
            cookie, username, error = login_via_browser(timeout_sec=300)
            if error or not cookie:
                err = error or "Sin sesion."
                self.after(0, lambda e=err: messagebox.showerror("Inicio de sesion", e))
                self.after(0, lambda: self.status_var.set("Error al iniciar sesion."))
                self.after(0, lambda: self._set_buttons_running(False))
                return

            display_name = self.new_name_var.get().strip() or (username or "Cuenta")

            def save_on_main() -> None:
                if self._save_account(display_name, cookie):
                    messagebox.showinfo("Listo", f"Cuenta '{display_name}' guardada cifrada.")
                    self.status_var.set(f"Cuenta '{display_name}' agregada.")
                self._set_buttons_running(False)

            self.after(0, save_on_main)

        self._set_buttons_running(True)
        threading.Thread(target=worker, daemon=True).start()

    def add_account_manual(self) -> None:
        name = self.new_name_var.get().strip()
        cookie = normalize_cookie(self.new_cookie_var.get())

        if not name:
            messagebox.showwarning("Aviso", "Nombre requerido (metodo manual).")
            return
        if not cookie or "TU_COOKIE" in cookie:
            messagebox.showwarning("Aviso", "Cookie invalida.")
            return
        if any(a.get("name") == name for a in self.accounts):
            messagebox.showwarning("Aviso", f"Ya existe '{name}'.")
            return
        if self._save_account(name, cookie):
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
        self._refresh_accounts_list()

    def _get_selected_accounts(self) -> list[dict]:
        idxs = list(self.accounts_list.curselection())
        return [self.accounts[i] for i in idxs if 0 <= i < len(self.accounts)]

    def _set_buttons_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for btn in (
            self.launch_selected_btn,
            self.launch_all_btn,
            self.reload_btn,
            self.add_account_btn,
            self.login_browser_btn,
            self.delete_account_btn,
        ):
            btn.configure(state=state)

    def _start_worker(self, accounts: list[dict]) -> None:
        place_id = self.place_var.get().strip() or "0"
        debug = bool(self.debug_var.get())

        roblox_exe = launcher.find_roblox_launcher()
        if not roblox_exe:
            messagebox.showerror("Error", "Roblox no encontrado.")
            return
        if not accounts:
            messagebox.showwarning("Aviso", "No hay cuentas seleccionadas.")
            return

        def worker() -> None:
            try:
                launcher.launch_accounts(accounts, roblox_exe, place_id=place_id, debug=debug)
                self.after(0, lambda: messagebox.showinfo("Listo", "Lanzamientos iniciados."))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self._set_buttons_running(False))

        self._set_buttons_running(True)
        threading.Thread(target=worker, daemon=True).start()

    def launch_selected(self) -> None:
        self._start_worker(self._get_selected_accounts())

    def launch_all(self) -> None:
        self._start_worker(self.accounts)


if __name__ == "__main__":
    app = MoreRobAccountsUI()
    app.mainloop()
