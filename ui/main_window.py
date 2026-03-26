"""
Main application window.
Layout (2 columns, no sidebar):
  Top toolbar — title + connection status + API Settings button
  Left column — document + supporting files + model selector + prompt panel + run button
  Right column — results panel
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
import tkinter.filedialog as fd
import tkinter.messagebox as mb
from pathlib import Path

import customtkinter as ctk

from core import ai_client, document_reader, prompt_store
from core.config_store import AppConfig, fetch_models, load_config, save_config, test_connection
from core.pricing import calculate_cost, format_stats
from ui.prompt_panel import PromptPanel
from ui.results_panel import ResultsPanel
from ui.api_setup_dialog import ApiSetupDialog
from ui.combine_dialog import CombineDialog

# Buffers streamed text for the results panel; worker thread only appends (no Tk calls).
# Main thread flushes every CHUNK_FLUSH_MS so the event queue is not flooded.
CHUNK_FLUSH_MS = 50
_SUMMARY_CHUNK_KEY = "__summary__"


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        prompt_store.init_db()

        self.title("AI QC Document Reviewer")
        self.geometry("1180x840")
        self.minsize(860, 640)
        self.after(80, self._apply_maximized)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self._cfg: AppConfig = load_config()
        self._document_path: str | None = None
        self._document_text: str | None = None
        # Supporting reference files — list of (filename, extracted_text)
        self._supporting_files: list[tuple[str, str]] = []
        self._running = False
        self._skip_event: threading.Event = threading.Event()
        self._current_model: str = ""
        self._model_start_time: float = 0.0
        self._timer_after_id = None
        # Real-time token tracking (estimates while streaming)
        self._current_input_tok_est: int = 0   # fixed per run — chars of full message ÷ 4
        self._current_output_chars: int = 0    # grows with each chunk on the main thread
        # Accumulated run stats: {model: (elapsed_s, input_tok, output_tok)}
        self._run_stats: dict[str, tuple[float, int, int]] = {}
        # Finished model lines (time + tokens + cost); current model shown below via timer
        self._run_status_completed_lines: list[str] = []
        self._summary_model_name: str = ""

        self._chunk_lock = threading.Lock()
        self._chunk_buffer: dict[str, list[str]] = defaultdict(list)
        self._chunk_flush_timer_id = None

        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self._on_close_request)

        # After window is visible, check API settings
        self.after(200, self._check_api_on_startup)

    def _apply_maximized(self) -> None:
        """Start with the window maximized (Windows: zoomed; Linux: -zoomed)."""
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        # Left ~25% narrower vs prior 5; results ~20% wider vs prior 6 → 5×0.75 : 6×1.2 = 25:48
        self.grid_columnconfigure(0, weight=25)
        self.grid_columnconfigure(1, weight=48)
        self.grid_rowconfigure(1, weight=1)

        # ── Top toolbar ──────────────────────────────────────────────────
        toolbar = ctk.CTkFrame(self, height=44, corner_radius=0, fg_color=("gray88", "gray18"))
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            toolbar,
            text="AI QC Document Reviewer",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=10)

        self._api_status_label = ctk.CTkLabel(
            toolbar, text="", font=ctk.CTkFont(size=12), text_color=("gray50", "gray60")
        )
        self._api_status_label.grid(row=0, column=1, sticky="e", padx=(0, 8))

        ctk.CTkButton(
            toolbar,
            text="API Settings",
            width=120,
            height=28,
            command=self._open_api_settings,
        ).grid(row=0, column=2, sticky="e", padx=(0, 10), pady=8)

        # ── Left column ──────────────────────────────────────────────────
        left = ctk.CTkFrame(self, corner_radius=8)
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)   # prompt panel expands; all other rows are fixed

        self._build_document_picker(left)          # row 0 — document + supporting files
        self._build_model_selector(left)           # row 1
        self._prompt_panel = PromptPanel(left)
        self._prompt_panel.grid(row=2, column=0, sticky="nsew")

        # Separator line above action buttons
        ctk.CTkFrame(left, height=2, fg_color=("gray75", "gray30")).grid(
            row=3, column=0, sticky="ew", padx=12, pady=(4, 0)
        )

        # Run + Cancel on the same row
        run_row = ctk.CTkFrame(left, fg_color="transparent")
        run_row.grid(row=4, column=0, sticky="ew", padx=12, pady=(6, 4))
        run_row.grid_columnconfigure(0, weight=1)

        self._run_btn = ctk.CTkButton(
            run_row,
            text="▶  Run Analysis",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=46,
            command=self._on_run,
        )
        self._run_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._cancel_btn = ctk.CTkButton(
            run_row,
            text="⏭ Skip Model",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=46,
            width=110,
            fg_color=("#c0392b", "#922b21"),
            hover_color=("#a93226", "#7b241c"),
            command=self._on_skip,
        )
        # Hidden initially — shown only while running
        self._cancel_btn.grid(row=0, column=1)
        self._cancel_btn.grid_remove()

        self._combine_btn = ctk.CTkButton(
            left,
            text="🔀  Combine Analysis",
            font=ctk.CTkFont(size=13),
            height=36,
            state="disabled",
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            command=self._on_combine,
        )
        self._combine_btn.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 6))

        self._export_btn = ctk.CTkButton(
            left,
            text="Export to Word",
            font=ctk.CTkFont(size=13),
            height=36,
            state="disabled",
            fg_color=("#1f6aa5", "#144870"),
            hover_color=("#1a5a8f", "#10375a"),
            command=self._on_export_word,
        )
        self._export_btn.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 6))

        ctk.CTkButton(
            left,
            text="New QC Review",
            font=ctk.CTkFont(size=13),
            height=36,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            command=self._on_reset_form,
        ).grid(row=7, column=0, sticky="ew", padx=12, pady=(0, 6))

        ctk.CTkLabel(
            left,
            text="Progress",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray40", "gray55"),
            anchor="w",
        ).grid(row=8, column=0, sticky="w", padx=12, pady=(4, 2))

        self._status_box = ctk.CTkTextbox(
            left,
            height=120,
            wrap="word",
            state="disabled",
            font=ctk.CTkFont(size=12),
            fg_color=("#f4f4f4", "#2a2a2a"),
            text_color=("gray15", "gray90"),
        )
        self._status_box.grid(row=9, column=0, sticky="ew", padx=12, pady=(0, 8))

        # ── Right column ─────────────────────────────────────────────────
        self._results_panel = ResultsPanel(self, corner_radius=8)
        self._results_panel.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=10)
        self._results_panel.set_export_button(self._export_btn)

    # ------------------------------------------------------------------ #
    # Document picker (+ supporting files under main document)
    # ------------------------------------------------------------------ #
    _MAX_SUPPORTING = 10
    # Scrollable list: ~4 rows visible; up to 10 files — rest scrolls.
    # For a shorter box (~50% height), use: (_SUPPORTING_VISIBLE_ROWS * _SUPPORTING_ROW_APPROX_PX) // 2
    _SUPPORTING_ROW_APPROX_PX = 24
    _SUPPORTING_VISIBLE_ROWS = 4
    _SUPPORTING_LIST_HEIGHT = _SUPPORTING_VISIBLE_ROWS * _SUPPORTING_ROW_APPROX_PX

    def _build_document_picker(self, parent: ctk.CTkFrame) -> None:
        doc_frame = ctk.CTkFrame(parent, fg_color="transparent")
        doc_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        doc_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            doc_frame, text="Browse main document", width=150, command=self._on_browse
        ).grid(row=0, column=0, padx=(0, 8))

        self._doc_label = ctk.CTkLabel(
            doc_frame,
            text="No document selected",
            anchor="w",
            text_color=("gray50", "gray60"),
        )
        self._doc_label.grid(row=0, column=1, sticky="ew")

        self._supporting_browse_btn = ctk.CTkButton(
            doc_frame,
            text="Browse supporting files",
            width=150,
            command=self._on_browse_supporting,
        )
        self._supporting_browse_btn.grid(row=1, column=0, padx=(0, 8), pady=(6, 4), sticky="nw")

        self._supporting_count_label = ctk.CTkLabel(
            doc_frame,
            text=f"0 / {self._MAX_SUPPORTING}",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
        )
        self._supporting_count_label.grid(row=1, column=1, sticky="e", pady=(6, 4))

        self._supporting_scroll = ctk.CTkScrollableFrame(
            doc_frame,
            height=self._SUPPORTING_LIST_HEIGHT,
            fg_color="transparent",
        )
        self._supporting_scroll.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 4)
        )
        self._supporting_scroll.grid_columnconfigure(0, weight=1)

        self._refresh_supporting_files_list()

    def _refresh_supporting_files_list(self) -> None:
        """Rebuild the scrollable file list to match self._supporting_files."""
        for widget in self._supporting_scroll.winfo_children():
            widget.destroy()

        if not self._supporting_files:
            placeholder = ctk.CTkLabel(
                self._supporting_scroll,
                text="No supporting files added.",
                text_color=("gray55", "gray45"),
                font=ctk.CTkFont(size=10),
                anchor="w",
            )
            placeholder.grid(row=0, column=0, sticky="w", padx=2)
        else:
            for i, (fname, _) in enumerate(self._supporting_files):
                row_frame = ctk.CTkFrame(self._supporting_scroll, fg_color="transparent")
                row_frame.grid(row=i, column=0, sticky="ew", pady=2)
                row_frame.grid_columnconfigure(0, weight=1)

                # Full filename from the start; wrap within the panel (no leading truncation)
                ctk.CTkLabel(
                    row_frame,
                    text=fname,
                    font=ctk.CTkFont(size=10),
                    anchor="w",
                    justify="left",
                    wraplength=300,
                    text_color=("gray10", "gray90"),
                ).grid(row=0, column=0, sticky="ew", padx=(2, 4))

                ctk.CTkButton(
                    row_frame,
                    text="✕",
                    width=22,
                    height=18,
                    font=ctk.CTkFont(size=10),
                    fg_color=("gray70", "gray35"),
                    hover_color=("#c0392b", "#922b21"),
                    command=lambda idx=i: self._remove_supporting_file(idx),
                ).grid(row=0, column=1, padx=(0, 2))

        n = len(self._supporting_files)
        self._supporting_count_label.configure(text=f"{n} / {self._MAX_SUPPORTING}")
        state = "disabled" if n >= self._MAX_SUPPORTING else "normal"
        self._supporting_browse_btn.configure(state=state)

    def _remove_supporting_file(self, idx: int) -> None:
        if 0 <= idx < len(self._supporting_files):
            self._supporting_files.pop(idx)
            self._refresh_supporting_files_list()

    # ------------------------------------------------------------------ #
    # Model selector
    # ------------------------------------------------------------------ #
    def _build_model_selector(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent, corner_radius=6)
        frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 4))
        frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Header row: label + refresh button
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=3, sticky="ew", padx=6, pady=(8, 4))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Models",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=4)

        self._refresh_btn = ctk.CTkButton(
            header,
            text="Refresh List",
            width=100,
            height=24,
            font=ctk.CTkFont(size=11),
            command=self._on_refresh_models,
        )
        self._refresh_btn.grid(row=0, column=1, sticky="e", padx=4)

        self._model_fetch_label = ctk.CTkLabel(
            header, text="", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60")
        )
        self._model_fetch_label.grid(row=0, column=2, sticky="e", padx=(0, 4))

        # Three combo boxes — optional slots start with a sentinel so users can clear them
        _NONE = "—  None  —"
        labels = ["Model 1", "Model 2 (optional)", "Model 3 (optional)"]
        defaults = [self._cfg.model1, self._cfg.model2, self._cfg.model3]
        self._model_combos: list[ctk.CTkComboBox] = []
        self._NONE_SENTINEL = _NONE

        for col, (lbl, default) in enumerate(zip(labels, defaults)):
            ctk.CTkLabel(frame, text=lbl, font=ctk.CTkFont(size=11), anchor="w").grid(
                row=1, column=col, sticky="w", padx=(10, 4), pady=(0, 2)
            )
            initial_values = [_NONE] if col > 0 else []
            combo = ctk.CTkComboBox(
                frame,
                values=initial_values,
                width=160,
                state="normal",     # allows free-text entry alongside dropdown
            )
            # For optional combos, show sentinel when config is blank
            combo.set(default if default else (_NONE if col > 0 else ""))
            combo.grid(row=2, column=col, sticky="ew", padx=(10, 10), pady=(0, 10))
            self._model_combos.append(combo)

    def _get_selected_models(self) -> list[str]:
        """Return non-blank, non-sentinel model names from the three selectors."""
        sentinel = getattr(self, "_NONE_SENTINEL", "")
        return [
            c.get().strip()
            for c in self._model_combos
            if c.get().strip() and c.get().strip() != sentinel
        ]

    def _save_model_selections(self) -> None:
        """Persist current model selections back into config.json."""
        vals = [c.get().strip() for c in self._model_combos]
        self._cfg.model1 = vals[0] if len(vals) > 0 else ""
        self._cfg.model2 = vals[1] if len(vals) > 1 else ""
        self._cfg.model3 = vals[2] if len(vals) > 2 else ""
        save_config(self._cfg)

    # ------------------------------------------------------------------ #
    # Model list fetch
    # ------------------------------------------------------------------ #
    def _on_refresh_models(self) -> None:
        """Manually triggered model list refresh."""
        if not self._cfg.api_is_complete():
            mb.showwarning("Not configured", "Please configure API settings before refreshing models.")
            return
        self._fetch_models_async()

    def _fetch_models_async(self) -> None:
        """Fetch available models from the server in a background thread."""
        self._refresh_btn.configure(state="disabled")
        self._model_fetch_label.configure(text="Fetching…")

        def _run():
            model_ids, err = fetch_models(self._cfg)
            self.after(0, lambda: self._on_models_fetched(model_ids, err))

        threading.Thread(target=_run, daemon=True).start()

    def _on_models_fetched(self, model_ids: list[str], err: str | None) -> None:
        self._refresh_btn.configure(state="normal")
        if err:
            self._model_fetch_label.configure(
                text=f"Fetch failed: {err[:60]}", text_color=("red", "#ff6b6b")
            )
            return

        self._fetched_model_list = model_ids  # stored for CombineDialog
        self._model_fetch_label.configure(
            text=f"{len(model_ids)} models", text_color=("gray50", "gray60")
        )

        # Update all three combos with the fetched list.
        # Preserve whatever the user has currently typed/selected.
        sentinel = getattr(self, "_NONE_SENTINEL", "")
        for i, combo in enumerate(self._model_combos):
            current = combo.get()
            values = ([sentinel] + model_ids) if i > 0 else model_ids
            combo.configure(values=values)
            if current and current not in (model_ids + [sentinel]):
                combo.set(current)
            else:
                combo.set(current)

    # ------------------------------------------------------------------ #
    # API setup
    # ------------------------------------------------------------------ #
    def _check_api_on_startup(self) -> None:
        if not self._cfg.api_is_complete():
            self._show_api_dialog(require_valid=True, message=None)
            return

        self._set_api_status("Checking connection…", color="gray")

        def _test():
            err = test_connection(self._cfg)
            self.after(0, lambda: self._handle_startup_test(err))

        threading.Thread(target=_test, daemon=True).start()

    def _handle_startup_test(self, err: str | None) -> None:
        if err:
            self._set_api_status("Not connected", color="red")
            self._show_api_dialog(
                require_valid=True,
                message=f"Could not reach the API server:\n{err}\n\nPlease check your settings.",
            )
        else:
            self._set_api_status("Connected", color="green")
            self._fetch_models_async()

    def _open_api_settings(self) -> None:
        self._show_api_dialog(require_valid=False)

    def _show_api_dialog(self, require_valid: bool, message: str | None = None) -> None:
        if message:
            mb.showwarning("API Connection Issue", message)

        def _on_success(cfg: AppConfig) -> None:
            self._cfg = cfg
            self._set_api_status("Connected", color="green")
            self._fetch_models_async()

        ApiSetupDialog(self, config=self._cfg, on_success=_on_success, require_valid=require_valid)

    def _set_api_status(self, msg: str, color: str = "gray") -> None:
        color_map = {
            "green": ("green", "#4caf50"),
            "red": ("red", "#ff6b6b"),
            "gray": ("gray50", "gray60"),
        }
        self._api_status_label.configure(
            text=msg, text_color=color_map.get(color, ("gray50", "gray60"))
        )

    # ------------------------------------------------------------------ #
    # Document browsing
    # ------------------------------------------------------------------ #
    def _on_browse(self) -> None:
        path = fd.askopenfilename(
            title="Select document",
            filetypes=[
                ("Supported documents", "*.pdf *.docx"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
            ],
        )
        if not path:
            return

        try:
            text = document_reader.read_document(path)
        except Exception as exc:
            mb.showerror("Error reading document", str(exc))
            return

        if not text.strip():
            mb.showwarning("Empty document", "The selected document contains no readable text.")
            return

        self._document_path = path
        self._document_text = text
        filename = Path(path).name
        self._doc_label.configure(text=filename, text_color=("gray10", "gray90"))
        self._results_panel.set_document_filename(filename)
        self._set_status_plain(f"Document loaded: {len(text):,} characters")

    def _on_export_word(self) -> None:
        self._results_panel.open_export_dialog()

    def _on_browse_supporting(self) -> None:
        slots_left = self._MAX_SUPPORTING - len(self._supporting_files)
        if slots_left <= 0:
            mb.showwarning(
                "Limit reached",
                f"You can add at most {self._MAX_SUPPORTING} supporting files.",
                parent=self,
            )
            return

        paths = fd.askopenfilenames(
            title="Select supporting files",
            filetypes=[
                ("Supported documents", "*.pdf *.docx"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
            ],
        )
        if not paths:
            return

        if len(paths) > slots_left:
            mb.showwarning(
                "Too many files selected",
                f"Only {slots_left} more file(s) can be added. "
                f"Taking the first {slots_left} of your selection.",
                parent=self,
            )
            paths = paths[:slots_left]

        errors: list[str] = []
        for path in paths:
            fname = Path(path).name
            try:
                text = document_reader.read_document(path)
            except Exception as exc:
                errors.append(f"{fname}: {exc}")
                continue
            if not text.strip():
                errors.append(f"{fname}: no readable text found")
                continue
            self._supporting_files.append((fname, text))

        self._refresh_supporting_files_list()

        if errors:
            mb.showwarning(
                "Some files could not be read",
                "\n".join(errors),
                parent=self,
            )

    # ------------------------------------------------------------------ #
    # Run analysis
    # ------------------------------------------------------------------ #
    def _on_run(self) -> None:
        if self._running:
            return

        if not self._cfg.api_is_complete():
            mb.showwarning("API not configured", "Please configure your API settings first.")
            self._show_api_dialog(require_valid=False)
            return

        selected_models = self._get_selected_models()
        if not selected_models:
            mb.showwarning("No model selected", "Please enter at least one model name.")
            return

        if not self._document_text:
            mb.showwarning("No document", "Please select a document to review.")
            return

        self._save_model_selections()

        full_prompt = self._prompt_panel.get_full_prompt()

        self._skip_event = threading.Event()
        self._run_stats = {}
        self._running = True

        # Build the document content passed to the AI.
        # The AI client wraps it as: "{full_prompt}\n\n---\n\nDocument to review:\n\n{doc_content}"
        # When supporting files are present, append them after the main document.
        doc_content = self._document_text
        if self._supporting_files:
            supporting_block = (
                "\n\n---\n\n"
                "SUPPORTING REFERENCE FILES\n"
                "The following files are provided as reference material only. "
                "As part of your review, check whether the information in the main document "
                "is consistent with these supporting files. "
                "Do NOT review or critique the supporting files themselves — "
                "they are reference only.\n"
            )
            for i, (fname, ftext) in enumerate(self._supporting_files, start=1):
                supporting_block += f"\n--- Supporting File {i}: {fname} ---\n{ftext}\n"
            doc_content = self._document_text + supporting_block

        # Estimate input tokens from the full message that will be sent
        full_message = f"{full_prompt}\n\n---\n\nDocument to review:\n\n{doc_content}"
        self._current_input_tok_est = max(1, len(full_message) // 4)
        with self._chunk_lock:
            self._current_output_chars = 0
        self._run_btn.configure(state="disabled", text="⏳  Running…")
        self._cancel_btn.configure(state="normal", text="⏭ Skip Model")
        self._cancel_btn.grid()           # show Skip button
        self._combine_btn.configure(
            state="disabled",
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            text="🔀  Combine Analysis",
        )
        self._results_panel.clear()
        self._run_status_completed_lines.clear()
        with self._chunk_lock:
            self._chunk_buffer = defaultdict(list)
        self._refresh_run_status_display("Starting analysis…")
        self._start_chunk_flush_loop()

        ai_client.run_analysis(
            api_key=self._cfg.api_key,
            base_url=self._cfg.base_url,
            models=selected_models,
            document_text=doc_content,
            full_prompt=full_prompt,
            on_model_start=self._on_model_start,
            on_chunk=self._on_stream_chunk,
            on_model_done=self._on_model_done,
            on_skipped=self._on_skipped,
            on_error=self._on_error,
            on_complete=self._on_complete,
            skip_event=self._skip_event,
        )

    def _on_skip(self) -> None:
        """User pressed Skip — abort current model and move to the next."""
        self._skip_event.set()
        self._cancel_btn.configure(state="disabled", text="Skipping…")
        self._stop_elapsed_timer()

    # ------------------------------------------------------------------ #
    # AI callbacks (worker thread → schedule on main thread)
    # ------------------------------------------------------------------ #
    def _on_model_start(self, model: str, ready_event) -> None:
        def _setup():
            self._results_panel.prepare_model_tab(model, ready_event)
            self._current_model = model
            self._model_start_time = time.monotonic()
            with self._chunk_lock:
                self._current_output_chars = 0
            self._cancel_btn.configure(state="normal", text="⏭ Skip Model")
            self._start_elapsed_timer()
        self.after(0, _setup)

    def _on_stream_chunk(self, model: str, chunk: str) -> None:
        """Called from the worker thread — only touches the buffer (no Tk)."""
        with self._chunk_lock:
            self._chunk_buffer[model].append(chunk)
            self._current_output_chars += len(chunk)

    def _start_chunk_flush_loop(self) -> None:
        """Main thread: periodic drain so the Tk queue is not flooded."""
        self._stop_chunk_flush_loop()
        self._chunk_flush_timer_id = self.after(CHUNK_FLUSH_MS, self._chunk_flush_tick)

    def _stop_chunk_flush_loop(self) -> None:
        if self._chunk_flush_timer_id is not None:
            try:
                self.after_cancel(self._chunk_flush_timer_id)
            except Exception:
                pass
            self._chunk_flush_timer_id = None

    def _chunk_flush_tick(self) -> None:
        self._chunk_flush_timer_id = None
        self._drain_chunk_buffer_impl()
        if self._running:
            self._chunk_flush_timer_id = self.after(CHUNK_FLUSH_MS, self._chunk_flush_tick)

    def _drain_chunk_buffer_impl(self) -> None:
        """Move buffered text into the results panel (main thread only)."""
        with self._chunk_lock:
            pending = self._chunk_buffer
            self._chunk_buffer = defaultdict(list)
        for model, parts in pending.items():
            if not parts:
                continue
            text = "".join(parts)
            if model == _SUMMARY_CHUNK_KEY:
                self._results_panel.append_summary_chunk(text)
            else:
                self._results_panel.append_chunk(model, text)

    def _on_close_request(self) -> None:
        if self._running:
            if not mb.askyesno(
                "Quit",
                "Analysis is running. Stop and exit?",
                parent=self,
            ):
                return
            self._skip_event.set()
        self.destroy()

    def _on_model_done(self, model: str, input_tok: int, output_tok: int) -> None:
        def _done():
            self._drain_chunk_buffer_impl()
            self._stop_elapsed_timer()
            elapsed = time.monotonic() - self._model_start_time
            self._run_stats[model] = (elapsed, input_tok, output_tok)
            stats = format_stats(model, elapsed, input_tok, output_tok)
            self._run_status_completed_lines.append(f"✓  {model}  —  {stats}")
            self._refresh_run_status_display()
        self.after(0, _done)

    def _on_skipped(self, model: str) -> None:
        def _skipped():
            self._drain_chunk_buffer_impl()
            self._stop_elapsed_timer()
            self._results_panel.append_error(model, "[Skipped by user]")
            self._run_status_completed_lines.append(f"⏭  {model}  —  skipped")
            self._refresh_run_status_display()
        self.after(0, _skipped)

    def _on_error(self, model: str, error: str) -> None:
        def _err():
            self._drain_chunk_buffer_impl()
            self._results_panel.append_error(model, error)
            short = error[:120] + "…" if len(error) > 120 else error
            self._run_status_completed_lines.append(f"⚠  {model}: {short}")
            self._refresh_run_status_display()
        self.after(0, _err)

    def _on_complete(self) -> None:
        def _finish():
            self._stop_chunk_flush_loop()
            self._drain_chunk_buffer_impl()
            self._stop_elapsed_timer()
            self._running = False
            self._run_btn.configure(state="normal", text="▶  Run Analysis")
            self._cancel_btn.configure(state="normal", text="⏭ Skip Model")
            self._cancel_btn.grid_remove()
            self._results_panel.mark_complete()
            model_results = self._results_panel.get_model_results()
            has_any = any(v.strip() for v in model_results.values())

            if len(model_results) >= 2 and has_any:
                self._combine_btn.configure(
                    state="normal",
                    fg_color=("#1f6aa5", "#144870"),
                    hover_color=("#1a5a8f", "#10375a"),
                )

            status = self._build_completion_status(has_any, len(model_results))
            self._run_status_completed_lines.append("")
            self._run_status_completed_lines.append(status)
            self._write_status_box("\n".join(self._run_status_completed_lines))
        self.after(0, _finish)

    def _build_completion_status(self, has_any: bool, n_models: int) -> str:
        if not has_any:
            return ("Analysis finished but no output received — "
                    "check tabs for errors. See data/qc_errors.log for details.")

        stats = self._run_stats
        if not stats:
            return "Analysis complete."

        total_in  = sum(s[1] for s in stats.values())
        total_out = sum(s[2] for s in stats.values())
        total_elapsed = sum(s[0] for s in stats.values())

        # Aggregate cost across all models that have known pricing
        total_cost: float | None = 0.0
        for model, (_, in_t, out_t) in stats.items():
            c = calculate_cost(model, in_t, out_t)
            if c is None:
                total_cost = None  # any unknown model → can't total
                break
            total_cost += c

        mins, secs = divmod(int(total_elapsed), 60)
        time_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        tok_str  = f"{total_in:,} in / {total_out:,} out tokens"
        cost_str = f"${total_cost:.4f}" if total_cost is not None else "cost unknown"

        prefix = "Analysis complete" if n_models >= 2 else "Analysis complete"
        return f"{prefix}  —  {time_str}  |  {tok_str}  |  {cost_str}"

    # ------------------------------------------------------------------ #
    # Elapsed timer
    # ------------------------------------------------------------------ #
    def _start_elapsed_timer(self) -> None:
        self._stop_elapsed_timer()
        self._tick_elapsed_timer()

    def _tick_elapsed_timer(self) -> None:
        if not self._running or self._skip_event.is_set():
            return

        elapsed = time.monotonic() - self._model_start_time
        mins, secs = divmod(int(elapsed), 60)
        time_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"

        in_tok = self._current_input_tok_est
        with self._chunk_lock:
            out_chars = self._current_output_chars
        out_tok = max(1, out_chars // 4)

        cost = calculate_cost(self._current_model, in_tok, out_tok)
        cost_str = f"~${cost:.4f}" if cost is not None else "cost unknown"

        cur = (
            f"⏳  {self._current_model}  —  {time_str}"
            f"  |  ~{in_tok:,} in / ~{out_tok:,} out tok"
            f"  |  {cost_str}"
        )
        self._refresh_run_status_display(current_line=cur)
        self._timer_after_id = self.after(1000, self._tick_elapsed_timer)

    def _stop_elapsed_timer(self) -> None:
        if self._timer_after_id is not None:
            try:
                self.after_cancel(self._timer_after_id)
            except Exception:
                pass
            self._timer_after_id = None

    # ------------------------------------------------------------------ #
    # Combine / summary
    # ------------------------------------------------------------------ #
    def _on_reset_form(self) -> None:
        """Restore the UI to a fresh-launch state (document, results, progress, prompts)."""
        if self._running:
            mb.showwarning(
                "New QC Review unavailable",
                "Wait for the current analysis or summary to finish, or use Skip.",
                parent=self,
            )
            return
        if not mb.askyesno(
            "New QC Review",
            "Clear the document, results, and progress and restore default model selections?",
            parent=self,
        ):
            return

        self._document_path = None
        self._document_text = None
        self._doc_label.configure(text="No document selected", text_color=("gray50", "gray60"))
        self._supporting_files.clear()
        self._refresh_supporting_files_list()
        self._results_panel.set_document_filename("document")
        self._results_panel.clear()
        self._prompt_panel.clear_additional()
        self._run_stats.clear()
        self._run_status_completed_lines.clear()
        self._summary_model_name = ""
        self._set_status_plain("")

        cfg = load_config()
        self._cfg = cfg
        for combo, v in zip(self._model_combos, (cfg.model1, cfg.model2, cfg.model3)):
            combo.set(v)

        self._combine_btn.configure(
            state="disabled",
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray25"),
            text="🔀  Combine Analysis",
        )

    def _on_combine(self) -> None:
        model_results = self._results_panel.get_model_results()
        if len(model_results) < 2:
            mb.showinfo("Not enough results", "Combine requires results from at least 2 models.")
            return

        # Build the list the user can pick from: currently saved models + any fetched ones
        saved = [c.get().strip() for c in self._model_combos if c.get().strip()]
        fetched = list(getattr(self, "_fetched_model_list", []))
        options = list(dict.fromkeys(saved + fetched)) or saved  # deduplicated, order preserved

        def _on_generate(model_name: str) -> None:
            self._run_summary(model_name, model_results)

        CombineDialog(self, available_models=options, on_generate=_on_generate)

    def _run_summary(self, model_name: str, model_results: dict) -> None:
        self._summary_model_name = model_name
        self._stop_chunk_flush_loop()
        self._drain_chunk_buffer_impl()
        with self._chunk_lock:
            self._chunk_buffer = defaultdict(list)

        self._skip_event = threading.Event()
        self._combine_btn.configure(state="disabled", text="⏳  Generating Summary…")
        self._run_btn.configure(state="disabled")
        self._cancel_btn.configure(state="normal", text="⏭ Skip Model")
        self._cancel_btn.grid()
        self._current_model = model_name
        self._model_start_time = time.monotonic()
        with self._chunk_lock:
            self._current_output_chars = 0
        # For summary the input is the combined model results; estimate from their total length
        combined_len = sum(len(t) for t in model_results.values())
        self._current_input_tok_est = max(1, combined_len // 4)
        self._running = True
        self._run_status_completed_lines.append("")
        self._run_status_completed_lines.append("── Combined summary ──")
        self._refresh_run_status_display()
        self._start_chunk_flush_loop()
        self._start_elapsed_timer()

        def _on_ready(ready_event):
            self.after(0, lambda: self._results_panel.prepare_summary_tab(ready_event))

        ai_client.run_summary(
            api_key=self._cfg.api_key,
            base_url=self._cfg.base_url,
            model=model_name,
            model_results=model_results,
            on_ready=_on_ready,
            on_chunk=lambda c: self._on_stream_chunk(_SUMMARY_CHUNK_KEY, c),
            on_error=lambda err: self.after(0, lambda e=err: self._on_summary_error(e)),
            on_complete=lambda s, el, i, o: self.after(
                0, lambda: self._on_summary_complete(s, el, i, o)
            ),
            skip_event=self._skip_event,
        )

    def _on_summary_error(self, error: str) -> None:
        self._drain_chunk_buffer_impl()
        self._results_panel.append_summary_error(error)
        self._run_status_completed_lines.append(f"⚠  Summary: {error[:80]}")
        self._refresh_run_status_display()

    def _on_summary_complete(
        self, success: bool, elapsed: float, in_tok: int, out_tok: int
    ) -> None:
        self._stop_chunk_flush_loop()
        self._drain_chunk_buffer_impl()
        self._stop_elapsed_timer()
        self._running = False
        self._run_btn.configure(state="normal")
        self._cancel_btn.configure(state="normal", text="⏭ Skip Model")
        self._cancel_btn.grid_remove()
        self._combine_btn.configure(
            state="normal",
            text="🔀  Combine Analysis",
            fg_color=("#1f6aa5", "#144870"),
            hover_color=("#1a5a8f", "#10375a"),
        )
        self._results_panel.mark_complete()
        name = self._summary_model_name
        if self._skip_event.is_set():
            self._run_status_completed_lines.append("Summary skipped.")
        elif success and name:
            if in_tok == 0 and out_tok == 0:
                in_tok = self._current_input_tok_est
                with self._chunk_lock:
                    out_tok = max(1, self._current_output_chars // 4)
            stats = format_stats(name, elapsed, in_tok, out_tok)
            self._run_status_completed_lines.append(f"✓  {name}  —  {stats}")
        self._refresh_run_status_display()

    # ------------------------------------------------------------------ #
    # Status / progress display
    # ------------------------------------------------------------------ #
    def _write_status_box(self, text: str) -> None:
        self._status_box.configure(state="normal")
        self._status_box.delete("1.0", "end")
        self._status_box.insert("1.0", text.rstrip() if text else "")
        self._status_box.configure(state="disabled")
        self._status_box.see("end")

    def _set_status_plain(self, msg: str) -> None:
        """Replace the progress area with a single message (clears run history)."""
        self._run_status_completed_lines.clear()
        self._write_status_box(msg)

    def _refresh_run_status_display(self, current_line: str | None = None) -> None:
        """
        Show all finished model lines, then (optional) a blank line and the
        live line for the model currently running.
        """
        parts: list[str] = []
        if self._run_status_completed_lines:
            parts.append("\n".join(self._run_status_completed_lines))
        if current_line:
            if parts:
                parts.append("")
            parts.append(current_line)
        self._write_status_box("\n".join(parts))
