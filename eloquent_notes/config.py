"""Configuration management for Eloquent Notes.

Handles loading and merging of default and user configuration files
and prompt files from ~/.config/eloquent-notes/.
"""

import copy
import os
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from eloquent_notes.i18n import _
from eloquent_notes.logging_utils import LOG_LEVELS

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
KEEP_ALIVE_RE = re.compile(r"^-?\d+(ns|us|µs|ms|s|m|h)?$")


def get_config_home() -> str:
    """Return the XDG base directory for user configuration files."""
    return os.environ.get("XDG_CONFIG_HOME") or str(Path("~/.config").expanduser())


def get_cache_home() -> str:
    """Return the XDG base directory for user cache files."""
    return os.environ.get("XDG_CACHE_HOME") or str(Path("~/.cache").expanduser())


def get_data_home() -> str:
    """Return the XDG base directory for user data files."""
    return os.environ.get("XDG_DATA_HOME") or str(Path("~/.local/share").expanduser())


CONFIG_DIR = str(Path(get_config_home(), "eloquent-notes"))
CONFIG_PATH = str(Path(CONFIG_DIR, "config.yaml"))
CACHE_DIR = str(Path(get_cache_home(), "eloquent-notes"))

PROMPTS_DIR = str(Path(CONFIG_DIR, "prompts"))

PACKAGE_DIR = str(Path(__file__).resolve().parent)
DEFAULT_CONFIG_SRC = str(Path(PACKAGE_DIR, "config.yaml"))
DEFAULT_PROMPTS_DIR = str(Path(PACKAGE_DIR, "prompts"))

RETRY_PROMPT_PATH = str(Path(PROMPTS_DIR, "retry_prompt.md"))
TRANSCRIPTION_SYSTEM_PROMPT_PATH = str(Path(PROMPTS_DIR, "transcription_system.md"))
TRANSCRIPTION_USER_PROMPT_PATH = str(Path(PROMPTS_DIR, "transcription_user.md"))
REWRITING_SYSTEM_PROMPT_PATH = str(Path(PROMPTS_DIR, "rewriting_system.md"))
REWRITING_USER_PROMPT_PATH = str(Path(PROMPTS_DIR, "rewriting_user.md"))
CLASSIFICATION_SYSTEM_PROMPT_PATH = str(Path(PROMPTS_DIR, "classification_system.md"))
CLASSIFICATION_USER_PROMPT_PATH = str(Path(PROMPTS_DIR, "classification_user.md"))
TAGGING_SYSTEM_PROMPT_PATH = str(Path(PROMPTS_DIR, "tagging_system.md"))
TAGGING_USER_PROMPT_PATH = str(Path(PROMPTS_DIR, "tagging_user.md"))

PROMPT_PATHS = (
    RETRY_PROMPT_PATH,
    TRANSCRIPTION_SYSTEM_PROMPT_PATH,
    TRANSCRIPTION_USER_PROMPT_PATH,
    REWRITING_SYSTEM_PROMPT_PATH,
    REWRITING_USER_PROMPT_PATH,
    CLASSIFICATION_SYSTEM_PROMPT_PATH,
    CLASSIFICATION_USER_PROMPT_PATH,
    TAGGING_SYSTEM_PROMPT_PATH,
    TAGGING_USER_PROMPT_PATH,
)

PROMPT_DEFAULTS = {path: str(Path(DEFAULT_PROMPTS_DIR, Path(path).name)) for path in PROMPT_PATHS}

_FILES_TO_COPY = (
    (DEFAULT_CONFIG_SRC, CONFIG_PATH),
    *((src, dst) for dst, src in PROMPT_DEFAULTS.items()),
)


def init_config_dir() -> None:
    """Create config directories and copy default files if they don't exist."""
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    Path(PROMPTS_DIR).mkdir(parents=True, exist_ok=True)

    for src, dst in _FILES_TO_COPY:
        if not Path(dst).exists():
            shutil.copy(src, dst)


def _is_valid_str(key: str, value: str, default_val: str) -> bool:
    if default_val.startswith("#"):
        return bool(_HEX_COLOR_RE.fullmatch(value))
    if key == "ollama_url":
        parsed = urlparse(value)
        return not any(c.isspace() for c in value) and parsed.scheme in ("http", "https") and bool(parsed.netloc)
    if key in ("keep_alive", "preload_keep_alive", "search_keep_alive"):
        return bool(KEEP_ALIVE_RE.fullmatch(value))
    if key == "level":
        return value.upper() in LOG_LEVELS
    return bool(value.strip())


def _is_valid_number(key: str, value: int | float) -> bool:
    if key == "channels":
        return value in (1, 2)
    if key == "min_similarity":
        return 0.0 <= value <= 1.0
    if key in ("max_retries", "backup_count"):
        return value >= 0
    return 0 < value < float("inf")


def _validate_override(key: str, value: object, default_val: object) -> None:
    if key == "context_length" and value is None:
        return
    expected = (int, float) if type(default_val) is float else (type(default_val),)
    if type(value) not in expected:
        raise TypeError(_("Invalid configuration value for '{key}'").format(key=key))

    valid = True
    if isinstance(value, str) and isinstance(default_val, str):
        valid = _is_valid_str(key, value, default_val)
    elif type(value) in (int, float) and isinstance(value, (int, float)):
        valid = _is_valid_number(key, value)

    if not valid:
        raise ValueError(_("Invalid configuration value for '{key}'").format(key=key))


def _merge_configs(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overrides into base config dict."""
    result = copy.deepcopy(base)
    for k, v in overrides.items():
        if k not in result:
            raise ValueError(f"Unknown configuration key '{k}'")
        default_val = result[k]
        if isinstance(default_val, dict):
            if not isinstance(v, dict):
                raise TypeError(
                    _("Configuration section '{key}' must be a mapping, got {type_name}").format(
                        key=k, type_name=type(v).__name__
                    )
                )
            result[k] = _merge_configs(default_val, v)
        else:
            _validate_override(k, v, default_val)
            result[k] = copy.deepcopy(v)
    return result


def diff_configs(default: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Recursively diff current config against defaults, returning only overrides."""
    overrides: dict[str, Any] = {}
    for k, default_val in default.items():
        v = current[k]
        if isinstance(default_val, dict) and isinstance(v, dict):
            diff = diff_configs(default_val, v)
            if diff:
                overrides[k] = diff
        elif isinstance(v, bool) != isinstance(default_val, bool) or v != default_val:
            overrides[k] = v
    return overrides


def load_default_config() -> dict[str, Any]:
    """Load and return the packaged default configuration dictionary."""
    with Path(DEFAULT_CONFIG_SRC).open(encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)
        return data


def load_config() -> dict[str, Any]:
    """Load and merge default config with user overrides."""
    init_config_dir()

    default_config = load_default_config()

    with Path(CONFIG_PATH).open(encoding="utf-8") as f:
        user_config = yaml.safe_load(f)

    if user_config is None:
        user_config = {}
    elif not isinstance(user_config, dict):
        raise TypeError(_("User config at {path} is not a valid YAML mapping").format(path=CONFIG_PATH))

    return _merge_configs(default_config, user_config)


def load_file(path: str) -> str:
    """Load and return the text content of a file."""
    return Path(path).read_text(encoding="utf-8")


def atomic_write(path: str, content: str | bytes) -> None:
    """Write content to a file atomically via a temporary replacement file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{path}.tmp")
    if isinstance(content, bytes):
        tmp_path.write_bytes(content)
    else:
        tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(target)


def save_config(config_data: dict[str, Any]) -> None:
    """Save configuration data to user config file."""
    content = yaml.safe_dump(config_data, default_flow_style=False, sort_keys=False)
    atomic_write(CONFIG_PATH, content)
