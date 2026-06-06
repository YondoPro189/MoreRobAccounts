"""Ventana Families: ver, crear y agregar cuentas desde tabla."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import app_storage
import roblox_fps
import ui_theme as theme

FPS_CHOICES = ["Default"] + [str(f) for f in roblox_fps.FPS_PRESETS if f > 0]


class AddAccountsTableDialog(tk.Toplevel):
    """Seleccionar cuentas de una tabla para agregarlas a una familia."""

    def __init__(
        self,
        parent: tk.Misc,
        family: dict,
        accounts: list[dict],
        on_saved,
    ) -> None:
        super().__init__(parent)
        self.family = family
        self.accounts = accounts
        self.on_saved = on_saved
        self.title(f"Add Accounts — {family['name']}")
        self.geometry("520x380")
        self.minsize(460, 320)
        self.configure(bg=theme.BG)
        self.transient(parent)
        self.grab_set()
        theme.apply_ttk_style(self)
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        theme.label(
            self,
            text=f"Select accounts for family '{self.family['name']}'",
            font=theme.FONT,
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))

        table_wrap = theme.frame(self)
        table_wrap.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        table_wrap.grid_columnconfigure(0, weight=1)
        table_wrap.grid_rowconfigure(0, weight=1)

        cols = ("username", "alias", "description")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("username", text="Username")
        self.tree.heading("alias", text="Alias")
        self.tree.heading("description", text="Description")
        self.tree.column("username", width=120, stretch=True, anchor="w")
        self.tree.column("alias", width=100, stretch=True, anchor="w")
        self.tree.column("description", width=160, stretch=True, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

        in_family = set(self.family.get("accounts", []))
        for acc in self.accounts:
            alias = acc.get("name", "?")
            username = acc.get("roblox_username") or alias
            desc = acc.get("description", "")
            self.tree.insert("", "end", iid=alias, values=(username, alias, desc))
            if alias in in_family:
                self.tree.selection_add(alias)

        theme.label(self, text="Tip: Ctrl+click to select multiple accounts.", fg=theme.MUTED, font=theme.FONT_SM).grid(
            row=2, column=0, sticky="w", padx=14
        )

        btns = tk.Frame(self, bg=theme.BG)
        btns.grid(row=3, column=0, sticky="ew", padx=14, pady=(8, 12))
        theme.button(btns, text="Add Selected", command=self._save).pack(side="left", padx=(0, 8))
        theme.button(btns, text="Cancel", command=self.destroy).pack(side="left")

    def _save(self) -> None:
        selected = list(self.tree.selection())
        if not selected:
            messagebox.showwarning("Add Accounts", "Select at least one account.", parent=self)
            return
        self.family["accounts"] = sorted(set(selected))
        families = app_storage.get_families()
        for i, fam in enumerate(families):
            if fam["name"] == self.family["name"]:
                families[i] = self.family
                break
        app_storage.save_families(families)
        self.on_saved()
        self.destroy()


class CreateFamilyDialog(tk.Toplevel):
    def __init__(self, parent, existing_names: list[str], on_created) -> None:
        super().__init__(parent)
        self.existing_names = existing_names
        self.on_created = on_created
        self.title("Create Family")
        self.geometry("320x160")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme.apply_ttk_style(self)

        theme.label(self, text="Family name").pack(anchor="w", padx=14, pady=(14, 4))
        self.name_var = tk.StringVar()
        theme.entry(self, textvariable=self.name_var).pack(fill="x", padx=14)

        theme.label(self, text="Place ID").pack(anchor="w", padx=14, pady=(8, 4))
        self.place_var = tk.StringVar(value="0")
        theme.entry(self, textvariable=self.place_var).pack(fill="x", padx=14)

        theme.label(self, text="FPS limit (per session)").pack(anchor="w", padx=14, pady=(8, 4))
        self.fps_var = tk.StringVar(value="Default")
        ttk.Combobox(self, textvariable=self.fps_var, values=FPS_CHOICES, state="readonly").pack(
            fill="x", padx=14
        )

        row = tk.Frame(self, bg=theme.BG)
        row.pack(fill="x", padx=14, pady=14)
        theme.button(row, text="Create", command=self._create).pack(side="left", padx=(0, 8))
        theme.button(row, text="Cancel", command=self.destroy).pack(side="left")

    def _create(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Create Family", "Enter a family name.", parent=self)
            return
        if name in self.existing_names:
            messagebox.showwarning("Create Family", f"Family '{name}' already exists.", parent=self)
            return
        place_id = self.place_var.get().strip() or "0"
        fps_limit = 0 if self.fps_var.get() == "Default" else roblox_fps.normalize_fps_limit(self.fps_var.get())
        self.on_created({"name": name, "place_id": place_id, "accounts": [], "fps_limit": fps_limit})
        self.destroy()


class EditFamilyDialog(tk.Toplevel):
    def __init__(self, parent, family: dict, on_saved) -> None:
        super().__init__(parent)
        self.family = family
        self.on_saved = on_saved
        self.title("Edit Family")
        self.geometry("320x200")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        theme.apply_ttk_style(self)

        theme.label(self, text="Place ID").pack(anchor="w", padx=14, pady=(14, 4))
        self.place_var = tk.StringVar(value=family.get("place_id", "0"))
        theme.entry(self, textvariable=self.place_var).pack(fill="x", padx=14)

        theme.label(self, text="FPS limit (per session)").pack(anchor="w", padx=14, pady=(8, 4))
        fps = int(family.get("fps_limit", 0) or 0)
        self.fps_var = tk.StringVar(value=roblox_fps.fps_label(fps) if fps <= 0 else str(fps))
        ttk.Combobox(self, textvariable=self.fps_var, values=FPS_CHOICES, state="readonly").pack(
            fill="x", padx=14
        )

        row = tk.Frame(self, bg=theme.BG)
        row.pack(fill="x", padx=14, pady=14)
        theme.button(row, text="Save", command=self._save).pack(side="left", padx=(0, 8))
        theme.button(row, text="Cancel", command=self.destroy).pack(side="left")

    def _save(self) -> None:
        self.family["place_id"] = self.place_var.get().strip() or "0"
        fps_raw = self.fps_var.get()
        self.family["fps_limit"] = 0 if fps_raw == "Default" else roblox_fps.normalize_fps_limit(fps_raw)
        families = app_storage.get_families()
        for i, fam in enumerate(families):
            if fam["name"] == self.family["name"]:
                families[i] = self.family
                break
        app_storage.save_families(families)
        self.on_saved()
        self.destroy()


class FamilyManagerDialog(tk.Toplevel):
    def __init__(self, parent, accounts: list[dict], on_saved) -> None:
        super().__init__(parent)
        self.title("Families")
        self.geometry("440x360")
        self.minsize(400, 300)
        self.configure(bg=theme.BG)
        self.accounts = accounts
        self.on_saved = on_saved
        self.families = app_storage.get_families()
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        theme.apply_ttk_style(self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        theme.dialog_title_bar(self, "Families", on_close=self.destroy).grid(row=0, column=0, sticky="ew")

        outer = theme.frame(self)
        outer.grid(row=1, column=0, sticky="nsew", padx=14, pady=10)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        theme.inner_title_box(outer, "Families").grid(row=0, column=0, sticky="ew", padx=8, pady=8)

        list_area = tk.Frame(outer, bg=theme.BG)
        list_area.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        list_area.grid_columnconfigure(0, weight=1)
        list_area.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_area,
            bg=theme.BG,
            fg=theme.TEXT,
            selectbackground="#2a2a2a",
            selectforeground=theme.TEXT,
            activestyle="none",
            highlightthickness=0,
            borderwidth=0,
            font=theme.FONT,
            relief="flat",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_area, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_family_select)
        self.listbox.bind("<Double-1>", lambda _e: self._add_accounts())
        self.listbox.bind("<Delete>", lambda _e: self._remove_family())

        self.members_label = theme.label(outer, text="", fg=theme.MUTED, font=theme.FONT_SM)
        self.members_label.grid(row=2, column=0, sticky="w", padx=8, pady=(0, 4))

        bottom = tk.Frame(self, bg=theme.BG)
        bottom.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 12))
        theme.underlined_button(bottom, "Create Family", command=self._create_family).pack(side="left", padx=(0, 14))
        theme.underlined_button(bottom, "Edit Family", command=self._edit_family).pack(side="left", padx=(0, 14))
        theme.underlined_button(bottom, "Add Accounts", command=self._add_accounts).pack(side="left", padx=(0, 14))
        theme.underlined_button(bottom, "Remove Family", command=self._remove_family).pack(side="left")

        self._refresh_list()

    def _refresh_list(self) -> None:
        sel = self.listbox.curselection()
        sel_name = self.families[sel[0]]["name"] if sel else None
        self.listbox.delete(0, tk.END)
        restore_idx = None
        for i, fam in enumerate(self.families):
            n = len(fam.get("accounts", []))
            fps = int(fam.get("fps_limit", 0) or 0)
            fps_txt = roblox_fps.fps_label(fps)
            line = f"{fam['name']}  ·  Place {fam.get('place_id', '0')}  ·  {fps_txt}  ·  {n} account(s)"
            self.listbox.insert(tk.END, line)
            if fam["name"] == sel_name:
                restore_idx = i
        if restore_idx is not None:
            self.listbox.selection_set(restore_idx)
            self._on_family_select()
        else:
            self.members_label.configure(text="")

    def _selected_family(self) -> dict | None:
        idx = self.listbox.curselection()
        if not idx:
            return None
        i = idx[0]
        if 0 <= i < len(self.families):
            return self.families[i]
        return None

    def _on_family_select(self, _event=None) -> None:
        fam = self._selected_family()
        if not fam:
            self.members_label.configure(text="")
            return
        members = fam.get("accounts", [])
        fps = int(fam.get("fps_limit", 0) or 0)
        fps_txt = roblox_fps.fps_label(fps)
        if members:
            self.members_label.configure(text=f"FPS: {fps_txt}  ·  Accounts: " + ", ".join(members))
        else:
            self.members_label.configure(text=f"FPS: {fps_txt}  ·  No accounts in this family yet.")

    def _edit_family(self) -> None:
        fam = self._selected_family()
        if not fam:
            messagebox.showwarning("Families", "Select a family to edit.", parent=self)
            return

        def on_saved() -> None:
            self.families = app_storage.get_families()
            self._refresh_list()
            self.on_saved()

        EditFamilyDialog(self, fam, on_saved)

    def _create_family(self) -> None:
        names = [f["name"] for f in self.families]

        def on_created(fam: dict) -> None:
            self.families.append(fam)
            app_storage.save_families(self.families)
            self._refresh_list()
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(len(self.families) - 1)
            self._on_family_select()
            self.on_saved()

        CreateFamilyDialog(self, names, on_created)

    def _add_accounts(self) -> None:
        fam = self._selected_family()
        if not fam:
            messagebox.showwarning("Families", "Select a family first, or create one.", parent=self)
            return
        if not self.accounts:
            messagebox.showwarning("Families", "No saved accounts yet.", parent=self)
            return

        def on_saved() -> None:
            self.families = app_storage.get_families()
            self._refresh_list()
            self.on_saved()

        AddAccountsTableDialog(self, fam, self.accounts, on_saved)

    def _remove_family(self) -> None:
        fam = self._selected_family()
        if not fam:
            messagebox.showwarning("Families", "Select a family to remove.", parent=self)
            return
        if not messagebox.askyesno("Families", f"Remove family '{fam['name']}'?", parent=self):
            return
        self.families = [f for f in self.families if f["name"] != fam["name"]]
        app_storage.save_families(self.families)
        self._refresh_list()
        self.on_saved()


def pick_family_dialog(parent, families: list[dict]) -> str | None:
    names = [f["name"] for f in families]
    if not names:
        return simpledialog.askstring("Add to Family", "New family name:", parent=parent)
    dialog = tk.Toplevel(parent)
    dialog.title("Add to Family")
    dialog.geometry("280x160")
    dialog.configure(bg=theme.BG)
    dialog.transient(parent)
    dialog.grab_set()
    theme.apply_ttk_style(dialog)

    choice = tk.StringVar(value=names[0])
    theme.label(dialog, text="Select family:").pack(anchor="w", padx=12, pady=(12, 4))
    ttk.Combobox(dialog, textvariable=choice, values=names, state="readonly").pack(fill="x", padx=12)

    new_var = tk.BooleanVar(value=False)
    theme.wire_checkbutton(dialog, "Create new family", new_var).pack(anchor="w", padx=12, pady=8)
    new_name_var = tk.StringVar()
    theme.entry(dialog, textvariable=new_name_var).pack(fill="x", padx=12)

    result = {"name": None}

    def ok() -> None:
        name = new_name_var.get().strip() if new_var.get() else choice.get().strip()
        if not name:
            messagebox.showwarning("Family", "Enter a family name.", parent=dialog)
            return
        result["name"] = name
        dialog.destroy()

    theme.button(dialog, text="OK", command=ok).pack(pady=12)
    dialog.wait_window()
    return result["name"]
