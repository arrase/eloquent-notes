import os
import shutil
import yaml

CONFIG_DIR = os.path.expanduser("~/.config/eloquent-notes")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.yaml")
PROMPTS_DIR = os.path.join(CONFIG_DIR, "prompts")
SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, "system_prompt.md")
USER_PROMPT_PATH = os.path.join(PROMPTS_DIR, "user_prompt.md")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_SRC = os.path.join(PACKAGE_DIR, "config.yaml")
DEFAULT_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "system_prompt.md")
DEFAULT_USER_PROMPT_SRC = os.path.join(PACKAGE_DIR, "prompts", "user_prompt.md")

TEMPLATES_DIR = os.path.join(CONFIG_DIR, "templates")
STANDALONE_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "standalone.md")
DAILY_NEW_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "daily_new.md")
DAILY_APPEND_TEMPLATE_PATH = os.path.join(TEMPLATES_DIR, "daily_append.md")

DEFAULT_STANDALONE_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "standalone.md")
DEFAULT_DAILY_NEW_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "daily_new.md")
DEFAULT_DAILY_APPEND_TEMPLATE_SRC = os.path.join(PACKAGE_DIR, "templates", "daily_append.md")

def init_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    if not os.path.exists(CONFIG_PATH) and os.path.exists(DEFAULT_CONFIG_SRC):
        shutil.copy(DEFAULT_CONFIG_SRC, CONFIG_PATH)

    if not os.path.exists(SYSTEM_PROMPT_PATH) and os.path.exists(DEFAULT_PROMPT_SRC):
        shutil.copy(DEFAULT_PROMPT_SRC, SYSTEM_PROMPT_PATH)

    if not os.path.exists(USER_PROMPT_PATH) and os.path.exists(DEFAULT_USER_PROMPT_SRC):
        shutil.copy(DEFAULT_USER_PROMPT_SRC, USER_PROMPT_PATH)

    if not os.path.exists(STANDALONE_TEMPLATE_PATH) and os.path.exists(DEFAULT_STANDALONE_TEMPLATE_SRC):
        shutil.copy(DEFAULT_STANDALONE_TEMPLATE_SRC, STANDALONE_TEMPLATE_PATH)

    if not os.path.exists(DAILY_NEW_TEMPLATE_PATH) and os.path.exists(DEFAULT_DAILY_NEW_TEMPLATE_SRC):
        shutil.copy(DEFAULT_DAILY_NEW_TEMPLATE_SRC, DAILY_NEW_TEMPLATE_PATH)

    if not os.path.exists(DAILY_APPEND_TEMPLATE_PATH) and os.path.exists(DEFAULT_DAILY_APPEND_TEMPLATE_SRC):
        shutil.copy(DEFAULT_DAILY_APPEND_TEMPLATE_SRC, DAILY_APPEND_TEMPLATE_PATH)

def merge_configs(dict1, dict2):
    result = dict1.copy()
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    return result

def load_config():
    with open(DEFAULT_CONFIG_SRC, "r", encoding="utf-8") as f:
        default_config = yaml.safe_load(f)

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            return merge_configs(default_config, user_config)
        
    return default_config

def _load_prompt(user_path, default_path):
    path = user_path if os.path.exists(user_path) else default_path
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_prompt_template():
    return _load_prompt(SYSTEM_PROMPT_PATH, DEFAULT_PROMPT_SRC)

def load_user_prompt_template():
    return _load_prompt(USER_PROMPT_PATH, DEFAULT_USER_PROMPT_SRC)

def load_standalone_template():
    return _load_prompt(STANDALONE_TEMPLATE_PATH, DEFAULT_STANDALONE_TEMPLATE_SRC)

def load_daily_new_template():
    return _load_prompt(DAILY_NEW_TEMPLATE_PATH, DEFAULT_DAILY_NEW_TEMPLATE_SRC)

def load_daily_append_template():
    return _load_prompt(DAILY_APPEND_TEMPLATE_PATH, DEFAULT_DAILY_APPEND_TEMPLATE_SRC)
