#!/usr/bin/env python3
"""
VideoCue - Multi-camera PTZ controller with VISCA-over-IP and NDI streaming
"""

import logging
import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt  # type: ignore
from PyQt6.QtGui import QIcon  # type: ignore
from PyQt6.QtWidgets import QApplication, QMessageBox  # type: ignore

from videocue import __version__
from videocue.exceptions import VideoCueError
from videocue.ui_strings import UIStrings

# Import qdarkstyle for dark theme
try:
    import qdarkstyle

    has_dark_style = True
except ImportError:
    has_dark_style = False
    # Logged after logging setup in main()

from videocue.ui.main_window import MainWindow
from videocue.utils import get_app_data_dir, resource_path


def setup_logging(file_logging_enabled: bool = False) -> None:
    """Configure application logging

    Args:
        file_logging_enabled: If True, logs to file in addition to console
    """
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "videocue.log"

    # Build handlers list based on preference
    handlers = [logging.StreamHandler(sys.stdout)]
    if file_logging_enabled:
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    # Set specific module levels
    logging.getLogger("videocue.controllers.usb_controller").setLevel(logging.WARNING)
    logging.getLogger("videocue.controllers.ndi_video").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info(f"VideoCue {__version__} starting")
    if file_logging_enabled:
        logger.info(f"Log file: {log_file}")
    else:
        logger.info("File logging disabled (console only)")
    logger.info("=" * 60)


def exception_hook(exc_type, exc_value, exc_traceback):
    """Global exception handler to prevent app crashes"""
    # Don't catch KeyboardInterrupt - let it exit normally
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # Log the exception
    logger = logging.getLogger(__name__)
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

    # Format the exception
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # Determine error severity
    error_title = UIStrings.ERROR_CRITICAL
    if issubclass(exc_type, VideoCueError):
        error_title = f"{type(exc_value).__name__}"

    # Show error dialog to user
    try:
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle(error_title)
        msg_box.setText(UIStrings.ERROR_GENERIC)
        msg_box.setDetailedText(error_msg)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    except Exception:
        # If even the error dialog fails, just log it
        logger.exception("Failed to show error dialog")


class ExceptionHandlingApplication(QApplication):
    """QApplication subclass that catches Qt event exceptions"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(__name__)

    def notify(self, receiver, event) -> bool:
        """Override notify to catch exceptions in Qt event handlers"""
        try:
            return super().notify(receiver, event)
        except KeyboardInterrupt:
            # Let Ctrl+C exit cleanly
            raise
        except Exception as e:
            error_msg = f"Exception in Qt event handler: {str(e)}"
            self.logger.exception(error_msg)

            # Show error dialog
            try:
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Icon.Critical)
                msg_box.setWindowTitle(UIStrings.ERROR_QT_EVENT)
                msg_box.setText(UIStrings.ERROR_QT_EVENT_MSG)
                msg_box.setDetailedText(f"{error_msg}\n\n{traceback.format_exc()}")
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.exec()
            except Exception:
                self.logger.exception("Failed to show Qt event error dialog")

            # Don't crash, return False to indicate event wasn't handled
            return False


class SingleInstanceLock:
    """Manages single instance enforcement using a lock file"""

    def __init__(self):
        """Initialize the lock file path"""
        from videocue.utils import get_app_data_dir

        self.lock_file = get_app_data_dir() / "videocue.lock"
        self.lock_fd = None

    def acquire(self) -> bool:
        """Attempt to acquire the instance lock.

        Returns:
            bool: True if lock acquired successfully, False if another instance is running
        """
        try:
            # Try to open the lock file exclusively
            if os.name == "nt":  # Windows
                import msvcrt

                try:
                    # Create or open the lock file
                    self.lock_fd = self.lock_file.open("w")  # noqa: SIM115
                    # Try to lock it exclusively (non-blocking)
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                    # Write PID to lock file
                    self.lock_fd.write(str(os.getpid()))
                    self.lock_fd.flush()
                    return True
                except OSError:
                    # Lock failed - another instance is running
                    if self.lock_fd:
                        self.lock_fd.close()
                        self.lock_fd = None
                    return False
            else:  # Unix/Linux/Mac
                import fcntl

                try:
                    # Create or open the lock file
                    self.lock_fd = self.lock_file.open("w")  # noqa: SIM115
                    # Try to lock it exclusively (non-blocking)
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    # Write PID to lock file
                    self.lock_fd.write(str(os.getpid()))
                    self.lock_fd.flush()
                    return True
                except OSError:
                    # Lock failed - another instance is running
                    if self.lock_fd:
                        self.lock_fd.close()
                        self.lock_fd = None
                    return False
        except Exception as e:
            # If we can't create/access the lock file, allow the app to run
            logging.getLogger(__name__).warning(f"Failed to check single instance lock: {e}")
            return True

    def release(self):
        """Release the instance lock"""
        if self.lock_fd:
            try:
                if os.name == "nt":  # Windows
                    import msvcrt

                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # Unix/Linux/Mac
                    import fcntl

                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                self.lock_fd.close()
            except Exception:
                pass  # Ignore errors during cleanup
            finally:
                self.lock_fd = None

        # Try to remove lock file
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
        except Exception:
            pass  # Ignore errors during cleanup


def main() -> None:
    """Main application entry point"""
    # Load config first to get logging preference
    from videocue.models.config_manager import ConfigManager

    config = ConfigManager()
    file_logging_enabled = config.config.get("preferences", {}).get("file_logging_enabled", False)

    # Setup logging with preference
    setup_logging(file_logging_enabled)
    logger = logging.getLogger(__name__)
    logger.info("Starting VideoCue application")

    # Check single instance mode
    instance_lock = None
    single_instance_mode = config.get_single_instance_mode()

    if single_instance_mode:
        logger.info("Single instance mode enabled - checking for existing instances")
        instance_lock = SingleInstanceLock()
        if not instance_lock.acquire():
            logger.warning("Another instance is already running")
            QMessageBox.warning(
                None,
                "VideoCue Already Running",
                "Another instance of VideoCue is already running.\n\n"
                "Only one instance can run at a time when single instance mode is enabled.\n\n"
                "To allow multiple instances:\n"
                "1. Close the existing instance\n"
                "2. Open Preferences → Application\n"
                "3. Disable 'Enable single instance mode'\n"
                "4. Restart VideoCue",
            )
            return 1
        logger.info("Single instance lock acquired successfully")
    else:
        logger.info("Single instance mode disabled - multiple instances allowed")

    # Log theme availability
    if not has_dark_style:
        logger.warning("qdarkstyle not installed, using default theme")

    # Install global exception handler
    sys.excepthook = exception_hook

    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application with custom exception handling
    app = ExceptionHandlingApplication(sys.argv)
    app.setApplicationName(UIStrings.APP_NAME)
    app.setOrganizationName(UIStrings.APP_NAME)

    # Set application icon
    icon_path = resource_path("resources/icon.png")
    if Path(icon_path).exists():
        app.setWindowIcon(QIcon(icon_path))

    # Apply dark theme if available
    if has_dark_style:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyqt6"))

    # Create and show main window
    try:
        window = MainWindow()
        window.show()
    except Exception as e:
        error_msg = f"Failed to initialize application:\n{str(e)}\n\n{traceback.format_exc()}"
        logger.critical("Startup error", exc_info=True)
        QMessageBox.critical(None, "Startup Error", error_msg)
        if instance_lock:
            instance_lock.release()
        return 1

    # Run event loop - Qt handles all lifecycle management
    logger.info("Starting Qt event loop")
    exit_code = app.exec()

    # Release instance lock before exiting
    if instance_lock:
        logger.info("Releasing single instance lock")
        instance_lock.release()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
