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
    BTN_ADD_CUE = "＋ Add"
    BTN_GO = "GO"
    BTN_DELETE_TEXT = "Delete"
    BTN_MOVE_UP = "↑"
    BTN_MOVE_DOWN = "↓"

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
    MENU_PREFERENCES = "Preferences..."
    MENU_VIEW = "&View"
    MENU_VIDEO_SIZE = "Video Size"
    MENU_PERFORMANCE = "Video Performance"
    MENU_COLOR_FORMAT = "Video Format"
    MENU_FILE_LOGGING = "Enable File Logging"
    MENU_HELP = "&Help"
    MENU_CHECK_UPDATES = "Check for &Updates..."
    MENU_ABOUT = "&About"
    # Controller Button Configuration
    GROUP_FOCUS_BUTTON = "One-Push Auto Focus"
    GROUP_STOP_BUTTON = "Stop Camera Movement"
    GROUP_MENU_BUTTON = "Preferences Menu"
    LBL_FOCUS_BUTTON_MAPPING = "Button Trigger:"
    LBL_STOP_BUTTON_MAPPING = "Button Trigger:"
    LBL_MENU_BUTTON_MAPPING = "Button Trigger:"
    USB_RUN_CUE_LABEL = "Enable Run on second joystick press (R3)"
    USB_RUN_CUE_TOOLTIP = (
        "When enabled, pressing the second joystick button runs the armed cue in the Cues tab."
    )
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
    DIALOG_PREFERENCES = "Preferences"
    DIALOG_ABOUT = "About VideoCue"
    DIALOG_CHECK_UPDATES = "Check for Updates"
    DIALOG_CONFIRM_DELETE = "Confirm Delete"
    DIALOG_CONFIRM_DELETE_MSG = "Are you sure you want to remove this camera?"
    DIALOG_RESTART_REQUIRED = "Restart Required"
    DIALOG_DELETE_CUE = "Delete Cue"

    # Cues Tab
    CUES_TITLE = "Create cues from camera presets"
    CUES_TABLE_HELP = "Cue rows with dynamic camera columns linked by camera ID"
    LBL_CUE_NAME = "Cue Name"
    LBL_CUE_CAMERA = "Camera"
    LBL_CUE_PRESET = "Preset"
    PLACEHOLDER_CUE_NAME = "Enter cue name"
    CUE_DEFAULT_NAME = "Cue"
    CUE_NO_CAMERAS = "No cameras available"
    CUE_NO_PRESETS = "No presets available"
    CUE_MISSING_CAMERA = "Missing Camera"
    CUE_MISSING_PRESET = "Missing Preset"
    CUE_DELETE_CONFIRM = "Delete cue '{name}'?"
    CUE_CREATE_ERROR = "Please select a camera and preset before creating a cue."
    CUE_RUN_CAMERA_MISSING = "The camera for this cue is not currently loaded."
    CUE_RUN_PRESET_MISSING = "The preset for this cue no longer exists."
    CUE_RUN_CAMERA_DISCONNECTED = "The camera is disconnected. Reconnect and try again."
    CUE_RUN_FAILED = "Failed to run cue '{name}'."
    CUE_COL_NUMBER = "Cue"
    CUE_COL_NAME = "Name"
    CUE_COL_CAMERA = "Cam {index}"
    CUE_COL_ARMED = "Next"
    CUE_ARMED_MARKER = ">"
    BTN_ADD_CUE_ROW = "Add Cue Row"
    BTN_DELETE_CUE_ROW = "Delete Selected Row"
    BTN_DELETE_CUE = "🗑 Delete"
    BTN_DUPLICATE_CUE = "⧉ Duplicate"
    BTN_INSERT_CUE = "↳ Insert"
    BTN_RUN_CUE = "▶ Run"
    BTN_LOCK = "🔒"
    BTN_UNLOCK = "🔓"
    TOOLTIP_CUE_LOCKED = "Cues table is locked"
    TOOLTIP_CUE_UNLOCKED = "Cues table is unlocked"
    CUE_INVALID_NUMBER = "Cue must be a whole number or decimal value (example: 100 or 100.1)."
    CUE_RUN_NO_SELECTION = "Select a cue row to run."

    # Logging Messages
    LOGGING_ENABLED_MSG = (
        "File logging has been enabled.\n\nPlease restart VideoCue for this change to take effect."
    )
    LOGGING_DISABLED_MSG = (
        "File logging has been disabled.\n\nPlease restart VideoCue for this change to take effect."
    )

    # Update Messages
    UPDATE_CHECKING = "Checking for updates..."
    UPDATE_AVAILABLE = "Update Available"
    UPDATE_AVAILABLE_MSG = "A new version of VideoCue is available!\n\nCurrent version: {current}\nLatest version: {latest}\n\nWould you like to download it now?"
    UPDATE_NOT_AVAILABLE = "You are using the latest version of VideoCue ({version})."
    UPDATE_ERROR = (
        "Unable to check for updates. Please check your internet connection and try again."
    )
    UPDATE_ERROR_TITLE = "Update Check Failed"
