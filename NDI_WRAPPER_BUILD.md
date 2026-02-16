# NDI Wrapper Build System - Quick Reference

## Overview

Three ways to build the NDI wrapper from C++ source:

### 1. **PowerShell Script** (Recommended for local development)

```powershell
cd C:\JPW\repo\VideoCue
.\build_ndi_wrapper.ps1
```

**Options:**

```powershell
# Build for specific Python version
.\build_ndi_wrapper.ps1 -PythonVersion 3.12

# Build for multiple versions (if both installed)
.\build_ndi_wrapper.ps1 -PythonVersion all

# Clean build (remove old artifacts first)
.\build_ndi_wrapper.ps1 -Clean

# Verbose output (show all compiler messages)
.\build_ndi_wrapper.ps1 -Verbose

# Custom NDI SDK path
.\build_ndi_wrapper.ps1 -NDIPath "C:\Program Files\NDI\NDI 6"
```

**What it does:**
- ✓ Checks all prerequisites (CMake, Visual Studio, NDI SDK, pybind11)
- ✓ Creates build directory
- ✓ Runs CMake configuration
- ✓ Compiles from videocue/ndi_wrapper/src/main.cpp
- ✓ Copies .pyd file to videocue/ndi_wrapper/
- ✓ Reports success/failure with details

---

### 2. **VS Code Tasks** (Quickest from IDE)

Use Ctrl+Shift+B or Command Palette → "Run Task"

Available tasks:

- **NDI: Build Wrapper (Current Python)** - Build for your current Python version
- **NDI: Build Wrapper (Python 3.12)** - Build for Python 3.12 specifically  
- **NDI: Build Wrapper (Python 3.10)** - Build for Python 3.10 specifically
- **NDI: Clean Build (Current Python)** - Remove build artifacts and rebuild

Output appears in a dedicated terminal panel.

---

### 3. **Manual CMake Build** (Full control)

```powershell
cd videocue\ndi_wrapper
mkdir build
cd build

# Configure (Windows)
cmake .. -G "Visual Studio 17 2022" -A x64 -DNDI_PATH="C:\NDI SDK 6"

# Build
cmake --build . --config Release

# Copy output
Copy-Item "Release/NDIlib.cp*.pyd" ".."
```

---

## Prerequisites

Before running the build script, ensure you have:

### **Required**
- [✓ Visual Studio 2019+](https://visualstudio.microsoft.com/) - C++ workload
- [✓ CMake 3.17+](https://cmake.org/download/) - `choco install cmake`
- [✓ NDI SDK 6+](https://ndi.tv/tools/) - Extract and install
- [✓ Python 3.10+](https://www.python.org/) - Development headers (usually included)
- [✓ pybind11](https://pybind11.readthedocs.io/) - `pip install pybind11`

### **Verify Prerequisites**

```powershell
# Check Python
python --version

# Check CMake
cmake --version

# Check pybind11
python -m pip show pybind11

# Check Visual Studio (Look for this folder)
ls "C:\Program Files\Microsoft Visual Studio\2022"

# Check NDI SDK
ls "C:\NDI SDK 6\Include"
```

If any are missing, the build script will tell you where to download them.

---

## Output

After a successful build, you'll have:

```
videocue/ndi_wrapper/
├── NDIlib.cp312-win_amd64.pyd    (newly compiled)
├── NDIlib.cp310-win_amd64.pyd    (existing)
└── src/
    └── main.cpp                   (C++ source)
```

The `.pyd` file is immediately usable - just restart your Python interpreter or reimport the module.

---

## Troubleshooting

### "CMake not found"
```powershell
choco install cmake
# OR download from https://cmake.org/download/
```

### "Visual Studio not found"
```
Download and install from:
https://visualstudio.microsoft.com/downloads/

Make sure to check "Desktop development with C++"
```

### "NDI SDK not found"
```
1. Download from https://ndi.tv/tools/
2. Install to default location: C:\NDI SDK 6
3. OR set environment variable: $env:NDI_PATH="C:\custom\path"
```

### "pybind11 not found"
```powershell
pip install pybind11
```

### Build fails but prerequisites exist
```powershell
# Try clean build
.\build_ndi_wrapper.ps1 -Clean

# Enable verbose output to see actual errors
.\build_ndi_wrapper.ps1 -Verbose

# Check build directory
ls videocue\ndi_wrapper\build
```

### .pyd file not found after build
Check the build output:
```powershell
ls -r videocue\ndi_wrapper\build | Select-Object -ExpandProperty Name
```

The file might be in a subdirectory like `Release/` or `Debug/`.

---

## Development Workflow

### **Make Changes to C++ Source**
```
1. Edit: videocue/ndi_wrapper/src/main.cpp
2. Run: .\build_ndi_wrapper.ps1 (or Ctrl+Shift+B in VS Code)
3. Test: Restart Python or import module
```

### **Add New NDI Operations**
```
1. Edit main.cpp to add pybind11 binding
2. Build: .\build_ndi_wrapper.ps1
3. Create high-level wrapper in: videocue/controllers/ndi_video.py
4. Test with VideoCue
```

### **Support New Python Version**
```
1. Install Python 3.z development headers
2. Run: .\build_ndi_wrapper.ps1 -PythonVersion 3.z
3. Commit: git add videocue/ndi_wrapper/NDIlib.cp3z-win_amd64.pyd
```

---

## How the Build Script Works

1. **Prerequisite Check**
   - Verifies CMake, Python, Visual Studio, NDI SDK, pybind11
   - Shows installation instructions if missing

2. **Directory Setup**
   - Creates `videocue/ndi_wrapper/build/` for build artifacts
   - Keeps source files clean (build/ in .gitignore)

3. **CMake Configuration**
   - Detects available Visual Studio (2022 > 2019)
   - Locates NDI SDK automatically or from parameter
   - Configures for x64 Release build

4. **Compilation**
   - Compiles main.cpp using pybind11
   - Links against NDI SDK headers and libraries
   - Generates .pyd file (Python extension module)

5. **Installation**
   - Copies .pyd to videocue/ndi_wrapper/
   - Ready to use immediately

6. **Verification**
   - Lists all .pyd files with file sizes
   - Confirms build success

---

## More Information

See detailed build instructions in:
- [videocue/ndi_wrapper/README_BUILD.md](videocue/ndi_wrapper/README_BUILD.md) - Comprehensive guide
- [videocue/ndi_wrapper/src/main.cpp](videocue/ndi_wrapper/src/main.cpp) - C++ source (1,495 lines)
- [videocue/ndi_wrapper/LICENSE.md](videocue/ndi_wrapper/LICENSE.md) - MIT license & attribution

---

## Quick Start

1. **First time setup:**
   ```powershell
   # Install NDI SDK from https://ndi.tv/tools/
   pip install pybind11
   choco install cmake
   ```

2. **Build:**
   ```powershell
   cd C:\JPW\repo\VideoCue
   .\build_ndi_wrapper.ps1
   ```

3. **Test:**
   ```powershell
   python
   >>> from videocue import ndi_wrapper
   >>> ndi_wrapper.initialize()
   # Success!
   ```

Done! 🎉
