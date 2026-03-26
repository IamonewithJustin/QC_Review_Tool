"""
OpenAI-compatible AI client.
Supports up to three models running sequentially for document analysis,
and a single-model combined summary pass.

Reliability features:
- Per-chunk stall timeout (CHUNK_STALL_TIMEOUT): if the server goes silent
  between stream events, raise ReadTimeout after this many seconds.
- Retry logic: each model retried MAX_RETRIES times on transient errors.
- Cancel event: caller can set a threading.Event to abort mid-run.
- All exceptions are caught and reported; on_complete() is always called.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.app_paths import get_data_dir

LOG_PATH = get_data_dir() / "qc_errors.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Seconds to establish a connection before giving up
CONNECT_TIMEOUT = 30.0

# Seconds of server silence between stream chunks before declaring it stalled.
# This fires per-chunk, so it handles mid-stream hangs, not just slow first-response.
CHUNK_STALL_TIMEOUT = 45.0

# Total write timeout (sending the request body)
WRITE_TIMEOUT = 30.0

# Retry attempts per model on transient failures (0 = no retries, just 1 attempt)
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds between retries

SUMMARY_PROMPT = """\
You are a senior scientific document review coordinator. Multiple independent AI \
reviewers have each analyzed the same document and produced separate QC reports. \
Your role is to synthesize all of their findings into a single, definitive, \
publication-ready QC summary report.

Your report must be organized into the following four sections:

SECTION 1 - CONSOLIDATED ISSUES
Merge and deduplicate all issues identified across every model's analysis. \
Organize findings into these categories:
  * Grammar, Spelling & Formatting Errors
  * Terminology, Style & Consistency Issues
  * Data Errors & Factual Inaccuracies
  * Story Flow & Structural Concerns

For each issue:
  - Describe the problem clearly and precisely, quoting the original text where helpful.
  - Provide the best recommended correction or rewrite, drawing on the strongest \
suggestions across all models.
  - Note when multiple models independently flagged the same issue (increases confidence).

SECTION 2 - PRIORITY FINDINGS
List the top five most critical issues that require immediate attention, ranked by \
severity and potential impact on the document's credibility and clarity. \
Provide a one-sentence rationale for each ranking.

SECTION 3 - OVERALL DOCUMENT ASSESSMENT
Provide a concise holistic assessment (3-5 sentences) covering the document's \
overall quality, its notable strengths, and its readiness for its intended purpose.

SECTION 4 - INTER-MODEL DISCREPANCIES  (mandatory - do not omit)
Systematically identify every area where the models disagreed, including:
  - Issues flagged by only one model and ignored by the others (assess whether \
each is likely a genuine problem or a false positive).
  - Cases where models gave conflicting corrections for the same passage.
  - Differences in severity or priority assessment.
  - Any contradictory findings or recommendations.

Be thorough, objective, and precise. Your output will be used directly by a \
scientific editor to improve the document.\
"""


def _make_client(api_key: str, base_url: str):
    """
    Create an OpenAI client with per-chunk stall timeout.
    Uses httpx.Timeout so the read timeout applies between stream events,
    not just to the total response — this catches mid-stream server hangs.
    """
    from openai import OpenAI
    try:
        import httpx
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=CHUNK_STALL_TIMEOUT,
            write=WRITE_TIMEOUT,
            pool=10.0,
        )
    except ImportError:
        # httpx not available separately; fall back to float timeout
        timeout = CHUNK_STALL_TIMEOUT

    return OpenAI(
        api_key=api_key,
        base_url=base_url if base_url.strip() else None,
        timeout=timeout,
        max_retries=0,  # we handle retries ourselves
    )


def _create_stream(client, model: str, messages: list):
    """
    Create a streaming completion, requesting token usage in the final chunk.
    Falls back to a plain stream if the server doesn't support stream_options.
    """
    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
        )
    except Exception:
        # Provider doesn't support stream_options — stream without usage
        return client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )


class _UsageCapture:
    """Mutable container filled by _safe_stream with token usage from the final chunk."""
    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self):
        self.input_tokens: int = 0
        self.output_tokens: int = 0


def _safe_stream(
    stream,
    skip_event: Optional[threading.Event] = None,
    usage: Optional[_UsageCapture] = None,
):
    """
    Iterate a streaming completion and yield text chunks.
    - Skips malformed chunks gracefully.
    - Checks skip_event between each chunk.
    - If usage is provided, captures input/output token counts from the
      final usage chunk (requires stream_options include_usage=True).
    """
    for chunk in stream:
        if skip_event and skip_event.is_set():
            return
        try:
            # Capture usage from the dedicated usage chunk (choices is empty there)
            if usage is not None and hasattr(chunk, "usage") and chunk.usage:
                u = chunk.usage
                usage.input_tokens = getattr(u, "prompt_tokens", 0) or 0
                usage.output_tokens = getattr(u, "completion_tokens", 0) or 0

            choices = chunk.choices
            if not choices:
                continue
            delta = choices[0].delta
            if delta and delta.content:
                yield delta.content
        except Exception as exc:
            logging.warning("Skipping malformed stream chunk: %s", exc)
            continue


def run_analysis(
    api_key: str,
    base_url: str,
    models: List[str],
    document_text: str,
    full_prompt: str,
    on_model_start: Callable[[str, threading.Event], None],
    on_chunk: Callable[[str, str], None],
    on_model_done: Callable[[str, int, int], None],   # (model, input_tok, output_tok)
    on_skipped: Callable[[str], None],
    on_error: Callable[[str, str], None],
    on_complete: Callable[[], None],
    skip_event: Optional[threading.Event] = None,
) -> threading.Thread:
    """
    Run analysis in a background thread.

    on_model_start(model_name, ready_event) — caller must set ready_event once
    the UI tab is prepared so streaming can begin.

    skip_event — set from the UI to skip the *current* model and move to the next.
    The worker clears this event automatically before starting each new model,
    so clicking Skip only affects the model that is currently running.
    """
    active_models = [m.strip() for m in models if m and m.strip()]
    if skip_event is None:
        skip_event = threading.Event()

    def worker():
        try:
            client = _make_client(api_key, base_url)
        except Exception as exc:
            logging.error("Client creation failed: %s", exc)
            on_error("setup", f"Failed to create API client: {exc}")
            on_complete()
            return

        messages = [
            {
                "role": "user",
                "content": f"{full_prompt}\n\n---\n\nDocument to review:\n\n{document_text}",
            }
        ]

        for model in active_models:
            # Reset skip state for this model so a previous skip doesn't bleed over
            skip_event.clear()

            # Signal UI to prepare tab; wait until it confirms ready
            ready_event = threading.Event()
            on_model_start(model, ready_event)
            if not ready_event.wait(timeout=10.0):
                logging.warning("Tab for %s never became ready; proceeding anyway", model)

            last_error = None
            succeeded = False
            for attempt in range(1, MAX_RETRIES + 2):
                if skip_event.is_set():
                    break
                try:
                    logging.info("Starting analysis: model=%s attempt=%d", model, attempt)
                    usage = _UsageCapture()
                    stream = _create_stream(client, model, messages)
                    for text in _safe_stream(stream, skip_event, usage):
                        on_chunk(model, text)

                    if skip_event.is_set():
                        break  # skipped mid-stream; don't mark as done

                    on_model_done(model, usage.input_tokens, usage.output_tokens)
                    succeeded = True
                    last_error = None
                    break

                except Exception as exc:
                    last_error = exc
                    logging.error(
                        "Analysis error: model=%s attempt=%d error=%s",
                        model, attempt, exc,
                    )
                    if attempt <= MAX_RETRIES and not skip_event.is_set():
                        on_error(
                            model,
                            f"Attempt {attempt}/{MAX_RETRIES + 1} failed: {exc}  "
                            f"— retrying in {RETRY_DELAY}s…",
                        )
                        for _ in range(RETRY_DELAY * 2):
                            if skip_event.is_set():
                                break
                            time.sleep(0.5)

            if skip_event.is_set():
                logging.info("Model skipped by user: %s", model)
                on_skipped(model)
            elif not succeeded and last_error is not None:
                on_error(
                    model,
                    f"All {MAX_RETRIES + 1} attempts failed.\nLast error: {last_error}\n"
                    f"Check data/qc_errors.log for details.",
                )

        on_complete()

    t = threading.Thread(target=worker, daemon=True, name="analysis-worker")
    t.start()
    return t


def run_summary(
    api_key: str,
    base_url: str,
    model: str,
    model_results: Dict[str, str],
    on_ready: Callable[[threading.Event], None],
    on_chunk: Callable[[str], None],
    on_error: Callable[[str], None],
    on_complete: Callable[[bool, float, int, int], None],
    skip_event: Optional[threading.Event] = None,
) -> threading.Thread:
    """
    Run the combined summary in a background thread.
    skip_event — set to cancel the summary (single model, so skip = cancel here).

    on_complete(success, elapsed_s, input_tokens, output_tokens) — always called once.
    success is True only when the stream finished without skip/cancel.
    """
    if skip_event is None:
        skip_event = threading.Event()

    def worker():
        try:
            client = _make_client(api_key, base_url)
        except Exception as exc:
            on_error(f"Failed to create API client: {exc}")
            on_complete(False, 0.0, 0, 0)
            return

        ready_event = threading.Event()
        on_ready(ready_event)
        if not ready_event.wait(timeout=10.0):
            logging.warning("Summary tab never became ready; proceeding anyway")

        if skip_event.is_set():
            on_complete(False, 0.0, 0, 0)
            return

        analyses_block = "\n\n".join(
            f"{'=' * 60}\nANALYSIS BY MODEL: {name}\n{'=' * 60}\n\n{text}"
            for name, text in model_results.items()
        )
        content = (
            f"{SUMMARY_PROMPT}\n\n"
            f"The following {len(model_results)} independent model analyses are provided "
            f"for synthesis:\n\n{analyses_block}"
        )

        last_error = None
        success = False
        summary_elapsed = 0.0
        final_in, final_out = 0, 0

        for attempt in range(1, MAX_RETRIES + 2):
            if skip_event.is_set():
                break
            try:
                logging.info("Starting summary: model=%s attempt=%d", model, attempt)
                t0 = time.monotonic()
                usage = _UsageCapture()
                stream = _create_stream(client, model, [{"role": "user", "content": content}])
                for text in _safe_stream(stream, skip_event, usage):
                    on_chunk(text)
                if skip_event.is_set():
                    summary_elapsed = time.monotonic() - t0
                    final_in = usage.input_tokens
                    final_out = usage.output_tokens
                    break
                summary_elapsed = time.monotonic() - t0
                final_in = usage.input_tokens
                final_out = usage.output_tokens
                success = True
                last_error = None
                break

            except Exception as exc:
                last_error = exc
                logging.error("Summary error: attempt=%d error=%s", attempt, exc)
                if attempt <= MAX_RETRIES and not skip_event.is_set():
                    on_error(
                        f"Attempt {attempt}/{MAX_RETRIES + 1} failed: {exc}  "
                        f"— retrying in {RETRY_DELAY}s…"
                    )
                    for _ in range(RETRY_DELAY * 2):
                        if skip_event.is_set():
                            break
                        time.sleep(0.5)

        if last_error is not None and not skip_event.is_set():
            on_error(
                f"All {MAX_RETRIES + 1} attempts failed.\nLast error: {last_error}\n"
                f"Check data/qc_errors.log for details."
            )

        on_complete(success, summary_elapsed, final_in, final_out)

    t = threading.Thread(target=worker, daemon=True, name="summary-worker")
    t.start()
    return t
