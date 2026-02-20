# VideoCue v0.6.16 - Portable Distribution

## Quick Start

1. **Extract Files**
   - Extract the entire folder to any location
   - No installation required!

2. **Run VideoCue**
   - Double-click `VideoCue.exe`
   - No Python installation needed

3. **Optional: NDI Video Streaming**
   - Download NDI Runtime from: https://ndi.tv/tools/
   - Install NDI Runtime if you want video streaming
   - Application works without NDI (IP control only)

## First Launch

1. Application window appears immediately
2. Camera connections happen in background (progress bar shown)
3. Use **File → Add Camera** to add your PTZ cameras
4. Cameras auto-discover via NDI or enter IP manually

## Requirements

- Windows 10/11 (64-bit)
- No Python required (standalone executable)
- Optional: NDI Runtime for video streaming
- Optional: USB game controller (Xbox, PlayStation, etc.)

## Features

- **VISCA-over-IP Control**: Industry-standard PTZ camera protocol
- **Multi-Camera Support**: Control multiple cameras simultaneously
- **NDI Streaming**: Live video preview with bandwidth control (requires NDI Runtime)
- **USB Controller**: Gamepad support for hands-free operation
  - X button: Emergency stop (halts camera movement)
  - B button: One-push autofocus
  - L1/R1: Switch cameras with auto-stop safety
  - Menu button: Open controller preferences
- **Camera Presets**: Store and recall pan/tilt/zoom positions
- **Exposure Control**: 5 modes (Auto, Manual, Shutter/Iris Priority, Bright)
- **White Balance**: 5 modes including manual color temperature
- **Focus Control**: Auto/Manual/One-Push AF modes
- **Dark Theme**: Professional appearance
- **Automatic Settings Sync**: Camera settings queried and synced on connection

## Video Performance

Access via **View → Video Performance** menu:
- **High Bandwidth**: Maximum quality, higher network usage
- **Low Bandwidth**: Compressed video, lower network usage (default)

Access via **View → Video Size** menu for resolution presets.

## Tested With

- BirdDog P400/P200/P202/P403/P404 cameras
- Xbox Series X/One controllers
- PlayStation DualShock 4/DualSense controllers
- Windows 11

## Configuration

Settings stored at: `%LOCALAPPDATA%\VideoCue\config.json`

Includes:
- Camera configurations with presets
- USB controller mappings and speeds
- Video size and bandwidth preferences
- Single instance mode (default: enabled)

## Network & Firewall Notes

**NDI Discovery:**
- NDI uses mDNS (UDP port 5353) for auto-discovery
- If camera discovery doesn't work:
  1. Allow UDP port 5353 in Windows Firewall, OR
  2. Use manual NDI source name entry (enter exact name like "BIRDDOG-12345 (Channel 1)")
- Manual entry works even when firewall blocks discovery

**Multi-Homed Systems:**
- Application auto-detects correct network interface
- Binds NDI to camera subnet automatically (v0.6.14+)

**VISCA Control:**
- UDP port 52381 (default)
- Ensure firewall allows UDP traffic on this port

## Troubleshooting

**Cameras show red status:**
- Verify IP address is correct
- Check VISCA port (usually 52381)
- Use Reconnect button or web interface link

**Video not showing:**
- Ensure NDI Runtime is installed
- Check bandwidth setting (View → Video Performance)
- Use play/pause button to toggle streaming

**USB controller not detected:**
- Wait up to 5 seconds for hotplug detection
- Verify controller recognized by Windows
- Check controller status in toolbar

## Support

- Documentation: See README.md in source repository
- Issues: Report on GitHub
- Logs: `%LOCALAPPDATA%\VideoCue\logs\videocue.log`

## What's New in v0.6.16

**Video & Network:**
- Bandwidth control menu (High/Low quality modes)
- Automatic network interface detection and binding (v0.6.14)
- Improved NDI discovery with polling (v0.6.15)
- Manual NDI source name entry for firewall-restricted networks

**Camera Control:**
- Automatic settings sync on connection (exposure, focus, WB queried)
- One-push autofocus via B button on controller
- Emergency stop via X button on controller
- Safe camera switching (auto-stops previous camera)

**User Experience:**
- Single instance mode prevents multiple app instances
- Comprehensive error handling prevents crashes
- Deferred camera loading (UI appears instantly)
- Red/green connection status indicators
- Play/pause video streaming controls

**Technical:**
- NumPy-based UYVY→RGB conversion (~100x faster)
- Thread-safe VISCA sequence numbers
- USB button mapping cache for responsive input
- Comprehensive logging to file

## License

MIT License - See LICENSE file

---

**Enjoy controlling your PTZ cameras!** 🎥
