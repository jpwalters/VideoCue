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

    # Stream Deck Status
    STREAMDECK_CONNECTING = "Stream Deck Connecting..."
    STREAMDECK_CONNECTED = "Stream Deck Connected"
    STREAMDECK_DISCONNECTED = "Stream Deck Disconnected"
    STREAMDECK_NOT_FOUND = "Stream Deck Plus Not Found"
    STREAMDECK_ERROR = "Stream Deck Error"

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
    BTN_STREAMDECK_PAGE_PREV = "PAGE←"
    BTN_STREAMDECK_PAGE_NEXT = "PAGE→"

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
    TOOLTIP_STREAMDECK_PREV = "Previous Camera Page"
    TOOLTIP_STREAMDECK_NEXT = "Next Camera Page"

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
    MENU_SCOPES = "Scopes"
    MENU_VIDEO_SIZE = "Video Size"
    MENU_PERFORMANCE = "Video Performance"
    MENU_COLOR_FORMAT = "Video Format"
    MENU_FALSE_COLOR = "False Color (Atomos-style)"
    TOOLTIP_FALSE_COLOR = "Display Atomos-style false color exposure preview"
    MENU_WAVEFORM = "Waveform Scope (Luma)"
    TOOLTIP_WAVEFORM = "Display luminance waveform scope for black-level evaluation"
    MENU_VECTORSCOPE = "Vectorscope (Chroma)"
    TOOLTIP_VECTORSCOPE = "Display chroma vectorscope with broadcast graticule"
    MENU_RGB_PARADE = "RGB Parade"
    TOOLTIP_RGB_PARADE = "Display side-by-side red, green, and blue waveform channels"
    MENU_HISTOGRAM = "Histogram (Luma + RGB)"
    TOOLTIP_HISTOGRAM = "Display overlaid luma and RGB histogram curves"
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

    # Color Matching
    BTN_MATCH_COLOR = "Match to Selected"
    TOOLTIP_MATCH_COLOR = (
        "Automatically match this camera's white balance and color to the selected camera"
    )
    TOOLTIP_MATCH_COLOR_UNAVAILABLE = (
        "Select a different connected camera as the color reference to enable matching"
    )
    BTN_KEEP = "Keep"
    BTN_REVERT = "Revert"
    DIALOG_COLOR_MATCH = "Color Match"
    MSG_MATCH_AIM_CAMERAS = (
        "Match {target} to {reference}?\n\n"
        "Point both cameras at the same scene and keep them still while matching.\n"
        "Exposure is not changed. This takes up to a few minutes."
    )
    MSG_MATCH_REFERENCE_AUTO_WB = (
        "\n\nNote: the reference camera is not in Manual white balance, so the match "
        "may drift when the lighting changes."
    )
    MSG_MATCH_RESULT = (
        "{target} matched to {reference} in {duration}s.\n\n"
        "Overall color difference: {before:.2f} → {after:.2f}\n"
        "White balance difference: {wb_before:.2f} → {wb_after:.2f}\n"
        "Hue sectors compared: {sectors}"
    )
    MSG_MATCH_NOT_IMPROVED = (
        "Could not improve the match ({before:.2f} → {after:.2f}). "
        "Original settings were restored.\n\n"
        "Make sure both cameras see the same, well-lit scene."
    )
    MSG_MATCH_EXPOSURE_DIFF = (
        "\n\nThe cameras' brightness differs noticeably; consider matching exposure too."
    )
    STATUS_MATCH_PREFLIGHT = "Checking cameras..."
    STATUS_MATCH_SNAPSHOT = "Saving current settings..."
    STATUS_MATCH_SEED = "Preparing target camera..."
    STATUS_MATCH_WB = "Matching white balance..."
    STATUS_MATCH_COLOR = "Matching color..."
    STATUS_MATCH_VERIFY = "Verifying match..."
    STATUS_MATCH_DONE = "Done"
    STATUS_MATCH_CANCELLED = "Color match cancelled; original settings restored"
    ERROR_MATCH_SAME_CAMERA = "Select a different camera as the color reference."
    ERROR_MATCH_NOT_CONNECTED = "Both cameras must be connected."
    ERROR_MATCH_SCOPES_ACTIVE = "Turn off scopes (View → Scopes) before color matching."
    ERROR_MATCH_NO_VIDEO = "Video must be playing on both cameras"
    ERROR_MATCH_REST_UNAVAILABLE = "BirdDog web API (port 8080) not reachable"
    ERROR_MATCH_UNSUPPORTED_MODEL = "Color matching supports BirdDog P200 and P400 cameras only."
    ERROR_MATCH_SCENE = "Scene not usable for matching"
    ERROR_MATCH_BUSY = "A color match is already running."
    ERROR_MATCH_REVERT_FAILED = "Some settings could not be restored:\n{details}"
    ERROR_CONFIG_LOAD = "Error loading configuration"
    ERROR_CONFIG_SAVE = "Error saving configuration"
    ERROR_USB_INIT = "USB controller initialization failed"
    ERROR_STREAMDECK_NO_DEVICE = (
        "Stream Deck Plus device not found. Please connect device and restart."
    )
    ERROR_APP_LAUNCH_FAILED = "Failed to launch application"
    ERROR_APP_CRASHED = "VideoCue closed unexpectedly due to a critical system error."
    ERROR_APP_EXIT_CODE = "Exit code: {code}"
    ERROR_APP_LOG_PATH = "Log file: {path}"
    ERROR_APP_CRASH_TROUBLESHOOT = "Try disabling NDI video in Preferences and reconnect cameras one-by-one to isolate the source."
    ERROR_APP_RESTARTING_SAFE_MODE = "VideoCue detected a startup crash in native video components and will restart with NDI video disabled for this session."
    ERROR_UNHANDLED_EXCEPTION = (
        "VideoCue encountered an unexpected error and cannot continue safely."
    )
    ERROR_EXCEPTION_TYPE = "Exception type: {exception_type}"
    ERROR_EXCEPTION_MESSAGE = "Exception message: {message}"
    ERROR_RESTART_PROMPT = "Choose how to restart VideoCue:"
    ERROR_NATIVE_CRASH_PROMPT = "VideoCue closed unexpectedly due to a critical system error. You can try restarting with or without NDI."
    WARN_NDI_SESSION_DISABLED = (
        "NDI video was automatically disabled for this session after a startup crash.\n"
        "Camera IP control is still available.\n\n"
        "To re-enable NDI later, restart the application and enable NDI video in Preferences."
    )

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

    # ATEM Switcher Tally
    TAB_SWITCHER = "Switcher"
    GROUP_ATEM = "ATEM Switcher Tally"
    ATEM_ENABLE = "Show tally from ATEM switcher"
    ATEM_ENABLE_TOOLTIP = (
        "Connect to a Blackmagic ATEM switcher (UDP port 9910) and mark which camera\n"
        "is on Program (red) and Preview (green). VideoCue only listens; it never switches."
    )
    LBL_ATEM_IP = "Switcher IP:"
    ATEM_IP_TOOLTIP = "IP address of the ATEM switcher (factory default 192.168.10.240)"
    LBL_ATEM_ME = "Tally source:"
    ATEM_ME_1 = "M/E 1 (main program output)"
    ATEM_ME_2 = "M/E 2"
    ATEM_ME_TOOLTIP = (
        "M/E 1 uses the switcher's own tally, including keyers, downstream keyers and\n"
        "transitions.\n"
        "M/E 2 tally is worked out from the M/E 2 buses, transitions and upstream keyers;\n"
        "downstream keyers are not included."
    )
    ATEM_ME_2_UNAVAILABLE = "Switcher reports one M/E; M/E 2 is unavailable"
    ATEM_SHOW_PREVIEW = "Show Preview tally (green)"
    BTN_ATEM_TEST = "Test Connection"
    ATEM_TEST_RUNNING = "Connecting to {ip}..."
    ATEM_TEST_OK = "Connected: {me_count} M/E, {input_count} inputs ({names})"
    ATEM_TEST_FAILED = "No response from {ip} on UDP port 9910"
    ATEM_INVALID_IP = "Enter a valid IPv4 address for the ATEM switcher."
    ATEM_TIPS = (
        "Tips:\n"
        "• Assign each camera's ATEM input by clicking the bar above its video\n"
        "• The laptop must reach the switcher on UDP port 9910\n"
        "• The switcher allows a limited number of control connections at once"
    )
    ATEM_ICON = "ATEM"
    TOOLTIP_ATEM_CONNECTED = "ATEM {ip}: connected, tally from {me}<br>Click to configure"
    TOOLTIP_ATEM_DISCONNECTED = "ATEM {ip}: not connected<br>Click to configure"
    TOOLTIP_ATEM_DISABLED = "ATEM tally disabled<br>Click to configure"
    TOOLTIP_ATEM_ME_FALLBACK = "<br>M/E 2 not available on this switcher; using M/E 1"
    TALLY_PROGRAM = "PROGRAM"
    TALLY_PREVIEW = "PREVIEW"
    TALLY_LABEL = "{state} · {input}"
    TALLY_INPUT_NAMED = "Input {id}: {name}"
    TALLY_INPUT_UNNAMED = "Input {id}"
    TALLY_UNASSIGNED = "No ATEM input · click to assign"
    TOOLTIP_TALLY = "Switcher tally for this camera. Click to choose its ATEM input."
    MENU_ATEM_INPUT_NONE = "None"
    MENU_ATEM_INPUT_SUGGESTED = "{label} (suggested)"

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
    BTN_RESTART_WITH_NDI = "Restart (With NDI)"
    BTN_RESTART_WITHOUT_NDI = "Restart (Without NDI)"
    BTN_EXIT_APP = "Exit"
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
