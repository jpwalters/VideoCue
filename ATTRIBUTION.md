# Attribution & Open Source Licenses

VideoCue is built on the shoulders of fantastic open source projects. This document provides comprehensive attribution for all incorporated code.

## Bundled Components

### NDI Python Wrapper

**Project**: [ndi-python](https://github.com/buresu/ndi-python)  
**Author**: Naoto Kondo  
**License**: MIT License  
**Status**: Bundled (incorporated into VideoCue)  
**Location**: [`videocue/ndi_wrapper/`](videocue/ndi_wrapper/)

The ndi-python project provides Python bindings to the NDI (Network Device Interface) SDK using pybind11. VideoCue incorporates the compiled C++ bindings and wrapper code directly to provide seamless NDI video streaming support.

**Why Bundled**: The original ndi-python project has not been updated in several years. Our bundled version includes critical bug fixes for:
- Thread safety during blocking operations (proper GIL release)
- Zero-copy frame data access using NumPy buffer protocol
- Improved frame reference counting to prevent memory leaks
- Better error handling and debugging information

**Original License Notice** (preserved in [`videocue/ndi_wrapper/LICENSE.md`](videocue/ndi_wrapper/LICENSE.md)):
```
MIT License

Copyright (c) 2019-2022 Naoto Kondo

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

**NDI Runtime**: The compiled NDI bindings in `ndi_wrapper/` require the **NDI Runtime** from NewTek/VIZRT:
- Download: https://ndi.tv/tools/
- License: NDI SDK License Agreement (provided by VIZRT)

---

## Dependencies

### Python Packages

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| PyQt6 | ≥6.5.0 | GPL v3 / Commercial | GUI framework |
| pygame | ≥2.5.0 | LGPL | USB game controller input |
| qdarkstyle | ≥3.1 | MIT | Dark theme stylesheet |
| numpy | ≥1.24.0 | BSD | Numerical computing (used by NDI) |
| ruff | ≥0.1.0 | MIT | Code linting and formatting |

### Runtime Dependencies

| Component | License | Purpose |
|-----------|---------|---------|
| NDI Runtime (6.x) | NDI SDK License | Video streaming over Ethernet |
| Processing.NDI.Lib.x64.dll | NDI SDK License | Windows NDI library (bundled in ndi_wrapper) |

---

## License Summary

**VideoCue Main Project**: [MIT License](LICENSE)

**Components Summary**:
- ✅ GPL v3 Compatible: PyQt6, pygame (LGPL)
- ✅ MIT Licensed: qdarkstyle, numpy, ruff, ndi-python
- ⚠️  Proprietary: NDI Runtime (optional dependency)

---

## How to Comply with These Licenses

1. **Include LICENSE file**: Distribute the included [LICENSE](LICENSE) file with VideoCue
2. **Include attribution**: This ATTRIBUTION.md file must be included with distributions
3. **NDI Runtime**: Users must separately download NDI Runtime from https://ndi.tv/tools/ and accept VIZRT's license
4. **Source code**: Source code for all open source components can be obtained from:
   - VideoCue: https://github.com/your-org/VideoCue
   - ndi-python: https://github.com/buresu/ndi-python
   - Other packages: Available via pip/PyPI

---

## Questions or Concerns?

If you have any questions about licensing or attribution:
- Open an issue on the VideoCue GitHub repository
- Consult the LICENSE files in each component directory
- For NDI licensing questions, contact VIZRT directly at https://ndi.tv/

---

###### Last Updated: February 2026
