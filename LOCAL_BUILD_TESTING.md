# Local Build Testing Guide

This document explains how to test the GitHub Actions build process locally to speed up debugging.

## Quick Local Build (Recommended)

The easiest way to test builds locally is to use the `build.ps1` script, which replicates most of the CI/CD process:

```powershell
# Full build with version update
.\build.ps1 -Version "0.6.20"

# Build without creating installer (faster for testing)
.\build.ps1 -SkipInstaller

# Build with debug console output (for troubleshooting)
.\build.ps1 -Debug

# Use existing dist/ folder (skip PyInstaller)
.\build.ps1 -SkipBuild
```

## Manual Step-by-Step Testing

To replicate the exact GitHub Actions workflow locally:

### 1. Verify Environment

```powershell
# Check Python version (should match CI: 3.10)
python --version

# Activate virtual environment (if using one)
.\.venv\Scripts\Activate.ps1
```

### 2. Install Locked Dependencies

```powershell
# Install exact versions from build lock file
pip install -r requirements-build.lock.txt
```

### 3. Download Stream Deck Dependencies

```powershell
# Download hidapi.dll (automated in build.ps1)
$hidapiUrl = "https://github.com/libusb/hidapi/releases/download/hidapi-0.14.0/hidapi-win.zip"
$tempZip = "$env:TEMP\hidapi-win.zip"
$tempExtract = "$env:TEMP\hidapi-extract"

Invoke-WebRequest -Uri $hidapiUrl -OutFile $tempZip
Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force
Copy-Item "$tempExtract\x64\hidapi.dll" -Destination "hidapi.dll" -Force

Remove-Item $tempZip, $tempExtract -Recurse -Force
```

### 4. Verify Stream Deck Dependencies

```powershell
# Check hidapi.dll
if (Test-Path "hidapi.dll") {
    $dllSize = (Get-Item "hidapi.dll").Length / 1KB
    Write-Host "✓ hidapi.dll found ($([math]::Round($dllSize, 2)) KB)"
}

# Check Python packages
python -c "import streamdeck"
python -c "import hid"
python -c "from PIL import Image"
```

### 5. Verify NDI Bindings (if built)

```powershell
# Check for bundled NDI files
if (Test-Path "videocue\ndi_wrapper\NDIlib.cp310-win_amd64.pyd") {
    Write-Host "✓ NDI bindings found"
} else {
    Write-Host "⚠ NDI bindings not found (will be disabled in build)"
}
```

### 6. Run Linter

```powershell
# Run ruff linter (matches CI)
ruff check .

# Auto-fix issues
ruff check . --fix
```

### 7. Build Executable

```powershell
# Clean build with PyInstaller
pyinstaller VideoCue.spec --clean --noconfirm
```

### 8. Verify Packaged Runtime DLLs

```powershell
# Check VC runtime DLLs
.\tools\verify_runtime_dlls.ps1 -DistRoot ".\dist\VideoCue"
```

### 9. Test Executable

```powershell
# Run the built executable
.\dist\VideoCue\VideoCue.exe
```

## Simulating GitHub Actions Locally (Advanced)

You can use [act](https://github.com/nektos/act) to run GitHub Actions workflows locally:

```powershell
# Install act (requires Docker Desktop)
choco install act-cli
# or
scoop install act

# Run CI workflow
act push -j build

# Run specific job from release workflow
act -W .github/workflows/build-release.yml
```

**Note:** `act` requires Docker Desktop and may have limitations on Windows. The `build.ps1` script is usually faster and more reliable for local testing.

## Differences Between Local and CI

| Aspect | Local Build | GitHub Actions CI |
|--------|-------------|-------------------|
| **Python Version** | Your installed version | Exact version (3.10.11) |
| **Environment** | Your system path/config | Clean runner |
| **Dependencies** | May have extras installed | Only requirements-build.lock.txt |
| **Cache** | PyInstaller cache persists | Fresh build each time |
| **Speed** | Faster (cached) | Slower (clean environment) |

## Troubleshooting Local Builds

### Issue: "Module not found" errors

**Solution:** Ensure you're using the locked dependencies:
```powershell
pip install -r requirements-build.lock.txt --force-reinstall
```

### Issue: NDI bindings not working

**Solution:** Run the NDI wrapper build script:
```powershell
.\build_ndi_wrapper.ps1
```

### Issue: hidapi.dll not found

**Solution:** Let `build.ps1` download it automatically, or manually download from GitHub:
```powershell
# build.ps1 handles this automatically via Get-HidapiDll function
.\build.ps1
```

### Issue: "ModuleNotFoundError: No module named 'streamdeck'" (CRITICAL)

**Root Cause:** The Python module name is `StreamDeck` (capital S, D) but the PyPI package is named `streamdeck` (lowercase).

**Explanation:**
- PyPI package: `streamdeck==0.9.8` (lowercase - pip install name)
- Python import: `from StreamDeck.DeviceManager import DeviceManager` (capital S, D)
- On Windows, the filesystem is case-insensitive but Python's import system is case-sensitive
- Testing `import streamdeck` (lowercase) will always fail
- Testing `from StreamDeck.DeviceManager import DeviceManager` (capital) works correctly

**Solution:** Always use capital case for StreamDeck imports:
```python
# CORRECT ✓
from StreamDeck.DeviceManager import DeviceManager

# WRONG ✗
import streamdeck  # This will fail!
```

**Why this was hard to debug:**
1. `pip show streamdeck` shows package installed ✓
2. Files exist in `site-packages/StreamDeck/` ✓  
3. But `import streamdeck` fails because Python looks for lowercase `streamdeck` module
4. This is not a bug - it's intentional package design where PyPI name ≠ Python module name

### Issue: Build works locally but fails in CI

**Possible causes:**
1. Extra packages installed locally not in requirements-build.lock.txt
2. Different Python version (CI uses 3.10.11)
3. Windows-specific dependencies not available in CI
4. Unicode encoding issues (CI uses cp1252, local may use UTF-8)

**Solution:** Use a clean virtual environment that matches CI:
```powershell
# Create fresh venv with Python 3.10
python -m venv .venv-test
.\.venv-test\Scripts\Activate.ps1
pip install -r requirements-build.lock.txt

# Test build
.\build.ps1
```

## Best Practices

1. **Always test with locked dependencies** before pushing to trigger CI
2. **Use `build.ps1` for quick iteration** - it's faster than waiting for CI
3. **Run ruff linter locally** before committing to catch issues early
4. **Test the built executable** - don't just verify it builds
5. **Keep requirements-build.lock.txt updated** when dependencies change

## Quick Verification Checklist

Before pushing changes that affect the build:

- [ ] `pip install -r requirements-build.lock.txt` succeeds
- [ ] `ruff check .` passes with no errors
- [ ] `.\build.ps1 -SkipInstaller` completes successfully
- [ ] `.\dist\VideoCue\VideoCue.exe` launches without errors
- [ ] Stream Deck features work (if hardware available)
- [ ] NDI features work (if cameras available)
- [ ] All UI elements render correctly
