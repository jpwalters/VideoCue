# VideoCue v0.1.0 - Portable Distribution

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

## Requirements

- Windows 10/11 (64-bit)
- No Python required (standalone executable)
- Optional: NDI Runtime for video streaming
- Optional: USB game controller (Xbox, PlayStation, etc.)

## Features

- **VISCA-over-IP Control**: Industry-standard PTZ camera protocol
- **Multi-Camera Support**: Control multiple cameras simultaneously
- **NDI Streaming**: Live video preview (requires NDI Runtime)
- **USB Controller**: Gamepad support for hands-free operation
- **Camera Presets**: Store and recall positions
- **Dark Theme**: Professional appearance

## Tested With

- BirdDog P400/P200 cameras
- Xbox Series X controller
- Windows 11

## Configuration

Settings stored at: `%LOCALAPPDATA%\VideoCue\config.json`

## Firewall Note

If NDI camera discovery doesn't work:
- Allow UDP port 5353 (mDNS) in Windows Firewall
- Or use manual NDI source name entry in Add Camera dialog

## Support

- Documentation: See README.md in source repository
- Issues: Report on GitHub
- Camera not responding? Check IP address and VISCA port (default: 52381)

## What's New in v0.1.0

- Initial public release
- Deferred camera loading (UI appears instantly)
- Connection state management with reconnect button
- Comprehensive error handling
- Play/pause video controls
- B button on controller for quick reconnect

## License

MIT License - See LICENSE file

---

**Enjoy controlling your PTZ cameras!** 🎥
