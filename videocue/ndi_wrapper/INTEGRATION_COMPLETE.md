# NDI Wrapper C++ Source Integration

**Date Completed**: Current session
**Status**: ✅ Complete - Full C++ source code incorporated for maintainability

## Overview

The VideoCue project now includes the complete C++ source code for the NDI Python bindings (pybind11 wrapper), enabling long-term maintenance, improvements, and customization independent of the upstream ndi-python project.

## Files Added

### 1. **videocue/ndi_wrapper/src/main.cpp** (1,495 lines)
- **Purpose**: Complete pybind11 C++ bindings wrapping the NDI SDK C library
- **Size**: ~50 KB source code
- **Contents**:
  - Python module initialization (PYBIND11_MODULE)
  - Frame type enums (Video, Audio, Metadata)
  - FourCC codec definitions
  - NDI frame structures (video_frame_v2, audio_frame_v2, audio_frame_v3)
  - Find operations (source discovery via mDNS)
  - Receive operations (video/audio capture)
  - Send operations (streaming output)
  - PTZ camera control (pan, tilt, zoom, focus, white balance, exposure)
  - Recording operations (record to file)
  - Routing operations (NDI routing)
  - Frame synchronization
  - Audio format conversion utilities
  - Threading safety (GIL management)
  - Zero-copy NumPy array integration
  - Comprehensive error handling
- **Origin**: Copied from ndi-python project by Naoto Kondo
- **License**: MIT (preserved in LICENSE.md)

### 2. **videocue/ndi_wrapper/CMakeLists.txt**
- **Purpose**: CMake build configuration for compiling C++ source to .pyd files
- **Key Features**:
  - Finds NDI SDK installation
  - Links pybind11 for Python bindings
  - Supports Windows, macOS, Linux
  - Multi-architecture support (x86_64, ARM64)
  - Proper RPATH handling for runtime library loading
  - Installs NDI Runtime DLL alongside bindings
- **C++ Standard**: C++17
- **Minimum CMake**: 3.17

### 3. **videocue/ndi_wrapper/README_BUILD.md** (comprehensive build guide)
- **Purpose**: Step-by-step instructions for rebuilding .pyd files from source
- **Contents**:
  - Windows/macOS/Linux prerequisites
  - Visual Studio, CMake, NDI SDK setup
  - pybind11 dependency installation
  - Build directory setup
  - CMake configuration commands (per platform)
  - Build commands
  - Output file locations
  - Installation instructions
  - FindNDI.cmake module explanation
  - Troubleshooting section (11 common issues)
  - Multi-Python-version build workflow
  - GitHub Actions automation example
  - Full source attribution and licensing

## Architecture Decision Rationale

### Why Include C++ Source Code?

**Problem Solved**:
- ndi-python upstream is dormant (4+ years without updates)
- User has custom bugfixes not upstreamed
- No way to adapt to future NDI SDK or Python version changes
- Bound to external package dependency maintenance

**Solution Benefits**:
1. **Independence**: VideoCue owns the wrapper implementation
2. **Maintainability**: Direct control over bug fixes and improvements
3. **Customization**: Can add VideoCue-specific NDI features
4. **Forward Compatibility**: Handle future NDI SDK API updates
5. **Python Version Support**: Easy to rebuild for new Python versions
6. **Faster Iteration**: No wait for upstream to merge changes
7. **Documentation**: Clear record of what the wrapper does

### Integration Strategy

**Dual Approach**:
- **Pre-compiled bindings** (`.pyd` files): For fast development (no build needed)
- **C++ source code**: For future maintenance and improvements
- **Best of both worlds**: Developers get instant setup, maintainers have full control

## Workflow for Future Maintenance

### Scenario 1: Bug Fix During Development
```
1. Identify issue in ndi_video.py or NDI operations
2. Trace to root cause in videocue/ndi_wrapper/src/main.cpp
3. Edit C++ source directly
4. Rebuild: cmake build && cmake --build . --config Release
5. Test with rebuilt .pyd
6. Commit both source changes and rebuilt .pyd files
```

### Scenario 2: Support New Python Version (e.g., Python 3.14)
```
1. Install Python 3.14 development headers
2. Run CMAKE for Python 3.14 environment
3. Build → generates NDIlib.cp314-win_amd64.pyd
4. Move file to videocue/ndi_wrapper/
5. Update PyInstaller spec if needed
6. Commit new .pyd file
```

### Scenario 3: Use New NDI SDK Features
```
1. Read NDI SDK changelog/documentation
2. Add new pybind11 bindings to main.cpp
3. Create high-level Python wrapper methods in ndi_video.py
4. Rebuild .pyd
5. Test and commit
```

## Technical Stack

```
NDI SDK (C Library)
        ↓
pybind11 (Python/C++ Bridge)
        ↓
NDIlib.cpp (Bindings - 1,495 lines)
        ↓
CMake (Build System)
        ↓
.pyd Files (Compiled Bindings)
        ↓
videocue/ndi_video.py (High-Level Interface)
        ↓
VideoCue Application (Python/PyQt6)
```

## File Locations Reference

```
videocue/ndi_wrapper/
├── __init__.py                    # Module initialization (DLL loading)
├── LICENSE.md                     # Full MIT license + attribution
├── README.md                      # Module documentation
├── README_BUILD.md               # Build instructions (THIS FILE)
├── CMakeLists.txt                # CMake build configuration
├── .gitignore                    # Excludes .dll, build artifacts
├── src/
│   └── main.cpp                  # C++ pybind11 bindings (1,495 lines)
├── NDIlib.cp310-win_amd64.pyd    # Pre-compiled for Python 3.10
├── NDIlib.cp312-win_amd64.pyd    # Pre-compiled for Python 3.12
└── (Processing.NDI.Lib.x64.dll   # Downloaded at build time, not in git)
```

## Dependency Management

### What's Included (Checked Into Repo)
✅ C++ source code (src/main.cpp)
✅ Build configuration (CMakeLists.txt)
✅ Pre-compiled bindings (.pyd files - ~850 KB total)
✅ Documentation (README_BUILD.md)
✅ License and attribution (LICENSE.md)

### What's Downloaded at Build Time
📥 NDI Runtime DLL (~30 MB, from https://ndi.tv/tools/)
📥 CMake and build tools (from system or via CI/CD)

### What's Not Needed Anymore
❌ ndi-python package from PyPI (removed from requirements.txt)
❌ External dependency management for wrapper
❌ Waiting for upstream updates

## Building for Production

### Local Build (One-Time Setup)
```powershell
# Install prerequisites once
choco install cmake visualstudio2022community
pip install pybind11

# Clone NDI SDK and set NDI_PATH environment variable
# (Instructions in https://ndi.tv/tools/)

# Then build
cd videocue/ndi_wrapper
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release

# Output: ..\Release\NDIlib.cp312-win_amd64.pyd
```

### CI/CD Build (GitHub Actions)
- Workflows already simplified to verify bundled .pyd files exist
- Optional: Create new workflow for auto-rebuilding on NDI SDK updates
- See README_BUILD.md for GitHub Actions example

## Version Control Strategy

### Commit Pre-Compiled Bindings
```bash
git add videocue/ndi_wrapper/NDIlib.cp*.pyd
git commit -m "Update NDI bindings for Python 3.12 support"
```

**Advantages**:
- Small file size (~850 KB total for cp310 + cp312)
- Developers don't need C++ compiler
- CI/CD doesn't need to rebuild
- Reproducible binaries (same source = same .pyd)

**Alternative**: Skip .pyd files and require CMake build
- Larger build times (+5-10 minutes per CI/CD run)
- Requires NDI SDK in CI/CD environment
- Not needed unless making C++ changes frequently

## Support and Maintenance

### For Breaking NDI SDK Changes
1. Read NDI SDK release notes
2. Update pybind11 bindings in main.cpp
3. Rebuild .pyd files
4. Test with VideoCue
5. Update CHANGELOG.md with breaking changes

### For Python Version Updates
- Just rebuild with new Python: `cmake --build . --config Release`
- Copy output .pyd to videocue/ndi_wrapper/
- Test with new Python version
- Commit updated .pyd

### For Performance Improvements
- Profile VideoCue's NDI operations
- Optimize C++ code in main.cpp
- Rebuild and measure impact
- Commit improvements

## Future Enhancements

Potential improvements now possible:

1. **Custom NDI Features**
   - Add project-specific camera control operations
   - Optimize frame copying for VideoCue's use case
   - Custom metadata handling

2. **Error Handling**
   - More descriptive error messages
   - Better timeout handling
   - Recovery mechanisms

3. **Performance**
   - Direct frame access optimization
   - Batch operations
   - Threading improvements

4. **Testing**
   - Unit tests for C++ bindings
   - Integration tests with mock NDI
   - Performance benchmarks

## Attribution

**Original ndi-python Project**:
- Author: Naoto Kondo (https://github.com/buresu/ndi-python)
- License: MIT
- Last updated: 2022 (dormant for 3+ years as of 2024)

**VideoCue Modifications**:
- Bug fixes from user's custom fork
- Integration into VideoCue project structure
- Enhanced C++ documentation
- Build system improvements

**Full attribution in**:
- videocue/ndi_wrapper/LICENSE.md
- ATTRIBUTION.md (project root)
- Individual file headers

---

**Next Steps** (Optional):
- Test local Build from C++ source
- Create GitHub Actions workflow for auto-rebuilding
- Document any VideoCue-specific NDI customizations
- Archive original ndi-python changes in release notes
