#!/usr/bin/env python3
"""
VideoCue - Multi-camera PTZ controller with VISCA-over-IP and NDI streaming
"""

import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt  # type: ignore
from PyQt6.QtGui import QIcon  # type: ignore
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox  # type: ignore

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


def _apply_popup_window_policy(dialog: QDialog) -> None:
    """Force popup dialogs to show only Close button (no minimize/maximize)."""
    try:
        dialog.setWindowFlag(Qt.WindowType.CustomizeWindowHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowTitleHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        dialog.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, False)
        dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        dialog.setWindowFlag(Qt.WindowType.WindowMinMaxButtonsHint, False)

        if os.name == "nt":
            dialog.setWindowFlag(Qt.WindowType.MSWindowsFixedSizeDialogHint, True)

        if isinstance(dialog, QMessageBox):
            dialog.setSizeGripEnabled(False)

        # Re-show if needed so updated flags are applied by the window manager.
        if dialog.isVisible():
            dialog.show()
    except Exception:
        logging.getLogger(__name__).debug("Failed applying popup window policy", exc_info=True)


def _show_native_error_dialog(title: str, message: str) -> None:
    """Show a crash dialog without relying on Qt (safe for supervisor process)."""
    if os.name == "nt":
        try:
            import ctypes

            MB_ICONERROR = 0x00000010
            MB_OK = 0x00000000
            ctypes.windll.user32.MessageBoxW(0, message, title, MB_OK | MB_ICONERROR)
            return
        except Exception:
            pass

    print(f"{title}\n{message}", file=sys.stderr)


def _is_abnormal_exit(exit_code: int) -> bool:
    """Return True for likely crash exits (native fault or terminated by signal)."""
    if exit_code == 0:
        return False

    if exit_code < 0:
        return True

    if os.name == "nt":
        # Windows NTSTATUS values are often surfaced as signed negatives or 0xC0000000+.
        if exit_code >= 0xC0000000:
            return True
        if exit_code > 0x7FFFFFFF:
            return True

    return False


def _run_with_supervisor() -> int:
    """Run app in a child process and report abnormal crashes to the user."""
    child_args = [arg for arg in sys.argv[1:] if arg != "--child-process"]

    def run_child(disable_ndi: bool) -> subprocess.CompletedProcess:
        child_env = os.environ.copy()
        child_env["VIDEOCUE_SUPERVISED_CHILD"] = "1"
        child_env["VIDEOCUE_PROCESS_ROLE"] = "child"
        if disable_ndi:
            child_env["VIDEOCUE_DISABLE_NDI"] = "1"

        if getattr(sys, "frozen", False):
            command = [sys.executable, *child_args, "--child-process"]
        else:
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                *child_args,
                "--child-process",
            ]

        return subprocess.run(command, env=child_env, check=False)

    try:
        completed = run_child(disable_ndi=False)
    except Exception as e:
        _show_native_error_dialog(
            UIStrings.ERROR_CRITICAL,
            f"{UIStrings.ERROR_APP_LAUNCH_FAILED}: {UIStrings.APP_NAME}.\n\n{e}",
        )
        return 1

    exit_code = completed.returncode
    if _is_abnormal_exit(exit_code):
        _show_native_error_dialog(
            UIStrings.ERROR_CRITICAL,
            UIStrings.ERROR_APP_RESTARTING_SAFE_MODE,
        )

        try:
            recovery_run = run_child(disable_ndi=True)
            recovery_exit = recovery_run.returncode
            if not _is_abnormal_exit(recovery_exit):
                return recovery_exit
            exit_code = recovery_exit
        except Exception as e:
            _show_native_error_dialog(
                UIStrings.ERROR_CRITICAL,
                f"{UIStrings.ERROR_APP_LAUNCH_FAILED}: {UIStrings.APP_NAME}.\n\n{e}",
            )
            return 1

        log_path = get_app_data_dir() / "logs" / "videocue.log"
        _show_native_error_dialog(
            UIStrings.ERROR_CRITICAL,
            (
                f"{UIStrings.ERROR_APP_CRASHED}\n\n"
                f"{UIStrings.ERROR_APP_EXIT_CODE.format(code=exit_code)}\n"
                f"{UIStrings.ERROR_APP_LOG_PATH.format(path=log_path)}\n\n"
                f"{UIStrings.ERROR_APP_CRASH_TROUBLESHOOT}"
            ),
        )

    return exit_code


def setup_logging(file_logging_enabled: bool = False, process_role: str = "direct") -> None:
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
    logger.info(f"Process role: {process_role}")

    # Write Python fatal crash diagnostics to a separate file when possible.
    try:
        import faulthandler

        crash_file = log_dir / "videocue-crash.log"
        crash_stream = crash_file.open("a", encoding="utf-8")
        faulthandler.enable(file=crash_stream, all_threads=True)
        logger.info(f"Faulthandler enabled: {crash_file}")
    except Exception as e:
        logger.debug(f"Could not enable faulthandler: {e}")
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
            # Enforce popup window buttons globally (covers static QMessageBox helpers too).
            if (
                isinstance(receiver, QDialog)
                and event is not None
                and event.type() in (QEvent.Type.Polish, QEvent.Type.Show)
            ):
                _apply_popup_window_policy(receiver)

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
                    # Note: Cannot use context manager (with statement) here because the file
                    # must remain open for the lifetime of the application to maintain the lock.
                    # The lock is released in release() method when app exits.
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
                    # Note: Cannot use context manager (with statement) here because the file
                    # must remain open for the lifetime of the application to maintain the lock.
                    # The lock is released in release() method when app exits.
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


def main() -> int:
    """Main application entry point"""
    # Load config first to get logging preference
    from videocue.models.config_manager import ConfigManager

    config = ConfigManager()
    file_logging_enabled = config.config.get("preferences", {}).get("file_logging_enabled", False)

    # Setup logging with preference
    process_role = os.environ.get("VIDEOCUE_PROCESS_ROLE", "direct")
    setup_logging(file_logging_enabled, process_role=process_role)
    logger = logging.getLogger(__name__)
    logger.info("Starting VideoCue application")
    ndi_disabled_for_session = os.environ.get("VIDEOCUE_DISABLE_NDI") == "1"
    if ndi_disabled_for_session:
        logger.warning("Running with NDI disabled for this session")

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

    if ndi_disabled_for_session:
        QMessageBox.warning(
            None, UIStrings.ERROR_NDI_NOT_AVAILABLE, UIStrings.WARN_NDI_SESSION_DISABLED
        )

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
    running_child = (
        os.environ.get("VIDEOCUE_SUPERVISED_CHILD") == "1" or "--child-process" in sys.argv
    )
    if "--child-process" in sys.argv:
        sys.argv = [arg for arg in sys.argv if arg != "--child-process"]

    use_supervisor = (
        os.name == "nt"
        and not running_child
        and os.environ.get("VIDEOCUE_SUPERVISOR_DISABLED") != "1"
    )

    if use_supervisor:
        os.environ["VIDEOCUE_PROCESS_ROLE"] = "supervisor"
        sys.exit(_run_with_supervisor())

    sys.exit(main())
