"""
Capture the README screenshot (resources/VideoCue-Screenshot.png).

Starts the real MainWindow with three demo cameras showing a drawn concert scene,
an in-process ATEM simulator for tally (red PROGRAM / green PREVIEW / grey idle)
and each camera's controls scrolled to a different section, then grabs the window.

Uses a throwaway config directory, so your real VideoCue config is never touched.
Camera IPs are in 192.0.2.0/24 (documentation range), so no real device is contacted.
Needs UDP port 9910 free (stop tools/atem_simulator.py first) and a visible desktop.

Usage:
    python tools/videocue_screenshot.py
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

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import (  # noqa: E402
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import QApplication, QScrollArea  # noqa: E402

SCENE_W, SCENE_H = 3840, 2160
VIDEO_SIZE = [384, 216]
WINDOW_SIZE = (1272, 793)

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
        "streamdeck": {"enabled": False},
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "resources" / "VideoCue-Screenshot.png",
        help="where to save the PNG (default: resources/VideoCue-Screenshot.png)",
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
            area = next(
                a for a in cam.findChildren(QScrollArea) if a.widget() is cam.controls_container
            )
            bar = area.verticalScrollBar()
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
