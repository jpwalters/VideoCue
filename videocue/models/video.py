"""
Video size model and presets
"""


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
    """Camera preset storing PTZ position"""

    def __init__(self, name: str, pan: int = 0, tilt: int = 0, zoom: int = 0):
        self.name = name
        self.pan = pan
        self.tilt = tilt
        self.zoom = zoom

    def to_dict(self):
        """Convert preset to dictionary"""
        return {
            'name': self.name,
            'pan': self.pan,
            'tilt': self.tilt,
            'zoom': self.zoom
        }

    @staticmethod
    def from_dict(data: dict):
        return CameraPreset(
            name=data['name'],
            pan=data.get('pan', 0),
            tilt=data.get('tilt', 0),
            zoom=data.get('zoom', 0)
        )
