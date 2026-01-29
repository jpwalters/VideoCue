"""
Camera add dialog for discovering and adding cameras"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QLineEdit, QPushButton, QScrollArea, QWidget, QLabel
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from videocue.controllers.ndi_video import find_ndi_cameras, ndi_available


class NDIDiscoveryThread(QThread):
    """Worker thread for NDI camera discovery to avoid blocking UI"""

    cameras_found = pyqtSignal(list)  # List of camera names

    def __init__(self, timeout_ms: int):
        super().__init__()
        self.timeout_ms = timeout_ms

    def run(self):
        """Discover cameras in background"""
        cameras = find_ndi_cameras(self.timeout_ms)
        self.cameras_found.emit(cameras)


class CameraAddDialog(QDialog):
    """Dialog for adding cameras via NDI discovery or manual IP"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.ndi_checkboxes = []
        self.ip_checkbox = None
        self.ip_input = None
        self.ndi_name_checkbox = None
        self.ndi_name_input = None
        self.discovery_thread = None

        self.init_ui()
        # Don't auto-discover on init - let user click refresh if needed
        # This prevents blocking the UI when dialog opens
        self.load_camera_list(quick=False, skip_discovery=True)

    def init_ui(self):
        """Initialize dialog UI"""
        self.setWindowTitle("Add Cameras")
        self.setModal(True)
        self.resize(480, 400)

        layout = QVBoxLayout(self)

        # Header with refresh button
        header = QHBoxLayout()
        header_label = QLabel("Select cameras to add:")
        header.addWidget(header_label)
        header.addStretch()

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(lambda: self.load_camera_list(quick=False))
        header.addWidget(refresh_button)

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

    def load_camera_list(self, quick: bool = True, skip_discovery: bool = False):
        """Load NDI cameras and populate list"""
        # Clear existing items
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.ndi_checkboxes.clear()

        # Always add manual IP section first (at bottom)
        self._add_manual_ip_section()

        # Load NDI cameras if available
        if ndi_available and not skip_discovery:
            # Show loading message at top
            loading_label = QLabel("Searching for NDI cameras...")
            loading_label.setStyleSheet("color: lightblue; font-style: italic;")
            loading_label.setObjectName("loading_label")
            self.list_layout.insertWidget(0, loading_label)

            # Start discovery in background thread
            timeout = 1000 if quick else 5000

            # Stop any existing discovery
            if self.discovery_thread and self.discovery_thread.isRunning():
                self.discovery_thread.wait()

            self.discovery_thread = NDIDiscoveryThread(timeout)
            self.discovery_thread.cameras_found.connect(self._on_cameras_discovered)
            self.discovery_thread.start()
        elif skip_discovery and ndi_available:
            # Show message that discovery is available via refresh button
            label = QLabel("Click 'Refresh' to discover NDI cameras, or enter details manually below")
            label.setStyleSheet("color: lightblue; font-style: italic;")
            self.list_layout.insertWidget(0, label)
        else:
            # NDI not available - show message
            label = QLabel("NDI not available - use manual IP entry below")
            label.setStyleSheet("color: orange; font-style: italic;")
            self.list_layout.insertWidget(0, label)

    def _on_cameras_discovered(self, ndi_cameras):
        """Handle NDI camera discovery completion"""
        # Remove loading label
        for i in range(self.list_layout.count()):
            item = self.list_layout.itemAt(i)
            if item and item.widget() and item.widget().objectName() == "loading_label":
                item.widget().deleteLater()
                break

        # Add discovered cameras at top
        if ndi_cameras:
            for idx, camera_name in enumerate(ndi_cameras):
                checkbox = QCheckBox(camera_name)
                checkbox.setChecked(True)  # Selected by default
                self.list_layout.insertWidget(idx, checkbox)
                self.ndi_checkboxes.append(checkbox)
        else:
            label = QLabel("No NDI cameras found")
            label.setStyleSheet("color: gray; font-style: italic;")
            self.list_layout.insertWidget(0, label)

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
            lambda: self.ndi_name_checkbox.setChecked(bool(self.ndi_name_input.text())))

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
        from PyQt6.QtGui import QRegularExpressionValidator
        from PyQt6.QtCore import QRegularExpression

        ip_regex = QRegularExpression(
            r"^(([01]?[0-9]{0,2})|(2[0-4][0-9])|(25[0-5]))?(\.(([01]?[0-9]{0,2})|(2[0-4][0-9])|(25[0-5]))){0,3}$"
        )
        validator = QRegularExpressionValidator(ip_regex)
        self.ip_input.setValidator(validator)

        # Auto-check checkbox when typing
        self.ip_input.textChanged.connect(
            lambda: self.ip_checkbox.setChecked(bool(self.ip_input.text())))

        ip_container.addWidget(self.ip_input)

        self.list_layout.addLayout(ip_container)
        self.list_layout.addStretch()

    def get_selected_ndi_cameras(self):
        """Get list of selected NDI camera names"""
        cameras = [
            cb.text()
            for cb in self.ndi_checkboxes
            if cb.isChecked()
        ]
        
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
            if ip.count('.') == 3:
                return ip
        return None
