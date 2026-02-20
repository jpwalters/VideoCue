"""
Network interface selection dialog.

Allows user to select which network interface to use for NDI connections.
"""

import logging

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from videocue.utils.network_interface import NetworkInterface

logger = logging.getLogger(__name__)


class NetworkInterfaceDialog(QDialog):
    """Dialog for selecting network interface for NDI connections."""

    def __init__(self, interfaces: list[NetworkInterface], camera_ips: list[str], parent=None):
        super().__init__(parent)
        self.interfaces = interfaces
        self.camera_ips = camera_ips
        self.selected_interface = None
        self.radio_buttons = []

        self.setWindowTitle("Network Interface Selection")
        self.setMinimumWidth(500)
        self.setup_ui()

    def setup_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout()

        # Explanation label
        explanation = QLabel(
            "<b>Multiple network interfaces detected.</b><br><br>"
            "VideoCue needs to know which network interface to use for connecting to cameras.<br>"
            "Please select the interface that is on the same network as your cameras."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        layout.addSpacing(10)

        # Camera info
        camera_label = QLabel(f"<b>Camera IP addresses:</b> {', '.join(self.camera_ips)}")
        camera_label.setWordWrap(True)
        layout.addWidget(camera_label)

        layout.addSpacing(15)

        # Interface options
        interface_label = QLabel("<b>Available network interfaces:</b>")
        layout.addWidget(interface_label)

        for iface in self.interfaces:
            # Check if this interface is on same subnet as any camera
            matches = sum(1 for ip in self.camera_ips if iface.is_on_same_subnet(ip))

            if matches > 0:
                text = f"{iface.ip}/{iface.netmask.split('.')[-1]} - {iface.name} ✓ (matches {matches} camera{'s' if matches > 1 else ''})"
            else:
                text = f"{iface.ip}/{iface.netmask.split('.')[-1]} - {iface.name}"

            radio = QRadioButton(text)
            self.radio_buttons.append((radio, iface))
            layout.addWidget(radio)

            # Auto-select first matching interface
            if matches > 0 and self.selected_interface is None:
                radio.setChecked(True)
                self.selected_interface = iface

        layout.addSpacing(15)

        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def accept(self):
        """Handle OK button."""
        # Find selected interface
        for radio, iface in self.radio_buttons:
            if radio.isChecked():
                self.selected_interface = iface
                logger.info(f"User selected interface: {iface.ip} ({iface.name})")
                super().accept()
                return

        # No selection
        QMessageBox.warning(self, "No Selection", "Please select a network interface.")

    def get_selected_interface(self) -> NetworkInterface:
        """Get the selected network interface."""
        return self.selected_interface


def show_interface_selection_dialog(
    interfaces: list[NetworkInterface], camera_ips: list[str], parent=None
) -> NetworkInterface | None:
    """
    Show dialog to select network interface.

    Args:
        interfaces: List of available network interfaces
        camera_ips: List of camera IP addresses
        parent: Parent widget

    Returns:
        Selected NetworkInterface or None if cancelled
    """
    dialog = NetworkInterfaceDialog(interfaces, camera_ips, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.get_selected_interface()
    return None
