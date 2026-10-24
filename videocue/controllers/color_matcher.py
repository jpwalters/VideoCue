"""
Closed-loop color matching of a target BirdDog camera to a reference camera.

The two sensors can't be modelled without a chart, so the matcher changes target settings,
measures the effect on the live NDI picture, and solves for the settings that minimise the
difference to the reference (Levenberg-Marquardt with a measured Jacobian).
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QImage

from videocue.controllers.birddog_api import BirdDogAPI, BirdDogAPIError, BirdDogModel
from videocue.controllers.visca_ip import ViscaIP, WhiteBalanceMode
from videocue.models.color_analysis import (
    WB_WEIGHT,
    ColorSignature,
    color_residual,
    common_sector_mask,
    compute_signature,
    qimage_to_rgb,
    residual_error,
    wb_residual,
)
from videocue.ui_strings import UIStrings

logger = logging.getLogger(__name__)

FRAMES_PER_SAMPLE = 3
CAPTURE_TIMEOUT_S = 4.0
SETTLE_MIN_S = 0.6
SETTLE_MAX_S = 3.0
SETTLE_EPS = 0.25
MATCH_TIMEOUT_S = 180.0
WB_TOLERANCE = 0.4
COLOR_TOLERANCE = 0.5
WB_MAX_ITERS = 6
WB_TOUCHUP_ITERS = 3
COLOR_MAX_ITERS = 4

WB_ENDPOINT = "birddogwbsetup"
CM_ENDPOINT = "birddogcmsetup"
WB_READ_ONLY_FIELDS = frozenset({"OnePushTrigger"})
WB_GAIN_FIELDS = ("RedGain", "BlueGain")
MANUAL_WB_MODES = frozenset({"USER", "MANUAL"})


@dataclass(frozen=True)
class ParamSpec:
    name: str
    lo: int
    hi: int
    probe_step: int
    max_dev: int


# The camera REST API accepts out-of-range values without clamping, so limits are enforced here
P400_COLOR_PARAMS = (
    ParamSpec("Level", 0, 14, 2, 6),
    ParamSpec("Phase", 0, 14, 2, 5),
    ParamSpec("RG", -99, 99, 15, 60),
    ParamSpec("RB", -99, 99, 15, 60),
    ParamSpec("GR", -99, 99, 15, 60),
    ParamSpec("GB", -99, 99, 15, 60),
    ParamSpec("BR", -99, 99, 15, 60),
    ParamSpec("BG", -99, 99, 15, 60),
)
P200_COLOR_PARAMS = (
    ParamSpec("ColourGain", 0, 255, 12, 60),
    ParamSpec("HuePhase", 0, 255, 8, 40),
    *(
        ParamSpec(f"{color}{kind}", 0, 63, 4, 16)
        for color in ("Red", "Yellow", "Green", "Cyan", "Blue", "Mag")
        for kind in ("Gain", "Hue")
    ),
)
COLOR_PARAMS = {
    BirdDogModel.P400: (WB_ENDPOINT, P400_COLOR_PARAMS),
    BirdDogModel.P200: (CM_ENDPOINT, P200_COLOR_PARAMS),
}
SEED_FIELDS = {
    BirdDogModel.P400: (
        WB_ENDPOINT,
        ("Matrix", "Select", "Level", "Phase", "RG", "RB", "GR", "GB", "BR", "BG"),
    ),
    BirdDogModel.P200: (CM_ENDPOINT, tuple(p.name for p in P200_COLOR_PARAMS)),
}
WB_PARAMS = (ParamSpec("RedGain", 0, 255, 10, 80), ParamSpec("BlueGain", 0, 255, 10, 80))


class ColorMatchError(Exception):
    """Color matching could not be completed"""


class ColorMatchCancelledError(ColorMatchError):
    """User cancelled color matching"""


@dataclass
class ColorMatchEndpoint:
    name: str
    ip: str
    visca: ViscaIP
    sampler_key: str


@dataclass
class ColorSnapshot:
    model: BirdDogModel
    wb: dict
    cm: dict = field(default_factory=dict)


def _clean(data: dict) -> dict:
    return {k: v for k, v in data.items() if not k.startswith("_")}


def take_snapshot(api: BirdDogAPI) -> ColorSnapshot:
    model = api.detect_model()
    wb = {
        k: v
        for k, v in _clean(api.get_endpoint(WB_ENDPOINT)).items()
        if k not in WB_READ_ONLY_FIELDS
    }
    cm = _clean(api.get_endpoint(CM_ENDPOINT)) if model == BirdDogModel.P200 else {}
    return ColorSnapshot(model=model, wb=wb, cm=cm)


def verify_snapshot(api: BirdDogAPI, snapshot: ColorSnapshot) -> list[str]:
    """Return descriptions of fields that differ from the snapshot."""
    mismatches = []
    current_wb = api.get_endpoint(WB_ENDPOINT)
    manual = snapshot.wb.get("WbMode") in MANUAL_WB_MODES
    for key, value in snapshot.wb.items():
        if key in WB_GAIN_FIELDS and not manual:
            continue  # gains drift continuously in auto modes
        if current_wb.get(key) != value:
            mismatches.append(f"{WB_ENDPOINT}.{key}: {current_wb.get(key)} != {value}")
    if snapshot.cm:
        current_cm = api.get_endpoint(CM_ENDPOINT)
        for key, value in snapshot.cm.items():
            if current_cm.get(key) != value:
                mismatches.append(f"{CM_ENDPOINT}.{key}: {current_cm.get(key)} != {value}")
    return mismatches


def restore_snapshot(api: BirdDogAPI, snapshot: ColorSnapshot) -> list[str]:
    """Write snapshot values back and return any fields that did not restore."""
    wb = dict(snapshot.wb)
    mode = wb.pop("WbMode", None)
    gains = {k: wb.pop(k) for k in WB_GAIN_FIELDS if k in wb}
    if snapshot.cm:
        api.post_endpoint(CM_ENDPOINT, snapshot.cm)
    if wb:
        api.post_endpoint(WB_ENDPOINT, wb)
    if mode is not None:
        api.post_endpoint(WB_ENDPOINT, {"WbMode": mode})
        if mode in MANUAL_WB_MODES and gains:
            api.post_endpoint(WB_ENDPOINT, gains)
    time.sleep(0.3)
    return verify_snapshot(api, snapshot)


def _restore_logged(api: BirdDogAPI, snapshot: ColorSnapshot) -> None:
    try:
        mismatches = restore_snapshot(api, snapshot)
    except BirdDogAPIError:
        logger.exception("Failed to restore color settings on %s", api.ip)
        return
    if mismatches:
        logger.warning("Color settings on %s not fully restored: %s", api.ip, mismatches)


class _FrameTap(QObject):
    def __init__(self, sampler: FrameSampler, key: str):
        super().__init__()
        self._sampler = sampler
        self._key = key

    @pyqtSlot(QImage)
    def on_frame(self, image: QImage) -> None:
        self._sampler.store(self._key, image)


class FrameSampler:
    """Thread-safe latest-frame store fed directly from NDI threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._frames: dict[str, tuple[int, QImage]] = {}
        self._taps: list[tuple[object, _FrameTap]] = []

    def attach(self, key: str, ndi_thread) -> None:
        tap = _FrameTap(self, key)
        # Direct connection: frames arrive even while the main thread is blocked
        ndi_thread.frame_ready.connect(tap.on_frame, Qt.ConnectionType.DirectConnection)
        self._taps.append((ndi_thread, tap))

    def detach_all(self) -> None:
        for ndi_thread, tap in self._taps:
            with contextlib.suppress(TypeError, RuntimeError):
                ndi_thread.frame_ready.disconnect(tap.on_frame)
        self._taps.clear()
        with self._lock:
            self._frames.clear()

    def store(self, key: str, image: QImage) -> None:
        with self._lock:
            seq = self._frames.get(key, (0, None))[0] + 1
            self._frames[key] = (seq, image)

    def _latest(self, key: str) -> tuple[int, QImage | None]:
        with self._lock:
            return self._frames.get(key, (0, None))

    def latest_image(self, key: str) -> QImage | None:
        return self._latest(key)[1]

    def capture(
        self,
        keys: tuple[str, ...],
        count: int = FRAMES_PER_SAMPLE,
        timeout: float = CAPTURE_TIMEOUT_S,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, list[np.ndarray]]:
        """Collect `count` new frames per key (frames already stored are ignored)."""
        last_seq = {key: self._latest(key)[0] for key in keys}
        frames: dict[str, list[np.ndarray]] = {key: [] for key in keys}
        deadline = time.monotonic() + timeout
        while any(len(frames[key]) < count for key in keys):
            if cancel_event is not None and cancel_event.is_set():
                raise ColorMatchCancelledError(UIStrings.STATUS_MATCH_CANCELLED)
            got_frame = False
            for key in keys:
                if len(frames[key]) >= count:
                    continue
                seq, image = self._latest(key)
                if seq > last_seq[key] and image is not None:
                    last_seq[key] = seq
                    frames[key].append(qimage_to_rgb(image))
                    got_frame = True
            if time.monotonic() > deadline:
                missing = [key for key in keys if len(frames[key]) < count]
                raise ColorMatchError(f"{UIStrings.ERROR_MATCH_NO_VIDEO} ({', '.join(missing)})")
            if not got_frame:
                time.sleep(0.02)
        return frames

    def signatures(
        self, ref_key: str, tgt_key: str, cancel_event: threading.Event | None = None
    ) -> tuple[ColorSignature, ColorSignature]:
        frames = self.capture((ref_key, tgt_key), cancel_event=cancel_event)
        try:
            return compute_signature(frames[ref_key]), compute_signature(frames[tgt_key])
        except ValueError as e:
            raise ColorMatchError(f"{UIStrings.ERROR_MATCH_SCENE}: {e}") from e


class ColorMatchWorker(QThread):
    """Matches the target camera's white balance and color to the reference camera."""

    progress = pyqtSignal(int, str)
    match_finished = pyqtSignal(dict)
    match_failed = pyqtSignal(str)

    def __init__(
        self,
        reference: ColorMatchEndpoint,
        target: ColorMatchEndpoint,
        sampler: FrameSampler,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.reference = reference
        self.target = target
        self.sampler = sampler
        self._cancel = threading.Event()
        self._deadline = 0.0
        self._progress_base = 0
        self._progress_span = 0
        self._progress_steps = 1
        self._progress_done = 0
        self._progress_text = ""

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            self.match_finished.emit(self.execute())
        except ColorMatchCancelledError:
            self.match_failed.emit(UIStrings.STATUS_MATCH_CANCELLED)
        except Exception as e:
            logger.exception("Color match failed")
            self.match_failed.emit(str(e))

    # ----- progress -----

    def _stage(self, base: int, span: int, text: str, steps: int = 1) -> None:
        self._progress_base, self._progress_span = base, span
        self._progress_steps, self._progress_done = max(steps, 1), 0
        self._progress_text = text
        self.progress.emit(base, text)

    def _step(self) -> None:
        self._progress_done = min(self._progress_done + 1, self._progress_steps)
        value = (
            self._progress_base + self._progress_span * self._progress_done // self._progress_steps
        )
        self.progress.emit(value, self._progress_text)

    def _check(self) -> None:
        if self._cancel.is_set():
            raise ColorMatchCancelledError(UIStrings.STATUS_MATCH_CANCELLED)

    def _out_of_time(self) -> bool:
        return time.monotonic() > self._deadline

    # ----- measurement -----

    def _signatures(self) -> tuple[ColorSignature, ColorSignature]:
        return self.sampler.signatures(
            self.reference.sampler_key, self.target.sampler_key, self._cancel
        )

    def _settled(self, residual_fn: Callable[[ColorSignature, ColorSignature], np.ndarray]):
        """Wait for the picture to stop changing after a settings change, then measure."""
        self._check()
        time.sleep(SETTLE_MIN_S)
        start = time.monotonic()
        previous = None
        while True:
            residual = residual_fn(*self._signatures())
            if previous is not None and (
                residual_error(residual - previous) < SETTLE_EPS
                or time.monotonic() - start > SETTLE_MAX_S
            ):
                self._step()
                return (residual + previous) / 2
            previous = residual

    # ----- optimizer -----

    def _optimize(
        self,
        params: tuple[ParamSpec, ...],
        start: dict[str, int],
        apply_fn: Callable[[dict[str, int]], None],
        residual_fn: Callable[[ColorSignature, ColorSignature], np.ndarray],
        max_iters: int,
        tolerance: float,
        jacobian: np.ndarray | None = None,
    ) -> tuple[dict[str, int], float, np.ndarray | None]:
        n = len(params)
        x = np.array([start[p.name] for p in params], dtype=np.float64)
        lo = np.array([max(p.lo, x[i] - p.max_dev) for i, p in enumerate(params)])
        hi = np.array([min(p.hi, x[i] + p.max_dev) for i, p in enumerate(params)])

        residual = self._settled(residual_fn)
        error = residual_error(residual)
        logger.info("Optimize start %s error=%.3f", [p.name for p in params], error)
        if error < tolerance:
            return self._as_dict(params, x), error, jacobian

        if jacobian is None or jacobian.shape != (residual.size, n):
            jacobian = np.zeros((residual.size, n))
            for i, p in enumerate(params):
                self._check()
                step = p.probe_step if x[i] + p.probe_step <= hi[i] else -p.probe_step
                apply_fn({p.name: int(x[i] + step)})
                probed = self._settled(residual_fn)
                jacobian[:, i] = (probed - residual) / step
                apply_fn({p.name: int(x[i])})
            residual = self._settled(residual_fn)
            error = residual_error(residual)

        damping = 1.0
        for _ in range(max_iters):
            self._check()
            if error < tolerance or self._out_of_time():
                break
            jtj = jacobian.T @ jacobian
            diag = np.diag(jtj)
            ridge = 1e-6 * max(float(diag.max()), 1e-12)
            system = jtj + damping * np.diag(diag) + ridge * np.eye(n)
            delta = -np.linalg.solve(system, jacobian.T @ residual)
            candidate = np.clip(np.round(x + delta), lo, hi)
            dx = candidate - x
            if not dx.any():
                if damping <= 1e-2:
                    break
                damping /= 4
                continue

            apply_fn(self._as_dict(params, candidate, changed_from=x))
            new_residual = self._settled(residual_fn)
            new_error = residual_error(new_residual)
            logger.info(
                "Optimize step error %.3f -> %.3f (damping %.3g)", error, new_error, damping
            )

            # Broyden update keeps the Jacobian current without re-probing every parameter
            jacobian += np.outer(new_residual - residual - jacobian @ dx, dx) / float(dx @ dx)
            if new_error < error:
                x, residual, error = candidate, new_residual, new_error
                damping = max(damping / 3, 1e-3)
            else:
                apply_fn(self._as_dict(params, x, changed_from=candidate))
                damping *= 4
        return self._as_dict(params, x), error, jacobian

    @staticmethod
    def _as_dict(
        params: tuple[ParamSpec, ...], x: np.ndarray, changed_from: np.ndarray | None = None
    ) -> dict[str, int]:
        return {
            p.name: int(x[i])
            for i, p in enumerate(params)
            if changed_from is None or x[i] != changed_from[i]
        }

    # ----- camera writes -----

    def _apply_wb(self, values: dict[str, int]) -> None:
        if "RedGain" in values:
            self.target.visca.set_red_gain(values["RedGain"])
        if "BlueGain" in values:
            self.target.visca.set_blue_gain(values["BlueGain"])

    # ----- main flow -----

    def execute(self) -> dict:
        started = time.monotonic()
        self._deadline = started + MATCH_TIMEOUT_S
        self._stage(0, 5, UIStrings.STATUS_MATCH_PREFLIGHT)
        try:
            ref_api = BirdDogAPI(self.reference.ip)
            tgt_api = BirdDogAPI(self.target.ip)
            ref_model = ref_api.detect_model()
            tgt_model = tgt_api.detect_model()
            ref_wb = ref_api.get_endpoint(WB_ENDPOINT)
        except (BirdDogAPIError, ValueError) as e:
            raise ColorMatchError(f"{UIStrings.ERROR_MATCH_REST_UNAVAILABLE}: {e}") from e
        if tgt_model not in COLOR_PARAMS:
            raise ColorMatchError(UIStrings.ERROR_MATCH_UNSUPPORTED_MODEL)

        ref_sig, tgt_sig = self._signatures()
        mask = common_sector_mask(ref_sig, tgt_sig)

        def full_residual(r: ColorSignature, t: ColorSignature) -> np.ndarray:
            return color_residual(r, t, mask)

        def wb_only(r: ColorSignature, t: ColorSignature) -> np.ndarray:
            return wb_residual(r, t)

        self._stage(5, 5, UIStrings.STATUS_MATCH_SNAPSHOT)
        try:
            snapshot = take_snapshot(tgt_api)
        except BirdDogAPIError as e:
            raise ColorMatchError(f"{UIStrings.ERROR_MATCH_REST_UNAVAILABLE}: {e}") from e

        try:
            before = self._settled(full_residual)
            wb_before = residual_error(before[:2] / WB_WEIGHT)
            error_before = residual_error(before)

            self._stage(10, 5, UIStrings.STATUS_MATCH_SEED)
            wb_start = {k: int(snapshot.wb.get(k, 128)) for k in WB_GAIN_FIELDS}
            if ref_model == tgt_model:
                endpoint, fields = SEED_FIELDS[tgt_model]
                source = ref_wb if endpoint == WB_ENDPOINT else ref_api.get_endpoint(endpoint)
                tgt_api.post_endpoint(endpoint, {k: source[k] for k in fields if k in source})
                wb_start = {k: int(ref_wb.get(k, wb_start[k])) for k in WB_GAIN_FIELDS}
            self.target.visca.set_white_balance_mode(WhiteBalanceMode.MANUAL)
            time.sleep(0.2)
            self._apply_wb(wb_start)

            self._stage(15, 25, UIStrings.STATUS_MATCH_WB, steps=2 * WB_MAX_ITERS + 4)
            wb_values, _, wb_jacobian = self._optimize(
                WB_PARAMS, wb_start, self._apply_wb, wb_only, WB_MAX_ITERS, WB_TOLERANCE
            )

            color_values = self._match_color(tgt_api, tgt_model, mask, full_residual)

            self._stage(85, 10, UIStrings.STATUS_MATCH_WB, steps=WB_TOUCHUP_ITERS + 2)
            wb_values, _, _ = self._optimize(
                WB_PARAMS,
                wb_values,
                self._apply_wb,
                wb_only,
                WB_TOUCHUP_ITERS,
                WB_TOLERANCE,
                jacobian=wb_jacobian,
            )

            self._stage(95, 5, UIStrings.STATUS_MATCH_VERIFY, steps=1)
            after = self._settled(full_residual)
        except BaseException:
            _restore_logged(tgt_api, snapshot)
            raise

        error_after = residual_error(after)
        improved = error_after < error_before
        if not improved:
            _restore_logged(tgt_api, snapshot)

        ref_sig, tgt_sig = self._signatures()
        self.progress.emit(100, UIStrings.STATUS_MATCH_DONE)
        return {
            "reference": self.reference.name,
            "target": self.target.name,
            "reference_model": ref_model.value,
            "target_model": tgt_model.value,
            "reference_auto_wb": ref_wb.get("WbMode") not in MANUAL_WB_MODES,
            "error_before": error_before,
            "error_after": error_after,
            "wb_error_before": wb_before,
            "wb_error_after": residual_error(after[:2] / WB_WEIGHT),
            "sectors_compared": int(mask.sum()),
            "sector_mask": mask.tolist(),
            "luma_reference": ref_sig.mean_luma,
            "luma_target": tgt_sig.mean_luma,
            "improved": improved,
            "applied": {"wb": wb_values, "color": color_values} if improved else {},
            "snapshot": snapshot,
            "duration_s": round(time.monotonic() - started, 1),
        }

    def _match_color(
        self,
        api: BirdDogAPI,
        model: BirdDogModel,
        mask: np.ndarray,
        residual_fn: Callable[[ColorSignature, ColorSignature], np.ndarray],
    ) -> dict[str, int]:
        endpoint, params = COLOR_PARAMS[model]
        if not mask.any():
            logger.info("No hue sectors in common; skipping color stage")
            return {}

        self._stage(
            40, 45, UIStrings.STATUS_MATCH_COLOR, steps=len(params) + 2 * COLOR_MAX_ITERS + 3
        )
        stage_start = _clean(api.get_endpoint(endpoint))
        params = tuple(p for p in params if p.name in stage_start)
        start_error = residual_error(self._settled(residual_fn))
        if not params or start_error < COLOR_TOLERANCE:
            return {}

        if model == BirdDogModel.P400 and stage_start.get("Matrix") != "On":
            api.post_endpoint(endpoint, {"Matrix": "On"})

        start = {p.name: int(stage_start[p.name]) for p in params}
        values, error, _ = self._optimize(
            params,
            start,
            lambda v: api.post_endpoint(endpoint, v),
            residual_fn,
            COLOR_MAX_ITERS,
            COLOR_TOLERANCE,
        )
        if error >= start_error:
            logger.info("Color stage did not improve (%.3f >= %.3f); reverting", error, start_error)
            restore = {p.name: stage_start[p.name] for p in params}
            if "Matrix" in stage_start:
                restore["Matrix"] = stage_start["Matrix"]
            api.post_endpoint(endpoint, restore)
            return {}
        return values
