"""
Application-wide constants
"""


class NetworkConstants:
    """Network and protocol constants"""

    VISCA_DEFAULT_PORT = 52381
    NDI_DISCOVERY_TIMEOUT_MS = (
        10000  # Initial discovery - allow time for all sources (CamControl uses longer timeouts)
    )
    NDI_DISCOVERY_QUICK_TIMEOUT_MS = 1500  # Quick rediscovery for cached sources
    NDI_FRAME_TIMEOUT_MS = 100
    NDI_NO_FRAME_THRESHOLD = 100  # frames before timeout (10 seconds at 100ms timeout)
    NDI_THREAD_STOP_TIMEOUT_S = 2.0  # seconds
    NDI_CONNECTION_RETRY_DELAY_MS = 500  # Delay before retry on connection failure


class UIConstants:
    """UI timing and sizing constants"""

    TIMER_DELAY_MS = 100
    VIDEO_DEFAULT_WIDTH = 512
    VIDEO_DEFAULT_HEIGHT = 288
    BUTTON_MIN_WIDTH = 50
    ERROR_TEXT_MAX_LENGTH = 50
    WINDOW_DEFAULT_X = 100
    WINDOW_DEFAULT_Y = 100
    WINDOW_DEFAULT_WIDTH = 1200
    WINDOW_DEFAULT_HEIGHT = 800


class HardwareConstants:
    """Hardware controller constants"""

    USB_POLL_RATE_MS = 16  # ~60 FPS
    USB_HOTPLUG_CHECK_MS = 5000
    COLOR_GAIN_MIN = 0
    COLOR_GAIN_MAX = 255


class ViscaConstants:
    """VISCA protocol constants"""

    SHUTTER_SPEEDS = [
        "Auto",
        "Manual",
        "1/10000",
        "1/5000",
        "1/3000",
        "1/2000",
        "1/1500",
        "1/1000",
        "1/725",
        "1/500",
        "1/350",
        "1/250",
        "1/180",
        "1/125",
        "1/100",
        "1/90",
        "1/60",
        "1/50",
        "1/30",
        "1/25",
        "1/15",
        "1/8",
        "1/4",
    ]
