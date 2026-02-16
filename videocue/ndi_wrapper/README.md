# NDI Wrapper Module

This directory contains the NDI (Network Device Interface) Python bindings for VideoCue.

## About

This module provides Python bindings to the NDI 6 SDK, enabling video streaming over Ethernet networks.

**Based on**: [ndi-python](https://github.com/buresu/ndi-python) by Naoto Kondo (MIT License)

## Contents

- `__init__.py` - Module initialization with automatic NDI Runtime DLL discovery
- `LICENSE.md` - Full attribution and licensing information
- `NDIlib.cp310-win_amd64.pyd` - Compiled bindings for Python 3.10 (Windows x64)
- `NDIlib.cp312-win_amd64.pyd` - Compiled bindings for Python 3.12 (Windows x64)
- `Processing.NDI.Lib.x64.dll` - NDI Runtime DLL (Windows x64, optional if system NDI installed)
- `README_BUILD.md` - Instructions for building the .pyd files from C++ source
- `src/main.cpp` - C++ pybind11 source code for NDI bindings

## Requirements

The NDI Runtime is required for NDI video streaming:
- **Download**: https://ndi.tv/tools/
- **Installation**: Choose "NDI Runtime" or "NDI 6 SDK" from https://ndi.tv/tools/
- **Supported Versions**: NDI 5, NDI 6
- **Automatic Detection**: The module automatically finds NDI Runtime in:
  - `C:\Program Files\NDI\NDI 6 Runtime\v6` (primary)
  - `C:\Program Files\NDI\NDI 5 Runtime\v5`
  - `C:\Program Files\NDI\NDI SDK`
  - Or bundled `Processing.NDI.Lib.x64.dll` in this directory
  - Or Windows Registry entry for custom installation

## How It Works

The module automatically handles NDI Runtime DLL loading:

1. **On Windows (Python 3.8+)**:
   - Searches for `Processing.NDI.Lib.x64.dll` in:
     - This directory (bundled .dll)
     - NDI Runtime installations
     - System PATH
   - Adds found paths to Python's DLL search
   - Imports compiled `.pyd` bindings

2. **If NDI Runtime Not Found**:
   - Module silently fails to load
   - `videocue/controllers/ndi_video.py` catches the error
   - Application continues in IP-only mode (VISCA still works)
   - User sees clear error message about NDI being unavailable

## Usage

Simply import the module:

```python
from videocue import ndi_wrapper as ndi

if hasattr(ndi, 'initialize') and ndi.initialize():
    ndi_find = ndi.find_create_v2()
    # ... rest of NDI operations
```

Or access via VideoCue's ndi_video.py which already handles the import.

## Modifications from Original

This bundled version includes improvements such as:
- Enhanced thread safety during blocking operations
- Better frame reference counting and memory management
- Improved error handling and debugging information

For full details on modifications, see the parent VideoCue project's documentation.

## License

See `LICENSE.md` for the original MIT license from Naoto Kondo and attribution information.
