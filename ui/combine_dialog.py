"""
Combine Analysis dialog — lets the user pick a model to generate the
combined multi-model summary. The summary prompt is hidden by default
and viewable via a button.
"""

from __future__ import annotations

from typing import Callable, List

import customtkinter as ctk

from core.ai_client import SUMMARY_PROMPT


class CombineDialog(ctk.CTkToplevel):
    """
    on_generate(model_name) is called when the user confirms their selection.
    """

    def __init__(
        self,
        master,
        available_models: List[str],
        on_generate: Callable[[str], None],
    ):
        super().__init__(master)
        self.title("Generate Combined Summary")
        self.geometry("460x210")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()

        self._on_generate = on_generate
        self._available_models = available_models

        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Generate Combined Summary",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 10))

        ctk.CTkLabel(
            self,
            text="Select model:",
            anchor="w",
        ).grid(row=1, column=0, padx=(16, 8), pady=6, sticky="w")

        self._model_combo = ctk.CTkComboBox(
            self,
            values=self._available_models,
            width=260,
            state="normal",
        )
        if self._available_models:
            self._model_combo.set(self._available_models[0])
        self._model_combo.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

        self._status_label = ctk.CTkLabel(
            self, text="", text_color=("red", "#ff6b6b"), anchor="w", wraplength=400
        )
        self._status_label.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 4), sticky="w")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(8, 16))

        ctk.CTkButton(
            btn_frame,
            text="Generate Summary",
            width=160,
            command=self._on_confirm,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame,
            text="View Summary Prompt",
            width=160,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_view_prompt,
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=90,
            fg_color="gray40",
            hover_color="gray30",
            command=self.destroy,
        ).pack(side="left", padx=8)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _on_confirm(self) -> None:
        model = self._model_combo.get().strip()
        if not model:
            self._status_label.configure(text="Please select or enter a model name.")
            return
        self._on_generate(model)
        self.destroy()

    def _on_view_prompt(self) -> None:
        _PromptViewer(self)


# ------------------------------------------------------------------ #
# Summary prompt viewer popup
# ------------------------------------------------------------------ #
class _PromptViewer(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Summary Prompt (read-only)")
        self.geometry("640x480")
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        box = ctk.CTkTextbox(
            self, wrap="word", state="disabled", fg_color=("#f0f0f0", "#2b2b2b")
        )
        box.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        box.configure(state="normal")
        box.insert("1.0", SUMMARY_PROMPT)
        box.configure(state="disabled")

        ctk.CTkButton(self, text="Close", width=100, command=self.destroy).grid(
            row=1, column=0, pady=(0, 12)
        )
