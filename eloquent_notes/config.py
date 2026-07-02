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

def init_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)

    if not os.path.exists(CONFIG_PATH) and os.path.exists(DEFAULT_CONFIG_SRC):
        shutil.copy(DEFAULT_CONFIG_SRC, CONFIG_PATH)

    if not os.path.exists(SYSTEM_PROMPT_PATH) and os.path.exists(DEFAULT_PROMPT_SRC):
        shutil.copy(DEFAULT_PROMPT_SRC, SYSTEM_PROMPT_PATH)

    if not os.path.exists(USER_PROMPT_PATH) and os.path.exists(DEFAULT_USER_PROMPT_SRC):
        shutil.copy(DEFAULT_USER_PROMPT_SRC, USER_PROMPT_PATH)

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
        default_config = yaml.safe_load(f) or {}

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            return merge_configs(default_config, user_config)
        
    return default_config

def load_prompt_template():
    path = SYSTEM_PROMPT_PATH if os.path.exists(SYSTEM_PROMPT_PATH) else DEFAULT_PROMPT_SRC
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def load_user_prompt_template():
    path = USER_PROMPT_PATH if os.path.exists(USER_PROMPT_PATH) else DEFAULT_USER_PROMPT_SRC
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# Initialize configuration directories and copy defaults upon module import
init_config_dir()
