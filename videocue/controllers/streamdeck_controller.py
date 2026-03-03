"""
Stream Deck Plus controller support with rotary encoders
"""

import contextlib
import logging
import threading
import time

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import QThread, pyqtSignal

from videocue.controllers.streamdeck_init import is_streamdeck_available
from videocue.ui_strings import UIStrings

logger = logging.getLogger(__name__)

# Initialize Stream Deck library with DLL search path fix
streamdeck_available = is_streamdeck_available()
streamdeck_error_message = ""

if streamdeck_available:
    try:
        from StreamDeck.DeviceManager import DeviceManager
        from StreamDeck.Devices.StreamDeck import DialEventType
        from StreamDeck.ImageHelpers import PILHelper

        logger.info("Stream Deck library ready")
    except Exception as e:
        streamdeck_available = False
        streamdeck_error_message = str(e)
        logger.error(f"Stream Deck library import error after initialization: {e}")
else:
    streamdeck_error_message = "Stream Deck library not available"
    logger.warning("Stream Deck library not available")


class StreamDeckController(QThread):
    """
    Stream Deck Plus controller manager with rotary encoders.
    Runs in separate thread with blocking USB reads.
    """

    # Signals - Qt automatically marshals these to main thread
    encoder_rotated = pyqtSignal(int, int)  # encoder_id (0-3), delta (-N to +N)
    encoder_pressed = pyqtSignal(int)  # encoder_id (0-3)
    encoder_released = pyqtSignal(int)  # encoder_id (0-3)
    button_pressed = pyqtSignal(int)  # button_id (0-7)
    button_released = pyqtSignal(int)  # button_id (0-7)
    device_connected = pyqtSignal(str)  # Emits device name
    device_disconnected = pyqtSignal()  # Device removed
    error = pyqtSignal(str)  # Error message

    def __init__(self, config=None):
        super().__init__()
        self.setObjectName("StreamDeckController")
        self.config = config
        self.running = False
        self._stop_event = threading.Event()
        self._deck = None
        self._device_serial = None

        # Font for rendering text on displays
        self._font_large = None
        self._font_medium = None
        self._font_small = None
        self._init_fonts()

        # State for encoder displays (Stream Deck Plus uses 800x100 touchscreen strip)
        # Each encoder is 200x100 pixels
        self._encoder_displays = [
            {"text": "", "color": (255, 255, 255), "background": (0, 0, 0), "border": None}
            for _ in range(4)
        ]

        logger.info("StreamDeckController initialized")

    def _init_fonts(self):
        """Initialize fonts for rendering text on Stream Deck displays"""
        try:
            # Try to load Arial font (Windows default)
            self._font_large = ImageFont.truetype("arial.ttf", 60)  # For encoder displays (200x100)
            self._font_medium = ImageFont.truetype("arial.ttf", 24)  # For buttons (72x72)
            self._font_small = ImageFont.truetype("arial.ttf", 16)  # Fallback
            logger.info("Successfully loaded TrueType fonts (Arial)")
        except Exception as e:
            logger.warning(f"Failed to load TrueType fonts: {e}")
            try:
                # Fallback to default PIL font
                self._font_large = ImageFont.load_default()
                self._font_medium = ImageFont.load_default()
                self._font_small = ImageFont.load_default()
                logger.warning("Using default bitmap font (may not display well)")
            except Exception as e2:
                logger.error(f"Failed to load any fonts: {e2}")

    def is_available(self) -> bool:
        """Check if Stream Deck library is available"""
        return streamdeck_available

    def _find_stream_deck_plus(self, silent=False):
        """
        Find and open Stream Deck Plus device

        Args:
            silent: If True, don't emit error signals (for reconnection attempts)
        """
        try:
            if not streamdeck_available:
                if not silent:
                    logger.error("Stream Deck library not available")
                    self.error.emit(UIStrings.STREAMDECK_ERROR)
                return None

            # Enumerate all connected Stream Decks
            decks = DeviceManager().enumerate()

            if not decks:
                if not silent:
                    logger.warning("No Stream Deck devices found")
                    self.error.emit(UIStrings.STREAMDECK_NOT_FOUND)
                return None

            # Find Stream Deck Plus (has encoders/dials)
            for deck in decks:
                deck.open()
                try:
                    # Stream Deck Plus has 4 dials/encoders
                    if hasattr(deck, "dial_count") and deck.dial_count() == 4:
                        device_name = deck.deck_type()
                        self._device_serial = deck.get_serial_number()

                        # Debug: Log available methods for dial/screen control
                        dial_methods = [
                            m
                            for m in dir(deck)
                            if "dial" in m.lower() or "screen" in m.lower() or "touch" in m.lower()
                        ]
                        logger.info(f"Available dial/screen methods: {dial_methods}")

                        logger.info(
                            f"Found Stream Deck Plus: {device_name} (Serial: {self._device_serial})"
                        )
                        self.device_connected.emit(device_name)
                        return deck
                    # Not a Stream Deck Plus, close and continue
                    deck.close()
                except Exception as e:
                    logger.warning(f"Error checking deck type: {e}")
                    deck.close()

            if not silent:
                logger.warning("No Stream Deck Plus device found (requires device with 4 encoders)")
                self.error.emit(UIStrings.STREAMDECK_NOT_FOUND)
            return None

        except Exception as e:
            if not silent:
                logger.exception(f"Error finding Stream Deck Plus: {e}")
                self.error.emit(f"{UIStrings.STREAMDECK_ERROR}: {str(e)}")
            return None

    def run(self) -> None:
        """Main event loop with reconnection support"""
        if not streamdeck_available:
            logger.error("Stream Deck library not available")
            self.error.emit(UIStrings.ERROR_STREAMDECK_NO_DEVICE)
            return

        self.running = True
        logger.info("Stream Deck controller thread started")

        reconnect_delay = 5  # seconds between reconnection attempts
        connected = False
        first_attempt = True  # Show error on first attempt only

        # Main reconnection loop
        while self.running and not self._stop_event.is_set():
            try:
                # Try to find and connect to Stream Deck Plus
                if not connected:
                    self._deck = self._find_stream_deck_plus(silent=not first_attempt)
                    if self._deck:
                        # Set up event callbacks
                        self._deck.set_key_callback(self._key_callback)

                        # Check if device supports dial/encoder callbacks
                        if hasattr(self._deck, "set_dial_callback"):
                            self._deck.set_dial_callback(self._dial_callback)

                        # Reset device (clear all displays)
                        self._deck.reset()

                        logger.info("Stream Deck Plus connected and ready")
                        connected = True
                    else:
                        # Device not found, wait before retrying
                        logger.debug(
                            f"Stream Deck Plus not found, retrying in {reconnect_delay}s..."
                        )
                        for _ in range(reconnect_delay * 10):  # Check stop signal every 100ms
                            if self._stop_event.is_set():
                                break
                            time.sleep(0.1)
                        continue

                # Device connected - monitor for disconnection
                if connected and self._deck and not self._deck.connected():
                    logger.warning("Stream Deck disconnected")
                    self.device_disconnected.emit()
                    connected = False

                    # Clean up disconnected device
                    try:
                        self._deck.close()
                    except Exception as e:
                        logger.debug(f"Error closing disconnected device: {e}")
                    self._deck = None

                    logger.info(f"Attempting to reconnect in {reconnect_delay}s...")
                    continue

                # Check stop event (faster response than sleep)
                if self._stop_event.wait(timeout=0.1):  # 100ms timeout
                    break  # Exit immediately when stop requested

            except Exception as e:
                logger.exception(f"Stream Deck controller error: {e}")
                self.error.emit(f"{UIStrings.STREAMDECK_ERROR}: {str(e)}")
                connected = False

                # Clean up on error
                if self._deck:
                    with contextlib.suppress(Exception):
                        self._deck.close()
                    self._deck = None

                # Wait before retrying
                for _ in range(reconnect_delay * 10):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)

        # Final cleanup - thread has exited loop
        logger.info("Stream Deck controller loop exiting")
        # Skip ALL device operations during cleanup to avoid DLL crashes
        # The device will automatically reset when Python exits
        # Calling close() can cause ACCESS_VIOLATION in hidapi.dll during shutdown
        if self._deck:
            logger.info("Stream Deck cleanup: skipping close() to avoid DLL crash")
            self._deck = None  # Just clear the reference

    def _key_callback(self, deck, key, state):
        """Callback for button press/release events"""
        try:
            # state is True for pressed, False for released
            if state:
                logger.debug(f"Stream Deck button {key} pressed")
                self.button_pressed.emit(key)
            else:
                logger.debug(f"Stream Deck button {key} released")
                self.button_released.emit(key)
        except Exception as e:
            logger.exception(f"Error in key callback: {e}")

    def _dial_callback(self, deck, dial, event, value):
        """Callback for encoder/dial events"""
        try:
            # event types: TURN (rotation), PUSH (button press), TOUCH (capacitive touch)
            if event == DialEventType.TURN:
                # value is the rotation delta (positive = clockwise, negative = counter-clockwise)
                logger.debug(f"Stream Deck encoder {dial} rotated: {value}")
                self.encoder_rotated.emit(dial, value)

            elif event == DialEventType.PUSH:
                # value is 1 for pressed, 0 for released
                if value == 1:
                    logger.debug(f"Stream Deck encoder {dial} pressed")
                    self.encoder_pressed.emit(dial)
                else:
                    logger.debug(f"Stream Deck encoder {dial} released")
                    self.encoder_released.emit(dial)

        except Exception as e:
            logger.exception(f"Error in dial callback: {e}")

    def stop(self) -> None:
        """
        Stop the controller thread.

        CRITICAL: Only sets stop flags. NO device operations (reset/close).
        Calling device methods from main thread while worker thread is in
        blocking USB read causes ACCESS_VIOLATION crash. All device cleanup
        happens in worker thread's run() method after loop exits naturally.
        """
        logger.info("StreamDeckController.stop() - setting stop flags only (no device operations)")
        self.running = False
        self._stop_event.set()
        logger.info("Stop flags set - thread will handle device cleanup safely")

    def set_encoder_display(
        self,
        encoder_id: int,
        text: str,
        color: tuple = (255, 255, 255),
        background: tuple = (0, 0, 0),
        border: tuple = None,
    ):
        """
        Set text display for an encoder section (200x100 pixels each)
        Stream Deck Plus uses 800x100 touchscreen strip, so we maintain state
        for all 4 encoders and render the full strip on each update.

        Args:
            encoder_id: Encoder index (0-3)
            text: Text to display (e.g., "1" for camera number)
            color: RGB text color (default: white)
            background: RGB background color (default: black)
            border: RGB border color (optional, draws 5px border if specified)
        """
        try:
            if not self._deck or not self.running:
                return

            # Validate encoder_id
            if encoder_id < 0 or encoder_id > 3:
                logger.error(f"Invalid encoder_id: {encoder_id} (must be 0-3)")
                return

            # Update state for this encoder
            self._encoder_displays[encoder_id] = {
                "text": text,
                "color": color,
                "background": background,
                "border": border,
            }

            # Render full touchscreen strip (800x100 pixels)
            self._render_touchscreen()

        except Exception as e:
            logger.exception(f"Error setting encoder display: {e}")

    def _render_touchscreen(self):
        """
        Render the full 800x100 touchscreen strip with all 4 encoder displays.
        Each encoder section is 200x100 pixels.
        """
        try:
            if not self._deck or not self.running:
                return

            if not hasattr(self._deck, "set_touchscreen_image"):
                logger.error("Deck does not have set_touchscreen_image method")
                return

            # Create touchscreen image using PILHelper (ensures correct dimensions)
            touchscreen = PILHelper.create_touchscreen_image(self._deck, background="black")
            logger.debug(
                f"Created touchscreen image: size={touchscreen.size}, mode={touchscreen.mode}"
            )

            # Render each encoder section (200x100 each)
            for encoder_id in range(4):
                display = self._encoder_displays[encoder_id]

                # Create section image
                section = Image.new("RGB", (200, 100), display["background"])
                draw = ImageDraw.Draw(section)

                # Draw border if specified
                if display["border"]:
                    # Draw 5px border around the section
                    border_width = 5
                    draw.rectangle(
                        [(0, 0), (199, 99)],
                        outline=display["border"],
                        width=border_width,
                    )

                # Draw text centered if not empty
                if display["text"]:
                    font = self._font_large if len(display["text"]) <= 2 else self._font_medium
                    draw.text(
                        (100, 50), display["text"], fill=display["color"], anchor="mm", font=font
                    )

                # Paste section into touchscreen at correct position
                x_offset = encoder_id * 200
                touchscreen.paste(section, (x_offset, 0))

            # Debug: Check image before conversion
            logger.debug(
                f"Touchscreen before conversion: size={touchscreen.size}, mode={touchscreen.mode}"
            )

            # Convert to native format and send to device
            native_image = PILHelper.to_native_touchscreen_format(self._deck, touchscreen)
            logger.debug(
                f"Native image: type={type(native_image)}, len={len(native_image) if hasattr(native_image, '__len__') else 'N/A'}"
            )

            # Check if deck has method to get expected size
            if hasattr(self._deck, "touchscreen_image_format"):
                expected = self._deck.touchscreen_image_format()
                logger.debug(f"Expected touchscreen format: {expected}")

            # Pass image with explicit dimensions (required by Stream Deck Plus API)
            width, height = touchscreen.size
            self._deck.set_touchscreen_image(
                native_image, x_pos=0, y_pos=0, width=width, height=height
            )

            logger.info(f"Touchscreen updated: {[d['text'] for d in self._encoder_displays]}")

        except Exception as e:
            logger.exception(f"Error rendering touchscreen: {e}")

    def set_button_display(
        self,
        button_id: int,
        text: str,
        color: tuple = (255, 255, 255),
        background: tuple = (0, 0, 0),
    ):
        """
        Set text display for a button LCD (72x72 pixels)

        Args:
            button_id: Button index (0-7)
            text: Text to display
            color: RGB text color (default: white)
            background: RGB background color (default: black)
        """
        try:
            if not self._deck or not self.running:
                return

            # Create button image using PILHelper (ensures correct dimensions and format)
            image = PILHelper.create_key_image(self._deck, background=background)
            draw = ImageDraw.Draw(image)

            # Draw text centered - use medium font for better readability
            # Button text is usually short (P1, ARM, etc.)
            font = self._font_medium if self._font_medium else self._font_small

            # Get image center
            width, height = image.size
            center_x, center_y = width // 2, height // 2

            draw.text((center_x, center_y), text, fill=color, anchor="mm", font=font)

            logger.debug(f"Created button {button_id} image: size={image.size}, text='{text}'")

            # Convert PIL image to native Stream Deck format
            native_image = PILHelper.to_native_key_format(self._deck, image)

            # Set the button display
            self._deck.set_key_image(button_id, native_image)

            logger.debug(f"Set button {button_id} display to: '{text}'")

        except Exception as e:
            logger.exception(f"Error setting button display: {e}")

    def clear_all_displays(self):
        """Clear all encoder and button displays"""
        try:
            if not self._deck or not self.running:
                return

            # Clear encoder displays
            for i in range(4):
                self.set_encoder_display(i, "", background=(0, 0, 0))

            # Clear button displays
            for i in range(8):
                self.set_button_display(i, "", background=(0, 0, 0))

        except Exception as e:
            logger.exception(f"Error clearing displays: {e}")

    def reset_device(self):
        """Reset device (clear all displays and reset state)"""
        try:
            if self._deck and self.running:
                self._deck.reset()
                logger.info("Stream Deck device reset")
        except Exception as e:
            logger.exception(f"Error resetting device: {e}")
