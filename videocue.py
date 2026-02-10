#!/usr/bin/env python3
"""
VideoCue - Multi-camera PTZ controller with VISCA-over-IP and NDI streaming
"""

import logging
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt  # type: ignore
from PyQt6.QtGui import QIcon  # type: ignore
from PyQt6.QtWidgets import QApplication, QMessageBox  # type: ignore

from videocue import __version__
from videocue.exceptions import VideoCueException
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


def setup_logging() -> None:
    """Configure application logging"""
    log_dir = get_app_data_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "videocue.log"

    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set specific module levels
    logging.getLogger("videocue.controllers.usb_controller").setLevel(logging.WARNING)
    logging.getLogger("videocue.controllers.ndi_video").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info(f"VideoCue {__version__} starting")
    logger.info(f"Log file: {log_file}")
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
    if issubclass(exc_type, VideoCueException):
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


def main() -> None:
    """Main application entry point"""
    # Setup logging first
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting VideoCue application")

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
        return 1

    # Run event loop - Qt handles all lifecycle management
    logger.info("Starting Qt event loop")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
