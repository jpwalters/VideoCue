"""
Utility functions for resource loading (PyInstaller compatible)
"""
import sys
import os
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # pylint: disable=no-member,protected-access
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_app_data_dir() -> Path:
    """Get application data directory"""
    if os.name == 'nt':
        # Windows: %LOCALAPPDATA%/VideoCue
        app_data = Path(os.getenv('LOCALAPPDATA', '')) / 'VideoCue'
    else:
        # Unix: ~/.config/VideoCue
        app_data = Path.home() / '.config' / 'VideoCue'

    app_data.mkdir(parents=True, exist_ok=True)
    return app_data
