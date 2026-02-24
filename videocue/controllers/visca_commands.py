"""
VISCA protocol command constants
All commands documented with their function and expected responses
"""


# Camera Control Commands
class ViscaCommands:
    """VISCA command string constants"""

    # PTZ Movement Commands
    PAN_TILT_STOP = "81 01 06 01 {pan_speed} {tilt_speed} 03 03 FF"
    PAN_TILT_UP = "81 01 06 01 {pan_speed} {tilt_speed} 03 01 FF"
    PAN_TILT_DOWN = "81 01 06 01 {pan_speed} {tilt_speed} 03 02 FF"
    PAN_TILT_LEFT = "81 01 06 01 {pan_speed} {tilt_speed} 01 03 FF"
    PAN_TILT_RIGHT = "81 01 06 01 {pan_speed} {tilt_speed} 02 03 FF"
    PAN_TILT_UP_LEFT = "81 01 06 01 {pan_speed} {tilt_speed} 01 01 FF"
    PAN_TILT_UP_RIGHT = "81 01 06 01 {pan_speed} {tilt_speed} 02 01 FF"
    PAN_TILT_DOWN_LEFT = "81 01 06 01 {pan_speed} {tilt_speed} 01 02 FF"
    PAN_TILT_DOWN_RIGHT = "81 01 06 01 {pan_speed} {tilt_speed} 02 02 FF"

    # Zoom Commands
    ZOOM_STOP = "81 01 04 07 00 FF"
    ZOOM_TELE = "81 01 04 07 2{speed} FF"  # speed: 0-7
    ZOOM_WIDE = "81 01 04 07 3{speed} FF"  # speed: 0-7

    # Focus Commands
    FOCUS_AUTO = "81 01 04 38 02 FF"
    FOCUS_MANUAL = "81 01 04 38 03 FF"
    FOCUS_ONE_PUSH = "81 01 04 18 01 FF"
    FOCUS_NEAR = "81 01 04 08 3{speed} FF"  # speed: 0-7
    FOCUS_FAR = "81 01 04 08 2{speed} FF"  # speed: 0-7
    FOCUS_STOP = "81 01 04 08 00 FF"

    # Exposure Commands
    EXPOSURE_MODE = (
        "81 01 04 39 {mode} FF"  # mode: 00=Auto, 03=Manual, 0A=Shutter, 0B=Iris, 0D=Bright
    )
    IRIS_UP = "81 01 04 0B 02 FF"
    IRIS_DOWN = "81 01 04 0B 03 FF"
    IRIS_DIRECT = "81 01 04 4B {value} FF"  # value: 0-17 (4 nibbles: 0p 0q 0r 0s)
    SHUTTER_UP = "81 01 04 0A 02 FF"
    SHUTTER_DOWN = "81 01 04 0A 03 FF"
    SHUTTER_DIRECT = "81 01 04 4A {value} FF"  # value: 0-21
    GAIN_UP = "81 01 04 0C 02 FF"
    GAIN_DOWN = "81 01 04 0C 03 FF"
    GAIN_DIRECT = "81 01 04 4C {value} FF"  # value: 0-15
    BRIGHTNESS_UP = "81 01 04 0D 02 FF"
    BRIGHTNESS_DOWN = "81 01 04 0D 03 FF"
    BRIGHTNESS_DIRECT = "81 01 04 4D {value} FF"  # value: 0-41
    BACKLIGHT_ON = "81 01 04 33 02 FF"
    BACKLIGHT_OFF = "81 01 04 33 03 FF"

    # White Balance Commands
    WHITE_BALANCE_MODE = (
        "81 01 04 35 {mode} FF"  # mode: 00=Auto, 01=Indoor, 02=Outdoor, 03=OnePush, 05=Manual
    )
    WHITE_BALANCE_ONE_PUSH = "81 01 04 10 05 FF"
    RED_GAIN_UP = "81 01 04 03 02 FF"
    RED_GAIN_DOWN = "81 01 04 03 03 FF"
    RED_GAIN_DIRECT = "81 01 04 43 00 00 {p} {q} FF"  # 0-255: split into nibbles
    BLUE_GAIN_UP = "81 01 04 04 02 FF"
    BLUE_GAIN_DOWN = "81 01 04 04 03 FF"
    BLUE_GAIN_DIRECT = "81 01 04 44 00 00 {p} {q} FF"  # 0-255: split into nibbles

    # Preset Commands
    PRESET_RECALL = "81 01 04 3F 02 {preset} FF"  # preset: 0-254
    PRESET_SAVE = "81 01 04 3F 01 {preset} FF"
    PRESET_SPEED = "81 01 06 01 {pan_speed} {tilt_speed} FF"

    # Video Format Commands
    VIDEO_FORMAT_SET = "81 01 06 35 00 {format} FF"  # format: see VideoFormat enum

    # Query Commands
    QUERY_FOCUS_MODE = "81 09 04 38 FF"  # Response: 90 50 0p FF (p: 2=Auto, 3=Manual)
    QUERY_EXPOSURE_MODE = "81 09 04 39 FF"  # Response: 90 50 0p FF
    QUERY_IRIS = "81 09 04 4B FF"  # Response: 90 50 0p 0q 0r 0s FF
    QUERY_SHUTTER = "81 09 04 4A FF"
    QUERY_GAIN = "81 09 04 4C FF"
    QUERY_BRIGHTNESS = "81 09 04 4D FF"
    QUERY_WHITE_BALANCE_MODE = "81 09 04 35 FF"
    QUERY_RED_GAIN = "81 09 04 43 FF"
    QUERY_BLUE_GAIN = "81 09 04 44 FF"
    QUERY_VIDEO_FORMAT = "81 09 06 23 FF"  # Response: 90 50 pp FF
    QUERY_BACKLIGHT = "81 09 04 33 FF"  # Response: 90 50 0p FF (p: 2=On, 3=Off)


# Speed Limits
class ViscaLimits:
    """VISCA protocol limits and ranges"""

    PAN_SPEED_MAX = 0x18  # 24 decimal
    TILT_SPEED_MAX = 0x14  # 20 decimal
    ZOOM_SPEED_MAX = 7
    FOCUS_SPEED_MAX = 7

    IRIS_MIN = 0
    IRIS_MAX = 17
    SHUTTER_MIN = 0
    SHUTTER_MAX = 21
    GAIN_MIN = 0
    GAIN_MAX = 15
    BRIGHTNESS_MIN = 0
    BRIGHTNESS_MAX = 41
    PRESET_MIN = 0
    PRESET_MAX = 254

    # Timeout settings
    COMMAND_TIMEOUT = 1.0  # seconds
    QUERY_TIMEOUT = 1.0
    CONNECTION_TIMEOUT = 2.0


# Response parsing helpers
class ViscaResponse:
    """VISCA response parsing utilities"""

    HEADER_LENGTH = 16  # VISCA-over-IP header in hex chars (8 bytes)

    @staticmethod
    def extract_single_nibble(response_hex: str, position: int = 5) -> int:
        """Extract single nibble from VISCA response after header"""
        visca_response = response_hex[ViscaResponse.HEADER_LENGTH :]
        return int(visca_response[position], 16)

    @staticmethod
    def extract_four_nibbles(response_hex: str) -> int:
        """Extract 4-nibble value from VISCA response (positions 5,7,9,11)"""
        visca_response = response_hex[ViscaResponse.HEADER_LENGTH :]
        p = int(visca_response[5], 16)
        q = int(visca_response[7], 16)
        r = int(visca_response[9], 16)
        s = int(visca_response[11], 16)
        return (p << 12) | (q << 8) | (r << 4) | s


class ViscaConstants:
    """VISCA protocol UI constants"""

    SHUTTER_SPEEDS = [
        "Auto",
        "Manual",
        "1/10000",
        "1/5000",
        "1/3000",
        "1/2000",
        "1/1500",
        "1/1000",
        "1/725",
        "1/500",
        "1/350",
        "1/250",
        "1/180",
        "1/125",
        "1/100",
        "1/90",
        "1/60",
        "1/50",
        "1/30",
        "1/25",
        "1/15",
        "1/8",
        "1/4",
    ]
