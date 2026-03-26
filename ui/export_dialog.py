"""
Modal dialog to choose which analysis sections to include in a Word export.
"""

from __future__ import annotations

import tkinter.messagebox as mb
from typing import Callable, Dict, List

import customtkinter as ctk


class ExportSelectionDialog(ctk.CTkToplevel):
    """
    on_confirm(selected_keys) is called with the list of checked section names,
    then this window is destroyed.
    """

    def __init__(
        self,
        parent,
        results: Dict[str, str],
        on_confirm: Callable[[List[str]], None],
    ):
        super().__init__(parent)
        self._results = results
        self._on_confirm = on_confirm
        self._checkboxes: dict[str, ctk.CTkCheckBox] = {}
        self._vars: dict[str, ctk.BooleanVar] = {}

        self.title("Export to Word — select sections")
        self.geometry("420x360")
        self.resizable(True, True)
        self.minsize(360, 280)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Choose which analyses to include in the report:",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 8))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)

        for i, key in enumerate(results.keys()):
            var = ctk.BooleanVar(value=True)
            self._vars[key] = var
            cb = ctk.CTkCheckBox(scroll, text=key, variable=var)
            cb.grid(row=i, column=0, sticky="w", pady=4)
            self._checkboxes[key] = cb

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        ctk.CTkButton(
            btn_row, text="Select all", width=100, command=self._select_all
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Clear all", width=100, command=self._clear_all
        ).pack(side="left", padx=(0, 16))

        action = ctk.CTkFrame(self, fg_color="transparent")
        action.grid(row=3, column=0, pady=(0, 14))

        ctk.CTkButton(
            action, text="Export", width=120, command=self._on_export_click
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            action,
            text="Cancel",
            width=100,
            fg_color="gray40",
            hover_color="gray30",
            command=self.destroy,
        ).pack(side="left", padx=8)

    def _select_all(self) -> None:
        for var in self._vars.values():
            var.set(True)

    def _clear_all(self) -> None:
        for var in self._vars.values():
            var.set(False)

    def _on_export_click(self) -> None:
        selected = [k for k, var in self._vars.items() if var.get()]
        if not selected:
            mb.showwarning(
                "Nothing selected",
                "Please check at least one section to export.",
                parent=self,
            )
            return
        self._on_confirm(selected)
        self.destroy()
