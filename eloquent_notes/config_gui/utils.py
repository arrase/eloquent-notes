"""Utility functions for config comparison."""


def diff_configs(default, current):
    """Recursively diff current config against defaults, returning only overrides."""
    overrides = {}
    for k, v in current.items():
        if k not in default:
            overrides[k] = v
        else:
            if isinstance(v, dict) and isinstance(default[k], dict):
                diff = diff_configs(default[k], v)
                if diff:  # only keep if not empty
                    overrides[k] = diff
            elif v != default[k]:
                overrides[k] = v
    return overrides
