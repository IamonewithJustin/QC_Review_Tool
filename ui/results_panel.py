"""
Results panel — tabbed display of per-model analysis output + export button.
The reserved tab name "Summary" holds the combined multi-model summary.
"""

from __future__ import annotations

import tkinter.filedialog as fd
import tkinter.messagebox as mb
from pathlib import Path
from typing import Dict

import customtkinter as ctk

from core import report_exporter
from ui.export_dialog import ExportSelectionDialog

SUMMARY_TAB = "📋 Summary"


class ResultsPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._results: Dict[str, str] = {}        # model_name -> text
        self._summary_text: str = ""
        self._document_filename: str = "document"
        self._tabs: Dict[str, ctk.CTkTextbox] = {}
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="Analysis Results", font=ctk.CTkFont(size=15, weight="bold"), anchor="w"
        ).grid(row=0, column=0, sticky="w")

        # Export control lives on the main window (left column); optional for tests
        self._export_btn: ctk.CTkButton | None = None

        self._tab_view = ctk.CTkTabview(self)
        self._tab_view.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))

        self._placeholder_label = ctk.CTkLabel(
            self._tab_view,
            text="Run an analysis to see results here.",
            text_color=("gray60", "gray40"),
        )
        self._placeholder_label.place(relx=0.5, rely=0.45, anchor="center")

    # ------------------------------------------------------------------ #
    # Public API — model tabs
    # ------------------------------------------------------------------ #
    def prepare_model_tab(self, model_name: str, ready_event=None) -> None:
        """
        Create (or clear) a tab for the given model.
        If ready_event is provided, sets it once the tab is fully constructed
        so the worker thread knows it is safe to start streaming.
        """
        try:
            self._placeholder_label.place_forget()

            # Add tab only if it doesn't already exist (avoid private _tab_dict)
            try:
                self._tab_view.add(model_name)
            except Exception:
                pass  # tab already exists; clear its content below

            tab = self._tab_view.tab(model_name)
            if model_name not in self._tabs:
                box = ctk.CTkTextbox(tab, wrap="word", state="disabled")
                box.pack(fill="both", expand=True)
                self._tabs[model_name] = box
            else:
                box = self._tabs[model_name]
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.configure(state="disabled")

            self._tab_view.set(model_name)
            self._results[model_name] = ""
        except Exception as exc:
            import logging
            logging.error("prepare_model_tab failed for %s: %s", model_name, exc)
        finally:
            if ready_event is not None:
                ready_event.set()

    def append_chunk(self, model_name: str, chunk: str) -> None:
        if model_name not in self._tabs:
            return
        box = self._tabs[model_name]
        box.configure(state="normal")
        box.insert("end", chunk)
        box.configure(state="disabled")
        box.see("end")
        self._results[model_name] = self._results.get(model_name, "") + chunk

    def append_error(self, model_name: str, error: str) -> None:
        if model_name not in self._tabs:
            self.prepare_model_tab(model_name)
        box = self._tabs[model_name]
        box.configure(state="normal")
        box.insert("end", f"\n\n[ERROR: {error}]")
        box.configure(state="disabled")

    def set_export_button(self, button: ctk.CTkButton | None) -> None:
        """Wire the Export to Word control from the main window."""
        self._export_btn = button

    def mark_complete(self) -> None:
        """Enable export once all models are done."""
        if self._results and self._export_btn is not None:
            self._export_btn.configure(state="normal")

    def get_model_results(self) -> Dict[str, str]:
        """Return the per-model results dict (excludes the summary tab)."""
        return {k: v for k, v in self._results.items() if k != SUMMARY_TAB}

    def set_document_filename(self, filename: str) -> None:
        self._document_filename = filename

    def clear(self) -> None:
        """Reset everything before a new analysis run."""
        for name in list(self._tabs.keys()):
            try:
                self._tab_view.delete(name)
            except Exception:
                pass
        self._tabs.clear()
        self._results.clear()
        self._summary_text = ""
        if self._export_btn is not None:
            self._export_btn.configure(state="disabled")
        self._placeholder_label.place(relx=0.5, rely=0.45, anchor="center")

    # ------------------------------------------------------------------ #
    # Public API — summary tab
    # ------------------------------------------------------------------ #
    def prepare_summary_tab(self, ready_event=None) -> None:
        """
        Create or clear the Summary tab and switch to it.
        Sets ready_event when done so the worker can start streaming.
        """
        try:
            self._placeholder_label.place_forget()
            self._summary_text = ""

            try:
                self._tab_view.add(SUMMARY_TAB)
            except Exception:
                pass  # already exists

            tab = self._tab_view.tab(SUMMARY_TAB)
            if SUMMARY_TAB not in self._tabs:
                box = ctk.CTkTextbox(tab, wrap="word", state="disabled")
                box.pack(fill="both", expand=True)
                self._tabs[SUMMARY_TAB] = box
            else:
                box = self._tabs[SUMMARY_TAB]
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.configure(state="disabled")

            self._tab_view.set(SUMMARY_TAB)
            self._results[SUMMARY_TAB] = ""
        except Exception as exc:
            import logging
            logging.error("prepare_summary_tab failed: %s", exc)
        finally:
            if ready_event is not None:
                ready_event.set()

    def append_summary_chunk(self, chunk: str) -> None:
        if SUMMARY_TAB not in self._tabs:
            return
        box = self._tabs[SUMMARY_TAB]
        box.configure(state="normal")
        box.insert("end", chunk)
        box.configure(state="disabled")
        box.see("end")
        self._summary_text += chunk
        self._results[SUMMARY_TAB] = self._summary_text

    def append_summary_error(self, error: str) -> None:
        if SUMMARY_TAB not in self._tabs:
            self.prepare_summary_tab()
        box = self._tabs[SUMMARY_TAB]
        box.configure(state="normal")
        box.insert("end", f"\n\n[ERROR: {error}]")
        box.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #
    def open_export_dialog(self) -> None:
        """Start the export-to-Word flow (same as former header button)."""
        self._on_export()

    def _on_export(self) -> None:
        if not self._results:
            mb.showinfo("Nothing to export", "Run an analysis first.")
            return

        def _do_export(selected_keys: list[str]) -> None:
            filtered = {k: self._results[k] for k in selected_keys}
            stem = Path(self._document_filename).stem
            default_name = f"QC_Report_{stem}.docx"
            out_path = fd.asksaveasfilename(
                title="Save QC Report",
                defaultextension=".docx",
                filetypes=[("Word Document", "*.docx")],
                initialfile=default_name,
            )
            if not out_path:
                return

            try:
                report_exporter.export_report(
                    results=filtered,
                    document_filename=self._document_filename,
                    output_path=out_path,
                )
                mb.showinfo("Exported", f"Report saved to:\n{out_path}")
            except Exception as exc:
                mb.showerror("Export failed", str(exc))

        ExportSelectionDialog(self, self._results, on_confirm=_do_export)
