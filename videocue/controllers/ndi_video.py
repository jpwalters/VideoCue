"""
NDI video receiver with frame dropping for performance
"""
import logging
import threading
from typing import Optional, List, Any
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage
from videocue.exceptions import NDINotAvailableError, NDIConnectionError, NDISourceNotFoundError
from videocue.constants import NetworkConstants

logger = logging.getLogger(__name__)

# Try to import NDI library
ndi: Any = None  # Type annotation for ndi module (conditionally imported)
ndi_available = False
ndi_error_message = ""
_ndi_initialized = False
_global_finder = None
_ndi_lock = threading.Lock()  # Thread safety for global NDI resources

try:
    import NDIlib as ndi
    ndi_available = True
except ImportError as e:
    ndi_error_message = (
        "NDI library not available. Please install NDI Runtime:\n\n"
        "Download from: https://ndi.tv/tools/\n\n"
        "The application will continue without NDI video streaming support.\n"
        "You can still control cameras using IP addresses."
    )
    print(f"NDI Import Error: {e}")
except Exception as e:
    ndi_error_message = f"NDI library error: {e}\n\nPlease install NDI Runtime from https://ndi.tv/tools/"
    print(f"NDI Error: {e}")


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
                if ndi.initialize():
                    _ndi_initialized = True
                    logger.info("[NDI Global] Creating global finder...")
                    find_settings = ndi.FindCreate()
                    find_settings.show_local_sources = True
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


def cleanup_ndi() -> None:
    """Cleanup NDI resources (call on application shutdown)"""
    global _ndi_initialized, _global_finder
    with _ndi_lock:
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
    Uses QueuedConnection with implicit queue size of 1 for frame_ready signal.
    """

    # Signals - Qt automatically marshals these to main thread
    frame_ready = pyqtSignal(QImage)  # Emits latest video frame
    connected = pyqtSignal(str)  # Emits web control URL on first connection
    error = pyqtSignal(str)  # Emits error message

    def __init__(self, source_name: str):
        super().__init__()
        self.source_name = source_name
        self.running = False
        self._stop_event = threading.Event()
        self._receiver = None
        self._finder = None
        logger.debug(f"NDI thread created for source: {source_name}")

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
            import traceback
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
        try:
            # Use the global finder
            ndi.find_wait_for_sources(_global_finder, 5000)
            sources = ndi.find_get_current_sources(_global_finder)

            # Find matching source
            target_source = None
            for source in sources:
                source_name = source.ndi_name.decode(
                    'utf-8') if isinstance(source.ndi_name, bytes) else str(source.ndi_name)
                if source_name == self.source_name:
                    target_source = source
                    break

            if not target_source:
                # Try to create source manually - discovery may not work but direct connection might
                try:
                    target_source = ndi.Source()
                    target_source.ndi_name = self.source_name.encode(
                        'utf-8') if isinstance(self.source_name, str) else self.source_name
                except (ImportError, RuntimeError, AttributeError):
                    self.error.emit(
                        f"NDI source '{self.source_name}' not found (found {len(sources)} sources)")
                    return

            # Create receiver
            self._receiver = ndi.recv_create_v3()
            if not self._receiver:
                self.error.emit("Failed to create NDI receiver")
                return

            # Connect to source
            ndi.recv_connect(self._receiver, target_source)
            print("[NDI] Connected to receiver")

            # Reception loop
            self.running = True
            first_frame = True
            frame_count = 0
            skip_count = 0
            no_frame_count = 0
            max_no_frame_attempts = 50  # 5 seconds (50 * 100ms)

            print("[NDI] Starting reception loop...")

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
                                if frame_count == 1:
                                    print(f"[NDI] Connected: {v.xres}x{v.yres}")
                                web_url = self._extract_web_control()  # pylint: disable=assignment-from-none
                                if web_url:
                                    self.connected.emit(web_url)
                                first_frame = False

                            # Skip every other frame for performance (30 FPS instead of 60)
                            skip_count += 1
                            if skip_count % 2 == 0:
                                # Convert frame to QImage
                                qimage = self._convert_frame(v)
                                if qimage:
                                    # Emit signal - Qt will drop old frames if UI hasn't processed them
                                    self.frame_ready.emit(qimage)

                            # Free the video frame
                            ndi.recv_free_video_v2(self._receiver, v)

                        elif t == ndi.FRAME_TYPE_NONE:
                            # No data received, increment timeout counter
                            no_frame_count += 1
                            if no_frame_count >= max_no_frame_attempts:
                                self.error.emit(f"NDI source '{self.source_name}' not responding after 5 seconds. Check source name and network connectivity.")
                                break
                        elif t == ndi.FRAME_TYPE_ERROR:
                            print("[NDI] Received error frame type")
                            self.error.emit(f"NDI error receiving from '{self.source_name}'")
                            break

                    except KeyboardInterrupt:
                        print("[NDI] Interrupted")
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

    def _extract_web_control(self) -> Optional[str]:
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
                    web_url = web_url.decode('utf-8')
                
                logger.info(f"Web control URL: {web_url}")
                return web_url
            
            return None
        except (ImportError, RuntimeError, AttributeError, KeyError) as e:
            logger.warning(f"Failed to get web control URL: {e}")
            return None

    def _convert_frame(self, video_frame) -> Optional[QImage]:
        """Convert NDI video frame (UYVY422) to QImage (RGB) with comprehensive error handling"""
        try:
            # Get frame data
            width = video_frame.xres
            height = video_frame.yres
            line_stride = video_frame.line_stride_in_bytes

            # Only support UYVY for now
            if video_frame.FourCC != ndi.FOURCC_VIDEO_TYPE_UYVY:
                print(
                    f"[NDI] Unsupported video format: {video_frame.FourCC} (expected UYVY: {ndi.FOURCC_VIDEO_TYPE_UYVY})")
                return None

            # Get frame data as bytes - handle different data types
            if hasattr(video_frame.data, 'tobytes'):
                frame_data = video_frame.data.tobytes()
            elif hasattr(video_frame.data, '__array__'):
                import numpy as np
                frame_data = bytes(np.array(video_frame.data).flatten())
            else:
                frame_data = bytes(video_frame.data)

            expected_size = line_stride * height
            if len(frame_data) < expected_size:
                print(f"[NDI] Frame data too small: {len(frame_data)} < {expected_size}")
                return None

            # Convert UYVY to RGB
            rgb_data = self._uyvy_to_rgb(frame_data, width, height, line_stride)
            if not rgb_data:
                print("[NDI] RGB conversion returned empty data")
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

        except (ValueError, TypeError, MemoryError, AttributeError) as e:
            import traceback
            print(f"[NDI] Frame conversion error: {e}")
            traceback.print_exc()
            return None
        except Exception as e:
            # Catch ANY other exception to prevent thread crash
            import traceback
            print(f"[NDI] Unexpected error during frame conversion: {e}")
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
                frame = frame.reshape(height, line_stride)[:, :width * 2].flatten()

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
            print("[NDI] WARNING: NumPy not available, using slow fallback")
            return self._uyvy_to_rgb_slow(uyvy_data, width, height, line_stride)
        except (ValueError, AttributeError, TypeError) as e:
            print(f"[NDI] NumPy conversion error: {e}")
            return self._uyvy_to_rgb_slow(uyvy_data, width, height, line_stride)

    def _uyvy_to_rgb_slow(self, uyvy_data: bytes, width: int, height: int, line_stride: int) -> bytes:
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
                rgb[rgb_offset:rgb_offset+3] = [r0, g0, b0]

                if x + 1 < width:
                    r1 = max(0, min(255, int(y1 + 1.402 * v)))
                    g1 = max(0, min(255, int(y1 - 0.344 * u - 0.714 * v)))
                    b1 = max(0, min(255, int(y1 + 1.772 * u)))
                    rgb_offset = (y * width + x + 1) * 3
                    rgb[rgb_offset:rgb_offset+3] = [r1, g1, b1]

        return bytes(rgb)

    def _cleanup(self):
        """Clean up NDI resources - never throws exceptions"""
        try:
            if self._receiver:
                try:
                    ndi.recv_destroy(self._receiver)
                except Exception as e:
                    print(f"[NDI] Error destroying receiver: {e}")
                finally:
                    self._receiver = None

            # Don't destroy global finder - it's shared
            self._finder = None

            # Don't call ndi.destroy() - keep NDI initialized globally
        except Exception as e:
            # Catch ANY exception during cleanup
            print(f"[NDI] Unexpected error during cleanup: {e}")


def find_ndi_cameras(timeout_ms: int = 5000) -> List[str]:
    """
    Discover NDI cameras on the network using mDNS.
    Returns list of NDI source names.
    
    Note: Requires firewall to allow mDNS traffic on UDP port 5353.
    If discovery returns empty list, check firewall configuration.
    Thread-safe: Uses lock to prevent concurrent access to global finder.
    """
    if not _ensure_ndi_initialized():
        print("[NDI Discovery] NDI not available or failed to initialize")
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
                    if hasattr(source, 'ndi_name'):
                        name = source.ndi_name
                        if isinstance(name, bytes):
                            name = name.decode('utf-8')
                        else:
                            name = str(name)
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
