"""
Prompt panel:
  - Button to view the built-in base prompt in a popup
  - Editable 'Additional Prompting' text area
  - Save / Load saved prompts
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from core import prompt_store
from core.base_prompt_store import get_base_prompt, save_base_prompt

class PromptPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._build_ui()
        self._refresh_prompt_toolbar()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)   # additional prompting expands

        # --- Row 0: "Additional Prompting (optional)" then View Base Prompt directly after ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            header,
            text="Additional Prompting (optional)",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            header,
            text="View Base Prompt",
            width=140,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._on_view_base_prompt,
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))

        # --- Row 1: editable additional prompting (expands) ---
        self._additional_box = ctk.CTkTextbox(self, wrap="word")
        self._additional_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        # --- Row 2: toolbar ---
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        toolbar.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            toolbar, text="Save Prompt", width=120, command=self._on_save
        ).grid(row=0, column=0, padx=(0, 8))

        self._delete_btn = ctk.CTkButton(
            toolbar,
            text="Delete…",
            width=90,
            fg_color=("gray65", "gray35"),
            hover_color=("gray55", "gray28"),
            command=self._on_delete,
        )
        self._delete_btn.grid(row=0, column=1, padx=(0, 8))

        self._load_btn = ctk.CTkButton(
            toolbar,
            text="Load saved…",
            width=120,
            command=self._on_open_load_dialog,
        )
        self._load_btn.grid(row=0, column=2, sticky="e")

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #
    def get_full_prompt(self) -> str:
        """Return the combined prompt sent to the AI."""
        base = get_base_prompt()
        additional = self._additional_box.get("1.0", "end").strip()
        if additional:
            return f"{base}\n\nAdditional Prompting:\n{additional}"
        return base

    def clear_additional(self) -> None:
        self._additional_box.delete("1.0", "end")

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def _on_view_base_prompt(self) -> None:
        _BasePromptViewer(self)

    def _on_save(self) -> None:
        additional = self._additional_box.get("1.0", "end").strip()
        if not additional:
            _show_info("Nothing to save", "Please enter additional prompting before saving.")
            return
        _SaveDialog(self, additional, on_saved=self._refresh_prompt_toolbar)

    def _on_delete(self) -> None:
        prompts = prompt_store.list_prompts()
        if not prompts:
            _show_info("Nothing to delete", "You have no saved prompts yet.")
            return
        _DeletePromptDialog(self, on_deleted=self._refresh_prompt_toolbar)

    def _on_open_load_dialog(self) -> None:
        prompts = prompt_store.list_prompts()
        if not prompts:
            _show_info("Nothing to load", "You have no saved prompts yet.")
            return

        def _apply(text: str) -> None:
            self._additional_box.delete("1.0", "end")
            self._additional_box.insert("1.0", text)

        _LoadPromptsDialog(self, prompts=prompts, on_loaded=_apply)

    def _refresh_prompt_toolbar(self) -> None:
        prompts = prompt_store.list_prompts()
        if not prompts:
            self._delete_btn.configure(state="disabled")
            self._load_btn.configure(state="disabled")
            return
        self._delete_btn.configure(state="normal")
        self._load_btn.configure(state="normal")


# ------------------------------------------------------------------ #
# Load saved prompts (multi-select: Ctrl+click / Cmd+click)
# ------------------------------------------------------------------ #
class _LoadPromptsDialog(ctk.CTkToplevel):
    """Insert selected prompt bodies into Additional Prompting, in list order."""

    _JOIN = "\n\n---\n\n"

    def __init__(
        self,
        parent,
        prompts: list,
        on_loaded: Callable[[str], None],
    ):
        super().__init__(parent)
        self._prompts = prompts
        self._on_loaded = on_loaded

        self.title("Load saved prompts")
        self.geometry("520x380")
        self.minsize(400, 280)
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text=(
                "Select one or more prompts. Ctrl+click (⌘+click on Mac) to select multiple. "
                "They are inserted in list order (top to bottom), separated by a line."
            ),
            wraplength=480,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))

        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        inner = tk.Frame(list_frame)
        inner.grid(row=0, column=0, sticky="nsew")
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=1)

        scroll = tk.Scrollbar(inner, orient=tk.VERTICAL)
        self._listbox = tk.Listbox(
            inner,
            selectmode=tk.EXTENDED,
            yscrollcommand=scroll.set,
            height=14,
            width=54,
            exportselection=False,
        )
        scroll.config(command=self._listbox.yview)
        self._listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        for p in prompts:
            self._listbox.insert(tk.END, f"{p.name} ({p.created_at[:10]})")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, pady=(0, 16))
        ctk.CTkButton(btn_frame, text="Load", width=100, command=self._do_load).pack(
            side="left", padx=8
        )
        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color=("gray65", "gray35"),
            hover_color=("gray55", "gray28"),
            command=self.destroy,
        ).pack(side="left", padx=8)

    def _do_load(self) -> None:
        selection = self._listbox.curselection()
        if not selection:
            _show_info("Nothing selected", "Select at least one prompt to load.", parent=self)
            return
        parts: list[str] = []
        for idx in sorted(selection):
            parts.append(self._prompts[idx].content)
        text = self._JOIN.join(parts)
        self._on_loaded(text)
        self.destroy()


# ------------------------------------------------------------------ #
# Base prompt viewer popup
# ------------------------------------------------------------------ #
class _BasePromptViewer(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Base Prompt")
        self.geometry("560x340")
        self.resizable(True, True)
        self.grab_set()
        self.lift()
        self.focus_force()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Base prompt (used for every analysis)",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        btn_font = ctk.CTkFont(size=11)
        self._edit_btn = ctk.CTkButton(
            header,
            text="Edit",
            width=56,
            height=26,
            font=btn_font,
            command=self._begin_edit,
        )
        self._edit_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))

        self._save_btn = ctk.CTkButton(
            header,
            text="Save",
            width=56,
            height=26,
            font=btn_font,
            command=self._save_edit,
        )
        self._cancel_btn = ctk.CTkButton(
            header,
            text="Cancel",
            width=56,
            height=26,
            font=btn_font,
            fg_color=("gray65", "gray35"),
            hover_color=("gray55", "gray28"),
            command=self._cancel_edit,
        )

        self._box = ctk.CTkTextbox(self, wrap="word", state="disabled", fg_color=("#f0f0f0", "#2b2b2b"))
        self._box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        self._box.configure(state="normal")
        self._box.insert("1.0", get_base_prompt())
        self._box.configure(state="disabled")

        self._close_btn = ctk.CTkButton(self, text="Close", width=100, command=self.destroy)
        self._close_btn.grid(row=2, column=0, pady=(0, 12))

    def _begin_edit(self) -> None:
        self._box.configure(state="normal")
        self._edit_btn.grid_remove()
        self._save_btn.grid(row=0, column=1, sticky="e", padx=(8, 4))
        self._cancel_btn.grid(row=0, column=2, sticky="e", padx=(0, 0))
        self._close_btn.configure(state="disabled")

    def _cancel_edit(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.insert("1.0", get_base_prompt())
        self._box.configure(state="disabled")
        self._save_btn.grid_remove()
        self._cancel_btn.grid_remove()
        self._edit_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._close_btn.configure(state="normal")

    def _save_edit(self) -> None:
        import tkinter.messagebox as mb

        text = self._box.get("1.0", "end")
        if not text.strip():
            mb.showwarning("Empty prompt", "The base prompt cannot be empty.", parent=self)
            return
        save_base_prompt(text.rstrip("\n"))
        self._box.configure(state="disabled")
        self._save_btn.grid_remove()
        self._cancel_btn.grid_remove()
        self._edit_btn.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self._close_btn.configure(state="normal")
        mb.showinfo("Saved", "Base prompt saved.", parent=self)


# ------------------------------------------------------------------ #
# Delete prompt dialog
# ------------------------------------------------------------------ #
class _DeletePromptDialog(ctk.CTkToplevel):
    def __init__(self, parent, on_deleted: Callable[[], None]):
        super().__init__(parent)
        self.title("Delete saved prompt")
        self.geometry("420x200")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self.focus_force()
        self._on_deleted = on_deleted

        prompts = prompt_store.list_prompts()
        self._id_map: dict[str, int] = {}
        labels = []
        for p in prompts:
            label = f"{p.name} ({p.created_at[:10]})"
            labels.append(label)
            self._id_map[label] = p.id

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Select a saved prompt to remove permanently:",
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        self._var = ctk.StringVar(value=labels[0])
        self._combo = ctk.CTkComboBox(self, values=labels, variable=self._var, width=360)
        self._combo.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")

        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.grid(row=2, column=0, pady=(0, 16))
        ctk.CTkButton(
            btn,
            text="Delete",
            width=100,
            fg_color=("#c0392b", "#922b21"),
            hover_color=("#a93226", "#7b241c"),
            command=self._do_delete,
        ).pack(side="left", padx=8)
        ctk.CTkButton(btn, text="Cancel", width=100, command=self.destroy).pack(side="left", padx=8)

    def _do_delete(self) -> None:
        import tkinter.messagebox as mb

        label = self._var.get().strip()
        pid = self._id_map.get(label)
        if pid is None:
            _show_info("Invalid selection", "Please choose a prompt from the list.", parent=self)
            return
        if not mb.askyesno(
            "Confirm delete",
            f"Permanently delete this saved prompt?\n\n{label}",
            parent=self,
        ):
            return
        prompt_store.delete_prompt(pid)
        self._on_deleted()
        self.destroy()


# ------------------------------------------------------------------ #
# Save dialog
# ------------------------------------------------------------------ #
class _SaveDialog(ctk.CTkToplevel):
    def __init__(self, parent, content: str, on_saved: Callable[[], None]):
        super().__init__(parent)
        self.title("Save Prompt")
        self.geometry("400x240")
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self._content = content
        self._on_saved = on_saved

        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Name *").grid(row=0, column=0, padx=12, pady=(16, 4), sticky="w")
        self._name_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self._name_var).grid(
            row=0, column=1, padx=(4, 12), pady=(16, 4), sticky="ew"
        )

        ctk.CTkLabel(self, text="Description").grid(row=1, column=0, padx=12, pady=4, sticky="nw")
        self._desc_box = ctk.CTkTextbox(self, height=80)
        self._desc_box.grid(row=1, column=1, padx=(4, 12), pady=4, sticky="ew")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=2, pady=12)
        ctk.CTkButton(btn_frame, text="Save", command=self._save, width=100).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, width=100).pack(side="left", padx=8)

    def _save(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            _show_info("Name required", "Please enter a name for this prompt.", parent=self)
            return
        description = self._desc_box.get("1.0", "end").strip()
        prompt_store.save_prompt(name, description, self._content)
        self._on_saved()
        self.destroy()


def _show_info(title: str, message: str, parent=None) -> None:
    import tkinter.messagebox as mb
    mb.showinfo(title, message, parent=parent)
