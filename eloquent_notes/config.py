"""Configuration management for Eloquent Notes.

Handles loading and merging of default and user configuration files,
prompt templates, and note templates from ~/.config/eloquent-notes/.
"""

import copy
import os
import shutil

import yaml

CONFIG_DIR = os.path.expanduser("~/.config/eloquent-notes")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")

PROMPTS_DIR = os.path.join(CONFIG_DIR, "prompts")
TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_SRC = os.path.join(PACKAGE_DIR, "config.yaml")

_MANAGED_FILES = [
    ("RETRY", "prompts", "retry_prompt.md"),
    ("TRANSCRIPTION_SYSTEM", "prompts", "transcription_system.md"),
    ("TRANSCRIPTION_USER", "prompts", "transcription_user.md"),
    ("REWRITING_SYSTEM", "prompts", "rewriting_system.md"),
    ("REWRITING_USER", "prompts", "rewriting_user.md"),
    ("CLASSIFICATION_SYSTEM", "prompts", "classification_system.md"),
    ("CLASSIFICATION_USER", "prompts", "classification_user.md"),
    ("STANDALONE", "templates", "standalone.md"),
    ("DAILY_NEW", "templates", "daily_new.md"),
    ("DAILY_APPEND", "templates", "daily_append.md"),
]

PROMPT_AND_TEMPLATE_PATHS = []
_FILES_TO_COPY = [(DEFAULT_CONFIG_SRC, CONFIG_PATH)]

for _base, _subdir, _filename in _MANAGED_FILES:
    if _subdir == "prompts":
        _user_var = f"{_base}_PROMPT_PATH"
        _default_var = f"DEFAULT_{_base}_SRC" if _base != "RETRY" else "DEFAULT_RETRY_PROMPT_SRC"
    else:
        _user_var = f"{_base}_TEMPLATE_PATH"
        _default_var = f"DEFAULT_{_base}_TEMPLATE_SRC"

    _target_dir = PROMPTS_DIR if _subdir == "prompts" else TEMPLATES_DIR
    _user_path = os.path.join(_target_dir, _filename)
    _src_path = os.path.join(PACKAGE_DIR, _subdir, _filename)

    globals()[_user_var] = _user_path
    globals()[_default_var] = _src_path

    PROMPT_AND_TEMPLATE_PATHS.append(_user_path)
    _FILES_TO_COPY.append((_src_path, _user_path))

PROMPT_AND_TEMPLATE_PATHS = tuple(PROMPT_AND_TEMPLATE_PATHS)


def init_config_dir():
    """Create config directories and copy default files if they don't exist."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    for src, dst in _FILES_TO_COPY:
        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copy(src, dst)


def _merge_configs(base, overrides):
    """Recursively merge overrides into base config dict."""
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config():
    """Load and merge default config with user overrides."""
    init_config_dir()

    with open(DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
        default_config = yaml.safe_load(f) or {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    if not isinstance(default_config, dict):
        raise ValueError(f"Default config at {DEFAULT_CONFIG_SRC} is not a valid YAML mapping")

    if not isinstance(user_config, dict):
        raise ValueError(f"User config at {CONFIG_PATH} is not a valid YAML mapping")

    return _merge_configs(default_config, user_config)


def load_file(path):
    """Load and return the text content of a file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_config(config_data):
    """Save configuration data to user config file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp_path = f"{CONFIG_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, default_flow_style=False, sort_keys=False)
    os.replace(tmp_path, CONFIG_PATH)


def save_file(path, content):
    """Save text content to a file."""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)
