"""
PyInstaller spec file for VideoCue
Build with: pyinstaller VideoCue.spec
"""

import os

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# NDI DLL path (checks multiple locations for local and CI builds)
ndi_dll_paths = [
    r"libs\Processing.NDI.Lib.x64.dll",  # CI build or repository copy
    r"C:\Program Files\NDI\NDI 6 SDK\Bin\x64\Processing.NDI.Lib.x64.dll",  # Local install
    os.path.join(os.getcwd(), "libs", "Processing.NDI.Lib.x64.dll"),  # Relative path
]

# Prepare binaries list
binaries = []
ndi_dll_found = False
for ndi_dll_path in ndi_dll_paths:
    if os.path.exists(ndi_dll_path):
        binaries.append((ndi_dll_path, "."))
        ndi_dll_found = True
        print(f"[OK] NDI DLL found at: {ndi_dll_path}")
        break

if not ndi_dll_found:
    print("WARNING: NDI DLL not found at any of these locations:")
    for path in ndi_dll_paths:
        print(f"  - {path}")
    print("NDI features will not work in the built executable.")

# Collect PyQt6 and pygame dynamic libraries
binaries += collect_dynamic_libs("PyQt6")
binaries += collect_dynamic_libs("pygame")

# Collect NDI Python module if available
try:
    binaries += collect_dynamic_libs("NDIlib")
except Exception:
    pass  # NDI not installed, skip

# Prepare data files
datas = [
    ("config_schema.json", "."),
]

# Add resources if they exist
if os.path.exists("resources"):
    datas.append(("resources", "resources"))

a = Analysis(
    ["videocue.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "pygame",
        "qdarkstyle",
        # Comprehensive numpy imports for ndi-python compatibility
        "numpy",
        "numpy.core",
        "numpy.core._methods",
        "numpy.core._internal",
        "numpy.core.multiarray",
        "numpy.core._multiarray_umath",
        "numpy.core._dtype",
        "numpy.core.numerictypes",
        "numpy.core.umath",
        "numpy.lib.format",
        "numpy.random",
        "numpy.random._common",
        "numpy.random._generator",
        "numpy.linalg",
        "numpy.fft",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused PyQt6 modules to reduce warnings and build size
        "PyQt6.Qt3DAnimation",
        "PyQt6.Qt3DCore",
        "PyQt6.Qt3DExtras",
        "PyQt6.Qt3DInput",
        "PyQt6.Qt3DLogic",
        "PyQt6.Qt3DRender",
        "PyQt6.QtBluetooth",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
        "PyQt6.QtDBus",
        "PyQt6.QtDesigner",
        "PyQt6.QtHelp",
        "PyQt6.QtLocation",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtNfc",
        "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtPositioning",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSpatialAudio",
        "PyQt6.QtSql",
        "PyQt6.QtSvg",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtTest",
        "PyQt6.QtTextToSpeech",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebEngine",
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebSockets",
        "PyQt6.QtWebView",
    ],
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
    name="VideoCue",
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
    icon=os.path.abspath("resources/icon.ico") if os.path.exists("resources/icon.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoCue",
)
