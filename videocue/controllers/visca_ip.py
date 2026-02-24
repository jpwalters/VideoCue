"""
VISCA-over-IP protocol implementation using UDP
"""

import contextlib
import logging
import socket
import struct
import threading
from enum import Enum

from videocue.constants import NetworkConstants
from videocue.controllers.visca_commands import ViscaLimits
from videocue.exceptions import ViscaConnectionError, ViscaTimeoutError

logger = logging.getLogger(__name__)


class FocusMode(Enum):
    AUTO = 1
    MANUAL = 2
    UNKNOWN = 3


class ExposureMode(Enum):
    """Exposure mode enumeration"""

    AUTO = 0
    MANUAL = 1
    SHUTTER_PRIORITY = 2
    IRIS_PRIORITY = 3
    BRIGHT = 4
    UNKNOWN = 5


class WhiteBalanceMode(Enum):
    """White balance mode enumeration"""

    AUTO = 0
    INDOOR = 1
    OUTDOOR = 2
    ONE_PUSH = 3
    MANUAL = 4
    UNKNOWN = 5


class VideoFormat(Enum):
    """Video format enumeration - BirdDog P400 format codes

    Based on actual camera responses and VISCA protocol documentation.
    Query: 81 09 06 23 FF
    Response: 90 50 pp FF (where pp is the format code)
    """

    FORMAT_1080P60 = 0x00  # 1920x1080 60fps
    FORMAT_1080P50 = 0x01  # 1920x1080 50fps
    FORMAT_720P50 = 0x02  # 1280x720 50fps - CONFIRMED
    FORMAT_1080P25 = 0x03  # 1920x1080 25fps (PAL)
    FORMAT_1080P29_97 = 0x04  # 1920x1080 29.97fps (NTSC)
    FORMAT_1080P30 = 0x05  # 1920x1080 30fps
    FORMAT_1080I60 = 0x06  # 1920x1080 60i
    FORMAT_1080I59_94 = 0x07  # 1920x1080 59.94i
    FORMAT_1080I50 = 0x08  # 1920x1080 50i
    FORMAT_720P60 = 0x09  # 1280x720 60fps
    FORMAT_720P59_94 = 0x0A  # 1280x720 59.94fps
    FORMAT_1080P59_94 = 0x0B  # 1920x1080 59.94fps
    FORMAT_720P30 = 0x0C  # 1280x720 30fps
    FORMAT_720P29_97 = 0x0D  # 1280x720 29.97fps
    FORMAT_720P25 = 0x0E  # 1280x720 25fps
    UNKNOWN = 0xFF  # Unknown/unsupported format


class ViscaIP:
    """
    VISCA protocol controller using UDP datagrams with connection pooling.

    Thread Safety:
        This class is thread-safe. The internal socket is protected by _socket_lock
        and can be safely called from multiple threads (e.g., main thread and USB
        controller thread). Each command acquires the lock before sending.
    """

    def __init__(self, ip: str, port: int = None):
        if port is None:
            port = NetworkConstants.VISCA_DEFAULT_PORT
        self.ip = ip
        self.port = port
        self._seq_num = 0
        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._last_error: str | None = None
        logger.info("ViscaIP initialized for %s:%s", ip, port)

    def __del__(self) -> None:
        """Cleanup socket on destruction"""
        self.close()

    def close(self) -> None:
        """Close socket connection"""
        with self._socket_lock:
            if self._socket:
                try:
                    self._socket.close()
                    logger.debug("Socket closed for %s:%s", self.ip, self.port)
                except Exception as e:
                    logger.warning("Error closing socket: %s", e)
                finally:
                    self._socket = None

    def _get_socket(self) -> socket.socket:
        """Get or create socket with proper error handling"""
        with self._socket_lock:
            if self._socket is None:
                try:
                    self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    self._socket.settimeout(ViscaLimits.COMMAND_TIMEOUT)
                    logger.debug("Socket created for %s:%s", self.ip, self.port)
                except OSError as e:
                    logger.error("Failed to create socket: %s", e)
                    raise ViscaConnectionError(f"Socket creation failed: {e}") from e
            return self._socket

    def _get_seq_num(self) -> int:
        """Get unique sequence number for packet - thread-safe"""
        with self._socket_lock:
            seq = self._seq_num
            self._seq_num = (self._seq_num + 1) % 99999990
            return seq

    def _build_packet(self, command: str) -> bytes:
        """
        Build VISCA-over-IP packet
        Format: [PayloadType:1byte][PayloadLength:3bytes][SequenceNumber:4bytes][ViscaCommand:Nbytes]
        """
        # Convert hex string to bytes (e.g., "81 01 06 01" -> b'\x81\x01\x06\x01')
        cmd_hex = command.replace(" ", "")
        cmd_bytes = bytes.fromhex(cmd_hex)

        payload_type = 0x01
        payload_length = len(cmd_bytes)
        seq_num = self._get_seq_num()

        # Pack: 1 byte type, 2 bytes length (big-endian), 1 byte padding, 4 bytes seq (big-endian)
        header = struct.pack(">BHxI", payload_type, payload_length, seq_num)
        return header + cmd_bytes

    def send_command(self, command: str) -> bool:
        """Send VISCA command without waiting for response"""
        try:
            sock = self._get_socket()
            packet = self._build_packet(command)
            sock.sendto(packet, (self.ip, self.port))
            logger.debug("Sent command to %s: %s...", self.ip, command[:20])
            return True
        except ViscaConnectionError:
            raise
        except TimeoutError:
            self._last_error = "Send timeout"
            logger.warning(f"Send timeout for {self.ip}")
            self.close()  # Recreate socket on next call
            return False
        except OSError as e:
            self._last_error = str(e)
            logger.error(f"Send error for {self.ip}: {e}")
            self.close()
            return False
        except Exception as e:
            self._last_error = str(e)
            logger.exception(f"Unexpected send error for {self.ip}")
            self.close()
            return False

    def query_command(self, command: str, timeout: float = None) -> bytes | None:
        """
        Send VISCA query and return response.

        VISCA-over-IP Response Format:
        [PayloadType:1byte][PayloadLength:3bytes][SequenceNumber:4bytes][ViscaResponse:Nbytes]

        When parsing responses:
        1. Convert to hex: response.hex().upper()
        2. Skip first 16 hex chars (8-byte VISCA-over-IP header)
        3. Parse VISCA response which typically follows format:
           - Single value: 90 50 0p FF (where p is the value)
           - Multi-nibble: 90 50 0p 0q 0r 0s FF (4 nibbles for larger values)
        4. Extract nibbles from specific positions after skipping header

        Args:
            command: VISCA command string
            timeout: Optional timeout override in seconds

        Returns:
            Response bytes or None on error
        """
        old_timeout = None
        try:
            sock = self._get_socket()
            if timeout is not None:
                old_timeout = sock.gettimeout()
                sock.settimeout(timeout)

            packet = self._build_packet(command)
            sock.sendto(packet, (self.ip, self.port))
            response, _ = sock.recvfrom(1024)
            logger.debug("Query response from %s: %s...", self.ip, response.hex()[:40])
            return response
        except TimeoutError:
            self._last_error = "Query timeout"
            logger.warning(f"Query timeout for {self.ip}")
            self.close()
            raise ViscaTimeoutError(f"Query timeout for {self.ip}") from None
        except OSError as e:
            self._last_error = str(e)
            logger.error(f"Query error for {self.ip}: {e}")
            self.close()
            return None
        except Exception as e:
            self._last_error = str(e)
            logger.exception(f"Unexpected query error for {self.ip}")
            self.close()
            return None
        finally:
            if old_timeout is not None and self._socket:
                with contextlib.suppress(Exception):
                    self._socket.settimeout(old_timeout)

    def _pan_speed(self, speed: float) -> str:
        """Convert 0.0-1.5+ speed to VISCA pan speed hex (01-18)"""
        # Map 0.3-1.5 to 1-18 (VISCA max pan speed 0x18=24)
        # Use rounding to preserve fractional speeds
        speed_val = max(1, min(24, round(speed * 12)))
        return f"{speed_val:02X}"

    def _tilt_speed(self, speed: float) -> str:
        """Convert 0.0-1.5+ speed to VISCA tilt speed hex (01-14)"""
        # Map 0.3-1.5 to 1-14 (VISCA max tilt speed 0x14=20)
        # Use rounding to preserve fractional speeds
        speed_val = max(1, min(20, round(speed * 10)))
        return f"{speed_val:02X}"

    def move(self, direction: str, pan_speed: float, tilt_speed: float) -> bool:
        """
        Move camera in specified direction
        Direction codes: up=0301, down=0302, left=0103, right=0203,
                        upleft=0101, upright=0201, downleft=0102, downright=0202
        """
        pan_hex = self._pan_speed(pan_speed)
        tilt_hex = self._tilt_speed(tilt_speed)
        command = f"81 01 06 01 {pan_hex} {tilt_hex} {direction} FF"

        return self.send_command(command)

    def stop(self) -> bool:
        """Stop camera movement"""
        return self.send_command("81 01 06 01 03 03 03 03 FF")

    def set_pan_tilt_speed_limit(self, pan_limit: int = 24, tilt_limit: int = 20) -> bool:
        """
        Set maximum pan/tilt speed limit (BirdDog cameras)
        pan_limit: 1-24 (default 24 = unlimited)
        tilt_limit: 1-20 (default 20 = unlimited)

        This fixes slow movement issues caused by speed limiters.
        """
        logger.debug(f"Setting speed limits: pan={pan_limit}, tilt={tilt_limit}")
        pan_hex = f"{pan_limit:02X}"
        tilt_hex = f"{tilt_limit:02X}"
        return self.send_command(f"81 01 06 11 {pan_hex} {tilt_hex} FF")

    def zoom_in(self, speed: float = 0.5) -> bool:
        """Zoom in with variable speed (0.0-1.0)"""
        if speed == 0.0:
            return self.zoom_stop()
        speed_val = max(0, min(7, int(speed * 7)))
        return self.send_command(f"81 01 04 07 2{speed_val} FF")

    def zoom_out(self, speed: float = 0.5) -> bool:
        """Zoom out with variable speed (0.0-1.0)"""
        if speed == 0.0:
            return self.zoom_stop()
        speed_val = max(0, min(7, int(speed * 7)))
        return self.send_command(f"81 01 04 07 3{speed_val} FF")

    def zoom_stop(self) -> bool:
        """Stop zoom"""
        return self.send_command("81 01 04 07 00 FF")

    def query_focus_mode(self) -> FocusMode:
        """Query camera focus mode"""
        response = self.query_command("81 09 04 38 FF")
        if response and len(response) > 3:
            # Response format: y0 50 0p FF where p: 2=Auto, 3=Manual
            response_hex = response.hex().upper()
            if len(response_hex) >= 3:
                code = response_hex[-3]
                if code == "2":
                    return FocusMode.AUTO
                if code == "3":
                    return FocusMode.MANUAL
        return FocusMode.UNKNOWN

    def query_exposure_mode(self) -> ExposureMode:
        """Query camera exposure mode"""
        response = self.query_command("81 09 04 39 FF")
        if response and len(response) > 2:
            # Skip VISCA-over-IP header (8 bytes = 16 hex chars)
            # Response format after header: 90 50 0p FF where p is mode code
            response_hex = response.hex().upper()
            logger.info(f"[{self.ip}] Raw exposure mode response: {response_hex}")
            if len(response_hex) >= 20:
                visca_response = response_hex[16:]  # Skip header
                logger.info(f"[{self.ip}] Exposure VISCA response (after header): {visca_response}")
                # Extract mode value from position 5 (second nibble of "0p" in "90 50 0p FF")
                try:
                    mode_value = int(visca_response[5], 16)
                    logger.info(f"[{self.ip}] Extracted exposure mode value: {mode_value}")
                    mode_map = {
                        0: ExposureMode.AUTO,
                        3: ExposureMode.MANUAL,
                        10: ExposureMode.SHUTTER_PRIORITY,  # 0A hex = 10 decimal
                        11: ExposureMode.IRIS_PRIORITY,  # 0B hex = 11 decimal
                        13: ExposureMode.BRIGHT,  # 0D hex = 13 decimal (standard VISCA)
                        15: ExposureMode.BRIGHT,  # 0F hex = 15 decimal (BirdDog cameras)
                    }
                    result = mode_map.get(mode_value, ExposureMode.UNKNOWN)
                    logger.info(
                        f"[{self.ip}] Exposure mode query: {result.name} (value: {mode_value})"
                    )
                    return result
                except (ValueError, IndexError) as e:
                    logger.warning(f"[{self.ip}] Failed to parse exposure mode: {e}")
        logger.warning(f"[{self.ip}] Exposure mode query failed - no valid response")
        return ExposureMode.UNKNOWN

    def query_iris(self) -> int | None:
        """Query camera iris value (0-17)"""
        response = self.query_command("81 09 04 4B FF")
        if response and len(response) > 3:
            # Response format: y0 50 0p 0q 0r 0s FF (4 nibbles)
            response_hex = response.hex().upper()
            if len(response_hex) >= 12:
                # Extract last nibble before FF
                value_str = response_hex[-4:-2]
                try:
                    return int(value_str, 16)
                except ValueError:
                    pass
        return None

    def query_shutter(self) -> int | None:
        """Query camera shutter value (0-21)"""
        response = self.query_command("81 09 04 4A FF")
        if response and len(response) > 3:
            response_hex = response.hex().upper()
            if len(response_hex) >= 12:
                value_str = response_hex[-4:-2]
                try:
                    return int(value_str, 16)
                except ValueError:
                    pass
        return None

    def query_gain(self) -> int | None:
        """Query camera gain value (0-15)"""
        response = self.query_command("81 09 04 4C FF")
        if response and len(response) > 3:
            response_hex = response.hex().upper()
            if len(response_hex) >= 12:
                value_str = response_hex[-4:-2]
                try:
                    return int(value_str, 16)
                except ValueError:
                    pass
        return None

    def query_brightness(self) -> int | None:
        """Query camera brightness value (0-41)"""
        response = self.query_command("81 09 04 4D FF")
        if response and len(response) > 3:
            response_hex = response.hex().upper()
            # Check for error response
            if "60" in response_hex or "61" in response_hex:
                return None
            # Skip VISCA-over-IP header (8 bytes = 16 hex chars)
            # Response format after header: 90 50 0p 0q 0r 0s FF
            if len(response_hex) >= 30:
                visca_response = response_hex[16:]  # Skip header
                # Extract second nibble from each byte: positions 5, 7, 9, 11 in visca_response
                try:
                    p = int(visca_response[5], 16)  # Second char of "0p"
                    q = int(visca_response[7], 16)  # Second char of "0q"
                    r = int(visca_response[9], 16)  # Second char of "0r"
                    s = int(visca_response[11], 16)  # Second char of "0s"
                    value = (p << 12) | (q << 8) | (r << 4) | s
                    return value
                except (ValueError, IndexError):
                    logger.exception("Brightness parse error")
                    pass
        return None

    def set_autofocus(self, enable: bool) -> bool:
        """Set autofocus mode"""
        mode = "02" if enable else "03"
        return self.send_command(f"81 01 04 38 {mode} FF")

    def one_push_autofocus(self) -> bool:
        """Trigger one-push autofocus (single AF operation)"""
        return self.send_command("81 01 04 18 01 FF")

    def focus_near(self, speed: float = 0.5) -> bool:
        """Focus near with variable speed (0.0-1.0)"""
        if speed == 0.0:
            return self.focus_stop()
        speed_val = max(0, min(7, int(speed * 7)))
        return self.send_command(f"81 01 04 08 2{speed_val} FF")

    def focus_far(self, speed: float = 0.5) -> bool:
        """Focus far with variable speed (0.0-1.0)"""
        if speed == 0.0:
            return self.focus_stop()
        speed_val = max(0, min(7, int(speed * 7)))
        return self.send_command(f"81 01 04 08 3{speed_val} FF")

    def focus_stop(self) -> bool:
        """Stop focus movement"""
        return self.send_command("81 01 04 08 00 FF")

    def set_pan_left_limit(self) -> bool:
        """Set current position as left pan limit"""
        logger.debug("Setting LEFT pan limit at current position")
        return self.send_command("81 01 06 07 01 FF")

    def set_pan_right_limit(self) -> bool:
        """Set current position as right pan limit"""
        logger.debug("Setting RIGHT pan limit at current position")
        return self.send_command("81 01 06 07 02 FF")

    def clear_pan_limits(self) -> bool:
        """Clear pan limits (reset to full range)"""
        logger.debug("Clearing pan limits (reset to full range)")
        return self.send_command("81 01 06 07 03 FF")

    def start_auto_pan(self, pan_speed: int = 10, tilt_speed: int = 10) -> bool:
        """
        Start auto pan mode (camera pans between set limits)

        Note: Pan limits must be set first using set_pan_left_limit() and set_pan_right_limit()
        The camera will continuously pan between these limits.

        Command format: 81 01 06 10 VV WW FF
        VV = pan speed (1-24)
        WW = tilt speed (1-20) - typically 0 for horizontal-only auto pan
        """
        logger.debug(f"Starting AUTO PAN with speed={pan_speed}")
        pan_hex = f"{pan_speed:02X}"
        # For auto pan (horizontal only), tilt speed is typically 00
        return self.send_command(f"81 01 06 10 {pan_hex} 00 FF")

    def stop_auto_pan(self) -> bool:
        """Stop auto pan mode (same as regular stop movement)"""
        logger.debug("Stopping AUTO PAN")
        return self.stop()

    def recall_preset_position(self, preset_number: int) -> bool:
        """
        Recall preset position (0-254)

        Uses standard VISCA preset recall command.
        Command format: 81 01 04 3F 02 pp FF
        pp = preset number (0x00 to 0xFE)
        """
        if preset_number < 0 or preset_number > 254:
            logger.warning(f"Invalid preset number: {preset_number} (must be 0-254)")
            return False
        preset_hex = f"{preset_number:02X}"
        cmd = f"81 01 04 3F 02 {preset_hex} FF"
        logger.info(f"[{self.ip}] Recalling preset #{preset_number} (cmd: {cmd})")
        return self.send_command(cmd)

    def store_preset_position(self, preset_number: int) -> bool:
        """
        Store current position to preset (0-254)

        Uses standard VISCA preset store command.
        Command format: 81 01 04 3F 01 pp FF
        pp = preset number (0x00 to 0xFE)
        """
        if preset_number < 0 or preset_number > 254:
            logger.warning(f"Invalid preset number: {preset_number} (must be 0-254)")
            return False
        preset_hex = f"{preset_number:02X}"
        cmd = f"81 01 04 3F 01 {preset_hex} FF"
        logger.info(f"[{self.ip}] Storing preset #{preset_number} (cmd: {cmd})")
        return self.send_command(cmd)

    def set_exposure_mode(self, mode: ExposureMode) -> bool:
        """Set exposure mode"""
        mode_codes = {
            ExposureMode.AUTO: "00",
            ExposureMode.MANUAL: "03",
            ExposureMode.SHUTTER_PRIORITY: "0A",
            ExposureMode.IRIS_PRIORITY: "0B",
            ExposureMode.BRIGHT: "0D",
        }
        code = mode_codes.get(mode)
        if code:
            return self.send_command(f"81 01 04 39 {code} FF")
        return False

    def set_iris(self, value: int) -> bool:
        """Set iris value (0-17, 0=closed, 17=open)"""
        value = max(0, min(17, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        return self.send_command(f"81 01 04 4B 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF")

    def set_shutter(self, value: int) -> bool:
        """Set shutter speed value (0-21)"""
        value = max(0, min(21, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        return self.send_command(f"81 01 04 4A 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF")

    def set_gain(self, value: int) -> bool:
        """Set gain value (0-15)"""
        value = max(0, min(15, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        return self.send_command(f"81 01 04 4C 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF")

    def set_backlight_comp(self, enable: bool) -> bool:
        """Enable/disable backlight compensation"""
        mode = "02" if enable else "03"
        return self.send_command(f"81 01 04 33 {mode} FF")

    def set_brightness(self, value: int) -> bool:
        """Set brightness level in Bright mode (0-41 for BirdDog cameras)"""
        value = max(0, min(41, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        command = f"81 01 04 4D 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF"
        return self.send_command(command)

    def set_white_balance_mode(self, mode: WhiteBalanceMode) -> bool:
        """Set white balance mode"""
        mode_codes = {
            WhiteBalanceMode.AUTO: "00",
            WhiteBalanceMode.INDOOR: "01",
            WhiteBalanceMode.OUTDOOR: "02",
            WhiteBalanceMode.ONE_PUSH: "03",
            WhiteBalanceMode.MANUAL: "05",
        }
        code = mode_codes.get(mode)
        if code:
            return self.send_command(f"81 01 04 35 {code} FF")
        return False

    def one_push_white_balance(self) -> bool:
        """Trigger one-push white balance (single WB calibration)"""
        return self.send_command("81 01 04 10 05 FF")

    def set_red_gain(self, value: int) -> bool:
        """Set red gain for manual white balance (0-255)"""
        value = max(0, min(255, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        return self.send_command(f"81 01 04 43 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF")

    def set_blue_gain(self, value: int) -> bool:
        """Set blue gain for manual white balance (0-255)"""
        value = max(0, min(255, value))
        # VISCA format: 4 nibbles (0p 0q 0r 0s)
        p = (value >> 12) & 0x0F
        q = (value >> 8) & 0x0F
        r = (value >> 4) & 0x0F
        s = value & 0x0F
        return self.send_command(f"81 01 04 44 0{p:X} 0{q:X} 0{r:X} 0{s:X} FF")

    def query_white_balance_mode(self) -> WhiteBalanceMode:
        """Query current white balance mode"""
        response = self.query_command("81 09 04 35 FF")
        if response and len(response) > 2:
            # Skip VISCA-over-IP header (8 bytes = 16 hex chars)
            # Response format after header: 90 50 pp pp pp pp FF (multi-byte response)
            # The actual value is in the last byte before FF
            response_hex = response.hex().upper()
            logger.info(f"[{self.ip}] Raw white balance mode response: {response_hex}")
            if len(response_hex) >= 20:
                visca_response = response_hex[16:]  # Skip header
                logger.info(
                    f"[{self.ip}] White balance VISCA response (after header): {visca_response}"
                )
                # Extract last byte before FF terminator (position -4:-2)
                try:
                    value_hex = visca_response[-4:-2]
                    mode_value = int(value_hex, 16)
                    logger.info(
                        f"[{self.ip}] Extracted white balance mode value: {mode_value} (hex: {value_hex})"
                    )
                    mode_map = {
                        0: WhiteBalanceMode.AUTO,
                        1: WhiteBalanceMode.INDOOR,  # Standard VISCA
                        2: WhiteBalanceMode.OUTDOOR,  # Standard VISCA
                        3: WhiteBalanceMode.ONE_PUSH,
                        5: WhiteBalanceMode.MANUAL,  # BirdDog P200 returns 5 for MANUAL
                        6: WhiteBalanceMode.INDOOR,  # BirdDog returns 6 for INDOOR
                        10: WhiteBalanceMode.MANUAL,  # BirdDog P400 returns 10 (0A hex) for MANUAL
                    }
                    result = mode_map.get(mode_value, WhiteBalanceMode.UNKNOWN)
                    logger.info(
                        f"[{self.ip}] White balance mode query: {result.name} (value: {mode_value})"
                    )
                    return result
                except (ValueError, IndexError) as e:
                    logger.warning(f"[{self.ip}] Failed to parse white balance mode: {e}")
        logger.warning(f"[{self.ip}] White balance mode query failed - no valid response")
        return WhiteBalanceMode.UNKNOWN

    def query_red_gain(self) -> int | None:
        """Query red gain value (0-255)"""
        response = self.query_command("81 09 04 43 FF")
        if response and len(response) > 3:
            response_hex = response.hex().upper()
            if len(response_hex) >= 30:
                visca_response = response_hex[16:]  # Skip VISCA-over-IP header
                # Response format: 90 50 0p 0q 0r 0s FF
                try:
                    p = int(visca_response[5], 16)
                    q = int(visca_response[7], 16)
                    r = int(visca_response[9], 16)
                    s = int(visca_response[11], 16)
                    value = (p << 12) | (q << 8) | (r << 4) | s
                    return value
                except (ValueError, IndexError):
                    pass
        return None

    def query_blue_gain(self) -> int | None:
        """Query blue gain value (0-255)"""
        response = self.query_command("81 09 04 44 FF")
        if response and len(response) > 3:
            response_hex = response.hex().upper()
            if len(response_hex) >= 30:
                visca_response = response_hex[16:]  # Skip VISCA-over-IP header
                # Response format: 90 50 0p 0q 0r 0s FF
                try:
                    p = int(visca_response[5], 16)
                    q = int(visca_response[7], 16)
                    r = int(visca_response[9], 16)
                    s = int(visca_response[11], 16)
                    value = (p << 12) | (q << 8) | (r << 4) | s
                    return value
                except (ValueError, IndexError):
                    pass
        return None

    def query_backlight_comp(self) -> bool | None:
        """Query backlight compensation status"""
        response = self.query_command("81 09 04 33 FF")
        if response and len(response) > 2:
            response_hex = response.hex().upper()
            if len(response_hex) >= 20:
                visca_response = response_hex[16:]  # Skip header
                # Response format: 90 50 0p FF where p is 02 (on) or 03 (off)
                try:
                    mode_value = int(visca_response[5], 16)
                    return mode_value == 2  # 02 = on, 03 = off
                except (ValueError, IndexError):
                    pass
        return None

    def query_video_format(self) -> "VideoFormat":
        """Query current video format"""
        response = self.query_command("81 09 06 23 FF")
        if response and len(response) > 2:
            response_hex = response.hex().upper()
            if len(response_hex) >= 20:
                visca_response = response_hex[16:]  # Skip header
                # Response format appears to be: 90 60 pp FF (not standard 90 50 pp FF)
                # The format code is at positions [2:4], not [4:6]
                try:
                    format_code = int(visca_response[2:4], 16)
                    for fmt in VideoFormat:
                        if fmt.value == format_code:
                            return fmt
                except (ValueError, IndexError):
                    pass
        return VideoFormat.UNKNOWN

    def set_video_format(self, format: "VideoFormat") -> bool:
        """Set video format"""
        if format == VideoFormat.UNKNOWN:
            return False
        return self.send_command(f"81 01 06 35 {format.value:02X} FF")


# Direction constants for easier use
class Direction:
    UP = "03 01"
    DOWN = "03 02"
    LEFT = "01 03"
    RIGHT = "02 03"
    UP_LEFT = "01 01"
    UP_RIGHT = "02 01"
    DOWN_LEFT = "01 02"
    DOWN_RIGHT = "02 02"
    STOP = "03 03"
