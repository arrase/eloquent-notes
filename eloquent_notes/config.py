"""Configuration management for Eloquent Notes.

Handles loading and merging of default and user configuration files,
prompt templates, and note templates from ~/.config/eloquent-notes/.
"""

import os
import shutil

import yaml

CONFIG_DIR = os.path.expanduser("~/.config/eloquent-notes")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")
PROMPTS_DIR = os.path.join(CONFIG_DIR, "prompts")
SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "system_prompt.md")
USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "user_prompt.md")
RETRY_PROMPT_PATH = os.path.join(PROMPTS_DIR, "retry_prompt.md")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_SRC = os.path.join(PACKAGE_DIR, "config.yaml")
DEFAULT_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "system_prompt.md")
DEFAULT_USER_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "user_prompt.md")
DEFAULT_RETRY_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "retry_prompt.md")

TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")
STANDALONE_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "standalone.md")
DAILY_NEW_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "daily_new.md")
DAILY_APPEND_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "daily_append.md")

DEFAULT_STANDALONE_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "standalone.md")
DEFAULT_DAILY_NEW_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "daily_new.md")
DEFAULT_DAILY_APPEND_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "daily_append.md")

_FILES_TO_COPY = [
    (DEFAULT_CONFIG_SRC, CONFIG_PATH),
    (DEFAULT_PROMPT_SRC, SYSTEM_PROMPT_PATH),
    (DEFAULT_USER_PROMPT_SRC, USER_PROMPT_PATH),
    (DEFAULT_RETRY_PROMPT_SRC, RETRY_PROMPT_PATH),
    (DEFAULT_STANDALONE_TEMPLATE_SRC, STANDALONE_TEMPLATE_PATH),
    (DEFAULT_DAILY_NEW_TEMPLATE_SRC, DAILY_NEW_TEMPLATE_PATH),
    (DEFAULT_DAILY_APPEND_TEMPLATE_SRC, DAILY_APPEND_TEMPLATE_PATH),
]


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
    result = base.copy()
    for key, value in overrides.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config():
    """Load and merge default config with user overrides."""
    with open(DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
        default_config = yaml.safe_load(f)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        user_config = yaml.safe_load(f) or {}

    return _merge_configs(default_config, user_config)


def load_file(path):
    """Load and return the text content of a file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
