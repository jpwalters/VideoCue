# Quick Start Guide - VideoCue Python

## Development Setup

### 1. Install Python Dependencies
```bash
cd c:\JPW\repo\VideoCue
pip install -r requirements.txt
```

### 2. Install Optional Linting Tools
```bash
pip install ruff  # Recommended for development
```

### 2. Install NDI Runtime (Optional)
Download and install NDI Runtime from https://ndi.tv/tools/
- Windows: NDI DLL will be automatically found at:
  - `C:\Program Files\NDI\NDI 6 Runtime\v6\Processing.NDI.Lib.x64.dll` (recommended)
  - `C:\Program Files\NDI\NDI 6 SDK\Lib\x64\Processing.NDI.Lib.x64.dll`
  - Or bundled in `videocue/ndi_wrapper/` directory
- **Optional**: App will work without NDI but video streaming features will be disabled

### 3. Run the Application
```bash
python videocue.py
```

## Project Structure

```
python/
├── videocue.py              # Main entry point with global exception handler
├── videocue/
│   ├── __init__.py
│   ├── constants.py         # Application constants (NetworkConstants, UIConstants, etc.)
│   ├── ui_strings.py        # Centralized UI text constants (all user-facing strings)
│   ├── utils.py             # Resource loading utilities
│   ├── controllers/
│   │   ├── visca_ip.py      # VISCA-over-IP protocol with BirdDog support
│   │   ├── visca_commands.py # VISCA command definitions
│   │   ├── ndi_video.py     # NDI video streaming with comprehensive error handling
│   │   └── usb_controller.py # USB game controller with stop button support
│   ├── models/
│   │   ├── video.py         # Video size and preset models
│   │   └── config_manager.py # JSON configuration persistence
│   └── ui/
│       ├── main_window.py    # Main application window with deferred loading
│       ├── camera_widget.py  # Camera control widget with query-based sync
│       ├── camera_add_dialog.py # Camera discovery dialog
│       └── preferences_dialog.py # USB controller settings
├── requirements.txt
├── build.ps1               # Automated PowerShell build script
├── config_schema.json
├── VideoCue.spec           # PyInstaller build configuration
├── ruff.toml               # Ruff linter configuration
├── .pylintrc               # Pylint configuration
├── .pyrightignore          # Pyright type checker ignore patterns
└── README.md
```

## Building Executable (Windows)

### Automated Build (Recommended)
Use the PowerShell build script:
```powershell
.\build.ps1 -Version "0.4.1"
```

This creates:
- Executable in `dist/VideoCue/` (~100-120 MB)
- Inno Setup installer in `installer_output/VideoCue-{version}-Setup.exe`
- Portable ZIP in `installer_output/VideoCue-{version}-portable.zip`
- NDI DLL detection is automatic - no manual configuration needed

### Build Options
```powershell
# Update version and build everything
.\build.ps1 -Version "0.4.1"

# Skip PyInstaller (use existing dist/)
.\build.ps1 -SkipBuild

# Skip Inno Setup installer
.\build.ps1 -SkipInstaller
```

### Manual Build
To build without automated script:

```bash
# Build executable
pyinstaller VideoCue.spec --clean

# NDI DLL detection is automatic - no manual configuration needed
```
   ```bash
   dist\VideoCue\VideoCue.exe
   ```

## Configuration

Configuration is stored in:
- **Windows**: `%LOCALAPPDATA%\VideoCue\config.json`
- **macOS/Linux**: `~/.config/VideoCue/config.json`

The configuration includes:
- Camera list (NDI sources, VISCA IPs, presets)
- Video size preferences
- USB controller settings

## Features Implemented

✅ VISCA-over-IP protocol (UDP)
- PTZ movement (8 directions + stop)
- Variable speed zoom
- Focus mode control (Auto/Manual/One-Push)
- Exposure modes (Auto, Manual, Shutter/Iris Priority, Bright)
- White balance modes (Auto, Indoor, Outdoor, One-Push, Manual)
- Query commands for connection verification and state sync
- BirdDog P200/P400 non-standard value support (exposure=15, WB modes)

✅ NDI video streaming
- Network camera discovery with polling-based reliability (v0.6.15)
- Manual NDI source name entry (firewall workaround)
- Automatic network interface detection and binding (v0.6.14-15)
- Live video display with frame dropping for performance
- Configurable bandwidth modes: High (max quality) or Low (compressed) - v0.6.16
- Configurable color format: UYVY, BGRA, or RGBA - v0.6.17
- Timer-driven rendering prevents frame queue buildup
- 5-second connection timeout prevents app freeze
- Play/pause video controls per camera

✅ USB game controller support
- Hotplug detection (5-second polling)
- Analog stick for continuous PTZ control
- Triggers for variable zoom
- D-pad for discrete movements
- Camera selection (L1/R1 buttons)
- **X button for emergency stop** (immediately halts camera movement)
- **B button for one-push autofocus** (trigger quick AF on selected camera)
- **Menu/Start button to open controller preferences dialog**
- Brightness control (Y/A buttons in Bright mode)
- **Safe camera switching** (auto-stop previous camera, configurable)
- **Optimized button handling** - Button mappings cached at init for responsive input

✅ Multi-camera management
- Add cameras via NDI discovery or manual IP
- Per-camera presets (store/recall/delete)
- Per-camera video size
- Selection highlighting
- Connection state tracking (red/green status indicators)
- Automatic control disabling when disconnected
- One-click reconnect for failed cameras

✅ User Experience
- Deferred camera loading (UI appears immediately)
- Granular progress bar (3 steps per camera)
- Progress advances on completed milestones (create/configure/initialized), not on "connecting" status text
- Startup timeout recovery marks stalled cameras disconnected and shows Reconnect
- Deletion confirmation dialogs
- Play/pause video streaming controls
- Settings cog icon for camera web interface
- Horizontal scrollbar for camera overflow

✅ Configuration persistence
- Auto-save on changes
- Camera-specific presets
- Video size preferences
- USB controller settings (including stop-on-switch safety option)

✅ Comprehensive error handling
- Global exception handler prevents crashes
- Try-except blocks in all critical paths
- Error dialogs with detailed information
- Comprehensive logging to `%LOCALAPPDATA%\VideoCue\logs\videocue.log`
- Console logging with full tracebacks
- Graceful degradation on failures

✅ Code quality & development tools
- Centralized UI strings in `ui_strings.py` (consistency and future i18n)
- Ruff linter configuration for fast, accurate linting
- Type checking with Pyright
- Automated build script with version management
- Thread-safe sequence number generation in VISCA protocol
- Performance optimizations (button mapping cache, frame dropping)

✅ Dark theme UI (qdarkstyle)

## Known Limitations

1. **Preset Position Query**: VISCA commands for querying current PTZ position are not yet implemented. Presets currently store placeholder values (0, 0, 0). This requires additional VISCA protocol research.

2. **BirdDog White Balance Firmware**: BirdDog P200/P400 cameras return identical values for OUTDOOR and MANUAL white balance modes (P200=5, P400=10). This is a camera firmware limitation. The app defaults to showing MANUAL for these values since precise control is typically preferred.

3. **Frame Dropping**: PyQt6 signals with QueuedConnection don't have explicit queue size limits. Frame dropping relies on Qt's internal handling. If UI lag occurs, may need manual implementation.

4. **Connection State**: Connection verification uses query commands (not fire-and-forget) for reliability, but doesn't implement full state machine with automatic retry logic.

## Testing Checklist

### Core Functionality
- [ ] Test VISCA communication with real camera
- [ ] Test NDI discovery on network
- [ ] Test NDI manual source name entry
- [ ] Test NDI video streaming
- [ ] Test IP-only camera (no NDI)
- [ ] Test camera connection status indicators (red/green)
- [ ] Test reconnect button functionality
- [ ] Test play/pause video controls

### USB Controller
- [ ] Test USB controller (Xbox/PlayStation)
- [ ] Test camera selection via controller (L1/R1)
- [ ] **Test X button emergency stop** (stops camera movement immediately)
- [ ] **Test auto-stop on camera switch** (previous camera stops when switching)
- [ ] Test PTZ movement via buttons (D-pad)
- [ ] Test PTZ movement via analog stick
- [ ] Test zoom via triggers
- [ ] Test B button one-push autofocus on selected camera
- [ ] Test brightness control (Y/A buttons in Bright mode)
- [ ] Test controller hotplug (disconnect/reconnect)
- [ ] Test camera switch safety preference (enable/disable in settings)

### Camera Controls
- [ ] Test focus mode switching (Auto/Manual/One-Push)
- [ ] Test exposure modes (Auto, Manual, Shutter/Iris Priority, Bright)
- [ ] Test white balance modes (Auto, Indoor, Outdoor, One-Push, Manual)
- [ ] Test preset store/recall/delete
- [ ] Test camera add/delete with confirmation dialog
- [ ] Test settings cog button (opens web interface)

### UI/UX
- [ ] Test deferred loading (UI appears before camera connections)
- [ ] Test loading progress bar (3 steps per camera)
- [ ] Confirm progress does not hit 100% before all cameras reach initialized/failed state
- [ ] Confirm stalled camera transitions to red status with Reconnect after startup timeout
- [ ] Test horizontal scrollbar with multiple cameras
- [ ] Test video size changes (View → Video Size)
- [ ] Test camera controls disabled when disconnected
- [ ] Test USB controller blocked when camera disconnected
- [ ] Test Help menu's Check for Updates (GitHub releases API)
- [ ] Test About dialog (Help → About)

### Configuration & Error Handling
- [ ] Test configuration persistence across restarts
- [ ] Test graceful NDI timeout (5 seconds for invalid sources)
- [ ] Test error dialogs instead of crashes
- [ ] Test camera load failure doesn't block other cameras
- [ ] Test PyInstaller build executable

## Troubleshooting

### NDI Not Found
- Ensure NDI Runtime is installed from https://ndi.tv/tools/
- Check NDI DLL path in VideoCue.spec
- Application will continue without NDI features (IP-only mode)

### No Cameras Discovered via NDI
- **Most Common**: Firewall blocking mDNS on UDP port 5353
- **Workaround**: Use manual NDI source name entry in Add Camera dialog
  - Get exact name from NDI Studio Monitor: "BIRDDOG-12345 (Channel 1)"
- Ensure cameras are on same network/subnet
- In Add Camera dialog, click Search to retry discovery
- Check Windows Firewall: Allow "NDI Discovery Service"

### Camera Shows Red Status / Won't Connect
- Verify camera IP address is correct
- Check camera is on network and reachable (ping test)
- Verify camera VISCA port (default 52381)
- Check firewall allows UDP on port 52381
- Click the Reconnect button when it appears
- Press B button on controller to reconnect selected camera

### NDI Source Times Out / App Freezes During Add
- Fixed: Now has 5-second timeout on invalid NDI sources
- If camera name is wrong, app will show error after 5 seconds
- Double-check NDI source name spelling (case-sensitive)

### Camera Controls Disabled (Grayed Out)
- Normal: Controls disable automatically when camera disconnected
- Check status indicator - red means disconnected
- Use Reconnect button
- Verify network connectivity to camera

### USB Controller Not Detected
- Ensure pygame is installed: `pip install pygame`
- Check if controller is recognized by Windows (joy.cpl)
- Try unplugging and replugging controller (5-second detection)
- Check console for pygame error messages
- Verify controller is DirectInput/XInput compatible

### Video Lag
- Switch color format (View → Video Color Format) - BGRA/RGBA use NDI SDK native conversion
- Reduce video size (View → Video Size menu)
- Switch to Low Bandwidth (View → Video Performance)
- Use play/pause button to stop video when not needed
- Close unused cameras
- Frame dropping should prevent UI lag, but high CPU usage may indicate issue

### Application Crashes or Disappears
- Fixed: Global exception handler now shows error dialog instead of crash
- Check console output for detailed error traces
- Most errors now allow application to continue running
- Report unexpected errors with console logs

### Linter False Positives (Development)
- Use Ruff instead of Pylint: `pip install ruff`
- Install Ruff VS Code extension: `charliermarsh.ruff`
- Disable Pylint extension to avoid pygame "has no member" false positives

## Next Steps

1. **Test with Real Hardware**: Continue testing with actual PTZ cameras and NDI sources
2. **Implement PTZ Position Query**: Add VISCA commands to query absolute positions for presets
3. **Verify NDI Metadata**: Test web control URL extraction from NDI metadata
4. **Add Keyboard Shortcuts**: Implement hotkeys for common actions (camera switching, PTZ)
5. **Internationalization (i18n)**: Leverage `ui_strings.py` to add multi-language support
6. **Camera Nicknames**: Add user-friendly camera naming separate from NDI source names
7. **Preset Thumbnails**: Consider adding thumbnail images to preset buttons
8. **Multi-Camera Sync**: Explore synchronized PTZ movements across multiple cameras
9. **Auto-Pan Enhancement**: Add configurable dwell time and transition speed
10. **Installer Distribution**: Test and refine Inno Setup installer for production releases
