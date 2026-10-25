"""
Capture the README screenshot (resources/VideoCue-Screenshot.png).

Starts the real MainWindow with three demo cameras showing a drawn concert scene,
an in-process ATEM simulator for tally (red PROGRAM / green PREVIEW / grey idle)
and each camera's controls scrolled to a different section, then grabs the window.

Uses a throwaway config directory, so your real VideoCue config is never touched.
Camera IPs are in 192.0.2.0/24 (documentation range), so no real device is contacted.
Needs UDP port 9910 free (stop tools/atem_simulator.py first) and a visible desktop.

With --docs it also saves the documentation screenshots in docs/images/
(Cues tab, full camera controls, scopes, Preferences tabs, Add Camera dialog).

Usage:
    python tools/videocue_screenshot.py
    python tools/videocue_screenshot.py --docs
    python tools/videocue_screenshot.py --output %TEMP%\\shot.png
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT, REPO_ROOT / "tools"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# Load NDI before PyQt6: PyQt6's bundled older MSVC runtime crashes the NDI 6 extension otherwise
import videocue.ndi_wrapper  # noqa: E402

with contextlib.suppress(ImportError):
    videocue.ndi_wrapper._load_ndilib()

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QWidget  # noqa: E402

SCENE_W, SCENE_H = 3840, 2160
VIDEO_SIZE = [384, 216]
WINDOW_SIZE = (1272, 793)
DOCS_DIR = REPO_ROOT / "docs" / "images"
BACKGROUND = QColor("#19232D")  # qdarkstyle window colour

# (cue number, name, {camera index: preset name}) for the Cues tab screenshot
DEMO_CUES = [
    ("1", "Walk-in", {0: "Vocal MS", 1: "Full Stage", 2: "Keys Wide"}),
    ("2", "Song 1 verse", {0: "Lead Vocal CU", 1: "Stage Left", 2: "Keys CU"}),
    ("2.1", "Guitar solo", {0: "Guitar Solo", 1: "Stage Right", 2: "Drums"}),
    ("3", "Crowd sing-along", {0: "Vocal MS", 1: "Crowd", 2: "Bass"}),
    ("4", "Encore", {0: "Lead Vocal CU", 1: "Full Stage", 2: "Encore"}),
]
DEMO_LAST_RUN_CUE, DEMO_ARMED_CUE = 1, 2

DEMO_NDI_SOURCES = ["PTZ Vocal", "PTZ Wide", "BIRDDOG-P400 (CAM 4)", "BIRDDOG-P200 (CAM 5)"]

# (camera name, ATEM input name, presets, scene crop x, y, width, controls scroll position)
# Scroll: 0..1 fraction of the controls scrollbar, or "presets" to show the Presets section.
CAMERAS = [
    ("PTZ Vocal", "Vocal", ["Lead Vocal CU", "Vocal MS", "Guitar Solo"], 1240, 560, 1360, 0.0),
    ("PTZ Wide", "Wide", ["Full Stage", "Crowd", "Stage Left", "Stage Right"], 0, 0, 3840, 0.42),
    (
        "PTZ Keys",
        "Keys",
        ["Keys CU", "Keys Wide", "Drums", "Bass", "Encore"],
        2020,
        640,
        1500,
        "presets",
    ),
]


def write_demo_config(config_root: Path) -> None:
    cameras = []
    for i, (name, _input, presets, *_rest) in enumerate(CAMERAS, 1):
        cameras.append(
            {
                "id": f"cam{i}",
                "ndi_source_name": name,
                "visca_ip": f"192.0.2.{10 + i}",
                "visca_port": 52381,
                "video_size": VIDEO_SIZE,
                "position": i - 1,
                "presets": [
                    {"uuid": str(uuid.uuid4()), "name": preset, "preset_number": n}
                    for n, preset in enumerate(presets)
                ],
                "atem_input": i,
            }
        )
    config = {
        "version": "1.0",
        "cameras": cameras,
        "preferences": {
            "video_size_default": VIDEO_SIZE,
            "ndi_video_enabled": False,
            "preferred_network_interface": "127.0.0.1",
            "single_instance_mode": False,
        },
        "usb_controller": {"enabled": True, "button_mappings": {}},
        "streamdeck": {
            "enabled": False,
            "encoder_press_enabled": True,
            "stop_sends_to_all_cameras": True,
            **{f"button_{i}_action": f"preset_{i + 1}" for i in range(4)},
            "button_4_action": "page_prev",
            "button_5_action": "stop_cue",
            "button_6_action": "run_cue",
            "button_7_action": "page_next",
            "button_5_color": "red",
            "button_6_color": "green",
        },
        "atem": {"enabled": True, "ip": "127.0.0.1", "tally_me": 0, "show_preview_tally": True},
    }
    # Windows uses %LOCALAPPDATA%\VideoCue, Unix uses ~/.config/VideoCue
    for config_dir in (config_root / "VideoCue", config_root / ".config" / "VideoCue"):
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")


def _performer(p: QPainter, cx: float, floor: float, height: float, rim: QColor, arm_up=False):
    s = height / 700
    body = QPainterPath()
    body.addEllipse(QPointF(cx, floor - 640 * s), 48 * s, 58 * s)
    torso = QPainterPath()
    torso.moveTo(cx - 95 * s, floor - 560 * s)
    for x, y in [(95, 560), (75, 300), (70, 0), (15, 0), (0, 260), (-15, 0), (-70, 0), (-75, 300)]:
        torso.lineTo(cx + x * s, floor - y * s)
    torso.closeSubpath()
    arm = QPainterPath()
    if arm_up:
        arm.addRoundedRect(QRectF(cx + 70 * s, floor - 900 * s, 40 * s, 380 * s), 18 * s, 18 * s)
    else:
        arm.addRoundedRect(QRectF(cx - 130 * s, floor - 540 * s, 40 * s, 300 * s), 18 * s, 18 * s)
    body = body.united(torso).united(arm)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(rim, 14 * s))
    p.drawPath(body)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#06030a"))
    p.drawPath(body)


def draw_concert() -> QImage:
    """Draw a stylised concert stage (LED wall, beams, band, crowd)."""
    w, h = SCENE_W, SCENE_H
    rng = random.Random(7)
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor("#07020f"))
    bg.setColorAt(0.6, QColor("#1a0830"))
    bg.setColorAt(1, QColor("#0b0414"))
    p.fillRect(0, 0, w, h, bg)

    # LED wall
    wall = QRectF(560, 260, 2720, 1060)
    led = QLinearGradient(wall.topLeft(), wall.bottomRight())
    led.setColorAt(0, QColor(255, 40, 150))
    led.setColorAt(0.5, QColor(110, 20, 255))
    led.setColorAt(1, QColor(0, 190, 255))
    p.fillRect(wall, led)
    sun = QRadialGradient(QPointF(1920, 760), 520)
    sun.setColorAt(0, QColor(255, 220, 120, 255))
    sun.setColorAt(0.35, QColor(255, 120, 60, 200))
    sun.setColorAt(1, QColor(255, 60, 120, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(sun)
    p.drawEllipse(QPointF(1920, 760), 520, 520)
    p.setPen(QPen(QColor(0, 0, 0, 120), 6))
    for x in range(int(wall.left()), int(wall.right()), 34):
        p.drawLine(x, int(wall.top()), x, int(wall.bottom()))
    for y in range(int(wall.top()), int(wall.bottom()), 34):
        p.drawLine(int(wall.left()), y, int(wall.right()), y)
    p.fillRect(wall, QColor(0, 0, 0, 70))

    # Truss and light beams (additive)
    p.fillRect(0, 110, w, 60, QColor("#141018"))
    colors = ["#ff2fa0", "#22d3ff", "#ffb020"]
    fixtures = [(x, QColor(colors[i % 3])) for i, x in enumerate(range(300, 3600, 460))]
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    p.setPen(Qt.PenStyle.NoPen)
    for i, (x, color) in enumerate(fixtures):
        target = 1920 + (x - 1920) * 0.35 + (-500 if i % 2 else 500)
        beam = QPolygonF(
            [
                QPointF(x - 18, 170),
                QPointF(x + 18, 170),
                QPointF(target + 260, 1560),
                QPointF(target - 260, 1560),
            ]
        )
        grad = QLinearGradient(0, 170, 0, 1560)
        grad.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 150))
        grad.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.setBrush(grad)
        p.drawPolygon(beam)
    for _ in range(14):
        haze = QRadialGradient(QPointF(rng.uniform(200, 3640), rng.uniform(500, 1500)), 520)
        haze.setColorAt(0, QColor(255, 255, 255, 22))
        haze.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(haze)
        p.drawRect(0, 0, w, h)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    for x, color in fixtures:
        glow = QRadialGradient(QPointF(x, 172), 70)
        glow.setColorAt(0, QColor(255, 255, 255))
        glow.setColorAt(0.3, color)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.drawEllipse(QPointF(x, 172), 70, 70)

    # Stage
    p.fillRect(0, 1540, w, 260, QColor("#120a18"))
    edge = QLinearGradient(0, 1530, 0, 1580)
    edge.setColorAt(0, QColor(255, 170, 60, 220))
    edge.setColorAt(1, QColor(255, 170, 60, 0))
    p.fillRect(0, 1530, w, 50, edge)

    # Drummer on riser
    p.setBrush(QColor("#0b0610"))
    p.drawRect(1300, 1360, 520, 180)
    for dx, r in [(1420, 90), (1560, 120), (1700, 80)]:
        p.setPen(QPen(QColor(255, 180, 90), 8))
        p.setBrush(QColor("#0a0610"))
        p.drawEllipse(QPointF(dx, 1330), r, r * 0.55)
    p.setPen(Qt.PenStyle.NoPen)
    _performer(p, 1560, 1360, 420, QColor(120, 200, 255))

    # Guitarist
    _performer(p, 1050, 1560, 720, QColor(255, 80, 180), arm_up=True)
    p.setBrush(QColor("#0a0610"))
    p.setPen(QPen(QColor(255, 80, 180), 8))
    p.drawEllipse(QPointF(1050, 1200), 95, 75)

    # Lead vocal with mic stand and floor spot
    p.setPen(QPen(QColor(200, 200, 210), 10))
    p.drawLine(1920, 1560, 1920, 1080)
    p.drawLine(1920, 1080, 1880, 1010)
    _performer(p, 1920, 1560, 760, QColor(255, 210, 120), arm_up=True)
    spot = QRadialGradient(QPointF(1920, 1560), 420)
    spot.setColorAt(0, QColor(255, 230, 170, 160))
    spot.setColorAt(1, QColor(255, 230, 170, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(spot)
    p.drawEllipse(QPointF(1920, 1560), 420, 90)

    # Keys player
    _performer(p, 2800, 1560, 700, QColor(80, 220, 255))
    p.setBrush(QColor("#0d0812"))
    p.setPen(QPen(QColor(80, 220, 255), 8))
    p.drawRect(QRectF(2580, 1200, 460, 60))
    p.drawLine(2640, 1260, 2600, 1540)
    p.drawLine(2980, 1260, 3020, 1540)
    p.setPen(Qt.PenStyle.NoPen)
    for k in range(18):
        p.setBrush(QColor(240, 240, 255) if k % 3 else QColor(30, 30, 40))
        p.drawRect(QRectF(2595 + k * 24.5, 1212, 20, 30))

    # Crowd silhouettes, raised hands and phone screens
    rows = [(1800, 0.8, "#0a0612"), (1950, 1.0, "#07040c"), (2110, 1.25, "#030206")]
    for row, (y0, scale, shade) in enumerate(rows):
        for _ in range(46 - row * 8):
            x = rng.uniform(-80, w + 80)
            y = y0 + rng.uniform(-30, 30)
            p.setBrush(QColor(shade))
            p.drawEllipse(QPointF(x, y - 120 * scale), 55 * scale, 66 * scale)
            p.drawRoundedRect(
                QRectF(x - 150 * scale, y - 60 * scale, 300 * scale, 400 * scale),
                80 * scale,
                80 * scale,
            )
            if rng.random() < 0.3:
                hx = x + rng.uniform(-60, 60) * scale
                p.setPen(QPen(QColor(shade), 34 * scale, cap=Qt.PenCapStyle.RoundCap))
                p.drawLine(
                    QPointF(x + 60 * scale, y - 40 * scale), QPointF(hx + 40, y - 420 * scale)
                )
                p.setPen(Qt.PenStyle.NoPen)
                if rng.random() < 0.4:
                    p.setBrush(QColor(200, 230, 255))
                    p.drawRoundedRect(
                        QRectF(hx + 20, y - 500 * scale, 44 * scale, 80 * scale), 6, 6
                    )

    vignette = QRadialGradient(QPointF(w / 2, h / 2), w * 0.62)
    vignette.setColorAt(0.55, QColor(0, 0, 0, 0))
    vignette.setColorAt(1, QColor(0, 0, 0, 200))
    p.setBrush(vignette)
    p.drawRect(0, 0, w, h)
    p.end()
    return img


def camera_frames(scene: QImage) -> list[QImage]:
    frames = []
    for _name, _input, _presets, x, y, width, _scroll in CAMERAS:
        crop = scene.copy(QRect(x, y, width, round(width * 9 / 16)))
        frames.append(
            crop.scaled(
                1920,
                1080,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return frames


def grab_window(widget: QWidget) -> QPixmap:
    """Grab a top-level window from the screen, including its title bar."""
    rect = widget.frameGeometry()
    return widget.screen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())


def save(image: QPixmap | QImage, name: str) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / name
    if not image.save(str(path)):
        raise RuntimeError(f"Could not save {path}")
    print(f"Saved {path.relative_to(REPO_ROOT)} ({image.width()}x{image.height()})")


def controls_scroll_area(cam) -> QScrollArea:
    return next(a for a in cam.findChildren(QScrollArea) if a.widget() is cam.controls_container)


def camera_controls_image(cam) -> QImage:
    """One camera's video header plus its whole (unscrolled) control panel in two columns."""
    area = controls_scroll_area(cam)
    header = cam.grab(QRect(0, 0, cam.width(), area.geometry().top()))
    controls = cam.controls_container.grab()
    settings_label = next(
        lbl
        for lbl in cam.controls_container.findChildren(QLabel)
        if lbl.text() == "<b>Settings</b>"
    )
    split = settings_label.y() - 4
    dpr = controls.devicePixelRatio()
    header_h = round(header.height() / dpr)
    controls_w = cam.controls_container.width()
    rest = cam.presets_container.geometry().bottom() + 8 - split
    gap, x, col_w = 24, area.geometry().left(), cam.width()
    height = max(header_h + split, rest)
    image = QImage(round((2 * col_w + gap) * dpr), round(height * dpr), QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(dpr)
    image.fill(BACKGROUND)
    p = QPainter(image)
    p.drawPixmap(0, 0, header)
    # Source rects of drawPixmap are in device pixels, target rects in logical pixels
    p.drawPixmap(
        QRectF(x, header_h, controls_w, split),
        controls,
        QRectF(0, 0, controls_w * dpr, split * dpr),
    )
    p.drawPixmap(
        QRectF(col_w + gap + x, 0, controls_w, rest),
        controls,
        QRectF(0, split * dpr, controls_w * dpr, rest * dpr),
    )
    p.end()
    return image


def scopes_image(frame: QImage) -> QImage:
    """Run the app's own scope renderers on a frame and lay the results out in a labelled grid."""
    from videocue.controllers.ndi_video import NDIVideoThread
    from videocue.ui_strings import UIStrings

    src = frame.convertToFormat(QImage.Format.Format_ARGB32)  # BGRA bytes in memory
    w, h, stride = src.width(), src.height(), src.bytesPerLine()
    data = src.constBits().asstring(src.sizeInBytes())
    renderer = NDIVideoThread("docs")
    modes = [
        (UIStrings.MENU_FALSE_COLOR, renderer._false_color_from_rgbx, None),
        (UIStrings.MENU_WAVEFORM, renderer._waveform_from_rgbx, renderer._annotate_waveform_image),
        (
            UIStrings.MENU_VECTORSCOPE,
            renderer._vectorscope_from_rgbx,
            renderer._annotate_vectorscope_image,
        ),
        (
            UIStrings.MENU_RGB_PARADE,
            renderer._rgb_parade_from_rgbx,
            renderer._annotate_rgb_parade_image,
        ),
        (
            UIStrings.MENU_HISTOGRAM,
            renderer._histogram_from_rgbx,
            renderer._annotate_histogram_image,
        ),
    ]
    tiles = [("Normal video", frame)]
    for label, convert, annotate in modes:
        rgb = convert(data, w, h, stride, is_bgra=True)
        if not rgb:
            raise RuntimeError(f"{label} renderer returned no data")
        img = QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888).copy()
        if annotate:
            annotate(img)
        tiles.append((label, img))

    tile_w, tile_h, caption, gap, cols = 512, 288, 30, 12, 3
    rows = (len(tiles) + cols - 1) // cols
    image = QImage(
        cols * tile_w + (cols + 1) * gap,
        rows * (tile_h + caption) + (rows + 1) * gap,
        QImage.Format.Format_RGB32,
    )
    image.fill(BACKGROUND)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    font = QFont()
    font.setPixelSize(16)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#DFE1E2"))
    for i, (label, img) in enumerate(tiles):
        x = gap + (i % cols) * (tile_w + gap)
        y = gap + (i // cols) * (tile_h + caption + gap)
        p.drawImage(QRect(x, y, tile_w, tile_h), img)
        p.drawText(QRect(x, y + tile_h, tile_w, caption), Qt.AlignmentFlag.AlignCenter, label)
    p.end()
    return image


def capture_docs(window, pump, frames: list[QImage]) -> None:
    from videocue.ui.camera_add_dialog import CameraAddDialog

    # Full control panel of a non-selected camera (so "Match to Selected" is enabled),
    # with Manual exposure and Manual white balance to show every slider.
    cam = window.cameras[1]
    cam.exposure_combo.blockSignals(True)
    cam.exposure_combo.setCurrentIndex(cam.exposure_combo.findData(1))
    cam.exposure_combo.blockSignals(False)
    cam.on_exposure_mode_changed(cam.exposure_combo.currentIndex(), send_command=False)
    cam.wb_combo.blockSignals(True)
    cam.wb_combo.setCurrentIndex(cam.wb_combo.findData(4))
    cam.wb_combo.blockSignals(False)
    cam.on_wb_mode_changed(cam.wb_combo.currentData(), send_command=False)
    cam.radio_autofocus.blockSignals(True)
    cam.radio_autofocus.setChecked(True)
    cam.radio_autofocus.blockSignals(False)
    pump(0.5)
    save(camera_controls_image(cam), "camera-controls.png")

    save(scopes_image(frames[1]), "scopes.png")

    # Cues tab with one cue already run (red) and the next one armed (green)
    cue_ids = []
    for number, name, picks in DEMO_CUES:
        cue_id = window.cue_manager.add_cue(number, name, window._cue_camera_columns)
        for cam_index, preset_name in picks.items():
            camera_id = window.cameras[cam_index].camera_id
            preset = next(
                p for p in window.config.get_presets(camera_id) if p["name"] == preset_name
            )
            window.cue_manager.update_camera_preset(cue_id, camera_id, preset["uuid"])
        cue_ids.append(cue_id)
    window._last_run_cue_id = cue_ids[DEMO_LAST_RUN_CUE]
    window._armed_cue_id = cue_ids[DEMO_ARMED_CUE]
    window.resize(WINDOW_SIZE[0], 420)
    window.tab_widget.setCurrentWidget(window.cues_tab)  # rebuilds the table
    window.cues_table.setColumnWidth(0, 60)
    window.cues_table.setColumnWidth(1, 220)
    for column in range(2, window.cues_table.columnCount()):
        window.cues_table.setColumnWidth(column, 200)
    window.cues_table.clearSelection()
    pump(1.0)
    save(grab_window(window), "cues-tab.png")
    window.tab_widget.setCurrentWidget(window.cameras_tab)
    window.resize(*WINDOW_SIZE)
    pump(0.5)

    # Preferences dialog, one screenshot per tab
    for index, name in [
        (0, "preferences-controller.png"),
        (1, "preferences-streamdeck.png"),
        (3, "preferences-switcher.png"),
    ]:
        window.show_controller_preferences(initial_tab=index)
        dialog = window.preferences_dialog
        dialog.resize(600, 760 if index < 2 else 420)
        dialog.move(window.pos() + QPoint(80, 20))
        if index == 3:
            dialog._test_atem_connection()
            pump(6, lambda d=dialog: d.atem_test_result_label.text().startswith("Connected"))
        dialog.raise_()
        dialog.activateWindow()
        pump(1.0)
        save(grab_window(dialog), name)
        dialog.reject()
        pump(0.5)

    # Add Camera dialog with simulated NDI discovery results
    dialog = CameraAddDialog(window, existing_cameras=window.config.get_cameras())
    dialog.show()
    dialog.move(window.pos() + QPoint(120, 60))
    pump(0.5)
    dialog._on_cameras_discovered(DEMO_NDI_SOURCES)
    dialog.ip_checkbox.setChecked(True)
    dialog.ip_input.setText("192.168.1.100")
    dialog.resize(520, 340)
    dialog.raise_()
    dialog.activateWindow()
    pump(1.0)
    save(grab_window(dialog), "add-camera.png")
    dialog.reject()
    pump(0.5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "resources" / "VideoCue-Screenshot.png",
        help="where to save the PNG (default: resources/VideoCue-Screenshot.png)",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="also save the documentation screenshots in docs/images/",
    )
    args = parser.parse_args()

    config_root = Path(tempfile.mkdtemp(prefix="videocue-screenshot-"))
    os.environ["LOCALAPPDATA"] = str(config_root)
    os.environ["HOME"] = str(config_root)
    write_demo_config(config_root)

    import qdarkstyle
    from atem_simulator import AtemSimulator

    from videocue.controllers.atem_tally import ATEM_PORT
    from videocue.ui.main_window import MainWindow
    from videocue.ui_strings import UIStrings

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(UIStrings.APP_NAME)
    app.setWindowIcon(QIcon(str(REPO_ROOT / "resources" / "icon.png")))
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyqt6"))

    def pump(seconds: float, until=None) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents()
            if until is not None and until():
                return True
            time.sleep(0.02)
        return False

    sim = AtemSimulator(port=ATEM_PORT)
    for i, (_name, input_name, *_rest) in enumerate(CAMERAS, 1):
        sim.input_names[i] = (input_name, input_name[:4].upper())
    sim.start()

    frames = camera_frames(draw_concert())
    window = MainWindow()
    try:
        window.resize(*WINDOW_SIZE)
        window.move(60, 40)
        window.show()
        ready = pump(
            20,
            lambda: (
                len(window.cameras) == len(CAMERAS)
                and window._atem_connected
                and all(cam._init_completed for cam in window.cameras)
                and window.cameras[0].tally_label.text().startswith(UIStrings.TALLY_PROGRAM)
            ),
        )
        if not ready:
            print("Timed out waiting for cameras and ATEM tally", file=sys.stderr)
            return 1
        pump(0.5)

        # Demo cameras never answer VISCA; make them look connected and streaming.
        for cam, frame in zip(window.cameras, frames, strict=True):
            cam.is_connected = True
            cam.status_indicator.setStyleSheet("background-color: green; border-radius: 6px;")
            cam.reconnect_button.setVisible(False)
            cam.set_controls_enabled(True)
            cam.connection_state_changed.emit(True)
            cam.video_toggle_button.setText(UIStrings.BTN_PAUSE)
            cam.video_toggle_button.setEnabled(True)
            cam.on_resolution_changed(1920, 1080, 59.94)
            cam.on_video_frame(frame)
            cam._render_latest_frame()
        pump(0.5)

        for cam, (*_rest, scroll) in zip(window.cameras, CAMERAS, strict=True):
            bar = controls_scroll_area(cam).verticalScrollBar()
            if scroll == "presets":
                label = cam.presets_label
                bar.setValue(label.mapTo(cam.controls_container, label.rect().topLeft()).y() - 8)
            else:
                bar.setValue(round(bar.maximum() * scroll))

        window.raise_()
        window.activateWindow()
        pump(1.0)

        frame_rect = window.frameGeometry()
        shot = window.screen().grabWindow(
            0, frame_rect.x(), frame_rect.y(), frame_rect.width(), frame_rect.height()
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not shot.save(str(args.output)):
            print(f"Could not save {args.output}", file=sys.stderr)
            return 1
        print(f"Saved {args.output} ({shot.width()}x{shot.height()})")
        if args.docs:
            capture_docs(window, pump, frames)
        return 0
    finally:
        window.close()
        pump(1)
        sim.stop()


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # Skip interpreter teardown; Qt worker threads otherwise warn while being destroyed.
    os._exit(code)
