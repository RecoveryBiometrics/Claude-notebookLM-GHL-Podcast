"""
Shared cost logger for Anthropic API calls.
Import and call log_api_cost() after every client.messages.create() call.

Usage:
    from cost_logger import log_api_cost
    response = client.messages.create(...)
    log_api_cost(response, script="my-script")
"""

import json
import os
from datetime import datetime

LOG_FILE = os.path.expanduser("~/.claude/api_costs.jsonl")

# Pricing per million tokens (as of March 2026)
PRICING = {
    # Haiku 4.5
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "cache_read": 0.08, "cache_write": 1.00},
    # Sonnet 4.6
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    # Opus 4.6
    "claude-opus-4-6": {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    # Fallback
    "default": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}


def get_pricing(model: str) -> dict:
    """Get pricing for a model, falling back to default."""
    for key in PRICING:
        if key in model:
            return PRICING[key]
    return PRICING["default"]


def calculate_cost(response) -> dict:
    """Calculate cost from an Anthropic API response."""
    usage = getattr(response, "usage", None)
    if not usage:
        return {"cost": 0, "input_tokens": 0, "output_tokens": 0}

    model = getattr(response, "model", "unknown")
    pricing = get_pricing(model)

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
        + (cache_read / 1_000_000) * pricing["cache_read"]
        + (cache_creation / 1_000_000) * pricing["cache_write"]
    )

    return {
        "cost": round(cost, 6),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "model": model,
    }


def log_api_cost(response, script: str = "unknown", note: str = ""):
    """Log an API call's cost to the shared cost log."""
    cost_data = calculate_cost(response)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "script": script,
        "note": note,
        **cost_data,
    }

    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Don't break the pipeline over logging

    return cost_data
