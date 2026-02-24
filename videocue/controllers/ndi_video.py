"""
NDI video receiver with frame dropping for performance
"""

import contextlib
import logging
import os
import threading
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from videocue.constants import NetworkConstants
from videocue.exceptions import NDINotAvailableError, NDISourceNotFoundError

logger = logging.getLogger(__name__)

# Try to import NDI library (bundled with VideoCue)
# NDI wrapper is based on ndi-python by Naoto Kondo (MIT License)
# See videocue/ndi_wrapper/LICENSE.md for full attribution
ndi: Any = None  # Type annotation for ndi module (conditionally imported)
ndi_available = False
ndi_error_message = ""
_ndi_initialized = False
_global_finder = None
_ndi_lock = threading.Lock()  # Thread safety for global NDI resources
_source_cache: dict = {}  # Cache of discovered sources {source_name: ndi.Source}
_last_discovery_time = 0.0  # Track when we last did a full discovery
_preferred_network_interface: str | None = None  # Preferred network interface IP for NDI binding
_stream_metrics_lock = threading.Lock()
_stream_metrics = {
    "active_streams": 0,
    "connected_streams": 0,
    "failed_streams": 0,
    "starts": 0,
    "stops": 0,
}


def _stream_metrics_snapshot() -> dict[str, int]:
    with _stream_metrics_lock:
        return dict(_stream_metrics)


def _stream_metrics_on_start() -> None:
    with _stream_metrics_lock:
        _stream_metrics["active_streams"] += 1
        _stream_metrics["starts"] += 1


def _stream_metrics_on_connected() -> None:
    with _stream_metrics_lock:
        _stream_metrics["connected_streams"] += 1


def _stream_metrics_on_failed() -> None:
    with _stream_metrics_lock:
        _stream_metrics["failed_streams"] += 1


def _stream_metrics_on_stop(was_connected: bool) -> None:
    with _stream_metrics_lock:
        _stream_metrics["active_streams"] = max(0, _stream_metrics["active_streams"] - 1)
        _stream_metrics["stops"] += 1
        if was_connected:
            _stream_metrics["connected_streams"] = max(
                0, _stream_metrics["connected_streams"] - 1
            )


def _get_process_rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        pass

    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):  # noqa: N801
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE

        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        handle = get_current_process()
        ok = get_process_memory_info(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return None
        return counters.WorkingSetSize / (1024 * 1024)
    except Exception:
        return None


class _NDIMemoryProbe:
    def __init__(self, source_name: str):
        self.source_name = source_name
        self.enabled = os.getenv("VIDEOCUE_NDI_MEM_DEBUG", "0") == "1"
        self.interval_s = max(1, int(os.getenv("VIDEOCUE_NDI_MEM_INTERVAL_S", "10")))
        self.snapshot_interval_s = max(
            5, int(os.getenv("VIDEOCUE_NDI_MEM_SNAPSHOT_INTERVAL_S", "30"))
        )
        self.top_n = max(1, int(os.getenv("VIDEOCUE_NDI_MEM_TOP_N", "5")))
        self.wrapper_imbalance_warn_threshold = max(
            1, int(os.getenv("VIDEOCUE_NDI_WRAPPER_IMBALANCE_WARN", "500"))
        )
        self._last_log_at = 0.0
        self._last_snapshot_at = 0.0
        self._baseline_rss = None
        self._last_rss = None
        self._last_snapshot = None
        self._last_wrapper_counters = None

        if not self.enabled:
            return

        try:
            import tracemalloc

            if not tracemalloc.is_tracing():
                tracemalloc.start(25)
            self._last_snapshot = tracemalloc.take_snapshot()
            self._last_snapshot_at = 0.0
        except Exception as e:
            logger.warning(f"[NDI MEM][{self.source_name}] tracemalloc init failed: {e}")
            self.enabled = False
            return

        self._baseline_rss = _get_process_rss_mb()
        self._last_rss = self._baseline_rss
        logger.info(
            f"[NDI MEM][{self.source_name}] enabled interval={self.interval_s}s "
            f"snapshot_interval={self.snapshot_interval_s}s top_n={self.top_n} "
            f"rss_baseline_mb={self._baseline_rss:.1f}"
            if self._baseline_rss is not None
            else f"[NDI MEM][{self.source_name}] enabled interval={self.interval_s}s "
            f"snapshot_interval={self.snapshot_interval_s}s top_n={self.top_n}"
        )

    def tick(self, frame_count: int) -> None:
        if not self.enabled:
            return

        import gc
        import time
        import tracemalloc

        now = time.time()
        if now - self._last_log_at < self.interval_s:
            return
        self._last_log_at = now

        rss_mb = _get_process_rss_mb()
        current, peak = tracemalloc.get_traced_memory()
        py_current_mb = current / (1024 * 1024)
        py_peak_mb = peak / (1024 * 1024)

        delta_rss = 0.0
        if rss_mb is not None and self._last_rss is not None:
            delta_rss = rss_mb - self._last_rss
        baseline_delta = 0.0
        if rss_mb is not None and self._baseline_rss is not None:
            baseline_delta = rss_mb - self._baseline_rss

        gc_counts = gc.get_count()

        wrapper_suffix = ""
        wrapper_total_video_imbalance = None
        wrapper_interval_video_imbalance = None
        try:
            if hasattr(ndi, "debug_get_counters"):
                counters = ndi.debug_get_counters()
                recv_outstanding = int(counters.get("recv_instances_outstanding", 0))
                find_outstanding = int(counters.get("find_instances_outstanding", 0))
                capture_v3_calls = int(counters.get("recv_capture_v3_calls", 0))
                video_captured = int(counters.get("recv_video_frames_captured", 0))
                free_video_calls = int(counters.get("recv_free_video_calls", 0))
                free_audio_v3_calls = int(counters.get("recv_free_audio_v3_calls", 0))
                free_metadata_calls = int(counters.get("recv_free_metadata_calls", 0))

                delta_capture = 0
                delta_video_captured = 0
                delta_free_video = 0
                if self._last_wrapper_counters is not None:
                    delta_capture = (
                        capture_v3_calls
                        - int(self._last_wrapper_counters.get("recv_capture_v3_calls", 0))
                    )
                    delta_video_captured = (
                        video_captured
                        - int(self._last_wrapper_counters.get("recv_video_frames_captured", 0))
                    )
                    delta_free_video = (
                        free_video_calls
                        - int(self._last_wrapper_counters.get("recv_free_video_calls", 0))
                    )

                self._last_wrapper_counters = counters
                wrapper_total_video_imbalance = video_captured - free_video_calls
                wrapper_interval_video_imbalance = delta_video_captured - delta_free_video
                wrapper_suffix = (
                    f" wrapper(recv_out={recv_outstanding} find_out={find_outstanding} "
                    f"cap_v3={capture_v3_calls} cap_vid={video_captured} free_v={free_video_calls} free_a3={free_audio_v3_calls} "
                    f"free_m={free_metadata_calls} d_cap={delta_capture:+d} d_cap_vid={delta_video_captured:+d} "
                    f"d_free_v={delta_free_video:+d} vid_imb={wrapper_total_video_imbalance:+d} "
                    f"d_vid_imb={wrapper_interval_video_imbalance:+d})"
                )
        except Exception:
            wrapper_suffix = " wrapper(debug_counters=error)"

        if (
            wrapper_total_video_imbalance is not None
            and wrapper_interval_video_imbalance is not None
            and abs(wrapper_total_video_imbalance) >= self.wrapper_imbalance_warn_threshold
        ):
            logger.warning(
                "[NDI MEM][%s] wrapper imbalance warning total_video_imbalance=%+d interval_video_imbalance=%+d threshold=%d",
                self.source_name,
                wrapper_total_video_imbalance,
                wrapper_interval_video_imbalance,
                self.wrapper_imbalance_warn_threshold,
            )

        stream_metrics = _stream_metrics_snapshot()

        if rss_mb is not None:
            logger.info(
                "[NDI MEM][%s] frames=%d rss_mb=%.1f delta_mb=%+.1f total_delta_mb=%+.1f "
                "py_mb=%.1f py_peak_mb=%.1f gc=%s streams(active=%d connected=%d failed=%d starts=%d stops=%d)%s",
                self.source_name,
                frame_count,
                rss_mb,
                delta_rss,
                baseline_delta,
                py_current_mb,
                py_peak_mb,
                gc_counts,
                stream_metrics["active_streams"],
                stream_metrics["connected_streams"],
                stream_metrics["failed_streams"],
                stream_metrics["starts"],
                stream_metrics["stops"],
                wrapper_suffix,
            )
            self._last_rss = rss_mb
        else:
            logger.info(
                "[NDI MEM][%s] frames=%d rss_mb=NA py_mb=%.1f py_peak_mb=%.1f gc=%s "
                "streams(active=%d connected=%d failed=%d starts=%d stops=%d)%s",
                self.source_name,
                frame_count,
                py_current_mb,
                py_peak_mb,
                gc_counts,
                stream_metrics["active_streams"],
                stream_metrics["connected_streams"],
                stream_metrics["failed_streams"],
                stream_metrics["starts"],
                stream_metrics["stops"],
                wrapper_suffix,
            )

        if now - self._last_snapshot_at >= self.snapshot_interval_s:
            try:
                snapshot = tracemalloc.take_snapshot()
                if self._last_snapshot is not None:
                    top_stats = snapshot.compare_to(self._last_snapshot, "lineno")
                    for stat in top_stats[: self.top_n]:
                        logger.info("[NDI MEM][%s] alloc %s", self.source_name, stat)
                self._last_snapshot = snapshot
                self._last_snapshot_at = now
            except Exception as e:
                logger.warning(f"[NDI MEM][{self.source_name}] snapshot failed: {e}")

    def finalize(self) -> None:
        if not self.enabled:
            return

        import gc

        before_gc = _get_process_rss_mb()
        gc.collect()
        after_gc = _get_process_rss_mb()

        if before_gc is not None and after_gc is not None:
            logger.info(
                "[NDI MEM][%s] finalize rss_before_gc_mb=%.1f rss_after_gc_mb=%.1f reclaimed_mb=%.1f",
                self.source_name,
                before_gc,
                after_gc,
                before_gc - after_gc,
            )
        else:
            logger.info("[NDI MEM][%s] finalize completed", self.source_name)

try:
    from videocue import ndi_wrapper as ndi  # noqa: N813

    ndi_available = True
except ImportError as e:
    ndi_error_message = (
        "NDI library not available. Please install NDI Runtime:\n\n"
        "Download from: https://ndi.tv/tools/\n\n"
        "The application will continue without NDI video streaming support.\n"
        "You can still control cameras using IP addresses."
    )
    logger.warning(f"NDI Import Error: {e}")
except Exception as e:
    ndi_error_message = (
        f"NDI library error: {e}\n\nPlease install NDI Runtime from https://ndi.tv/tools/"
    )
    logger.warning(f"NDI Error: {e}")


def set_preferred_network_interface(interface_ip: str | None) -> None:
    """
    Set preferred network interface IP for NDI binding.
    Must be called BEFORE any NDI initialization (_ensure_ndi_initialized).

    Args:
        interface_ip: IP address of the network interface to use (e.g., "192.168.1.235")
                     or None to use NDI default behavior (all interfaces)
    """
    global _preferred_network_interface
    # Thread-safe modification of global state
    with _ndi_lock:
        _preferred_network_interface = interface_ip
    if interface_ip:
        logger.info("[NDI Config] Preferred network interface set to: %s", interface_ip)
    else:
        logger.info("[NDI Config] Using NDI default network interface selection")


def _ensure_ndi_initialized() -> bool:
    """Ensure NDI is initialized globally (call once) - thread-safe"""
    global _ndi_initialized, _global_finder
    if not ndi_available:
        return False

    # Use lock to ensure only one thread initializes NDI
    with _ndi_lock:
        if not _ndi_initialized:
            logger.info("[NDI Global] Initializing NDI...")
            try:
                # Use NDI default protocol (TCP) - proven reliable by CamControl
                # Removed RUDP as it may cause connection instability

                if ndi.initialize():
                    _ndi_initialized = True
                    logger.info("[NDI Global] Creating global finder...")
                    find_settings = ndi.FindCreate()
                    find_settings.show_local_sources = True

                    # Apply network interface binding if configured
                    if _preferred_network_interface:
                        find_settings.extra_ips = _preferred_network_interface
                        logger.info(
                            f"[NDI Global] Binding to network interface: {_preferred_network_interface}"
                        )

                    _global_finder = ndi.find_create_v2(find_settings)
                    if _global_finder:
                        logger.info("[NDI Global] NDI initialized successfully")
                    else:
                        logger.error("[NDI Global] Failed to create finder")
                        return False
                else:
                    logger.error("[NDI Global] Failed to initialize NDI")
                    return False
            except (ImportError, RuntimeError, OSError, AttributeError) as e:
                logger.exception(f"[NDI Global] Exception during initialization: {e}")
                return False

        return _ndi_initialized and _global_finder is not None


def clear_source_cache() -> None:
    """Clear the cached NDI sources (useful if sources change on network)"""
    global _source_cache
    with _ndi_lock:
        _source_cache.clear()
        logger.info("[NDI] Source cache cleared")


def cleanup_ndi() -> None:
    """Cleanup NDI resources (call on application shutdown)"""
    global _ndi_initialized, _global_finder, _source_cache
    with _ndi_lock:
        # Clear source cache
        _source_cache.clear()

        if _global_finder:
            try:
                ndi.find_destroy(_global_finder)
                logger.info("[NDI Global] Finder destroyed")
            except Exception as e:
                logger.error(f"[NDI Global] Error destroying finder: {e}")
            finally:
                _global_finder = None

        if _ndi_initialized:
            try:
                ndi.destroy()
                logger.info("[NDI Global] NDI destroyed")
            except Exception as e:
                logger.error(f"[NDI Global] Error destroying NDI: {e}")
            finally:
                _ndi_initialized = False

        # Capture final wrapper counters as proof of cleanup
        try:
            final_counters = ndi.debug_get_counters()
            recv_out = final_counters.get('recv_instances_outstanding', 0)
            find_out = final_counters.get('find_instances_outstanding', 0)
            cap_v3 = final_counters.get('recv_capture_video_frames_total', 0)
            free_v = final_counters.get('recv_free_video_total', 0)
            vid_imb = cap_v3 - free_v
            logger.info(f"[NDI Global] SHUTDOWN PROOF: wrapper(recv_out={recv_out} find_out={find_out} cap_v3={cap_v3} free_v={free_v} vid_imb={vid_imb})")
        except Exception:
            # If counters unavailable, that's fine - NDI may have been destroyed
            pass


class NDIVideoThread(QThread):
    """
    NDI video receiver thread with automatic frame dropping.
    Each thread has its own NDI finder for isolation.
    Uses QueuedConnection with implicit queue size of 1 for frame_ready signal.
    """

    # Signals - Qt automatically marshals these to main thread
    frame_ready = pyqtSignal(QImage)  # Emits latest video frame
    connected = pyqtSignal(str)  # Emits web control URL on first connection
    error = pyqtSignal(str)  # Emits error message
    resolution_changed = pyqtSignal(int, int, float)  # Emits width, height, frame rate

    def __init__(self, source_name: str, frame_skip: int = 6, bandwidth: str = "low", color_format: str = "bgra"):
        super().__init__()
        self.setObjectName(f"NDIVideoThread-{source_name}")
        self.source_name = source_name
        self.frame_skip = (
            frame_skip  # How many frames to skip between displays (higher = faster/lower quality)
        )
        self.bandwidth = bandwidth  # "high" or "low" - NDI receiver bandwidth mode
        self.color_format = color_format  # "bgra", "rgba", or "uyvy" - pixel format mode
        self.running = False
        self._stop_event = threading.Event()
        self._receiver = None
        self._finder = None  # Per-camera finder
        self._finder_created_at = None
        self._metrics_started = False
        self._metrics_connected = False
        self._metrics_failed = False
        self._memory_probe = _NDIMemoryProbe(source_name)
        # Persistent buffers for UYVY conversion (reused across frames)
        self._rgb_buffer = None
        self._rgb_buffer_shape = None
        # Persistent working buffers for UYVY math (avoid per-frame allocations)
        self._uyvy_work_buffers = None  # (y0, y1, u, v, temp1, temp2) float32 arrays
        self._uyvy_work_shape = None
        logger.info(
            f"[{source_name}] NDI thread created with frame_skip={frame_skip}, bandwidth={bandwidth}, color_format={color_format}"
        )

    def run(self) -> None:
        """Main video reception loop with comprehensive error handling"""
        # Wrap EVERYTHING in try-except to prevent thread crashes from killing the app
        _stream_metrics_on_start()
        self._metrics_started = True
        try:
            if not _ensure_ndi_initialized():
                err_msg = "NDI not available or failed to initialize"
                logger.error(f"[NDI] {err_msg}")
                if not self._metrics_failed:
                    _stream_metrics_on_failed()
                    self._metrics_failed = True
                self.error.emit(err_msg)
                return

            self._run_reception_loop()
        except NDINotAvailableError as e:
            logger.error(f"[NDI] NDI not available: {e}")
            self.error.emit(str(e))
        except NDISourceNotFoundError as e:
            logger.warning(f"[NDI] Source not found: {e}")
            self.error.emit(str(e))
        except Exception as e:
            # Catch ANY unhandled exception to prevent app crash
            error_msg = f"Video thread crashed: {str(e)}"
            logger.exception(f"[NDI] CRITICAL: {error_msg}")
            self.error.emit(error_msg)
        finally:
            # Always clean up, even if something catastrophic happened
            try:
                self._cleanup()
            except Exception as cleanup_error:
                logger.error(f"[NDI] Error during cleanup: {cleanup_error}")

    def _run_reception_loop(self):
        """Internal reception loop (called by run() with error handling)"""
        import gc
        import time

        def _build_manual_source():
            source = ndi.Source()
            source.ndi_name = (
                self.source_name.encode("utf-8")
                if isinstance(self.source_name, str)
                else self.source_name
            )
            return source

        def _create_receiver_instance():
            receiver_start = time.time()
            try:
                recv_settings = ndi.RecvCreateV3()
                # Select color format based on configuration
                if self.color_format == "uyvy":
                    recv_settings.color_format = ndi.RECV_COLOR_FORMAT_FASTEST
                    format_label = "UYVY"
                elif self.color_format == "rgba":
                    recv_settings.color_format = ndi.RECV_COLOR_FORMAT_RGBX_RGBA
                    format_label = "RGBA"
                else:  # default to BGRA (matches Qt's native ARGB32 on little-endian Windows)
                    recv_settings.color_format = ndi.RECV_COLOR_FORMAT_BGRX_BGRA
                    format_label = "BGRA"
                if self.bandwidth == "high":
                    recv_settings.bandwidth = ndi.RECV_BANDWIDTH_HIGHEST
                    bandwidth_label = "HIGHEST"
                else:
                    recv_settings.bandwidth = ndi.RECV_BANDWIDTH_LOWEST
                    bandwidth_label = "LOWEST"
                recv_settings.allow_video_fields = True
                receiver = ndi.recv_create_v3(recv_settings)
                receiver_elapsed = (time.time() - receiver_start) * 1000
                logger.info(
                    f"[{self.source_name}] ✓ Receiver created in {receiver_elapsed:.1f}ms ({bandwidth_label} bandwidth, {format_label} format, frame_skip={self.frame_skip})"
                )
                return receiver
            except (AttributeError, TypeError) as e:
                logger.warning(
                    f"[{self.source_name}] RecvCreateV3 failed: {e}, using defaults"
                )
                receiver = ndi.recv_create_v3()
                receiver_elapsed = (time.time() - receiver_start) * 1000
                logger.info(
                    f"[{self.source_name}] Receiver created in {receiver_elapsed:.1f}ms (defaults)"
                )
                return receiver

        def _resolve_fresh_source_for_reconnect():
            try:
                with _ndi_lock:
                    ndi.find_wait_for_sources(
                        _global_finder, NetworkConstants.NDI_DISCOVERY_QUICK_TIMEOUT_MS
                    )
                    sources = ndi.find_get_current_sources(_global_finder)
                for source in sources:
                    source_name = (
                        source.ndi_name.decode("utf-8")
                        if isinstance(source.ndi_name, bytes)
                        else str(source.ndi_name)
                    )
                    if source_name == self.source_name:
                        return _build_manual_source(), "global-finder-refresh-manual-handle"
            except Exception as reconnect_lookup_error:
                logger.warning(
                    f"[{self.source_name}] Global finder refresh failed: {reconnect_lookup_error}"
                )

            if self._finder:
                try:
                    ndi.find_wait_for_sources(
                        self._finder, NetworkConstants.NDI_DISCOVERY_QUICK_TIMEOUT_MS
                    )
                    sources = ndi.find_get_current_sources(self._finder)
                    for source in sources:
                        source_name = (
                            source.ndi_name.decode("utf-8")
                            if isinstance(source.ndi_name, bytes)
                            else str(source.ndi_name)
                        )
                        if source_name == self.source_name:
                            return (
                                _build_manual_source(),
                                "per-camera-finder-refresh-manual-handle",
                            )
                except Exception as per_finder_error:
                    logger.warning(
                        f"[{self.source_name}] Per-camera finder refresh failed: {per_finder_error}"
                    )

            return _build_manual_source(), "manual-refresh"

        def _quick_probe_source_frames(timeout_ms: int = 1500) -> int:
            probe_receiver = None
            frames = 0
            try:
                probe_receiver = _create_receiver_instance()
                if not probe_receiver:
                    return 0

                probe_source, probe_method = _resolve_fresh_source_for_reconnect()
                ndi.recv_connect(probe_receiver, probe_source)
                deadline = time.time() + max(0.2, timeout_ms / 1000.0)

                while time.time() < deadline:
                    t, v, _a, _m = ndi.recv_capture_v3(
                        probe_receiver, NetworkConstants.NDI_FRAME_TIMEOUT_MS
                    )
                    if t == ndi.FRAME_TYPE_VIDEO:
                        frames += 1
                        ndi.recv_free_video_v2(probe_receiver, v)
                    elif t == ndi.FRAME_TYPE_AUDIO:
                        # CRITICAL: Free audio frames to prevent memory leaks
                        with contextlib.suppress(Exception):
                            ndi.recv_free_audio_v3(probe_receiver, _a)
                    elif t == ndi.FRAME_TYPE_METADATA:
                        # CRITICAL: Free metadata frames to prevent memory leaks
                        with contextlib.suppress(Exception):
                            ndi.recv_free_metadata(probe_receiver, _m)
                    elif t == ndi.FRAME_TYPE_ERROR:
                        break

                logger.info(
                    f"[{self.source_name}] Quick probe via {probe_method}: video_frames={frames}"
                )
                return frames
            except Exception as probe_error:
                logger.warning(
                    f"[{self.source_name}] Quick probe failed: {probe_error}",
                    exc_info=True,
                )
                return 0
            finally:
                if probe_receiver:
                    try:
                        ndi.recv_destroy(probe_receiver)
                    except Exception:
                        logger.debug(
                            f"[{self.source_name}] Probe receiver destroy raised exception",
                            exc_info=True,
                        )

        start_time = time.time()

        try:
            logger.info(f"[{self.source_name}] === CONNECTION START ===")
            logger.info(
                f"[{self.source_name}] Strategy: discovered source first (cache/global finder), manual fallback"
            )

            target_source = None
            source_creation_method = "unknown"

            # METHOD 1: Cache hint only (do NOT use cached source object directly)
            # Cached ndi.Source instances can become stale across thread/native lifetimes.
            # Use cache only as a hint, then resolve a fresh source handle via finder.
            try:
                with _ndi_lock:
                    cache_hit = self.source_name in _source_cache
                if cache_hit:
                    logger.info(
                        f"[{self.source_name}] Cache hint present; resolving fresh source via global finder"
                    )
            except Exception as e:
                logger.warning(f"[{self.source_name}] Failed to use global cache: {e}")

            # METHOD 2: Refresh global finder and match source by name
            try:
                logger.info(f"[{self.source_name}] Querying global finder for source...")
                with _ndi_lock:
                    ndi.find_wait_for_sources(
                        _global_finder, NetworkConstants.NDI_DISCOVERY_QUICK_TIMEOUT_MS
                    )
                    sources = ndi.find_get_current_sources(_global_finder)

                    for source in sources:
                        source_name = (
                            source.ndi_name.decode("utf-8")
                            if isinstance(source.ndi_name, bytes)
                            else str(source.ndi_name)
                        )
                        if source_name == self.source_name:
                            target_source = source
                            _source_cache[self.source_name] = source
                            source_creation_method = "global-finder"
                            logger.info(
                                f"[{self.source_name}] ✓ Matched source via global finder"
                            )
                            break
            except Exception as e:
                logger.warning(f"[{self.source_name}] Global finder lookup failed: {e}")

            # METHOD 3: Per-camera finder with discovery (if cache/global finder miss)
            if not target_source:
                logger.warning(f"[{self.source_name}] Source not in cache/global finder, trying per-camera finder...")
                try:
                    # Create dedicated finder for this camera
                    logger.info(f"[{self.source_name}] Creating dedicated NDI finder...")
                    finder_start = time.time()
                    find_settings = ndi.FindCreate()
                    find_settings.show_local_sources = True

                    # Apply network interface binding if configured
                    if _preferred_network_interface:
                        find_settings.extra_ips = _preferred_network_interface
                        logger.info(
                            f"[{self.source_name}] Binding to network interface: {_preferred_network_interface}"
                        )

                    self._finder = ndi.find_create_v2(find_settings)
                    self._finder_created_at = time.time()
                    finder_elapsed = (time.time() - finder_start) * 1000
                    logger.info(f"[{self.source_name}] ✓ Finder created in {finder_elapsed:.1f}ms")

                    # Quick discovery with per-camera finder
                    logger.info(
                        f"[{self.source_name}] Discovering sources (quick: 1500ms timeout)..."
                    )
                    discover_start = time.time()
                    ndi.find_wait_for_sources(
                        self._finder, NetworkConstants.NDI_DISCOVERY_QUICK_TIMEOUT_MS
                    )
                    sources = ndi.find_get_current_sources(self._finder)
                    discover_elapsed = (time.time() - discover_start) * 1000
                    logger.info(
                        f"[{self.source_name}] Found {len(sources)} sources in {discover_elapsed:.1f}ms"
                    )

                    for source in sources:
                        source_name = (
                            source.ndi_name.decode("utf-8")
                            if isinstance(source.ndi_name, bytes)
                            else str(source.ndi_name)
                        )
                        logger.debug(f"[{self.source_name}]   - Discovered: {source_name}")
                        if source_name == self.source_name:
                            target_source = source
                            logger.info(f"[{self.source_name}] ✓ Matched source via discovery")
                            source_creation_method = "per-camera-finder"
                            break

                except Exception as e:
                    logger.error(f"[{self.source_name}] ✗ Per-camera finder failed: {e}")

            # METHOD 4: Manual source creation fallback (least reliable)
            if not target_source:
                try:
                    logger.warning(
                        f"[{self.source_name}] Falling back to manual source creation by name"
                    )
                    manual_start = time.time()
                    target_source = ndi.Source()
                    target_source.ndi_name = (
                        self.source_name.encode("utf-8")
                        if isinstance(self.source_name, str)
                        else self.source_name
                    )
                    manual_elapsed = (time.time() - manual_start) * 1000
                    logger.info(
                        f"[{self.source_name}] ✓ Manual source created in {manual_elapsed:.1f}ms"
                    )
                    source_creation_method = "manual"
                except (ImportError, RuntimeError, AttributeError) as e:
                    logger.error(f"[{self.source_name}] ✗ Manual source creation failed: {e}")

            # Final check
            if not target_source:
                elapsed = (time.time() - start_time) * 1000
                logger.error(
                    f"[{self.source_name}] ✗ FAILED after {elapsed:.1f}ms - no source obtained"
                )
                self.error.emit(f"NDI source '{self.source_name}' not found")
                return

            # IMPORTANT: Always connect with a fresh manual source handle by name.
            # Finder-provided source objects can be stale across thread/native boundaries.
            # Finder is used for discovery/validation only.
            target_source = _build_manual_source()
            source_creation_method = f"{source_creation_method}-manual-handle"

            logger.info(f"[{self.source_name}] Source obtained via: {source_creation_method}")

            # Create receiver with SDK-compliant settings
            # SDK BEST PRACTICES (from official NDI documentation):
            # - RECV_COLOR_FORMAT_FASTEST: Best performance, no conversion overhead
            # - RECV_BANDWIDTH_HIGHEST: Maximum quality, higher bandwidth usage
            # - RECV_BANDWIDTH_LOWEST: Lower bandwidth, more compression
            # - allow_video_fields=True: Required for FASTEST mode
            logger.info(f"[{self.source_name}] Creating NDI receiver...")
            self._receiver = _create_receiver_instance()

            if not self._receiver:
                self.error.emit("Failed to create NDI receiver")
                return

            # Connect to source
            logger.info(f"[{self.source_name}] Calling recv_connect()...")
            connect_start = time.time()
            ndi.recv_connect(self._receiver, target_source)
            connect_elapsed = (time.time() - connect_start) * 1000
            logger.info(
                f"[{self.source_name}] ✓ recv_connect() returned in {connect_elapsed:.1f}ms"
            )

            # Reception loop
            self.running = True
            first_frame = True
            frame_count = 0
            skip_count = 0
            no_frame_count = 0
            max_no_frame_attempts = (
                NetworkConstants.NDI_NO_FRAME_THRESHOLD
            )  # Use constant (10 seconds)
            recovery_threshold = max(20, max_no_frame_attempts // 3)
            current_resolution = None  # Track resolution to detect changes
            first_frame_time = None
            attempted_manual_reconnect = False
            attempted_receiver_recreate = False
            attempted_probe_recovery = False

            total_elapsed = (time.time() - start_time) * 1000
            logger.info(
                f"[{self.source_name}] Starting frame reception loop (setup took {total_elapsed:.1f}ms)..."
            )
            logger.info(f"[{self.source_name}] Waiting for first frame (10s timeout)...")
            logger.info(
                f"[{self.source_name}] Recovery threshold set to {recovery_threshold} no-frame polls"
            )

            try:
                while self.running:
                    try:
                        # SDK RECOMMENDATION: Use recv_capture_v3 to match recv_create_v3
                        # v3 is thread-safe and provides better audio frame handling
                        # Use 100ms timeout (SDK: reasonable timeout better than zero-timeout polling)
                        t, v, _a, _m = ndi.recv_capture_v3(self._receiver, 100)

                        if t == ndi.FRAME_TYPE_VIDEO:
                            frame_count += 1
                            self._memory_probe.tick(frame_count)
                            no_frame_count = 0  # Reset timeout counter on successful frame

                            # Extract web control URL on first frame
                            if first_frame:
                                if not first_frame_time:
                                    first_frame_time = time.time()
                                    first_frame_elapsed = (first_frame_time - start_time) * 1000
                                    logger.info(
                                        f"[{self.source_name}] ✓✓✓ FIRST FRAME received after {first_frame_elapsed:.1f}ms ✓✓✓"
                                    )
                                    logger.info(
                                        f"[{self.source_name}] Resolution: {v.xres}x{v.yres}"
                                    )
                                    logger.info(f"[{self.source_name}] === CONNECTION SUCCESS ===")
                                    if not self._metrics_connected:
                                        _stream_metrics_on_connected()
                                        self._metrics_connected = True
                                web_url = self._extract_web_control()  # pylint: disable=assignment-from-none
                                if web_url:
                                    self.connected.emit(web_url)
                                first_frame = False

                            # Emit resolution info if changed
                            resolution = (
                                v.xres,
                                v.yres,
                                v.frame_rate_N / v.frame_rate_D if v.frame_rate_D > 0 else 0.0,
                            )
                            if resolution != current_resolution:
                                self.resolution_changed.emit(v.xres, v.yres, resolution[2])
                                current_resolution = resolution

                            # Skip frames based on preference (higher skip = lower quality/CPU but faster)
                            skip_count += 1
                            if skip_count % (self.frame_skip + 1) == 0:
                                # Convert frame to QImage
                                qimage = self._convert_frame(v)
                                if qimage:
                                    # Emit signal - Qt will drop old frames if UI hasn't processed them
                                    self.frame_ready.emit(qimage)

                                    # Log every 100 processed frames to verify performance
                                    if frame_count % 100 == 0:
                                        logger.debug(
                                            f"[NDI] {self.source_name}: Processed {frame_count} frames, displayed ~{frame_count // (self.frame_skip + 1)} (skip={self.frame_skip})"
                                        )

                                    # MEMORY OPTIMIZATION: frequent incremental GC to limit young-object buildup
                                    # (conversion path creates many temporary arrays/bytes)
                                    if frame_count % 30 == 0:
                                        gc.collect(generation=0)

                                    # Full GC more frequently to reduce long-run RSS drift
                                    if frame_count % 300 == 0:
                                        gc.collect()
                                        logger.debug(
                                            f"[NDI] {self.source_name}: Full GC at {frame_count} frames"
                                        )

                                # Explicitly delete QImage to help memory cleanup
                                del qimage

                                # Reset skip counter to prevent overflow
                                skip_count = 0

                            # Free the video frame
                            ndi.recv_free_video_v2(self._receiver, v)

                        elif t == ndi.FRAME_TYPE_AUDIO:
                            # CRITICAL: Audio frames MUST be freed to prevent memory leaks
                            with contextlib.suppress(Exception):
                                ndi.recv_free_audio_v3(self._receiver, _a)

                        elif t == ndi.FRAME_TYPE_METADATA:
                            # CRITICAL: Metadata frames MUST be freed to prevent memory leaks
                            with contextlib.suppress(Exception):
                                ndi.recv_free_metadata(self._receiver, _m)

                        elif t == ndi.FRAME_TYPE_NONE:
                            # No data received, increment timeout counter
                            no_frame_count += 1
                            if no_frame_count >= recovery_threshold:
                                # Recovery path: if initial source came from finder/cache and produced no frames,
                                # retry connection once using manual source object by name.
                                if (
                                    not attempted_manual_reconnect
                                    and source_creation_method != "manual"
                                    and self._receiver
                                ):
                                    logger.warning(
                                        f"[{self.source_name}] No frames via {source_creation_method}; retrying with manual source fallback"
                                    )
                                    try:
                                        manual_source = _build_manual_source()
                                        ndi.recv_connect(self._receiver, manual_source)
                                        source_creation_method = "manual-reconnect"
                                        attempted_manual_reconnect = True
                                        no_frame_count = 0
                                        first_frame = True
                                        logger.info(
                                            f"[{self.source_name}] Manual reconnect applied; waiting for frames again"
                                        )
                                        continue
                                    except Exception as reconnect_error:
                                        logger.error(
                                            f"[{self.source_name}] Manual reconnect failed: {reconnect_error}",
                                            exc_info=True,
                                        )

                                if (
                                    not attempted_receiver_recreate
                                    and self._receiver
                                ):
                                    logger.warning(
                                        f"[{self.source_name}] No frames persisted; recreating receiver and reconnecting with refreshed source"
                                    )
                                    attempted_receiver_recreate = True
                                    try:
                                        try:
                                            ndi.recv_destroy(self._receiver)
                                        except Exception:
                                            logger.debug(
                                                f"[{self.source_name}] Receiver destroy during recovery raised exception",
                                                exc_info=True,
                                            )
                                        finally:
                                            self._receiver = None

                                        self._receiver = _create_receiver_instance()
                                        if not self._receiver:
                                            raise RuntimeError("Receiver recreation failed")

                                        reconnect_source, reconnect_method = (
                                            _resolve_fresh_source_for_reconnect()
                                        )
                                        ndi.recv_connect(self._receiver, reconnect_source)
                                        source_creation_method = f"receiver-recreate-{reconnect_method}"
                                        no_frame_count = 0
                                        first_frame = True
                                        logger.info(
                                            f"[{self.source_name}] Receiver recreation reconnect via {reconnect_method} applied; waiting for frames again"
                                        )
                                        continue
                                    except Exception as recreate_error:
                                        logger.error(
                                            f"[{self.source_name}] Receiver recreation reconnect failed: {recreate_error}",
                                            exc_info=True,
                                        )

                                if (
                                    not attempted_probe_recovery
                                    and self._receiver
                                ):
                                    attempted_probe_recovery = True
                                    logger.warning(
                                        f"[{self.source_name}] No frames persisted after reconnect attempts; running quick probe recovery"
                                    )
                                    probe_frames = _quick_probe_source_frames(timeout_ms=1500)
                                    if probe_frames > 0:
                                        try:
                                            try:
                                                ndi.recv_destroy(self._receiver)
                                            except Exception:
                                                logger.debug(
                                                    f"[{self.source_name}] Receiver destroy during probe recovery raised exception",
                                                    exc_info=True,
                                                )
                                            finally:
                                                self._receiver = None

                                            self._receiver = _create_receiver_instance()
                                            if not self._receiver:
                                                raise RuntimeError(
                                                    "Receiver creation failed during probe recovery"
                                                )

                                            reconnect_source, reconnect_method = (
                                                _resolve_fresh_source_for_reconnect()
                                            )
                                            ndi.recv_connect(self._receiver, reconnect_source)
                                            source_creation_method = (
                                                f"probe-recovery-{reconnect_method}"
                                            )
                                            no_frame_count = 0
                                            first_frame = True
                                            logger.info(
                                                f"[{self.source_name}] Probe recovery reconnect via {reconnect_method} applied; waiting for frames again"
                                            )
                                            continue
                                        except Exception as probe_reconnect_error:
                                            logger.error(
                                                f"[{self.source_name}] Probe recovery reconnect failed: {probe_reconnect_error}",
                                                exc_info=True,
                                            )
                                    else:
                                        logger.warning(
                                            f"[{self.source_name}] Quick probe observed 0 frames; proceeding to failure"
                                        )

                                if (
                                    attempted_manual_reconnect
                                    and attempted_receiver_recreate
                                    and attempted_probe_recovery
                                ):
                                    elapsed_total = (time.time() - start_time) * 1000
                                    timeout_seconds = (
                                        no_frame_count * NetworkConstants.NDI_FRAME_TIMEOUT_MS
                                    ) // 1000
                                    logger.error(
                                        f"[{self.source_name}] ✗✗✗ NO FRAMES after staged recovery attempts ({timeout_seconds}s since last frame) ✗✗✗"
                                    )
                                    logger.error(
                                        f"[{self.source_name}] Total time: {elapsed_total:.1f}ms"
                                    )
                                    logger.error(
                                        f"[{self.source_name}] Source method: {source_creation_method}"
                                    )
                                    logger.error(
                                        f"[{self.source_name}] recv_connect() succeeded but no video data received"
                                    )
                                    logger.error(
                                        f"[{self.source_name}] === CONNECTION FAILED ==="
                                    )
                                    if not self._metrics_failed:
                                        _stream_metrics_on_failed()
                                        self._metrics_failed = True
                                    self.error.emit(
                                        f"NDI source '{self.source_name}' not responding after staged reconnect attempts. "
                                        "Check source name and network connectivity. Try reconnecting."
                                    )
                                    break
                        elif t == ndi.FRAME_TYPE_ERROR:
                            logger.debug("Received error frame type")
                            if not self._metrics_failed:
                                _stream_metrics_on_failed()
                                self._metrics_failed = True
                            self.error.emit(f"NDI error receiving from '{self.source_name}'")
                            break

                    except KeyboardInterrupt:
                        logger.debug("Interrupted")
                        break
                    except (ImportError, RuntimeError, OSError, AttributeError) as e:
                        logger.error(f"Error in reception loop: {e}", exc_info=True)
                        if not self._metrics_failed:
                            _stream_metrics_on_failed()
                            self._metrics_failed = True
                        self.error.emit(f"NDI error: {str(e)}")
                        break
                    except Exception as e:
                        # Catch ANY other exception in the frame processing
                        logger.error(f"Unexpected error processing frame: {e}", exc_info=True)
                        if not self._metrics_failed:
                            _stream_metrics_on_failed()
                            self._metrics_failed = True
                        self.error.emit(f"NDI unexpected error: {str(e)}")
                        break
            except Exception as e:
                logger.critical(f"Fatal error in reception loop: {e}", exc_info=True)
                if not self._metrics_failed:
                    _stream_metrics_on_failed()
                    self._metrics_failed = True
                self.error.emit(f"NDI fatal error: {str(e)}")
        except Exception as e:
            # Outer catch for the entire reception setup
            logger.critical(f"Fatal error during source setup: {e}", exc_info=True)
            if not self._metrics_failed:
                _stream_metrics_on_failed()
                self._metrics_failed = True
            self.error.emit(f"NDI setup error: {str(e)}")

    def stop(self, timeout: float = None) -> bool:
        """
        Stop video reception with proper synchronization.

        Args:
            timeout: Not used (kept for API compatibility)

        Returns:
            Always returns True (thread stops asynchronously)
        """
        if timeout is None:
            timeout = NetworkConstants.NDI_THREAD_STOP_TIMEOUT_S
        logger.debug(f"Stopping NDI thread for {self.source_name}")
        self.running = False
        self._stop_event.set()

        # DON'T call self.wait() here - it blocks the main thread!
        # Thread will stop asynchronously, caller should check isRunning() if needed
        return True

    def _extract_web_control(self) -> str | None:
        """Extract web control URL from NDI receiver metadata"""
        if not self._receiver:
            return None

        try:
            # Get web control URL from NDI receiver
            # This returns a URL like "http://192.168.1.100/" or similar
            web_url = ndi.recv_get_web_control(self._receiver)

            if web_url:
                # Decode if bytes
                if isinstance(web_url, bytes):
                    web_url = web_url.decode("utf-8")

                logger.info(f"Web control URL: {web_url}")
                return web_url

            return None
        except (ImportError, RuntimeError, AttributeError, KeyError) as e:
            logger.warning(f"Failed to get web control URL: {e}")
            return None

    def _convert_frame(self, video_frame) -> QImage | None:
        """Convert NDI video frame to QImage with minimal allocations"""
        try:
            # Get frame data
            width = video_frame.xres
            height = video_frame.yres
            line_stride = video_frame.line_stride_in_bytes

            # Native BGRA path - matches Qt's ARGB32 on little-endian Windows
            if video_frame.FourCC == ndi.FOURCC_VIDEO_TYPE_BGRA:
                # Get frame data as bytes - handle different data types
                if hasattr(video_frame.data, "tobytes"):
                    frame_data = video_frame.data.tobytes()
                elif hasattr(video_frame.data, "__array__"):
                    import numpy as np
                    frame_data = bytes(np.array(video_frame.data).flatten())
                else:
                    frame_data = bytes(video_frame.data)

                expected_size = line_stride * height
                if len(frame_data) < expected_size:
                    logger.debug(f"Frame data too small: {len(frame_data)} < {expected_size}")
                    return None

                # BGRA matches ARGB32 on little-endian (B,G,R,A byte order)
                qimage = QImage(frame_data, width, height, line_stride, QImage.Format.Format_ARGB32)
                result = qimage.copy()  # Own the data
                del frame_data
                del qimage
                return result

            # Fallback: RGBA path
            if video_frame.FourCC == ndi.FOURCC_VIDEO_TYPE_RGBA:
                if hasattr(video_frame.data, "tobytes"):
                    frame_data = video_frame.data.tobytes()
                elif hasattr(video_frame.data, "__array__"):
                    import numpy as np
                    frame_data = bytes(np.array(video_frame.data).flatten())
                else:
                    frame_data = bytes(video_frame.data)

                expected_size = line_stride * height
                if len(frame_data) < expected_size:
                    logger.debug(f"Frame data too small: {len(frame_data)} < {expected_size}")
                    return None

                qimage = QImage(frame_data, width, height, line_stride, QImage.Format.Format_RGBA8888)
                result = qimage.copy()
                del frame_data
                del qimage
                return result

            # Fallback: UYVY path (legacy)
            if video_frame.FourCC == ndi.FOURCC_VIDEO_TYPE_UYVY:
                # Get frame data as bytes - handle different data types
                if hasattr(video_frame.data, "tobytes"):
                    frame_data = video_frame.data.tobytes()
                elif hasattr(video_frame.data, "__array__"):
                    import numpy as np
                    frame_data = bytes(np.array(video_frame.data).flatten())
                else:
                    frame_data = bytes(video_frame.data)

                expected_size = line_stride * height
                if len(frame_data) < expected_size:
                    logger.debug(f"Frame data too small: {len(frame_data)} < {expected_size}")
                    return None

                # Convert UYVY to RGB
                rgb_data = self._uyvy_to_rgb(frame_data, width, height, line_stride)
                if not rgb_data:
                    logger.debug("RGB conversion returned empty data")
                    return None

                qimage = QImage(rgb_data, width, height, width * 3, QImage.Format.Format_RGB888)
                result = qimage.copy()
                del rgb_data
                del frame_data
                del qimage
                return result

            # Unsupported format
            logger.debug(
                f"Unsupported video format: {video_frame.FourCC} (expected RGBA or UYVY)"
            )
            return None

        except (ValueError, TypeError, MemoryError, AttributeError):
            import traceback

            logger.exception("Frame conversion error")
            traceback.print_exc()
            return None
        except Exception:
            # Catch ANY other exception to prevent thread crash
            import traceback

            logger.exception("Unexpected error during frame conversion")
            traceback.print_exc()
            return None

    def _uyvy_to_rgb(self, uyvy_data: bytes, width: int, height: int, line_stride: int) -> bytes:
        """
        Convert UYVY422 to RGB888 using NumPy with minimal allocations.
        Each UYVY macropixel (4 bytes) encodes 2 pixels: U Y0 V Y1

        Memory optimization: All buffers are persistent and reused across frames.
        Uses in-place operations to avoid temporary array allocations.
        """
        try:
            import numpy as np

            # View input as numpy array (no copy)
            frame = np.frombuffer(uyvy_data, dtype=np.uint8)

            # Handle line stride
            if line_stride != width * 2:
                frame = frame.reshape(height, line_stride)[:, : width * 2].ravel()

            # Reshape to UYVY macropixels: [height, width//2, 4]
            uyvy = frame.reshape(height, width // 2, 4)

            # Reuse persistent RGB output buffer
            target_shape = (height, width, 3)
            if self._rgb_buffer is None or self._rgb_buffer_shape != target_shape:
                self._rgb_buffer = np.empty(target_shape, dtype=np.uint8)
                self._rgb_buffer_shape = target_shape
            rgb = self._rgb_buffer

            # Reuse persistent working buffers for intermediate calculations
            work_shape = (height, width // 2)
            if self._uyvy_work_buffers is None or self._uyvy_work_shape != work_shape:
                # Allocate all working arrays once
                self._uyvy_work_buffers = {
                    'y0': np.empty(work_shape, dtype=np.float32),
                    'y1': np.empty(work_shape, dtype=np.float32),
                    'u': np.empty(work_shape, dtype=np.float32),
                    'v': np.empty(work_shape, dtype=np.float32),
                    'temp': np.empty(work_shape, dtype=np.float32),
                }
                self._uyvy_work_shape = work_shape

            y0 = self._uyvy_work_buffers['y0']
            y1 = self._uyvy_work_buffers['y1']
            u = self._uyvy_work_buffers['u']
            v = self._uyvy_work_buffers['v']
            temp = self._uyvy_work_buffers['temp']

            # Extract channels into persistent buffers (in-place where possible)
            np.copyto(y0, uyvy[:, :, 1])
            np.copyto(y1, uyvy[:, :, 3])
            np.copyto(u, uyvy[:, :, 0])
            np.subtract(u, 128.0, out=u)
            np.copyto(v, uyvy[:, :, 2])
            np.subtract(v, 128.0, out=v)

            # ITU-R BT.601 conversion using in-place operations
            # R = Y + 1.402*V
            # G = Y - 0.344*U - 0.714*V
            # B = Y + 1.772*U

            # Pixel 0 (even columns) - R channel
            np.multiply(v, 1.402, out=temp)
            np.add(y0, temp, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 0::2, 0] = temp.astype(np.uint8)

            # Pixel 0 - G channel: y0 - 0.344*u - 0.714*v
            np.multiply(u, 0.344, out=temp)
            np.subtract(y0, temp, out=temp)
            np.multiply(v, 0.714, out=u)  # Reuse u as temp2 (we're done with u after this)
            np.subtract(temp, u, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 0::2, 1] = temp.astype(np.uint8)

            # Restore u for remaining calculations
            np.copyto(u, uyvy[:, :, 0])
            np.subtract(u, 128.0, out=u)

            # Pixel 0 - B channel: y0 + 1.772*u
            np.multiply(u, 1.772, out=temp)
            np.add(y0, temp, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 0::2, 2] = temp.astype(np.uint8)

            # Pixel 1 (odd columns) - R channel
            np.multiply(v, 1.402, out=temp)
            np.add(y1, temp, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 1::2, 0] = temp.astype(np.uint8)

            # Pixel 1 - G channel: y1 - 0.344*u - 0.714*v
            np.multiply(u, 0.344, out=temp)
            np.subtract(y1, temp, out=temp)
            np.multiply(v, 0.714, out=u)  # Reuse u as temp2
            np.subtract(temp, u, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 1::2, 1] = temp.astype(np.uint8)

            # Restore u for B channel
            np.copyto(u, uyvy[:, :, 0])
            np.subtract(u, 128.0, out=u)

            # Pixel 1 - B channel: y1 + 1.772*u
            np.multiply(u, 1.772, out=temp)
            np.add(y1, temp, out=temp)
            np.clip(temp, 0, 255, out=temp)
            rgb[:, 1::2, 2] = temp.astype(np.uint8)

            # Return copy of buffer data
            return rgb.tobytes()

        except ImportError:
            # Fallback to simpler conversion if NumPy not available (shouldn't happen)
            logger.warning("NumPy not available, using slow fallback")
            return self._uyvy_to_rgb_slow(uyvy_data, width, height, line_stride)
        except (ValueError, AttributeError, TypeError):
            logger.exception("NumPy conversion error")
            return self._uyvy_to_rgb_slow(uyvy_data, width, height, line_stride)

    def _uyvy_to_rgb_slow(
        self, uyvy_data: bytes, width: int, height: int, line_stride: int
    ) -> bytes:
        """Slow fallback UYVY conversion (avoid using this)"""
        rgb = bytearray(width * height * 3)

        for y in range(height):
            line_offset = y * line_stride
            for x in range(0, width, 2):
                pixel_offset = line_offset + (x * 2)
                if pixel_offset + 3 >= len(uyvy_data):
                    break

                u = int(uyvy_data[pixel_offset]) - 128
                y0 = int(uyvy_data[pixel_offset + 1])
                v = int(uyvy_data[pixel_offset + 2]) - 128
                y1 = int(uyvy_data[pixel_offset + 3])

                # Simple YUV->RGB
                r0 = max(0, min(255, int(y0 + 1.402 * v)))
                g0 = max(0, min(255, int(y0 - 0.344 * u - 0.714 * v)))
                b0 = max(0, min(255, int(y0 + 1.772 * u)))

                rgb_offset = (y * width + x) * 3
                rgb[rgb_offset : rgb_offset + 3] = [r0, g0, b0]

                if x + 1 < width:
                    r1 = max(0, min(255, int(y1 + 1.402 * v)))
                    g1 = max(0, min(255, int(y1 - 0.344 * u - 0.714 * v)))
                    b1 = max(0, min(255, int(y1 + 1.772 * u)))
                    rgb_offset = (y * width + x + 1) * 3
                    rgb[rgb_offset : rgb_offset + 3] = [r1, g1, b1]

        return bytes(rgb)

    def _cleanup(self):
        """Clean up NDI resources - never throws exceptions"""
        try:
            if self._receiver:
                try:
                    logger.debug(f"[{self.source_name}] Destroying receiver...")
                    ndi.recv_destroy(self._receiver)
                except Exception:
                    logger.exception(f"[{self.source_name}] Error destroying receiver")
                finally:
                    self._receiver = None

            # Destroy per-camera finder
            if self._finder:
                try:
                    logger.debug(f"[{self.source_name}] Destroying per-camera finder...")
                    ndi.find_destroy(self._finder)
                except Exception:
                    logger.exception(f"[{self.source_name}] Error destroying finder")
                finally:
                    self._finder = None

            # Don't call ndi.destroy() - keep NDI initialized globally
            self._memory_probe.finalize()
            if self._metrics_started:
                _stream_metrics_on_stop(self._metrics_connected)
                self._metrics_started = False

            # Release persistent UYVY conversion buffer
            self._rgb_buffer = None
            self._rgb_buffer_shape = None
            self._uyvy_work_buffers = None
            self._uyvy_work_shape = None
        except Exception:
            # Catch ANY exception during cleanup
            logger.exception(f"[{self.source_name}] Unexpected error during cleanup")


def discover_and_cache_all_sources(timeout_ms: int = None, expected_count: int = 0) -> int:
    """
    Discover all NDI sources once and cache them for immediate use by camera threads.
    Polls repeatedly until expected_count sources found or timeout reached.
    This should be called once at app startup before creating camera widgets.
    Returns the number of sources found and cached.

    Args:
        timeout_ms: Total timeout in milliseconds
        expected_count: Number of sources expected (will poll until found or timeout)
    """
    global _source_cache, _last_discovery_time
    import time

    if not _ensure_ndi_initialized():
        logger.warning("[NDI] Cannot discover sources - NDI not initialized")
        return 0

    # Use default discovery timeout if not specified
    if timeout_ms is None:
        timeout_ms = NetworkConstants.NDI_DISCOVERY_TIMEOUT_MS

    try:
        with _ndi_lock:
            if expected_count > 0:
                logger.info(
                    f"[NDI] Polling for {expected_count} sources (timeout: {timeout_ms}ms)..."
                )
            else:
                logger.info(f"[NDI] Discovering all sources (timeout: {timeout_ms}ms)...")

            start_time = time.time()
            poll_interval_ms = 200  # Poll every 200ms

            while True:
                # Poll for sources
                ndi.find_wait_for_sources(_global_finder, poll_interval_ms)
                sources = ndi.find_get_current_sources(_global_finder)

                # Cache discovered sources
                for source in sources:
                    try:
                        source_name = (
                            source.ndi_name.decode("utf-8")
                            if isinstance(source.ndi_name, bytes)
                            else str(source.ndi_name)
                        )
                        if source_name not in _source_cache:
                            _source_cache[source_name] = source
                            logger.info(f"[NDI Discovery] ✓ Cached source: '{source_name}'")
                    except Exception as e:
                        logger.warning(f"[NDI] Error caching source: {e}")

                # Check if we found all expected sources
                if expected_count > 0 and len(_source_cache) >= expected_count:
                    logger.info(f"[NDI] Found all {expected_count} expected sources")
                    break

                # Check timeout
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms >= timeout_ms:
                    if expected_count > 0 and len(_source_cache) < expected_count:
                        logger.warning(
                            f"[NDI] Timeout: Found {len(_source_cache)}/{expected_count} "
                            f"sources after {int(elapsed_ms)}ms"
                        )
                    break

                # Continue polling if we haven't found all sources yet
                if expected_count == 0:
                    # No expected count - just do one poll
                    break

            # Update discovery timestamp
            _last_discovery_time = time.time()

            logger.info(f"[NDI] Cached {len(_source_cache)} sources")
            return len(_source_cache)

    except Exception as e:
        logger.exception(f"[NDI] Error during source discovery: {e}")
        return 0


def find_ndi_cameras(timeout_ms: int = 5000) -> list[str]:
    """
    Discover NDI cameras on the network using mDNS.
    Returns list of NDI source names.

    Note: Requires firewall to allow mDNS traffic on UDP port 5353.
    If discovery returns empty list, check firewall configuration.
    Thread-safe: Uses lock to prevent concurrent access to global finder.
    """
    if not _ensure_ndi_initialized():
        logger.debug("NDI not available or failed to initialize")
        return []

    try:
        # Use lock to prevent concurrent access to global finder
        with _ndi_lock:
            # Wait for sources (this blocks!)
            ndi.find_wait_for_sources(_global_finder, timeout_ms)
            sources = ndi.find_get_current_sources(_global_finder)

            camera_names = []
            for i, source in enumerate(sources):
                try:
                    if hasattr(source, "ndi_name"):
                        name = source.ndi_name
                        name = name.decode("utf-8") if isinstance(name, bytes) else str(name)
                        camera_names.append(name)
                except (AttributeError, UnicodeDecodeError, ValueError) as e:
                    logger.warning(f"NDI Discovery - Error processing source {i}: {e}")

            if camera_names:
                logger.info(f"NDI Discovery found {len(camera_names)} camera(s)")
            return camera_names

    except (ImportError, RuntimeError, OSError, AttributeError) as e:
        logger.error(f"NDI Discovery error: {e}", exc_info=True)
        return []


def get_ndi_error_message() -> str:
    """Get NDI error message if library is not available"""
    return ndi_error_message
