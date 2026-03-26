"""API settings panel — key, server URL, model names."""

from __future__ import annotations

import customtkinter as ctk


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        ctk.CTkLabel(self, text="API Settings", font=ctk.CTkFont(size=15, weight="bold")).grid(
            row=0, column=0, columnspan=2, pady=(10, 6), padx=12, sticky="w"
        )

        self._api_key_var = ctk.StringVar()
        self._base_url_var = ctk.StringVar(value="https://api.openai.com/v1")
        self._model1_var = ctk.StringVar(value="gpt-4o")
        self._model2_var = ctk.StringVar()

        fields = [
            ("API Key", self._api_key_var, True),
            ("Server URL", self._base_url_var, False),
            ("Model 1", self._model1_var, False),
            ("Model 2 (optional)", self._model2_var, False),
        ]

        for i, (label, var, is_secret) in enumerate(fields, start=1):
            ctk.CTkLabel(self, text=label, anchor="w").grid(
                row=i, column=0, padx=(12, 4), pady=4, sticky="w"
            )
            show = "*" if is_secret else ""
            entry = ctk.CTkEntry(self, textvariable=var, show=show, width=200)
            entry.grid(row=i, column=1, padx=(4, 12), pady=4, sticky="ew")

        self.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------ #
    # Public getters
    # ------------------------------------------------------------------ #
    @property
    def api_key(self) -> str:
        return self._api_key_var.get().strip()

    @property
    def base_url(self) -> str:
        return self._base_url_var.get().strip()

    @property
    def model1(self) -> str:
        return self._model1_var.get().strip()

    @property
    def model2(self) -> str:
        return self._model2_var.get().strip()

    def validate(self) -> str | None:
        """Return an error message string if settings are invalid, else None."""
        if not self.api_key:
            return "Please enter an API key."
        if not self.base_url:
            return "Please enter a server URL."
        if not self.model1:
            return "Please enter at least one model name."
        return None
