"""
Custom exception hierarchy for VideoCue application
"""


class VideoCueException(Exception):
    """Base exception for all VideoCue errors"""
    pass


class CameraException(VideoCueException):
    """Base exception for camera-related errors"""
    pass


class ViscaException(CameraException):
    """VISCA protocol errors"""
    pass


class ViscaConnectionError(ViscaException):
    """VISCA connection failure"""
    pass


class ViscaCommandError(ViscaException):
    """VISCA command failed or returned error"""
    pass


class ViscaTimeoutError(ViscaException):
    """VISCA command timeout"""
    pass


class NDIException(CameraException):
    """NDI streaming errors"""
    pass


class NDINotAvailableError(NDIException):
    """NDI library not available or not initialized"""
    pass


class NDIConnectionError(NDIException):
    """NDI source connection failure"""
    pass


class NDISourceNotFoundError(NDIException):
    """NDI source not found during discovery"""
    pass


class USBControllerException(VideoCueException):
    """USB game controller errors"""
    pass


class USBControllerNotFoundError(USBControllerException):
    """USB controller not connected"""
    pass


class ConfigException(VideoCueException):
    """Configuration file errors"""
    pass


class ConfigLoadError(ConfigException):
    """Failed to load configuration"""
    pass


class ConfigSaveError(ConfigException):
    """Failed to save configuration"""
    pass
