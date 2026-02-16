"""
PyInstaller spec file for VideoCue
Build with: pyinstaller VideoCue.spec
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None

# NDI DLL path (bundled in videocue/ndi_wrapper or in libs directory for CI builds)
ndi_dll_paths = [
    r"videocue\ndi_wrapper\Processing.NDI.Lib.x64.dll",  # Bundled with VideoCue
    r"libs\Processing.NDI.Lib.x64.dll",  # CI build or repository copy (fallback)
    r"C:\Program Files\NDI\NDI 6 Runtime\v6\Processing.NDI.Lib.x64.dll",  # Local install
    str(Path.cwd() / "videocue" / "ndi_wrapper" / "Processing.NDI.Lib.x64.dll"),  # Relative path
]

# Prepare binaries list
binaries = []
ndi_dll_found = False
for ndi_dll_path in ndi_dll_paths:
    if Path(ndi_dll_path).exists():
        binaries.append((ndi_dll_path, "videocue/ndi_wrapper"))
        ndi_dll_found = True
        print(f"[OK] NDI DLL found at: {ndi_dll_path}")
        break

if not ndi_dll_found:
    print("WARNING: NDI DLL not found. Checking if NDI Runtime is installed on system...")
    # Don't fail the build - NDI is optional

# Collect PyQt6 and pygame dynamic libraries
binaries += collect_dynamic_libs("PyQt6")
binaries += collect_dynamic_libs("pygame")

# Collect NDI Python module bindings (bundled in videocue/ndi_wrapper)
# The .pyd files are included automatically via datas below

# Prepare data files
datas = [
    ("config_schema.json", "."),
    ("videocue/ndi_wrapper", "videocue/ndi_wrapper"),  # Include NDI wrapper with bindings
]

# Add resources if they exist
if Path("resources").exists():
    datas.append(("resources", "resources"))

a = Analysis(  # noqa: F821
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
        "videocue.ndi_wrapper",  # Local NDI wrapper module (bundled)
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
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
    icon=str(Path("resources/icon.ico").resolve()) if Path("resources/icon.ico").exists() else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VideoCue",
)
