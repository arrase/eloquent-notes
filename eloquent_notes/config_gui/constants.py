"""Constants for Eloquent Notes configuration GUI."""

from eloquent_notes import config

PROMPTS = [
    (
        "Transcription - System Prompt",
        config.TRANSCRIPTION_SYSTEM_PROMPT_PATH,
        config.DEFAULT_TRANSCRIPTION_SYSTEM_SRC,
    ),
    (
        "Transcription - User Prompt",
        config.TRANSCRIPTION_USER_PROMPT_PATH,
        config.DEFAULT_TRANSCRIPTION_USER_SRC,
    ),
    (
        "Rewriting - System Prompt",
        config.REWRITING_SYSTEM_PROMPT_PATH,
        config.DEFAULT_REWRITING_SYSTEM_SRC,
    ),
    (
        "Rewriting - User Prompt",
        config.REWRITING_USER_PROMPT_PATH,
        config.DEFAULT_REWRITING_USER_SRC,
    ),
    (
        "Classification - System Prompt",
        config.CLASSIFICATION_SYSTEM_PROMPT_PATH,
        config.DEFAULT_CLASSIFICATION_SYSTEM_SRC,
    ),
    (
        "Classification - User Prompt",
        config.CLASSIFICATION_USER_PROMPT_PATH,
        config.DEFAULT_CLASSIFICATION_USER_SRC,
    ),
    ("Retry Prompt", config.RETRY_PROMPT_PATH, config.DEFAULT_RETRY_PROMPT_SRC),
]

TEMPLATES = [
    (
        "Standalone Note Template",
        config.STANDALONE_TEMPLATE_PATH,
        config.DEFAULT_STANDALONE_TEMPLATE_SRC,
    ),
    (
        "Daily Note - New",
        config.DAILY_NEW_TEMPLATE_PATH,
        config.DEFAULT_DAILY_NEW_TEMPLATE_SRC,
    ),
    (
        "Daily Note - Append",
        config.DAILY_APPEND_TEMPLATE_PATH,
        config.DEFAULT_DAILY_APPEND_TEMPLATE_SRC,
    ),
]
