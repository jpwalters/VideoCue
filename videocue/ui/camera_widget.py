"""
Camera widget displaying video and controls
"""
import logging
from typing import List
from PyQt6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QGridLayout, QSizePolicy,
    QRadioButton, QButtonGroup, QInputDialog, QMessageBox,
    QSlider, QCheckBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QTimer, QThread  # type: ignore
from PyQt6.QtGui import QPixmap, QImage  # type: ignore

from videocue.controllers.visca_ip import ViscaIP, FocusMode, Direction
from videocue.controllers.visca_commands import ViscaConstants
from videocue.controllers.ndi_video import NDIVideoThread, ndi_available
from videocue.controllers.usb_controller import MovementDirection
from videocue.models.config_manager import ConfigManager
from videocue.models.video import CameraPreset
from videocue.exceptions import ViscaTimeoutError, ViscaConnectionError
from videocue.constants import HardwareConstants

logger = logging.getLogger(__name__)


class ViscaConnectionTestThread(QThread):
    """Background thread for testing VISCA connection without blocking UI"""
    test_complete = pyqtSignal(bool, str)  # success, error_message
    
    def __init__(self, visca: ViscaIP):
        super().__init__()
        self.visca = visca
    
    def run(self) -> None:
        """Test connection in background"""
        try:
            # Test with a query command that requires a response
            focus_mode = self.visca.query_focus_mode()
            success = focus_mode != FocusMode.UNKNOWN
            if success:
                logger.debug(f"VISCA connection test passed for {self.visca.ip}")
            else:
                logger.warning(f"VISCA connection test failed for {self.visca.ip}")
            self.test_complete.emit(success, "" if success else "Connection failed")
        except ViscaTimeoutError as e:
            logger.error(f"VISCA connection timeout for {self.visca.ip}: {e}")
            self.test_complete.emit(False, str(e))
        except ViscaConnectionError as e:
            logger.error(f"VISCA connection error for {self.visca.ip}: {e}")
            self.test_complete.emit(False, str(e))
        except Exception as e:
            logger.exception(f"Unexpected error testing VISCA connection for {self.visca.ip}")
            self.test_complete.emit(False, str(e))


class CameraWidget(QWidget):
    """Camera control widget with video display and PTZ controls"""

    delete_requested = pyqtSignal()
    move_left_requested = pyqtSignal()
    move_right_requested = pyqtSignal()
    connection_starting = pyqtSignal()  # Emitted when connection attempt begins
    initialized = pyqtSignal()  # Emitted when camera initialization complete

    def __init__(self, camera_id: str, ndi_source_name: str, visca_ip: str,
                 visca_port: int, config: ConfigManager, init_delay: int = 100,
                 video_size: List[int] = None):
        super().__init__()

        self.camera_id = camera_id
        self.ndi_source_name = ndi_source_name
        self.visca_ip = visca_ip
        self.visca_port = visca_port
        self.config = config
        self.init_delay = init_delay  # Staggered startup delay

        self.is_selected = False
        self.is_connected = False  # Track connection state
        self.visca = ViscaIP(visca_ip, visca_port)
        self.ndi_thread = None

        # Use provided video size or get from config
        if video_size is None:
            video_size = config.get_default_video_size()
        self.video_width = video_size[0]
        self.video_height = video_size[1]

        # Auto pan state
        self.auto_pan_active = False
        
        # Connection retry state
        self._retry_count = 0
        self._max_retries = 3
        self._retry_timer = QTimer()
        self._retry_timer.timeout.connect(self._retry_connection)
        
        # Cached display name to avoid repeated formatting
        self._cached_display_name: str = ""

        # Pre-initialize attributes (defined in init_ui and create_controls_layout)
        self.brightness_vertical_container = None
        self.brightness_slider_vertical = None
        self.brightness_value_vertical = None
        self.btn_up_left = None
        self.btn_up = None
        self.btn_up_right = None
        self.btn_left = None
        self.btn_stop = None
        self.btn_right = None
        self.btn_down_left = None
        self.btn_down = None
        self.btn_down_right = None
        self.btn_zoom_out = None
        self.btn_zoom_stop = None
        self.btn_zoom_in = None
        self.presets_label = None
        self.presets_container = None
        self.presets_layout = None
        self.left_preset_combo = None
        self.right_preset_combo = None
        self.auto_pan_speed_slider = None
        self.auto_pan_speed_value_label = None
        self.start_auto_pan_btn = None
        self.stop_auto_pan_btn = None
        self.auto_pan_status_label = None
        self.auto_pan_timer = None
        self.auto_pan_current_target = None
        self.focus_group = None
        self.radio_autofocus = None
        self.radio_manual_focus = None
        self.one_push_af_btn = None
        self.btn_focus_near = None
        self.btn_focus_far = None
        self.manual_focus_widget = None
        self.exposure_combo = None
        self.iris_label = None
        self.iris_slider = None
        self.iris_value_label = None
        self.iris_layout_widget = None
        self.shutter_label = None
        self.shutter_slider = None
        self.shutter_value_label = None
        self.shutter_layout_widget = None
        self.gain_label = None
        self.gain_slider = None
        self.gain_value_label = None
        self.gain_layout_widget = None
        self.brightness_label = None
        self.brightness_slider = None
        self.brightness_value_label = None
        self.brightness_layout_widget = None
        self.backlight_checkbox = None
        self.wb_combo = None
        self.red_gain_label = None
        self.red_gain_slider = None
        self.red_gain_value_label = None
        self.blue_gain_label = None
        self.blue_gain_slider = None
        self.blue_gain_value_label = None
        self.wb_manual_widget = None
        self.one_push_wb_btn = None
        self.red_gain_layout_widget = None
        self.blue_gain_layout_widget = None
        self._last_frame_time = None

        self.init_ui()
        
        # Start with controls disabled until connection is established
        # (will be enabled after successful connection test)
        self.set_controls_enabled(False)

        # Set initial widget width based on default video size
        self.setFixedWidth(self.video_width + 14)

        # Defer video initialization to avoid blocking UI startup
        # NDI sources should already be cached by main_window.load_cameras()
        # Use staggered delays to prevent all cameras from starting simultaneously
        if ndi_source_name and ndi_available:
            QTimer.singleShot(self.init_delay, self.start_video)
        elif visca_ip and ndi_available and not ndi_source_name:
            QTimer.singleShot(self.init_delay, self.try_discover_ndi_source)
        else:
            # No video initialization needed, but test VISCA connection for IP-only cameras
            if not ndi_available or not ndi_source_name:
                QTimer.singleShot(self.init_delay, self._test_visca_connection)
            else:
                QTimer.singleShot(self.init_delay, self.initialized.emit)

    def _format_camera_display_name(self, ndi_name: str = None, ip: str = None, force_refresh: bool = False) -> str:
        """
        Format camera display name, avoiding redundancy.
        If NDI name and IP are the same (case-insensitive), only show one.
        Results are cached to avoid repeated formatting.
        
        Args:
            ndi_name: Optional NDI source name override
            ip: Optional IP address override
            force_refresh: Force recalculation even if cached
        
        Returns:
            Formatted display name string
        """
        # Use cached value if available and not forcing refresh
        if self._cached_display_name and not force_refresh:
            return self._cached_display_name
        
        ndi = ndi_name or self.ndi_source_name
        addr = ip or self.visca_ip
        
        if not ndi:
            # No NDI name, just show IP
            result = addr
        elif addr.lower() in ndi.lower() or ndi.lower() == addr.lower():
            # Redundant, just show NDI name
            result = ndi
        else:
            # Different, show both
            result = f"{ndi} ({addr})"
        
        # Cache the result
        self._cached_display_name = result
        logger.debug(f"Formatted camera display name: {result}")
        return result
    
    def init_ui(self):
        """Initialize widget UI"""
        # Don't set fixed width initially - will be set based on video size

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Video display
        self.video_label = QLabel()
        self.video_label.setFixedSize(self.video_width, self.video_height)
        self.video_label.setStyleSheet("background-color: black; border: 2px solid grey;")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setText("No Video")
        layout.addWidget(self.video_label)

        # Brightness overlay (positioned over video display)
        self.brightness_overlay = QLabel(self.video_label)
        self.brightness_overlay.setStyleSheet(
            "background-color: rgba(0, 0, 0, 180); "
            "color: white; "
            "font-size: 24px; "
            "font-weight: bold; "
            "padding: 10px 20px; "
            "border-radius: 8px;"
        )
        self.brightness_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brightness_overlay.hide()
        self.brightness_overlay_timer = QTimer()
        self.brightness_overlay_timer.setSingleShot(True)
        self.brightness_overlay_timer.timeout.connect(self.brightness_overlay.hide)

        # Status bar
        status_bar = QHBoxLayout()

        # Connection indicator
        self.status_indicator = QWidget()
        self.status_indicator.setFixedSize(12, 12)
        self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
        status_bar.addWidget(self.status_indicator)
        
        # Reconnect button (shown when connection fails)
        self.reconnect_button = QPushButton("Reconnect")
        self.reconnect_button.setFixedHeight(20)
        self.reconnect_button.setStyleSheet("font-size: 10px; padding: 2px 8px;")
        self.reconnect_button.setToolTip("Retry camera connection")
        self.reconnect_button.clicked.connect(self.reconnect_camera)
        self.reconnect_button.setVisible(False)
        status_bar.addWidget(self.reconnect_button)

        # Loading indicator
        self.loading_label = QLabel("⟳")
        self.loading_label.setStyleSheet("font-size: 16px; color: orange;")
        self.loading_label.setVisible(False)
        status_bar.addWidget(self.loading_label)

        # Camera name and IP
        display_text = self._format_camera_display_name()
        self.name_label = QLabel(display_text)
        status_bar.addWidget(self.name_label)

        # Resolution label (initially hidden until video connects)
        self.resolution_label = QLabel("")
        self.resolution_label.setStyleSheet("color: gray; font-size: 10px;")
        self.resolution_label.setVisible(False)
        status_bar.addWidget(self.resolution_label)

        status_bar.addStretch()

        # Video start/stop button
        self.video_toggle_button = QPushButton("▶")  # Start as play icon (video not started yet)
        self.video_toggle_button.setFixedWidth(30)
        self.video_toggle_button.setStyleSheet("font-size: 14px;")
        self.video_toggle_button.setToolTip("Play")
        self.video_toggle_button.clicked.connect(self.toggle_video_streaming)
        self.video_toggle_button.setEnabled(ndi_available and bool(self.ndi_source_name))
        status_bar.addWidget(self.video_toggle_button)

        # Move left button
        move_left_button = QPushButton("◀")
        move_left_button.setFixedWidth(30)
        move_left_button.setStyleSheet("font-size: 12px;")
        move_left_button.setToolTip("Move camera left")
        move_left_button.clicked.connect(self.move_left_requested.emit)
        status_bar.addWidget(move_left_button)

        # Move right button
        move_right_button = QPushButton("▶")
        move_right_button.setFixedWidth(30)
        move_right_button.setStyleSheet("font-size: 12px;")
        move_right_button.setToolTip("Move camera right")
        move_right_button.clicked.connect(self.move_right_requested.emit)
        status_bar.addWidget(move_right_button)

        # Web browser button (settings icon)
        web_button = QPushButton("⚙")
        web_button.setFixedWidth(30)
        web_button.setStyleSheet("font-size: 14px;")
        web_button.setToolTip("Open camera web interface")
        web_button.clicked.connect(self.open_web_browser)
        status_bar.addWidget(web_button)

        # Delete button
        delete_button = QPushButton("×")
        delete_button.setFixedWidth(30)
        delete_button.setStyleSheet("font-size: 16px;")
        delete_button.clicked.connect(self.delete_requested.emit)
        status_bar.addWidget(delete_button)

        layout.addLayout(status_bar)

        # Controls scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(400)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Controls container
        self.controls_container = QWidget()
        self.controls_layout = QVBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(5, 5, 5, 5)
        self.controls_layout.setSpacing(10)

        scroll_area.setWidget(self.controls_container)
        layout.addWidget(scroll_area)

        self.create_controls_layout()

    def create_controls_layout(self):
        """Create controls layout"""
        # Camera Controls section
        controls_label = QLabel("<b>Camera Controls</b>")
        self.controls_layout.addWidget(controls_label)

        controls_widget = QWidget()
        controls_widget_layout = QVBoxLayout(controls_widget)
        controls_widget_layout.setContentsMargins(5, 5, 5, 5)

        # PTZ and brightness controls container with brightness on far left
        ptz_brightness_layout = QHBoxLayout()
        ptz_brightness_layout.setSpacing(5)
        ptz_brightness_layout.setContentsMargins(0, 0, 0, 0)

        # Vertical brightness slider (far left side) - compact design
        self.brightness_vertical_container = QWidget()
        self.brightness_vertical_container.setFixedWidth(30)  # Fix container width to match slider
        brightness_container = QVBoxLayout(self.brightness_vertical_container)
        brightness_container.setSpacing(2)
        brightness_container.setContentsMargins(0, 0, 0, 0)
        brightness_label = QLabel("Brt")
        brightness_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brightness_label.setStyleSheet("font-size: 9px;")
        brightness_container.addWidget(brightness_label)

        self.brightness_slider_vertical = QSlider(Qt.Orientation.Vertical)
        self.brightness_slider_vertical.setRange(0, 41)
        self.brightness_slider_vertical.setValue(21)
        self.brightness_slider_vertical.setFixedHeight(180)
        self.brightness_slider_vertical.valueChanged.connect(self.on_brightness_vertical_changed)
        brightness_container.addWidget(self.brightness_slider_vertical,
                                       0, Qt.AlignmentFlag.AlignCenter)

        self.brightness_value_vertical = QLabel("21")
        self.brightness_value_vertical.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brightness_value_vertical.setStyleSheet("font-size: 10px;")
        brightness_container.addWidget(self.brightness_value_vertical)

        ptz_brightness_layout.addWidget(
            self.brightness_vertical_container, 0)  # 0 stretch - don't expand
        ptz_brightness_layout.addStretch()  # Center PTZ grid in remaining space

        # PTZ button grid
        ptz_grid = QGridLayout()
        ptz_grid.setSpacing(2)
        ptz_grid.setContentsMargins(0, 0, 0, 0)

        # Create 9 buttons (3x3 grid)
        self.btn_up_left = self.create_ptz_button("↖")
        self.btn_up = self.create_ptz_button("↑")
        self.btn_up_right = self.create_ptz_button("↗")
        self.btn_left = self.create_ptz_button("←")
        self.btn_stop = self.create_ptz_button("■")
        self.btn_right = self.create_ptz_button("→")
        self.btn_down_left = self.create_ptz_button("↙")
        self.btn_down = self.create_ptz_button("↓")
        self.btn_down_right = self.create_ptz_button("↘")

        ptz_grid.addWidget(self.btn_up_left, 0, 0)
        ptz_grid.addWidget(self.btn_up, 0, 1)
        ptz_grid.addWidget(self.btn_up_right, 0, 2)
        ptz_grid.addWidget(self.btn_left, 1, 0)
        ptz_grid.addWidget(self.btn_stop, 1, 1)
        ptz_grid.addWidget(self.btn_right, 1, 2)
        ptz_grid.addWidget(self.btn_down_left, 2, 0)
        ptz_grid.addWidget(self.btn_down, 2, 1)
        ptz_grid.addWidget(self.btn_down_right, 2, 2)

        # Wire PTZ buttons
        self.btn_up_left.pressed.connect(lambda: self.move_camera(Direction.UP_LEFT))
        self.btn_up_left.released.connect(self.stop_camera)
        self.btn_up.pressed.connect(lambda: self.move_camera(Direction.UP))
        self.btn_up.released.connect(self.stop_camera)
        self.btn_up_right.pressed.connect(lambda: self.move_camera(Direction.UP_RIGHT))
        self.btn_up_right.released.connect(self.stop_camera)
        self.btn_left.pressed.connect(lambda: self.move_camera(Direction.LEFT))
        self.btn_left.released.connect(self.stop_camera)
        self.btn_stop.clicked.connect(self.stop_camera)
        self.btn_right.pressed.connect(lambda: self.move_camera(Direction.RIGHT))
        self.btn_right.released.connect(self.stop_camera)
        self.btn_down_left.pressed.connect(lambda: self.move_camera(Direction.DOWN_LEFT))
        self.btn_down_left.released.connect(self.stop_camera)
        self.btn_down.pressed.connect(lambda: self.move_camera(Direction.DOWN))
        self.btn_down.released.connect(self.stop_camera)
        self.btn_down_right.pressed.connect(lambda: self.move_camera(Direction.DOWN_RIGHT))
        self.btn_down_right.released.connect(self.stop_camera)

        ptz_brightness_layout.addLayout(ptz_grid, 0)  # 0 stretch - don't expand PTZ grid
        ptz_brightness_layout.addStretch()  # Center PTZ grid in remaining space
        controls_widget_layout.addLayout(ptz_brightness_layout)

        # Zoom controls
        zoom_layout = QHBoxLayout()
        zoom_layout.addStretch()

        self.btn_zoom_out = QPushButton("Zoom -")
        self.btn_zoom_out.setMinimumWidth(50)
        self.btn_zoom_out.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_zoom_out.pressed.connect(lambda: self.zoom_camera(-1))
        self.btn_zoom_out.released.connect(self.zoom_stop)
        zoom_layout.addWidget(self.btn_zoom_out)

        self.btn_zoom_stop = QPushButton("Stop")
        self.btn_zoom_stop.setMinimumWidth(40)
        self.btn_zoom_stop.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_zoom_stop.clicked.connect(self.zoom_stop)
        zoom_layout.addWidget(self.btn_zoom_stop)

        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_in.setMinimumWidth(50)
        self.btn_zoom_in.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_zoom_in.pressed.connect(lambda: self.zoom_camera(1))
        self.btn_zoom_in.released.connect(self.zoom_stop)
        zoom_layout.addWidget(self.btn_zoom_in)

        zoom_layout.addStretch()
        controls_widget_layout.addLayout(zoom_layout)

        # Speed limit reset button
        speed_reset_layout = QHBoxLayout()
        speed_reset_layout.addStretch()

        reset_speed_btn = QPushButton("⚡ Reset Speed Limit")
        reset_speed_btn.setToolTip("Reset camera to maximum pan/tilt speed (fixes slow movement)")
        reset_speed_btn.setMinimumWidth(80)
        reset_speed_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        reset_speed_btn.setStyleSheet("background-color: #444; color: #ffcc00; font-weight: bold;")
        reset_speed_btn.clicked.connect(self.on_reset_speed_limit)
        speed_reset_layout.addWidget(reset_speed_btn)

        speed_reset_layout.addStretch()
        controls_widget_layout.addLayout(speed_reset_layout)

        self.controls_layout.addWidget(controls_widget)

        # Auto Pan section
        auto_pan_label = QLabel("<b>Auto Pan</b>")
        self.controls_layout.addWidget(auto_pan_label)

        auto_pan_widget = self.create_auto_pan_widget()
        self.controls_layout.addWidget(auto_pan_widget)

        # Settings section
        settings_label = QLabel("<b>Settings</b>")
        self.controls_layout.addWidget(settings_label)

        settings_widget = self.create_settings_widget()
        self.controls_layout.addWidget(settings_widget)

        # Presets section
        self.presets_label = QLabel("<b>Preset Locations</b>")
        self.controls_layout.addWidget(self.presets_label)

        # Presets container
        self.presets_container = QWidget()
        self.presets_layout = QVBoxLayout(self.presets_container)
        self.presets_layout.setContentsMargins(5, 5, 5, 5)
        self.presets_layout.setSpacing(5)
        self.controls_layout.addWidget(self.presets_container)

        self.update_presets_widget()

        self.controls_layout.addStretch()

    def create_ptz_button(self, text: str) -> QPushButton:
        """Create PTZ control button"""
        btn = QPushButton(text)
        btn.setFixedSize(60, 60)
        btn.setStyleSheet("font-size: 20px; font-weight: bold;")
        return btn

    def create_auto_pan_widget(self) -> QWidget:
        """Create auto pan controls panel (preset-based)"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Instructions
        instructions = QLabel(
            "<b>Preset-Based Auto Pan</b><br>"
            "1. Create presets at left and right positions<br>"
            "2. Select which presets to use for auto pan<br>"
            "3. Click Start to pan continuously between them"
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet(
            "color: #aaa; font-size: 10px; padding: 5px; "
            "background-color: #2a2a2a; border-radius: 3px;")
        instructions.setMinimumWidth(50)
        instructions.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout.addWidget(instructions)

        # Preset selection
        preset_selection_layout = QHBoxLayout()

        preset_selection_layout.addWidget(QLabel("Left Position:"))
        self.left_preset_combo = QComboBox()
        self.left_preset_combo.setMinimumWidth(50)
        self.left_preset_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.left_preset_combo.currentTextChanged.connect(self.on_auto_pan_preset_changed)
        preset_selection_layout.addWidget(self.left_preset_combo)

        preset_selection_layout.addWidget(QLabel("Right Position:"))
        self.right_preset_combo = QComboBox()
        self.right_preset_combo.setMinimumWidth(50)
        self.right_preset_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.right_preset_combo.currentTextChanged.connect(self.on_auto_pan_preset_changed)
        preset_selection_layout.addWidget(self.right_preset_combo)

        layout.addLayout(preset_selection_layout)

        # Populate preset dropdowns
        self.update_auto_pan_preset_list()

        # Speed control
        speed_label = QLabel("Pan Speed (delay between positions):")
        layout.addWidget(speed_label)

        speed_layout = QHBoxLayout()
        self.auto_pan_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.auto_pan_speed_slider.setMinimum(1)
        self.auto_pan_speed_slider.setMaximum(10)
        self.auto_pan_speed_slider.setValue(3)
        self.auto_pan_speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.auto_pan_speed_slider.setTickInterval(1)
        self.auto_pan_speed_slider.setMinimumWidth(60)
        self.auto_pan_speed_slider.valueChanged.connect(self.on_auto_pan_speed_changed)
        speed_layout.addWidget(self.auto_pan_speed_slider)

        self.auto_pan_speed_value_label = QLabel("3s")
        self.auto_pan_speed_value_label.setFixedWidth(25)
        speed_layout.addWidget(self.auto_pan_speed_value_label)
        layout.addLayout(speed_layout)

        # Start/Stop auto pan buttons
        auto_pan_control_layout = QHBoxLayout()

        self.start_auto_pan_btn = QPushButton("▶ Start Auto Pan")
        self.start_auto_pan_btn.setToolTip("Start automatic panning between selected presets")
        self.start_auto_pan_btn.setStyleSheet("background-color: #2d5016; font-weight: bold;")
        self.start_auto_pan_btn.setMinimumWidth(50)
        self.start_auto_pan_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.start_auto_pan_btn.clicked.connect(self.on_start_auto_pan)
        auto_pan_control_layout.addWidget(self.start_auto_pan_btn)

        self.stop_auto_pan_btn = QPushButton("■ Stop Auto Pan")
        self.stop_auto_pan_btn.setToolTip("Stop automatic panning")
        self.stop_auto_pan_btn.setStyleSheet("background-color: #5d1616; font-weight: bold;")
        self.stop_auto_pan_btn.setMinimumWidth(50)
        self.stop_auto_pan_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.stop_auto_pan_btn.clicked.connect(self.on_stop_auto_pan)
        self.stop_auto_pan_btn.setEnabled(False)
        auto_pan_control_layout.addWidget(self.stop_auto_pan_btn)

        layout.addLayout(auto_pan_control_layout)

        # Status indicator
        self.auto_pan_status_label = QLabel("Status: Stopped")
        self.auto_pan_status_label.setStyleSheet("color: #888; font-style: italic;")
        self.auto_pan_status_label.setMinimumWidth(50)
        self.auto_pan_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.auto_pan_status_label)

        # Auto pan timer
        self.auto_pan_timer = QTimer()
        self.auto_pan_timer.timeout.connect(self.auto_pan_tick)
        self.auto_pan_current_target = "left"  # Start by going to left

        return widget

    def create_settings_widget(self) -> QWidget:
        """Create settings panel"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # Focus mode
        focus_label = QLabel("Focus Mode:")
        layout.addWidget(focus_label)

        focus_layout = QHBoxLayout()
        self.focus_group = QButtonGroup()

        self.radio_autofocus = QRadioButton("Auto")
        self.radio_manual_focus = QRadioButton("Manual")

        self.focus_group.addButton(self.radio_autofocus, 0)
        self.focus_group.addButton(self.radio_manual_focus, 1)

        self.radio_autofocus.toggled.connect(self.on_focus_mode_changed)

        focus_layout.addWidget(self.radio_autofocus)
        focus_layout.addWidget(self.radio_manual_focus)

        # One Push AF button
        self.one_push_af_btn = QPushButton("One Push")
        self.one_push_af_btn.setToolTip("Trigger single autofocus operation")
        self.one_push_af_btn.setMinimumWidth(60)
        self.one_push_af_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.one_push_af_btn.clicked.connect(self.on_one_push_af)
        focus_layout.addWidget(self.one_push_af_btn)

        focus_layout.addStretch()

        layout.addLayout(focus_layout)

        # Manual focus controls (Near/Far buttons)
        manual_focus_layout = QHBoxLayout()
        manual_focus_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_focus_near = QPushButton("◄ Near")
        self.btn_focus_near.setToolTip("Focus closer (hold for continuous)")
        self.btn_focus_near.setMinimumWidth(50)
        self.btn_focus_near.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_focus_near.pressed.connect(self.focus_near)
        self.btn_focus_near.released.connect(self.focus_stop)
        manual_focus_layout.addWidget(self.btn_focus_near)

        self.btn_focus_far = QPushButton("Far ►")
        self.btn_focus_far.setToolTip("Focus farther (hold for continuous)")
        self.btn_focus_far.setMinimumWidth(50)
        self.btn_focus_far.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_focus_far.pressed.connect(self.focus_far)
        self.btn_focus_far.released.connect(self.focus_stop)
        manual_focus_layout.addWidget(self.btn_focus_far)

        manual_focus_layout.addStretch()

        self.manual_focus_widget = QWidget()
        self.manual_focus_widget.setLayout(manual_focus_layout)
        layout.addWidget(self.manual_focus_widget)

        # Update manual focus button visibility based on focus mode
        self.update_focus_controls_visibility()

        # Exposure mode
        exposure_label = QLabel("Exposure Mode:")
        layout.addWidget(exposure_label)

        self.exposure_combo = QComboBox()
        self.exposure_combo.addItem("Auto", 0)
        self.exposure_combo.addItem("Manual", 1)
        self.exposure_combo.addItem("Shutter Priority", 2)
        self.exposure_combo.addItem("Iris Priority", 3)
        self.exposure_combo.addItem("Bright", 4)
        self.exposure_combo.setMinimumWidth(5)
        self.exposure_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.exposure_combo.currentIndexChanged.connect(self.on_exposure_mode_changed)
        layout.addWidget(self.exposure_combo)

        # Iris control
        self.iris_label = QLabel("Iris (Aperture):")
        layout.addWidget(self.iris_label)

        iris_layout = QHBoxLayout()
        self.iris_slider = QSlider(Qt.Orientation.Horizontal)
        self.iris_slider.setMinimum(0)
        self.iris_slider.setMaximum(17)
        self.iris_slider.setValue(8)
        self.iris_slider.valueChanged.connect(self.on_iris_changed)
        self.iris_value_label = QLabel("F8")
        iris_layout.addWidget(self.iris_slider)
        iris_layout.addWidget(self.iris_value_label)
        self.iris_layout_widget = QWidget()
        self.iris_layout_widget.setLayout(iris_layout)
        layout.addWidget(self.iris_layout_widget)

        # Shutter control
        self.shutter_label = QLabel("Shutter Speed:")
        layout.addWidget(self.shutter_label)

        shutter_layout = QHBoxLayout()
        self.shutter_slider = QSlider(Qt.Orientation.Horizontal)
        self.shutter_slider.setMinimum(0)
        self.shutter_slider.setMaximum(21)
        self.shutter_slider.setValue(10)
        self.shutter_slider.valueChanged.connect(self.on_shutter_changed)
        self.shutter_value_label = QLabel("1/60")
        shutter_layout.addWidget(self.shutter_slider)
        shutter_layout.addWidget(self.shutter_value_label)
        self.shutter_layout_widget = QWidget()
        self.shutter_layout_widget.setLayout(shutter_layout)
        layout.addWidget(self.shutter_layout_widget)

        # Gain control
        self.gain_label = QLabel("Gain:")
        layout.addWidget(self.gain_label)

        gain_layout = QHBoxLayout()
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setMinimum(0)
        self.gain_slider.setMaximum(15)
        self.gain_slider.setValue(0)
        self.gain_slider.valueChanged.connect(self.on_gain_changed)
        self.gain_value_label = QLabel("0 dB")
        gain_layout.addWidget(self.gain_slider)
        gain_layout.addWidget(self.gain_value_label)
        self.gain_layout_widget = QWidget()
        self.gain_layout_widget.setLayout(gain_layout)
        layout.addWidget(self.gain_layout_widget)

        # Brightness (for Bright mode, 0-41 range)
        self.brightness_label = QLabel("Brightness:")
        layout.addWidget(self.brightness_label)
        brightness_layout = QHBoxLayout()
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(0, 41)
        self.brightness_slider.setValue(21)  # Middle value
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)
        self.brightness_slider.valueChanged.connect(self.show_brightness_overlay)
        self.brightness_value_label = QLabel("21")
        brightness_layout.addWidget(self.brightness_slider)
        brightness_layout.addWidget(self.brightness_value_label)
        self.brightness_layout_widget = QWidget()
        self.brightness_layout_widget.setLayout(brightness_layout)
        layout.addWidget(self.brightness_layout_widget)

        # Backlight compensation
        self.backlight_checkbox = QCheckBox("Backlight Compensation")
        self.backlight_checkbox.stateChanged.connect(self.on_backlight_changed)
        layout.addWidget(self.backlight_checkbox)

        # White Balance section
        wb_label = QLabel("White Balance Mode:")
        layout.addWidget(wb_label)

        self.wb_combo = QComboBox()
        self.wb_combo.addItem("Auto", 0)
        self.wb_combo.addItem("Indoor (3200K)", 1)
        self.wb_combo.addItem("Outdoor (5600K)", 2)
        self.wb_combo.addItem("One Push", 3)
        self.wb_combo.addItem("Manual", 4)
        self.wb_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.wb_combo.currentIndexChanged.connect(self.on_wb_mode_changed)
        layout.addWidget(self.wb_combo)

        # One Push WB button
        wb_button_layout = QHBoxLayout()
        self.one_push_wb_btn = QPushButton("One Push WB")
        self.one_push_wb_btn.setToolTip("Trigger single white balance calibration")
        self.one_push_wb_btn.setMinimumWidth(70)
        self.one_push_wb_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.one_push_wb_btn.clicked.connect(self.on_one_push_wb)
        wb_button_layout.addWidget(self.one_push_wb_btn)
        wb_button_layout.addStretch()
        layout.addLayout(wb_button_layout)

        # Red Gain (for manual WB)
        self.red_gain_label = QLabel("Red Gain:")
        layout.addWidget(self.red_gain_label)

        red_gain_layout = QHBoxLayout()
        self.red_gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.red_gain_slider.setRange(HardwareConstants.COLOR_GAIN_MIN, HardwareConstants.COLOR_GAIN_MAX)
        self.red_gain_slider.setValue(128)
        self.red_gain_slider.valueChanged.connect(self.on_red_gain_changed)
        self.red_gain_value_label = QLabel("128")
        red_gain_layout.addWidget(self.red_gain_slider)
        red_gain_layout.addWidget(self.red_gain_value_label)
        self.red_gain_layout_widget = QWidget()
        self.red_gain_layout_widget.setLayout(red_gain_layout)
        layout.addWidget(self.red_gain_layout_widget)

        # Blue Gain (for manual WB)
        self.blue_gain_label = QLabel("Blue Gain:")
        layout.addWidget(self.blue_gain_label)

        blue_gain_layout = QHBoxLayout()
        self.blue_gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.blue_gain_slider.setRange(HardwareConstants.COLOR_GAIN_MIN, HardwareConstants.COLOR_GAIN_MAX)
        self.blue_gain_slider.setValue(128)
        self.blue_gain_slider.valueChanged.connect(self.on_blue_gain_changed)
        self.blue_gain_value_label = QLabel("128")
        blue_gain_layout.addWidget(self.blue_gain_slider)
        blue_gain_layout.addWidget(self.blue_gain_value_label)
        self.blue_gain_layout_widget = QWidget()
        self.blue_gain_layout_widget.setLayout(blue_gain_layout)
        layout.addWidget(self.blue_gain_layout_widget)

        layout.addStretch()

        # Initialize visibility based on default selections (before querying camera)
        self.on_exposure_mode_changed(self.exposure_combo.currentIndex(), send_command=False)
        self.on_wb_mode_changed(self.wb_combo.currentData(), send_command=False)

        # Don't query settings here - camera not ready yet
        # Settings will be queried after connection is fully established:
        # - For NDI cameras: in on_ndi_connected() after video connects
        # - For IP-only cameras: in _on_visca_test_complete() after connection test

        return widget

    def update_presets_widget(self):
        """Update presets widget"""
        # Clear existing preset widgets
        while self.presets_layout.count() > 0:
            item = self.presets_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add store preset button
        store_button = QPushButton("Store Current Position as Preset")
        store_button.clicked.connect(self.store_preset_dialog)
        self.presets_layout.addWidget(store_button)

        # Load presets from config
        presets = self.config.get_presets(self.camera_id)

        for preset_data in presets:
            preset = CameraPreset.from_dict(preset_data)
            self.add_preset_item(preset)

        # Update auto pan preset dropdowns
        if hasattr(self, 'left_preset_combo'):
            self.update_auto_pan_preset_list()

    def add_preset_item(self, preset: CameraPreset):
        """Add preset item to layout"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        # Reorder buttons
        up_btn = QPushButton("↑")
        up_btn.setFixedSize(24, 24)
        up_btn.setToolTip("Move preset up in list")
        up_btn.clicked.connect(lambda: self.reorder_preset(preset.name, 'up'))
        layout.addWidget(up_btn)

        down_btn = QPushButton("↓")
        down_btn.setFixedSize(24, 24)
        down_btn.setToolTip("Move preset down in list")
        down_btn.clicked.connect(lambda: self.reorder_preset(preset.name, 'down'))
        layout.addWidget(down_btn)

        # Preset name label (double-click to rename)
        label = QLabel(preset.name)
        label.setStyleSheet("padding: 4px; background-color: #333; border-radius: 3px;")
        label.setToolTip("Double-click to rename")
        label.mouseDoubleClickEvent = lambda event: self.rename_preset_dialog(preset.name)
        layout.addWidget(label)
        layout.addStretch()

        # GO button (renamed from Recall)
        go_btn = QPushButton("GO")
        go_btn.setMinimumWidth(40)
        go_btn.setStyleSheet("background-color: #228B22; color: white; font-weight: bold;")
        go_btn.setToolTip("Recall this preset position")
        go_btn.clicked.connect(lambda: self.recall_preset(preset))
        layout.addWidget(go_btn)

        # Update button
        update_btn = QPushButton("Update")
        update_btn.setMinimumWidth(50)
        update_btn.setStyleSheet("background-color: #4169E1; color: white;")
        update_btn.setToolTip("Update preset to current camera position")
        update_btn.clicked.connect(lambda: self.update_preset(preset.name))
        layout.addWidget(update_btn)

        # Delete button
        delete_btn = QPushButton("Delete")
        delete_btn.setMinimumWidth(50)
        delete_btn.setStyleSheet("background-color: #8B0000; color: white;")
        delete_btn.setToolTip("Delete this preset")
        delete_btn.clicked.connect(lambda: self.delete_preset(preset.name))
        layout.addWidget(delete_btn)

        self.presets_layout.addWidget(widget)

    def _test_visca_connection(self):
        """Test VISCA connection for IP-only cameras using background thread"""
        print(f"[Camera] Testing VISCA connection to {self.visca_ip}...")
        
        # Emit connection starting signal
        self.connection_starting.emit()
        
        # Create and start background test thread
        test_thread = ViscaConnectionTestThread(self.visca)
        test_thread.test_complete.connect(self._on_visca_test_complete)
        test_thread.start()
    
    def _on_visca_test_complete(self, success: bool, error_message: str):
        """Handle VISCA connection test completion (called from background thread signal)"""
        try:
            if success:
                self.is_connected = True
                self.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
                self.set_controls_enabled(True)
                self.video_label.setText("IP Control Ready\n(No Video)")
                # Query settings after a short delay to ensure camera is ready
                # Use background thread to prevent UI blocking during slow queries
                QTimer.singleShot(200, self._query_all_settings_async)  # Reduced from 500ms
            else:
                self.is_connected = False
                self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
                self.reconnect_button.setVisible(True)
                self.set_controls_enabled(False)
                error_text = error_message[:50] if error_message else "Connection Failed"
                self.video_label.setText(f"{error_text}\nIP: {self.visca_ip}")
        except Exception as e:
            logger.exception("Connection test handler error")
            self.is_connected = False
            self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
            self.reconnect_button.setVisible(True)
            self.set_controls_enabled(False)
            self.video_label.setText(f"Connection Error\n{str(e)[:50]}")
        
        # Mark as initialized
        self.initialized.emit()
    
    def try_discover_ndi_source(self):
        """Try to discover NDI source matching the VISCA IP address"""
        from videocue.controllers.ndi_video import find_ndi_cameras
        
        # Emit connection starting signal
        self.connection_starting.emit()

        print(f"[Camera] Attempting to discover NDI source for IP {self.visca_ip}")
        cameras = find_ndi_cameras(timeout_ms=5000)

        print(f"[Camera] Found {len(cameras)} NDI sources: {cameras}")

        # Try to find a source containing this IP
        for camera_name in cameras:
            if self.visca_ip in camera_name:
                print(f"[Camera] Matched NDI source: {camera_name}")
                self.ndi_source_name = camera_name
                # Update label with formatted name (avoids redundancy)
                self.name_label.setText(self._format_camera_display_name())

                # Update configuration
                self.config.update_camera_ndi_name(self.camera_id, camera_name)
                self.config.save()

                # Start video
                self.start_video()
                return

        print(f"[Camera] No NDI source found matching IP {self.visca_ip}")
        self.video_label.setText("No NDI source\n(IP control only)")
        
        # Test VISCA connection for IP-only control
        self._test_visca_connection()

    def start_video(self):
        """Start NDI video reception"""
        if self.ndi_thread or not self.ndi_source_name or not ndi_available:
            # Mark as initialized even if we can't start video
            QTimer.singleShot(100, self.initialized.emit)
            return
        
        try:
            # Emit connection starting signal
            self.connection_starting.emit()

            # Get frame_skip preference from config (default 6)
            frame_skip = self.config.config.get('preferences', {}).get('video_frame_skip', 6)
            logger.info(f"[Camera] Starting NDI video with frame_skip={frame_skip} for {self.ndi_source_name}")
            self.ndi_thread = NDIVideoThread(self.ndi_source_name, frame_skip=frame_skip)
            self.ndi_thread.frame_ready.connect(self.on_video_frame)
            self.ndi_thread.connected.connect(self.on_ndi_connected)
            self.ndi_thread.error.connect(self.on_ndi_error)
            self.ndi_thread.resolution_changed.connect(self.on_resolution_changed)
            self.ndi_thread.start()
            
            # Update button state
            if hasattr(self, 'video_toggle_button'):
                self.video_toggle_button.setText("⏸")
                self.video_toggle_button.setToolTip("Stop video streaming")
        except Exception as e:
            import traceback
            error_msg = f"Failed to start NDI video: {str(e)}"
            print(f"\n{error_msg}")
            traceback.print_exc()
            self.video_label.setText(f"Video Error:\n{str(e)}")
            self.initialized.emit()

    def stop_video(self):
        """Stop NDI video reception"""
        if self.ndi_thread:
            self.ndi_thread.stop()
            self.ndi_thread = None
            self.video_label.setText("Video Stopped")
            
        # Update button state
        if hasattr(self, 'video_toggle_button'):
            self.video_toggle_button.setText("▶")
            self.video_toggle_button.setToolTip("Start video streaming")
    
    def toggle_video_streaming(self):
        """Toggle video streaming on/off"""
        if self.ndi_thread:
            self.stop_video()
        else:
            self.start_video()

    @pyqtSlot(QImage)
    def on_video_frame(self, image: QImage):
        """Handle new video frame with throttling"""
        # Throttle to ~30 FPS max (33ms between frames)
        from PyQt6.QtCore import QTime  # type: ignore
        current_time = QTime.currentTime()

        if self._last_frame_time is None:
            self._last_frame_time = current_time

        elapsed = self._last_frame_time.msecsTo(current_time)
        if elapsed < 33:  # Skip frame if less than 33ms elapsed
            return

        self._last_frame_time = current_time

        # Scale to fit video label using FAST transformation
        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.video_width, self.video_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation  # Much faster than SmoothTransformation
        )
        self.video_label.setPixmap(scaled)

    @pyqtSlot(str)
    def on_resolution_changed(self, width: int, height: int, fps: float):
        """Update resolution display when video format changes"""
        # Format: 1920x1080@29.97
        if fps > 0:
            self.resolution_label.setText(f"{width}x{height}@{fps:.2f}fps")
        else:
            self.resolution_label.setText(f"{width}x{height}")
        self.resolution_label.setVisible(True)

    def on_ndi_connected(self, web_url: str):
        """Handle NDI connection established"""
        # Extract IP from web URL if available
        if web_url:
            # Parse URL to extract IP
            import re
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', web_url)
            if match:
                extracted_ip = match.group(1)
                print(f"[Camera] Extracted IP {extracted_ip} from NDI web control URL")
                
                # Update IP address if it was unknown or different
                if self.visca_ip != extracted_ip:
                    self.visca_ip = extracted_ip
                    self.visca = ViscaIP(self.visca_ip, self.visca_port)
                    
                    # Update UI label with formatted name (avoids redundancy)
                    display_text = self._format_camera_display_name()
                    self.name_label.setText(display_text)
                    print(f"[Camera] Updated UI label to: {display_text}")
                    
                    # Save IP to config
                    self.config.update_camera(self.camera_id, visca_ip=self.visca_ip)
                    print(f"[Camera] Saved IP {self.visca_ip} to config")
        
        # Emit initialized signal
        self.initialized.emit()

        # Update status indicator and mark as connected
        self.is_connected = True
        self.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
        self.reconnect_button.setVisible(False)
        self.set_controls_enabled(True)

        # Query all camera settings asynchronously (don't block other cameras from starting)
        QTimer.singleShot(100, self._query_all_settings_async)

    @pyqtSlot(str)
    def on_ndi_error(self, error: str) -> None:
        """Handle NDI error"""
        logger.error(f"NDI error for {self.ndi_source_name}: {error}")
        self.video_label.setText(f"Error: {error}")
        
        # Mark as disconnected and show reconnect button
        self.is_connected = False
        self.status_indicator.setStyleSheet("background-color: red; border-radius: 6px;")
        self.reconnect_button.setVisible(True)
        self.set_controls_enabled(False)
        
        # Emit initialized signal even on error
        self.initialized.emit()

    def move_camera(self, direction: str, speed: float = 0.7):
        """Move camera in specified direction"""
        success = self.visca.move(direction, speed, speed)
        self.update_status_indicator(success)

    def stop_camera(self):
        """Stop camera movement"""
        success = self.visca.stop()
        self.update_status_indicator(success)

    def zoom_camera(self, direction: int):
        """Zoom camera (direction: 1=in, -1=out)"""
        if direction > 0:
            success = self.visca.zoom_in(0.5)
        else:
            success = self.visca.zoom_out(0.5)
        self.update_status_indicator(success)

    def zoom_stop(self):
        """Stop zoom"""
        success = self.visca.zoom_stop()
        self.update_status_indicator(success)

    def on_reset_speed_limit(self):
        """Reset camera pan/tilt speed limit to maximum"""
        success = self.visca.set_pan_tilt_speed_limit(24, 20)  # Max speeds
        self.update_status_indicator(success)
        if success:
            QMessageBox.information(
                self,
                "Speed Limit Reset",
                "Camera speed limit has been reset to maximum.\n\n"
                "Pan/tilt movements should now be at normal speed."
            )

    def query_focus_mode(self):
        """Query and update focus mode"""
        mode = self.visca.query_focus_mode()
        if mode == FocusMode.AUTO:
            self.radio_autofocus.setChecked(True)
        elif mode == FocusMode.MANUAL:
            self.radio_manual_focus.setChecked(True)
        self.update_focus_controls_visibility()

    def _query_all_settings_async(self):
        """Start querying all settings in background thread to prevent UI blocking"""
        from PyQt6.QtCore import QThread
        
        class QueryThread(QThread):
            """Background thread for querying camera settings"""
            finished = pyqtSignal(dict)  # Emits dict of all queried values
            
            def __init__(self, visca, visca_ip):
                super().__init__()
                self.visca = visca
                self.visca_ip = visca_ip
            
            def run(self):
                """Query all settings in background"""
                
                logger.info(f"[QueryThread] Querying all settings for camera {self.visca_ip}...")
                results = {}
                
                try:
                    results['focus_mode'] = self.visca.query_focus_mode()
                    results['exposure_mode'] = self.visca.query_exposure_mode()
                    results['iris'] = self.visca.query_iris()
                    results['shutter'] = self.visca.query_shutter()
                    results['gain'] = self.visca.query_gain()
                    results['brightness'] = self.visca.query_brightness()
                    results['wb_mode'] = self.visca.query_white_balance_mode()
                    results['red_gain'] = self.visca.query_red_gain()
                    results['blue_gain'] = self.visca.query_blue_gain()
                    results['backlight'] = self.visca.query_backlight_comp()
                    logger.info(f"[QueryThread] Finished querying for camera {self.visca_ip}")
                except Exception:
                    logger.exception(f"[QueryThread] Error querying settings for camera {self.visca_ip}")
                
                self.finished.emit(results)
        
        # Show loading indicator
        self.loading_label.setVisible(True)
        
        # Start background thread
        self._query_thread = QueryThread(self.visca, self.visca_ip)
        self._query_thread.finished.connect(self._apply_queried_settings)
        self._query_thread.start()

    def _apply_queried_settings(self, results: dict):
        """Apply queried settings to UI (called on main thread after background query)"""
        from videocue.controllers.visca_ip import ExposureMode, WhiteBalanceMode, FocusMode
        
        logger.info(f"Applying queried settings for camera {self.visca_ip}...")
        
        # Apply focus mode
        if 'focus_mode' in results:
            mode = results['focus_mode']
            if mode == FocusMode.AUTO:
                self.radio_autofocus.setChecked(True)
            elif mode == FocusMode.MANUAL:
                self.radio_manual_focus.setChecked(True)
            self.update_focus_controls_visibility()
        
        # Apply exposure mode
        if 'exposure_mode' in results:
            exp_mode = results['exposure_mode']
            if exp_mode != ExposureMode.UNKNOWN:
                self.exposure_combo.blockSignals(True)
                index = self.exposure_combo.findData(exp_mode.value)
                if index >= 0:
                    self.exposure_combo.setCurrentIndex(index)
                self.exposure_combo.blockSignals(False)
                self.on_exposure_mode_changed(self.exposure_combo.currentIndex(), send_command=False)
        
        # Apply iris
        if 'iris' in results and results['iris'] is not None:
            self.iris_slider.blockSignals(True)
            self.iris_slider.setValue(results['iris'])
            self.iris_slider.blockSignals(False)
            f_stops = ["Closed", "F16", "F14", "F11", "F9.6", "F8", "F6.8", "F5.6",
                       "F4.8", "F4", "F3.4", "F2.8", "F2.4", "F2", "F1.8", "F1.6", "F1.4", "Open"]
            if results['iris'] < len(f_stops):
                self.iris_value_label.setText(f_stops[results['iris']])
        
        # Apply shutter
        if 'shutter' in results and results['shutter'] is not None:
            self.shutter_slider.blockSignals(True)
            self.shutter_slider.setValue(results['shutter'])
            self.shutter_slider.blockSignals(False)
            speeds = ViscaConstants.SHUTTER_SPEEDS[2:]
            if results['shutter'] < len(speeds):
                self.shutter_value_label.setText(speeds[results['shutter']])
        
        # Apply gain
        if 'gain' in results and results['gain'] is not None:
            self.gain_slider.blockSignals(True)
            self.gain_slider.setValue(results['gain'])
            self.gain_slider.blockSignals(False)
            self.gain_value_label.setText(f"{results['gain'] * 3} dB")
        
        # Apply brightness
        if 'brightness' in results and results['brightness'] is not None:
            self.brightness_slider.blockSignals(True)
            self.brightness_slider.setValue(results['brightness'])
            self.brightness_slider.blockSignals(False)
            self.brightness_value_label.setText(str(results['brightness']))
            self.brightness_slider_vertical.blockSignals(True)
            self.brightness_slider_vertical.setValue(results['brightness'])
            self.brightness_slider_vertical.blockSignals(False)
            self.brightness_value_vertical.setText(str(results['brightness']))
        
        # Apply white balance mode
        if 'wb_mode' in results:
            wb_mode = results['wb_mode']
            if wb_mode != WhiteBalanceMode.UNKNOWN:
                self.wb_combo.blockSignals(True)
                index = self.wb_combo.findData(wb_mode.value)
                if index >= 0:
                    self.wb_combo.setCurrentIndex(index)
                self.wb_combo.blockSignals(False)
                self.on_wb_mode_changed(wb_mode.value, send_command=False)
        
        # Apply red gain
        if 'red_gain' in results and results['red_gain'] is not None:
            self.red_gain_slider.blockSignals(True)
            self.red_gain_slider.setValue(results['red_gain'])
            self.red_gain_slider.blockSignals(False)
            self.red_gain_value_label.setText(str(results['red_gain']))
        
        # Apply blue gain
        if 'blue_gain' in results and results['blue_gain'] is not None:
            self.blue_gain_slider.blockSignals(True)
            self.blue_gain_slider.setValue(results['blue_gain'])
            self.blue_gain_slider.blockSignals(False)
            self.blue_gain_value_label.setText(str(results['blue_gain']))
        
        # Apply backlight
        if 'backlight' in results and results['backlight'] is not None:
            self.backlight_checkbox.blockSignals(True)
            self.backlight_checkbox.setChecked(results['backlight'])
            self.backlight_checkbox.blockSignals(False)
        
        logger.info(f"Finished applying settings for camera {self.visca_ip}")
        self.loading_label.setVisible(False)

    def query_all_settings(self):
        """
        Query all camera settings and update UI to match camera state.

        PATTERN FOR ALL PARAMETERS (when adding new UI controls):
        1. Query the value from camera using visca.query_*() method
        2. Block signals on the UI control (prevents triggering set commands)
        3. Update UI control value to match camera
        4. Unblock signals on the UI control
        5. Update any associated label/display text
        6. If the parameter affects visibility of other controls, call the handler
           with send_command=False to update visibility without sending commands

        This ensures:
        - UI always reflects actual camera state on load
        - No unnecessary commands sent to camera during initialization
        - Visibility logic is applied based on queried state
        - Signal blocking prevents command loops
        """
        logger.info(f"Querying all settings for camera {self.visca_ip}...")
        self.loading_label.setVisible(True)

        # Query focus mode
        self.query_focus_mode()

        # Query exposure mode
        from videocue.controllers.visca_ip import ExposureMode
        exp_mode = self.visca.query_exposure_mode()
        logger.debug(f"Exposure mode query returned: {exp_mode}")
        if exp_mode != ExposureMode.UNKNOWN:
            # Block signals to prevent triggering commands while updating
            self.exposure_combo.blockSignals(True)
            index = self.exposure_combo.findData(exp_mode.value)
            if index >= 0:
                self.exposure_combo.setCurrentIndex(index)
                logger.info(f"Set exposure combo to index {index} (mode: {exp_mode.name})")
            else:
                logger.warning(f"Could not find combo index for exposure mode value: {exp_mode.value}")
            self.exposure_combo.blockSignals(False)
            # Manually trigger visibility update without sending command
            self.on_exposure_mode_changed(self.exposure_combo.currentIndex(), send_command=False)
        else:
            logger.warning(f"Exposure mode query returned UNKNOWN for camera {self.visca_ip}")

        # Query iris
        iris_value = self.visca.query_iris()
        if iris_value is not None:
            self.iris_slider.blockSignals(True)
            self.iris_slider.setValue(iris_value)
            self.iris_slider.blockSignals(False)
            # Update label
            f_stops = ["Closed", "F16", "F14", "F11", "F9.6", "F8", "F6.8", "F5.6",
                       "F4.8", "F4", "F3.4", "F2.8", "F2.4", "F2", "F1.8", "F1.6", "F1.4", "Open"]
            if iris_value < len(f_stops):
                self.iris_value_label.setText(f_stops[iris_value])

        # Query shutter
        shutter_value = self.visca.query_shutter()
        if shutter_value is not None:
            self.shutter_slider.blockSignals(True)
            self.shutter_slider.setValue(shutter_value)
            self.shutter_slider.blockSignals(False)
            # Update label using constant list
            speeds = ViscaConstants.SHUTTER_SPEEDS[2:]  # Skip "Auto" and "Manual"
            if shutter_value < len(speeds):
                self.shutter_value_label.setText(speeds[shutter_value])

        # Query gain
        gain_value = self.visca.query_gain()
        if gain_value is not None:
            self.gain_slider.blockSignals(True)
            self.gain_slider.setValue(gain_value)
            self.gain_slider.blockSignals(False)
            self.gain_value_label.setText(f"{gain_value * 3} dB")

        # Query brightness
        brightness_value = self.visca.query_brightness()
        if brightness_value is not None:
            self.brightness_slider.blockSignals(True)
            self.brightness_slider.setValue(brightness_value)
            self.brightness_slider.blockSignals(False)
            self.brightness_value_label.setText(str(brightness_value))
            # Sync vertical slider
            self.brightness_slider_vertical.blockSignals(True)
            self.brightness_slider_vertical.setValue(brightness_value)
            self.brightness_slider_vertical.blockSignals(False)
            self.brightness_value_vertical.setText(str(brightness_value))

        # Query white balance mode
        from videocue.controllers.visca_ip import WhiteBalanceMode
        wb_mode = self.visca.query_white_balance_mode()
        logger.info(f"White balance mode from camera: {wb_mode}, enum value: {wb_mode.value}")
        if wb_mode != WhiteBalanceMode.UNKNOWN:
            self.wb_combo.blockSignals(True)
            index = self.wb_combo.findData(wb_mode.value)
            logger.info(f"Finding combo item with data={wb_mode.value}, found index={index}")
            if index >= 0:
                self.wb_combo.setCurrentIndex(index)
                logger.info(f"Set white balance combo to index {index}")
            else:
                logger.warning(f"Could not find combo index for white balance value: {wb_mode.value}")
            self.wb_combo.blockSignals(False)
            # Manually trigger visibility update without sending command
            self.on_wb_mode_changed(wb_mode.value, send_command=False)

        # Query red gain (for manual WB)
        red_gain_value = self.visca.query_red_gain()
        if red_gain_value is not None:
            self.red_gain_slider.blockSignals(True)
            self.red_gain_slider.setValue(red_gain_value)
            self.red_gain_slider.blockSignals(False)
            self.red_gain_value_label.setText(str(red_gain_value))

        # Query blue gain (for manual WB)
        blue_gain_value = self.visca.query_blue_gain()
        if blue_gain_value is not None:
            self.blue_gain_slider.blockSignals(True)
            self.blue_gain_slider.setValue(blue_gain_value)
            self.blue_gain_slider.blockSignals(False)
            self.blue_gain_value_label.setText(str(blue_gain_value))

        # Query backlight compensation
        backlight_enabled = self.visca.query_backlight_comp()
        if backlight_enabled is not None:
            self.backlight_checkbox.blockSignals(True)
            self.backlight_checkbox.setChecked(backlight_enabled)
            self.backlight_checkbox.blockSignals(False)

        logger.info(f"Finished querying all settings for camera {self.visca_ip}")
        self.loading_label.setVisible(False)

    def on_focus_mode_changed(self):
        """Handle focus mode radio button change"""
        auto = self.radio_autofocus.isChecked()
        success = self.visca.set_autofocus(auto)
        self.update_status_indicator(success)
        self.update_focus_controls_visibility()

    def on_one_push_af(self):
        """Handle one-push autofocus button"""
        success = self.visca.one_push_autofocus()
        self.update_status_indicator(success)

    def update_focus_controls_visibility(self):
        """Show/hide focus controls based on focus mode"""
        is_manual = self.radio_manual_focus.isChecked()
        self.manual_focus_widget.setVisible(is_manual)

    def focus_near(self):
        """Focus near (closer)"""
        success = self.visca.focus_near(0.5)
        self.update_status_indicator(success)

    def focus_far(self):
        """Focus far (farther away)"""
        success = self.visca.focus_far(0.5)
        self.update_status_indicator(success)

    def focus_stop(self):
        """Stop focus movement"""
        success = self.visca.focus_stop()
        self.update_status_indicator(success)

    def update_auto_pan_preset_list(self):
        """Update the preset dropdown lists for auto pan"""
        # Check if auto pan widgets have been created yet
        if not hasattr(self, 'left_preset_combo') or not hasattr(self, 'right_preset_combo'):
            return
        if self.left_preset_combo is None or self.right_preset_combo is None:
            return

        presets = self.config.get_presets(self.camera_id)

        # Get saved selections from config (not from current dropdown text)
        camera_config = self.config.get_camera(self.camera_id)
        left_saved = camera_config.get('auto_pan_left_preset', '')
        right_saved = camera_config.get('auto_pan_right_preset', '')

        # Block signals while updating to prevent saving during initialization
        self.left_preset_combo.blockSignals(True)
        self.right_preset_combo.blockSignals(True)

        # Clear and repopulate
        self.left_preset_combo.clear()
        self.right_preset_combo.clear()

        if not presets:
            self.left_preset_combo.addItem("(No presets available)")
            self.right_preset_combo.addItem("(No presets available)")
            self.left_preset_combo.setEnabled(False)
            self.right_preset_combo.setEnabled(False)
            if hasattr(self, 'start_auto_pan_btn') and self.start_auto_pan_btn is not None:
                self.start_auto_pan_btn.setEnabled(False)
        else:
            for preset_data in presets:
                preset = CameraPreset.from_dict(preset_data)
                self.left_preset_combo.addItem(preset.name)
                self.right_preset_combo.addItem(preset.name)

            self.left_preset_combo.setEnabled(True)
            self.right_preset_combo.setEnabled(True)
            if hasattr(self, 'start_auto_pan_btn') and self.start_auto_pan_btn is not None:
                self.start_auto_pan_btn.setEnabled(True)

            # Restore selections from config file
            if left_saved:
                index = self.left_preset_combo.findText(left_saved)
                if index >= 0:
                    self.left_preset_combo.setCurrentIndex(index)
            # else: left stays at index 0 (first preset) by default

            if right_saved:
                index = self.right_preset_combo.findText(right_saved)
                if index >= 0:
                    self.right_preset_combo.setCurrentIndex(index)
            else:
                # On first load with no saved selection, default right to second preset
                if len(presets) > 1:
                    self.right_preset_combo.setCurrentIndex(1)

        # Unblock signals
        self.left_preset_combo.blockSignals(False)
        self.right_preset_combo.blockSignals(False)

    def on_auto_pan_preset_changed(self):
        """Save auto pan preset selections to config when changed"""
        if not hasattr(self, 'left_preset_combo') or not hasattr(self, 'right_preset_combo'):
            return

        left_preset = self.left_preset_combo.currentText()
        right_preset = self.right_preset_combo.currentText()

        # Skip saving if showing placeholder text
        if left_preset == "(No presets available)" or right_preset == "(No presets available)":
            return

        # Save to config
        self.config.update_camera(self.camera_id,
                                  auto_pan_left_preset=left_preset,
                                  auto_pan_right_preset=right_preset)
        print(f"[AUTO PAN] Saved preset selections: Left='{left_preset}', Right='{right_preset}'")

    def on_start_auto_pan(self):
        """Start preset-based auto pan"""
        left_preset = self.left_preset_combo.currentText()
        right_preset = self.right_preset_combo.currentText()

        if not left_preset or not right_preset or left_preset == "(No presets available)":
            QMessageBox.warning(
                self,
                "No Presets",
                "Please create presets before starting auto pan."
            )
            return

        if left_preset == right_preset:
            QMessageBox.warning(
                self,
                "Same Preset",
                "Please select different presets for left and right positions."
            )
            return

        # Start timer
        delay_seconds = self.auto_pan_speed_slider.value()
        self.auto_pan_timer.start(delay_seconds * 1000)  # Convert to milliseconds

        self.auto_pan_active = True
        self.auto_pan_current_target = "left"
        self.start_auto_pan_btn.setEnabled(False)
        self.stop_auto_pan_btn.setEnabled(True)
        self.auto_pan_status_label.setText("Status: Running")
        self.auto_pan_status_label.setStyleSheet(
            "color: #00ff00; font-style: italic; font-weight: bold;")

        # Immediately go to first position
        self.auto_pan_tick()

    def on_stop_auto_pan(self):
        """Stop preset-based auto pan"""
        self.auto_pan_timer.stop()
        self.auto_pan_active = False
        self.start_auto_pan_btn.setEnabled(True)
        self.stop_auto_pan_btn.setEnabled(False)
        self.auto_pan_status_label.setText("Status: Stopped")
        self.auto_pan_status_label.setStyleSheet("color: #888; font-style: italic;")

    def auto_pan_tick(self):
        """Timer callback for auto pan - alternate between presets"""
        if self.auto_pan_current_target == "left":
            preset_name = self.left_preset_combo.currentText()
            target_label = "LEFT"
            self.auto_pan_current_target = "right"
        else:
            preset_name = self.right_preset_combo.currentText()
            target_label = "RIGHT"
            self.auto_pan_current_target = "left"

        print(f"[AUTO PAN] Going to {target_label} position: '{preset_name}'")

        # Find and recall preset
        presets = self.config.get_presets(self.camera_id)
        for preset_data in presets:
            preset = CameraPreset.from_dict(preset_data)
            if preset.name == preset_name:
                # Use VISCA preset recall (preset numbers 0-254)
                # We'll use the index in the list as the preset number
                preset_index = presets.index(preset_data)
                self.visca.recall_preset_position(preset_index)
                break

    def on_auto_pan_speed_changed(self, value: int):
        """Handle auto pan speed slider change"""
        self.auto_pan_speed_value_label.setText(f"{value}s")

        # If auto pan is running, update timer interval
        if self.auto_pan_active and self.auto_pan_timer.isActive():
            self.auto_pan_timer.setInterval(value * 1000)

    def on_exposure_mode_changed(self, index: int, send_command: bool = True):
        """Handle exposure mode change"""
        _ = index  # Unused - value read from combo box directly
        from videocue.controllers.visca_ip import ExposureMode
        mode = ExposureMode(self.exposure_combo.currentData())

        # Only send command if not loading from camera
        if send_command:
            success = self.visca.set_exposure_mode(mode)
            self.update_status_indicator(success)

        # Show/hide controls based on mode - only show what's relevant
        is_manual = mode == ExposureMode.MANUAL
        is_shutter_priority = mode == ExposureMode.SHUTTER_PRIORITY
        is_iris_priority = mode == ExposureMode.IRIS_PRIORITY
        is_bright = mode == ExposureMode.BRIGHT

        # Iris: visible in Manual and Iris Priority modes
        show_iris = is_manual or is_iris_priority
        self.iris_label.setVisible(show_iris)
        self.iris_layout_widget.setVisible(show_iris)

        # Shutter: visible in Manual and Shutter Priority modes
        show_shutter = is_manual or is_shutter_priority
        self.shutter_label.setVisible(show_shutter)
        self.shutter_layout_widget.setVisible(show_shutter)

        # Gain: visible only in Manual mode
        self.gain_label.setVisible(is_manual)
        self.gain_layout_widget.setVisible(is_manual)

        # Brightness: visible only in Bright mode (both horizontal and vertical)
        self.brightness_label.setVisible(is_bright)
        self.brightness_layout_widget.setVisible(is_bright)
        self.brightness_vertical_container.setVisible(is_bright)

    def on_iris_changed(self, value: int):
        """Handle iris slider change"""
        # Iris values: 0=closed, 17=fully open
        # Display as F-stop approximation
        f_stops = ["Closed", "F16", "F14", "F11", "F9.6", "F8", "F6.8", "F5.6",
                   "F4.8", "F4", "F3.4", "F2.8", "F2.4", "F2", "F1.8", "F1.6", "F1.4", "Open"]
        self.iris_value_label.setText(f_stops[value])
        success = self.visca.set_iris(value)
        self.update_status_indicator(success)

    def on_shutter_changed(self, value: int) -> None:
        """Handle shutter slider change"""
        # Use constant list, skipping "Auto" and "Manual" entries
        speeds = ViscaConstants.SHUTTER_SPEEDS[2:]
        if value < len(speeds):
            self.shutter_value_label.setText(speeds[value])
        else:
            self.shutter_value_label.setText(str(value))
        success = self.visca.set_shutter(value)
        self.update_status_indicator(success)

    def on_gain_changed(self, value: int):
        """Handle gain slider change"""
        self.gain_value_label.setText(f"{value * 3} dB")  # Typical 3dB steps
        success = self.visca.set_gain(value)
        self.update_status_indicator(success)

    def on_brightness_changed(self, value: int):
        """Handle brightness slider change"""
        self.brightness_value_label.setText(str(value))
        # Sync with vertical slider
        if self.brightness_slider_vertical.value() != value:
            self.brightness_slider_vertical.blockSignals(True)
            self.brightness_slider_vertical.setValue(value)
            self.brightness_slider_vertical.blockSignals(False)
            self.brightness_value_vertical.setText(str(value))
        success = self.visca.set_brightness(value)
        self.update_status_indicator(success)

    def on_brightness_vertical_changed(self, value: int):
        """Handle vertical brightness slider change"""
        self.brightness_value_vertical.setText(str(value))
        # Sync with horizontal slider
        if self.brightness_slider.value() != value:
            self.brightness_slider.blockSignals(True)
            self.brightness_slider.setValue(value)
            self.brightness_slider.blockSignals(False)
            self.brightness_value_label.setText(str(value))
        # Show overlay when using vertical slider
        self.show_brightness_overlay()

    def show_brightness_overlay(self):
        """Show brightness value overlay on video display"""
        value = self.brightness_slider.value()
        self.brightness_overlay.setText(f"Brightness: {value}")

        # Position overlay at bottom center of video
        overlay_width = 240
        overlay_height = 60
        x = (self.video_width - overlay_width) // 2
        y = self.video_height - overlay_height - 20
        self.brightness_overlay.setGeometry(x, y, overlay_width, overlay_height)

        self.brightness_overlay.show()
        self.brightness_overlay_timer.start(2000)  # Hide after 2 seconds

    def on_backlight_changed(self, state: int):
        """Handle backlight compensation checkbox"""
        enabled = state == Qt.CheckState.Checked.value
        success = self.visca.set_backlight_comp(enabled)
        self.update_status_indicator(success)

    def on_wb_mode_changed(self, index: int, send_command: bool = True):
        """Handle white balance mode change"""
        _ = index  # Unused - value read from combo box directly
        from videocue.controllers.visca_ip import WhiteBalanceMode
        mode = WhiteBalanceMode(self.wb_combo.currentData())

        # Only send command if not loading from camera
        if send_command:
            success = self.visca.set_white_balance_mode(mode)
            self.update_status_indicator(success)

        # Show/hide manual controls based on mode
        is_manual = mode == WhiteBalanceMode.MANUAL
        self.red_gain_label.setVisible(is_manual)
        self.red_gain_layout_widget.setVisible(is_manual)
        self.blue_gain_label.setVisible(is_manual)
        self.blue_gain_layout_widget.setVisible(is_manual)

        # Show One Push button only in One Push mode
        is_one_push = mode == WhiteBalanceMode.ONE_PUSH
        self.one_push_wb_btn.setVisible(is_one_push)

    def on_one_push_wb(self):
        """Handle one-push white balance button"""
        success = self.visca.one_push_white_balance()
        self.update_status_indicator(success)

    def on_red_gain_changed(self, value: int):
        """Handle red gain slider change"""
        self.red_gain_value_label.setText(str(value))
        success = self.visca.set_red_gain(value)
        self.update_status_indicator(success)

    def on_blue_gain_changed(self, value: int):
        """Handle blue gain slider change"""
        self.blue_gain_value_label.setText(str(value))
        success = self.visca.set_blue_gain(value)
        self.update_status_indicator(success)

    def update_status_indicator(self, success: bool):
        """Update status indicator based on command success"""
        color = "green" if success else "red"
        self.status_indicator.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
        
        # Update connection state
        was_connected = self.is_connected
        self.is_connected = success
        
        # Show reconnect button and disable controls if connection failed
        if not success and was_connected:
            self.reconnect_button.setVisible(True)
            self.set_controls_enabled(False)
        elif success and not was_connected:
            self.reconnect_button.setVisible(False)
            self.set_controls_enabled(True)

    def set_selected(self, selected: bool):
        """Set camera selection state"""
        self.is_selected = selected
        border_color = "orange" if selected else "grey"
        self.video_label.setStyleSheet(
            f"background-color: black; border: 2px solid {border_color};"
        )

    def set_video_size(self, width: int, height: int):
        """Set video display size"""
        self.video_width = width
        self.video_height = height
        self.video_label.setFixedSize(width, height)

        # Set widget width to match video width plus margins/padding
        # Account for layout margins (5px left + 5px right = 10px)
        # and video border (2px left + 2px right = 4px)
        self.setFixedWidth(width + 14)
    
    def set_controls_enabled(self, enabled: bool):
        """Enable or disable camera controls"""
        # Disable/enable all control widgets in the controls container
        if hasattr(self, 'controls_container'):
            for widget in self.controls_container.findChildren(QPushButton):
                widget.setEnabled(enabled)
            for widget in self.controls_container.findChildren(QSlider):
                widget.setEnabled(enabled)
            for widget in self.controls_container.findChildren(QComboBox):
                widget.setEnabled(enabled)
            for widget in self.controls_container.findChildren(QRadioButton):
                widget.setEnabled(enabled)
            for widget in self.controls_container.findChildren(QCheckBox):
                widget.setEnabled(enabled)
    
    def reconnect_camera(self):
        """Attempt to reconnect to camera (non-blocking)"""
        try:
            print(f"[Camera] Attempting to reconnect to {self.visca_ip}...")
            
            # Hide reconnect button and show loading indicator
            self.reconnect_button.setVisible(False)
            self.loading_label.setVisible(True)
            
            # Reconnect immediately on next event loop iteration
            QTimer.singleShot(50, self._cleanup_and_reconnect)
        except Exception as e:
            import traceback
            print(f"[Camera] Error in reconnect_camera: {e}")
            traceback.print_exc()
            self.loading_label.setVisible(False)
            self.reconnect_button.setVisible(True)
            self.video_label.setText(f"Reconnect Error:\\n{str(e)[:50]}")
    
    def _wait_for_thread_stop(self):
        """Poll for thread to finish without blocking UI"""
        if self.ndi_thread and self.ndi_thread.isRunning():
            # Thread still running, check again in 100ms
            print("[Camera] Waiting for thread to stop...")
            QTimer.singleShot(100, self._wait_for_thread_stop)
        else:
            # Thread stopped, proceed with reconnection
            print("[Camera] Thread stopped, proceeding with reconnection")
            self._cleanup_and_reconnect()
    
    def _cleanup_and_reconnect(self):
        """Clean up old thread and attempt reconnection"""
        # Ensure thread is fully stopped
        if self.ndi_thread:
            self.ndi_thread = None
        
        # Try to reconnect
        if self.ndi_source_name and ndi_available:
            # For NDI cameras, refresh cache in background then reconnect
            self._refresh_cache_and_reconnect()
        else:
            # Just test VISCA connection
            self._attempt_visca_reconnect()
    
    def _refresh_cache_and_reconnect(self):
        """Refresh NDI cache in background thread, then reconnect"""
        try:
            # Import here to avoid circular dependency
            from videocue.controllers.ndi_video import discover_and_cache_all_sources
            from PyQt6.QtCore import QThread
            
            # Create a worker thread to refresh the cache
            class CacheRefreshThread(QThread):
                def run(self):
                    try:
                        discover_and_cache_all_sources()
                    except Exception as e:
                        print(f"[Camera] Cache refresh error: {e}")
            
            self.cache_refresh_thread = CacheRefreshThread()
            self.cache_refresh_thread.finished.connect(self._attempt_video_reconnect)
            self.cache_refresh_thread.start()
        except Exception as e:
            import traceback
            print(f"[Camera] Error starting cache refresh: {e}")
            traceback.print_exc()
            # Fall back to direct reconnect
            self._attempt_video_reconnect()
    
    def _attempt_video_reconnect(self):
        """Attempt to reconnect video stream"""
        try:
            self.loading_label.setVisible(False)
            self.start_video()
        except Exception as e:
            import traceback
            print(f"[Camera] Error in video reconnect: {e}")
            traceback.print_exc()
            self.reconnect_button.setVisible(True)
            self.video_label.setText(f"Video Reconnect Failed:\\n{str(e)[:50]}")
    
    def _attempt_visca_reconnect(self):
        """Attempt to reconnect VISCA control"""
        try:
            # Use background thread to avoid blocking UI and other cameras
            self.connection_test_thread = ViscaConnectionTestThread(self.visca)
            self.connection_test_thread.test_complete.connect(self._on_visca_reconnect_complete)
            self.connection_test_thread.start()
        except Exception as e:
            import traceback
            print(f"[Camera] Error starting VISCA reconnect: {e}")
            traceback.print_exc()
            self.loading_label.setVisible(False)
            self.reconnect_button.setVisible(True)
            self.video_label.setText(f"VISCA Reconnect Failed:\n{str(e)[:50]}")
    
    def _on_visca_reconnect_complete(self, success: bool, error_message: str):
        """Handle VISCA reconnection test result"""
        try:
            self.loading_label.setVisible(False)
            
            if success:
                self.is_connected = True
                self.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
                self.set_controls_enabled(True)
                # Don't query all settings on reconnect - it blocks UI
                print(f"[Camera] Reconnected to {self.visca_ip}")
            else:
                # Reconnect failed, show button again
                self.is_connected = False
                self.reconnect_button.setVisible(True)
                self.video_label.setText("Reconnection failed\nClick Reconnect to retry")
        except Exception as e:
            import traceback
            print(f"[Camera] Error handling VISCA reconnect result: {e}")
            traceback.print_exc()
            self.reconnect_button.setVisible(True)
    
    def _retry_connection(self) -> None:
        """Retry connection with exponential backoff"""
        self._retry_timer.stop()
        
        if self._retry_count >= self._max_retries:
            logger.warning(f"Max retries ({self._max_retries}) reached for {self.visca_ip}")
            self._retry_count = 0
            self.reconnect_button.setVisible(True)
            return
        
        self._retry_count += 1
        delay_seconds = 2 ** self._retry_count  # Exponential backoff: 2, 4, 8 seconds
        
        logger.info(f"Retrying connection to {self.visca_ip} (attempt {self._retry_count}/{self._max_retries}) in {delay_seconds}s")
        self._retry_timer.start(delay_seconds * 1000)
        
        # Attempt reconnection
        QTimer.singleShot(100, self.reconnect_camera)
    
    def start_retry_mechanism(self) -> None:
        """Start automatic retry mechanism for failed connections"""
        if self.is_connected:
            return
        
        self._retry_count = 0
        logger.info(f"Starting retry mechanism for {self.visca_ip}")
        QTimer.singleShot(2000, self._retry_connection)  # Start after 2 seconds
    
    def stop_retry_mechanism(self) -> None:
        """Stop automatic retry mechanism"""
        self._retry_timer.stop()
        self._retry_count = 0

    def open_web_browser(self):
        """Open camera web interface"""
        import webbrowser
        url = f"http://{self.visca_ip}/"
        webbrowser.open(url)

    def store_preset_dialog(self):
        """Show dialog to store current position as preset"""
        name, ok = QInputDialog.getText(
            self,
            "Store Preset",
            "Enter preset name:"
        )

        if ok and name:
            # Get next preset number (use index in list)
            presets = self.config.get_presets(self.camera_id)
            preset_number = len(presets)  # Next available slot

            # Store preset in camera memory using VISCA
            success = self.visca.store_preset_position(preset_number)

            if success:
                # Store preset info in config (with placeholder PTZ values)
                self.config.add_preset(self.camera_id, name, 0, 0, 0)
                self.update_presets_widget()

                QMessageBox.information(
                    self,
                    "Preset Stored",
                    f"Preset '{name}' has been stored to camera memory.\n\n"
                    f"Preset number: {preset_number}\n\n"
                    "The camera will recall this exact position when selected."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Preset Storage Failed",
                    "Failed to store preset in camera memory.\n\n"
                    "Please check camera connection."
                )

    def recall_preset(self, preset: CameraPreset):
        """Recall preset position"""
        # Find preset index (which corresponds to camera memory slot)
        presets = self.config.get_presets(self.camera_id)
        preset_index = None

        for i, preset_data in enumerate(presets):
            p = CameraPreset.from_dict(preset_data)
            if p.name == preset.name:
                preset_index = i
                break

        if preset_index is not None:
            success = self.visca.recall_preset_position(preset_index)
            self.update_status_indicator(success)
            if not success:
                QMessageBox.warning(
                    self,
                    "Recall Failed",
                    f"Failed to recall preset '{preset.name}'.\n\n"
                    "The preset may not be stored in camera memory."
                )

    def delete_preset(self, name: str):
        """Delete preset"""
        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete preset '{name}'?\n\n"
            "Note: This removes the preset from the app, but the \n"
            "position remains stored in camera memory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.config.remove_preset(self.camera_id, name)
            self.update_presets_widget()

    def rename_preset_dialog(self, old_name: str):
        """Show dialog to rename a preset"""
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Preset",
            "Enter new preset name:",
            text=old_name
        )

        if ok and new_name and new_name != old_name:
            # Check if name already exists
            presets = self.config.get_presets(self.camera_id)
            existing_names = [CameraPreset.from_dict(p).name for p in presets]

            if new_name in existing_names:
                QMessageBox.warning(
                    self,
                    "Name Exists",
                    f"A preset named '{new_name}' already exists.\n\n"
                    "Please choose a different name."
                )
                return

            # Update the preset name
            success = self.config.update_preset_name(self.camera_id, old_name, new_name)

            if success:
                self.update_presets_widget()
            else:
                QMessageBox.warning(
                    self,
                    "Rename Failed",
                    f"Failed to rename preset '{old_name}'."
                )

    def update_preset(self, name: str):
        """Update preset to current camera position"""
        # Find preset index (camera memory slot)
        presets = self.config.get_presets(self.camera_id)
        preset_index = None

        for i, preset_data in enumerate(presets):
            p = CameraPreset.from_dict(preset_data)
            if p.name == name:
                preset_index = i
                break

        if preset_index is not None:
            # Store current position to camera memory at the same slot
            success = self.visca.store_preset_position(preset_index)

            if success:
                # Update config (keep placeholder values since we can't query position)
                self.config.update_preset(self.camera_id, name, 0, 0, 0)

                QMessageBox.information(
                    self,
                    "Preset Updated",
                    f"Preset '{name}' has been updated to the current camera position.\n\n"
                    f"Preset slot: {preset_index}"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Update Failed",
                    f"Failed to update preset '{name}' in camera memory.\n\n"
                    "Please check camera connection."
                )

    def reorder_preset(self, name: str, direction: str):
        """Reorder preset in the list"""
        success = self.config.reorder_preset(self.camera_id, name, direction)

        if success:
            # Need to re-store all presets to camera memory in new order
            # since preset number = list index
            presets = self.config.get_presets(self.camera_id)

            reply = QMessageBox.question(
                self,
                "Re-store Presets?",
                f"Preset '{name}' has been moved {direction}.\n\n"
                "The preset order has changed, which means preset slot numbers \n"
                "in camera memory need to be updated.\n\n"
                "Would you like to re-store all presets to camera memory now?\n\n"
                "(You'll need to position the camera at each preset location)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Show instructions for re-storing
                preset_names = [CameraPreset.from_dict(p).name for p in presets]
                msg = "Please re-store each preset in order:\n\n"
                for i, pname in enumerate(preset_names):
                    msg += f"{i+1}. {pname}\n"
                msg += "\nPosition the camera and click 'Update' for each preset."

                QMessageBox.information(
                    self,
                    "Re-store Instructions",
                    msg
                )

            # Refresh the widget to show new order
            self.update_presets_widget()

    # USB controller handlers
    def handle_usb_movement(self, direction: MovementDirection, speed: float):
        """Handle USB controller movement"""
        if not self.is_selected:
            return

        direction_map = {
            MovementDirection.UP: Direction.UP,
            MovementDirection.DOWN: Direction.DOWN,
            MovementDirection.LEFT: Direction.LEFT,
            MovementDirection.RIGHT: Direction.RIGHT,
            MovementDirection.UP_LEFT: Direction.UP_LEFT,
            MovementDirection.UP_RIGHT: Direction.UP_RIGHT,
            MovementDirection.DOWN_LEFT: Direction.DOWN_LEFT,
            MovementDirection.DOWN_RIGHT: Direction.DOWN_RIGHT,
            MovementDirection.STOP: Direction.STOP,
        }

        visca_dir = direction_map.get(direction)
        if visca_dir == Direction.STOP:
            self.stop_camera()
        elif visca_dir:
            self.move_camera(visca_dir, speed)

    def handle_usb_zoom_in(self, speed: float):
        """Handle USB zoom in"""
        if not self.is_selected:
            return
        self.visca.zoom_in(speed)

    def handle_usb_zoom_out(self, speed: float):
        """Handle USB zoom out"""
        if not self.is_selected:
            return
        self.visca.zoom_out(speed)

    def handle_usb_zoom_stop(self):
        """Handle USB zoom stop"""
        if not self.is_selected:
            return
        self.zoom_stop()

    def handle_usb_brightness_increase(self):
        """Handle USB brightness increase (only in Bright mode)"""
        if not self.is_selected:
            return

        # Only work in Bright mode
        from videocue.controllers.visca_ip import ExposureMode
        current_mode = ExposureMode(self.exposure_combo.currentData())
        if current_mode != ExposureMode.BRIGHT:
            return

        # Get brightness step from config
        usb_config = self.config.get_usb_controller_config()
        brightness_step = usb_config.get("brightness_step", 1)

        # Increase brightness by step (0-41 range)
        current_value = self.brightness_slider.value()
        new_value = min(current_value + brightness_step, 41)
        if new_value != current_value:
            self.brightness_slider.setValue(new_value)

    def handle_usb_brightness_decrease(self):
        """Handle USB brightness decrease (only in Bright mode)"""
        if not self.is_selected:
            return

        # Only work in Bright mode
        from videocue.controllers.visca_ip import ExposureMode
        current_mode = ExposureMode(self.exposure_combo.currentData())
        if current_mode != ExposureMode.BRIGHT:
            return

        # Get brightness step from config
        usb_config = self.config.get_usb_controller_config()
        brightness_step = usb_config.get("brightness_step", 1)

        # Decrease brightness by step (0-41 range)
        current_value = self.brightness_slider.value()
        new_value = max(current_value - brightness_step, 0)
        if new_value != current_value:
            self.brightness_slider.setValue(new_value)
