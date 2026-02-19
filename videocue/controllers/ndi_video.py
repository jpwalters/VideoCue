"""
NDI video receiver with frame dropping for performance
"""

import logging
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
                # Set environment variables for NDI configuration (like CamControl)
                # RUDP mode provides more reliable connections
                import os

                if "NDI_RECV_PROTOCOL_MODE" not in os.environ:
                    os.environ["NDI_RECV_PROTOCOL_MODE"] = (
                        "RUDP"  # Reliable UDP (same as CamControl)
                    )
                    logger.info("[NDI Global] Set NDI protocol mode to RUDP")

                if ndi.initialize():
                    _ndi_initialized = True
                    logger.info("[NDI Global] Creating global finder...")
                    find_settings = ndi.FindCreate()
                    find_settings.show_local_sources = True
                    _global_finder = ndi.find_create_v2(find_settings)
                    if _global_finder:
                        logger.info("[NDI Global] NDI initialized successfully with RUDP")
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

    def __init__(self, source_name: str, frame_skip: int = 6):
        super().__init__()
        self.source_name = source_name
        self.frame_skip = (
            frame_skip  # How many frames to skip between displays (higher = faster/lower quality)
        )
        self.running = False
        self._stop_event = threading.Event()
        self._receiver = None
        self._finder = None  # Per-camera finder
        self._finder_created_at = None
        logger.info(f"[{source_name}] NDI thread created with frame_skip={frame_skip}")

    def run(self) -> None:
        """Main video reception loop with comprehensive error handling"""
        # Wrap EVERYTHING in try-except to prevent thread crashes from killing the app
        try:
            if not _ensure_ndi_initialized():
                err_msg = "NDI not available or failed to initialize"
                logger.error(f"[NDI] {err_msg}")
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
        import time

        start_time = time.time()

        try:
            # EXPERIMENT: Skip discovery entirely, create source manually first
            # This tests whether NDI discovery is even necessary when we know the source name
            logger.info(f"[{self.source_name}] === CONNECTION START ===")
            logger.info(f"[{self.source_name}] Strategy: Manual source creation (skip discovery)")

            target_source = None
            source_creation_method = "unknown"

            # METHOD 1: Manual source creation (FASTEST - no discovery)
            try:
                logger.info(f"[{self.source_name}] Creating source manually from name...")
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

            # METHOD 2: Per-camera finder with discovery (if manual fails)
            if not target_source:
                logger.warning(
                    f"[{self.source_name}] Manual creation failed, trying per-camera finder..."
                )
                try:
                    # Create dedicated finder for this camera
                    logger.info(f"[{self.source_name}] Creating dedicated NDI finder...")
                    finder_start = time.time()
                    find_settings = ndi.FindCreate()
                    find_settings.show_local_sources = True
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

            # Final check
            if not target_source:
                elapsed = (time.time() - start_time) * 1000
                logger.error(
                    f"[{self.source_name}] ✗ FAILED after {elapsed:.1f}ms - no source obtained"
                )
                self.error.emit(f"NDI source '{self.source_name}' not found")
                return

            logger.info(f"[{self.source_name}] Source obtained via: {source_creation_method}")

            # Create receiver with settings optimized for multiple camera preview
            # Note: bandwidth setting affects both quality and latency
            # - HIGHEST: Full quality, lowest latency, but high network/CPU usage (CAUSES ISSUES with multiple cameras)
            # - LOWEST: Reduced quality, higher latency, but lowest network/CPU usage (BEST for multiple cameras)
            # - Auto-negotiate: Can cause contention issues with 3+ cameras
            # CamControl uses LOWEST bandwidth with RUDP protocol for reliable multi-camera streaming
            logger.info(f"[{self.source_name}] Creating NDI receiver...")
            receiver_start = time.time()
            try:
                recv_settings = ndi.RecvCreateV3()  # Correct class name
                recv_settings.color_format = ndi.RECV_COLOR_FORMAT_UYVY_BGRA  # Default format
                # Use LOWEST bandwidth for multiple camera stability (like CamControl)
                recv_settings.bandwidth = ndi.RECV_BANDWIDTH_LOWEST  # Best for multiple cameras
                recv_settings.allow_video_fields = False  # Progressive only for simplicity
                self._receiver = ndi.recv_create_v3(recv_settings)
                receiver_elapsed = (time.time() - receiver_start) * 1000
                logger.info(
                    f"[{self.source_name}] ✓ Receiver created in {receiver_elapsed:.1f}ms (LOWEST bandwidth, frame_skip={self.frame_skip})"
                )
            except (AttributeError, TypeError) as e:
                # If settings not supported, fall back to defaults
                logger.warning(f"[{self.source_name}] RecvCreateV3 failed: {e}, using defaults")
                self._receiver = ndi.recv_create_v3()
                receiver_elapsed = (time.time() - receiver_start) * 1000
                logger.info(
                    f"[{self.source_name}] Receiver created in {receiver_elapsed:.1f}ms (defaults)"
                )

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
            current_resolution = None  # Track resolution to detect changes
            first_frame_time = None

            total_elapsed = (time.time() - start_time) * 1000
            logger.info(
                f"[{self.source_name}] Starting frame reception loop (setup took {total_elapsed:.1f}ms)..."
            )
            logger.info(f"[{self.source_name}] Waiting for first frame (10s timeout)...")

            try:
                while self.running:
                    try:
                        # Use shorter timeout (100ms) for more responsive shutdown
                        t, v, _a, _m = ndi.recv_capture_v2(self._receiver, 100)

                        if t == ndi.FRAME_TYPE_VIDEO:
                            frame_count += 1
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

                                # Reset skip counter to prevent overflow
                                skip_count = 0

                            # Free the video frame
                            ndi.recv_free_video_v2(self._receiver, v)

                        elif t == ndi.FRAME_TYPE_NONE:
                            # No data received, increment timeout counter
                            no_frame_count += 1
                            if no_frame_count >= max_no_frame_attempts:
                                elapsed_total = (time.time() - start_time) * 1000
                                timeout_seconds = (
                                    max_no_frame_attempts * NetworkConstants.NDI_FRAME_TIMEOUT_MS
                                ) // 1000
                                logger.error(
                                    f"[{self.source_name}] ✗✗✗ NO FRAMES after {max_no_frame_attempts} attempts ({timeout_seconds}s) ✗✗✗"
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
                                logger.error(f"[{self.source_name}] === CONNECTION FAILED ===")
                                self.error.emit(
                                    f"NDI source '{self.source_name}' not responding after {timeout_seconds} seconds. "
                                    "Check source name and network connectivity. Try reconnecting."
                                )
                                break
                        elif t == ndi.FRAME_TYPE_ERROR:
                            logger.debug("Received error frame type")
                            self.error.emit(f"NDI error receiving from '{self.source_name}'")
                            break

                    except KeyboardInterrupt:
                        logger.debug("Interrupted")
                        break
                    except (ImportError, RuntimeError, OSError, AttributeError) as e:
                        logger.error(f"Error in reception loop: {e}", exc_info=True)
                        self.error.emit(f"NDI error: {str(e)}")
                        break
                    except Exception as e:
                        # Catch ANY other exception in the frame processing
                        logger.error(f"Unexpected error processing frame: {e}", exc_info=True)
                        self.error.emit(f"NDI unexpected error: {str(e)}")
                        break
            except Exception as e:
                logger.critical(f"Fatal error in reception loop: {e}", exc_info=True)
                self.error.emit(f"NDI fatal error: {str(e)}")
        except Exception as e:
            # Outer catch for the entire reception setup
            logger.critical(f"Fatal error during source setup: {e}", exc_info=True)
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
        """Convert NDI video frame (UYVY422) to QImage (RGB) with comprehensive error handling"""
        try:
            # Get frame data
            width = video_frame.xres
            height = video_frame.yres
            line_stride = video_frame.line_stride_in_bytes

            # Only support UYVY for now
            if video_frame.FourCC != ndi.FOURCC_VIDEO_TYPE_UYVY:
                logger.debug(
                    f"Unsupported video format: {video_frame.FourCC} (expected UYVY: {ndi.FOURCC_VIDEO_TYPE_UYVY})"
                )
                return None

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

            # Create QImage - use bytearray to ensure data ownership
            # QImage constructor doesn't take ownership of bytes, so we need to ensure
            # the data persists long enough for copy() to complete
            rgb_bytearray = bytearray(rgb_data)
            qimage = QImage(rgb_bytearray, width, height, width * 3, QImage.Format.Format_RGB888)

            # Make a copy so it persists independently
            # We need to explicitly keep rgb_bytearray alive until copy() completes
            result = qimage.copy()
            # Force Python to not optimize away rgb_bytearray before copy() completes
            _ = len(rgb_bytearray)
            return result

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
        Convert UYVY422 to RGB888 using NumPy for performance (100x+ faster than Python loops).
        Each UYVY macropixel (4 bytes) encodes 2 pixels: U Y0 V Y1
        """
        try:
            import numpy as np

            # Convert to numpy array
            frame = np.frombuffer(uyvy_data, dtype=np.uint8)

            # Reshape to handle line stride if needed
            if line_stride != width * 2:
                # Crop each line to actual width
                frame = frame.reshape(height, line_stride)[:, : width * 2].flatten()

            # Reshape to UYVY macropixels: [height, width//2, 4]
            uyvy = frame.reshape(height, width // 2, 4)

            # Extract components (vectorized)
            u = uyvy[:, :, 0].astype(np.int16) - 128
            y0 = uyvy[:, :, 1].astype(np.int16)
            v = uyvy[:, :, 2].astype(np.int16) - 128
            y1 = uyvy[:, :, 3].astype(np.int16)

            # ITU-R BT.601 conversion (vectorized)
            # Pixel 0
            r0 = y0 + 1.402 * v
            g0 = y0 - 0.344 * u - 0.714 * v
            b0 = y0 + 1.772 * u

            # Pixel 1
            r1 = y1 + 1.402 * v
            g1 = y1 - 0.344 * u - 0.714 * v
            b1 = y1 + 1.772 * u

            # Clip to [0, 255] and convert to uint8
            r0 = np.clip(r0, 0, 255).astype(np.uint8)
            g0 = np.clip(g0, 0, 255).astype(np.uint8)
            b0 = np.clip(b0, 0, 255).astype(np.uint8)
            r1 = np.clip(r1, 0, 255).astype(np.uint8)
            g1 = np.clip(g1, 0, 255).astype(np.uint8)
            b1 = np.clip(b1, 0, 255).astype(np.uint8)

            # Interleave pixels: [height, width, 3]
            rgb = np.zeros((height, width, 3), dtype=np.uint8)
            rgb[:, 0::2, 0] = r0
            rgb[:, 0::2, 1] = g0
            rgb[:, 0::2, 2] = b0
            rgb[:, 1::2, 0] = r1
            rgb[:, 1::2, 1] = g1
            rgb[:, 1::2, 2] = b1

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
        except Exception:
            # Catch ANY exception during cleanup
            logger.exception(f"[{self.source_name}] Unexpected error during cleanup")


def discover_and_cache_all_sources(timeout_ms: int = None) -> int:
    """
    Discover all NDI sources once and cache them for immediate use by camera threads.
    This should be called once at app startup before creating camera widgets.
    Returns the number of sources found and cached.
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
            logger.info(f"[NDI] Discovering all sources (timeout: {timeout_ms}ms)...")
            ndi.find_wait_for_sources(_global_finder, timeout_ms)
            sources = ndi.find_get_current_sources(_global_finder)

            logger.info(f"[NDI] Found {len(sources)} sources, caching them...")

            # Cache all discovered sources
            for source in sources:
                try:
                    source_name = (
                        source.ndi_name.decode("utf-8")
                        if isinstance(source.ndi_name, bytes)
                        else str(source.ndi_name)
                    )
                    _source_cache[source_name] = source
                    logger.info(f"[NDI Discovery] ✓ Cached source: '{source_name}'")
                except Exception as e:
                    logger.warning(f"[NDI] Error caching source: {e}")

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
