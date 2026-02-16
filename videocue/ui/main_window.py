"""
Main application window
"""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSlot  # type: ignore
from PyQt6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon  # type: ignore
from PyQt6.QtWidgets import (  # type: ignore
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from videocue import __version__
from videocue.constants import UIConstants
from videocue.controllers.ndi_video import cleanup_ndi, get_ndi_error_message, ndi_available
from videocue.controllers.usb_controller import MovementDirection, USBController
from videocue.models.config_manager import ConfigManager
from videocue.models.video import VideoSize
from videocue.ui.about_dialog import AboutDialog
from videocue.ui.camera_add_dialog import CameraAddDialog
from videocue.ui.camera_widget import CameraWidget
from videocue.ui.update_check_thread import UpdateCheckThread
from videocue.ui_strings import UIStrings
from videocue.utils import resource_path

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Set window icon
        icon_path = resource_path("resources/icon.png")
        if Path(icon_path).exists():
            self.setWindowIcon(QIcon(icon_path))

        # Configuration manager
        self.config = ConfigManager()

        # Camera widgets list
        self.cameras = []
        self.selected_camera_index = 0

        # USB controller
        self.usb_controller = None

        # Pre-initialize UI attributes
        self.usb_icon_label = None
        self.cameras_container = None
        self.cameras_layout = None
        self.loading_label = None
        self.loading_progress = None
        self.preferences_dialog = None
        self._preferences_dialog_open = False
        self._total_cameras_to_load = 0
        self._cameras_initialized = 0
        self._current_progress_step = 0
        self._total_progress_steps = 0

        # USB controller signal handlers (stored for connect/disconnect)
        self._usb_signal_handlers = {}

        # Update check thread (stored to prevent garbage collection)
        self._update_check_thread = None
        self._update_progress_dialog = None

        # Setup UI
        self.init_ui()

        # Initialize USB controller
        self.init_usb_controller()

        # Defer camera loading until after window is shown
        self._cameras_loaded = False

        # Show NDI error if library not available and user hasn't disabled NDI video in preferences
        if not ndi_available and self.config.get_ndi_video_enabled():
            QMessageBox.warning(
                self, "NDI Not Available", get_ndi_error_message(), QMessageBox.StandardButton.Ok
            )

    def init_ui(self) -> None:
        """Initialize user interface"""
        self.setWindowTitle(UIStrings.APP_NAME)
        self.setGeometry(
            UIConstants.WINDOW_DEFAULT_X,
            UIConstants.WINDOW_DEFAULT_Y,
            UIConstants.WINDOW_DEFAULT_WIDTH,
            UIConstants.WINDOW_DEFAULT_HEIGHT,
        )
        logger.info("Initializing main window UI")

        # Create menu bar
        self.create_menu_bar()

        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Cameras tab
        self.cameras_tab = self.create_cameras_tab()
        self.tab_widget.addTab(self.cameras_tab, UIStrings.TAB_CAMERAS)

    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        preferences_action = QAction("Preferences", self)
        preferences_action.triggered.connect(self.show_controller_preferences)
        edit_menu.addAction(preferences_action)

        # Logging preferences
        edit_menu.addSeparator()
        file_logging_action = QAction(UIStrings.MENU_FILE_LOGGING, self)
        file_logging_action.setCheckable(True)
        file_logging_action.setChecked(
            self.config.config.get("preferences", {}).get("file_logging_enabled", False)
        )
        file_logging_action.triggered.connect(self.on_file_logging_toggled)
        edit_menu.addAction(file_logging_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Video size submenu
        video_size_menu = QMenu("Video Size", self)
        view_menu.addMenu(video_size_menu)

        # Create radio group for video sizes
        size_group = QActionGroup(self)
        size_group.setExclusive(True)

        default_size = self.config.get_default_video_size()

        for size in VideoSize.presets():
            action = QAction(str(size), self)
            action.setCheckable(True)
            action.setData(size)

            # Check if this is the default size
            if size.width == default_size[0] and size.height == default_size[1]:
                action.setChecked(True)

            action.triggered.connect(lambda checked, s=size: self.on_video_size_changed(s))
            size_group.addAction(action)
            video_size_menu.addAction(action)

        # Performance submenu
        performance_menu = QMenu("Video Performance", self)
        view_menu.addMenu(performance_menu)

        # Create radio group for frame rates
        framerate_group = QActionGroup(self)
        framerate_group.setExclusive(True)

        current_skip = self.config.get_video_frame_skip()

        # Frame skip options: (skip_value, label, description)
        # Lower skip = more frames processed = better quality but slower
        # Higher skip = fewer frames processed = worse quality but faster
        framerate_options = [
            (20, "Maximum Performance", "Fastest - ~3 FPS (skips most frames)"),
            (8, "High Performance", "Very fast - ~7.5 FPS"),
            (6, "Balanced", "Good balance - ~10 FPS (recommended)"),
            (4, "Good Quality", "Better quality - ~15 FPS"),
            (2, "Best Quality", "Highest quality - ~30 FPS (may lag)"),
        ]

        for skip_value, label, tooltip in framerate_options:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.setData(skip_value)

            if skip_value == current_skip:
                action.setChecked(True)

            action.triggered.connect(
                lambda checked, skip=skip_value: self.on_frame_rate_changed(skip)
            )
            framerate_group.addAction(action)
            performance_menu.addAction(action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        check_updates_action = QAction(UIStrings.MENU_CHECK_UPDATES, self)
        check_updates_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_updates_action)

        help_menu.addSeparator()

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_cameras_tab(self):
        """Create cameras tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Top toolbar
        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)

        # USB controller status indicator with icon
        from PyQt6.QtWidgets import QLabel

        self.usb_icon_label = QLabel()
        self.usb_icon_label.setFixedSize(28, 28)
        self.usb_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.usb_icon_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.usb_icon_label.mousePressEvent = lambda event: self.show_controller_preferences()  # type: ignore
        self.usb_icon_label.setToolTip("Controller Settings")

        toolbar.addWidget(self.usb_icon_label)

        # Update icon based on connection status
        self._update_usb_indicator(False)

        toolbar.addStretch()

        # Loading indicator
        from PyQt6.QtWidgets import QProgressBar

        self.loading_label = QLabel("")
        self.loading_label.setVisible(False)
        toolbar.addWidget(self.loading_label)

        self.loading_progress = QProgressBar()
        self.loading_progress.setMaximumWidth(200)
        self.loading_progress.setTextVisible(True)
        self.loading_progress.setVisible(False)
        toolbar.addWidget(self.loading_progress)

        # Add camera button
        from PyQt6.QtWidgets import QPushButton  # type: ignore

        add_button = QPushButton("Add Camera")
        add_button.clicked.connect(self.add_camera_dialog)
        toolbar.addWidget(add_button)

        # Scroll area for cameras
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        # Container for camera widgets
        self.cameras_container = QWidget()
        self.cameras_layout = QHBoxLayout(self.cameras_container)
        self.cameras_layout.setSpacing(10)
        self.cameras_layout.setContentsMargins(5, 5, 5, 5)
        self.cameras_layout.addStretch()

        scroll.setWidget(self.cameras_container)

        return widget

    def init_usb_controller(self):
        """Initialize USB controller"""
        try:
            self.usb_controller = USBController(self.config)

            # Store signal handlers for connect/disconnect when dialog opens/closes
            # We don't disconnect 'connected' and 'disconnected' as they don't affect cameras
            self._usb_signal_handlers["prev_camera"] = lambda: self.select_camera(-1)
            self._usb_signal_handlers["next_camera"] = lambda: self.select_camera(1)
            self._usb_signal_handlers["movement_direction"] = self.on_usb_movement
            self._usb_signal_handlers["zoom_in"] = self.on_usb_zoom_in
            self._usb_signal_handlers["zoom_out"] = self.on_usb_zoom_out
            self._usb_signal_handlers["zoom_stop"] = self.on_usb_zoom_stop
            self._usb_signal_handlers["stop_movement"] = self.on_usb_stop_movement
            self._usb_signal_handlers["brightness_increase"] = self.on_usb_brightness_increase
            self._usb_signal_handlers["brightness_decrease"] = self.on_usb_brightness_decrease
            self._usb_signal_handlers["focus_one_push"] = self.on_usb_focus_one_push
            self._usb_signal_handlers["button_a_pressed"] = lambda: None  # Placeholder for dialog

            # Connect signals
            self.usb_controller.connected.connect(self.on_usb_connected)
            self.usb_controller.disconnected.connect(self.on_usb_disconnected)
            self.usb_controller.prev_camera.connect(self._usb_signal_handlers["prev_camera"])
            self.usb_controller.next_camera.connect(self._usb_signal_handlers["next_camera"])
            self.usb_controller.movement_direction.connect(
                self._usb_signal_handlers["movement_direction"]
            )
            self.usb_controller.zoom_in.connect(self._usb_signal_handlers["zoom_in"])
            self.usb_controller.zoom_out.connect(self._usb_signal_handlers["zoom_out"])
            self.usb_controller.zoom_stop.connect(self._usb_signal_handlers["zoom_stop"])
            self.usb_controller.stop_movement.connect(self._usb_signal_handlers["stop_movement"])
            self.usb_controller.brightness_increase.connect(
                self._usb_signal_handlers["brightness_increase"]
            )
            self.usb_controller.brightness_decrease.connect(
                self._usb_signal_handlers["brightness_decrease"]
            )
            self.usb_controller.focus_one_push.connect(self._usb_signal_handlers["focus_one_push"])
            self.usb_controller.menu_button_pressed.connect(self.show_controller_preferences)
            # Note: button_a_pressed is only used by preferences dialog and not connected here

            # Update UI to reflect current connection state
            if self.usb_controller.joystick is not None:
                name = self.usb_controller.joystick.get_name()
                self._update_usb_indicator(True, name)

        except (ImportError, RuntimeError, OSError) as e:
            logger.error(f"USB controller initialization error: {e}")

    def showEvent(self, event):
        """Override showEvent to load cameras after UI is visible"""
        try:
            super().showEvent(event)

            # Load cameras only once, after window is shown
            if not self._cameras_loaded:
                self._cameras_loaded = True

                # Show loading indicator immediately
                camera_configs = self.config.get_cameras()
                if len(camera_configs) > 0:
                    self._total_cameras_to_load = len(camera_configs)
                    self._cameras_initialized = 0
                    self._current_progress_step = 0
                    # Use 3 steps per camera for more granular progress
                    self._total_progress_steps = self._total_cameras_to_load * 3
                    self.loading_label.setText(
                        f"Preparing to load {self._total_cameras_to_load} camera(s)..."
                    )
                    self.loading_label.setVisible(True)
                    self.loading_progress.setRange(0, self._total_progress_steps)
                    self.loading_progress.setValue(0)
                    self.loading_progress.setVisible(True)

                # Use timer to ensure UI is fully rendered before loading cameras
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(100, self.load_cameras)
        except Exception as e:
            logger.exception("CRITICAL ERROR in showEvent")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Startup Error", f"Error during window show:\n{str(e)}")

    def load_cameras(self):
        """Load cameras from configuration"""
        try:
            camera_configs = self.config.get_cameras()

            # Pre-discover all NDI sources once before creating camera widgets
            # This prevents each camera from doing its own 2-second discovery wait
            if camera_configs:
                from videocue.controllers.ndi_video import (
                    discover_and_cache_all_sources,
                    ndi_available,
                )

                if ndi_available:
                    logger.info("[Startup] Pre-discovering all NDI sources...")
                    num_sources = discover_and_cache_all_sources(timeout_ms=2000)
                    logger.info(f"[Startup] Cached {num_sources} NDI source(s)")

            # Load cameras with minimal video stagger to prevent NDI connection contention
            # Widget loads immediately but video starts with 50ms offset per camera
            for i, cam_config in enumerate(camera_configs, 1):
                cam_config["_init_delay"] = (
                    i - 1
                ) * 50  # First camera: 0ms, second: 50ms, third: 100ms, etc.
                self.add_camera_from_config(cam_config)
        except Exception as e:
            logger.exception("CRITICAL ERROR in load_cameras")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Camera Load Error", f"Error loading cameras:\n{str(e)}")

    def add_camera_from_config(self, cam_config: dict):
        """Add camera widget from configuration"""
        camera_num = len(self.cameras) + 1

        try:
            # Step 1: Creating widget
            self._update_loading_progress(
                f"Creating camera {camera_num}/{self._total_cameras_to_load}..."
            )

            # Get staggered init delay (set by load_cameras)
            init_delay = cam_config.get("_init_delay", 100)

            # Get video size from camera config
            video_size = cam_config.get(
                "video_size", [UIConstants.VIDEO_DEFAULT_WIDTH, UIConstants.VIDEO_DEFAULT_HEIGHT]
            )

            camera = CameraWidget(
                camera_id=cam_config["id"],
                ndi_source_name=cam_config.get("ndi_source_name", ""),
                visca_ip=cam_config["visca_ip"],
                visca_port=cam_config["visca_port"],
                config=self.config,
                init_delay=init_delay,
                video_size=video_size,
            )

            # Step 2: Configuring
            self._update_loading_progress(
                f"Configuring camera {camera_num}/{self._total_cameras_to_load}..."
            )

            # Connect delete signal
            camera.delete_requested.connect(lambda: self.remove_camera(camera))

            # Connect reorder signals
            camera.move_left_requested.connect(lambda cam=camera: self.move_camera_left(cam))
            camera.move_right_requested.connect(lambda cam=camera: self.move_camera_right(cam))

            # Connect initialization signals to track progress
            camera.connection_starting.connect(
                lambda: self._update_loading_progress(
                    f"Connecting to camera {camera_num}/{self._total_cameras_to_load}..."
                )
            )
            camera.initialized.connect(self.on_camera_initialized)

            # Add to layout (before stretch)
            self.cameras_layout.insertWidget(len(self.cameras), camera)
            self.cameras.append(camera)

            # Select first camera
            if len(self.cameras) == 1:
                self.select_camera_at_index(0)

        except Exception as e:
            error_msg = f"Failed to load camera {camera_num}:\n{str(e)}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.warning(self, "Camera Load Error", error_msg, QMessageBox.StandardButton.Ok)
            # Still increment initialized count so progress completes
            self.on_camera_initialized()

    def _update_loading_progress(self, message: str) -> None:
        """Update loading progress bar and message"""
        self._current_progress_step += 1
        self.loading_progress.setValue(self._current_progress_step)
        self.loading_label.setText(message)

    def on_camera_initialized(self):
        """Handle camera initialization completion"""
        try:
            self._cameras_initialized += 1
            self._update_loading_progress(
                f"Camera {self._cameras_initialized}/{self._total_cameras_to_load} ready"
            )

            # Hide progress when all cameras loaded
            if self._cameras_initialized >= self._total_cameras_to_load:
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(500, self._hide_loading_indicator)
        except Exception as e:
            logger.exception("ERROR in on_camera_initialized")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Camera Initialization Error",
                f"Error during camera initialization:\n{str(e)}",
            )

    def _hide_loading_indicator(self):
        """Hide the loading indicator"""
        try:
            logger.debug("Hiding loading indicator...")
            self.loading_label.setVisible(False)
            self.loading_progress.setVisible(False)
            logger.debug("Loading indicator hidden successfully")
        except Exception:
            logger.exception("ERROR hiding loading indicator")

    def add_camera_dialog(self):
        """Show add camera dialog"""
        # Get list of existing cameras to pass to dialog
        existing_cameras = self.config.get_cameras()
        dialog = CameraAddDialog(self, existing_cameras=existing_cameras)

        if dialog.exec():
            # Get selected cameras
            ndi_cameras = dialog.get_selected_ndi_cameras()
            ip_address = dialog.get_ip_address()

            # Count how many cameras we're adding
            cameras_to_add = len(ndi_cameras) + (1 if ip_address else 0)

            if cameras_to_add > 0:
                # Show loading progress bar
                self._total_cameras_to_load = len(self.cameras) + cameras_to_add
                self._cameras_initialized = len(self.cameras)  # Already loaded cameras
                self._current_progress_step = len(self.cameras) * 3  # 3 steps per camera
                self._total_progress_steps = self._total_cameras_to_load * 3
                self.loading_label.setText(f"Adding {cameras_to_add} camera(s)...")
                self.loading_label.setVisible(True)
                self.loading_progress.setRange(0, self._total_progress_steps)
                self.loading_progress.setValue(self._current_progress_step)
                self.loading_progress.setVisible(True)

            # Add NDI cameras
            for ndi_name in ndi_cameras:
                # Try to match existing config or extract IP from NDI name
                existing = self.config.get_camera_by_ndi_name(ndi_name)

                if existing:
                    # Already configured, reload
                    self.add_camera_from_config(existing)
                else:
                    # New camera - extract IP from NDI name
                    visca_ip = self.extract_ip_from_ndi_name(ndi_name)

                    # Add to config
                    camera_id = self.config.add_camera(ndi_source_name=ndi_name, visca_ip=visca_ip)

                    # Get config and add widget
                    cam_config = self.config.get_camera(camera_id)
                    if cam_config:
                        self.add_camera_from_config(cam_config)

            # Add IP-only camera
            if ip_address:
                camera_id = self.config.add_camera(ndi_source_name="", visca_ip=ip_address)

                cam_config = self.config.get_camera(camera_id)
                if cam_config:
                    self.add_camera_from_config(cam_config)

    def extract_ip_from_ndi_name(self, ndi_name: str) -> str:
        """Extract IP address from NDI source name (format: 'Name (IP)')"""
        if "(" in ndi_name and ")" in ndi_name:
            start = ndi_name.index("(") + 1
            end = ndi_name.index(")")
            return ndi_name[start:end].strip()
        return "192.168.1.100"  # Default

    def remove_camera(self, camera: "CameraWidget"):
        """Remove camera widget with confirmation"""
        # Show confirmation dialog
        from PyQt6.QtWidgets import QMessageBox

        camera_name = camera.ndi_source_name if camera.ndi_source_name else camera.visca_ip
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete camera:\n{camera_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if camera in self.cameras:
            # Stop video
            camera.stop_video()

            # Remove from config
            self.config.remove_camera(camera.camera_id)

            # Remove from layout and list
            self.cameras_layout.removeWidget(camera)
            self.cameras.remove(camera)
            camera.deleteLater()

            # Reselect camera if needed
            if len(self.cameras) > 0:
                self.selected_camera_index = min(self.selected_camera_index, len(self.cameras) - 1)
                self.select_camera_at_index(self.selected_camera_index)

    def move_camera_left(self, camera: "CameraWidget"):
        """Move camera one position to the left"""
        if camera not in self.cameras:
            return

        index = self.cameras.index(camera)
        if index > 0:
            # Swap in list
            self.cameras[index], self.cameras[index - 1] = (
                self.cameras[index - 1],
                self.cameras[index],
            )

            # Update layout
            self._rebuild_camera_layout()

            # Update config order
            self._save_camera_order()

            # Update selection index if needed
            if self.selected_camera_index == index:
                self.selected_camera_index = index - 1
            elif self.selected_camera_index == index - 1:
                self.selected_camera_index = index

    def move_camera_right(self, camera: "CameraWidget"):
        """Move camera one position to the right"""
        if camera not in self.cameras:
            return

        index = self.cameras.index(camera)
        if index < len(self.cameras) - 1:
            # Swap in list
            self.cameras[index], self.cameras[index + 1] = (
                self.cameras[index + 1],
                self.cameras[index],
            )

            # Update layout
            self._rebuild_camera_layout()

            # Update config order
            self._save_camera_order()

            # Update selection index if needed
            if self.selected_camera_index == index:
                self.selected_camera_index = index + 1
            elif self.selected_camera_index == index + 1:
                self.selected_camera_index = index

    def _rebuild_camera_layout(self):
        """Rebuild the camera layout to reflect current order"""
        # Remove all cameras from layout
        for camera in self.cameras:
            self.cameras_layout.removeWidget(camera)

        # Re-add in current order (before the stretch)
        for i, camera in enumerate(self.cameras):
            self.cameras_layout.insertWidget(i, camera)

    def _save_camera_order(self):
        """Save the current camera order to config"""
        # Reorder cameras in config to match current order
        camera_ids = [camera.camera_id for camera in self.cameras]
        self.config.reorder_cameras(camera_ids)
        self.config.save()

    def select_camera(self, offset: int):
        """Select camera by offset from current"""
        if len(self.cameras) == 0:
            return

        new_index = (self.selected_camera_index + offset) % len(self.cameras)
        self.select_camera_at_index(new_index)

    def select_camera_at_index(self, index: int):
        """Select camera at specific index"""
        if index < 0 or index >= len(self.cameras):
            return

        # Stop previous camera if enabled
        usb_config = self.config.get_usb_controller_config()
        stop_on_switch = usb_config.get("stop_on_camera_switch", True)

        if stop_on_switch and 0 <= self.selected_camera_index < len(self.cameras):
            previous_camera = self.cameras[self.selected_camera_index]
            if previous_camera.is_connected:
                try:
                    previous_camera.stop_camera()
                except Exception as e:
                    logger.warning(f"Failed to stop previous camera: {e}")

        # Deselect all
        for cam in self.cameras:
            cam.set_selected(False)

        # Select target
        self.selected_camera_index = index
        self.cameras[index].set_selected(True)

    def get_selected_camera(self) -> "CameraWidget | None":
        """Get currently selected camera"""
        if 0 <= self.selected_camera_index < len(self.cameras):
            return self.cameras[self.selected_camera_index]
        return None

    def _update_usb_indicator(self, connected: bool, name: str = ""):
        """Update USB controller visual indicator"""
        if connected:
            self.usb_icon_label.setText("\U0001f3ae\ufe0e")
            self.usb_icon_label.setStyleSheet("color: #00FF00; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                f"<span style='font-size: 10pt;'>Controller: {name}<br>Click for settings</span>"
            )
        else:
            self.usb_icon_label.setText("\U0001f3ae\ufe0e")
            self.usb_icon_label.setStyleSheet("color: #FF0000; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                "<span style='font-size: 10pt;'>No controller connected<br>Click for settings</span>"
            )

    @pyqtSlot(str)
    def on_usb_connected(self, name: str) -> None:
        """Handle USB controller connected"""
        try:
            self._update_usb_indicator(True, name)
            self.config.set_usb_controller_name(name)
            logger.info(f"USB Controller connected: {name}")
        except Exception:
            logger.exception("Error handling USB connection")

    @pyqtSlot()
    def on_usb_disconnected(self) -> None:
        """Handle USB controller disconnected"""
        try:
            self._update_usb_indicator(False)
            logger.info("USB Controller disconnected")
        except Exception:
            logger.exception("Error handling USB disconnection")

    @pyqtSlot(object, float)
    def on_usb_movement(self, direction: MovementDirection, speed: float):
        """Handle USB controller movement"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_movement(direction, speed)
        except Exception:
            logger.exception("Error handling USB movement")

    @pyqtSlot(float)
    def on_usb_zoom_in(self, speed: float):
        """Handle USB controller zoom in"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_in(speed)
        except Exception:
            logger.exception("Error handling USB zoom in")

    @pyqtSlot(float)
    def on_usb_zoom_out(self, speed: float):
        """Handle USB controller zoom out"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_out(speed)
        except Exception:
            logger.exception("Error handling USB zoom out")

    @pyqtSlot()
    def on_usb_stop_movement(self):
        """Handle USB controller stop movement"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_stop()
        except Exception:
            logger.exception("Error handling USB stop")

    @pyqtSlot()
    def on_usb_zoom_stop(self):
        """Handle USB controller zoom stop"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_stop()
        except Exception:
            logger.exception("Error handling USB zoom stop")

    @pyqtSlot()
    def on_usb_brightness_increase(self) -> None:
        """Handle USB controller brightness increase"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_increase()
        except Exception:
            logger.exception("Error handling USB brightness increase")

    @pyqtSlot()
    def on_usb_brightness_decrease(self) -> None:
        """Handle USB controller brightness decrease"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_decrease()
        except Exception:
            logger.exception("Error handling USB brightness decrease")

    @pyqtSlot()
    @pyqtSlot()
    def on_usb_reconnect(self) -> None:
        """Handle reconnect request from USB controller"""
        try:
            camera = self.get_selected_camera()
            if camera and not camera.is_connected:
                camera.reconnect_camera()
        except Exception:
            logger.exception("Error handling USB reconnect")

    @pyqtSlot()
    def on_usb_focus_one_push(self) -> None:
        """Handle one-push autofocus from USB controller (B button)"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.on_one_push_af()
        except Exception:
            logger.exception("Error handling USB one-push autofocus")

    def on_video_size_changed(self, size: VideoSize) -> None:
        """Handle video size menu selection"""
        try:
            # Update default preference
            self.config.set_default_video_size(size.width, size.height)

            # Update all cameras
            for camera in self.cameras:
                camera.set_video_size(size.width, size.height)
        except Exception:
            logger.exception("Error changing video size")

    def on_frame_rate_changed(self, skip_value: int) -> None:
        """Handle video performance/frame rate menu selection"""
        try:
            # Update preference
            self.config.set_video_frame_skip(skip_value)

            # Restart video on all cameras to apply new setting
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    # Update the frame skip on the running thread
                    camera.ndi_thread.frame_skip = skip_value

            logger.debug(f"Video frame skip set to {skip_value}")
        except Exception:
            logger.exception("Error handling frame rate change")

    def on_file_logging_toggled(self, checked: bool) -> None:
        """Handle file logging preference toggle"""
        try:
            # Update preference
            if "preferences" not in self.config.config:
                self.config.config["preferences"] = {}
            self.config.config["preferences"]["file_logging_enabled"] = checked
            self.config.save()

            # Inform user that restart is required
            message = UIStrings.LOGGING_ENABLED_MSG if checked else UIStrings.LOGGING_DISABLED_MSG
            QMessageBox.information(
                self,
                UIStrings.DIALOG_RESTART_REQUIRED,
                message,
            )
            logger.info(f"File logging preference set to {checked} (restart required)")
        except Exception:
            logger.exception("Error toggling file logging preference")

    def show_about(self):
        """Show about dialog with open source components"""
        dialog = AboutDialog(self)
        dialog.exec()

    def check_for_updates(self):
        """Check for updates on GitHub"""
        try:
            logger.info("Starting update check")

            # Prevent multiple simultaneous checks
            if self._update_check_thread is not None:
                try:
                    if self._update_check_thread.isRunning():
                        logger.warning("Update check already in progress")
                        return
                except RuntimeError:
                    # Thread object was deleted, clear reference
                    logger.debug("Clearing stale thread reference")
                    self._update_check_thread = None

            # Show checking message with Cancel button
            self._update_progress_dialog = QMessageBox(self)
            self._update_progress_dialog.setWindowTitle(UIStrings.DIALOG_CHECK_UPDATES)
            self._update_progress_dialog.setText(UIStrings.UPDATE_CHECKING)
            self._update_progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
            self._update_progress_dialog.setModal(False)  # Non-modal so it doesn't block UI

            # Handle cancel button
            cancel_btn = self._update_progress_dialog.button(QMessageBox.StandardButton.Cancel)
            cancel_btn.clicked.connect(self._cancel_update_check)

            self._update_progress_dialog.show()

            # Create and start worker thread
            self._update_check_thread = UpdateCheckThread(__version__)
            self._update_check_thread.update_result.connect(self._on_update_check_complete)
            self._update_check_thread.finished.connect(self._on_update_thread_finished)
            self._update_check_thread.start()

            logger.debug("Update check thread started")

        except Exception as e:
            logger.exception(f"Failed to start update check: {e}")
            import traceback

            traceback.print_exc()

            # Close progress dialog if it was created
            if self._update_progress_dialog:
                self._update_progress_dialog.close()
                self._update_progress_dialog = None

            QMessageBox.critical(
                self,
                UIStrings.UPDATE_ERROR_TITLE,
                f"Failed to check for updates: {str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _cancel_update_check(self):
        """Cancel the update check (user clicked Cancel button)"""
        logger.info("User cancelled update check")

        # Close dialog
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        # Stop thread if running
        if self._update_check_thread:
            try:
                if self._update_check_thread.isRunning():
                    logger.debug("Stopping update check thread")
                    self._update_check_thread.terminate()  # Force stop the thread
                    self._update_check_thread.wait(1000)  # Wait up to 1 second for thread to stop
            except RuntimeError:
                # Thread object was already deleted
                logger.debug("Thread already deleted during cancel")
            finally:
                self._update_check_thread = None

    def _on_update_thread_finished(self):
        """Handle update check thread completion (cleanup)"""
        logger.debug("Update check thread finished")
        if self._update_check_thread:
            self._update_check_thread.deleteLater()
            self._update_check_thread = None

    def _on_update_check_complete(self, success: bool, data):
        """Handle update check completion (slot for UpdateCheckThread signal)"""
        try:
            # Close progress dialog (only if still open)
            if self._update_progress_dialog:
                self._update_progress_dialog.close()
                self._update_progress_dialog = None

            if not success:
                logger.warning(f"Update check failed: {data}")
                QMessageBox.warning(
                    self,
                    UIStrings.UPDATE_ERROR_TITLE,
                    UIStrings.UPDATE_ERROR,
                    QMessageBox.StandardButton.Ok,
                )
                return

            # Parse version from tag_name (e.g., "v0.5.1" -> "0.5.1")
            latest_version = data.get("tag_name", "").lstrip("v")
            current_version = __version__

            logger.info(
                f"Update check complete. Current: {current_version}, Latest: {latest_version}"
            )

            if self._is_newer_version(latest_version, current_version):
                # Show update available dialog
                reply = QMessageBox.question(
                    self,
                    UIStrings.UPDATE_AVAILABLE,
                    UIStrings.UPDATE_AVAILABLE_MSG.format(
                        current=current_version, latest=latest_version
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # Open releases page in browser
                    url = data.get("html_url", "https://github.com/jpwalters/VideoCue/releases")
                    logger.info(f"Opening release URL: {url}")
                    QDesktopServices.openUrl(QUrl(url))
            else:
                # Already on latest version
                QMessageBox.information(
                    self,
                    UIStrings.DIALOG_CHECK_UPDATES,
                    UIStrings.UPDATE_NOT_AVAILABLE.format(version=current_version),
                    QMessageBox.StandardButton.Ok,
                )

        except Exception as e:
            logger.exception(f"Error handling update check result: {e}")
            import traceback

            traceback.print_exc()
            QMessageBox.critical(
                self,
                UIStrings.UPDATE_ERROR_TITLE,
                f"Error processing update information: {str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Compare version strings (e.g., '0.5.1' vs '0.4.1')"""
        try:
            latest_parts = [int(x) for x in latest.split(".")]
            current_parts = [int(x) for x in current.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))

            return latest_parts > current_parts
        except (ValueError, AttributeError):
            return False

    def show_controller_preferences(self):
        """Show controller preferences dialog (non-modal, stays open)"""
        from videocue.ui.controller_preferences_dialog import ControllerPreferencesDialog

        logger.info(
            f"show_controller_preferences called. dialog_open={self._preferences_dialog_open}"
        )

        # If dialog is already open, ignore this menu button press (prevents multiple windows)
        if self._preferences_dialog_open:
            logger.info("Dialog already open, ignoring menu press")
            return

        # Mark dialog as open
        self._preferences_dialog_open = True
        logger.info("Opening preferences dialog")

        # DISABLE ALL CAMERA/CONTROL SIGNALS - only dialog should respond to controller
        logger.debug("Disconnecting ALL camera control signals")
        if self.usb_controller:
            try:
                self.usb_controller.prev_camera.disconnect()
                self.usb_controller.next_camera.disconnect()
                self.usb_controller.movement_direction.disconnect()
                self.usb_controller.zoom_in.disconnect()
                self.usb_controller.zoom_out.disconnect()
                self.usb_controller.zoom_stop.disconnect()
                self.usb_controller.stop_movement.disconnect()
                self.usb_controller.brightness_increase.disconnect()
                self.usb_controller.brightness_decrease.disconnect()
                self.usb_controller.focus_one_push.disconnect()
            except TypeError:
                pass  # Already disconnected

        # Always create fresh dialog
        logger.debug(f"Creating dialog with usb_controller={self.usb_controller}")
        self.preferences_dialog = ControllerPreferencesDialog(
            self.config, self, self.usb_controller
        )

        # Connect finished signal to reset flag when dialog closes
        self.preferences_dialog.finished.connect(self._on_preferences_dialog_closed)

        logger.debug("Dialog created, calling show() - ready for input")

        # Use show() instead of exec() so signals are processed while dialog is visible
        self.preferences_dialog.show()

    def _on_preferences_dialog_closed(self):
        """Called when preferences dialog is closed - reset flag and reconnect all signals"""
        logger.info("Preferences dialog closed, reconnecting signals")

        # RECONNECT ALL CAMERA/CONTROL SIGNALS
        logger.debug("Reconnecting ALL camera control signals")
        if self.usb_controller and self._usb_signal_handlers:
            self.usb_controller.prev_camera.connect(self._usb_signal_handlers["prev_camera"])
            self.usb_controller.next_camera.connect(self._usb_signal_handlers["next_camera"])
            self.usb_controller.movement_direction.connect(
                self._usb_signal_handlers["movement_direction"]
            )
            self.usb_controller.zoom_in.connect(self._usb_signal_handlers["zoom_in"])
            self.usb_controller.zoom_out.connect(self._usb_signal_handlers["zoom_out"])
            self.usb_controller.zoom_stop.connect(self._usb_signal_handlers["zoom_stop"])
            self.usb_controller.stop_movement.connect(self._usb_signal_handlers["stop_movement"])
            self.usb_controller.brightness_increase.connect(
                self._usb_signal_handlers["brightness_increase"]
            )
            self.usb_controller.brightness_decrease.connect(
                self._usb_signal_handlers["brightness_decrease"]
            )
            self.usb_controller.focus_one_push.connect(self._usb_signal_handlers["focus_one_push"])

        self._preferences_dialog_open = False

    def closeEvent(self, event) -> None:
        """Handle window close event"""
        logger.info("Closing application and cleaning up threads...")

        # Save configuration
        try:
            self.config.save()
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config on close: {e}")

        # Stop all cameras asynchronously
        logger.info(f"Stopping {len(self.cameras)} camera threads...")
        for camera in self.cameras:
            camera._cleanup_threads()  # Stop all camera threads
            camera.stop_retry_mechanism()  # Stop any retry timers

        # Stop USB controller timers
        if self.usb_controller:
            self.usb_controller.poll_timer.stop()
            self.usb_controller.hotplug_timer.stop()
            logger.info("USB controller timers stopped")

        # Cleanup NDI global resources
        try:
            cleanup_ndi()
            logger.info("NDI resources cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up NDI: {e}")

        logger.info("Cleanup complete, exiting...")
        event.accept()

        # Let Qt handle application shutdown naturally
        # No forced quit - just accept the close event
