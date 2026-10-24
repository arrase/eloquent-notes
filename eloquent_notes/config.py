"""Configuration management for Eloquent Notes.

Handles loading and merging of default and user configuration files
and prompt files from ~/.config/eloquent-notes/.
"""

import copy
import os
import re
import shutil
from urllib.parse import urlparse

import yaml

from eloquent_notes.i18n import _
from eloquent_notes.logging_utils import LOG_LEVELS

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
KEEP_ALIVE_RE = re.compile(r"^-?\d+(ns|us|µs|ms|s|m|h)?$")


def get_config_home():
    """Return the XDG base directory for user configuration files."""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")


def get_cache_home():
    """Return the XDG base directory for user cache files."""
    return os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")


def get_data_home():
    """Return the XDG base directory for user data files."""
    return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")


CONFIG_DIR = os.path.join(get_config_home(), "eloquent-notes")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")
CACHE_DIR = os.path.join(get_cache_home(), "eloquent-notes")

PROMPTS_DIR = os.path.join(CONFIG_DIR, "prompts")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_SRC = os.path.join(PACKAGE_DIR, "config.yaml")
DEFAULT_PROMPTS_DIR = os.path.join(PACKAGE_DIR, "prompts")

RETRY_PROMPT_PATH = os.path.join(PROMPTS_DIR, "retry_prompt.md")
TRANSCRIPTION_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "transcription_system.md")
TRANSCRIPTION_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "transcription_user.md")
REWRITING_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "rewriting_system.md")
REWRITING_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "rewriting_user.md")
CLASSIFICATION_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "classification_system.md")
CLASSIFICATION_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "classification_user.md")

PROMPT_PATHS = (
    RETRY_PROMPT_PATH,
    TRANSCRIPTION_SYSTEM_PROMPT_PATH,
    TRANSCRIPTION_USER_PROMPT_PATH,
    REWRITING_SYSTEM_PROMPT_PATH,
    REWRITING_USER_PROMPT_PATH,
    CLASSIFICATION_SYSTEM_PROMPT_PATH,
    CLASSIFICATION_USER_PROMPT_PATH,
)

PROMPT_DEFAULTS = {
    path: os.path.join(DEFAULT_PROMPTS_DIR, os.path.basename(path))
    for path in PROMPT_PATHS
}

_FILES_TO_COPY = (
    (DEFAULT_CONFIG_SRC, CONFIG_PATH),
    *((src, dst) for dst, src in PROMPT_DEFAULTS.items()),
)


def init_config_dir():
    """Create config directories and copy default files if they don't exist."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)

    for src, dst in _FILES_TO_COPY:
        if not os.path.exists(dst):
            shutil.copy(src, dst)


def _validate_override(key: str, value, default_val) -> None:
    if key == "context_length" and value is None:
        return
    expected = (int, float) if type(default_val) is float else (type(default_val),)
    if type(value) not in expected:
        raise TypeError(_("Invalid configuration value for '{key}'").format(key=key))

    valid = True
    if isinstance(value, str):
        if default_val.startswith("#"):
            valid = bool(_HEX_COLOR_RE.fullmatch(value))
        elif key == "ollama_url":
            parsed = urlparse(value)
            valid = (
                not any(c.isspace() for c in value)
                and parsed.scheme in ("http", "https")
                and bool(parsed.netloc)
            )
        elif key in ("keep_alive", "preload_keep_alive", "search_keep_alive"):
            valid = bool(KEEP_ALIVE_RE.fullmatch(value))
        elif key == "level":
            valid = value.upper() in LOG_LEVELS
        else:
            valid = bool(value.strip())
    elif type(value) in (int, float):
        if key == "sample_rate":
            valid = value >= 8000
        elif key == "channels":
            valid = value in (1, 2)
        elif key == "min_similarity":
            valid = 0.0 <= value <= 1.0
        elif key in ("max_retries", "backup_count"):
            valid = value >= 0
        else:
            valid = 0 < value < float("inf")

    if not valid:
        raise ValueError(_("Invalid configuration value for '{key}'").format(key=key))


def _merge_configs(base: dict, overrides: dict) -> dict:
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


def diff_configs(default: dict, current: dict) -> dict:
    """Recursively diff current config against defaults, returning only overrides."""
    overrides = {}
    for k, default_val in default.items():
        v = current[k]
        if isinstance(default_val, dict) and isinstance(v, dict):
            diff = diff_configs(default_val, v)
            if diff:
                overrides[k] = diff
        elif isinstance(v, bool) != isinstance(default_val, bool) or v != default_val:
            overrides[k] = v
    return overrides


def load_default_config():
    """Load and return the packaged default configuration dictionary."""
    with open(DEFAULT_CONFIG_SRC, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config():
    """Load and merge default config with user overrides."""
    init_config_dir()

    default_config = load_default_config()

    with open(CONFIG_PATH, encoding="utf-8") as f:
        user_config = yaml.safe_load(f)

    if user_config is None:
        user_config = {}
    elif not isinstance(user_config, dict):
        raise TypeError(_("User config at {path} is not a valid YAML mapping").format(path=CONFIG_PATH))

    return _merge_configs(default_config, user_config)


def load_file(path):
    """Load and return the text content of a file."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def atomic_write(path: str, content: str | bytes) -> None:
    """Write content to a file atomically via a temporary replacement file."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    tmp_path = f"{path}.tmp"
    if isinstance(content, bytes):
        with open(tmp_path, "wb") as f:
            f.write(content)
    else:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
    os.replace(tmp_path, path)


def save_config(config_data):
    """Save configuration data to user config file."""
    content = yaml.safe_dump(config_data, default_flow_style=False, sort_keys=False)
    atomic_write(CONFIG_PATH, content)
