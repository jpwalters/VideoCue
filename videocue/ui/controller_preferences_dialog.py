"""
Controller Preferences Dialog
"""
import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QSlider, QCheckBox, QComboBox, QPushButton, QFormLayout, QSpinBox, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt
from videocue.ui_strings import UIStrings

logger = logging.getLogger(__name__)


class ControllerPreferencesDialog(QDialog):
    """Dialog for configuring USB controller preferences"""

    def __init__(self, config, parent=None, usb_controller=None):
        super().__init__(parent)
        self.config = config
        self.usb_controller = usb_controller
        self.save_button = None  # Will be set in init_ui
        
        print("[PrefsDialog.__init__] Starting...")
        self.setWindowTitle(UIStrings.DIALOG_PREFERENCES)
        self.setModal(False)  # NON-MODAL so signals are processed while dialog is visible
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        self.init_ui()
        self.load_preferences()
        
        print("[PrefsDialog.__init__] UI initialized, setting stylesheet...")
        # Set up orange focus stylesheet
        self.setStyleSheet("""
            QSlider:focus, QCheckBox:focus, QComboBox:focus, QSpinBox:focus, QPushButton:focus {
                border: 2px solid #FF8800;
                border-radius: 4px;
                outline: none;
            }
            QSlider {
                border: 1px solid transparent;
                border-radius: 4px;
            }
        """)
        
        print("[PrefsDialog.__init__] Connecting controller signals...")
        # Connect controller signals for navigation and adjustment while dialog is open
        if self.usb_controller:
            print("[PrefsDialog] USB controller found, connecting signals...")
            logger.info("[PrefsDialog] USB controller found, connecting signals...")
            # B button to save
            self.usb_controller.focus_one_push.connect(self.on_b_button_pressed)
            print("[PrefsDialog] Connected focus_one_push signal")
            logger.info("[PrefsDialog] Connected focus_one_push signal")
            # Navigation buttons (D-Pad and Joystick for Tab navigation)
            self.usb_controller.prev_camera.connect(self.navigate_previous)
            print("[PrefsDialog] Connected prev_camera signal")
            logger.info("[PrefsDialog] Connected prev_camera signal")
            self.usb_controller.next_camera.connect(self.navigate_next)
            print("[PrefsDialog] Connected next_camera signal")
            logger.info("[PrefsDialog] Connected next_camera signal")
            # Brightness buttons for slider adjustment
            self.usb_controller.brightness_increase.connect(self.on_brightness_increase)
            print("[PrefsDialog] Connected brightness_increase signal")
            logger.info("[PrefsDialog] Connected brightness_increase signal")
            self.usb_controller.brightness_decrease.connect(self.on_brightness_decrease)
            print("[PrefsDialog] Connected brightness_decrease signal")
            logger.info("[PrefsDialog] Connected brightness_decrease signal")
        else:
            print("[PrefsDialog] ERROR: No USB controller provided!")
            logger.warning("[PrefsDialog] No USB controller provided!")
        print("[PrefsDialog.__init__] Complete, ready for exec()")

    def init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)

        # Controller usage instructions
        instructions_label = QLabel(
            "Controller Usage:\n"
            "• LB/RB (prev/next camera buttons) = Navigate between controls\n"
            "• A Button = Toggle checkboxes\n"
            "• Y Button (brightness+) = Increase slider values\n"
            "• X Button (brightness-) = Decrease slider values\n"
            "• B Button = Save and close this window\n"
            "• Orange border shows which control is selected"
        )
        instructions_label.setStyleSheet("font-size: 9px; color: #888; background-color: #2a2a2a; padding: 8px; border-radius: 4px;")
        main_layout.addWidget(instructions_label)

        # Scrollable content area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)

        # Speed Settings Group (moved to top, most important)
        speed_group = QGroupBox("Speed Settings (Adjust with Arrow Keys Left/Right)")
        speed_layout = QFormLayout()

        # D-pad speed slider
        dpad_layout = QHBoxLayout()
        self.dpad_slider = QSlider(Qt.Orientation.Horizontal)
        self.dpad_slider.setMinimum(10)
        self.dpad_slider.setMaximum(150)
        self.dpad_slider.setValue(70)
        self.dpad_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.dpad_slider.setTickInterval(10)
        self.dpad_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.dpad_value_label = QLabel("0.7")
        self.dpad_value_label.setMinimumWidth(40)
        self.dpad_slider.valueChanged.connect(self.update_dpad_label)
        dpad_layout.addWidget(self.dpad_slider, 1)
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
        self.joystick_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.joystick_value_label = QLabel("1.0")
        self.joystick_value_label.setMinimumWidth(40)
        self.joystick_slider.valueChanged.connect(self.update_joystick_label)
        joystick_layout.addWidget(self.joystick_slider, 1)
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
        self.zoom_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.zoom_value_label = QLabel("0.7")
        self.zoom_value_label.setMinimumWidth(40)
        self.zoom_slider.valueChanged.connect(self.update_zoom_label)
        zoom_layout.addWidget(self.zoom_slider, 1)
        zoom_layout.addWidget(self.zoom_value_label)
        speed_layout.addRow("Zoom Speed:", zoom_layout)

        speed_group.setLayout(speed_layout)
        speed_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        layout.addWidget(speed_group)

        # Direction Settings Group
        direction_group = QGroupBox("Direction Settings")
        direction_layout = QVBoxLayout()

        self.invert_vertical_checkbox = QCheckBox("Invert Up/Down (Reverse Y-axis)")
        self.invert_vertical_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        direction_layout.addWidget(self.invert_vertical_checkbox)

        direction_group.setLayout(direction_layout)
        layout.addWidget(direction_group)

        # Joystick Mode Group
        mode_group = QGroupBox("Joystick Mode")
        mode_layout = QFormLayout()

        self.joystick_mode_combo = QComboBox()
        self.joystick_mode_combo.addItem("Single Joystick (Combined Pan/Tilt)", "single")
        self.joystick_mode_combo.addItem("Dual Joystick (Left=Pan, Right=Tilt)", "dual")
        self.joystick_mode_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        mode_layout.addRow("Mode:", self.joystick_mode_combo)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Brightness Control Group
        brightness_group = QGroupBox("Brightness Control (Bright Mode Only)")
        brightness_layout = QFormLayout()

        self.brightness_enabled_checkbox = QCheckBox("Enable brightness control")
        self.brightness_enabled_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        brightness_layout.addRow("", self.brightness_enabled_checkbox)

        # Brightness step size
        self.brightness_step_spinbox = QSpinBox()
        self.brightness_step_spinbox.setMinimum(1)
        self.brightness_step_spinbox.setMaximum(10)
        self.brightness_step_spinbox.setValue(1)
        self.brightness_step_spinbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.brightness_increase_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        self.brightness_decrease_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        brightness_layout.addRow("Decrease Button:", self.brightness_decrease_combo)

        brightness_group.setLayout(brightness_layout)
        layout.addWidget(brightness_group)

        # Video Streaming Group
        video_group = QGroupBox("Video Streaming")
        video_layout = QFormLayout()

        self.ndi_video_enabled_checkbox = QCheckBox("Enable NDI video streaming (requires NDI Runtime)")
        self.ndi_video_enabled_checkbox.setToolTip(
            "Enable or disable NDI video streaming globally.\n"
            "When disabled, cameras will operate in IP control mode only.\n"
            "Disabling can improve performance on systems with limited resources.\n"
            "Requires NDI Runtime to be installed."
        )
        self.ndi_video_enabled_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        video_layout.addRow("", self.ndi_video_enabled_checkbox)

        video_group.setLayout(video_layout)
        layout.addWidget(video_group)

        # Camera switching group
        switching_group = QGroupBox("Camera Switching")
        switching_layout = QFormLayout()

        self.stop_on_switch_checkbox = QCheckBox("Stop camera movement when switching cameras")
        self.stop_on_switch_checkbox.setToolTip(
            "When enabled, automatically sends STOP command to the previous camera\n"
            "when switching to a different camera. Prevents cameras from continuing\n"
            "to move after you've switched away."
        )
        self.stop_on_switch_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        switching_layout.addRow("", self.stop_on_switch_checkbox)

        switching_group.setLayout(switching_layout)
        layout.addWidget(switching_group)

        # Quick tips
        tips_label = QLabel(
            "Quick Tips:\n"
            "• Most users only need to adjust the three speed sliders above\n"
            "• Use Tab to navigate, Arrow keys to adjust slider values\n"
            "• Press Space to toggle checkboxes\n"
            "• Press Enter or click Save when done"
        )
        tips_label.setStyleSheet("color: #aaa; font-size: 9px; margin-top: 10px;")
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        layout.addStretch()

        # Add scroll area to main layout
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        # Buttons (large, easy to press)
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setMinimumHeight(40)
        cancel_button.setMinimumWidth(100)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        save_button = QPushButton("Save")
        save_button.setMinimumHeight(40)
        save_button.setMinimumWidth(100)
        save_button.clicked.connect(self.save_preferences)
        save_button.setDefault(True)
        save_button.setStyleSheet("QPushButton { font-weight: bold; background-color: #0d47a1; color: white; }"+
                                   "QPushButton:focus { border: 2px solid #FF8800; }")
        save_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.save_button = save_button  # Store reference for B button handler
        button_layout.addWidget(save_button)

        main_layout.addLayout(button_layout)

        # Set initial focus to first speed slider
        self.dpad_slider.setFocus()

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

        # Load NDI video enabled setting
        ndi_video_enabled = self.config.get_ndi_video_enabled()
        self.ndi_video_enabled_checkbox.setChecked(ndi_video_enabled)

    def on_b_button_pressed(self):
        """Handle B button press to save preferences"""
        print("[PrefsDialog.on_b_button_pressed] === SIGNAL HANDLER CALLED ===")
        logger.info("[PrefsDialog] B button pressed, saving preferences...")
        self.save_preferences()

    def navigate_previous(self):
        """Navigate to previous control (Shift+Tab)"""
        print("[PrefsDialog.navigate_previous] === SIGNAL HANDLER CALLED ===")
        logger.info("[PrefsDialog] LB button pressed, navigating to previous control")
        focused = self.focusWidget()
        print(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        logger.info(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        self.focusPreviousChild()
        new_focused = self.focusWidget()
        print(f"[PrefsDialog] New focused widget: {type(new_focused).__name__ if new_focused else 'None'}")
        logger.info(f"[PrefsDialog] New focused widget: {type(new_focused).__name__ if new_focused else 'None'}")

    def navigate_next(self):
        """Navigate to next control (Tab)"""
        print("[PrefsDialog.navigate_next] === SIGNAL HANDLER CALLED ===")
        logger.info("[PrefsDialog] RB button pressed, navigating to next control")
        focused = self.focusWidget()
        print(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        logger.info(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        self.focusNextChild()
        new_focused = self.focusWidget()
        print(f"[PrefsDialog] New focused widget: {type(new_focused).__name__ if new_focused else 'None'}")
        logger.info(f"[PrefsDialog] New focused widget: {type(new_focused).__name__ if new_focused else 'None'}")

    def on_brightness_increase(self):
        """Increase slider value when brightness_increase button pressed"""
        print("[PrefsDialog.on_brightness_increase] === SIGNAL HANDLER CALLED ===")
        logger.info("[PrefsDialog] Y button pressed (brightness_increase)")
        focused = self.focusWidget()
        print(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        logger.info(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        if isinstance(focused, QSlider):
            old_val = focused.value()
            focused.setValue(min(focused.value() + 5, focused.maximum()))
            print(f"[PrefsDialog] Slider adjusted: {old_val} -> {focused.value()}")
            logger.info(f"[PrefsDialog] Slider adjusted: {old_val} -> {focused.value()}")
        else:
            print(f"[PrefsDialog] Focused widget is not a slider, ignoring")
            logger.info(f"[PrefsDialog] Focused widget is not a slider, ignoring")

    def on_brightness_decrease(self):
        """Decrease slider value when brightness_decrease button pressed"""
        print("[PrefsDialog.on_brightness_decrease] === SIGNAL HANDLER CALLED ===")
        logger.info("[PrefsDialog] X button pressed (brightness_decrease)")
        focused = self.focusWidget()
        print(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        logger.info(f"[PrefsDialog] Currently focused widget: {type(focused).__name__ if focused else 'None'}")
        if isinstance(focused, QSlider):
            old_val = focused.value()
            focused.setValue(max(focused.value() - 5, focused.minimum()))
            print(f"[PrefsDialog] Slider adjusted: {old_val} -> {focused.value()}")
            logger.info(f"[PrefsDialog] Slider adjusted: {old_val} -> {focused.value()}")
        else:
            print(f"[PrefsDialog] Focused widget is not a slider, ignoring")
            logger.info(f"[PrefsDialog] Focused widget is not a slider, ignoring")

    def closeEvent(self, event):
        """Clean up when dialog closes"""
        print("[PrefsDialog.closeEvent] Dialog closing...")
        # Disconnect all controller signals when dialog closes
        if self.usb_controller:
            try:
                self.usb_controller.focus_one_push.disconnect(self.on_b_button_pressed)
                self.usb_controller.prev_camera.disconnect(self.navigate_previous)
                self.usb_controller.next_camera.disconnect(self.navigate_next)
                self.usb_controller.brightness_increase.disconnect(self.on_brightness_increase)
                self.usb_controller.brightness_decrease.disconnect(self.on_brightness_decrease)
                print("[PrefsDialog.closeEvent] Disconnected all signals")
            except TypeError:
                pass  # Already disconnected
        super().closeEvent(event)
        print("[PrefsDialog.closeEvent] Dialog close complete")

    def showEvent(self, event):
        """Called when dialog becomes visible"""
        print("[PrefsDialog.showEvent] Dialog is now VISIBLE and RESPONSIVE, ready for controller input...")
        logger.info("[PrefsDialog.showEvent] Dialog is now VISIBLE and RESPONSIVE, ready for controller input...")
        super().showEvent(event)

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

        # Save NDI video enabled setting
        self.config.set_ndi_video_enabled(self.ndi_video_enabled_checkbox.isChecked())

        self.config.save()
        
        # Close dialog (emits finished signal)
        self.accept()
        self.accept()
