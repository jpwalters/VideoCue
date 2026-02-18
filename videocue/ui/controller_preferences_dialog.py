"""
Controller Preferences Dialog
"""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from videocue.ui_strings import UIStrings

logger = logging.getLogger(__name__)


class ControllerPreferencesDialog(QDialog):
    """Dialog for configuring USB controller preferences"""

    def __init__(self, config, parent=None, usb_controller=None):
        super().__init__(parent)
        self.config = config
        self.usb_controller = usb_controller
        self.save_button = None  # Will be set in init_ui

        logger.debug("ControllerPreferencesDialog: Starting initialization...")
        self.setWindowTitle(UIStrings.DIALOG_PREFERENCES)
        self.setModal(False)  # NON-MODAL so signals are processed while dialog is visible
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        self.init_ui()
        self.load_preferences()

        logger.debug("ControllerPreferencesDialog: UI initialized, setting stylesheet...")
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

        logger.debug("ControllerPreferencesDialog: Connecting controller signals...")
        # Connect controller signals for navigation and adjustment while dialog is open
        if self.usb_controller:
            logger.info("ControllerPreferencesDialog: USB controller found, connecting signals...")
            # A button to save
            self.usb_controller.button_a_pressed.connect(self.on_a_button_pressed)
            logger.debug("ControllerPreferencesDialog: Connected button_a_pressed signal")
            # D-Pad for navigation and slider adjustment
            self.usb_controller.movement_direction.connect(self.on_movement_direction)
            logger.debug("ControllerPreferencesDialog: Connected movement_direction signal")
            # X button to cancel
            self.usb_controller.stop_movement.connect(self.on_x_button_pressed)
            logger.debug("ControllerPreferencesDialog: Connected stop_movement signal for X button")
            # B button to toggle checkboxes
            self.usb_controller.focus_one_push.connect(self.on_b_button_pressed)
            logger.debug(
                "ControllerPreferencesDialog: Connected focus_one_push signal for B button"
            )
        else:
            logger.warning("ControllerPreferencesDialog: No USB controller provided!")
        logger.debug("ControllerPreferencesDialog: Initialization complete, ready for display")

    def init_ui(self):
        """Initialize the UI"""
        main_layout = QVBoxLayout(self)

        # Controller usage instructions
        instructions_label = QLabel(
            "Controller Usage:\n"
            "• D-Pad Up/Down = Navigate between controls\n"
            "• D-Pad Left/Right = Adjust slider values\n"
            "• A Button = Save and close this window\n"
            "• B Button = Toggle checkbox (when focused)\n"
            "• X Button = Cancel and close this window\n"
            "• Orange border shows which control is selected"
        )
        instructions_label.setStyleSheet(
            "font-size: 9px; color: #888; background-color: #2a2a2a; padding: 8px; border-radius: 4px;"
        )
        main_layout.addWidget(instructions_label)

        # Scrollable content area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
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

        # B Button Control Group
        b_button_group = QGroupBox(UIStrings.GROUP_FOCUS_BUTTON)
        b_button_layout = QFormLayout()

        # Button mapping for B button (focus one-push)
        self.focus_one_push_button_combo = QComboBox()
        self.focus_one_push_button_combo.addItem("None", None)
        self.focus_one_push_button_combo.addItem("Button 0 (A/Cross)", 0)
        self.focus_one_push_button_combo.addItem("Button 1 (B/Circle)", 1)
        self.focus_one_push_button_combo.addItem("Button 2 (X/Square)", 2)
        self.focus_one_push_button_combo.addItem("Button 3 (Y/Triangle)", 3)
        self.focus_one_push_button_combo.addItem("Button 6 (Back/Select)", 6)
        self.focus_one_push_button_combo.addItem("Button 7 (Start)", 7)
        self.focus_one_push_button_combo.addItem("Button 8 (Left Stick)", 8)
        self.focus_one_push_button_combo.addItem("Button 9 (Right Stick)", 9)
        self.focus_one_push_button_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        b_button_layout.addRow(UIStrings.LBL_FOCUS_BUTTON_MAPPING, self.focus_one_push_button_combo)

        b_button_group.setLayout(b_button_layout)
        layout.addWidget(b_button_group)

        # X Button Control Group
        x_button_group = QGroupBox(UIStrings.GROUP_STOP_BUTTON)
        x_button_layout = QFormLayout()

        # Button mapping for X button (stop movement)
        self.stop_movement_button_combo = QComboBox()
        self.stop_movement_button_combo.addItem("None", None)
        self.stop_movement_button_combo.addItem("Button 0 (A/Cross)", 0)
        self.stop_movement_button_combo.addItem("Button 1 (B/Circle)", 1)
        self.stop_movement_button_combo.addItem("Button 2 (X/Square)", 2)
        self.stop_movement_button_combo.addItem("Button 3 (Y/Triangle)", 3)
        self.stop_movement_button_combo.addItem("Button 6 (Back/Select)", 6)
        self.stop_movement_button_combo.addItem("Button 7 (Start)", 7)
        self.stop_movement_button_combo.addItem("Button 8 (Left Stick)", 8)
        self.stop_movement_button_combo.addItem("Button 9 (Right Stick)", 9)
        self.stop_movement_button_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        x_button_layout.addRow(UIStrings.LBL_STOP_BUTTON_MAPPING, self.stop_movement_button_combo)

        x_button_group.setLayout(x_button_layout)
        layout.addWidget(x_button_group)

        # Menu Button Control Group
        menu_button_group = QGroupBox(UIStrings.GROUP_MENU_BUTTON)
        menu_button_layout = QFormLayout()

        # Button mapping for Menu button (controller preferences)
        self.menu_button_combo = QComboBox()
        self.menu_button_combo.addItem("None", None)
        self.menu_button_combo.addItem("Button 0 (A/Cross)", 0)
        self.menu_button_combo.addItem("Button 1 (B/Circle)", 1)
        self.menu_button_combo.addItem("Button 2 (X/Square)", 2)
        self.menu_button_combo.addItem("Button 3 (Y/Triangle)", 3)
        self.menu_button_combo.addItem("Button 6 (Back/Select)", 6)
        self.menu_button_combo.addItem("Button 7 (Start)", 7)
        self.menu_button_combo.addItem("Button 8 (Left Stick)", 8)
        self.menu_button_combo.addItem("Button 9 (Right Stick)", 9)
        self.menu_button_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        menu_button_layout.addRow(UIStrings.LBL_MENU_BUTTON_MAPPING, self.menu_button_combo)

        menu_button_group.setLayout(menu_button_layout)
        layout.addWidget(menu_button_group)

        # Video Streaming Group
        video_group = QGroupBox("Video Streaming")
        video_layout = QFormLayout()

        self.ndi_video_enabled_checkbox = QCheckBox(
            "Enable NDI video streaming (requires NDI Runtime)"
        )
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

        # Application group
        app_group = QGroupBox("Application")
        app_layout = QFormLayout()

        self.single_instance_checkbox = QCheckBox("Enable single instance mode (requires restart)")
        self.single_instance_checkbox.setToolTip(
            "When enabled, only one instance of VideoCue can run at a time.\n"
            "When disabled, multiple instances can run simultaneously.\n"
            "This setting requires restarting the application to take effect."
        )
        self.single_instance_checkbox.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        app_layout.addRow("", self.single_instance_checkbox)

        app_group.setLayout(app_layout)
        layout.addWidget(app_group)

        # Quick tips
        tips_label = QLabel(
            "Quick Tips:\n"
            "• Most users only need to adjust the three speed sliders above\n"
            "• Use D-Pad Up/Down to navigate between controls (or Tab with keyboard)\n"
            "• Use D-Pad Left/Right to adjust slider values (or Arrow keys with keyboard)\n"
            "• Press A button or spacebar to toggle checkboxes\n"
            "• Press A button to save and close, or press Enter (keyboard)"
        )
        tips_label.setStyleSheet("color: #aaa; font-size: 9px; margin-top: 10px;")
        tips_label.setWordWrap(True)
        layout.addWidget(tips_label)

        layout.addStretch()

        # Add scroll area to main layout
        self.scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(self.scroll_area)

        # Buttons (large, easy to press)
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel (X)")
        cancel_button.setMinimumHeight(40)
        cancel_button.setMinimumWidth(100)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        self.cancel_button = cancel_button  # Store reference for X button handler

        save_button = QPushButton("Save (A)")
        save_button.setMinimumHeight(40)
        save_button.setMinimumWidth(100)
        save_button.clicked.connect(self.save_preferences)
        save_button.setDefault(True)
        save_button.setStyleSheet(
            "QPushButton { font-weight: bold; background-color: #0d47a1; color: white; }"
            + "QPushButton:focus { border: 2px solid #FF8800; }"
        )
        save_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.save_button = save_button  # Store reference for A button handler
        button_layout.addWidget(save_button)

        main_layout.addLayout(button_layout)

        # Set initial focus to first speed slider
        self.dpad_slider.setFocus()

        # Connect combobox signals to update button availability
        self.brightness_increase_combo.currentIndexChanged.connect(self.update_button_availability)
        self.brightness_decrease_combo.currentIndexChanged.connect(self.update_button_availability)
        self.focus_one_push_button_combo.currentIndexChanged.connect(
            self.update_button_availability
        )
        self.stop_movement_button_combo.currentIndexChanged.connect(self.update_button_availability)
        self.menu_button_combo.currentIndexChanged.connect(self.update_button_availability)

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

    def update_button_availability(self):
        """Update which button options are enabled/disabled based on selections"""
        # Get all currently selected buttons (excluding None)
        selected_buttons = {}
        selected_buttons["brightness_increase"] = self.brightness_increase_combo.currentData()
        selected_buttons["brightness_decrease"] = self.brightness_decrease_combo.currentData()
        selected_buttons["focus_one_push"] = self.focus_one_push_button_combo.currentData()
        selected_buttons["stop_movement"] = self.stop_movement_button_combo.currentData()
        selected_buttons["menu"] = self.menu_button_combo.currentData()

        # List of all button comboboxes
        all_combos = [
            (self.brightness_increase_combo, "brightness_increase"),
            (self.brightness_decrease_combo, "brightness_decrease"),
            (self.focus_one_push_button_combo, "focus_one_push"),
            (self.stop_movement_button_combo, "stop_movement"),
            (self.menu_button_combo, "menu"),
        ]

        # Update each combobox to disable already-selected buttons
        for combo, combo_key in all_combos:
            # Get the model of the combobox
            model = combo.model()
            if model is None:
                continue

            for row in range(combo.count()):
                item = model.item(row)
                if item is None:
                    continue

                button_value = combo.itemData(row)

                # Always enable None items
                if button_value is None:
                    item.setEnabled(True)
                    continue

                # Check if this button is selected by another combo
                is_used_elsewhere = False
                for _other_combo, other_key in all_combos:
                    if other_key != combo_key:  # Don't compare with itself
                        other_value = selected_buttons[other_key]
                        # Only compare non-None values
                        if other_value is not None and other_value == button_value:
                            is_used_elsewhere = True
                            break

                # Enable/disable the item based on whether it's used elsewhere
                item.setEnabled(not is_used_elsewhere)

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

        # Load B button (focus one-push) settings
        focus_one_push_button = usb_config.get("focus_one_push_button", 1)
        index = self.focus_one_push_button_combo.findData(focus_one_push_button)
        if index >= 0:
            self.focus_one_push_button_combo.setCurrentIndex(index)

        # Load X button (stop movement) settings
        stop_movement_button = usb_config.get("stop_movement_button", 2)
        index = self.stop_movement_button_combo.findData(stop_movement_button)
        if index >= 0:
            self.stop_movement_button_combo.setCurrentIndex(index)

        # Load Menu button settings
        menu_button = usb_config.get("menu_button", 7)
        index = self.menu_button_combo.findData(menu_button)
        if index >= 0:
            self.menu_button_combo.setCurrentIndex(index)

        # Load NDI video enabled setting
        ndi_video_enabled = self.config.get_ndi_video_enabled()
        self.ndi_video_enabled_checkbox.setChecked(ndi_video_enabled)

        # Load single instance mode setting
        single_instance_mode = self.config.get_single_instance_mode()
        self.single_instance_checkbox.setChecked(single_instance_mode)

        # Update button availability after loading all preferences
        self.update_button_availability()

    def on_a_button_pressed(self):
        """Handle A button press to save preferences"""
        self.save_preferences()

    def on_x_button_pressed(self):
        """Handle X button press to cancel preferences"""
        self.reject()

    def on_b_button_pressed(self):
        """Handle B button press to toggle focused checkbox"""
        focused = self.focusWidget()
        if isinstance(focused, QCheckBox):
            focused.setChecked(not focused.isChecked())

    def on_movement_direction(self, direction, speed):
        """Handle D-pad for field navigation and slider adjustment"""
        from videocue.controllers.usb_controller import MovementDirection

        if direction == MovementDirection.UP:
            self.focusPreviousChild()
            new_focused = self.focusWidget()
            # Ensure newly focused widget is visible in scroll area
            if new_focused and self.scroll_area:
                self.scroll_area.ensureWidgetVisible(new_focused)
        elif direction == MovementDirection.DOWN:
            self.focusNextChild()
            new_focused = self.focusWidget()
            # Ensure newly focused widget is visible in scroll area
            if new_focused and self.scroll_area:
                self.scroll_area.ensureWidgetVisible(new_focused)
        elif direction == MovementDirection.RIGHT:
            focused = self.focusWidget()
            if isinstance(focused, QSlider):
                focused.setValue(min(focused.value() + 5, focused.maximum()))
        elif direction == MovementDirection.LEFT:
            focused = self.focusWidget()
            if isinstance(focused, QSlider):
                focused.setValue(max(focused.value() - 5, focused.minimum()))

    def on_brightness_increase(self):
        """Increase slider value when brightness_increase button pressed"""
        focused = self.focusWidget()
        if isinstance(focused, QSlider):
            focused.setValue(min(focused.value() + 5, focused.maximum()))

    def on_brightness_decrease(self):
        """Decrease slider value when brightness_decrease button pressed"""
        focused = self.focusWidget()
        if isinstance(focused, QSlider):
            focused.setValue(max(focused.value() - 5, focused.minimum()))

    def closeEvent(self, event):
        """Clean up when dialog closes"""
        # Disconnect all controller signals when dialog closes
        if self.usb_controller:
            try:
                self.usb_controller.button_a_pressed.disconnect(self.on_a_button_pressed)
                self.usb_controller.movement_direction.disconnect(self.on_movement_direction)
                self.usb_controller.stop_movement.disconnect(self.on_x_button_pressed)
                self.usb_controller.focus_one_push.disconnect(self.on_b_button_pressed)
            except TypeError:
                pass  # Already disconnected
        super().closeEvent(event)

    def showEvent(self, event):
        """Called when dialog becomes visible"""
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

        # Save B button (focus one-push) settings
        usb_config["focus_one_push_button"] = self.focus_one_push_button_combo.currentData()

        # Save X button (stop movement) settings
        usb_config["stop_movement_button"] = self.stop_movement_button_combo.currentData()

        # Save Menu button settings
        usb_config["menu_button"] = self.menu_button_combo.currentData()

        # Save stop on camera switch setting
        usb_config["stop_on_camera_switch"] = self.stop_on_switch_checkbox.isChecked()

        # Save NDI video enabled setting
        self.config.set_ndi_video_enabled(self.ndi_video_enabled_checkbox.isChecked())

        # Save single instance mode setting
        self.config.set_single_instance_mode(self.single_instance_checkbox.isChecked())

        self.config.save()

        # Close dialog (emits finished signal)
        self.accept()
