"""
Token pricing lookup for common OpenAI-compatible models.
Prices are in USD per 1,000,000 tokens (input, output).
Models not in the table will show token counts but no cost estimate.
"""

from __future__ import annotations
from typing import Optional, Tuple

# (input_price_per_M, output_price_per_M) in USD
_PRICE_TABLE: dict[str, Tuple[float, float]] = {
    # ── OpenAI ────────────────────────────────────────────────────────────
    "gpt-4.1":            (2.00,  8.00),
    "gpt-4.1-mini":       (0.40,  1.60),
    "gpt-4.1-nano":       (0.10,  0.40),
    "gpt-4o":             (2.50, 10.00),
    "gpt-4o-mini":        (0.15,  0.60),
    "gpt-4-turbo":       (10.00, 30.00),
    "gpt-4":             (30.00, 60.00),
    "gpt-3.5-turbo":      (0.50,  1.50),
    "gpt-5":             (10.00, 40.00),   # placeholder — update when published
    "o1":                (15.00, 60.00),
    "o1-mini":            (3.00, 12.00),
    "o1-pro":            (150.0, 600.0),
    "o3":                (10.00, 40.00),
    "o3-mini":            (1.10,  4.40),
    "o4-mini":            (1.10,  4.40),
    # ── Anthropic (via proxy / compatible endpoint) ───────────────────────
    "claude-opus-4":     (15.00, 75.00),
    "claude-sonnet-4":    (3.00, 15.00),
    "claude-haiku-4":     (0.80,  4.00),
    "claude-3-5-sonnet":  (3.00, 15.00),
    "claude-3-5-haiku":   (0.80,  4.00),
    "claude-3-opus":     (15.00, 75.00),
    "claude-3-sonnet":    (3.00, 15.00),
    "claude-3-haiku":     (0.25,  1.25),
    # ── Google Gemini (via compatible endpoint) ───────────────────────────
    "gemini-2.5-pro":     (1.25,  10.00),
    "gemini-2.0-flash":   (0.10,   0.40),
    "gemini-1.5-pro":     (1.25,   5.00),
    "gemini-1.5-flash":   (0.075,  0.30),
    "gemini-pro":         (0.50,   1.50),
    # ── Meta / Llama (common hosted variants) ────────────────────────────
    "llama-3.3-70b":      (0.59,  0.79),
    "llama-3.1-405b":     (3.00,  3.00),
    "llama-3.1-70b":      (0.52,  0.75),
    "llama-3.1-8b":       (0.05,  0.08),
}


def lookup(model_name: str) -> Optional[Tuple[float, float]]:
    """
    Return (input_price_per_M, output_price_per_M) for the given model name.
    Uses substring matching (case-insensitive) so partial names like
    'claude-sonnet-4.5' still match 'claude-sonnet-4'.
    Returns None if no match is found.
    """
    name_lower = model_name.lower()
    # Exact match first
    if name_lower in _PRICE_TABLE:
        return _PRICE_TABLE[name_lower]
    # Longest-key substring match to avoid 'gpt-4' matching 'gpt-4.1'
    best_key = None
    best_len = 0
    for key, prices in _PRICE_TABLE.items():
        if key in name_lower and len(key) > best_len:
            best_key = key
            best_len = len(key)
    return _PRICE_TABLE[best_key] if best_key else None


def calculate_cost(
    model_name: str, input_tokens: int, output_tokens: int
) -> Optional[float]:
    """Return total USD cost, or None if pricing is unknown."""
    prices = lookup(model_name)
    if prices is None:
        return None
    input_price, output_price = prices
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def format_stats(
    model_name: str,
    elapsed_s: float,
    input_tokens: int,
    output_tokens: int,
) -> str:
    """Return a compact human-readable stats string."""
    mins, secs = divmod(int(elapsed_s), 60)
    time_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"

    tok_str = f"{input_tokens:,} in / {output_tokens:,} out"

    cost = calculate_cost(model_name, input_tokens, output_tokens)
    cost_str = f"${cost:.4f}" if cost is not None else "cost unknown"

    return f"{time_str}  |  {tok_str} tokens  |  {cost_str}"
