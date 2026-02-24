"""
Cue list manager for JSON persistence in dedicated cues.json file.
"""

import json
import logging
import uuid

from videocue.utils import get_app_data_dir

logger = logging.getLogger(__name__)


class CueManager:
    """Manages cue list persistence in a dedicated JSON file."""

    def __init__(self):
        self.cues_path = get_app_data_dir() / "cues.json"
        self.data = self.load()
        if self._normalize_cues():
            self.save()

    def _default_schema(self) -> dict:
        return {
            "version": "1.0",
            "camera_columns": [],
            "cues": [],
        }

    def load(self) -> dict:
        """Load cue configuration from cues.json."""
        if self.cues_path.exists():
            try:
                with self.cues_path.open(encoding="utf-8") as cue_file:
                    data = json.load(cue_file)
                logger.info("Cues loaded from %s", self.cues_path)
                return data
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to load cues file, using defaults")
                return self._default_schema()

        logger.info("No cues file found, using defaults")
        return self._default_schema()

    def save(self) -> None:
        """Save cue configuration to cues.json."""
        try:
            with self.cues_path.open("w", encoding="utf-8") as cue_file:
                json.dump(self.data, cue_file, indent=2)
            logger.debug("Cues saved to %s", self.cues_path)
        except OSError:
            logger.exception("Failed to save cues file")

    def _normalize_cues(self) -> bool:
        """Normalize cue data for legacy or malformed entries."""
        changed = False

        camera_columns = self.data.get("camera_columns")
        if not isinstance(camera_columns, list):
            self.data["camera_columns"] = []
            camera_columns = self.data["camera_columns"]
            changed = True

        normalized_columns: list[str] = []
        for column_camera_id in camera_columns:
            if not isinstance(column_camera_id, str) or not column_camera_id:
                changed = True
                continue
            if column_camera_id in normalized_columns:
                changed = True
                continue
            normalized_columns.append(column_camera_id)
        if normalized_columns != camera_columns:
            self.data["camera_columns"] = normalized_columns
            changed = True

        cues = self.data.get("cues")
        if not isinstance(cues, list):
            self.data["cues"] = []
            return True

        seen_ids: set[str] = set()
        normalized: list[dict] = []
        for cue in cues:
            if not isinstance(cue, dict):
                changed = True
                continue

            cue_id = cue.get("id")
            if not isinstance(cue_id, str) or not cue_id or cue_id in seen_ids:
                cue_id = str(uuid.uuid4())
                cue["id"] = cue_id
                changed = True
            seen_ids.add(cue_id)

            if not isinstance(cue.get("name"), str) or not cue.get("name"):
                cue["name"] = "Cue"
                changed = True

            cue_number = cue.get("cue_number")
            if cue_number is None:
                cue_number = cue.get("cue", "")
                cue["cue_number"] = str(cue_number) if cue_number is not None else ""
                changed = True
            elif not isinstance(cue_number, str):
                cue["cue_number"] = str(cue_number)
                changed = True

            if "camera_presets" not in cue:
                legacy_camera_id = cue.get("camera_id")
                legacy_preset_uuid = cue.get("preset_uuid")
                camera_presets: dict[str, str | None] = {}
                if isinstance(legacy_camera_id, str) and legacy_camera_id:
                    camera_presets[legacy_camera_id] = (
                        legacy_preset_uuid
                        if isinstance(legacy_preset_uuid, str) and legacy_preset_uuid
                        else None
                    )
                cue["camera_presets"] = camera_presets
                changed = True

            camera_presets_raw = cue.get("camera_presets")
            if not isinstance(camera_presets_raw, dict):
                cue["camera_presets"] = {}
                camera_presets_raw = cue["camera_presets"]
                changed = True

            normalized_camera_presets: dict[str, str | None] = {}
            for camera_id, preset_uuid in camera_presets_raw.items():
                if not isinstance(camera_id, str) or not camera_id:
                    changed = True
                    continue
                if isinstance(preset_uuid, str) and preset_uuid:
                    normalized_camera_presets[camera_id] = preset_uuid
                else:
                    normalized_camera_presets[camera_id] = None
                    if preset_uuid is not None:
                        changed = True

            if normalized_camera_presets != camera_presets_raw:
                cue["camera_presets"] = normalized_camera_presets
                changed = True

            normalized.append(cue)

        if len(normalized) != len(cues):
            self.data["cues"] = normalized
            changed = True

        return changed

    def get_cues(self) -> list[dict]:
        """Return all cues in display order."""
        return self.data.get("cues", [])

    def get_camera_columns(self) -> list[str]:
        """Return camera IDs used as cue table columns."""
        return self.data.get("camera_columns", [])

    def sync_camera_columns(self, loaded_camera_ids: list[str]) -> list[str]:
        """Ensure camera columns exist and include currently loaded cameras."""
        columns = self.get_camera_columns()

        if not columns:
            self.data["camera_columns"] = list(loaded_camera_ids)
            self.save()
            return self.data["camera_columns"]

        changed = False
        for camera_id in loaded_camera_ids:
            if camera_id not in columns:
                columns.append(camera_id)
                changed = True

        if changed:
            self.save()

        return columns

    def get_cue_by_id(self, cue_id: str) -> dict | None:
        """Return a cue by UUID."""
        for cue in self.get_cues():
            if cue.get("id") == cue_id:
                return cue
        return None

    def add_cue(self, cue_number: str, name: str, camera_columns: list[str]) -> str:
        """Create a cue row and return cue ID."""
        cue_id = str(uuid.uuid4())
        camera_presets = dict.fromkeys(camera_columns)
        cue = {
            "id": cue_id,
            "cue_number": cue_number,
            "name": name,
            "camera_presets": camera_presets,
        }
        self.data.setdefault("cues", []).append(cue)
        self.save()
        return cue_id

    def insert_cue_at(
        self,
        index: int,
        cue_number: str,
        name: str,
        camera_columns: list[str],
        camera_presets: dict[str, str | None] | None = None,
    ) -> str:
        """Insert cue row at index and return cue ID."""
        cue_id = str(uuid.uuid4())
        normalized_presets = dict.fromkeys(camera_columns)
        if camera_presets:
            for camera_id in camera_columns:
                preset_uuid = camera_presets.get(camera_id)
                normalized_presets[camera_id] = (
                    preset_uuid if isinstance(preset_uuid, str) else None
                )

        cue = {
            "id": cue_id,
            "cue_number": cue_number,
            "name": name,
            "camera_presets": normalized_presets,
        }

        cues = self.data.setdefault("cues", [])
        safe_index = max(0, min(index, len(cues)))
        cues.insert(safe_index, cue)
        self.save()
        return cue_id

    def duplicate_cue_at(self, cue_id: str, index: int, camera_columns: list[str]) -> str | None:
        """Duplicate existing cue and insert copy at index."""
        source = self.get_cue_by_id(cue_id)
        if not source:
            return None

        source_presets = source.get("camera_presets", {})
        if not isinstance(source_presets, dict):
            source_presets = {}

        return self.insert_cue_at(
            index=index,
            cue_number=str(source.get("cue_number", "")),
            name=str(source.get("name", "Cue")),
            camera_columns=camera_columns,
            camera_presets={
                camera_id: source_presets.get(camera_id) for camera_id in camera_columns
            },
        )

    def update_cue_field(self, cue_id: str, field_name: str, value: str) -> bool:
        """Update top-level cue field value."""
        cue = self.get_cue_by_id(cue_id)
        if not cue:
            return False

        if field_name not in {"cue_number", "name"}:
            return False

        cue[field_name] = value
        self.save()
        return True

    def update_camera_preset(self, cue_id: str, camera_id: str, preset_uuid: str | None) -> bool:
        """Update mapped preset for one camera column in a cue row."""
        cue = self.get_cue_by_id(cue_id)
        if not cue:
            return False

        camera_presets = cue.setdefault("camera_presets", {})
        if preset_uuid:
            camera_presets[camera_id] = preset_uuid
        else:
            camera_presets[camera_id] = None

        self.save()
        return True

    def remove_cue(self, cue_id: str) -> bool:
        """Delete cue by ID."""
        cues = self.get_cues()
        original_len = len(cues)
        self.data["cues"] = [cue for cue in cues if cue.get("id") != cue_id]
        changed = len(self.data["cues"]) != original_len
        if changed:
            self.save()
        return changed

    def get_preset_for_camera(self, cue_id: str, camera_id: str) -> str | None:
        """Return mapped preset UUID for a cue/camera pair."""
        cue = self.get_cue_by_id(cue_id)
        if not cue:
            return None

        camera_presets = cue.get("camera_presets", {})
        if not isinstance(camera_presets, dict):
            return None

        preset_uuid = camera_presets.get(camera_id)
        return preset_uuid if isinstance(preset_uuid, str) and preset_uuid else None
