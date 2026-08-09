"""Utility functions for config comparison."""


def diff_configs(default: dict, current: dict) -> dict:
    """Recursively diff current config against defaults, returning only overrides."""
    overrides = {}
    for k, v in current.items():
        if k not in default:
            overrides[k] = v
        else:
            default_val = default[k]
            if isinstance(v, dict) and isinstance(default_val, dict):
                diff = diff_configs(default_val, v)
                if diff or (not v and bool(default_val)):
                    overrides[k] = diff
            elif isinstance(v, bool) != isinstance(default_val, bool):
                overrides[k] = v
            elif v != default_val:
                overrides[k] = v
    return overrides

