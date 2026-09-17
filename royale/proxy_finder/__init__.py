"""Public interface for CLI and future API integration."""

from .config import Settings
from .service import find_matching_ip

__all__ = ['Settings', 'find_matching_ip']
