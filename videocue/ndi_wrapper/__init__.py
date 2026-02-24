"""
NDI Wrapper Module

This module provides Python bindings to the NDI (Network Device Interface) SDK.

The bindings are based on the ndi-python project by Naoto Kondo:
  - Project: https://github.com/buresu/ndi-python
  - License: MIT (see LICENSE.md in this directory)

This version includes bug fixes and improvements made to the original ndi-python project
to ensure better thread safety, memory management, and error handling.
"""

import contextlib
import importlib
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
_ndilib_module = None

# On Windows, add the directory containing NDI DLLs to the DLL search path
# This is necessary for the compiled .pyd extension to find Processing.NDI.Lib.x64.dll
if os.name == "nt" and sys.version_info >= (3, 8):
    dll_paths = []

    # 1. Add wrapper directory first (for bundled DLLs in portable/executable)
    wrapper_dir = Path(__file__).parent
    dll_paths.append(wrapper_dir)

    # 2. Add NDI Runtime library directory (system installation - primary)
    ndi_runtime_paths = [
        Path("C:/Program Files/NDI/NDI 6 Runtime/v6"),
        Path("C:/Program Files/NDI/NDI 5 Runtime/v5"),
        Path("C:/Program Files/NDI/NDI Runtime"),
    ]

    for ndi_path in ndi_runtime_paths:
        if ndi_path.exists():
            dll_paths.append(ndi_path)

    # 3. Add NDI SDK library directory if it exists (fallback)
    ndi_sdk_paths = [
        Path("C:/Program Files/NDI/NDI 6 SDK/Lib/x64"),
        Path("C:/Program Files (x86)/NDI SDK/Lib/x64"),
        Path("C:/NDI SDK/Lib/x64"),
    ]

    for ndi_path in ndi_sdk_paths:
        if ndi_path.exists():
            dll_paths.append(ndi_path)

    # 4. Also check registry for NDI installation
    if not any(p.exists() for p in ndi_sdk_paths + ndi_runtime_paths):
        try:
            import winreg

            reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\NewTek\NDI")
            ndi_root, _ = winreg.QueryValueEx(reg_key, "PathToApp")
            ndi_lib_path = Path(ndi_root) / "Lib" / "x64"
            if ndi_lib_path.exists():
                dll_paths.append(ndi_lib_path)
            winreg.CloseKey(reg_key)
        except Exception:
            pass  # NDI not found in registry

    # Add all found paths to DLL search
    for path in dll_paths:
        with contextlib.suppress(Exception):
            os.add_dll_directory(str(path))


def _load_ndilib():
    """Load the compiled NDI extension module lazily."""
    global _ndilib_module
    if _ndilib_module is not None:
        return _ndilib_module

    try:
        ndilib = importlib.import_module(".NDIlib", __name__)

        _ndilib_module = ndilib
        return _ndilib_module
    except ImportError as e:
        logger.debug(
            f"NDI bindings not available: {e}\n"
            "This usually means:\n"
            "1. The NDI SDK is not installed (download from https://ndi.tv/tools/)\n"
            "2. The compiled NDI wrapper (.pyd/.so) is not compatible with your Python version\n"
            "3. DLL dependencies are missing on Windows"
        )
        raise ImportError(
            f"NDI SDK bindings not available: {e}. "
            "Install NDI Runtime from https://ndi.tv/tools/ or build the wrapper from source."
        ) from e


def __getattr__(name: str):
    """Proxy attribute access to the compiled NDI extension module."""
    ndilib = _load_ndilib()
    return getattr(ndilib, name)


def __dir__():
    """Expose extension attributes for introspection/completion when available."""
    base_names = set(globals().keys())
    with contextlib.suppress(ImportError):
        base_names.update(dir(_load_ndilib()))
    return sorted(base_names)


def ensure_loaded() -> bool:
    """Return True if the native NDI extension can be loaded."""
    _load_ndilib()
    return True


__all__ = []
