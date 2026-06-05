"""Diálogos para gestionar familias de lanzamiento."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

import app_storage

_BG = "#0a0a0a"
_INPUT = "#0f0f0f"
_TEXT = "#f2f2f2"
_ACCENT = "#e02c2c"
_FONT = ("Segoe UI", 9)


class FamilyManagerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, account_names: list[str], on_saved) -> None:
        super().__init__(parent)
        self.title("Familias de lanzamiento")
        self.configure(bg=_BG)
        self.resizable(True, True)
        self.minsize(420, 320)
        self.account_names = account_names
        self.on_saved = on_saved
        self.families = app_storage.get_families()
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text="Cada familia tiene un Place ID y las cuentas que se lanzan juntas.",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        body = ttk.Frame(self, padding=8)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            body,
            bg=_INPUT,
            fg=_TEXT,
            selectbackground=_ACCENT,
            selectforeground="#fff",
            highlightthickness=0,
            font=_FONT,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<Double-Button-1>", lambda _e: self._edit())

        sb = ttk.Scrollbar(body, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)

        btns = ttk.Frame(self, padding=8)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Agregar", command=self._add).pack(side="left", padx=4)
        ttk.Button(btns, text="Editar", command=self._edit).pack(side="left", padx=4)
        ttk.Button(btns, text="Eliminar", command=self._delete).pack(side="left", padx=4)
        ttk.Button(btns, text="Cerrar", command=self.destroy).pack(side="right", padx=4)

        self._refresh_list()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, tk.END)
        for fam in self.families:
            n = len(fam.get("accounts", []))
            self.listbox.insert(
                tk.END,
                f"{fam['name']}  |  Place {fam.get('place_id', '0')}  |  {n} cuenta(s)",
            )

    def _add(self) -> None:
        if self._edit_family(None):
            self._refresh_list()
            self.on_saved()

    def _edit(self) -> None:
        idx = self.listbox.curselection()
        if not idx:
            messagebox.showwarning("Aviso", "Selecciona una familia.", parent=self)
            return
        if self._edit_family(self.families[idx[0]]):
            self._refresh_list()
            self.on_saved()

    def _delete(self) -> None:
        idx = self.listbox.curselection()
        if not idx:
            return
        fam = self.families[idx[0]]
        if not messagebox.askyesno("Confirmar", f"Eliminar familia '{fam['name']}'?", parent=self):
            return
        del self.families[idx[0]]
        app_storage.save_families(self.families)
        self._refresh_list()
        self.on_saved()

    def _edit_family(self, existing: dict | None) -> bool:
        dialog = tk.Toplevel(self)
        dialog.title("Editar familia" if existing else "Nueva familia")
        dialog.configure(bg=_BG)
        dialog.transient(self)
        dialog.grab_set()

        name_var = tk.StringVar(value=existing["name"] if existing else "")
        place_var = tk.StringVar(value=existing.get("place_id", "0") if existing else "0")
        selected = set(existing.get("accounts", []) if existing else [])

        ttk.Label(dialog, text="Nombre familia").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(dialog, textvariable=name_var, width=28).grid(row=0, column=1, padx=8, pady=4)
        ttk.Label(dialog, text="Place ID").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(dialog, textvariable=place_var, width=28).grid(row=1, column=1, padx=8, pady=4)

        ttk.Label(dialog, text="Cuentas").grid(row=2, column=0, sticky="nw", padx=8, pady=4)
        lb = tk.Listbox(
            dialog,
            selectmode="extended",
            height=8,
            bg=_INPUT,
            fg=_TEXT,
            selectbackground=_ACCENT,
            width=32,
        )
        lb.grid(row=2, column=1, padx=8, pady=4, sticky="ew")
        for i, name in enumerate(self.account_names):
            lb.insert(tk.END, name)
            if name in selected:
                lb.selection_set(i)

        result = {"ok": False}

        def save() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Aviso", "Nombre requerido.", parent=dialog)
                return
            idxs = lb.curselection()
            accounts = [self.account_names[i] for i in idxs]
            if not accounts:
                messagebox.showwarning("Aviso", "Selecciona al menos una cuenta.", parent=dialog)
                return
            fam = {
                "name": name,
                "place_id": place_var.get().strip() or "0",
                "accounts": accounts,
            }
            if existing:
                existing.update(fam)
            else:
                if any(f["name"] == name for f in self.families):
                    messagebox.showwarning("Aviso", "Ya existe esa familia.", parent=dialog)
                    return
                self.families.append(fam)
            app_storage.save_families(self.families)
            result["ok"] = True
            dialog.destroy()

        btns = ttk.Frame(dialog)
        btns.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="Guardar", command=save).pack(side="left", padx=8)
        ttk.Button(btns, text="Cancelar", command=dialog.destroy).pack(side="left", padx=8)
        dialog.wait_window()
        return result["ok"]
