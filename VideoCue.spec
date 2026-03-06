"""
PyInstaller spec file for VideoCue
Build with: pyinstaller VideoCue.spec
"""

import platform
import sys
from pathlib import Path

from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_dynamic_libs

block_cipher = None
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"

# NDI runtime paths by OS (NDI is optional)
if IS_WINDOWS:
    ndi_runtime_paths = [
        r"videocue\ndi_wrapper\Processing.NDI.Lib.x64.dll",  # Bundled with VideoCue
        r"libs\Processing.NDI.Lib.x64.dll",  # CI build or repository copy (fallback)
        r"C:\Program Files\NDI\NDI 6 Runtime\v6\Processing.NDI.Lib.x64.dll",  # Local install
        str(Path.cwd() / "videocue" / "ndi_wrapper" / "Processing.NDI.Lib.x64.dll"),
    ]
elif IS_MACOS:
    ndi_runtime_paths = [
        "videocue/ndi_wrapper/Processing.NDI.Lib.arm64.dylib",  # Bundled with VideoCue
        "videocue/ndi_wrapper/Processing.NDI.Lib.x86_64.dylib",  # Bundled with VideoCue
        "/usr/local/lib/libndi.dylib",  # Common NDI runtime location
        "/usr/local/lib/Processing.NDI.Lib.dylib",  # Alternate runtime name
        "/opt/homebrew/lib/libndi.dylib",  # Homebrew prefix on Apple Silicon
    ]
else:
    ndi_runtime_paths = [
        "videocue/ndi_wrapper/libndi.so",
        "/usr/lib/libndi.so",
        "/usr/local/lib/libndi.so",
    ]

# Prepare binaries list
binaries = []
ndi_runtime_found = False
for ndi_runtime_path in ndi_runtime_paths:
    if Path(ndi_runtime_path).exists():
        binaries.append((ndi_runtime_path, "videocue/ndi_wrapper"))
        ndi_runtime_found = True
        print(f"[OK] NDI runtime found at: {ndi_runtime_path}")
        break

if not ndi_runtime_found:
    print(
        "WARNING: NDI runtime not found in known locations. App will run in IP-only mode if unavailable."
    )
    # Don't fail the build - NDI is optional

# Collect PyQt6 and pygame dynamic libraries
binaries += collect_dynamic_libs("PyQt6")
binaries += collect_dynamic_libs("pygame")

# Collect streamdeck library dependencies (hidapi DLL for USB communication)
try:
    binaries += collect_dynamic_libs("streamdeck")
    print("[OK] Stream Deck library dependencies collected")
except Exception as e:
    print(f"[INFO] Stream Deck library not found (optional): {e}")

# Windows-specific explicit hidapi.dll packaging (Stream Deck support)
if IS_WINDOWS:
    hidapi_dll_paths = [
        "hidapi.dll",  # Project root (development)
        str(Path.cwd() / "hidapi.dll"),  # Absolute project root
    ]

    # Also check site-packages where pip might have installed it
    try:
        import site

        for site_dir in site.getsitepackages():
            hidapi_dll_paths.append(str(Path(site_dir) / "hidapi.dll"))
    except Exception:
        pass

    hidapi_found = False
    for hidapi_path in hidapi_dll_paths:
        if Path(hidapi_path).exists():
            binaries.append((hidapi_path, "."))
            hidapi_found = True
            print(f"[OK] hidapi.dll found at: {hidapi_path}")
            break

    if not hidapi_found:
        print(
            "[INFO] hidapi.dll not found (Stream Deck support may require manual DLL installation)"
        )

# Replace old bundled VC runtime DLLs (from PyQt) with current system versions.
# Older 14.26 runtime binaries can conflict with newer native SDKs (e.g. NDI 6.x)
# and cause native startup crashes in frozen builds.
vc_runtime_names = {
    "msvcp140.dll",
    "msvcp140_1.dll",
    "msvcp140_2.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
}

if IS_WINDOWS:
    binaries = [
        (src, dst) for src, dst in binaries if Path(src).name.lower() not in vc_runtime_names
    ]

    system32 = Path(r"C:/Windows/System32")
    for runtime_name in sorted(vc_runtime_names):
        runtime_path = system32 / runtime_name
        if runtime_path.exists():
            binaries.append((str(runtime_path), "."))
            print(f"[OK] VC runtime added from System32: {runtime_name}")

# Collect NDI Python module bindings (.pyd/.so files) - MUST be in binaries not datas!
ndi_wrapper_dir = Path("videocue/ndi_wrapper")
python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"

if IS_WINDOWS:
    ndi_binding_patterns = [f"NDIlib.{python_tag}-*.pyd", "*.pyd"]
else:
    ndi_binding_patterns = [
        f"NDIlib.{python_tag}-*.so",
        f"NDIlib.cpython-{sys.version_info.major}{sys.version_info.minor}*-darwin*.so",
        "*.so",
    ]

ndi_binding_files = []
for pattern in ndi_binding_patterns:
    ndi_binding_files = list(ndi_wrapper_dir.glob(pattern))
    if ndi_binding_files:
        break

for binding_file in ndi_binding_files:
    binaries.append((str(binding_file), "videocue/ndi_wrapper"))
    print(f"[OK] NDI binding added: {binding_file.name}")

# Prepare data files
datas = [
    ("config_schema.json", "."),
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
        "videocue.ndi_wrapper.NDIlib",  # Native extension loaded lazily at runtime
        # Stream Deck Plus support (optional)
        "streamdeck",
        "StreamDeck.DeviceManager",
        "StreamDeck.Devices.StreamDeck",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
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
    hookspath=[str(Path("hooks").resolve())],
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

# Final runtime sanitization at Analysis output level: remove any stale VC runtime
# copies (including those pulled transitively into PyQt subfolders), then add
# current System32 runtime binaries once.
if IS_WINDOWS:
    filtered_binaries = [
        entry for entry in a.binaries if Path(entry[0]).name.lower() not in vc_runtime_names
    ]

    for runtime_name in sorted(vc_runtime_names):
        runtime_path = system32 / runtime_name
        if runtime_path.exists():
            filtered_binaries.append((runtime_name, str(runtime_path), "BINARY"))

    a.binaries = TOC(filtered_binaries)

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
    icon=(
        str(Path("resources/icon.ico").resolve())
        if Path("resources/icon.ico").exists() and IS_WINDOWS
        else None
    ),
)

if IS_MACOS:
    app = BUNDLE(  # noqa: F821
        exe,
        name="VideoCue.app",
        icon=str(Path("resources/icon.icns").resolve())
        if Path("resources/icon.icns").exists()
        else None,
        bundle_identifier="com.jpw.videocue",
    )

    coll = COLLECT(  # noqa: F821
        app,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="VideoCue",
    )
else:
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
