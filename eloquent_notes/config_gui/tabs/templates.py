"""Templates configuration tab."""

from eloquent_notes.config_gui.constants import TEMPLATES
from eloquent_notes.config_gui.tabs.text_files import TextFilesTab


class TemplatesTab(TextFilesTab):
    """Templates configuration tab."""

    def __init__(self, parent=None):
        super().__init__(
            items=TEMPLATES,
            editor_label="Template Content:",
            placeholder="Select a template to edit...",
            parent=parent,
        )
