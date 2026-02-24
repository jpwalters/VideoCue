# Build and Installer Creation Guide

## Quick Start: Automated Build (Recommended)

The easiest way to build VideoCue is using the PowerShell build script:

```powershell
# Install locked build dependencies (recommended for reproducible builds)
pip install -r requirements-build.lock.txt
```

```powershell
# Build everything with version update
.\build.ps1 -Version "0.4.2"
```

This single command:
- ✅ Updates version numbers in all files
- ✅ Runs PyInstaller to create executable
- ✅ Compiles Inno Setup installer
- ✅ Creates portable ZIP distribution
- ✅ Reports file sizes and locations

**Output:**
- `dist/VideoCue/VideoCue.exe` - Standalone executable
- `installer_output/VideoCue-0.4.1-Setup.exe` - Windows installer (~70 MB)
- `installer_output/VideoCue-0.4.1-portable.zip` - Portable version (~100 MB)

---

## Build Status: ✅ Complete

The PyInstaller build completed successfully!

### Build Output
- **Location**: `dist/VideoCue/`
- **Executable**: `dist/VideoCue/VideoCue.exe`
- **Size**: ~110-120 MB (includes PyQt6, pygame, NDI wrapper module, NumPy for video conversion)
- **Warnings**: Minor Qt6 plugin warnings (non-critical, 3D/WebView features not used)
- **Latest Version**: 0.6.16 (bandwidth menu, network interface binding, NDI polling improvements)

### Testing the Build
```powershell
# Run the executable directly
.\dist\VideoCue\VideoCue.exe

# Test in clean environment (no Python required)
# Copy entire dist\VideoCue\ folder to another machine and run
```

## Build Script Options

### Basic Usage
```powershell
# Build with version update (updates __init__.py and installer.iss)
.\build.ps1 -Version "0.4.1"

# Build without version update (uses current version)
.\build.ps1

# Skip PyInstaller (use existing dist/ folder)
.\build.ps1 -SkipBuild

# Skip installer creation (only build executable)
.\build.ps1 -SkipInstaller

# Build executable only, no installer
.\build.ps1 -SkipInstaller
```

### What the Script Does
1. **Version Update** (if -Version specified):
   - Updates `videocue/__init__.py`
   - Updates `installer.iss`

2. **PyInstaller Build**:
   - Cleans dist folder
   - Runs `pyinstaller VideoCue.spec --clean --noconfirm`
   - Reports build time and file size

3. **Inno Setup Compiler**:
   - Locates Inno Setup installation
   - Compiles installer from `installer.iss`
   - Creates Setup.exe in `installer_output/`

4. **Portable ZIP**:
   - Creates staging directory
   - Copies executable files
   - Adds PORTABLE_README.txt
   - Creates compressed ZIP archive

---

## Manual Build Process

### Prerequisites
1. Python 3.10+ with dependencies installed
2. NDI Runtime installed (optional but recommended)
3. Inno Setup 6 (for installer creation)

### Step-by-Step Manual Build

#### 1. PyInstaller Build
```powershell
# Basic build
pyinstaller VideoCue.spec

# Clean build (recommended)
pyinstaller VideoCue.spec --clean --noconfirm

# Debug build (with console window)
pyinstaller VideoCue.spec --console --clean
```

#### 2. Create Installer with Inno Setup

**Manual Compilation:**

1. **Download Inno Setup**
   - https://jrsoftware.org/isinfo.php
   - Install Inno Setup 6.x

2. **Compile Installer**
   ```powershell
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
   # Or on 64-bit systems:
   & "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
   ```

3. **Output**
   - Installer will be in `installer_output/`
   - Filename: `VideoCue-{version}-Setup.exe`
   - Includes uninstaller and Start Menu shortcuts

4. **Customize**
   Edit `installer.iss`:
   - Update version number (line 7: `#define MyAppVersion`)
   - Update GitHub URL (line 9)
   - Modify default install location
   - Add/remove components

#### 3. Create Portable ZIP

**Using Build Script (Recommended):**
```powershell
.\build.ps1
```

**Manual Creation:**
```powershell
# Simple ZIP
Compress-Archive -Path "dist\VideoCue\*" -DestinationPath "VideoCue-0.4.1-portable.zip"

# With README
$staging = "dist\VideoCue-Portable"
Copy-Item "dist\VideoCue\*" -Destination $staging -Recurse
Copy-Item "PORTABLE_README.txt" -Destination "$staging\README.txt"
Compress-Archive -Path "$staging\*" -DestinationPath "VideoCue-0.4.1-portable.zip"
```

## Build Configuration

### VideoCue.spec
PyInstaller build specification:
- **NDI DLL Search**: Automatically configured via `videocue/ndi_wrapper/__init__.py`
  - No manual configuration needed
  - Searches system NDI Runtime installations automatically
- **Icon**: `resources/icon.png` (if present)
- **Console**: Set to `False` for production (no console window)
- **UPX**: Disabled (breaks PyQt6 libraries)

### What's Included
- ✅ VideoCue.exe (main application)
- ✅ PyQt6 runtime libraries (~80 MB)
- ✅ pygame libraries (~15 MB)
- ✅ qdarkstyle theme
- ✅ numpy libraries (~20 MB)
- ✅ NDI wrapper module with .pyd bindings (~5 MB)
- ✅ Bundled `Processing.NDI.Lib.x64.dll` (fallback)
- ✅ config_schema.json
- ✅ Application resources (icons, etc.)

### What's NOT Included
- ❌ Python interpreter (not needed)
- ❌ Source code
- ❌ Development tools
- ❌ NDI Runtime installer (user must install separately)

## Distribution Checklist

### Before Releasing
- [ ] Update version number in `videocue/__init__.py`
- [ ] Update version in `installer.iss` (or use `build.ps1 -Version`)
- [ ] Test executable on clean Windows machine
- [ ] Verify NDI streaming works (if NDI Runtime installed)
- [ ] Test USB controller detection (Xbox/PlayStation controllers)
- [ ] Verify VISCA camera control
- [ ] Test X button emergency stop
- [ ] Test camera switch safety (auto-stop previous camera)
- [ ] Check error handling (disconnect camera, invalid IP, etc.)
- [ ] Test configuration save/load
- [ ] Verify play/pause video controls
- [ ] Test reconnect button functionality
- [ ] Verify uninstaller works (if using Inno Setup)

### Release Package Should Include
1. `VideoCue-{version}-Setup.exe` (Windows installer ~70 MB)
2. `VideoCue-{version}-portable.zip` (Portable version ~100 MB)
3. README.md or release notes
4. Link to NDI Runtime download (https://ndi.tv/tools/)
5. Changelog with new features and bug fixes

## File Sizes (v0.4.1)
- **dist/VideoCue/**: ~120-150 MB (uncompressed)
- **VideoCue-Setup.exe**: ~65-75 MB (compressed installer)
- **VideoCue-portable.zip**: ~95-105 MB (compressed archive)

## Quick Reference

### Automated Build (Recommended)
```powershell
# Full build with version update
.\build.ps1 -Version "0.4.1"

# Build with current version
.\build.ps1

# Build executable only
.\build.ps1 -SkipInstaller
```

### Manual Build
```powershell
# PyInstaller only
pyinstaller VideoCue.spec --clean

# Inno Setup only (requires existing dist/)
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

# Portable ZIP only
Compress-Archive -Path "dist\VideoCue\*" -DestinationPath "VideoCue-portable.zip"
```

---

## Next Steps

### If Using the Automated Script:
```powershell
# Just run the build script!
.\build.ps1 -Version "0.4.1"

# Output files will be in:
# - dist/VideoCue/VideoCue.exe
# - installer_output/VideoCue-0.4.1-Setup.exe
# - installer_output/VideoCue-0.4.1-portable.zip
```

### If Inno Setup is NOT Installed:
```powershell
# Create portable ZIP only (or install Inno Setup first)
.\build.ps1 -SkipInstaller

# Or download Inno Setup from:
Start-Process "https://jrsoftware.org/isinfo.php"
```

### If Inno Setup IS Installed:
```powershell
# Use the automated script (detects installation automatically)
.\build.ps1

# Or manually compile:
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
# Output: installer_output\VideoCue-{version}-Setup.exe
```

## Troubleshooting

### Build Script Issues
- **"Cannot find pyinstaller"**: Activate virtual environment first: `.venv\Scripts\activate`
- **"Inno Setup not found"**: Use `-SkipInstaller` flag or install from https://jrsoftware.org/isinfo.php
- **Version update fails**: Check file permissions on `videocue/__init__.py` and `installer.iss`

### Build Issues
- **Missing NDI DLL**: The build automatically searches for NDI Runtime in standard locations
  - If not found, bundled DLL in `videocue/ndi_wrapper/` is used
  - No manual configuration needed
- **Import errors**: Make sure all dependencies in requirements.txt are installed
- **Build too large**: Normal for PyQt6 apps (100MB+ is expected)

### Runtime Issues
- **NDI not working**: User needs to install NDI Runtime separately
- **MSVCP140.dll missing**: Install Visual C++ Redistributable
- **App won't start**: Check Windows Event Viewer for error details

### Alternative Build Methods

#### WiX Toolset (MSI Installer)
For MSI installer instead of EXE:
- https://wixtoolset.org/
- More complex but better for enterprise deployment
- Better integration with Windows Installer service

#### MSIX Packaging (Windows Store)
- Requires UWP packaging
- MSIX format for Microsoft Store distribution
- See: https://docs.microsoft.com/windows/msix/

### Reduce Size (Optional)
Edit `VideoCue.spec`:
```python
# Add to excludes list
excludes=[
    'tkinter',
    'unittest',
    'email',
    'html',
    'http',
    'urllib',
    'xml.etree',
],
```

### Debug Build
```powershell
# Build with console window for debugging
pyinstaller VideoCue.spec --console --clean
```

## Distribution Platforms

### GitHub Releases (Recommended)
1. Update version: `videocue/__init__.py`
2. Build: `.\build.ps1 -Version "0.4.1"`
3. Commit changes: `git commit -am "Release v0.4.1"`
4. Tag version: `git tag v0.4.1`
5. Push: `git push && git push --tags`
6. Create release on GitHub
7. Upload both installer and portable ZIP as release assets
8. Add release notes from changelog

### Direct Download
- Host on personal website
- Share via Google Drive/Dropbox
- Upload to File.io for temporary sharing

### Future: Windows Store
- Requires UWP packaging
- MSIX format instead of MSI
- See: https://docs.microsoft.com/windows/msix/
