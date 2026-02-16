"""
Custom exception hierarchy for VideoCue application
"""


class VideoCueError(Exception):
    """Base exception for all VideoCue errors"""

    pass


class CameraError(VideoCueError):
    """Base exception for camera-related errors"""

    pass


class ViscaError(CameraError):
    """VISCA protocol errors"""

    pass


class ViscaConnectionError(ViscaError):
    """VISCA connection failure"""

    pass


class ViscaCommandError(ViscaError):
    """VISCA command failed or returned error"""

    pass


class ViscaTimeoutError(ViscaError):
    """VISCA command timeout"""

    pass


class NDIError(CameraError):
    """NDI streaming errors"""

    pass


class NDINotAvailableError(NDIError):
    """NDI library not available or not initialized"""

    pass


class NDIConnectionError(NDIError):
    """NDI source connection failure"""

    pass


class NDISourceNotFoundError(NDIError):
    """NDI source not found during discovery"""

    pass


class USBControllerError(VideoCueError):
    """USB game controller errors"""

    pass


class USBControllerNotFoundError(USBControllerError):
    """USB controller not connected"""

    pass


class ConfigError(VideoCueError):
    """Configuration file errors"""

    pass


class ConfigLoadError(ConfigError):
    """Failed to load configuration"""

    pass


class ConfigSaveError(ConfigError):
    """Failed to save configuration"""

    pass
