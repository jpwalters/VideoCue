"""
Video size model and presets
"""

import uuid


class VideoSize:
    """Video display size preset"""

    def __init__(self, name: str, width: int, height: int):
        self.name = name
        self.width = width
        self.height = height

    def __str__(self):
        """Return string representation"""
        return self.name

    def __repr__(self):
        return f"VideoSize({self.name}, {self.width}x{self.height})"

    @staticmethod
    def presets():
        """Return list of predefined video sizes"""
        return [
            VideoSize("384 x 216", 384, 216),
            VideoSize("512 x 288", 512, 288),
            VideoSize("640 x 360", 640, 360),
            VideoSize("768 x 432", 768, 432),
            VideoSize("896 x 504", 896, 504),
        ]

    @staticmethod
    def get_default():
        """Return default video size (512x288)"""
        return VideoSize.presets()[1]


class CameraPreset:
    """
    Camera preset for VISCA memory recall

    The camera stores the actual PTZ position in its firmware memory.
    This class only tracks metadata for the UI.

    Attributes:
        uuid: Unique identifier for Cue tab references
        name: User-friendly display name
        preset_number: Camera memory slot (0-127 for Birddog, 0-254 for VISCA)
    """

    def __init__(self, name: str, preset_number: int, preset_uuid: str = None):
        self.uuid = preset_uuid if preset_uuid else str(uuid.uuid4())
        self.name = name
        self.preset_number = preset_number

    def to_dict(self):
        """Convert preset to dictionary for JSON storage"""
        return {
            "uuid": self.uuid,
            "name": self.name,
            "preset_number": self.preset_number,
        }

    @staticmethod
    def from_dict(data: dict):
        """Create preset from dictionary (supports legacy format)"""
        # Support legacy format without uuid/preset_number
        if "uuid" not in data or "preset_number" not in data:
            # Legacy format - generate new UUID and use 0 as preset number
            return CameraPreset(
                name=data["name"],
                preset_number=data.get("preset_number", 0),
                preset_uuid=data.get("uuid", str(uuid.uuid4())),
            )

        return CameraPreset(
            name=data["name"], preset_number=data["preset_number"], preset_uuid=data["uuid"]
        )
