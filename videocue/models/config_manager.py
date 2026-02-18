"""
Configuration manager for JSON persistence
"""

import json
import logging
import os
import uuid
from pathlib import Path

from videocue.constants import NetworkConstants, UIConstants
from videocue.exceptions import ConfigLoadError, ConfigSaveError

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration persistence"""

    def __init__(self):
        # Use %LOCALAPPDATA%/VideoCue/config.json on Windows
        if os.name == "nt":
            config_dir = Path(os.getenv("LOCALAPPDATA", "")) / "VideoCue"
        else:
            # Use ~/.config/VideoCue on Unix
            config_dir = Path.home() / ".config" / "VideoCue"

        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_dir / "config.json"
        self.config = self.load()

    def load(self) -> dict:
        """Load configuration from JSON file"""
        if self.config_path.exists():
            try:
                with self.config_path.open(encoding="utf-8") as f:
                    config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_path}")
                return config
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in config file: {e}")
                raise ConfigLoadError(f"Invalid JSON: {e}") from e
            except OSError as e:
                logger.error(f"Error reading config file: {e}")
                raise ConfigLoadError(f"Cannot read config: {e}") from e

        # Return default schema
        logger.info("No config file found, using defaults")
        return self._default_schema()

    def save(self) -> None:
        """Save configuration to JSON file"""
        try:
            with self.config_path.open("w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            logger.debug(f"Configuration saved to {self.config_path}")
        except OSError as e:
            logger.error(f"Error saving config: {e}")
            raise ConfigSaveError(f"Cannot save config: {e}") from e

    def _default_schema(self) -> dict:
        """Return default configuration schema"""
        return {
            "version": "1.0",
            "cameras": [],
            "preferences": {
                "video_size_default": [
                    UIConstants.VIDEO_DEFAULT_WIDTH,
                    UIConstants.VIDEO_DEFAULT_HEIGHT,
                ],
                "video_frame_skip": 6,
                "theme": "dark",
                "auto_discover_ndi": True,
                "ndi_video_enabled": True,
                "file_logging_enabled": False,
                "single_instance_mode": True,
            },
            "usb_controller": {
                "enabled": True,
                "device_name": "",
                "dpad_speed": 0.7,
                "joystick_speed": 1.0,
                "zoom_speed": 0.7,
                "invert_vertical": False,
                "joystick_mode": "single",
                "stop_on_camera_switch": True,
                "brightness_enabled": True,
                "brightness_step": 1,
                "brightness_increase_button": 3,
                "brightness_decrease_button": 0,
                "focus_one_push_button": 1,
                "stop_movement_button": 2,
                "menu_button": 7,
                "button_mappings": {
                    "button_4": "prev_camera",
                    "button_5": "next_camera",
                    "axis_0": "pan",
                    "axis_1": "tilt",
                    "axis_4": "zoom_out",
                    "axis_5": "zoom_in",
                },
            },
        }

    def add_camera(
        self,
        ndi_source_name: str,
        visca_ip: str,
        visca_port: int | None = None,
        video_size: list[int] | None = None,
    ) -> str:
        """Add camera to configuration, return camera ID"""
        camera_id = str(uuid.uuid4())
        if video_size is None:
            video_size = self.config["preferences"]["video_size_default"]
        if visca_port is None:
            visca_port = NetworkConstants.VISCA_DEFAULT_PORT

        camera = {
            "id": camera_id,
            "ndi_source_name": ndi_source_name,
            "visca_ip": visca_ip,
            "visca_port": visca_port,
            "video_size": video_size,
            "position": len(self.config["cameras"]),
            "presets": [],
        }

        self.config["cameras"].append(camera)
        self.save()
        return camera_id

    def remove_camera(self, camera_id: str):
        """Remove camera from configuration"""
        self.config["cameras"] = [cam for cam in self.config["cameras"] if cam["id"] != camera_id]
        # Reorder positions
        for i, cam in enumerate(self.config["cameras"]):
            cam["position"] = i
        self.save()

    def reorder_cameras(self, camera_ids: list) -> None:
        """Reorder cameras based on provided list of camera IDs"""
        # Create a mapping of camera ID to camera config
        camera_map = {cam["id"]: cam for cam in self.config["cameras"]}

        # Rebuild cameras list in the new order
        new_cameras = []
        for camera_id in camera_ids:
            if camera_id in camera_map:
                new_cameras.append(camera_map[camera_id])

        # Update positions
        for i, cam in enumerate(new_cameras):
            cam["position"] = i

        self.config["cameras"] = new_cameras
        self.save()  # Now consistent - always auto-save

    def update_camera(self, camera_id: str, **kwargs):
        """Update camera configuration"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                cam.update(kwargs)
                self.save()
                break

    def get_camera(self, camera_id: str) -> dict | None:
        """Get camera configuration by ID"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                return cam
        return None

    def get_camera_by_ndi_name(self, ndi_name: str) -> dict | None:
        """
        Find camera by NDI source name using fuzzy matching.
        Matches base name before IP address in parentheses.
        """
        search_base = ndi_name.split("(")[0].strip()

        for cam in self.config["cameras"]:
            stored_name = cam.get("ndi_source_name", "")
            stored_base = stored_name.split("(")[0].strip()

            if stored_base == search_base:
                # Update stored name with current full name (IP may have changed)
                cam["ndi_source_name"] = ndi_name
                return cam

        return None

    def update_camera_ndi_name(self, camera_id: str, ndi_name: str):
        """Update NDI source name for a camera"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                cam["ndi_source_name"] = ndi_name
                break

    def add_preset(self, camera_id: str, name: str, pan: int, tilt: int, zoom: int):
        """Add preset to camera"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                preset = {"name": name, "pan": pan, "tilt": tilt, "zoom": zoom}
                cam["presets"].append(preset)
                self.save()
                break

    def remove_preset(self, camera_id: str, preset_name: str):
        """Remove preset from camera"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                cam["presets"] = [p for p in cam["presets"] if p["name"] != preset_name]
                self.save()
                break

    def update_preset_name(self, camera_id: str, old_name: str, new_name: str):
        """Rename a preset"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                for preset in cam["presets"]:
                    if preset["name"] == old_name:
                        preset["name"] = new_name
                        self.save()
                        return True
                break
        return False

    def update_preset(self, camera_id: str, preset_name: str, pan: int, tilt: int, zoom: int):
        """Update preset position values"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                for preset in cam["presets"]:
                    if preset["name"] == preset_name:
                        preset["pan"] = pan
                        preset["tilt"] = tilt
                        preset["zoom"] = zoom
                        self.save()
                        return True
                break
        return False

    def reorder_preset(self, camera_id: str, preset_name: str, direction: str):
        """Move preset up or down in the list"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                presets = cam["presets"]
                for i, preset in enumerate(presets):
                    if preset["name"] == preset_name:
                        if direction == "up" and i > 0:
                            # Swap with previous
                            presets[i], presets[i - 1] = presets[i - 1], presets[i]
                            self.save()
                            return True
                        if direction == "down" and i < len(presets) - 1:
                            # Swap with next
                            presets[i], presets[i + 1] = presets[i + 1], presets[i]
                            self.save()
                            return True
                        break
                break
        return False

    def get_presets(self, camera_id: str) -> list[dict]:
        """Get all presets for camera"""
        cam = self.get_camera(camera_id)
        return cam.get("presets", []) if cam else []

    def set_default_video_size(self, width: int, height: int):
        """Set default video size preference"""
        self.config["preferences"]["video_size_default"] = [width, height]
        self.save()

    def get_default_video_size(self) -> list[int]:
        """Get default video size preference"""
        return self.config["preferences"]["video_size_default"]

    def set_video_frame_skip(self, skip: int):
        """Set video frame skip rate (higher = lower framerate, better performance)"""
        self.config["preferences"]["video_frame_skip"] = skip
        self.save()

    def get_video_frame_skip(self) -> int:
        """Get video frame skip rate (default 6 = ~10 FPS from 60 FPS source)"""
        return self.config["preferences"].get("video_frame_skip", 6)

    def set_ndi_video_enabled(self, enabled: bool):
        """Set NDI video enabled/disabled globally"""
        self.config["preferences"]["ndi_video_enabled"] = enabled
        self.save()

    def get_ndi_video_enabled(self) -> bool:
        """Get NDI video enabled/disabled preference (default True)"""
        return self.config["preferences"].get("ndi_video_enabled", True)

    def set_single_instance_mode(self, enabled: bool):
        """Set single instance mode enabled/disabled"""
        self.config["preferences"]["single_instance_mode"] = enabled
        self.save()

    def get_single_instance_mode(self) -> bool:
        """Get single instance mode preference (default True)"""
        return self.config["preferences"].get("single_instance_mode", True)

    def set_usb_controller_name(self, name: str):
        """Set USB controller device name"""
        self.config["usb_controller"]["device_name"] = name
        self.save()

    def get_usb_controller_config(self) -> dict:
        """Get USB controller configuration"""
        return self.config.get("usb_controller", self._default_schema()["usb_controller"])

    def get_cameras(self) -> list[dict]:
        """Get all cameras sorted by position"""
        return sorted(self.config["cameras"], key=lambda c: c["position"])
