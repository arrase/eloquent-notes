"""Utility functions for config comparison."""


def _diff_entry(default: dict, k: str, v):
    """Determine whether key/value is an override against default dict."""
    if k not in default:
        return True, v
    default_val = default[k]
    if isinstance(v, dict) and isinstance(default_val, dict):
        diff = diff_configs(default_val, v)
        if diff or (not v and bool(default_val)):
            return True, diff
        return False, None
    if isinstance(v, bool) != isinstance(default_val, bool) or v != default_val:
        return True, v
    return False, None


def diff_configs(default: dict, current: dict) -> dict:
    """Recursively diff current config against defaults, returning only overrides."""
    overrides = {}
    for k, v in current.items():
        is_override, val = _diff_entry(default, k, v)
        if is_override:
            overrides[k] = val
    return overrides

