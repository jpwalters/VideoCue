"""
Stream Deck library initialization with DLL search path fix for Windows
"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def init_streamdeck_library():
    """
    Initialize python-elgato-streamdeck library with proper DLL loading.

    On Windows, the hidapi.dll needs to be in the DLL search path.
    This function ensures the DLL can be found before importing the library.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Windows 10+ : Add current directory and common DLL locations to search path
        if sys.platform == "win32":
            import os

            if hasattr(os, "add_dll_directory"):
                # Add current directory
                try:
                    current_file = Path(__file__).resolve()
                    project_root = str(current_file.parent.parent.parent)
                    os.add_dll_directory(project_root)
                    logger.info(f"Added DLL search path: {project_root}")
                except Exception as e:
                    logger.warning(f"Could not add project root to DLL path: {e}")

                # Add Python site-packages (where we copied hidapi.dll)
                try:
                    import site

                    for site_dir in site.getsitepackages():
                        site_path = Path(site_dir)
                        if site_path.exists():
                            os.add_dll_directory(site_dir)
                            logger.debug(f"Added DLL search path: {site_dir}")
                except Exception as e:
                    logger.warning(f"Could not add site-packages to DLL path: {e}")

        # Now try to import the StreamDeck library
        from StreamDeck.DeviceManager import DeviceManager  # noqa: F401
        from StreamDeck.Devices.StreamDeck import DialEventType, TouchscreenEventType  # noqa: F401

        logger.info("python-elgato-streamdeck library loaded successfully")
        return True

    except ImportError as e:
        logger.warning(f"Stream Deck library not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Stream Deck library initialization error: {e}")
        return False


# Initialize on module import
_streamdeck_available = init_streamdeck_library()


def is_streamdeck_available() -> bool:
    """Check if Stream Deck library is available"""
    return _streamdeck_available
