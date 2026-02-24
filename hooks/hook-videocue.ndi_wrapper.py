"""PyInstaller hook for videocue.ndi_wrapper.

Ensures the local NDI native bindings are collected without importing the
extension module during analysis.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import get_package_paths

hiddenimports = ["videocue.ndi_wrapper.NDIlib"]

binaries = []

_base_path, package_path = get_package_paths("videocue.ndi_wrapper")
wrapper_dir = Path(package_path)

python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
matching_pyd = sorted(wrapper_dir.glob(f"NDIlib.{python_tag}-*.pyd"))
all_pyd = sorted(wrapper_dir.glob("NDIlib*.pyd"))
selected_pyd = matching_pyd if matching_pyd else all_pyd

for pyd_file in selected_pyd:
    binaries.append((str(pyd_file), "videocue/ndi_wrapper"))

ndi_dll = wrapper_dir / "Processing.NDI.Lib.x64.dll"
if ndi_dll.exists():
    binaries.append((str(ndi_dll), "videocue/ndi_wrapper"))
