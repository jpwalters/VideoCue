# NDI Wrapper - Building from Source

This document explains how to rebuild the NDI Python bindings (`.pyd` files) from the C++ source code included in this project.

## Prerequisites

### Windows (Primary Target)

1. **Visual Studio 2019 or 2022** with C++ workload
   - Includes MSVC compiler and build tools
   - Download from: https://visualstudio.microsoft.com/downloads/

2. **CMake 3.17+**
   ```powershell
   choco install cmake
   # Or download from https://cmake.org/download/
   ```

3. **Python Development Headers**
   - Install with your Python version (usually included)
   - Verify: `python -m pip install pybind11`

4. **NDI SDK** (Required at build time)
   - Download NDI SDK from: https://ndi.tv/tools/
   - Install to default location (or set `NDI_PATH` environment variable)
   - SDK includes headers (`Processing.NDI.Lib.h`) and library files

5. **pybind11 dependency**
   ```bash
   git submodule update --init --recursive
   # OR manually clone:
   git clone https://github.com/pybind/pybind11.git lib/pybind11
   ```

### macOS

Additional requirements:
- Xcode Command Line Tools: `xcode-select --install`
- Homebrew package manager

### Linux

Additional requirements:
```bash
sudo apt-get install build-essential cmake python3-dev
```

## Building Steps

### Step 1: Set Up Build Directory

```bash
cd videocue/ndi_wrapper
mkdir build
cd build
```

### Step 2: Configure with CMake

**Windows:**
```powershell
cmake .. -G "Visual Studio 16 2019" -A x64
# Or for Visual Studio 2022:
cmake .. -G "Visual Studio 17 2022" -A x64
```

**macOS/Linux:**
```bash
cmake ..
```

**Custom NDI Location (if not installed to default):**
```bash
cmake .. -DNDI_PATH="C:/NDI SDK 6.x"
```

### Step 3: Build

**Windows:**
```powershell
cmake --build . --config Release
```

**macOS/Linux:**
```bash
cmake --build . --config Release -- -j$(nproc)
```

### Step 4: Output

The compiled bindings will be in your build directory:
- **Windows**: `Release/NDIlib.cp{version}-win_amd64.pyd`
- **macOS**: `NDIlib.cpython-{version}-darwin.so`
- **Linux**: `NDIlib.cpython-{version}-x86_64-linux-gnu.so`

### Step 5: Install

Copy the generated `.pyd` (or `.so`) file back to `videocue/ndi_wrapper/`:

**Windows:**
```powershell
Copy-Item "Release/NDIlib.cp*.pyd" "../NDIlib.cp312-win_amd64.pyd"
```

**macOS/Linux:**
```bash
cp NDIlib.cpython-*.so ../NDIlib.cpython-312-darwin.so
```

## CMake Find Module

The build system uses `cmake/Modules/FindNDI.cmake` to locate the NDI SDK. This module searches for:

1. `NDI_PATH` environment variable
2. Default installation paths:
   - **Windows**: `C:/NDI SDK 6.x`, `C:/NDI/`
   - **macOS**: `/Applications/NDI/`, `/usr/local/NDI/`
   - **Linux**: `/opt/NDI/`, `/usr/local/NDI/`

If you install NDI to a non-standard location, set the environment variable:

```bash
# Windows
set NDI_PATH=C:\path\to\NDI\SDK

# macOS/Linux
export NDI_PATH=/path/to/NDI/SDK
```

## Troubleshooting

### CMake Can't Find NDI

**Error**: `Could not find module FindNDI.cmake`

**Solution**: Install NDI SDK from https://ndi.tv/tools/, or set `NDI_PATH`:
```bash
cmake .. -DNDI_PATH="C:/program files/NDI 6"
```

### pybind11 Not Found

**Error**: `Could not find Python packages (pybind11, ...)`

**Solution**: 
```bash
pip install pybind11
git submodule update --init  # If using git submodule
```

### MSVC Compiler Errors

**Error**: `error MSB8036: The Windows SDK version ... could not be found`

**Solution**: Update Visual Studio or specify SDK version:
```powershell
cmake .. -G "Visual Studio 17 2022" -DCMAKE_SYSTEM_VERSION=10.0.22000.0
```

### Python Version Mismatch

**Error**: `.pyd` file doesn't load in target Python version

**Solution**: Build with the target Python version:
```powershell
C:\path\to\python312\python.exe -m pip install pybind11
cmake .. -DCMAKE_COMMAND="C:/path/to/python312/python.exe"
```

## Rebuilding for Multiple Python Versions

To build `.pyd` files for Python 3.10 and 3.12 (as included in the repo):

```powershell
# Build for Python 3.10
C:\Python310\Scripts\pip install pybind11
cmake --build build_310 --config Release
Copy-Item "build_310/Release/NDIlib.cp310-win_amd64.pyd" "../NDIlib.cp310-win_amd64.pyd"

# Build for Python 3.12
C:\Python312\Scripts\pip install pybind11
cmake --build build_312 --config Release
Copy-Item "build_312/Release/NDIlib.cp312-win_amd64.pyd" "../NDIlib.cp312-win_amd64.pyd"

# Commit changes
git add NDIlib.cp*.pyd
git commit -m "Update NDI bindings"
```

## GitHub Actions Integration

To automatically rebuild `.pyd` files on NDI SDK updates, create a workflow in `.github/workflows/rebuild-ndi.yml`:

```yaml
name: Rebuild NDI Bindings

on:
  workflow_dispatch:  # Manual trigger
  schedule:
    - cron: '0 0 1 * *'  # Monthly

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ilammy/msvc-dev-cmd@v1
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      
      - name: Download NDI SDK
        run: |
          # Download and extract NDI SDK
          # (Details depend on NDI distribution)
      
      - name: Build NDI bindings
        run: |
          pip install cmake pybind11
          mkdir build && cd build
          cmake .. -G "Visual Studio 17 2022" -A x64
          cmake --build . --config Release
          Copy-Item "Release/NDIlib.cp*" "../videocue/ndi_wrapper/"
      
      - name: Commit changes
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI Bot"
          git add videocue/ndi_wrapper/NDIlib.cp*.pyd
          git commit -m "Rebuild NDI bindings for latest SDK" || true
          git push
```

## License

The C++ bindings are part of the ndi-python project (MIT License) by Naoto Kondo.
See `LICENSE.md` for full attribution and licensing details.

## Support

For issues related to:
- **NDI SDK**: Visit https://ndi.tv/ or contact support
- **CMake**: See https://cmake.org/documentation/
- **pybind11**: See https://pybind11.readthedocs.io/
- **This wrapper**: See VideoCue project issues on GitHub
