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
        changed = self._normalize_cameras()
        if self._normalize_presets():
            changed = True
        if changed:
            self.save()

    def _normalize_cameras(self) -> bool:
        """Normalize camera IDs and positions in loaded configuration."""
        changed = False
        cameras = self.config.get("cameras", [])

        if not isinstance(cameras, list):
            self.config["cameras"] = []
            return True

        seen_ids: set[str] = set()
        for index, camera in enumerate(cameras):
            if not isinstance(camera, dict):
                continue

            camera_id = camera.get("id")
            if not isinstance(camera_id, str) or not camera_id or camera_id in seen_ids:
                camera_id = str(uuid.uuid4())
                camera["id"] = camera_id
                changed = True
            seen_ids.add(camera_id)

            if camera.get("position") != index:
                camera["position"] = index
                changed = True

        return changed

    @staticmethod
    def _next_available_slot(used_slots: set[int], max_slots: int = 128) -> int | None:
        """Return first available preset slot number."""
        for slot in range(max_slots):
            if slot not in used_slots:
                return slot
        return None

    def _normalize_presets(self) -> bool:
        """Normalize legacy/invalid preset data in loaded configuration."""
        changed = False

        for camera in self.config.get("cameras", []):
            presets = camera.get("presets", [])
            if not isinstance(presets, list):
                camera["presets"] = []
                changed = True
                continue

            used_slots: set[int] = set()
            seen_uuids: set[str] = set()

            for preset in presets:
                if not isinstance(preset, dict):
                    continue

                preset_uuid = preset.get("uuid")
                if not isinstance(preset_uuid, str) or not preset_uuid or preset_uuid in seen_uuids:
                    preset_uuid = str(uuid.uuid4())
                    preset["uuid"] = preset_uuid
                    changed = True
                seen_uuids.add(preset_uuid)

                preset_name = preset.get("name")
                if not isinstance(preset_name, str) or not preset_name:
                    preset["name"] = "Preset"
                    changed = True

                slot = preset.get("preset_number")
                slot_valid = isinstance(slot, int) and 0 <= slot < 128 and slot not in used_slots
                if not slot_valid:
                    next_slot = self._next_available_slot(used_slots, max_slots=128)
                    if next_slot is None:
                        continue
                    preset["preset_number"] = next_slot
                    slot = next_slot
                    changed = True

                used_slots.add(slot)

        return changed

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
                "ndi_bandwidth": "low",  # "high" or "low" - NDI receiver bandwidth mode
                "ndi_color_format": "uyvy",  # "uyvy", "bgra", or "rgba" - NDI color format
                "ndi_false_color_enabled": False,  # Atomos-style false color video mode
                "ndi_waveform_enabled": False,  # Luma waveform scope mode
                "ndi_vectorscope_enabled": False,  # Chroma vectorscope mode
                "theme": "dark",
                "auto_discover_ndi": True,
                "ndi_video_enabled": True,
                "file_logging_enabled": False,
                "single_instance_mode": True,
                "preferred_network_interface": None,  # Auto-detected or user-selected interface IP
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
                "run_cue_enabled": True,
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

    def add_preset(self, camera_id: str, name: str, preset_number: int, preset_uuid: str = None):
        """
        Add preset to camera

        Args:
            camera_id: Camera identifier
            name: Preset display name
            preset_number: Camera memory slot (0-127)
            preset_uuid: Optional UUID (generated if not provided)
        """
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                preset = {
                    "uuid": preset_uuid if preset_uuid else str(uuid.uuid4()),
                    "name": name,
                    "preset_number": preset_number,
                }
                cam["presets"].append(preset)
                self.save()
                break

    def remove_preset(self, camera_id: str, preset_uuid: str):
        """Remove preset from camera by UUID"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                cam["presets"] = [p for p in cam["presets"] if p.get("uuid") != preset_uuid]
                self.save()
                break

    def get_preset_by_uuid(self, camera_id: str, preset_uuid: str) -> dict | None:
        """Get preset by UUID"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                for preset in cam["presets"]:
                    if preset.get("uuid") == preset_uuid:
                        return preset
                break
        return None

    def update_preset_name(self, camera_id: str, preset_uuid: str, new_name: str):
        """Rename a preset by UUID"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                for preset in cam["presets"]:
                    if preset.get("uuid") == preset_uuid:
                        preset["name"] = new_name
                        self.save()
                        return True
                break
        return False

    def update_preset(self, camera_id: str, preset_uuid: str, **kwargs):
        """Update preset fields by UUID"""
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                for preset in cam["presets"]:
                    if preset.get("uuid") == preset_uuid:
                        preset.update(kwargs)
                        self.save()
                        return True
                break
        return False

    def get_next_available_preset_number(
        self, camera_id: str, max_presets: int = 128
    ) -> int | None:
        """
        Find next available preset number for camera (0-based)

        Args:
            camera_id: Camera identifier
            max_presets: Maximum preset slots (128 for Birddog, 254 for VISCA)

        Returns:
            Next available preset number (0-127), or None if all slots used
        """
        presets = self.get_presets(camera_id)
        used_numbers = {p.get("preset_number", -1) for p in presets}

        for i in range(max_presets):
            if i not in used_numbers:
                return i

        return None  # All slots used

    def reorder_preset(self, camera_id: str, preset_uuid: str, direction: str):
        """
        Move preset up or down in the DISPLAY list

        Note: This only changes UI display order, not camera memory slots.
        The preset_number field remains unchanged.
        """
        for cam in self.config["cameras"]:
            if cam["id"] == camera_id:
                presets = cam["presets"]
                for i, preset in enumerate(presets):
                    if preset.get("uuid") == preset_uuid:
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

    def set_ndi_bandwidth(self, bandwidth: str):
        """Set NDI bandwidth mode ('high' or 'low')"""
        self.config["preferences"]["ndi_bandwidth"] = bandwidth
        self.save()

    def get_ndi_bandwidth(self) -> str:
        """Get NDI bandwidth mode (default 'low')"""
        return self.config["preferences"].get("ndi_bandwidth", "low")

    def set_ndi_color_format(self, color_format: str):
        """Set NDI color format ('uyvy', 'bgra', or 'rgba')"""
        self.config["preferences"]["ndi_color_format"] = color_format
        self.save()

    def get_ndi_color_format(self) -> str:
        """Get NDI color format (default 'uyvy')"""
        return self.config["preferences"].get("ndi_color_format", "uyvy")

    def set_ndi_false_color_enabled(self, enabled: bool):
        """Set NDI false color mode enabled/disabled globally"""
        self.config["preferences"]["ndi_false_color_enabled"] = enabled
        self.save()

    def get_ndi_false_color_enabled(self) -> bool:
        """Get NDI false color mode preference (default False)"""
        return self.config["preferences"].get("ndi_false_color_enabled", False)

    def set_ndi_waveform_enabled(self, enabled: bool):
        """Set NDI waveform scope mode enabled/disabled globally"""
        self.config["preferences"]["ndi_waveform_enabled"] = enabled
        self.save()

    def get_ndi_waveform_enabled(self) -> bool:
        """Get NDI waveform scope mode preference (default False)"""
        return self.config["preferences"].get("ndi_waveform_enabled", False)

    def set_ndi_vectorscope_enabled(self, enabled: bool):
        """Set NDI vectorscope mode enabled/disabled globally"""
        self.config["preferences"]["ndi_vectorscope_enabled"] = enabled
        self.save()

    def get_ndi_vectorscope_enabled(self) -> bool:
        """Get NDI vectorscope mode preference (default False)"""
        return self.config["preferences"].get("ndi_vectorscope_enabled", False)

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

    def set_preferred_network_interface(self, interface_ip: str | None):
        """Set preferred network interface IP for NDI binding"""
        self.config["preferences"]["preferred_network_interface"] = interface_ip
        self.save()

    def get_preferred_network_interface(self) -> str | None:
        """Get preferred network interface IP (default None = auto-detect)"""
        return self.config["preferences"].get("preferred_network_interface", None)

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
