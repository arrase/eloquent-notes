"""Base module for config tabs."""

from .ai import AITab
from .audio import AudioTab
from .general import GeneralTab
from .obsidian import ObsidianTab
from .prompts import PromptsTab
from .templates import TemplatesTab

__all__ = [
    "AITab",
    "AudioTab",
    "GeneralTab",
    "ObsidianTab",
    "PromptsTab",
    "TemplatesTab",
]
