"""
Main application window
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSlot  # type: ignore
from PyQt6.QtGui import (  # type: ignore
    QAction,
    QActionGroup,
    QBrush,
    QColor,
    QDesktopServices,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (  # type: ignore
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from videocue import __version__
from videocue.constants import UIConstants
from videocue.controllers.ndi_video import cleanup_ndi, get_ndi_error_message, ndi_available
from videocue.controllers.usb_controller import MovementDirection, USBController
from videocue.models.config_manager import ConfigManager
from videocue.models.cue_manager import CueManager
from videocue.models.video import VideoSize
from videocue.ui.about_dialog import AboutDialog
from videocue.ui.camera_add_dialog import CameraAddDialog
from videocue.ui.camera_widget import CameraWidget
from videocue.ui.update_check_thread import UpdateCheckThread
from videocue.ui_strings import UIStrings
from videocue.utils import resource_path

logger = logging.getLogger(__name__)


class CueHeaderView(QHeaderView):
    """Custom header view supporting per-section highlight."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._highlighted_section = -1
        self._disconnected_sections: set[int] = set()

    def set_highlighted_section(self, section: int) -> None:
        """Set highlighted logical section index (-1 for none)."""
        if self._highlighted_section == section:
            return
        self._highlighted_section = section
        self.viewport().update()

    def set_disconnected_sections(self, sections: set[int]) -> None:
        """Set header sections corresponding to disconnected cameras."""
        if self._disconnected_sections == sections:
            return
        self._disconnected_sections = sections
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        """Paint header section with optional orange highlight."""
        super().paintSection(painter, rect, logicalIndex)

        is_disconnected = logicalIndex in self._disconnected_sections
        is_selected = logicalIndex == self._highlighted_section

        if not is_disconnected and not is_selected:
            return

        header_text = self.model().headerData(
            logicalIndex, self.orientation(), Qt.ItemDataRole.DisplayRole
        )

        painter.save()
        if is_disconnected:
            painter.fillRect(rect, QColor("#6B1D1D"))
            painter.setPen(QColor("#FFB3B3"))
        else:
            painter.fillRect(rect, QColor("#2B2B2B"))
            painter.setPen(QColor("#FF8C00"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(header_text))
        painter.restore()


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Set window icon
        icon_path = resource_path("resources/icon.png")
        if Path(icon_path).exists():
            self.setWindowIcon(QIcon(icon_path))

        # Configuration manager
        self.config = ConfigManager()
        self.cue_manager = CueManager()

        # Camera widgets list
        self.cameras = []
        self.selected_camera_index = 0

        # USB controller
        self.usb_controller = None

        # Pre-initialize UI attributes
        self.usb_icon_label = None
        self.cameras_container = None
        self.cameras_layout = None
        self.loading_label = None
        self.loading_progress = None
        self.cues_tab = None
        self.cues_table = None
        self.cues_header = None
        self.cue_add_button = None
        self.cue_delete_button = None
        self.cue_duplicate_button = None
        self.cue_insert_button = None
        self.cue_run_button = None
        self.cue_lock_button = None
        self.cue_run_shortcut_space = None
        self.cue_run_shortcut_enter = None
        self.cue_run_shortcut_return = None
        self._cue_camera_columns = []
        self._cue_table_updating = False
        self._cue_table_locked = False
        self._armed_cue_id = None
        self._last_run_cue_id = None
        self.preferences_dialog = None
        self._preferences_dialog_open = False
        self._total_cameras_to_load = 0
        self._cameras_initialized = 0
        self._initialized_camera_ids: set[str] = set()
        self._current_progress_step = 0
        self._total_progress_steps = 0

        # USB controller signal handlers (stored for connect/disconnect)
        self._usb_signal_handlers = {}

        # Update check thread (stored to prevent garbage collection)
        self._update_check_thread = None
        self._update_progress_dialog = None
        self.false_color_action = None
        self.waveform_action = None
        self.vectorscope_action = None
        self.rgb_parade_action = None
        self.histogram_action = None

        # Setup UI
        self.init_ui()

        # Initialize USB controller
        self.init_usb_controller()

        # Defer camera loading until after window is shown
        self._cameras_loaded = False

        # Show NDI error if library not available and user hasn't disabled NDI video in preferences
        if not ndi_available and self.config.get_ndi_video_enabled():
            QMessageBox.warning(
                self, "NDI Not Available", get_ndi_error_message(), QMessageBox.StandardButton.Ok
            )

    def init_ui(self) -> None:
        """Initialize user interface"""
        self.setWindowTitle(UIStrings.APP_NAME)
        self.setGeometry(
            UIConstants.WINDOW_DEFAULT_X,
            UIConstants.WINDOW_DEFAULT_Y,
            UIConstants.WINDOW_DEFAULT_WIDTH,
            UIConstants.WINDOW_DEFAULT_HEIGHT,
        )
        logger.info("Initializing main window UI")

        # Create menu bar
        self.create_menu_bar()

        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Cameras tab
        self.cameras_tab = self.create_cameras_tab()
        self.tab_widget.addTab(self.cameras_tab, UIStrings.TAB_CAMERAS)

        # Cues tab
        self.cues_tab = self.create_cues_tab()
        self.tab_widget.addTab(self.cues_tab, UIStrings.TAB_CUES)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def create_menu_bar(self):
        """Create application menu bar"""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        preferences_action = QAction("Preferences", self)
        preferences_action.triggered.connect(self.show_controller_preferences)
        edit_menu.addAction(preferences_action)

        # Logging preferences
        edit_menu.addSeparator()
        file_logging_action = QAction(UIStrings.MENU_FILE_LOGGING, self)
        file_logging_action.setCheckable(True)
        file_logging_action.setChecked(
            self.config.config.get("preferences", {}).get("file_logging_enabled", False)
        )
        file_logging_action.triggered.connect(self.on_file_logging_toggled)
        edit_menu.addAction(file_logging_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Video size submenu
        video_size_menu = QMenu("Video Size", self)
        view_menu.addMenu(video_size_menu)

        # Create radio group for video sizes
        size_group = QActionGroup(self)
        size_group.setExclusive(True)

        default_size = self.config.get_default_video_size()

        for size in VideoSize.presets():
            action = QAction(str(size), self)
            action.setCheckable(True)
            action.setData(size)

            # Check if this is the default size
            if size.width == default_size[0] and size.height == default_size[1]:
                action.setChecked(True)

            action.triggered.connect(lambda checked, s=size: self.on_video_size_changed(s))
            size_group.addAction(action)
            video_size_menu.addAction(action)

        # Performance submenu
        performance_menu = QMenu("Video Performance", self)
        view_menu.addMenu(performance_menu)

        # Create radio group for NDI bandwidth
        bandwidth_group = QActionGroup(self)
        bandwidth_group.setExclusive(True)

        current_bandwidth = self.config.get_ndi_bandwidth()

        # NDI bandwidth options: (bandwidth_value, label, description)
        bandwidth_options = [
            ("high", "High Bandwidth", "Maximum quality, higher network usage"),
            ("low", "Low Bandwidth", "Lower network usage, more compression"),
        ]

        for bandwidth_value, label, tooltip in bandwidth_options:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.setData(bandwidth_value)

            if bandwidth_value == current_bandwidth:
                action.setChecked(True)

            action.triggered.connect(
                lambda checked, bw=bandwidth_value: self.on_bandwidth_changed(bw)
            )
            bandwidth_group.addAction(action)
            performance_menu.addAction(action)

        # Color format submenu
        color_format_menu = QMenu(UIStrings.MENU_COLOR_FORMAT, self)
        view_menu.addMenu(color_format_menu)

        # Create radio group for color format
        format_group = QActionGroup(self)
        format_group.setExclusive(True)

        current_format = self.config.get_ndi_color_format()

        # Color format options: (format_value, label, tooltip)
        format_options = [
            ("uyvy", "UYVY (Default)", "Native camera format with NumPy conversion"),
            ("bgra", "BGRA", "Qt-native format, minimal conversion overhead"),
            ("rgba", "RGBA", "Standard RGBA format"),
        ]

        for format_value, label, tooltip in format_options:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setToolTip(tooltip)
            action.setData(format_value)

            if format_value == current_format:
                action.setChecked(True)

            action.triggered.connect(
                lambda checked, fmt=format_value: self.on_color_format_changed(fmt)
            )
            format_group.addAction(action)
            color_format_menu.addAction(action)

        # Scope toggles (mutually exclusive live view modes)
        scopes_menu = QMenu(UIStrings.MENU_SCOPES, self)
        view_menu.addMenu(scopes_menu)

        self.false_color_action = QAction(UIStrings.MENU_FALSE_COLOR, self)
        self.false_color_action.setCheckable(True)
        self.false_color_action.setToolTip(UIStrings.TOOLTIP_FALSE_COLOR)
        self.false_color_action.setChecked(self.config.get_ndi_false_color_enabled())
        self.false_color_action.triggered.connect(self.on_false_color_toggled)
        scopes_menu.addAction(self.false_color_action)

        self.waveform_action = QAction(UIStrings.MENU_WAVEFORM, self)
        self.waveform_action.setCheckable(True)
        self.waveform_action.setToolTip(UIStrings.TOOLTIP_WAVEFORM)
        self.waveform_action.setChecked(self.config.get_ndi_waveform_enabled())
        self.waveform_action.triggered.connect(self.on_waveform_toggled)
        scopes_menu.addAction(self.waveform_action)

        self.vectorscope_action = QAction(UIStrings.MENU_VECTORSCOPE, self)
        self.vectorscope_action.setCheckable(True)
        self.vectorscope_action.setToolTip(UIStrings.TOOLTIP_VECTORSCOPE)
        self.vectorscope_action.setChecked(self.config.get_ndi_vectorscope_enabled())
        self.vectorscope_action.triggered.connect(self.on_vectorscope_toggled)
        scopes_menu.addAction(self.vectorscope_action)

        self.rgb_parade_action = QAction(UIStrings.MENU_RGB_PARADE, self)
        self.rgb_parade_action.setCheckable(True)
        self.rgb_parade_action.setToolTip(UIStrings.TOOLTIP_RGB_PARADE)
        self.rgb_parade_action.setChecked(self.config.get_ndi_rgb_parade_enabled())
        self.rgb_parade_action.triggered.connect(self.on_rgb_parade_toggled)
        scopes_menu.addAction(self.rgb_parade_action)

        self.histogram_action = QAction(UIStrings.MENU_HISTOGRAM, self)
        self.histogram_action.setCheckable(True)
        self.histogram_action.setToolTip(UIStrings.TOOLTIP_HISTOGRAM)
        self.histogram_action.setChecked(self.config.get_ndi_histogram_enabled())
        self.histogram_action.triggered.connect(self.on_histogram_toggled)
        scopes_menu.addAction(self.histogram_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        check_updates_action = QAction(UIStrings.MENU_CHECK_UPDATES, self)
        check_updates_action.triggered.connect(self.check_for_updates)
        help_menu.addAction(check_updates_action)

        help_menu.addSeparator()

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def create_cameras_tab(self):
        """Create cameras tab content"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Top toolbar
        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)

        # USB controller status indicator with icon
        from PyQt6.QtWidgets import QLabel

        self.usb_icon_label = QLabel()
        self.usb_icon_label.setFixedSize(28, 28)
        self.usb_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.usb_icon_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.usb_icon_label.mousePressEvent = lambda event: self.show_controller_preferences()  # type: ignore
        self.usb_icon_label.setToolTip("Controller Settings")

        toolbar.addWidget(self.usb_icon_label)

        # Update icon based on connection status
        self._update_usb_indicator(False)

        toolbar.addStretch()

        # Loading indicator
        from PyQt6.QtWidgets import QProgressBar

        self.loading_label = QLabel("")
        self.loading_label.setVisible(False)
        toolbar.addWidget(self.loading_label)

        self.loading_progress = QProgressBar()
        self.loading_progress.setMaximumWidth(200)
        self.loading_progress.setTextVisible(True)
        self.loading_progress.setVisible(False)
        toolbar.addWidget(self.loading_progress)

        # Add camera button
        from PyQt6.QtWidgets import QPushButton  # type: ignore

        add_button = QPushButton("Add Camera")
        add_button.clicked.connect(self.add_camera_dialog)
        toolbar.addWidget(add_button)

        # Scroll area for cameras
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        # Container for camera widgets
        self.cameras_container = QWidget()
        self.cameras_layout = QHBoxLayout(self.cameras_container)
        self.cameras_layout.setSpacing(10)
        self.cameras_layout.setContentsMargins(5, 5, 5, 5)
        self.cameras_layout.addStretch()

        scroll.setWidget(self.cameras_container)

        return widget

    def create_cues_tab(self):
        """Create cues tab content."""
        from PyQt6.QtWidgets import (
            QAbstractItemView,
            QHBoxLayout,
            QPushButton,
            QTableWidget,
        )

        widget = QWidget()
        layout = QVBoxLayout(widget)

        button_row = QHBoxLayout()
        self.cue_lock_button = QPushButton(UIStrings.BTN_LOCK)
        self.cue_lock_button.clicked.connect(self._toggle_cue_lock)
        self._style_cue_toolbar_button(self.cue_lock_button, "lock")
        button_row.addWidget(self.cue_lock_button)

        self.cue_run_button = QPushButton(UIStrings.BTN_RUN_CUE)
        self.cue_run_button.clicked.connect(self._run_selected_cue_row)
        self._style_cue_toolbar_button(self.cue_run_button, "run")
        button_row.addWidget(self.cue_run_button)

        button_row.addStretch()

        self.cue_add_button = QPushButton(UIStrings.BTN_ADD_CUE)
        self.cue_add_button.clicked.connect(self._add_cue_row)
        self._style_cue_toolbar_button(self.cue_add_button, "add")
        button_row.addWidget(self.cue_add_button)

        self.cue_insert_button = QPushButton(UIStrings.BTN_INSERT_CUE)
        self.cue_insert_button.clicked.connect(self._insert_cue_row_after_selected)
        self._style_cue_toolbar_button(self.cue_insert_button, "insert")
        button_row.addWidget(self.cue_insert_button)

        self.cue_duplicate_button = QPushButton(UIStrings.BTN_DUPLICATE_CUE)
        self.cue_duplicate_button.clicked.connect(self._duplicate_selected_cue_row)
        self._style_cue_toolbar_button(self.cue_duplicate_button, "duplicate")
        button_row.addWidget(self.cue_duplicate_button)

        self.cue_delete_button = QPushButton(UIStrings.BTN_DELETE_CUE)
        self.cue_delete_button.clicked.connect(self._delete_selected_cue_row)
        self._style_cue_toolbar_button(self.cue_delete_button, "delete")
        button_row.addWidget(self.cue_delete_button)

        layout.addLayout(button_row)

        self.cues_table = QTableWidget()
        self.cues_header = CueHeaderView(Qt.Orientation.Horizontal, self.cues_table)
        self.cues_table.setHorizontalHeader(self.cues_header)
        self.cues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cues_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.cues_table.cellChanged.connect(self._on_cue_table_cell_changed)
        self.cues_table.verticalHeader().sectionDoubleClicked.connect(
            self._on_cue_row_header_double_clicked
        )

        self.cue_run_shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self.cues_table)
        self.cue_run_shortcut_space.activated.connect(self._run_cue_if_cues_tab_active)
        self.cue_run_shortcut_enter = QShortcut(QKeySequence(Qt.Key.Key_Enter), self.cues_table)
        self.cue_run_shortcut_enter.activated.connect(self._run_cue_if_cues_tab_active)
        self.cue_run_shortcut_return = QShortcut(QKeySequence(Qt.Key.Key_Return), self.cues_table)
        self.cue_run_shortcut_return.activated.connect(self._run_cue_if_cues_tab_active)

        layout.addWidget(self.cues_table)

        self._refresh_cues_table()
        self._update_cue_controls_state()

        return widget

    def _style_cue_toolbar_button(self, button: QWidget, button_type: str) -> None:
        """Apply visual style for cue toolbar buttons."""
        style_map = {
            "add": ("#1F6FEB", "#2F81F7", "#1A5DC4"),
            "insert": ("#8250DF", "#9966FF", "#6D42BF"),
            "duplicate": ("#0E8A16", "#1BAA27", "#0C7312"),
            "delete": ("#B62324", "#D73A49", "#9A1B1C"),
            "run": ("#238636", "#2EA043", "#1D6F2C"),
            "lock": ("#57606A", "#6E7781", "#4A525B"),
        }
        normal, hover, pressed = style_map.get(button_type, style_map["lock"])
        button.setStyleSheet(
            "QPushButton {"
            f"background-color: {normal};"
            "color: white;"
            "border: none;"
            "border-radius: 4px;"
            "padding: 6px 10px;"
            "font-weight: 600;"
            "}"
            "QPushButton:hover {"
            f"background-color: {hover};"
            "}"
            "QPushButton:pressed {"
            f"background-color: {pressed};"
            "}"
            "QPushButton:disabled {"
            "background-color: #3B3B3B;"
            "color: #999999;"
            "}"
        )

    def _on_tab_changed(self, index: int) -> None:
        """Refresh Cues tab state when tab is selected."""
        if self.tab_widget.widget(index) != self.cues_tab:
            return

        self._refresh_cues_table()

    def _refresh_cues_table(self) -> None:
        """Rebuild cue table from cue storage and camera/preset state."""
        from PyQt6.QtWidgets import QComboBox, QTableWidgetItem

        if not self.cues_table:
            return

        loaded_camera_ids = [
            camera.get("id")
            for camera in self.config.get_cameras()
            if isinstance(camera.get("id"), str) and camera.get("id")
        ]
        self._cue_camera_columns = self.cue_manager.sync_camera_columns(loaded_camera_ids)

        headers = [UIStrings.CUE_COL_NUMBER, UIStrings.CUE_COL_NAME]
        headers.extend(
            UIStrings.CUE_COL_CAMERA.format(index=index + 1)
            for index in range(len(self._cue_camera_columns))
        )

        self._cue_table_updating = True
        self.cues_table.blockSignals(True)
        self.cues_table.setColumnCount(len(headers))
        self.cues_table.setHorizontalHeaderLabels(headers)

        for index, camera_id in enumerate(self._cue_camera_columns):
            camera_label = self._get_camera_display_name(camera_id)
            header_item = self.cues_table.horizontalHeaderItem(index + 2)
            if header_item:
                header_item.setToolTip(camera_label)

        cues = self.cue_manager.get_cues()
        self.cues_table.setRowCount(len(cues))

        row_labels: list[str] = []

        for row_index, cue in enumerate(cues):
            cue_id = cue.get("id", "")
            cue_number = str(cue.get("cue_number", ""))
            cue_name = str(cue.get("name", UIStrings.CUE_DEFAULT_NAME))

            row_bg = QBrush()
            row_fg = QBrush()
            if cue_id == self._last_run_cue_id:
                row_bg = QBrush(QColor("#7A1F1F"))
                row_fg = QBrush(QColor("#FFFFFF"))
            elif cue_id == self._armed_cue_id:
                row_bg = QBrush(QColor("#1F6A3A"))
                row_fg = QBrush(QColor("#FFFFFF"))

            row_number_text = str(row_index + 1)
            if cue_id == self._armed_cue_id:
                row_number_text = f"{UIStrings.CUE_ARMED_MARKER} {row_number_text}"
            row_labels.append(row_number_text)

            cue_item = QTableWidgetItem(cue_number)
            cue_item.setData(Qt.ItemDataRole.UserRole, cue_id)
            if self._cue_table_locked:
                cue_item.setFlags(cue_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            cue_item.setBackground(row_bg)
            cue_item.setForeground(row_fg)
            self.cues_table.setItem(row_index, 0, cue_item)

            name_item = QTableWidgetItem(cue_name)
            name_item.setData(Qt.ItemDataRole.UserRole, cue_id)
            if self._cue_table_locked:
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setBackground(row_bg)
            name_item.setForeground(row_fg)
            self.cues_table.setItem(row_index, 1, name_item)

            for column_index, camera_id in enumerate(self._cue_camera_columns):
                combo = QComboBox()
                combo.addItem("", None)
                for preset in self.config.get_presets(camera_id):
                    preset_uuid = preset.get("uuid")
                    preset_name = preset.get("name", UIStrings.CUE_MISSING_PRESET)
                    preset_number = preset.get("preset_number", 0)
                    combo.addItem(f"[{preset_number}] {preset_name}", preset_uuid)

                selected_preset_uuid = self.cue_manager.get_preset_for_camera(cue_id, camera_id)
                if selected_preset_uuid:
                    for option_index in range(combo.count()):
                        if combo.itemData(option_index) == selected_preset_uuid:
                            combo.setCurrentIndex(option_index)
                            break

                combo.currentIndexChanged.connect(
                    lambda _index, cid=cue_id, cam_id=camera_id, cmb=combo: (
                        self._on_cue_preset_changed(cid, cam_id, cmb.currentData())
                    )
                )
                combo.setEnabled(not self._cue_table_locked)
                if cue_id == self._last_run_cue_id:
                    combo.setStyleSheet(
                        "QComboBox { background-color: #7A1F1F; color: white; border: 1px solid #9F3A3A; }"
                    )
                elif cue_id == self._armed_cue_id:
                    combo.setStyleSheet(
                        "QComboBox { background-color: #1F6A3A; color: white; border: 1px solid #2B8A4C; }"
                    )
                else:
                    combo.setStyleSheet("")
                self.cues_table.setCellWidget(row_index, column_index + 2, combo)

        self.cues_table.setVerticalHeaderLabels(row_labels)
        self.cues_table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        self.cues_table.blockSignals(False)
        self._cue_table_updating = False
        self._update_cue_controls_state()
        self._update_cue_header_highlight()

    def _update_cue_header_highlight(self) -> None:
        """Highlight cue table camera column that matches selected camera."""
        if not self.cues_table:
            return

        selected_camera_id = None
        if 0 <= self.selected_camera_index < len(self.cameras):
            selected_camera_id = self.cameras[self.selected_camera_index].camera_id

        highlighted_section = -1
        disconnected_sections: set[int] = set()
        for column_index, camera_id in enumerate(self._cue_camera_columns):
            header_item = self.cues_table.horizontalHeaderItem(column_index + 2)
            if not header_item:
                continue

            base_text = UIStrings.CUE_COL_CAMERA.format(index=column_index + 1)
            header_item.setText(base_text)

            camera_widget = self._get_camera_widget_by_id(camera_id)
            if camera_widget and not camera_widget.is_connected:
                disconnected_sections.add(column_index + 2)

            if selected_camera_id and camera_id == selected_camera_id:
                highlighted_section = column_index + 2

        if self.cues_header:
            self.cues_header.set_highlighted_section(highlighted_section)
            self.cues_header.set_disconnected_sections(disconnected_sections)

    def _on_cue_preset_changed(self, cue_id: str, camera_id: str, preset_uuid: str | None) -> None:
        """Persist selected preset for a camera column in one cue row."""
        if self._cue_table_updating or self._cue_table_locked:
            return
        self.cue_manager.update_camera_preset(cue_id, camera_id, preset_uuid)

    def _update_cue_controls_state(self) -> None:
        """Apply lock/unlock state to cue controls and table editing."""
        from PyQt6.QtWidgets import QAbstractItemView

        if self.cues_table:
            if self._cue_table_locked:
                self.cues_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            else:
                self.cues_table.setEditTriggers(
                    QAbstractItemView.EditTrigger.DoubleClicked
                    | QAbstractItemView.EditTrigger.EditKeyPressed
                    | QAbstractItemView.EditTrigger.AnyKeyPressed
                )

        edit_enabled = not self._cue_table_locked
        if self.cue_add_button:
            self.cue_add_button.setEnabled(edit_enabled)
        if self.cue_delete_button:
            self.cue_delete_button.setEnabled(edit_enabled)
        if self.cue_duplicate_button:
            self.cue_duplicate_button.setEnabled(edit_enabled)
        if self.cue_insert_button:
            self.cue_insert_button.setEnabled(edit_enabled)

        if self.cue_lock_button:
            if self._cue_table_locked:
                self.cue_lock_button.setText(UIStrings.BTN_LOCK)
                self.cue_lock_button.setToolTip(UIStrings.TOOLTIP_CUE_LOCKED)
            else:
                self.cue_lock_button.setText(UIStrings.BTN_UNLOCK)
                self.cue_lock_button.setToolTip(UIStrings.TOOLTIP_CUE_UNLOCKED)

    def _toggle_cue_lock(self) -> None:
        """Toggle lock state for cue table editing."""
        self._cue_table_locked = not self._cue_table_locked
        self._refresh_cues_table()

    def _get_cue_id_for_row(self, row: int) -> str | None:
        """Get cue ID from table row metadata."""
        if not self.cues_table:
            return None

        cue_item = self.cues_table.item(row, 0)
        if not cue_item:
            return None

        cue_id = cue_item.data(Qt.ItemDataRole.UserRole)
        return cue_id if isinstance(cue_id, str) and cue_id else None

    def _on_cue_table_cell_changed(self, row: int, column: int) -> None:
        """Handle cue/Name text cell edits and persist changes."""
        if self._cue_table_updating or self._cue_table_locked or not self.cues_table:
            return

        cue_id = self._get_cue_id_for_row(row)
        if not cue_id:
            return

        item = self.cues_table.item(row, column)
        if not item:
            return

        value = item.text().strip()

        if column == 0:
            if not re.fullmatch(r"\d+(\.\d+)?", value):
                QMessageBox.warning(self, UIStrings.TAB_CUES, UIStrings.CUE_INVALID_NUMBER)
                existing_cue = self.cue_manager.get_cue_by_id(cue_id)
                previous_value = str(existing_cue.get("cue_number", "")) if existing_cue else ""
                self._cue_table_updating = True
                item.setText(previous_value)
                self._cue_table_updating = False
                return

            self.cue_manager.update_cue_field(cue_id, "cue_number", value)
            self._refresh_cues_table()
            return

        if column == 1:
            if not value:
                value = UIStrings.CUE_DEFAULT_NAME
                self._cue_table_updating = True
                item.setText(value)
                self._cue_table_updating = False
            self.cue_manager.update_cue_field(cue_id, "name", value)
            self._refresh_cues_table()

    def _on_cue_row_header_double_clicked(self, row: int) -> None:
        """Arm cue row when user double-clicks the row header index."""
        cue_id = self._get_cue_id_for_row(row)
        if not cue_id:
            return

        self._armed_cue_id = cue_id
        self._refresh_cues_table()

    def _add_cue_row(self) -> None:
        """Add a new empty cue row."""
        if self._cue_table_locked:
            return

        cue_number = str(len(self.cue_manager.get_cues()) + 1)
        self.cue_manager.add_cue(
            cue_number=cue_number,
            name=UIStrings.CUE_DEFAULT_NAME,
            camera_columns=self._cue_camera_columns,
        )
        if self._armed_cue_id is None:
            cues = self.cue_manager.get_cues()
            if cues:
                self._armed_cue_id = cues[0].get("id")
        self._refresh_cues_table()

    def _get_selected_cue_row(self) -> int | None:
        """Return selected cue row index, if any."""
        if not self.cues_table:
            return None

        selected_ranges = self.cues_table.selectedRanges()
        if not selected_ranges:
            return None

        return selected_ranges[0].topRow()

    def _delete_selected_cue_row(self) -> None:
        """Delete currently selected cue row."""
        if self._cue_table_locked or not self.cues_table:
            return

        selected_row = self._get_selected_cue_row()
        if selected_row is None:
            return

        cue_id = self._get_cue_id_for_row(selected_row)
        if not cue_id:
            return

        cue = self.cue_manager.get_cue_by_id(cue_id)
        cue_name = (
            cue.get("name", UIStrings.CUE_DEFAULT_NAME) if cue else UIStrings.CUE_DEFAULT_NAME
        )

        reply = QMessageBox.question(
            self,
            UIStrings.DIALOG_DELETE_CUE,
            UIStrings.CUE_DELETE_CONFIRM.format(name=cue_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes and self.cue_manager.remove_cue(cue_id):
            if self._armed_cue_id == cue_id:
                self._armed_cue_id = None
            if self._last_run_cue_id == cue_id:
                self._last_run_cue_id = None
            self._refresh_cues_table()

    def _duplicate_selected_cue_row(self) -> None:
        """Duplicate selected cue row and insert after it."""
        if self._cue_table_locked:
            return

        selected_row = self._get_selected_cue_row()
        if selected_row is None:
            return

        cue_id = self._get_cue_id_for_row(selected_row)
        if not cue_id:
            return

        inserted_id = self.cue_manager.duplicate_cue_at(
            cue_id=cue_id,
            index=selected_row + 1,
            camera_columns=self._cue_camera_columns,
        )
        if inserted_id:
            if self._armed_cue_id is None:
                self._armed_cue_id = inserted_id
            self._refresh_cues_table()

    def _insert_cue_row_after_selected(self) -> None:
        """Insert cue row after selected with cue number +0.1."""
        if self._cue_table_locked:
            return

        selected_row = self._get_selected_cue_row()
        if selected_row is None:
            return

        cue_id = self._get_cue_id_for_row(selected_row)
        if not cue_id:
            return

        selected_cue = self.cue_manager.get_cue_by_id(cue_id)
        cue_number = ""
        if selected_cue:
            selected_number = str(selected_cue.get("cue_number", "")).strip()
            try:
                inserted_number = Decimal(selected_number) + Decimal("0.1")
                cue_number = format(inserted_number, "f").rstrip("0").rstrip(".")
            except (InvalidOperation, ValueError):
                cue_number = str(len(self.cue_manager.get_cues()) + 1)

        if not cue_number:
            cue_number = str(len(self.cue_manager.get_cues()) + 1)

        self.cue_manager.insert_cue_at(
            index=selected_row + 1,
            cue_number=cue_number,
            name=UIStrings.CUE_DEFAULT_NAME,
            camera_columns=self._cue_camera_columns,
        )
        self._refresh_cues_table()

    def _get_row_by_cue_id(self, cue_id: str) -> int | None:
        """Find table row index by cue ID."""
        if not self.cues_table:
            return None

        for row in range(self.cues_table.rowCount()):
            row_cue_id = self._get_cue_id_for_row(row)
            if row_cue_id == cue_id:
                return row
        return None

    def _advance_armed_cue(self) -> None:
        """Advance armed cue marker to next row (wrap to first)."""
        cues = self.cue_manager.get_cues()
        if not cues:
            self._armed_cue_id = None
            return

        cue_ids = [cue.get("id") for cue in cues if cue.get("id")]
        if not cue_ids:
            self._armed_cue_id = None
            return

        if self._armed_cue_id not in cue_ids:
            self._armed_cue_id = cue_ids[0]
            return

        current_index = cue_ids.index(self._armed_cue_id)
        next_index = (current_index + 1) % len(cue_ids)
        self._armed_cue_id = cue_ids[next_index]

    def _get_camera_widget_by_id(self, camera_id: str) -> CameraWidget | None:
        """Find loaded camera widget by camera ID."""
        for camera in self.cameras:
            if camera.camera_id == camera_id:
                return camera
        return None

    def _run_selected_cue_row(self) -> None:
        """Run armed cue row across mapped camera columns."""
        cue_id = self._armed_cue_id
        if not cue_id:
            selected_row = self._get_selected_cue_row()
            if selected_row is not None:
                cue_id = self._get_cue_id_for_row(selected_row)
            if not cue_id:
                cues = self.cue_manager.get_cues()
                cue_id = cues[0].get("id") if cues else None
            self._armed_cue_id = cue_id

        if not cue_id:
            return

        cue = self.cue_manager.get_cue_by_id(cue_id)
        if not cue:
            return

        first_camera_to_select: CameraWidget | None = None

        for camera_id in self._cue_camera_columns:
            preset_uuid = self.cue_manager.get_preset_for_camera(cue_id, camera_id)
            if not preset_uuid:
                continue

            preset_data = self.config.get_preset_by_uuid(camera_id, preset_uuid)
            if not preset_data:
                continue

            camera_widget = self._get_camera_widget_by_id(camera_id)
            if not camera_widget or not camera_widget.is_connected:
                continue

            preset_number = preset_data.get("preset_number", 0)
            camera_widget.visca.recall_preset_position(preset_number)
            if first_camera_to_select is None:
                first_camera_to_select = camera_widget

        if first_camera_to_select and first_camera_to_select in self.cameras:
            self.select_camera_at_index(self.cameras.index(first_camera_to_select))

        self._last_run_cue_id = cue_id
        self._advance_armed_cue()
        self._refresh_cues_table()

    def _run_cue_if_cues_tab_active(self) -> None:
        """Run cue only when Cues tab is active."""
        if self.tab_widget.currentWidget() != self.cues_tab:
            return
        self._run_selected_cue_row()

    def _get_camera_display_name(self, camera_id: str) -> str:
        """Return camera display name for cues tab."""
        camera = self.config.get_camera(camera_id)
        if not camera:
            return UIStrings.CUE_MISSING_CAMERA

        ndi_name = camera.get("ndi_source_name", "")
        visca_ip = camera.get("visca_ip", "")
        return ndi_name if ndi_name else visca_ip

    def init_usb_controller(self):
        """Initialize USB controller"""
        try:
            self.usb_controller = USBController(self.config)

            # Store signal handlers for connect/disconnect when dialog opens/closes
            # We don't disconnect 'connected' and 'disconnected' as they don't affect cameras
            self._usb_signal_handlers["prev_camera"] = lambda: self.select_camera(-1)
            self._usb_signal_handlers["next_camera"] = lambda: self.select_camera(1)
            self._usb_signal_handlers["movement_direction"] = self.on_usb_movement
            self._usb_signal_handlers["zoom_in"] = self.on_usb_zoom_in
            self._usb_signal_handlers["zoom_out"] = self.on_usb_zoom_out
            self._usb_signal_handlers["zoom_stop"] = self.on_usb_zoom_stop
            self._usb_signal_handlers["stop_movement"] = self.on_usb_stop_movement
            self._usb_signal_handlers["brightness_increase"] = self.on_usb_brightness_increase
            self._usb_signal_handlers["brightness_decrease"] = self.on_usb_brightness_decrease
            self._usb_signal_handlers["focus_one_push"] = self.on_usb_focus_one_push
            self._usb_signal_handlers["run_cue"] = self._run_cue_if_cues_tab_active
            self._usb_signal_handlers["button_a_pressed"] = lambda: None  # Placeholder for dialog

            # Connect signals using UniqueConnection to prevent duplicate connections
            # This allows the preferences dialog to also connect without causing duplicates
            self.usb_controller.connected.connect(
                self.on_usb_connected, Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.disconnected.connect(
                self.on_usb_disconnected, Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.prev_camera.connect(
                self._usb_signal_handlers["prev_camera"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.next_camera.connect(
                self._usb_signal_handlers["next_camera"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.movement_direction.connect(
                self._usb_signal_handlers["movement_direction"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.zoom_in.connect(
                self._usb_signal_handlers["zoom_in"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.zoom_out.connect(
                self._usb_signal_handlers["zoom_out"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.zoom_stop.connect(
                self._usb_signal_handlers["zoom_stop"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.stop_movement.connect(
                self._usb_signal_handlers["stop_movement"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.brightness_increase.connect(
                self._usb_signal_handlers["brightness_increase"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.brightness_decrease.connect(
                self._usb_signal_handlers["brightness_decrease"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.focus_one_push.connect(
                self._usb_signal_handlers["focus_one_push"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.run_cue_requested.connect(
                self._usb_signal_handlers["run_cue"], Qt.ConnectionType.UniqueConnection
            )
            self.usb_controller.menu_button_pressed.connect(
                self.show_controller_preferences, Qt.ConnectionType.UniqueConnection
            )
            # Note: button_a_pressed is only used by preferences dialog and not connected here

            # Update UI to reflect current connection state
            if self.usb_controller.joystick is not None:
                name = self.usb_controller.joystick.get_name()
                self._update_usb_indicator(True, name)

        except (ImportError, RuntimeError, OSError) as e:
            logger.error(f"USB controller initialization error: {e}")

    def _configure_network_interface(self, camera_configs: list[dict]) -> None:
        """
        Detect and configure network interface for NDI binding.
        Called before NDI initialization to ensure consistent interface selection.
        """
        from videocue.controllers.ndi_video import set_preferred_network_interface
        from videocue.ui.network_interface_dialog import show_interface_selection_dialog
        from videocue.utils.network_interface import (
            get_network_interfaces,
            get_preferred_interface_ip,
        )

        # Step 1: Extract camera IP addresses from config (using visca_ip field)
        camera_ips = [
            cam.get("visca_ip")
            for cam in camera_configs
            if cam.get("visca_ip") and cam.get("visca_ip") != ""
        ]

        if not camera_ips:
            logger.info("[Network] No camera IPs found, using default network interface")
            return

        logger.info("[Network] Camera IPs: %s", camera_ips)

        # Step 2: Check for saved preference
        preferred_ip = self.config.get_preferred_network_interface()

        # Step 3: Auto-detect if no saved preference
        if not preferred_ip:
            logger.info("[Network] No saved preference, attempting auto-detection...")
            preferred_ip = get_preferred_interface_ip(camera_ips)

            if preferred_ip:
                logger.info("[Network] Auto-detected interface: %s", preferred_ip)
                # Save the auto-detected preference
                self.config.set_preferred_network_interface(preferred_ip)
            else:
                logger.warning("[Network] Auto-detection failed or ambiguous")

        # Step 4: Show dialog if detection failed or ambiguous
        if not preferred_ip:
            interfaces = get_network_interfaces()
            if len(interfaces) > 1:
                logger.info("[Network] Multiple interfaces detected, showing selection dialog...")
                selected = show_interface_selection_dialog(interfaces, camera_ips, self)
                if selected:
                    preferred_ip = selected.ip
                    logger.info("[Network] User selected interface: %s", preferred_ip)
                    # Save user's selection
                    self.config.set_preferred_network_interface(preferred_ip)
                else:
                    logger.warning("[Network] User cancelled interface selection")
            elif len(interfaces) == 1:
                # Only one interface, use it
                preferred_ip = interfaces[0].ip
                logger.info("[Network] Single interface detected: %s", preferred_ip)
                self.config.set_preferred_network_interface(preferred_ip)

        # Step 5: Configure NDI to use selected interface
        if preferred_ip:
            logger.info("[Network] Configuring NDI to use interface: %s", preferred_ip)
            set_preferred_network_interface(preferred_ip)
        else:
            logger.info("[Network] Using NDI default network interface selection")
            set_preferred_network_interface(None)

    def showEvent(self, event):
        """Override showEvent to load cameras after UI is visible"""
        try:
            super().showEvent(event)

            # Load cameras only once, after window is shown
            if not self._cameras_loaded:
                self._cameras_loaded = True

                # Show loading indicator immediately
                camera_configs = self.config.get_cameras()
                if len(camera_configs) > 0:
                    self._total_cameras_to_load = len(camera_configs)
                    self._cameras_initialized = 0
                    self._initialized_camera_ids.clear()
                    self._current_progress_step = 0
                    # Use 3 steps per camera for more granular progress
                    self._total_progress_steps = self._total_cameras_to_load * 3
                    self.loading_label.setText(
                        f"Preparing to load {self._total_cameras_to_load} camera(s)..."
                    )
                    self.loading_label.setVisible(True)
                    self.loading_progress.setRange(0, self._total_progress_steps)
                    self.loading_progress.setValue(0)
                    self.loading_progress.setVisible(True)

                # Use timer to ensure UI is fully rendered before loading cameras
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(100, self.load_cameras)
        except Exception as e:
            logger.exception("CRITICAL ERROR in showEvent")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Startup Error", f"Error during window show:\n{str(e)}")

    def load_cameras(self):
        """Load cameras from configuration"""
        try:
            camera_configs = self.config.get_cameras()

            # Detect and configure network interface BEFORE NDI initialization
            self._configure_network_interface(camera_configs)

            # Pre-discover all NDI sources once before creating camera widgets
            # This prevents each camera from doing its own 2-second discovery wait
            if camera_configs:
                from videocue.constants import NetworkConstants
                from videocue.controllers.ndi_video import (
                    discover_and_cache_all_sources,
                    ndi_available,
                )

                if ndi_available:
                    logger.info("[Startup] Pre-discovering all NDI sources...")
                    # Count expected NDI sources from config
                    expected_sources = sum(
                        1 for cam in camera_configs if cam.get("ndi_source_name")
                    )
                    logger.info(f"[Startup] Expecting {expected_sources} NDI sources...")

                    # Use extended discovery timeout and poll until all sources found
                    num_sources = discover_and_cache_all_sources(
                        timeout_ms=NetworkConstants.NDI_DISCOVERY_TIMEOUT_MS,
                        expected_count=expected_sources,
                    )
                    logger.info(f"[Startup] Cached {num_sources} NDI source(s)")

                    # Short delay after discovery to let sources fully stabilize
                    import time

                    time.sleep(0.5)  # 500ms stabilization delay
                    logger.info("[Startup] Sources stabilized, creating camera widgets...")

            # Load cameras immediately - no stagger delay
            for i, cam_config in enumerate(camera_configs, 1):
                cam_config["_init_delay"] = (
                    i - 1
                ) * 50  # First camera: 0ms, second: 50ms, third: 100ms, etc.
                self.add_camera_from_config(cam_config)
        except Exception as e:
            logger.exception("CRITICAL ERROR in load_cameras")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Camera Load Error", f"Error loading cameras:\n{str(e)}")

    def add_camera_from_config(self, cam_config: dict):
        """Add camera widget from configuration"""
        camera_num = len(self.cameras) + 1

        try:
            # Step 1: Creating widget
            self._update_loading_progress(
                f"Creating camera {camera_num}/{self._total_cameras_to_load}..."
            )

            # Get staggered init delay (set by load_cameras)
            init_delay = cam_config.get("_init_delay", 100)

            # Get video size from camera config
            video_size = cam_config.get(
                "video_size", [UIConstants.VIDEO_DEFAULT_WIDTH, UIConstants.VIDEO_DEFAULT_HEIGHT]
            )

            camera = CameraWidget(
                camera_id=cam_config["id"],
                ndi_source_name=cam_config.get("ndi_source_name", ""),
                visca_ip=cam_config["visca_ip"],
                visca_port=cam_config["visca_port"],
                config=self.config,
                init_delay=init_delay,
                video_size=video_size,
            )

            # Step 2: Configuring
            self._update_loading_progress(
                f"Configuring camera {camera_num}/{self._total_cameras_to_load}..."
            )

            # Connect delete signal
            camera.delete_requested.connect(lambda: self.remove_camera(camera))

            # Connect reorder signals
            camera.move_left_requested.connect(lambda cam=camera: self.move_camera_left(cam))
            camera.move_right_requested.connect(lambda cam=camera: self.move_camera_right(cam))
            camera.selection_requested.connect(
                lambda cam=camera: self.select_camera_at_index(self.cameras.index(cam))
            )
            camera.connection_state_changed.connect(
                lambda _connected, _cam=camera: self._update_cue_header_highlight()
            )

            # Connect initialization signals to track progress
            camera.connection_starting.connect(
                lambda: self._update_loading_progress(
                    f"Connecting to camera {camera_num}/{self._total_cameras_to_load}...",
                    increment=False,
                )
            )
            camera.initialized.connect(
                lambda cam_id=camera.camera_id: self.on_camera_initialized(cam_id)
            )

            # Add to layout (before stretch)
            self.cameras_layout.insertWidget(len(self.cameras), camera)
            self.cameras.append(camera)

            # Select first camera
            if len(self.cameras) == 1:
                self.select_camera_at_index(0)

            self._refresh_cues_table()

        except Exception as e:
            error_msg = f"Failed to load camera {camera_num}:\n{str(e)}"
            logger.error(error_msg, exc_info=True)
            QMessageBox.warning(self, "Camera Load Error", error_msg, QMessageBox.StandardButton.Ok)
            # Still increment initialized count so progress completes
            self.on_camera_initialized(cam_config.get("id"))

    def _update_loading_progress(self, message: str, increment: bool = True) -> None:
        """Update loading progress bar and message"""
        if increment:
            self._current_progress_step = min(
                self._current_progress_step + 1,
                self._total_progress_steps,
            )
        self.loading_progress.setValue(self._current_progress_step)
        self.loading_label.setText(message)

    def on_camera_initialized(self, camera_id: str | None = None):
        """Handle camera initialization completion"""
        try:
            if camera_id and camera_id in self._initialized_camera_ids:
                logger.debug("Ignoring duplicate initialized signal for camera %s", camera_id)
                return

            if camera_id:
                self._initialized_camera_ids.add(camera_id)

            self._cameras_initialized += 1
            self._update_loading_progress(
                f"Camera {self._cameras_initialized}/{self._total_cameras_to_load} ready"
            )

            # Hide progress when all cameras loaded
            if self._cameras_initialized >= self._total_cameras_to_load:
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(500, self._hide_loading_indicator)
        except Exception as e:
            logger.exception("ERROR in on_camera_initialized")
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Camera Initialization Error",
                f"Error during camera initialization:\n{str(e)}",
            )

    def _hide_loading_indicator(self):
        """Hide the loading indicator"""
        try:
            logger.debug("Hiding loading indicator...")
            self.loading_label.setVisible(False)
            self.loading_progress.setVisible(False)
            logger.debug("Loading indicator hidden successfully")
        except Exception:
            logger.exception("ERROR hiding loading indicator")

    def add_camera_dialog(self):
        """Show add camera dialog"""
        # Get list of existing cameras to pass to dialog
        existing_cameras = self.config.get_cameras()
        dialog = CameraAddDialog(self, existing_cameras=existing_cameras)

        if dialog.exec():
            # Get selected cameras
            ndi_cameras = dialog.get_selected_ndi_cameras()
            manual_host_port = dialog.get_ip_address()  # Returns (host, port) tuple or None

            # Count how many cameras we're adding
            cameras_to_add = len(ndi_cameras) + (1 if manual_host_port else 0)

            if cameras_to_add > 0:
                # Show loading progress bar
                self._total_cameras_to_load = len(self.cameras) + cameras_to_add
                self._cameras_initialized = len(self.cameras)  # Already loaded cameras
                self._initialized_camera_ids = {
                    cam.camera_id
                    for cam in self.cameras
                    if hasattr(cam, "camera_id") and cam.camera_id
                }
                self._current_progress_step = len(self.cameras) * 3  # 3 steps per camera
                self._total_progress_steps = self._total_cameras_to_load * 3
                self.loading_label.setText(f"Adding {cameras_to_add} camera(s)...")
                self.loading_label.setVisible(True)
                self.loading_progress.setRange(0, self._total_progress_steps)
                self.loading_progress.setValue(self._current_progress_step)
                self.loading_progress.setVisible(True)

            # Add NDI cameras
            for ndi_name in ndi_cameras:
                # Try to match existing config or extract IP from NDI name
                existing = self.config.get_camera_by_ndi_name(ndi_name)

                if existing:
                    # Already configured, reload
                    self.add_camera_from_config(existing)
                else:
                    # New camera - extract IP from NDI name
                    visca_ip = self.extract_ip_from_ndi_name(ndi_name)

                    # Add to config
                    camera_id = self.config.add_camera(ndi_source_name=ndi_name, visca_ip=visca_ip)

                    # Get config and add widget
                    cam_config = self.config.get_camera(camera_id)
                    if cam_config:
                        self.add_camera_from_config(cam_config)

            # Add IP-only camera (manual host/port entry)
            if manual_host_port:
                host, port = manual_host_port
                camera_id = self.config.add_camera(
                    ndi_source_name="", visca_ip=host, visca_port=port
                )

                cam_config = self.config.get_camera(camera_id)
                if cam_config:
                    self.add_camera_from_config(cam_config)

            self._refresh_cues_table()

    def extract_ip_from_ndi_name(self, ndi_name: str) -> str:
        """Extract IP address from NDI source name (format: 'Name (IP)')"""
        if "(" in ndi_name and ")" in ndi_name:
            start = ndi_name.index("(") + 1
            end = ndi_name.index(")")
            return ndi_name[start:end].strip()
        return ""

    def remove_camera(self, camera: "CameraWidget"):
        """Remove camera widget with confirmation"""
        # Show confirmation dialog
        from PyQt6.QtWidgets import QMessageBox

        camera_name = camera.ndi_source_name if camera.ndi_source_name else camera.visca_ip
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete camera:\n{camera_name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        if camera in self.cameras:
            # Stop video and cleanup threads explicitly before deletion
            camera.stop_video()
            camera.cleanup()

            # Remove from config
            self.config.remove_camera(camera.camera_id)

            # Remove from layout and list
            self.cameras_layout.removeWidget(camera)
            self.cameras.remove(camera)
            camera.deleteLater()

            # Reselect camera if needed
            if len(self.cameras) > 0:
                self.selected_camera_index = min(self.selected_camera_index, len(self.cameras) - 1)
                self.select_camera_at_index(self.selected_camera_index)

            self._refresh_cues_table()

    def move_camera_left(self, camera: "CameraWidget"):
        """Move camera one position to the left"""
        if camera not in self.cameras:
            return

        index = self.cameras.index(camera)
        if index > 0:
            # Swap in list
            self.cameras[index], self.cameras[index - 1] = (
                self.cameras[index - 1],
                self.cameras[index],
            )

            # Update layout
            self._rebuild_camera_layout()

            # Update config order
            self._save_camera_order()

            # Update selection index if needed
            if self.selected_camera_index == index:
                self.selected_camera_index = index - 1
            elif self.selected_camera_index == index - 1:
                self.selected_camera_index = index

    def move_camera_right(self, camera: "CameraWidget"):
        """Move camera one position to the right"""
        if camera not in self.cameras:
            return

        index = self.cameras.index(camera)
        if index < len(self.cameras) - 1:
            # Swap in list
            self.cameras[index], self.cameras[index + 1] = (
                self.cameras[index + 1],
                self.cameras[index],
            )

            # Update layout
            self._rebuild_camera_layout()

            # Update config order
            self._save_camera_order()

            # Update selection index if needed
            if self.selected_camera_index == index:
                self.selected_camera_index = index + 1
            elif self.selected_camera_index == index + 1:
                self.selected_camera_index = index

    def _rebuild_camera_layout(self):
        """Rebuild the camera layout to reflect current order"""
        # Remove all cameras from layout
        for camera in self.cameras:
            self.cameras_layout.removeWidget(camera)

        # Re-add in current order (before the stretch)
        for i, camera in enumerate(self.cameras):
            self.cameras_layout.insertWidget(i, camera)

    def _save_camera_order(self):
        """Save the current camera order to config"""
        # Reorder cameras in config to match current order
        camera_ids = [camera.camera_id for camera in self.cameras]
        self.config.reorder_cameras(camera_ids)
        self.config.save()

    def select_camera(self, offset: int):
        """Select camera by offset from current"""
        if len(self.cameras) == 0:
            return

        new_index = (self.selected_camera_index + offset) % len(self.cameras)
        self.select_camera_at_index(new_index)

    def select_camera_at_index(self, index: int):
        """Select camera at specific index"""
        if index < 0 or index >= len(self.cameras):
            return

        # Stop previous camera if enabled
        usb_config = self.config.get_usb_controller_config()
        stop_on_switch = usb_config.get("stop_on_camera_switch", True)

        if stop_on_switch and 0 <= self.selected_camera_index < len(self.cameras):
            previous_camera = self.cameras[self.selected_camera_index]
            if previous_camera.is_connected:
                try:
                    previous_camera.stop_camera()
                except Exception as e:
                    logger.warning(f"Failed to stop previous camera: {e}")

        # Deselect all
        for cam in self.cameras:
            cam.set_selected(False)

        # Select target
        self.selected_camera_index = index
        self.cameras[index].set_selected(True)
        self._update_cue_header_highlight()

    def get_selected_camera(self) -> "CameraWidget | None":
        """Get currently selected camera"""
        if 0 <= self.selected_camera_index < len(self.cameras):
            return self.cameras[self.selected_camera_index]
        return None

    def _update_usb_indicator(self, connected: bool, name: str = ""):
        """Update USB controller visual indicator"""
        if connected:
            self.usb_icon_label.setText("\U0001f3ae\ufe0e")
            self.usb_icon_label.setStyleSheet("color: #00FF00; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                f"<span style='font-size: 10pt;'>Controller: {name}<br>Click for settings</span>"
            )
        else:
            self.usb_icon_label.setText("\U0001f3ae\ufe0e")
            self.usb_icon_label.setStyleSheet("color: #FF0000; font-size: 20px;")
            self.usb_icon_label.setToolTip(
                "<span style='font-size: 10pt;'>No controller connected<br>Click for settings</span>"
            )

    @pyqtSlot(str)
    def on_usb_connected(self, name: str) -> None:
        """Handle USB controller connected"""
        try:
            self._update_usb_indicator(True, name)
            self.config.set_usb_controller_name(name)
            logger.info(f"USB Controller connected: {name}")
        except Exception:
            logger.exception("Error handling USB connection")

    @pyqtSlot()
    def on_usb_disconnected(self) -> None:
        """Handle USB controller disconnected"""
        try:
            self._update_usb_indicator(False)
            logger.info("USB Controller disconnected")
        except Exception:
            logger.exception("Error handling USB disconnection")

    @pyqtSlot(object, float)
    def on_usb_movement(self, direction: MovementDirection, speed: float):
        """Handle USB controller movement"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_movement(direction, speed)
        except Exception:
            logger.exception("Error handling USB movement")

    @pyqtSlot(float)
    def on_usb_zoom_in(self, speed: float):
        """Handle USB controller zoom in"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_in(speed)
        except Exception:
            logger.exception("Error handling USB zoom in")

    @pyqtSlot(float)
    def on_usb_zoom_out(self, speed: float):
        """Handle USB controller zoom out"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_out(speed)
        except Exception:
            logger.exception("Error handling USB zoom out")

    @pyqtSlot()
    def on_usb_stop_movement(self):
        """Handle USB controller stop movement"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_stop()
        except Exception:
            logger.exception("Error handling USB stop")

    @pyqtSlot()
    def on_usb_zoom_stop(self):
        """Handle USB controller zoom stop"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_zoom_stop()
        except Exception:
            logger.exception("Error handling USB zoom stop")

    @pyqtSlot()
    def on_usb_brightness_increase(self) -> None:
        """Handle USB controller brightness increase"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_increase()
        except Exception:
            logger.exception("Error handling USB brightness increase")

    @pyqtSlot()
    def on_usb_brightness_decrease(self) -> None:
        """Handle USB controller brightness decrease"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.handle_usb_brightness_decrease()
        except Exception:
            logger.exception("Error handling USB brightness decrease")

    @pyqtSlot()
    @pyqtSlot()
    def on_usb_reconnect(self) -> None:
        """Handle reconnect request from USB controller"""
        try:
            camera = self.get_selected_camera()
            if camera and not camera.is_connected:
                camera.reconnect_camera()
        except Exception:
            logger.exception("Error handling USB reconnect")

    @pyqtSlot()
    def on_usb_focus_one_push(self) -> None:
        """Handle one-push autofocus from USB controller (B button)"""
        try:
            camera = self.get_selected_camera()
            if camera and camera.is_connected:
                camera.on_one_push_af()
        except Exception:
            logger.exception("Error handling USB one-push autofocus")

    def on_video_size_changed(self, size: VideoSize) -> None:
        """Handle video size menu selection"""
        try:
            # Update default preference
            self.config.set_default_video_size(size.width, size.height)

            # Update all cameras
            for camera in self.cameras:
                camera.set_video_size(size.width, size.height)
        except Exception:
            logger.exception("Error changing video size")

    def on_bandwidth_changed(self, bandwidth: str) -> None:
        """Handle NDI bandwidth menu selection"""
        try:
            # Update preference
            self.config.set_ndi_bandwidth(bandwidth)

            # Restart active videos to apply new bandwidth setting
            self._restart_active_video_streams()

            logger.info(f"NDI bandwidth set to {bandwidth}")
        except Exception:
            logger.exception("Error handling bandwidth change")

    def on_color_format_changed(self, color_format: str) -> None:
        """Handle NDI color format menu selection"""
        try:
            # Update preference
            self.config.set_ndi_color_format(color_format)

            # Restart active videos to apply new color format
            self._restart_active_video_streams()

            logger.info(f"NDI color format set to {color_format}")
        except Exception:
            logger.exception("Error handling color format change")

    def on_false_color_toggled(self, enabled: bool) -> None:
        """Handle NDI false color mode toggle"""
        try:
            if enabled:
                self.config.set_ndi_waveform_enabled(False)
                self.config.set_ndi_vectorscope_enabled(False)
                self.config.set_ndi_rgb_parade_enabled(False)
                self.config.set_ndi_histogram_enabled(False)
                if self.waveform_action and self.waveform_action.isChecked():
                    self.waveform_action.blockSignals(True)
                    self.waveform_action.setChecked(False)
                    self.waveform_action.blockSignals(False)
                if self.vectorscope_action and self.vectorscope_action.isChecked():
                    self.vectorscope_action.blockSignals(True)
                    self.vectorscope_action.setChecked(False)
                    self.vectorscope_action.blockSignals(False)
                if self.rgb_parade_action and self.rgb_parade_action.isChecked():
                    self.rgb_parade_action.blockSignals(True)
                    self.rgb_parade_action.setChecked(False)
                    self.rgb_parade_action.blockSignals(False)
                if self.histogram_action and self.histogram_action.isChecked():
                    self.histogram_action.blockSignals(True)
                    self.histogram_action.setChecked(False)
                    self.histogram_action.blockSignals(False)

            # Update preference
            self.config.set_ndi_false_color_enabled(enabled)

            # Apply immediately to active streams (no restart required)
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    camera.ndi_thread.waveform_enabled = False
                    camera.ndi_thread.vectorscope_enabled = False
                    camera.ndi_thread.rgb_parade_enabled = False
                    camera.ndi_thread.histogram_enabled = False
                    camera.ndi_thread.false_color_enabled = enabled

            logger.info(f"NDI false color mode set to {enabled}")
        except Exception:
            logger.exception("Error handling false color toggle")

    def on_waveform_toggled(self, enabled: bool) -> None:
        """Handle NDI waveform scope mode toggle"""
        try:
            if enabled:
                self.config.set_ndi_false_color_enabled(False)
                self.config.set_ndi_vectorscope_enabled(False)
                self.config.set_ndi_rgb_parade_enabled(False)
                self.config.set_ndi_histogram_enabled(False)
                if self.false_color_action and self.false_color_action.isChecked():
                    self.false_color_action.blockSignals(True)
                    self.false_color_action.setChecked(False)
                    self.false_color_action.blockSignals(False)
                if self.vectorscope_action and self.vectorscope_action.isChecked():
                    self.vectorscope_action.blockSignals(True)
                    self.vectorscope_action.setChecked(False)
                    self.vectorscope_action.blockSignals(False)
                if self.rgb_parade_action and self.rgb_parade_action.isChecked():
                    self.rgb_parade_action.blockSignals(True)
                    self.rgb_parade_action.setChecked(False)
                    self.rgb_parade_action.blockSignals(False)
                if self.histogram_action and self.histogram_action.isChecked():
                    self.histogram_action.blockSignals(True)
                    self.histogram_action.setChecked(False)
                    self.histogram_action.blockSignals(False)

            # Update preference
            self.config.set_ndi_waveform_enabled(enabled)

            # Apply immediately to active streams (no restart required)
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    camera.ndi_thread.false_color_enabled = False
                    camera.ndi_thread.vectorscope_enabled = False
                    camera.ndi_thread.rgb_parade_enabled = False
                    camera.ndi_thread.histogram_enabled = False
                    camera.ndi_thread.waveform_enabled = enabled

            logger.info(f"NDI waveform scope mode set to {enabled}")
        except Exception:
            logger.exception("Error handling waveform toggle")

    def on_vectorscope_toggled(self, enabled: bool) -> None:
        """Handle NDI vectorscope mode toggle"""
        try:
            if enabled:
                self.config.set_ndi_false_color_enabled(False)
                self.config.set_ndi_waveform_enabled(False)
                self.config.set_ndi_rgb_parade_enabled(False)
                self.config.set_ndi_histogram_enabled(False)
                if self.false_color_action and self.false_color_action.isChecked():
                    self.false_color_action.blockSignals(True)
                    self.false_color_action.setChecked(False)
                    self.false_color_action.blockSignals(False)
                if self.waveform_action and self.waveform_action.isChecked():
                    self.waveform_action.blockSignals(True)
                    self.waveform_action.setChecked(False)
                    self.waveform_action.blockSignals(False)
                if self.rgb_parade_action and self.rgb_parade_action.isChecked():
                    self.rgb_parade_action.blockSignals(True)
                    self.rgb_parade_action.setChecked(False)
                    self.rgb_parade_action.blockSignals(False)
                if self.histogram_action and self.histogram_action.isChecked():
                    self.histogram_action.blockSignals(True)
                    self.histogram_action.setChecked(False)
                    self.histogram_action.blockSignals(False)

            # Update preference
            self.config.set_ndi_vectorscope_enabled(enabled)

            # Apply immediately to active streams (no restart required)
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    camera.ndi_thread.false_color_enabled = False
                    camera.ndi_thread.waveform_enabled = False
                    camera.ndi_thread.rgb_parade_enabled = False
                    camera.ndi_thread.histogram_enabled = False
                    camera.ndi_thread.vectorscope_enabled = enabled

            logger.info(f"NDI vectorscope mode set to {enabled}")
        except Exception:
            logger.exception("Error handling vectorscope toggle")

    def on_rgb_parade_toggled(self, enabled: bool) -> None:
        """Handle NDI RGB parade scope mode toggle"""
        try:
            if enabled:
                self.config.set_ndi_false_color_enabled(False)
                self.config.set_ndi_waveform_enabled(False)
                self.config.set_ndi_vectorscope_enabled(False)
                self.config.set_ndi_histogram_enabled(False)
                if self.false_color_action and self.false_color_action.isChecked():
                    self.false_color_action.blockSignals(True)
                    self.false_color_action.setChecked(False)
                    self.false_color_action.blockSignals(False)
                if self.waveform_action and self.waveform_action.isChecked():
                    self.waveform_action.blockSignals(True)
                    self.waveform_action.setChecked(False)
                    self.waveform_action.blockSignals(False)
                if self.vectorscope_action and self.vectorscope_action.isChecked():
                    self.vectorscope_action.blockSignals(True)
                    self.vectorscope_action.setChecked(False)
                    self.vectorscope_action.blockSignals(False)
                if self.histogram_action and self.histogram_action.isChecked():
                    self.histogram_action.blockSignals(True)
                    self.histogram_action.setChecked(False)
                    self.histogram_action.blockSignals(False)

            # Update preference
            self.config.set_ndi_rgb_parade_enabled(enabled)

            # Apply immediately to active streams (no restart required)
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    camera.ndi_thread.false_color_enabled = False
                    camera.ndi_thread.waveform_enabled = False
                    camera.ndi_thread.vectorscope_enabled = False
                    camera.ndi_thread.histogram_enabled = False
                    camera.ndi_thread.rgb_parade_enabled = enabled

            logger.info(f"NDI RGB parade mode set to {enabled}")
        except Exception:
            logger.exception("Error handling RGB parade toggle")

    def on_histogram_toggled(self, enabled: bool) -> None:
        """Handle NDI histogram scope mode toggle"""
        try:
            if enabled:
                self.config.set_ndi_false_color_enabled(False)
                self.config.set_ndi_waveform_enabled(False)
                self.config.set_ndi_vectorscope_enabled(False)
                self.config.set_ndi_rgb_parade_enabled(False)
                if self.false_color_action and self.false_color_action.isChecked():
                    self.false_color_action.blockSignals(True)
                    self.false_color_action.setChecked(False)
                    self.false_color_action.blockSignals(False)
                if self.waveform_action and self.waveform_action.isChecked():
                    self.waveform_action.blockSignals(True)
                    self.waveform_action.setChecked(False)
                    self.waveform_action.blockSignals(False)
                if self.vectorscope_action and self.vectorscope_action.isChecked():
                    self.vectorscope_action.blockSignals(True)
                    self.vectorscope_action.setChecked(False)
                    self.vectorscope_action.blockSignals(False)
                if self.rgb_parade_action and self.rgb_parade_action.isChecked():
                    self.rgb_parade_action.blockSignals(True)
                    self.rgb_parade_action.setChecked(False)
                    self.rgb_parade_action.blockSignals(False)

            # Update preference
            self.config.set_ndi_histogram_enabled(enabled)

            # Apply immediately to active streams (no restart required)
            for camera in self.cameras:
                if camera.ndi_thread and camera.ndi_thread.isRunning():
                    camera.ndi_thread.false_color_enabled = False
                    camera.ndi_thread.waveform_enabled = False
                    camera.ndi_thread.vectorscope_enabled = False
                    camera.ndi_thread.rgb_parade_enabled = False
                    camera.ndi_thread.histogram_enabled = enabled

            logger.info(f"NDI histogram mode set to {enabled}")
        except Exception:
            logger.exception("Error handling histogram toggle")

    def _restart_active_video_streams(self) -> None:
        """Restart running camera video streams with staggered startup to reduce NDI contention."""
        active_cameras = [
            camera for camera in self.cameras if camera.ndi_thread and camera.ndi_thread.isRunning()
        ]

        if not active_cameras:
            return

        for camera in active_cameras:
            camera.stop_video()

        start_delay_ms = 120
        for index, camera in enumerate(active_cameras):
            QTimer.singleShot(start_delay_ms * (index + 1), camera.start_video)

    def on_file_logging_toggled(self, checked: bool) -> None:
        """Handle file logging preference toggle"""
        try:
            # Update preference
            if "preferences" not in self.config.config:
                self.config.config["preferences"] = {}
            self.config.config["preferences"]["file_logging_enabled"] = checked
            self.config.save()

            # Inform user that restart is required
            message = UIStrings.LOGGING_ENABLED_MSG if checked else UIStrings.LOGGING_DISABLED_MSG
            QMessageBox.information(
                self,
                UIStrings.DIALOG_RESTART_REQUIRED,
                message,
            )
            logger.info(f"File logging preference set to {checked} (restart required)")
        except Exception:
            logger.exception("Error toggling file logging preference")

    def show_about(self):
        """Show about dialog with open source components"""
        dialog = AboutDialog(self)
        dialog.exec()

    def check_for_updates(self):
        """Check for updates on GitHub"""
        try:
            logger.info("Starting update check")

            # Prevent multiple simultaneous checks
            if self._update_check_thread is not None:
                try:
                    if self._update_check_thread.isRunning():
                        logger.warning("Update check already in progress")
                        return
                except RuntimeError:
                    # Thread object was deleted, clear reference
                    logger.debug("Clearing stale thread reference")
                    self._update_check_thread = None

            # Show checking message with Cancel button
            self._update_progress_dialog = QMessageBox(self)
            self._update_progress_dialog.setWindowTitle(UIStrings.DIALOG_CHECK_UPDATES)
            self._update_progress_dialog.setWindowFlag(
                Qt.WindowType.WindowMinimizeButtonHint, False
            )
            self._update_progress_dialog.setWindowFlag(
                Qt.WindowType.WindowMaximizeButtonHint, False
            )
            self._update_progress_dialog.setText(UIStrings.UPDATE_CHECKING)
            self._update_progress_dialog.setStandardButtons(QMessageBox.StandardButton.Cancel)
            self._update_progress_dialog.setModal(False)  # Non-modal so it doesn't block UI

            # Handle cancel button
            cancel_btn = self._update_progress_dialog.button(QMessageBox.StandardButton.Cancel)
            cancel_btn.clicked.connect(self._cancel_update_check)

            self._update_progress_dialog.show()

            # Create and start worker thread
            self._update_check_thread = UpdateCheckThread(__version__)
            self._update_check_thread.update_result.connect(self._on_update_check_complete)
            self._update_check_thread.finished.connect(self._on_update_thread_finished)
            self._update_check_thread.start()

            logger.debug("Update check thread started")

        except Exception as e:
            logger.exception(f"Failed to start update check: {e}")
            import traceback

            traceback.print_exc()

            # Close progress dialog if it was created
            if self._update_progress_dialog:
                self._update_progress_dialog.close()
                self._update_progress_dialog = None

            QMessageBox.critical(
                self,
                UIStrings.UPDATE_ERROR_TITLE,
                f"Failed to check for updates: {str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _cancel_update_check(self):
        """Cancel the update check (user clicked Cancel button)"""
        logger.info("User cancelled update check")

        # Close dialog
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        # Stop thread if running
        if self._update_check_thread:
            try:
                if self._update_check_thread.isRunning():
                    logger.debug("Stopping update check thread")
                    self._update_check_thread.terminate()  # Force stop the thread
                    self._update_check_thread.wait(1000)  # Wait up to 1 second for thread to stop
            except RuntimeError:
                # Thread object was already deleted
                logger.debug("Thread already deleted during cancel")
            finally:
                self._update_check_thread = None

    def _on_update_thread_finished(self):
        """Handle update check thread completion (cleanup)"""
        logger.debug("Update check thread finished")
        if self._update_check_thread:
            self._update_check_thread.deleteLater()
            self._update_check_thread = None

    def _on_update_check_complete(self, success: bool, data):
        """Handle update check completion (slot for UpdateCheckThread signal)"""
        try:
            # Close progress dialog (only if still open)
            if self._update_progress_dialog:
                self._update_progress_dialog.close()
                self._update_progress_dialog = None

            if not success:
                logger.warning(f"Update check failed: {data}")
                QMessageBox.warning(
                    self,
                    UIStrings.UPDATE_ERROR_TITLE,
                    UIStrings.UPDATE_ERROR,
                    QMessageBox.StandardButton.Ok,
                )
                return

            # Parse version from tag_name (e.g., "v0.5.1" -> "0.5.1")
            latest_version = data.get("tag_name", "").lstrip("v")
            current_version = __version__

            logger.info(
                f"Update check complete. Current: {current_version}, Latest: {latest_version}"
            )

            if self._is_newer_version(latest_version, current_version):
                # Show update available dialog
                reply = QMessageBox.question(
                    self,
                    UIStrings.UPDATE_AVAILABLE,
                    UIStrings.UPDATE_AVAILABLE_MSG.format(
                        current=current_version, latest=latest_version
                    ),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    # Open releases page in browser
                    url = data.get("html_url", "https://github.com/jpwalters/VideoCue/releases")
                    logger.info(f"Opening release URL: {url}")
                    QDesktopServices.openUrl(QUrl(url))
            else:
                # Already on latest version
                QMessageBox.information(
                    self,
                    UIStrings.DIALOG_CHECK_UPDATES,
                    UIStrings.UPDATE_NOT_AVAILABLE.format(version=current_version),
                    QMessageBox.StandardButton.Ok,
                )

        except Exception as e:
            logger.exception(f"Error handling update check result: {e}")
            import traceback

            traceback.print_exc()
            QMessageBox.critical(
                self,
                UIStrings.UPDATE_ERROR_TITLE,
                f"Error processing update information: {str(e)}",
                QMessageBox.StandardButton.Ok,
            )

    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Compare version strings (e.g., '0.5.1' vs '0.4.1')"""
        try:
            latest_parts = [int(x) for x in latest.split(".")]
            current_parts = [int(x) for x in current.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))

            return latest_parts > current_parts
        except (ValueError, AttributeError):
            return False

    def show_controller_preferences(self):
        """Show controller preferences dialog (non-modal, stays open)"""
        from videocue.ui.preferences_dialog import PreferencesDialog

        logger.info(
            f"show_controller_preferences called. dialog_open={self._preferences_dialog_open}"
        )

        # If dialog is already open, ignore this menu button press (prevents multiple windows)
        if self._preferences_dialog_open:
            logger.info("Dialog already open, ignoring menu press")
            return

        # Mark dialog as open
        self._preferences_dialog_open = True
        logger.info("Opening preferences dialog")

        # Disconnect ONLY the main window's camera control handlers while dialog is open
        # This prevents camera movement while adjusting preferences
        # Disconnect specific handlers (not all handlers) to be safe
        logger.debug("Disconnecting main window camera control handlers")
        if self.usb_controller and self._usb_signal_handlers:
            try:
                self.usb_controller.prev_camera.disconnect(self._usb_signal_handlers["prev_camera"])
                self.usb_controller.next_camera.disconnect(self._usb_signal_handlers["next_camera"])
                self.usb_controller.movement_direction.disconnect(
                    self._usb_signal_handlers["movement_direction"]
                )
                self.usb_controller.zoom_in.disconnect(self._usb_signal_handlers["zoom_in"])
                self.usb_controller.zoom_out.disconnect(self._usb_signal_handlers["zoom_out"])
                self.usb_controller.zoom_stop.disconnect(self._usb_signal_handlers["zoom_stop"])
                self.usb_controller.stop_movement.disconnect(
                    self._usb_signal_handlers["stop_movement"]
                )
                self.usb_controller.brightness_increase.disconnect(
                    self._usb_signal_handlers["brightness_increase"]
                )
                self.usb_controller.brightness_decrease.disconnect(
                    self._usb_signal_handlers["brightness_decrease"]
                )
                self.usb_controller.focus_one_push.disconnect(
                    self._usb_signal_handlers["focus_one_push"]
                )
                self.usb_controller.run_cue_requested.disconnect(
                    self._usb_signal_handlers["run_cue"]
                )
                logger.debug("Successfully disconnected all main window camera control handlers")
            except TypeError as e:
                logger.warning(f"Some handlers were already disconnected: {e}")

        # Always create fresh dialog
        logger.debug(f"Creating dialog with usb_controller={self.usb_controller}")
        self.preferences_dialog = PreferencesDialog(self.config, self, self.usb_controller)

        # Connect finished signal to reset flag when dialog closes
        self.preferences_dialog.finished.connect(self._on_preferences_dialog_closed)

        logger.debug("Dialog created, calling show() - ready for input")

        # Use show() instead of exec() so signals are processed while dialog is visible
        self.preferences_dialog.show()

    def _on_preferences_dialog_closed(self):
        """Called when preferences dialog is closed - reconnect camera control handlers"""
        logger.info("Preferences dialog closed, scheduling handler reconnection")

        # Add a small delay before reconnecting handlers to allow any pending button events
        # from the dialog close action (e.g., A button press) to fully complete.
        # This prevents the close button from triggering camera commands.
        QTimer.singleShot(150, self._reconnect_usb_handlers)

        self._preferences_dialog_open = False

    def _reconnect_usb_handlers(self):
        """Reconnect USB controller handlers after preferences dialog closes"""
        logger.debug("Reconnecting main window camera control handlers (after delay)")

        # Reconnect main window camera control handlers using UniqueConnection
        # UniqueConnection can raise TypeError if connection already exists, so we handle it gracefully
        if self.usb_controller and self._usb_signal_handlers:
            # Helper to safely reconnect with UniqueConnection
            def safe_connect(signal, handler, name=""):
                try:
                    signal.connect(handler, Qt.ConnectionType.UniqueConnection)
                except TypeError as e:
                    if "unique" in str(e).lower():
                        logger.debug(f"Connection for {name} already exists (safe to ignore)")
                    else:
                        logger.warning(f"Unexpected error reconnecting {name}: {e}")

            safe_connect(
                self.usb_controller.prev_camera,
                self._usb_signal_handlers["prev_camera"],
                "prev_camera",
            )
            safe_connect(
                self.usb_controller.next_camera,
                self._usb_signal_handlers["next_camera"],
                "next_camera",
            )
            safe_connect(
                self.usb_controller.movement_direction,
                self._usb_signal_handlers["movement_direction"],
                "movement_direction",
            )
            safe_connect(
                self.usb_controller.zoom_in, self._usb_signal_handlers["zoom_in"], "zoom_in"
            )
            safe_connect(
                self.usb_controller.zoom_out, self._usb_signal_handlers["zoom_out"], "zoom_out"
            )
            safe_connect(
                self.usb_controller.zoom_stop, self._usb_signal_handlers["zoom_stop"], "zoom_stop"
            )
            safe_connect(
                self.usb_controller.stop_movement,
                self._usb_signal_handlers["stop_movement"],
                "stop_movement",
            )
            safe_connect(
                self.usb_controller.brightness_increase,
                self._usb_signal_handlers["brightness_increase"],
                "brightness_increase",
            )
            safe_connect(
                self.usb_controller.brightness_decrease,
                self._usb_signal_handlers["brightness_decrease"],
                "brightness_decrease",
            )
            safe_connect(
                self.usb_controller.focus_one_push,
                self._usb_signal_handlers["focus_one_push"],
                "focus_one_push",
            )
            safe_connect(
                self.usb_controller.run_cue_requested,
                self._usb_signal_handlers["run_cue"],
                "run_cue",
            )
            logger.debug("Successfully reconnected all main window camera control handlers")

    def closeEvent(self, event) -> None:
        """Handle window close event"""
        logger.info("Closing application and cleaning up threads...")

        # Save configuration
        try:
            self.config.save()
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config on close: {e}")

        # Stop all cameras asynchronously
        logger.info(f"Stopping {len(self.cameras)} camera threads...")
        for camera in self.cameras:
            camera._cleanup_threads()  # Stop all camera threads
            camera.stop_retry_mechanism()  # Stop any retry timers

        # Stop USB controller timers
        if self.usb_controller:
            self.usb_controller.poll_timer.stop()
            self.usb_controller.hotplug_timer.stop()
            logger.info("USB controller timers stopped")

        # Cleanup NDI global resources
        try:
            cleanup_ndi()
            logger.info("NDI resources cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up NDI: {e}")

        logger.info("Cleanup complete, exiting...")
        event.accept()

        # Let Qt handle application shutdown naturally
        # No forced quit - just accept the close event
