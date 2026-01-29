#!/usr/bin/env python3
"""
VideoCue - Multi-camera PTZ controller with VISCA-over-IP and NDI streaming
"""
import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox  # type: ignore
from PyQt6.QtCore import Qt  # type: ignore
from PyQt6.QtGui import QIcon  # type: ignore

# Import qdarkstyle for dark theme
try:
    import qdarkstyle
    has_dark_style = True
except ImportError:
    has_dark_style = False
    print("qdarkstyle not installed, using default theme")

from videocue.ui.main_window import MainWindow
from videocue.utils import resource_path


def exception_hook(exc_type, exc_value, exc_traceback):
    """Global exception handler to prevent app crashes"""
    # Format the exception
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"\n{'='*60}")
    print("UNHANDLED EXCEPTION:")
    print(error_msg)
    print('='*60)
    
    # Show error dialog to user
    try:
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setWindowTitle("Error")
        msg_box.setText("An unexpected error occurred.")
        msg_box.setDetailedText(error_msg)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()
    except Exception:
        # If even the error dialog fails, just print
        pass


def main():
    """Main application entry point"""
    # Install global exception handler
    sys.excepthook = exception_hook
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("VideoCue")
    app.setOrganizationName("VideoCue")

    # Set application icon
    icon_path = resource_path('resources/icon.png')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # Apply dark theme if available
    if has_dark_style:
        app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api='pyqt6'))

    # Create and show main window
    try:
        window = MainWindow()
        window.show()
    except Exception as e:
        error_msg = f"Failed to initialize application:\n{str(e)}\n\n{traceback.format_exc()}"
        print(error_msg)
        QMessageBox.critical(None, "Startup Error", error_msg)
        return 1

    # Run application
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
