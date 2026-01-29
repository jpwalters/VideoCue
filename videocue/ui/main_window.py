"""
Main application window
"""
import os
from PyQt6.QtWidgets import (  # type: ignore
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QScrollArea, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSlot  # type: ignore
from PyQt6.QtGui import QAction, QActionGroup, QIcon  # type: ignore

from videocue.models.config_manager import ConfigManager
from videocue.models.video import VideoSize
from videocue.controllers.usb_controller import USBController, MovementDirection
from videocue.controllers.ndi_video import ndi_available, get_ndi_error_message
from videocue.ui.camera_widget import CameraWidget
from videocue.ui.camera_add_dialog import CameraAddDialog
from videocue.utils import resource_path


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Set window icon
        icon_path = resource_path('resources/icon.png')
        if os.path.exists(icon_path):
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
        self._total_cameras_to_load = 0
        self._cameras_initialized = 0
        self._current_progress_step = 0
        self._total_progress_steps = 0

        # Setup UI
        self.init_ui()

        # Initialize USB controller
        self.init_usb_controller()

        # Defer camera loading until after window is shown
        self._cameras_loaded = False

        # Show NDI error if library not available
        if not ndi_available:
            QMessageBox.warning(
                self,
                "NDI Not Available",
                get_ndi_error_message(),
                QMessageBox.StandardButton.Ok
            )

    def init_ui(self):
        """Initialize user interface"""
        self.setWindowTitle("VideoCue")
        self.setGeometry(100, 100, 1200, 800)

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
        self.tab_widget.addTab(self.cameras_tab, "Cameras")

        # Cues tab (placeholder) - Hidden for now
        # cues_tab = QWidget()
        # self.tab_widget.addTab(cues_tab, "Cues")

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

        preferences_action = QAction("Controller &Preferences...", self)
        preferences_action.triggered.connect(self.show_controller_preferences)
        edit_menu.addAction(preferences_action)

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

        # Help menu
        help_menu = menubar.addMenu("&Help")

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

            # Connect signals
            self.usb_controller.connected.connect(self.on_usb_connected)
            self.usb_controller.disconnected.connect(self.on_usb_disconnected)
            self.usb_controller.prev_camera.connect(lambda: self.select_camera(-1))
            self.usb_controller.next_camera.connect(lambda: self.select_camera(1))
            self.usb_controller.movement_direction.connect(self.on_usb_movement)
            self.usb_controller.zoom_in.connect(self.on_usb_zoom_in)
            self.usb_controller.zoom_out.connect(self.on_usb_zoom_out)
            self.usb_controller.zoom_stop.connect(self.on_usb_zoom_stop)
            self.usb_controller.brightness_increase.connect(self.on_usb_brightness_increase)
            self.usb_controller.brightness_decrease.connect(self.on_usb_brightness_decrease)
            self.usb_controller.reconnect_requested.connect(self.on_usb_reconnect)

            # Update UI to reflect current connection state
            if self.usb_controller.joystick is not None:
                name = self.usb_controller.joystick.get_name()
                self._update_usb_indicator(True, name)

        except (ImportError, RuntimeError, OSError) as e:
            print(f"USB controller initialization error: {e}")

    def showEvent(self, event):
        """Override showEvent to load cameras after UI is visible"""
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
                self.loading_label.setText(f"Preparing to load {self._total_cameras_to_load} camera(s)...")
                self.loading_label.setVisible(True)
                self.loading_progress.setRange(0, self._total_progress_steps)
                self.loading_progress.setValue(0)
                self.loading_progress.setVisible(True)
            
            # Use timer to ensure UI is fully rendered before loading cameras
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self.load_cameras)
    
    def load_cameras(self):
        """Load cameras from configuration"""
        camera_configs = self.config.get_cameras()
        
        for cam_config in camera_configs:
            self.add_camera_from_config(cam_config)

    def add_camera_from_config(self, cam_config: dict):
        """Add camera widget from configuration"""
        camera_num = len(self.cameras) + 1
        
        try:
            # Step 1: Creating widget
            self._update_loading_progress(f"Creating camera {camera_num}/{self._total_cameras_to_load}...")
            
            camera = CameraWidget(
                camera_id=cam_config['id'],
                ndi_source_name=cam_config.get('ndi_source_name', ''),
                visca_ip=cam_config['visca_ip'],
                visca_port=cam_config['visca_port'],
                config=self.config
            )

            # Set video size
            video_size = cam_config.get('video_size', [512, 288])
            camera.set_video_size(video_size[0], video_size[1])

            # Step 2: Configuring
            self._update_loading_progress(f"Configuring camera {camera_num}/{self._total_cameras_to_load}...")

            # Connect delete signal
            camera.delete_requested.connect(lambda: self.remove_camera(camera))
            
            # Connect initialization signals to track progress
            camera.connection_starting.connect(lambda: self._update_loading_progress(f"Connecting to camera {camera_num}/{self._total_cameras_to_load}..."))
            camera.initialized.connect(self.on_camera_initialized)

            # Add to layout (before stretch)
            self.cameras_layout.insertWidget(len(self.cameras), camera)
            self.cameras.append(camera)

            # Select first camera
            if len(self.cameras) == 1:
                self.select_camera_at_index(0)
                
        except Exception as e:
            import traceback
            error_msg = f"Failed to load camera {camera_num}:\n{str(e)}"
            print(f"\n{error_msg}")
            traceback.print_exc()
            QMessageBox.warning(
                self,
                "Camera Load Error",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            # Still increment initialized count so progress completes
            self.on_camera_initialized()

    def _update_loading_progress(self, message: str):
        """Update loading progress bar and message"""
        self._current_progress_step += 1
        self.loading_progress.setValue(self._current_progress_step)
        self.loading_label.setText(message)
    
    def on_camera_initialized(self):
        """Handle camera initialization completion"""
        self._cameras_initialized += 1
        self._update_loading_progress(f"Camera {self._cameras_initialized}/{self._total_cameras_to_load} ready")
        
        # Hide progress when all cameras loaded
        if self._cameras_initialized >= self._total_cameras_to_load:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self._hide_loading_indicator)
    
    def _hide_loading_indicator(self):
        """Hide the loading indicator"""
        self.loading_label.setVisible(False)
        self.loading_progress.setVisible(False)
    
    def add_camera_dialog(self):
        """Show add camera dialog"""
        dialog = CameraAddDialog(self)

        if dialog.exec():
            # Get selected cameras
            ndi_cameras = dialog.get_selected_ndi_cameras()
            ip_address = dialog.get_ip_address()

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
                    camera_id = self.config.add_camera(
                        ndi_source_name=ndi_name,
                        visca_ip=visca_ip
                    )

                    # Get config and add widget
                    cam_config = self.config.get_camera(camera_id)
                    if cam_config:
                        self.add_camera_from_config(cam_config)

            # Add IP-only camera
            if ip_address:
                camera_id = self.config.add_camera(
                    ndi_source_name="",
                    visca_ip=ip_address
                )

                cam_config = self.config.get_camera(camera_id)
                if cam_config:
                    self.add_camera_from_config(cam_config)

    def extract_ip_from_ndi_name(self, ndi_name: str) -> str:
        """Extract IP address from NDI source name (format: 'Name (IP)')"""
        if '(' in ndi_name and ')' in ndi_name:
            start = ndi_name.index('(') + 1
            end = ndi_name.index(')')
            return ndi_name[start:end].strip()
        return "192.168.1.100"  # Default

    def remove_camera(self, camera: 'CameraWidget'):
        """Remove camera widget with confirmation"""
        # Show confirmation dialog
        from PyQt6.QtWidgets import QMessageBox
        
        camera_name = camera.ndi_source_name if camera.ndi_source_name else camera.visca_ip
        reply = QMessageBox.question(
            self,
            'Confirm Delete',
            f'Are you sure you want to delete camera:\n{camera_name}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
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

        # Deselect all
        for cam in self.cameras:
            cam.set_selected(False)

        # Select target
        self.selected_camera_index = index
        self.cameras[index].set_selected(True)

    def get_selected_camera(self) -> 'CameraWidget | None':
        """Get currently selected camera"""
        if 0 <= self.selected_camera_index < len(self.cameras):
            return self.cameras[self.selected_camera_index]
        return None

    def _update_usb_indicator(self, connected: bool, name: str = ""):
        """Update USB controller visual indicator"""
        if connected:
            self.usb_icon_label.setText("\U0001F3AE\uFE0E")
            self.usb_icon_label.setStyleSheet("color: #00FF00; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                f"<span style='font-size: 10pt;'>Controller: {name}<br>Click for settings</span>")
        else:
            self.usb_icon_label.setText("\U0001F3AE\uFE0E")
            self.usb_icon_label.setStyleSheet("color: #FF0000; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                "<span style='font-size: 10pt;'>No controller connected<br>Click for settings</span>")

    @pyqtSlot(str)
    def on_usb_connected(self, name: str):
        """Handle USB controller connected"""
        try:
            self._update_usb_indicator(True, name)
            self.config.set_usb_controller_name(name)
            print(f"✓ USB Controller connected: {name}")
        except Exception as e:
            import traceback
            print(f"Error handling USB connection: {e}")
            traceback.print_exc()

    @pyqtSlot()
    def on_usb_disconnected(self):
        """Handle USB controller disconnected"""
        try:
            self._update_usb_indicator(False)
            print("✗ USB Controller disconnected")
        except Exception as e:
            import traceback
            print(f"Error handling USB disconnection: {e}")
            traceback.print_exc()

    @pyqtSlot(object, float)
    def on_usb_movement(self, direction: MovementDirection, speed: float):
        """Handle USB controller movement"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_movement(direction, speed)
        except Exception as e:
            import traceback
            print(f"Error handling USB movement: {e}")
            traceback.print_exc()

    @pyqtSlot(float)
    def on_usb_zoom_in(self, speed: float):
        """Handle USB controller zoom in"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_in(speed)
        except Exception as e:
            import traceback
            print(f"Error handling USB zoom in: {e}")
            traceback.print_exc()

    @pyqtSlot(float)
    def on_usb_zoom_out(self, speed: float):
        """Handle USB controller zoom out"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_out(speed)
        except Exception as e:
            import traceback
            print(f"Error handling USB zoom out: {e}")
            traceback.print_exc()

    @pyqtSlot()
    def on_usb_zoom_stop(self):
        """Handle USB controller zoom stop"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_stop()
        except Exception as e:
            import traceback
            print(f"Error handling USB zoom stop: {e}")
            traceback.print_exc()

    @pyqtSlot()
    def on_usb_brightness_increase(self):
        """Handle USB controller brightness increase"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_increase()
        except Exception as e:
            import traceback
            print(f"Error handling USB brightness increase: {e}")
            traceback.print_exc()

    @pyqtSlot()
    def on_usb_brightness_decrease(self):
        """Handle USB controller brightness decrease"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_decrease()
        except Exception as e:
            import traceback
            print(f"Error handling USB brightness decrease: {e}")
            traceback.print_exc()
    
    @pyqtSlot()
    def on_usb_reconnect(self):
        """Handle reconnect request from USB controller (B button)"""
        try:
            camera = self.get_selected_camera()
            if camera and not camera.is_connected:
                camera.reconnect_camera()
        except Exception as e:
            import traceback
            print(f"Error handling USB reconnect: {e}")
            traceback.print_exc()

    def on_video_size_changed(self, size: VideoSize):
        """Handle video size menu selection"""
        try:
            # Update default preference
            self.config.set_default_video_size(size.width, size.height)

            # Update all cameras
            for camera in self.cameras:
                camera.set_video_size(size.width, size.height)
        except Exception as e:
            import traceback
            print(f"Error handling video size change: {e}")
            traceback.print_exc()

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About VideoCue",
            "VideoCue - Multi-camera PTZ Controller\n\n"
            "Version 1.0.0\n\n"
            "Controls professional PTZ cameras using VISCA-over-IP protocol\n"
            "with NDI video streaming support."
        )

    def show_controller_preferences(self):
        """Show controller preferences dialog"""
        from videocue.ui.controller_preferences_dialog import ControllerPreferencesDialog

        dialog = ControllerPreferencesDialog(self.config, self)
        if dialog.exec():
            print("[USB] Controller preferences saved")
            # Config is saved in dialog, controller will read new values on next event

    def closeEvent(self, event):
        """Handle window close event"""
        # Save configuration
        self.config.save()

        # Stop all cameras
        for camera in self.cameras:
            camera.stop_video()

        # Cleanup USB controller
        if self.usb_controller:
            self.usb_controller.cleanup()

        event.accept()
