"""
Utility functions for VideoCue application
"""

import os
import re
import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller.

    Args:
        relative_path: Relative path to the resource file

    Returns:
        Absolute path to the resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        # pylint: disable=no-member,protected-access
        base_path: str = sys._MEIPASS  # type: ignore
    except AttributeError:
        base_path = os.path.abspath(".")  # noqa: PTH100

    return os.path.join(base_path, relative_path)  # noqa: PTH118


def get_app_data_dir() -> Path:
    """
    Get application data directory.

    Returns:
        Path to application data directory (creates if doesn't exist)
        - Windows: %LOCALAPPDATA%/VideoCue
        - Unix: ~/.config/VideoCue
    """
    if os.name == "nt":
        # Windows: %LOCALAPPDATA%/VideoCue
        local_app_data: str | None = os.getenv("LOCALAPPDATA")
        if not local_app_data:
            local_app_data = str(Path.home() / "AppData" / "Local")
        app_data = Path(local_app_data) / "VideoCue"
    else:
        # Unix: ~/.config/VideoCue
        app_data = Path.home() / ".config" / "VideoCue"

    app_data.mkdir(parents=True, exist_ok=True)
    return app_data


def truncate_error(error: Exception, max_length: int = 50) -> str:
    """
    Truncate error message for UI display.

    Args:
        error: Exception to format
        max_length: Maximum length of error message

    Returns:
        Truncated error message string
    """
    return str(error)[:max_length]


# IP address extraction pattern
IP_PATTERN = re.compile(r"(\d+\.\d+\.\d+\.\d+)")


def extract_ip_from_url(url: str) -> str | None:
    """
    Extract IP address from URL string.

    Args:
        url: URL string that may contain an IP address

    Returns:
        IP address string if found, None otherwise
    """
    match = IP_PATTERN.search(url)
    return match.group(1) if match else None


# Re-export network_interface module for convenience
from videocue.utils.network_interface import (  # noqa: E402, F401
    NetworkInterface,
    find_interface_for_camera,
    get_network_interfaces,
    get_preferred_interface_ip,
)
