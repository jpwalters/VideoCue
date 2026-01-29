# Security Policy

## Supported Versions

Currently, this project is in initial release. Security updates will be provided for the latest version.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |

## Reporting a Vulnerability

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Considerations

### Network Communication
- VISCA-over-IP uses UDP (port 52381) - no encryption by default
- NDI uses mDNS (port 5353) for discovery
- All network communication should be on trusted networks

### Configuration Files
- Config stored locally at `%LOCALAPPDATA%\VideoCue\config.json`
- Contains camera IP addresses and presets
- No passwords or credentials stored

### Third-Party Dependencies
- Keep dependencies updated: `pip install --upgrade -r requirements.txt`
- Monitor security advisories for PyQt6, pygame, numpy

### NDI Runtime
- Downloaded from https://ndi.tv/tools/
- Verify download source before installation
- Keep NDI Runtime updated for security patches

## Best Practices

1. **Firewall**: Configure firewall rules for NDI and VISCA ports
2. **Network Isolation**: Use on trusted/isolated networks for production
3. **Updates**: Keep Python and all dependencies updated
4. **Access Control**: Protect camera web interfaces with strong passwords
5. **Physical Security**: PTZ cameras can be physically controlled - secure installations

## Known Limitations

- No built-in authentication for camera control
- VISCA protocol is unencrypted UDP
- Relies on network security (VLANs, firewalls)

For production deployments, consider:
- Network segmentation
- VPN for remote access
- Camera firmware updates
- Monitoring for unauthorized access
