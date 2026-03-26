"""
API Setup dialog — shown on startup if settings are missing or the server
is unreachable, and accessible any time via the 'API Settings' button.
Only handles API key and server URL (model selection lives on the main screen).
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

import customtkinter as ctk

from core.config_store import AppConfig, save_config, test_connection


class ApiSetupDialog(ctk.CTkToplevel):
    """
    Modal dialog for entering API key and server URL.
    on_success(cfg) is called with the saved AppConfig when the user saves.
    """

    def __init__(
        self,
        master,
        config: AppConfig,
        on_success: Callable[[AppConfig], None],
        require_valid: bool = False,
    ):
        super().__init__(master)
        self._cfg = config
        self._on_success = on_success
        self._require_valid = require_valid

        self.title("API Settings")
        self.geometry("460x240")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        self._build_ui()
        self._populate(config)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="API Configuration",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(16, 12), padx=16, sticky="w")

        # Row 1 — API Key
        ctk.CTkLabel(self, text="API Key *", anchor="w").grid(
            row=1, column=0, padx=(16, 8), pady=6, sticky="w"
        )
        self._key_entry = ctk.CTkEntry(self, show="*", width=280)
        self._key_entry.grid(row=1, column=1, padx=(0, 16), pady=6, sticky="ew")

        # Row 2 — Server URL
        ctk.CTkLabel(self, text="Server URL *", anchor="w").grid(
            row=2, column=0, padx=(16, 8), pady=6, sticky="w"
        )
        self._url_entry = ctk.CTkEntry(self, width=280)
        self._url_entry.grid(row=2, column=1, padx=(0, 16), pady=6, sticky="ew")

        # Row 3 — status
        self._status_label = ctk.CTkLabel(
            self, text="", wraplength=420, anchor="w"
        )
        self._status_label.grid(row=3, column=0, columnspan=2, padx=16, pady=(6, 0), sticky="w")

        # Row 4 — buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 16))

        self._test_btn = ctk.CTkButton(
            btn_frame, text="Test Connection", width=150, command=self._on_test
        )
        self._test_btn.pack(side="left", padx=8)

        self._save_btn = ctk.CTkButton(
            btn_frame, text="Save", width=100, command=self._on_save
        )
        self._save_btn.pack(side="left", padx=8)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color="gray40",
            hover_color="gray30",
            command=self._on_close_request,
        ).pack(side="left", padx=8)

    def _populate(self, cfg: AppConfig) -> None:
        self._key_entry.delete(0, "end")
        self._key_entry.insert(0, cfg.api_key)
        self._url_entry.delete(0, "end")
        self._url_entry.insert(0, cfg.base_url)

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _current_config(self) -> AppConfig:
        """Build a config from the dialog fields, preserving existing model selections."""
        return AppConfig(
            api_key=self._key_entry.get().strip(),
            base_url=self._url_entry.get().strip(),
            model1=self._cfg.model1,
            model2=self._cfg.model2,
            model3=self._cfg.model3,
        )

    def _on_test(self) -> None:
        cfg = self._current_config()
        if not cfg.api_is_complete():
            self._set_status("Please fill in API Key and Server URL before testing.", error=True)
            return

        self._set_status("Testing connection…", color=("gray50", "gray60"))
        self._test_btn.configure(state="disabled")
        self._save_btn.configure(state="disabled")

        def _run():
            err = test_connection(cfg)
            self.after(0, lambda: self._handle_test_result(err))

        threading.Thread(target=_run, daemon=True).start()

    def _handle_test_result(self, err: Optional[str]) -> None:
        self._test_btn.configure(state="normal")
        self._save_btn.configure(state="normal")
        if err:
            self._set_status(f"Connection failed: {err}", error=True)
        else:
            self._set_status("Connection successful!", color=("green", "#4caf50"))

    def _on_save(self) -> None:
        cfg = self._current_config()
        if not cfg.api_is_complete():
            self._set_status("Please fill in API Key and Server URL.", error=True)
            return
        save_config(cfg)
        self._on_success(cfg)
        self.destroy()

    def _on_close_request(self) -> None:
        if self._require_valid:
            import tkinter.messagebox as mb
            mb.showwarning(
                "Settings required",
                "API key and server URL must be configured before using the application.",
                parent=self,
            )
        else:
            self.destroy()

    def _set_status(
        self,
        msg: str,
        error: bool = False,
        color: tuple | str | None = None,
    ) -> None:
        if color is not None:
            self._status_label.configure(text=msg, text_color=color)
        elif error:
            self._status_label.configure(text=msg, text_color=("red", "#ff6b6b"))
        else:
            self._status_label.configure(text=msg, text_color=("gray50", "gray60"))
