# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for VideoCue
Build with: pyinstaller VideoCue.spec
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

# NDI DLL path (update this to match your NDI installation)
ndi_dll_path = r'C:\Program Files\NDI\NDI 5 Runtime\v5\Processing.NDI.Lib.x64.dll'

# Prepare binaries list
binaries = []
if os.path.exists(ndi_dll_path):
    binaries.append((ndi_dll_path, '.'))
else:
    print(f"WARNING: NDI DLL not found at {ndi_dll_path}")
    print("NDI features will not work in the built executable.")

# Collect PyQt6 and pygame dynamic libraries
binaries += collect_dynamic_libs('PyQt6')
binaries += collect_dynamic_libs('pygame')

# Prepare data files
datas = [
    ('config_schema.json', '.'),
]

# Add resources if they exist
if os.path.exists('resources'):
    datas.append(('resources', 'resources'))

a = Analysis(
    ['videocue.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'pygame',
        'qdarkstyle',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoCue',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico' if os.path.exists('resources/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoCue',
)
