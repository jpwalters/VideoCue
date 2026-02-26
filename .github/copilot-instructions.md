# VideoCue - Python VISCA-over-IP Camera Controller

## Project Overview
Python/PyQt6 application for controlling professional PTZ cameras using VISCA-over-IP protocol (UDP port 52381) with optional NDI video streaming and USB game controller support. Port of JavaFX version.

## Architecture

### Key Components
- **videocue.py**: Application entry point, initializes PyQt6 app with qdarkstyle theme, **global exception handler** prevents crashes, **SingleInstanceLock** for optional single-instance mode, **global popup window policy** (remove minimize/maximize on dialogs)
- **ui/main_window.py**: Main window (QTabWidget), **deferred camera loading** via showEvent, progress bar with 3-step milestone tracking per camera (create/configure/initialized), **USB signal management** with UniqueConnection pattern
- **ui/camera_widget.py**: Per-camera widget (QTreeWidget sections: video, PTZ controls, exposure, white balance, focus, presets), **connection state tracking** (is_connected), **reconnect button**, **play/pause video controls**, **automatic settings query** on connection, **startup initialization watchdog** (timeout -> failed + reconnect)
- **ui/preferences_dialog.py**: Preferences dialog with USB controller settings, application settings (single instance mode, NDI video toggle), **150ms reconnection delay** prevents button bleed-through
- **ui/camera_add_dialog.py**: NDI discovery + manual IP entry dialog + **manual NDI source name entry** (firewall workaround)
- **controllers/visca_ip.py**: VISCA protocol (UDP datagrams, hex commands), **send_command (fire-and-forget)** vs **query_command (waits for response)**
- **controllers/ndi_video.py**: NDI video receiver (separate QThread per camera, **configurable color format** UYVY/BGRA/RGBA, frame dropping), **5-second timeout**, **configurable bandwidth** (HIGHEST/LOWEST), **Scopes rendering modes** (False Color, Waveform, Vectorscope, RGB Parade, Histogram), **network interface binding**, **comprehensive error handling**, **persistent NumPy buffers for UYVY conversion**
- **controllers/usb_controller.py**: pygame joystick polling (16ms events, 5s hotplug), emits PyQt signals, **B button for one-push autofocus**, **Menu button opens preferences dialog**
- **models/config_manager.py**: JSON config at `%LOCALAPPDATA%\VideoCue\config.json` (Windows) / `~/.config/VideoCue/config.json` (Unix), **ndi_bandwidth preference**, **ndi_color_format preference** (default: uyvy), **scope mode preferences** (`ndi_false_color_enabled`, `ndi_waveform_enabled`, `ndi_vectorscope_enabled`, `ndi_rgb_parade_enabled`, `ndi_histogram_enabled`)
- **models/video.py**: Video size and camera preset data models
- **ui_strings.py**: **Centralized UI text constants** - all user-facing strings (buttons, tooltips, status messages, errors) for consistency and future i18n
- **utils/__init__.py**: `resource_path()` for PyInstaller compatibility, `get_app_data_dir()` for config location
- **utils/network_interface.py**: Network interface detection and subnet matching for NDI binding (v0.6.14)

### Camera Discovery Architecture
**VISCA has no built-in discovery** - requires knowing IP address beforehand. The app uses NDI for discovery:
1. NDI sources broadcast via mDNS (port 5353) with metadata including web control URL
2. NDI receiver calls `recv_get_web_control()` to get URL like `http://192.168.1.100/`
3. IP address extracted via regex: `r'(\d+\.\d+\.\d+\.\d+)'` from web control URL
4. Extracted IP used to initialize `ViscaIP(ip, port)` for camera control
5. Manual IP entry available as fallback when NDI discovery unavailable

### VISCA Protocol
- UDP datagrams to port 52381 (default)
- Packet format: `[PayloadType:1][PayloadLength:3][SequenceNumber:4][Command:N]` bytes
  - Built in `_build_packet()`: `struct.pack('>BHxI', type, length, seq)` + command bytes
- Commands are hex strings: `"81 01 06 01 FF"` → parsed via `bytes.fromhex()`
- ViscaIP class at [controllers/visca_ip.py](videocue/controllers/visca_ip.py):
  - `send_command(hex_string)`: Fire-and-forget, returns True on successful send (no response wait)
  - `query_command(hex_string)`: Waits for response with 1s timeout, returns parsed data or None
  - **Connection Testing**: Uses `query_focus_mode()` which requires response (returns FocusMode.UNKNOWN on failure)
- Example commands: PTZ (8 directions + stop), zoom (variable speed 0-7), focus (auto/manual/one-push)
- **Key Distinction**: Control commands use `send_command()` (fast), connection tests use `query_command()` (reliable)
- **Presets**: Camera firmware stores PTZ positions in memory slots (0-127 for Birddog, 0-254 for VISCA). App sends store/recall commands without needing to query positions.

### NDI Video Streaming
- Uses **bundled ndi_wrapper module** (in `videocue/ndi_wrapper/`), based on ndi-python by Naoto Kondo (MIT License)
- **Optional dependency**: Graceful fallback if NDI Runtime not available (app continues in IP-only mode)
- **Automatic NDI Runtime Detection**: `__init__.py` searches system for:
  - `C:\Program Files\NDI\NDI 6 Runtime\v6` (primary)
  - `C:\Program Files\NDI\NDI 5 Runtime\v5`
  - Bundled DLL in ndi_wrapper directory
  - Windows Registry entries for custom installations
- **Network Requirements**: NDI uses mDNS (port 5353) for discovery - requires proper firewall configuration
  - **Firewall Workaround**: Manual NDI source name entry field available in camera add dialog
  - Users can enter exact NDI source name (e.g., "BIRDDOG-12345 (Channel 1)") to bypass discovery
  - Useful in corporate/restricted network environments where mDNS is blocked
- **Network Interface Binding** (v0.6.14-15): Auto-detects correct network interface based on camera IPs, binds NDI via `extra_ips` property
- **NDI Discovery Polling** (v0.6.15): Polls every 200ms until all expected cameras found (dynamic count from config), eliminates random timeouts
- Each camera spawns separate QThread with NDI receiver loop
- **Connection Timeout**: If no frames received within 5 seconds, thread exits with error message (prevents app slowdown from invalid source names)
- **Bandwidth Control** (v0.6.16): User-configurable via View → Video Performance menu
  - High Bandwidth: `RECV_BANDWIDTH_HIGHEST` - maximum quality, higher network usage
  - Low Bandwidth: `RECV_BANDWIDTH_LOWEST` - compression, lower network usage (default)
- **Color Format Selection** (v0.6.17+): Configurable via View → Video Format menu
  - UYVY: Native camera format, requires NumPy conversion (CPU-bound)
  - BGRA: NDI SDK converts natively, optimal for Windows (ARGB32 format)
  - RGBA: NDI SDK converts natively, cross-platform compatible
- **Scope Modes**: Configurable via View → Scopes menu (mutually exclusive)
  - False Color (Atomos-style)
  - Waveform (Luma)
  - Vectorscope (Chroma)
  - RGB Parade
  - Histogram (Luma + RGB overlaid curves)
- **Video Conversion Architecture**:
  - UYVY path: Uses persistent NumPy buffers with ITU-R BT.601 coefficients
  - BGRA/RGBA path: NDI SDK handles conversion natively (uses SIMD/GPU when available)
  - Scaling: Done in PyQt6 via `QPixmap.scaled()` with `FastTransformation`
- **Timer-Driven Rendering**: 33ms cadence timer limits UI work and prevents frame queue buildup
- **Frame Memory Management (CRITICAL)**:
  - `recv_capture_v3()` returns `(type, video, audio, metadata)` tuple
  - ALL frame types MUST be freed to prevent memory leaks:
    - `recv_free_video_v2(receiver, video)` for FRAME_TYPE_VIDEO
    - `recv_free_audio_v3(receiver, audio)` for FRAME_TYPE_AUDIO  
    - `recv_free_metadata(receiver, metadata)` for FRAME_TYPE_METADATA
  - Failure to free audio/metadata frames causes ~30 MB/min memory growth
- Frame dropping via PyQt signal queuing (Qt auto-drops old queued frames)
- **Graceful degradation**: App continues in IP-only mode if NDI unavailable (no crash)
- Requires NDI Runtime installed from https://ndi.tv/tools/ on end-user system

### USB Controller
- pygame joystick API with 16ms polling (60 Hz)
- Hotplug detection every 5 seconds
- **Button Mappings**:
  - Button 0 (A): Brightness decrease (configurable, can be disabled)
  - Button 1 (B): One-push autofocus (quick AF trigger on selected camera)
  - **Button 2 (X): Stop camera movement** (sends VISCA stop command)
  - Button 3 (Y): Brightness increase (configurable, can be disabled)
  - Button 4 (L1/LB): Previous camera
  - Button 5 (R1/RB): Next camera
  - Button 7 (Menu/Start): Open controller preferences dialog
- **Axis Mappings**: Axis 0/1 (left stick → PTZ), Axis 4/5 (triggers → zoom)
- **Stop on Camera Switch**: Configurable option (enabled by default) automatically sends stop command to previous camera when switching
- **Connection Awareness**: All USB handlers check `camera.is_connected` before sending commands
- Emits PyQt signals, Qt automatically marshals to main thread
- **Error Handling**: Try-except blocks in all event handlers with console logging

### Camera Features (via VISCA)
- **Exposure**: 5 modes (Auto, Manual, Shutter Priority, Iris Priority, Bright) with Enum-based state management
- **White Balance**: 5 modes (Auto, Indoor, Outdoor, One Push, Manual) with red/blue gain adjustment (0-255)
- **Focus**: Auto/Manual/One-Push AF modes controlled via FocusMode enum
- **PTZ**: 8 directional movements + stop, variable zoom speed (0-7)
- **Presets**: Store/recall camera positions (up to 128 slots for Birddog, 254 for VISCA standard)
  - Each preset has UUID for Cue tab references and permanent preset_number (camera memory slot)
  - Camera stores actual PTZ coordinates in firmware
  - App stores preset metadata (UUID, name, preset_number) in JSON config
  - Reordering presets only changes display order - preset_number remains permanent
  - Position queries not implemented - camera firmware manages positions

### Camera Preset Architecture
- **UUID-based identification**: Each preset has unique UUID for Cue tab ordered preset sequences across cameras
- **Permanent preset numbers**: Each preset assigned to camera memory slot (0-127 for Birddog, 0-254 for VISCA)
  - Preset number never changes, even when reordering display list
  - Deleting preset frees up that memory slot for reuse
  - `get_next_available_preset_number()` finds first gap in 0-127 range
- **Simple VISCA commands** (like mini project):
  - Store: `81 01 04 3F 01 {preset_hex} FF` - saves current position to camera memory
  - Recall: `81 01 04 3F 02 {preset_hex} FF` - moves to stored position
  - Camera firmware handles all position storage - app doesn't track PTZ values
- **CameraPreset model** (videocue/models/video.py):
  - `uuid`: Unique identifier for Cue tab cross-references
  - `name`: User-friendly display name
  - `preset_number`: Camera memory slot (0-127)
  - Legacy format support: Auto-generates UUID for old configs without uuid/preset_number
- **ConfigManager methods** (videocue/models/config_manager.py):
  - `add_preset(camera_id, name, preset_number, preset_uuid)` - Create with UUID and slot
  - `remove_preset(camera_id, preset_uuid)` - Delete by UUID
  - `update_preset_name(camera_id, preset_uuid, new_name)` - Rename by UUID
  - `get_next_available_preset_number(camera_id, max_presets=128)` - Find free slot
  - `reorder_preset(camera_id, preset_uuid, direction)` - Change display order only
- **UI Features** (camera_widget.py):
  - Display shows: [slot#] Name (e.g., "[3] Wide Shot")
  - GO button: Recalls preset from permanent camera memory slot
  - Update button: Re-saves current position to same slot
  - Delete button: Removes from app, frees camera memory slot
  - Reorder (↑↓): Changes list order without affecting camera memory
  - No complex re-storing workflow - reordering is instant

### Deferred Loading Architecture
- **Problem**: Camera connections (especially NDI) block UI from appearing
- **Solution**: UI loads first, then cameras connect in background
- **Implementation**:
  1. `MainWindow.showEvent()` triggers deferred loading via `QTimer.singleShot(100ms)`
  2. Progress bar appears at top of window
  3. Each camera reports milestones: create/configure/initialized (progress increments only on completed milestones)
  4. `connection_starting` updates loading text but does not increment progress value
  5. `on_camera_initialized()` de-duplicates by camera ID and hides progress when complete
  6. `CameraWidget` initialization watchdog times out stalled cameras (~15s), marks them failed, and emits `initialized`
  7. Failed cameras don't block other cameras from loading
- **User Experience**: Application window appears instantly, cameras connect with progress feedback

### Connection State Management
- **is_connected boolean**: Tracks camera connection state (True = green status, False = red status)
- **Status Indicators**: Green circle (connected) / Red circle (disconnected)
- **Control State**: All camera controls automatically enable/disable based on `is_connected`
  - `set_controls_enabled(enabled)`: Recursively finds all child widgets and sets enabled state
- **Connection Testing**: 
  - IP-only cameras: `_test_visca_connection()` uses `query_focus_mode()` (requires response)
  - NDI cameras: Connection verified when first frame received
- **Reconnect Functionality**:
  - Reconnect button appears when status is red
  - Reconnect button and menu dialog available for manual reconnection
  - `reconnect_camera()` method: stops video thread, waits 500ms, attempts reconnection
  - Startup watchdog converts stalled initialization into explicit failed state (red + reconnect visible)
- **USB Controller Protection**: All USB handlers check `camera.is_connected` before sending commands

### Error Handling Architecture
- **Global Exception Handler**: `sys.excepthook` in `videocue.py` catches all unhandled exceptions
  - Shows QMessageBox with error details instead of crashing
  - Logs full traceback to console
  - Application continues running after error dialog
- **Try-Except Coverage**:
  - Main window initialization (videocue.py)
  - Camera widget loading (add_camera_from_config)
  - NDI video operations (start_video, reconnect)
  - VISCA connection testing (_test_visca_connection)
  - USB controller event handling (all signal handlers)
  - NDI thread reception loop (nested try-except)
- **Error User Experience**:
  - Failed camera loads show warning dialog, other cameras continue
  - Video errors display in video label area
  - Console logs include full tracebacks for debugging
  - No silent failures - all errors logged

### Video Streaming Controls
- **Play/Pause Button**: Toggle video streaming per camera (▶/⏸ Unicode symbols)
  - Font size: 14px for better visibility
  - Tooltip updates based on state
  - Initial state: ▶ (play), changes to ⏸ (pause) after connection
- **State Management**: 
  - `start_video()`: Creates and starts NDI thread
  - `stop_video()`: Stops thread, clears video label
  - `toggle_video()`: Switches between play/pause states

## Development Workflow

### Setup and Run
```bash
# Install dependencies
pip install -r requirements.txt

# Run application
python videocue.py

# Build executable
pyinstaller VideoCue.spec
```

### Project Dependencies
- PyQt6 (6.5.0+): UI framework
- ndi-python (5.0.0+): NDI video streaming (optional, graceful fallback)
- pygame (2.5.0+): USB controller support
- qdarkstyle (3.1+): Dark theme
- ruff (recommended): Fast Python linter with fewer false positives than Pylint

### Configuration
- Stored at `%LOCALAPPDATA%\VideoCue\config.json` (Windows) or `~/.config/VideoCue/config.json` (Unix)
- Schema: cameras array (id, ndi_source, ip, port, presets), preferences (video_size_default, video_frame_skip, ndi_bandwidth, ndi_color_format, scope toggles, theme, **single_instance_mode**, **ndi_video_enabled**), usb_controller (mappings, speeds, **brightness_enabled**, **brightness_step**)
- See [config_schema.json](config_schema.json) for full JSON structure
- ConfigManager uses `uuid.uuid4()` for camera IDs
- Auto-saves on camera add/delete, preset changes, video size changes, app exit
- **Always call `config.save()` explicitly after modifications** - no auto-save on property changes

## Code Conventions

### UI Text Management
**CRITICAL**: All user-facing text must use `UIStrings` constants from [ui_strings.py](videocue/ui_strings.py).

```python
from videocue.ui_strings import UIStrings

# Button text
button = QPushButton(UIStrings.BTN_SAVE)
button.setToolTip(UIStrings.TOOLTIP_RECONNECT)

# Status text
label.setText(UIStrings.STATUS_CONNECTED)

# Dialog titles
self.setWindowTitle(UIStrings.DIALOG_ADD_CAMERA)
```

**Never use hardcoded strings** for:
- Button labels (BTN_*)
- Status messages (STATUS_*)
- Tooltips (TOOLTIP_*)
- Dialog titles (DIALOG_*)
- Menu items (MENU_*)
- Error messages (ERROR_*)
- Mode names (EXPOSURE_*, WB_*, FOCUS_*)

**Benefits**:
- Centralized text management for consistency
- Future internationalization (i18n) support
- Easy to find and update all UI text
- Self-documenting UI constants

**When adding new UI text**:
1. Add constant to `ui_strings.py` with descriptive name
2. Use the constant in your UI code
3. Never commit hardcoded UI strings

### PyQt Signal/Slot Pattern
```python
# Define signals in class
class MyThread(QThread):
    frame_ready = pyqtSignal(QImage)  # Qt auto-marshals to main thread
    
# Connect in UI
thread.frame_ready.connect(self.update_frame)

# Emit from worker thread (thread-safe)
self.frame_ready.emit(qimage)
```

### Enums for Protocol States
```python
# Use Python Enum for VISCA states (not string literals)
from enum import Enum

class FocusMode(Enum):
    AUTO = 1
    MANUAL = 2
    UNKNOWN = 3

# Usage: self.visca.set_focus_mode(FocusMode.AUTO)
```

### Resource Loading (PyInstaller Compatible)
```python
from videocue.utils import resource_path

# Load image/file
path = resource_path('resources/icon.png')
```

### Widget Hierarchy
- QMainWindow (main_window.py) contains QTabWidget
- Cameras tab contains QScrollArea with QHBoxLayout of CameraWidgets
- CameraWidget uses QTreeWidget for collapsible sections (Camera Controls, Settings, Presets)
- No FXML equivalent - UI created programmatically
- Pre-initialize widget attributes to None in `__init__` before UI creation (avoids AttributeError)

### Configuration Updates
```python
# Always save after changes
self.config.add_camera(...)
self.config.save()  # Explicit save
```

### Error Handling Best Practices
```python
# All critical operations wrapped in try-except
try:
    # Operation that might fail
    camera.start_video()
except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()
    # Show user-friendly error
    self.video_label.setText(f"Error: {str(e)[:50]}")
```

### Connection State Pattern
```python
# Check connection before operations
if camera and camera.is_connected:
    camera.handle_usb_movement(direction, speed)

# Update controls when connection changes
self.is_connected = success
self.set_controls_enabled(success)
if success:
    self.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
    self.reconnect_button.setVisible(False)
else:
    self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
    self.reconnect_button.setVisible(True)
```

### USB Signal Management Pattern (Preferences Dialog)
```python
# Disconnect handlers when preferences dialog opens
if self.usb_controller and self._usb_signal_handlers:
    self.usb_controller.brightness_increase.disconnect(
        self._usb_signal_handlers["brightness_increase"]
    )
    # ... disconnect other handlers

# Reconnect with 150ms delay when dialog closes (prevents button bleed-through)
def _on_preferences_dialog_closed(self):
    QTimer.singleShot(150, self._reconnect_usb_handlers)
    self._preferences_dialog_open = False

def _reconnect_usb_handlers(self):
    # Use UniqueConnection to prevent duplicate connections
    def safe_connect(signal, handler, name=""):
        try:
            signal.connect(handler, Qt.ConnectionType.UniqueConnection)
        except TypeError as e:
            if "unique" in str(e).lower():
                logger.debug(f"Connection for {name} already exists")
    
    safe_connect(self.usb_controller.brightness_increase, 
                 self._usb_signal_handlers["brightness_increase"], 
                 "brightness_increase")
```

### Single Instance Mode
```python
# In videocue.py - SingleInstanceLock class
class SingleInstanceLock:
    """Platform-specific file locking for single instance enforcement"""
    def __init__(self):
        self.lock_file = get_app_data_dir() / "videocue.lock"
        self.lock_fd = None
    
    def acquire(self) -> bool:
        # Windows: msvcrt.locking()
        # Unix: fcntl.flock()
        # Returns True if lock acquired, False if another instance running
    
    def release(self):
        # Release lock on app exit

# Usage in main()
if config.get_single_instance_mode():
    lock = SingleInstanceLock()
    if not lock.acquire():
        # Show warning dialog, exit
```

### Camera Settings Query Pattern
```python
# Query all settings asynchronously after connection
def _query_all_settings_async(self):
    """Background thread queries all camera settings"""
    class QueryThread(QThread):
        finished = pyqtSignal(dict)
        def run(self):
            results = {}
            results["focus_mode"] = self.visca.query_focus_mode()
            results["exposure_mode"] = self.visca.query_exposure_mode()
            results["brightness"] = self.visca.query_brightness()
            # ... query all settings
            self.finished.emit(results)
    
    self._query_thread = QueryThread(self.visca, self.visca_ip)
    self._query_thread.finished.connect(self._apply_queried_settings)
    self._query_thread.start()

def _apply_queried_settings(self, results: dict):
    """Apply queried settings to UI sliders/combos"""
    if "brightness" in results and results["brightness"] is not None:
        self.brightness_slider.blockSignals(True)
        self.brightness_slider.setValue(results["brightness"])
        self.brightness_slider.blockSignals(False)
```

## Common Tasks

### Adding VISCA Commands
1. Add method to [ViscaIP class](videocue/controllers/visca_ip.py)
2. Build command hex string: `"81 01 ... FF"`
3. Choose command type:
   - **Control operation**: `self.send_command(cmd)` (fire-and-forget, returns bool)
   - **Query operation**: `self.query_command(cmd)` (waits for response, returns data or None)
4. Add UI control in [CameraWidget](videocue/ui/camera_widget.py)
5. **Add UI text to [ui_strings.py](videocue/ui_strings.py)** if creating new buttons/labels/tooltips
6. Wire button/control to VISCA method using UIStrings constants
7. Wrap in try-except for error handling

### Adding Error Handling to New Code
1. Wrap critical operations in try-except blocks
2. Import traceback for detailed error logging: `import traceback`
3. Print error to console: `print(f"Error: {e}")` and `traceback.print_exc()`
4. Show user-friendly message (QMessageBox or label text)
5. Allow operation to continue when possible (graceful degradation)

### Adding New UI Elements
1. **First**: Add text constants to [ui_strings.py](videocue/ui_strings.py) with descriptive names
2. Import UIStrings: `from videocue.ui_strings import UIStrings`
3. Use constants for all user-facing text: `QPushButton(UIStrings.BTN_NAME)`
4. Set tooltips with constants: `button.setToolTip(UIStrings.TOOLTIP_NAME)`
5. **Never commit hardcoded UI strings** - they make i18n difficult and create inconsistency

### Adding USB Controller Mappings
1. Update button/axis handler in [USBController](videocue/controllers/usb_controller.py)
2. Emit appropriate signal (movement_direction, zoom_in, etc.)
3. Connect signal in [MainWindow.init_usb_controller()](videocue/ui/main_window.py)
4. Route to selected camera via `get_selected_camera()`

### Modifying UI Layout
- CameraWidget PTZ buttons: 3x3 QGridLayout in `create_controls_tree()`
- Main window tabs: QTabWidget in `init_ui()`
- Camera list: QHBoxLayout in QScrollArea (cameras_layout)
- Collapsible sections: QTreeWidget with custom item widgets

## Threading Model

### Threads
1. **Main thread**: PyQt event loop, all UI updates
2. **NDI threads**: One QThread per camera for video reception
3. **USB polling**: QTimer on main thread (16ms for events, 5s for hotplug)

### Thread Safety
- PyQt signals automatically queue cross-thread calls
- NDI thread emits signals, main thread receives via slots
- No manual `Platform.runLater()` equivalent needed (Qt handles it)
- VISCA UDP calls are synchronous with 1s timeout (safe to call from any thread)

### Frame Dropping
- NDI thread emits `frame_ready` signal with QImage
- Qt signal queue implicitly drops old frames if UI busy
- No explicit queue size management needed

## Known Limitations

1. **NDI Web Control URL**: `ndi-python` library API for extracting web control URLs needs verification. Currently returns None, may need metadata XML parsing.

2. **Build Size**: PyInstaller executable ~100-120 MB (includes PyQt6, NDI SDK, pygame DLLs).

3. **Platform Support**: Primary target is Windows (bundles NDI DLL). Mac/Linux require separate NDI Runtime installation.

## Troubleshooting

### NDI Not Loading
- Check NDI Runtime installed: https://ndi.tv/tools/
- Verify DLL path in VideoCue.spec
- Application continues without NDI (IP-only cameras)
- Error message shown on startup if NDI unavailable

### NDI Discovery Not Finding Cameras
- **Root cause**: Firewall blocking mDNS traffic on port 5353 (UDP)
- **Solution 1**: Configure firewall to allow NDI Discovery Service and mDNS traffic
- **Solution 2**: Use manual NDI source name entry in camera add dialog (firewall workaround)
  - Get exact source name from NDI Studio Monitor (NDI Tools) on a machine with proper access
  - Typical format: "BIRDDOG-12345 (Channel 1)" or "CAMERA_NAME (Channel 1)"
  - Manual connection works even when discovery is blocked by firewall
- Check Windows Firewall rules: `Get-NetFirewallRule | Where-Object {$_.DisplayName -like "*NDI*"}`

### VISCA Not Discovering Cameras
- **VISCA has no discovery protocol** - you must know the camera's IP address
- Use NDI discovery which provides web control URL containing the IP
- Or manually enter the camera's IP address
- IP extracted from NDI web control URL via regex pattern: `r'(\d+\.\d+\.\d+\.\d+)'`

### Camera Shows Red Status / Won't Connect
- Verify IP address is correct
- Check network connectivity (ping test)
- Verify VISCA port (usually 52381)
- Check firewall allows UDP on port 52381
- Use reconnect button or B button on controller
- Check console output for error details

### Video Performance Issues
- **Color Format**: View → Video Format menu
  - BGRA/RGBA use NDI SDK's native conversion (recommended for lower CPU usage)
  - UYVY uses NumPy conversion (higher CPU, useful for debugging)
- **Bandwidth Control**: View → Video Performance menu
  - Switch to Low Bandwidth to reduce network usage (enables compression)
  - Switch to High Bandwidth for maximum quality
- **Scopes**: View → Scopes menu
  - False Color/Waveform/Vectorscope/RGB Parade/Histogram are mutually exclusive
  - Histogram and waveform-style scopes increase CPU usage due to per-frame analysis
- **Video Size**: View → Video Size menu to reduce resolution
- **Pause Streams**: Use play/pause button to stop video when not needed
- Frame dropping and timer-driven rendering prevent UI lag

### Application Crashes/Errors
- Global exception handler shows error dialog instead of crash
- Check console output for detailed tracebacks
- Most errors allow application to continue
- NDI timeouts after 5 seconds prevent freeze

### USB Controller
- Ensure pygame installed and controller recognized by OS
- Hotplug detection may take up to 5 seconds
- Check console for pygame errors
- Controller commands blocked when camera disconnected

### Linter False Positives (Development)
- Use Ruff instead of Pylint: `pip install ruff`
- Ruff has better pygame support (no "has no member" false positives)
- Install Ruff VS Code extension: `charliermarsh.ruff`
- Disable Pylint to avoid noise

## Testing

See [QUICKSTART.md](QUICKSTART.md) for comprehensive testing checklist.

Key test areas:
- VISCA communication with real cameras
- NDI discovery and streaming
- USB controller input (analog + digital)
- Configuration persistence across sessions
- Graceful NDI fallback
- PyInstaller build executable
