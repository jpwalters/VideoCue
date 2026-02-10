"""
Controller Preferences Dialog
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSlider, QCheckBox, QComboBox, QPushButton, QFormLayout, QSpinBox
)
from PyQt6.QtCore import Qt
from videocue.ui_strings import UIStrings


class ControllerPreferencesDialog(QDialog):
    """Dialog for configuring USB controller preferences"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(UIStrings.DIALOG_PREFERENCES)
        self.setModal(True)
        self.setMinimumWidth(450)

        self.init_ui()
        self.load_preferences()

    def init_ui(self):
        """Initialize the UI"""
        layout = QVBoxLayout(self)

        # Speed Settings Group
        speed_group = QGroupBox("Speed Settings")
        speed_layout = QFormLayout()

        # D-pad speed slider
        dpad_layout = QHBoxLayout()
        self.dpad_slider = QSlider(Qt.Orientation.Horizontal)
        self.dpad_slider.setMinimum(10)
        self.dpad_slider.setMaximum(150)
        self.dpad_slider.setValue(70)
        self.dpad_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.dpad_slider.setTickInterval(10)
        self.dpad_value_label = QLabel("0.7")
        self.dpad_slider.valueChanged.connect(self.update_dpad_label)
        dpad_layout.addWidget(self.dpad_slider)
        dpad_layout.addWidget(self.dpad_value_label)
        speed_layout.addRow("D-Pad Speed:", dpad_layout)

        # Joystick speed slider
        joystick_layout = QHBoxLayout()
        self.joystick_slider = QSlider(Qt.Orientation.Horizontal)
        self.joystick_slider.setMinimum(10)
        self.joystick_slider.setMaximum(150)
        self.joystick_slider.setValue(100)
        self.joystick_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.joystick_slider.setTickInterval(10)
        self.joystick_value_label = QLabel("1.0")
        self.joystick_slider.valueChanged.connect(self.update_joystick_label)
        joystick_layout.addWidget(self.joystick_slider)
        joystick_layout.addWidget(self.joystick_value_label)
        speed_layout.addRow("Joystick Speed:", joystick_layout)

        # Zoom speed slider
        zoom_layout = QHBoxLayout()
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(10)
        self.zoom_slider.setMaximum(150)
        self.zoom_slider.setValue(70)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setTickInterval(10)
        self.zoom_value_label = QLabel("0.7")
        self.zoom_slider.valueChanged.connect(self.update_zoom_label)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.zoom_value_label)
        speed_layout.addRow("Zoom Speed:", zoom_layout)

        speed_group.setLayout(speed_layout)
        layout.addWidget(speed_group)

        # Direction Settings Group
        direction_group = QGroupBox("Direction Settings")
        direction_layout = QVBoxLayout()

        self.invert_vertical_checkbox = QCheckBox("Invert Up/Down (Reverse Y-axis)")
        direction_layout.addWidget(self.invert_vertical_checkbox)

        direction_group.setLayout(direction_layout)
        layout.addWidget(direction_group)

        # Joystick Mode Group
        mode_group = QGroupBox("Joystick Mode")
        mode_layout = QFormLayout()

        self.joystick_mode_combo = QComboBox()
        self.joystick_mode_combo.addItem("Single Joystick (Combined Pan/Tilt)", "single")
        self.joystick_mode_combo.addItem("Dual Joystick (Left=Pan, Right=Tilt)", "dual")
        mode_layout.addRow("Mode:", self.joystick_mode_combo)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Brightness Control Group
        brightness_group = QGroupBox("Brightness Control (Bright Mode Only)")
        brightness_layout = QFormLayout()

        self.brightness_enabled_checkbox = QCheckBox("Enable brightness control")
        brightness_layout.addRow("", self.brightness_enabled_checkbox)

        # Brightness step size
        self.brightness_step_spinbox = QSpinBox()
        self.brightness_step_spinbox.setMinimum(1)
        self.brightness_step_spinbox.setMaximum(10)
        self.brightness_step_spinbox.setValue(1)
        brightness_layout.addRow("Step Size:", self.brightness_step_spinbox)

        # Button mapping for brightness increase
        self.brightness_increase_combo = QComboBox()
        self.brightness_increase_combo.addItem("Button 0 (A/Cross)", 0)
        self.brightness_increase_combo.addItem("Button 1 (B/Circle)", 1)
        self.brightness_increase_combo.addItem("Button 2 (X/Square)", 2)
        self.brightness_increase_combo.addItem("Button 3 (Y/Triangle)", 3)
        self.brightness_increase_combo.addItem("Button 6 (Back/Select)", 6)
        self.brightness_increase_combo.addItem("Button 7 (Start)", 7)
        self.brightness_increase_combo.addItem("Button 8 (Left Stick)", 8)
        self.brightness_increase_combo.addItem("Button 9 (Right Stick)", 9)
        brightness_layout.addRow("Increase Button:", self.brightness_increase_combo)

        # Button mapping for brightness decrease
        self.brightness_decrease_combo = QComboBox()
        self.brightness_decrease_combo.addItem("Button 0 (A/Cross)", 0)
        self.brightness_decrease_combo.addItem("Button 1 (B/Circle)", 1)
        self.brightness_decrease_combo.addItem("Button 2 (X/Square)", 2)
        self.brightness_decrease_combo.addItem("Button 3 (Y/Triangle)", 3)
        self.brightness_decrease_combo.addItem("Button 6 (Back/Select)", 6)
        self.brightness_decrease_combo.addItem("Button 7 (Start)", 7)
        self.brightness_decrease_combo.addItem("Button 8 (Left Stick)", 8)
        self.brightness_decrease_combo.addItem("Button 9 (Right Stick)", 9)
        brightness_layout.addRow("Decrease Button:", self.brightness_decrease_combo)

        brightness_group.setLayout(brightness_layout)
        layout.addWidget(brightness_group)

        # Camera switching group
        switching_group = QGroupBox("Camera Switching")
        switching_layout = QFormLayout()

        self.stop_on_switch_checkbox = QCheckBox("Stop camera movement when switching cameras")
        self.stop_on_switch_checkbox.setToolTip(
            "When enabled, automatically sends STOP command to the previous camera\n"
            "when switching to a different camera. Prevents cameras from continuing\n"
            "to move after you've switched away."
        )
        switching_layout.addRow("", self.stop_on_switch_checkbox)

        switching_group.setLayout(switching_layout)
        layout.addWidget(switching_group)

        # Help text
        help_label = QLabel(
            "Dual Joystick Mode:\n"
            "• Left Stick (Axis 0) = Left/Right movement only\n"
            "• Right Stick (Axis 3) = Up/Down movement only\n\n"
            "Brightness Control:\n"
            "• Only works when camera is in Bright exposure mode\n"
            "• Step Size controls how much each button press changes brightness (0-41 range)\n"
            "• Buttons increase/decrease brightness by the step size\n"
            "• Default: Y=Increase, A=Decrease, Step=1"
        )
        help_label.setStyleSheet("color: gray; font-size: 10px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_preferences)
        save_button.setDefault(True)
        button_layout.addWidget(save_button)

        layout.addLayout(button_layout)

    def update_dpad_label(self, value):
        """Update D-pad speed label"""
        speed = value / 100.0
        self.dpad_value_label.setText(f"{speed:.1f}")

    def update_joystick_label(self, value):
        """Update joystick speed label"""
        speed = value / 100.0
        self.joystick_value_label.setText(f"{speed:.1f}")

    def update_zoom_label(self, value):
        """Update zoom speed label"""
        speed = value / 100.0
        self.zoom_value_label.setText(f"{speed:.1f}")

    def load_preferences(self):
        """Load current preferences from config"""
        usb_config = self.config.get_usb_controller_config()

        # Load speeds
        dpad_speed = usb_config.get("dpad_speed", 0.7)
        self.dpad_slider.setValue(int(dpad_speed * 100))

        joystick_speed = usb_config.get("joystick_speed", 1.0)
        self.joystick_slider.setValue(int(joystick_speed * 100))

        zoom_speed = usb_config.get("zoom_speed", 0.7)
        self.zoom_slider.setValue(int(zoom_speed * 100))

        # Load invert
        invert = usb_config.get("invert_vertical", False)
        self.invert_vertical_checkbox.setChecked(invert)

        # Load joystick mode
        mode = usb_config.get("joystick_mode", "single")
        index = self.joystick_mode_combo.findData(mode)
        if index >= 0:
            self.joystick_mode_combo.setCurrentIndex(index)

        # Load brightness control settings
        brightness_enabled = usb_config.get("brightness_enabled", True)
        self.brightness_enabled_checkbox.setChecked(brightness_enabled)

        # Load stop on camera switch setting
        stop_on_switch = usb_config.get("stop_on_camera_switch", True)
        self.stop_on_switch_checkbox.setChecked(stop_on_switch)

        brightness_step = usb_config.get("brightness_step", 1)
        self.brightness_step_spinbox.setValue(brightness_step)

        brightness_increase = usb_config.get("brightness_increase_button", 3)
        index = self.brightness_increase_combo.findData(brightness_increase)
        if index >= 0:
            self.brightness_increase_combo.setCurrentIndex(index)

        brightness_decrease = usb_config.get("brightness_decrease_button", 0)
        index = self.brightness_decrease_combo.findData(brightness_decrease)
        if index >= 0:
            self.brightness_decrease_combo.setCurrentIndex(index)

    def save_preferences(self):
        """Save preferences to config"""
        usb_config = self.config.get_usb_controller_config()

        # Save speeds
        usb_config["dpad_speed"] = self.dpad_slider.value() / 100.0
        usb_config["joystick_speed"] = self.joystick_slider.value() / 100.0
        usb_config["zoom_speed"] = self.zoom_slider.value() / 100.0

        # Save invert
        usb_config["invert_vertical"] = self.invert_vertical_checkbox.isChecked()

        # Save joystick mode
        usb_config["joystick_mode"] = self.joystick_mode_combo.currentData()

        # Save brightness control settings
        usb_config["brightness_enabled"] = self.brightness_enabled_checkbox.isChecked()
        usb_config["brightness_step"] = self.brightness_step_spinbox.value()
        usb_config["brightness_increase_button"] = self.brightness_increase_combo.currentData()
        usb_config["brightness_decrease_button"] = self.brightness_decrease_combo.currentData()

        # Save stop on camera switch setting
        usb_config["stop_on_camera_switch"] = self.stop_on_switch_checkbox.isChecked()

        self.config.save()
        self.accept()
