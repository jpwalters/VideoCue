# Build and Installer Creation

## Build Status: ✅ Complete

The PyInstaller build completed successfully!

### Build Output
- **Location**: `dist/VideoCue/`
- **Executable**: `dist/VideoCue/VideoCue.exe`
- **Size**: ~120-150 MB (includes PyQt6, pygame, NDI DLL)
- **Warnings**: Minor Qt6 plugin warnings (non-critical, 3D/WebView features not used)

### Testing the Build
```powershell
# Run the executable
.\dist\VideoCue\VideoCue.exe

# Test in clean environment (no Python required)
# Copy entire dist\VideoCue\ folder to another machine and run
```

## Creating an Installer

### Option 1: Inno Setup (Recommended)

1. **Download Inno Setup**
   - https://jrsoftware.org/isinfo.php
   - Install Inno Setup 6.x

2. **Compile Installer**
   ```powershell
   # After installing Inno Setup
   & "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
   ```

3. **Output**
   - Installer will be in `installer_output/`
   - Filename: `VideoCue-0.1.0-Setup.exe`
   - Includes uninstaller and Start Menu shortcuts

4. **Customize**
   Edit `installer.iss`:
   - Update GitHub URL (line 9)
   - Change version number (line 7)
   - Modify default install location
   - Add/remove components

### Option 2: WiX Toolset (Advanced)
For MSI installer instead of EXE:
- https://wixtoolset.org/
- More complex but better for enterprise deployment

### Option 3: ZIP Distribution
Simple option without installer:
```powershell
# Create ZIP file
Compress-Archive -Path "dist\VideoCue\*" -DestinationPath "VideoCue-0.1.0-portable.zip"
```

## Build Configuration

### What's Included
- ✅ VideoCue.exe (main application)
- ✅ PyQt6 runtime libraries
- ✅ pygame libraries
- ✅ qdarkstyle theme
- ✅ numpy libraries
- ✅ NDI DLL (if found at build time)
- ✅ config_schema.json

### What's NOT Included
- ❌ Python interpreter (not needed)
- ❌ Source code
- ❌ Development tools
- ❌ NDI Runtime installer (user must install separately)

## Distribution Checklist

### Before Releasing
- [ ] Test executable on clean Windows machine
- [ ] Verify NDI streaming works (if NDI Runtime installed)
- [ ] Test USB controller detection
- [ ] Verify VISCA camera control
- [ ] Check error handling (disconnect camera, invalid IP, etc.)
- [ ] Test configuration save/load
- [ ] Verify uninstaller works (if using Inno Setup)

### Release Package Should Include
1. `VideoCue-0.1.0-Setup.exe` (installer) OR
2. `VideoCue-0.1.0-portable.zip` (portable version)
3. README.md or QuickStart guide
4. Link to NDI Runtime download
5. Release notes

## File Sizes
- **dist/VideoCue/**: ~120-150 MB (uncompressed)
- **VideoCue-Setup.exe**: ~50-70 MB (compressed installer)
- **VideoCue-portable.zip**: ~45-60 MB (compressed archive)

## Next Steps

### If Inno Setup is NOT Installed:
```powershell
# Create portable ZIP distribution
Compress-Archive -Path "dist\VideoCue\*" -DestinationPath "VideoCue-0.1.0-portable.zip"

# Or download Inno Setup from:
Start-Process "https://jrsoftware.org/isinfo.php"
```

### If Inno Setup IS Installed:
```powershell
# Compile installer
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

# Output will be in: installer_output\VideoCue-0.1.0-Setup.exe
```

## Troubleshooting

### Build Issues
- **Missing NDI DLL**: Edit `VideoCue.spec` line 13 with correct path
- **Import errors**: Make sure all dependencies in requirements.txt
- **Build too large**: Normal for PyQt6 apps (100MB+ is expected)

### Runtime Issues
- **NDI not working**: User needs to install NDI Runtime separately
- **MSVCP140.dll missing**: Install Visual C++ Redistributable
- **App won't start**: Check Windows Event Viewer for error details

## Alternative Build Options

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

### GitHub Releases
1. Tag version: `git tag v0.1.0`
2. Create release on GitHub
3. Upload installer/ZIP as release assets
4. Add release notes from CODE_REVIEW.md

### Direct Download
- Host on personal website
- Share via Google Drive/Dropbox
- Upload to File.io for temporary sharing

### Future: Windows Store
- Requires UWP packaging
- MSIX format instead of MSI
- See: https://docs.microsoft.com/windows/msix/
