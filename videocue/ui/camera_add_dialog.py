"""
Camera add dialog for discovering and adding cameras"""

import logging

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from videocue.controllers.ndi_video import find_ndi_cameras, ndi_available

logger = logging.getLogger(__name__)


class NDIDiscoveryThread(QThread):
    """Worker thread for NDI camera discovery to avoid blocking UI"""

    cameras_found = pyqtSignal(list)  # List of camera names
    error_occurred = pyqtSignal(str)  # Error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeout_ms = 5000
        self._should_run = False

    def set_timeout(self, timeout_ms: int):
        """Set timeout for next discovery run"""
        self.timeout_ms = timeout_ms

    def run(self):
        """Discover cameras in background"""
        try:
            logger.debug(f"Starting NDI discovery with {self.timeout_ms}ms timeout")
            cameras = find_ndi_cameras(self.timeout_ms)
            logger.debug(f"Discovery complete, found {len(cameras)} cameras")

            # Add explicit logging and error handling around signal emission
            try:
                logger.debug(f"About to emit cameras_found signal with {len(cameras)} cameras...")
                self.cameras_found.emit(cameras)
                logger.debug("Signal emitted successfully")
            except Exception:
                logger.exception("CRITICAL: Failed to emit signal")
                raise

        except Exception as e:
            import traceback

            error_msg = f"Discovery failed: {str(e)}"
            logger.exception("Error during NDI discovery")
            traceback.print_exc()
            try:
                self.error_occurred.emit(error_msg)
                self.cameras_found.emit([])  # Emit empty list on error
            except Exception:
                logger.exception("CRITICAL: Failed to emit error signal")


class CameraAddDialog(QDialog):
    """Dialog for adding cameras via NDI discovery or manual IP"""

    def __init__(self, parent=None, existing_cameras=None):
        super().__init__(parent)

        self.ndi_checkboxes = []
        self.ip_checkbox = None
        self.ip_input = None
        self.ndi_name_checkbox = None
        self.ndi_name_input = None
        self.discovery_thread = None
        self.search_button = None
        self.loading_timer = None
        self.loading_dots = 0
        self._processing_results = False  # Guard flag to prevent concurrent result processing
        self._search_in_progress = False  # Guard flag to prevent multiple simultaneous searches
        self.existing_cameras = existing_cameras or []  # List of existing camera configs

        self.init_ui()
        # Don't auto-discover on init - let user click search if needed
        # This prevents blocking the UI when dialog opens
        self.load_camera_list(quick=False, skip_discovery=True)

    def init_ui(self):
        """Initialize dialog UI"""
        self.setWindowTitle("Add Cameras")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)

        # Header with search button
        header = QHBoxLayout()
        header_label = QLabel("Select cameras to add:")
        header.addWidget(header_label)
        header.addStretch()

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.start_search)
        header.addWidget(self.search_button)

        layout.addLayout(header)

        # Scroll area for camera list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        # Container for checkboxes
        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(self.list_container)

        # Bottom buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)

    def start_search(self):
        """Start camera search with loading animation"""
        try:
            from PyQt6.QtCore import QTimer

            # If a search is already running, don't start another
            if self._search_in_progress:
                logger.debug("Search already in progress, ignoring request")
                return

            if self.discovery_thread and self.discovery_thread.isRunning():
                logger.debug("Discovery thread still running, ignoring request")
                return

            self._search_in_progress = True

            # Disable search button IMMEDIATELY
            if self.search_button:
                self.search_button.setEnabled(False)
                self.search_button.setText("Searching.")

            # Start loading animation IMMEDIATELY
            self.loading_dots = 1  # Start at 1 since we already show one dot
            if self.loading_timer:
                self.loading_timer.stop()

            self.loading_timer = QTimer()
            self.loading_timer.timeout.connect(self._update_loading_animation)
            self.loading_timer.start(500)  # Update every 500ms

            # Defer the actual search to next event loop iteration
            # This ensures UI updates (button disable, text change) happen immediately
            QTimer.singleShot(10, lambda: self.load_camera_list(quick=False))
        except Exception as e:
            import traceback

            logger.exception("Error starting search")
            traceback.print_exc()
            # Re-enable search button on error
            self._search_in_progress = False
            if self.search_button:
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")
            # Show error to user
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Search Error", f"Failed to start camera search:\n{str(e)}")

    def _update_loading_animation(self):
        """Update loading animation dots"""
        try:
            if self.search_button:
                self.loading_dots = (self.loading_dots + 1) % 4
                dots = "." * self.loading_dots
                self.search_button.setText(f"Searching{dots}")
        except Exception:
            logger.exception("Error updating animation")

    def load_camera_list(self, quick: bool = True, skip_discovery: bool = False):
        """Load NDI cameras and populate list"""
        try:
            # Clear only NDI discovery items (not manual IP section)
            # Remove items from top until we hit the manual IP section
            items_to_remove = []
            for i in range(self.list_layout.count()):
                item = self.list_layout.itemAt(i)
                widget = item.widget() if item else None
                # Stop when we hit the manual IP section (spacing before it)
                if item and item.spacerItem():
                    break
                if widget and (isinstance(widget, (QCheckBox, QLabel))):
                    items_to_remove.append(widget)

            # Delete widgets immediately to prevent accumulation
            for widget in items_to_remove:
                try:
                    self.list_layout.removeWidget(widget)
                    widget.setParent(None)
                    widget.deleteLater()
                except RuntimeError:
                    pass  # Widget already deleted

            self.ndi_checkboxes.clear()

            # Add manual IP section only if it doesn't exist yet
            if self.ip_checkbox is None or self.ip_input is None:
                self._add_manual_ip_section()

            # Load NDI cameras if available
            if ndi_available and not skip_discovery:
                # If a discovery is already running, don't start another
                if self.discovery_thread and self.discovery_thread.isRunning():
                    logger.debug("Discovery already in progress, skipping new search")
                    return

                # Clean up old thread if it exists
                if self.discovery_thread:
                    logger.debug(f"Cleaning up old thread {id(self.discovery_thread)}...")
                    # Wait for thread to finish if still running
                    if self.discovery_thread.isRunning():
                        logger.debug("Waiting for thread to finish...")
                        self.discovery_thread.wait(2000)
                    # Disconnect all signals
                    try:
                        self.discovery_thread.cameras_found.disconnect()
                        self.discovery_thread.error_occurred.disconnect()
                    except (TypeError, RuntimeError):
                        pass  # Already disconnected
                    # Delete the thread
                    self.discovery_thread.deleteLater()
                    self.discovery_thread = None
                    logger.debug("Old thread cleaned up")

                # Always create a fresh thread
                logger.debug("Creating new discovery thread...")
                self.discovery_thread = NDIDiscoveryThread(self)
                logger.debug(f"Thread object ID: {id(self.discovery_thread)}")
                logger.debug("Connecting signals...")
                self.discovery_thread.cameras_found.connect(self._on_cameras_discovered)
                self.discovery_thread.error_occurred.connect(self._on_discovery_error)
                logger.debug("Signals connected")

                # Show loading message at top
                loading_label = QLabel("Searching for NDI cameras...")
                loading_label.setStyleSheet("color: lightblue; font-style: italic;")
                loading_label.setObjectName("loading_label")
                self.list_layout.insertWidget(0, loading_label)

                # Start discovery in background thread
                timeout = 1000 if quick else 5000
                logger.debug(f"Setting timeout to {timeout}ms and starting discovery...")
                self.discovery_thread.set_timeout(timeout)
                self.discovery_thread.start()
                logger.debug(
                    f"Discovery thread started. Running: {self.discovery_thread.isRunning()}"
                )
            elif skip_discovery and ndi_available:
                # Show message that discovery is available via search button
                label = QLabel(
                    "Click 'Search' to discover NDI cameras, or enter details manually below"
                )
                label.setStyleSheet("color: lightblue; font-style: italic;")
                self.list_layout.insertWidget(0, label)
            else:
                # NDI not available - show message
                label = QLabel("NDI not available - use manual IP entry below")
                label.setStyleSheet("color: orange; font-style: italic;")
                self.list_layout.insertWidget(0, label)
        except Exception as e:
            import traceback

            logger.exception("Error loading camera list")
            traceback.print_exc()
            # Re-enable search button on error
            if self.loading_timer:
                self.loading_timer.stop()
                self.loading_timer = None
            if self.search_button:
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")
            # Try to show error in UI
            try:
                error_label = QLabel(f"Error loading cameras: {str(e)}")
                error_label.setStyleSheet("color: red; font-style: italic;")
                self.list_layout.insertWidget(0, error_label)
            except Exception:
                pass

    def _on_cameras_discovered(self, ndi_cameras):
        """Handle NDI camera discovery completion"""
        try:
            logger.debug(f"_on_cameras_discovered called with {len(ndi_cameras)} cameras")
        except Exception:
            logger.exception("ERROR in initial logging")

        # Prevent concurrent processing of results (can happen if multiple discoveries complete)
        if self._processing_results:
            logger.debug("Already processing results, ignoring duplicate call")
            return

        logger.debug("Starting result processing...")
        self._processing_results = True
        try:
            logger.debug("Stopping loading animation...")
            # Stop loading animation
            if self.loading_timer:
                self.loading_timer.stop()
                self.loading_timer = None

            logger.debug("Re-enabling search button...")
            # Re-enable search button
            if self.search_button:
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")

            logger.debug(f"Clearing {len(self.ndi_checkboxes)} existing checkboxes...")
            # Clear ALL existing checkboxes (safer than selective removal)
            for i, checkbox in enumerate(self.ndi_checkboxes):
                try:
                    logger.debug(f"Removing checkbox {i}: {checkbox.text()}")
                    self.list_layout.removeWidget(checkbox)
                    checkbox.setParent(None)
                    checkbox.deleteLater()
                except RuntimeError:
                    logger.exception(f"RuntimeError removing checkbox {i}")
                except Exception:
                    logger.exception(f"Unexpected error removing checkbox {i}")
                    import traceback

                    traceback.print_exc()
            self.ndi_checkboxes.clear()
            logger.debug("Checkboxes cleared")

            logger.debug("Removing label widgets...")
            # Remove any labels at the top (loading, error, "no cameras" messages)
            items_to_remove = []
            for i in range(self.list_layout.count()):
                item = self.list_layout.itemAt(i)
                if item and item.spacerItem():
                    logger.debug(f"Found spacer at index {i}, stopping label removal")
                    break  # Stop at spacer (before manual IP section)
                widget = item.widget() if item else None
                if widget and isinstance(widget, QLabel):
                    logger.debug(f"Marking label for removal: {widget.text()[:50]}")
                    items_to_remove.append(widget)

            logger.debug(f"Removing {len(items_to_remove)} labels...")
            for j, widget in enumerate(items_to_remove):
                try:
                    logger.debug(f"Removing label {j}...")
                    self.list_layout.removeWidget(widget)
                    widget.setParent(None)
                    widget.deleteLater()
                except RuntimeError:
                    logger.exception(f"RuntimeError removing label {j}")
                except Exception:
                    logger.exception(f"Unexpected error removing label {j}")
                    import traceback

                    traceback.print_exc()

            logger.debug("Labels removed, adding new content...")
            # Add discovered cameras at top
            if ndi_cameras:
                logger.debug(f"Adding {len(ndi_cameras)} camera checkboxes...")
                for k, camera_name in enumerate(ndi_cameras):
                    try:
                        logger.debug(f"Creating checkbox {k}: {camera_name}")

                        # Check if camera already exists
                        already_added = self._is_camera_already_added(camera_name)
                        checkbox = QCheckBox(camera_name)

                        if already_added:
                            # Show camera but indicate it's already added
                            checkbox.setChecked(False)
                            checkbox.setEnabled(False)
                            checkbox.setStyleSheet("color: gray; font-style: italic;")
                        else:
                            checkbox.setChecked(True)  # Selected by default

                        insert_pos = len(self.ndi_checkboxes)
                        logger.debug(f"Inserting at position {insert_pos}")
                        self.list_layout.insertWidget(insert_pos, checkbox)
                        self.ndi_checkboxes.append(checkbox)
                        logger.debug(f"Checkbox {k} added successfully")
                    except Exception:
                        logger.exception(f"ERROR adding checkbox {k}")
                        import traceback

                        traceback.print_exc()
            else:
                logger.debug("No cameras found, adding label...")
                try:
                    label = QLabel("No NDI cameras found")
                    label.setStyleSheet("color: gray; font-style: italic;")
                    self.list_layout.insertWidget(0, label)
                    logger.debug("'No cameras' label added")
                except Exception:
                    logger.exception("ERROR adding 'no cameras' label")

            logger.debug("Result processing completed successfully")
            # Don't call adjustSize() or processEvents() - they can block UI
            # Dialog will resize naturally with content
        except Exception:
            logger.exception("EXCEPTION in _on_cameras_discovered")
            # Re-enable search button on error
            if self.loading_timer:
                self.loading_timer.stop()
                self.loading_timer = None
            if self.search_button:
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")
        finally:
            logger.debug("Resetting search and processing flags")
            # Always reset both flags
            self._search_in_progress = False
            self._processing_results = False
            logger.debug("Flags reset, _on_cameras_discovered complete")

    def _on_discovery_error(self, error_msg: str):
        """Handle discovery error"""
        try:
            logger.warning(f"Discovery error: {error_msg}")

            # Clear the search in progress flag
            self._search_in_progress = False

            # Stop loading animation
            if self.loading_timer:
                self.loading_timer.stop()
                self.loading_timer = None

            # Re-enable search button
            if self.search_button:
                self.search_button.setEnabled(True)
                self.search_button.setText("Search")

            # Remove loading label and show error
            for i in range(self.list_layout.count()):
                item = self.list_layout.itemAt(i)
                if item and item.widget() and item.widget().objectName() == "loading_label":
                    item.widget().deleteLater()
                    break

            # Show error message
            error_label = QLabel(f"Discovery failed: {error_msg}")
            error_label.setStyleSheet("color: red; font-style: italic;")
            self.list_layout.insertWidget(0, error_label)
        except Exception:
            logger.exception("Error handling discovery error")
            self._search_in_progress = False

    def _is_camera_already_added(self, ndi_name: str) -> bool:
        """Check if camera with this NDI name is already added"""
        for cam_config in self.existing_cameras:
            if cam_config.get("ndi_source_name") == ndi_name:
                return True
        return False

    def _add_manual_ip_section(self):
        """Add the manual IP entry section"""
        # Add separator
        self.list_layout.addSpacing(20)

        # Manual NDI source name entry (for firewall-restricted networks)
        ndi_container = QHBoxLayout()
        self.ndi_name_checkbox = QCheckBox("Manual NDI Name:")
        ndi_container.addWidget(self.ndi_name_checkbox)

        self.ndi_name_input = QLineEdit()
        self.ndi_name_input.setPlaceholderText("BIRDDOG-12345 (Channel 1)")
        self.ndi_name_input.setToolTip("Enter NDI source name if discovery is blocked by firewall")

        # Auto-check checkbox when typing
        self.ndi_name_input.textChanged.connect(
            lambda: self.ndi_name_checkbox.setChecked(bool(self.ndi_name_input.text()))
        )

        ndi_container.addWidget(self.ndi_name_input)
        self.list_layout.addLayout(ndi_container)

        # Manual IP entry
        ip_container = QHBoxLayout()

        self.ip_checkbox = QCheckBox("Manual IP:")
        ip_container.addWidget(self.ip_checkbox)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("192.168.1.100")
        self.ip_input.setMaxLength(15)

        # Simple IP validation (allow partial input)
        from PyQt6.QtCore import QRegularExpression
        from PyQt6.QtGui import QRegularExpressionValidator

        ip_regex = QRegularExpression(
            r"^(([01]?[0-9]{0,2})|(2[0-4][0-9])|(25[0-5]))?(\.(([01]?[0-9]{0,2})|(2[0-4][0-9])|(25[0-5]))){0,3}$"
        )
        validator = QRegularExpressionValidator(ip_regex)
        self.ip_input.setValidator(validator)

        # Auto-check checkbox when typing
        self.ip_input.textChanged.connect(
            lambda: self.ip_checkbox.setChecked(bool(self.ip_input.text()))
        )

        ip_container.addWidget(self.ip_input)

        self.list_layout.addLayout(ip_container)
        self.list_layout.addStretch()

    def get_selected_ndi_cameras(self):
        """Get list of selected NDI camera names"""
        cameras = [cb.text() for cb in self.ndi_checkboxes if cb.isChecked()]

        # Add manual NDI name if provided
        if self.ndi_name_checkbox and self.ndi_name_checkbox.isChecked():
            ndi_name = self.ndi_name_input.text().strip()
            if ndi_name:
                cameras.append(ndi_name)

        return cameras

    def get_ip_address(self):
        """Get manual IP address if checked"""
        if self.ip_checkbox and self.ip_checkbox.isChecked():
            ip = self.ip_input.text().strip()
            # Validate it's a complete IP (4 octets)
            if ip.count(".") == 3:
                return ip
        return None
