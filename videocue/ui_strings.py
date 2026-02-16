"""
UI string constants for VideoCue application
Centralizes all user-facing strings for consistency and future i18n support
"""


class UIStrings:
    """User interface text constants"""

    # Application
    APP_NAME = "VideoCue"

    # Camera Status
    STATUS_NO_VIDEO = "No Video"
    STATUS_VIDEO_STOPPED = "Video Stopped"
    STATUS_CONNECTING = "Connecting..."
    STATUS_CONNECTED = "Connected"
    STATUS_DISCONNECTED = "Disconnected"
    STATUS_ERROR = "Error"
    STATUS_LOADING = "⟳"

    # Buttons
    BTN_RECONNECT = "Reconnect"
    BTN_DELETE = "×"
    BTN_SETTINGS = "⚙"
    BTN_PLAY = "▶"
    BTN_PAUSE = "⏸"
    BTN_STOP = "Stop"
    BTN_ADD_CAMERA = "Add Camera"
    BTN_SAVE = "Save"
    BTN_CANCEL = "Cancel"
    BTN_OK = "OK"
    BTN_CLOSE = "Close"

    # Tooltips
    TOOLTIP_RECONNECT = "Retry camera connection"
    TOOLTIP_OPEN_WEB = "Open camera web interface"
    TOOLTIP_PLAY_VIDEO = "Play"
    TOOLTIP_PAUSE_VIDEO = "Pause"
    TOOLTIP_USB_CONNECTED = "USB Controller Connected"
    TOOLTIP_USB_DISCONNECTED = "No USB Controller"
    TOOLTIP_BRIGHTNESS_INCREASE = "Increase Brightness"
    TOOLTIP_BRIGHTNESS_DECREASE = "Decrease Brightness"
    TOOLTIP_FOCUS_ONE_PUSH = "One-Push Auto Focus"
    TOOLTIP_STOP_MOVEMENT = "Stop Camera Movement"

    # Camera Controls
    CTRL_PTZ_CONTROLS = "<b>Camera Controls</b>"
    CTRL_EXPOSURE = "Exposure"
    CTRL_WHITE_BALANCE = "White Balance"
    CTRL_FOCUS = "Focus"
    CTRL_PRESETS = "Presets"
    CTRL_BRIGHTNESS = "Bright"
    CTRL_IRIS = "Iris"
    CTRL_SHUTTER = "Shutter"
    CTRL_GAIN = "Gain"
    CTRL_RED_GAIN = "Red"
    CTRL_BLUE_GAIN = "Blue"
    CTRL_BACKLIGHT = "Backlight"

    # Exposure Modes
    EXPOSURE_AUTO = "Auto"
    EXPOSURE_MANUAL = "Manual"
    EXPOSURE_SHUTTER_PRIORITY = "Shutter Priority"
    EXPOSURE_IRIS_PRIORITY = "Iris Priority"
    EXPOSURE_BRIGHT = "Bright"

    # White Balance Modes
    WB_AUTO = "Auto"
    WB_INDOOR = "Indoor"
    WB_OUTDOOR = "Outdoor"
    WB_ONE_PUSH = "One Push"
    WB_MANUAL = "Manual"

    # Focus Modes
    FOCUS_AUTO = "Auto Focus"
    FOCUS_MANUAL = "Manual Focus"
    FOCUS_ONE_PUSH = "One Push AF"
    FOCUS_NEAR = "Near"
    FOCUS_FAR = "Far"

    # Menu Items
    MENU_FILE = "&File"
    MENU_EXIT = "E&xit"
    MENU_EDIT = "&Edit"
    MENU_PREFERENCES = "Controller &Preferences..."
    MENU_VIEW = "&View"
    MENU_VIDEO_SIZE = "Video Size"
    MENU_PERFORMANCE = "Video Performance"
    MENU_HELP = "&Help"
    MENU_CHECK_UPDATES = "Check for &Updates..."
    MENU_ABOUT = "&About"
    # Controller Button Configuration
    GROUP_FOCUS_BUTTON = "One-Push Auto Focus"
    GROUP_STOP_BUTTON = "Stop Camera Movement"
    GROUP_MENU_BUTTON = "Controller Preferences Menu"
    LBL_FOCUS_BUTTON_MAPPING = "Button Trigger:"
    LBL_STOP_BUTTON_MAPPING = "Button Trigger:"
    LBL_MENU_BUTTON_MAPPING = "Button Trigger:"
    # Error Messages
    ERROR_CRITICAL = "Critical Error"
    ERROR_GENERIC = "An unexpected error occurred. The application will attempt to continue."
    ERROR_QT_EVENT = "Qt Event Error"
    ERROR_QT_EVENT_MSG = "An error occurred during UI event processing."
    ERROR_NDI_NOT_AVAILABLE = "NDI Not Available"
    ERROR_CAMERA_CONNECTION = "Camera connection failed"
    ERROR_VIDEO_THREAD = "Video thread error"
    ERROR_CONFIG_LOAD = "Error loading configuration"
    ERROR_CONFIG_SAVE = "Error saving configuration"
    ERROR_USB_INIT = "USB controller initialization failed"

    # Warnings
    WARN_NDI_MESSAGE = (
        "NDI library not available. Please install NDI Runtime:\n\n"
        "Download from: https://ndi.tv/tools/\n\n"
        "The application will continue without NDI video streaming support.\n"
        "You can still control cameras using IP addresses."
    )

    # Info Messages
    INFO_CAMERA_ADDED = "Camera added successfully"
    INFO_CAMERA_REMOVED = "Camera removed"
    INFO_PRESET_SAVED = "Preset saved"
    INFO_PRESET_RECALLED = "Preset recalled"

    # Performance Options
    PERF_MAX = "Maximum Performance"
    PERF_MAX_DESC = "Fastest - ~3 FPS (skips most frames)"
    PERF_HIGH = "High Performance"
    PERF_HIGH_DESC = "Very fast - ~7.5 FPS"
    PERF_BALANCED = "Balanced"
    PERF_BALANCED_DESC = "Good balance - ~10 FPS (recommended)"
    PERF_GOOD = "Good Quality"
    PERF_GOOD_DESC = "Better quality - ~15 FPS"
    PERF_BEST = "Best Quality"
    PERF_BEST_DESC = "Highest quality - ~30 FPS (may lag)"

    # Tabs
    TAB_CAMERAS = "Cameras"
    TAB_CUES = "Cues"

    # Dialog Titles
    DIALOG_ADD_CAMERA = "Add Camera"
    DIALOG_PREFERENCES = "Controller Preferences"
    DIALOG_ABOUT = "About VideoCue"
    DIALOG_CHECK_UPDATES = "Check for Updates"
    DIALOG_CONFIRM_DELETE = "Confirm Delete"
    DIALOG_CONFIRM_DELETE_MSG = "Are you sure you want to remove this camera?"

    # Update Messages
    UPDATE_CHECKING = "Checking for updates..."
    UPDATE_AVAILABLE = "Update Available"
    UPDATE_AVAILABLE_MSG = "A new version of VideoCue is available!\n\nCurrent version: {current}\nLatest version: {latest}\n\nWould you like to download it now?"
    UPDATE_NOT_AVAILABLE = "You are using the latest version of VideoCue ({version})."
    UPDATE_ERROR = (
        "Unable to check for updates. Please check your internet connection and try again."
    )
    UPDATE_ERROR_TITLE = "Update Check Failed"
