"""
USB game controller support using pygame
"""
from enum import Enum
import os
import logging
# Suppress pygame welcome message
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
import pygame
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from videocue.exceptions import USBControllerNotFoundError
from videocue.constants import HardwareConstants

logger = logging.getLogger(__name__)


class MovementDirection(Enum):
    """8-direction movement enumeration"""
    STOP = 0
    UP = 1
    DOWN = 2
    LEFT = 3
    RIGHT = 4
    UP_LEFT = 5
    UP_RIGHT = 6
    DOWN_LEFT = 7
    DOWN_RIGHT = 8


class USBController(QObject):
    """
    USB game controller manager with hotplug detection.
    Polls pygame joystick events and emits PyQt signals.
    """

    # Signals
    connected = pyqtSignal(str)  # Emits controller name
    disconnected = pyqtSignal()
    button_pressed = pyqtSignal(int)  # Button index
    button_released = pyqtSignal(int)
    axis_moved = pyqtSignal(int, float)  # Axis index, value (-1.0 to 1.0)
    movement_direction = pyqtSignal(object, float)  # MovementDirection enum, speed
    zoom_in = pyqtSignal(float)  # Speed (0.0 to 1.0)
    zoom_out = pyqtSignal(float)
    zoom_stop = pyqtSignal()
    stop_movement = pyqtSignal()  # X button for stop
    reconnect_requested = pyqtSignal()  # B button for reconnect
    prev_camera = pyqtSignal()
    next_camera = pyqtSignal()
    brightness_increase = pyqtSignal()
    brightness_decrease = pyqtSignal()

    def __init__(self, config=None):
        super().__init__()

        self.config = config

        # Initialize pygame with timeout protection
        try:
            # Set environment variable to make pygame quieter
            os.environ['SDL_AUDIODRIVER'] = 'dummy'  # Disable audio to prevent hangs
            os.environ['SDL_VIDEODRIVER'] = 'dummy'  # Use dummy video driver for event system
            
            pygame.init()
            pygame.joystick.init()
            logger.info("pygame initialized successfully")
        except Exception as e:
            logger.error(f"pygame initialization failed: {e}")

        self.joystick = None
        self._axis_x = 0.0  # Left stick X (axis 0)
        self._axis_y = 0.0  # Left stick Y (axis 1)
        self._axis_rx = 0.0  # Right stick X (axis 2)
        self._axis_ry = 0.0  # Right stick Y (axis 3)
        self._current_direction = MovementDirection.STOP

        # Event polling timer (60 Hz)
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_events)
        self.poll_timer.start(HardwareConstants.USB_POLL_RATE_MS)  # ~60 FPS

        # Hotplug detection timer (5 seconds)
        self.hotplug_timer = QTimer()
        self.hotplug_timer.timeout.connect(self._check_hotplug)
        self.hotplug_timer.start(HardwareConstants.USB_HOTPLUG_CHECK_MS)

        # Initial controller check
        self._check_hotplug()

    def _check_hotplug(self) -> None:
        """Check for newly connected/disconnected controllers"""
        try:
            # Don't quit/reinit joystick module - causes event queue corruption
            count = pygame.joystick.get_count()

            if count > 0 and self.joystick is None:
                # Controller connected
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                name = self.joystick.get_name()
                logger.info(f"USB controller connected: {name}")
                self.connected.emit(name)

            elif count == 0 and self.joystick is not None:
                # Controller disconnected
                logger.info("USB controller disconnected")
                self.joystick = None
                self.disconnected.emit()
                self._reset_state()

        except Exception as e:
            logger.warning(f"Hotplug check error: {e}")

    def _poll_events(self) -> None:
        """Poll pygame events and emit signals"""
        if self.joystick is None:
            return

        try:
            # CRITICAL: pump() must be called before get() for some controllers
            pygame.event.pump()

            # Filter to only joystick events to avoid pygame internal errors
            event_types = [
                pygame.JOYBUTTONDOWN,
                pygame.JOYBUTTONUP,
                pygame.JOYAXISMOTION,
                pygame.JOYHATMOTION,
                pygame.JOYDEVICEADDED,
                pygame.JOYDEVICEREMOVED
            ]

            events = pygame.event.get(event_types)

            for event in events:
                try:
                    if event.type == pygame.JOYBUTTONDOWN:
                        self._handle_button_down(event.button)

                    elif event.type == pygame.JOYBUTTONUP:
                        self._handle_button_up(event.button)

                    elif event.type == pygame.JOYAXISMOTION:
                        self._handle_axis_motion(event.axis, event.value)

                    elif event.type == pygame.JOYHATMOTION:
                        self._handle_hat_motion(event.hat, event.value)

                    elif event.type == pygame.JOYDEVICEADDED:
                        logger.debug("Joystick device added")

                    elif event.type == pygame.JOYDEVICEREMOVED:
                        logger.debug("Joystick device removed")

                except Exception as e:
                    logger.warning(f"Error handling event {event.type}: {e}")

        except Exception as e:
            logger.error(f"Error in polling loop: {e}")
            # Clear the event queue on error to prevent further corruption
            try:
                pygame.event.clear()
            except:
                pass

    def _handle_button_down(self, button: int):
        """Handle button press"""
        self.button_pressed.emit(button)

        # Get brightness settings from config
        brightness_enabled = False
        brightness_increase_button = 3  # Default Y button
        brightness_decrease_button = 0  # Default A button

        if self.config:
            usb_config = self.config.get_usb_controller_config()
            brightness_enabled = usb_config.get("brightness_enabled", True)
            brightness_increase_button = usb_config.get("brightness_increase_button", 3)
            brightness_decrease_button = usb_config.get("brightness_decrease_button", 0)

        # Brightness control (only if enabled)
        if brightness_enabled:
            if button == brightness_increase_button:
                self.brightness_increase.emit()
                return  # Don't process other button actions
            elif button == brightness_decrease_button:
                self.brightness_decrease.emit()
                return  # Don't process other button actions
        
        # Button 1 = B button (reconnect when camera disconnected)
        if button == 1:
            self.reconnect_requested.emit()

        # Button 2 = X button (stop movement)
        elif button == 2:
            self.stop_movement.emit()

        # Button 4 = LB/L1 (prev camera)
        elif button == 4:
            self.prev_camera.emit()

        # Button 5 = RB/R1 (next camera)
        elif button == 5:
            self.next_camera.emit()

    def _handle_button_up(self, button: int):
        """Handle button release"""
        self.button_released.emit(button)

    def _handle_axis_motion(self, axis: int, value: float):
        """Handle analog stick/trigger movement"""
        # Quantize to reduce noise (3 decimal places)
        value = int(value * 1000) / 1000.0
        value = max(-1.0, min(1.0, value))

        self.axis_moved.emit(axis, value)

        # Get joystick mode from config
        joystick_mode = "single"
        if self.config:
            usb_config = self.config.get_usb_controller_config()
            joystick_mode = usb_config.get("joystick_mode", "single")

        # Axis 0 = Left stick X (pan)
        if axis == 0:
            self._axis_x = value
            self._update_movement_direction()

        # Axis 1 = Left stick Y (tilt)
        elif axis == 1:
            self._axis_y = value
            self._update_movement_direction()

        # Axis 2 = Right stick X
        elif axis == 2:
            self._axis_rx = value
            if joystick_mode == "dual":
                self._update_movement_direction()

        # Axis 3 = Right stick Y
        elif axis == 3:
            self._axis_ry = value
            if joystick_mode == "dual":
                self._update_movement_direction()

        # Axis 4 = Left trigger (zoom out)
        elif axis == 4:
            # Normalize trigger range (some drivers use -1 to 1, others 0 to 1)
            normalized = (value + 1.0) / 2.0  # Convert to 0-1 range
            if normalized > 0.05:  # Deadzone
                # Apply zoom speed multiplier from config
                zoom_speed = 0.7
                if self.config:
                    usb_config = self.config.get_usb_controller_config()
                    zoom_speed = usb_config.get("zoom_speed", 0.7)
                self.zoom_out.emit(normalized * zoom_speed)
            else:
                self.zoom_stop.emit()

        # Axis 5 = Right trigger (zoom in)
        elif axis == 5:
            normalized = (value + 1.0) / 2.0
            if normalized > 0.05:
                # Apply zoom speed multiplier from config
                zoom_speed = 0.7
                if self.config:
                    usb_config = self.config.get_usb_controller_config()
                    zoom_speed = usb_config.get("zoom_speed", 0.7)
                self.zoom_in.emit(normalized * zoom_speed)
            else:
                self.zoom_stop.emit()

    def _handle_hat_motion(self, hat: int, value: tuple):
        """Handle D-pad movement"""
        if hat != 0:
            return

        x, y = value

        # Get D-pad speed and invert from config
        speed = 0.7
        invert = False
        if self.config:
            usb_config = self.config.get_usb_controller_config()
            speed = usb_config.get("dpad_speed", 0.7)
            invert = usb_config.get("invert_vertical", False)

        # Invert Y if configured
        if invert:
            y = -y

        # Map D-pad to movement directions
        if x == 0 and y == 1:  # Up
            self.movement_direction.emit(MovementDirection.UP, speed)
        elif x == 0 and y == -1:  # Down
            self.movement_direction.emit(MovementDirection.DOWN, speed)
        elif x == -1 and y == 0:  # Left
            self.movement_direction.emit(MovementDirection.LEFT, speed)
        elif x == 1 and y == 0:  # Right
            self.movement_direction.emit(MovementDirection.RIGHT, speed)
        elif x == -1 and y == 1:  # Up-Left
            self.movement_direction.emit(MovementDirection.UP_LEFT, speed)
        elif x == 1 and y == 1:  # Up-Right
            self.movement_direction.emit(MovementDirection.UP_RIGHT, speed)
        elif x == -1 and y == -1:  # Down-Left
            self.movement_direction.emit(MovementDirection.DOWN_LEFT, speed)
        elif x == 1 and y == -1:  # Down-Right
            self.movement_direction.emit(MovementDirection.DOWN_RIGHT, speed)
        else:  # Centered
            self.movement_direction.emit(MovementDirection.STOP, 0.0)

    def _update_movement_direction(self):
        """Update movement direction based on analog stick position"""
        # Get config settings
        joystick_speed = 1.0
        invert = False
        joystick_mode = "single"

        if self.config:
            usb_config = self.config.get_usb_controller_config()
            joystick_speed = usb_config.get("joystick_speed", 1.0)
            invert = usb_config.get("invert_vertical", False)
            joystick_mode = usb_config.get("joystick_mode", "single")

        # Determine which axes to use based on mode
        if joystick_mode == "dual":
            # Dual mode: Left stick X only, Right stick Y only
            x = self._axis_x if abs(self._axis_x) > 0.15 else 0.0
            y = self._axis_ry if abs(self._axis_ry) > 0.15 else 0.0
        else:
            # Single mode: Left stick X and Y
            x = self._axis_x if abs(self._axis_x) > 0.15 else 0.0
            y = self._axis_y if abs(self._axis_y) > 0.15 else 0.0

        # Invert Y if configured
        if invert:
            y = -y

        # Use configured joystick speed
        speed = joystick_speed if (x != 0 or y != 0) else 0.0

        # Determine direction based on dominant axis
        direction = MovementDirection.STOP

        if x == 0 and y == 0:
            direction = MovementDirection.STOP
        else:
            # Use higher threshold to make diagonal movement harder (prefer cardinal directions)
            # Both axes need to be pushed significantly for diagonal
            if abs(x) > 0.6 and abs(y) > 0.6:
                # Diagonal movement
                if x > 0 and y < 0:
                    direction = MovementDirection.UP_RIGHT
                elif x > 0 and y > 0:
                    direction = MovementDirection.DOWN_RIGHT
                elif x < 0 and y < 0:
                    direction = MovementDirection.UP_LEFT
                elif x < 0 and y > 0:
                    direction = MovementDirection.DOWN_LEFT
            else:
                # Cardinal movement - use dominant axis
                if abs(x) > abs(y):
                    direction = MovementDirection.RIGHT if x > 0 else MovementDirection.LEFT
                else:
                    direction = MovementDirection.UP if y < 0 else MovementDirection.DOWN

        # Only emit if direction changed or stopped
        if direction != self._current_direction:
            self._current_direction = direction
            self.movement_direction.emit(direction, speed)

    def _reset_state(self):
        """Reset controller state"""
        self._axis_x = 0.0
        self._axis_y = 0.0
        self._current_direction = MovementDirection.STOP
        self.movement_direction.emit(MovementDirection.STOP, 0.0)
        self.zoom_stop.emit()

    def cleanup(self):
        """Clean up resources (non-blocking)"""
        self.poll_timer.stop()
        self.hotplug_timer.stop()
        # Don't quit joystick or pygame - can cause hangs on exit
        # Qt will clean up when process exits
