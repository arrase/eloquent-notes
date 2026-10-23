"""Configuration management for Eloquent Notes.

Handles loading and merging of default and user configuration files
and prompt files from ~/.config/eloquent-notes/.
"""

import copy
import os
import shutil

import yaml


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

RETRY_PROMPT_PATH = os.path.join(PROMPTS_DIR, "retry_prompt.md")
TRANSCRIPTION_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "transcription_system.md")
TRANSCRIPTION_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "transcription_user.md")
REWRITING_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "rewriting_system.md")
REWRITING_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "rewriting_user.md")
CLASSIFICATION_SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "classification_system.md")
CLASSIFICATION_USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "classification_user.md")

DEFAULT_RETRY_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "retry_prompt.md")
DEFAULT_TRANSCRIPTION_SYSTEM_SRC = os.path.join(PACKAGE_DIR, "prompts", "transcription_system.md")
DEFAULT_TRANSCRIPTION_USER_SRC = os.path.join(PACKAGE_DIR, "prompts", "transcription_user.md")
DEFAULT_REWRITING_SYSTEM_SRC = os.path.join(PACKAGE_DIR, "prompts", "rewriting_system.md")
DEFAULT_REWRITING_USER_SRC = os.path.join(PACKAGE_DIR, "prompts", "rewriting_user.md")
DEFAULT_CLASSIFICATION_SYSTEM_SRC = os.path.join(PACKAGE_DIR, "prompts", "classification_system.md")
DEFAULT_CLASSIFICATION_USER_SRC = os.path.join(PACKAGE_DIR, "prompts", "classification_user.md")

_FILES_TO_COPY = (
    (DEFAULT_CONFIG_SRC, CONFIG_PATH),
    (DEFAULT_RETRY_PROMPT_SRC, RETRY_PROMPT_PATH),
    (DEFAULT_TRANSCRIPTION_SYSTEM_SRC, TRANSCRIPTION_SYSTEM_PROMPT_PATH),
    (DEFAULT_TRANSCRIPTION_USER_SRC, TRANSCRIPTION_USER_PROMPT_PATH),
    (DEFAULT_REWRITING_SYSTEM_SRC, REWRITING_SYSTEM_PROMPT_PATH),
    (DEFAULT_REWRITING_USER_SRC, REWRITING_USER_PROMPT_PATH),
    (DEFAULT_CLASSIFICATION_SYSTEM_SRC, CLASSIFICATION_SYSTEM_PROMPT_PATH),
    (DEFAULT_CLASSIFICATION_USER_SRC, CLASSIFICATION_USER_PROMPT_PATH),
)

PROMPT_PATHS = tuple(dst for _, dst in _FILES_TO_COPY[1:])


def init_config_dir():
    """Create config directories and copy default files if they don't exist."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)

    for src, dst in _FILES_TO_COPY:
        if not os.path.exists(dst):
            shutil.copy(src, dst)


def _validate_override(key: str, value, default_val) -> None:
    if default_val is None or (key == "context_length" and value is None):
        return
    expected = (int, float) if type(default_val) is float else (type(default_val),)
    if type(value) not in expected:
        raise TypeError(f"Invalid configuration value for '{key}'")


def _merge_configs(base: dict, overrides: dict) -> dict:
    """Recursively merge overrides into base config dict."""
    result = copy.deepcopy(base)
    for k, v in overrides.items():
        default_val = result.get(k)
        if isinstance(default_val, dict):
            if not isinstance(v, dict):
                raise TypeError(
                    f"Configuration section '{k}' must be a mapping, got {type(v).__name__}"
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
        raise TypeError(f"User config at {CONFIG_PATH} is not a valid YAML mapping")

    return _merge_configs(default_config, user_config)


def load_file(path):
    """Load and return the text content of a file."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def atomic_write(path, content):
    """Write content to a file atomically via a temporary replacement file."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)


def save_config(config_data):
    """Save configuration data to user config file."""
    content = yaml.safe_dump(config_data, default_flow_style=False, sort_keys=False)
    atomic_write(CONFIG_PATH, content)
