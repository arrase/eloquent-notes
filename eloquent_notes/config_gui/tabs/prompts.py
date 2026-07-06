"""Prompts configuration tab."""

from eloquent_notes.config_gui.constants import PROMPTS
from eloquent_notes.config_gui.tabs.text_files import TextFilesTab


class PromptsTab(TextFilesTab):
    """Prompts configuration tab."""

    def __init__(self, parent=None):
        super().__init__(
            items=PROMPTS,
            editor_label="Prompt Content:",
            placeholder="Select a prompt to edit...",
            parent=parent,
        )
