"""
Minimal NDI UI memory test.

Purpose:
- Discover NDI cameras
- Select a responsive source
- Render video in a basic PyQt window
- Log RSS memory periodically

This adds UI rendering on top of streaming to compare memory behavior
against the non-UI test harness.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import signal
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from videocue.controllers import ndi_video  # noqa: E402
from videocue.models.config_manager import ConfigManager  # noqa: E402


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


def get_rss_mb() -> float | None:
    try:
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
        ok = get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        )
        if not ok:
            return None
        return counters.WorkingSetSize / (1024 * 1024)
    except Exception:
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal NDI UI memory test")
    parser.add_argument("--duration-sec", type=int, default=180)
    parser.add_argument("--report-every-sec", type=int, default=2)
    parser.add_argument("--discovery-timeout-ms", type=int, default=5000)
    parser.add_argument("--capture-timeout-ms", type=int, default=100)
    parser.add_argument("--probe-timeout-sec", type=int, default=5)
    parser.add_argument("--probe-min-frames", type=int, default=20)
    parser.add_argument("--probe-rounds", type=int, default=3)
    parser.add_argument("--probe-retry-delay-ms", type=int, default=400)
    parser.add_argument("--verify-timeout-sec", type=int, default=3)
    parser.add_argument("--verify-min-frames", type=int, default=5)
    parser.add_argument("--verify-rounds", type=int, default=3)
    parser.add_argument("--ndi-interface-ip", type=str, default="")
    parser.add_argument("--source-name", type=str, default="")
    parser.add_argument("--bandwidth", choices=["low", "high"], default="low")
    parser.add_argument("--color-format", choices=["bgra", "rgba", "uyvy"], default="bgra")
    parser.add_argument("--frame-skip", type=int, default=2)
    parser.add_argument("--warmup-sec", type=int, default=30)
    return parser.parse_args()


def source_object(ndi: object, source_name: str):
    source = ndi.Source()
    source.ndi_name = source_name.encode("utf-8") if isinstance(source_name, str) else source_name
    return source


def create_receiver(ndi: object, bandwidth: str):
    try:
        recv_settings = ndi.RecvCreateV3()
        recv_settings.color_format = ndi.RECV_COLOR_FORMAT_FASTEST
        recv_settings.bandwidth = (
            ndi.RECV_BANDWIDTH_HIGHEST if bandwidth == "high" else ndi.RECV_BANDWIDTH_LOWEST
        )
        recv_settings.allow_video_fields = True
        return ndi.recv_create_v3(recv_settings)
    except Exception:
        return ndi.recv_create_v3()


def probe_source(
    ndi: object,
    source_name: str,
    bandwidth: str,
    timeout_sec: int,
    capture_timeout_ms: int,
) -> tuple[int, int, int]:
    receiver = None
    try:
        receiver = create_receiver(ndi, bandwidth)
        if not receiver:
            return (0, 0, 0)

        ndi.recv_connect(receiver, source_object(ndi, source_name))
        deadline = time.time() + max(1, timeout_sec)
        video_frames = 0
        none_frames = 0
        other_frames = 0

        while time.time() < deadline:
            t, v, a, m = ndi.recv_capture_v3(receiver, capture_timeout_ms)
            if t == ndi.FRAME_TYPE_VIDEO:
                video_frames += 1
                ndi.recv_free_video_v2(receiver, v)
            elif t == ndi.FRAME_TYPE_AUDIO:
                other_frames += 1
                ndi.recv_free_audio_v3(receiver, a)
            elif t == ndi.FRAME_TYPE_METADATA:
                other_frames += 1
                ndi.recv_free_metadata(receiver, m)
            elif t == ndi.FRAME_TYPE_NONE:
                none_frames += 1
            else:
                other_frames += 1

        return (video_frames, none_frames, other_frames)
    finally:
        if receiver:
            with contextlib.suppress(Exception):
                ndi.recv_destroy(receiver)


def choose_source_candidates(args: argparse.Namespace) -> list[tuple[str, int]]:
    print("Discovering NDI cameras...")
    expected_count = 0
    try:
        config = ConfigManager()
        expected_count = len(config.get_cameras())
    except Exception:
        expected_count = 0

    pre_discovered = ndi_video.discover_and_cache_all_sources(
        timeout_ms=max(args.discovery_timeout_ms, 10000),
        expected_count=expected_count,
    )
    print(
        f"Pre-discovery cached sources: {pre_discovered} "
        f"(expected={expected_count if expected_count else 'unknown'})"
    )

    cameras = ndi_video.find_ndi_cameras(timeout_ms=args.discovery_timeout_ms)
    if not cameras:
        return []

    if args.source_name:
        if args.source_name in cameras:
            return [(args.source_name, 0)]
        print(f"Requested source '{args.source_name}' not found.")
        return []

    print(
        f"Probing {len(cameras)} discovered source(s) "
        f"(rounds={max(1, args.probe_rounds)}, timeout={args.probe_timeout_sec}s, "
        f"min_frames={args.probe_min_frames})..."
    )
    ndi = ndi_video.ndi

    best_scores: dict[str, int] = dict.fromkeys(cameras, 0)
    rounds = max(1, args.probe_rounds)
    threshold_hit = False

    for round_idx in range(1, rounds + 1):
        if round_idx > 1:
            ndi_video.discover_and_cache_all_sources(
                timeout_ms=max(args.discovery_timeout_ms, 10000),
                expected_count=expected_count,
            )
            refreshed_cameras = ndi_video.find_ndi_cameras(timeout_ms=args.discovery_timeout_ms)
            for refreshed_name in refreshed_cameras:
                if refreshed_name not in best_scores:
                    best_scores[refreshed_name] = 0
            cameras = list(best_scores.keys())

        print(f"Probe round {round_idx}/{rounds}")

        for name in cameras:
            print(f"Probe start: {name}")
            video_frames, none_frames, other_frames = probe_source(
                ndi,
                name,
                args.bandwidth,
                args.probe_timeout_sec,
                args.capture_timeout_ms,
            )
            print(
                f"Probe {name}: video={video_frames} none={none_frames} other={other_frames}"
            )
            if video_frames > best_scores[name]:
                best_scores[name] = video_frames
            if video_frames >= args.probe_min_frames:
                threshold_hit = True

        if threshold_hit:
            break

        if round_idx < rounds:
            time.sleep(max(0.0, args.probe_retry_delay_ms / 1000.0))

    scored: list[tuple[str, int]] = list(best_scores.items())

    if not scored:
        return []

    scored.sort(key=lambda item: item[1], reverse=True)
    best_name, best_video = scored[0]
    if best_video < args.probe_min_frames:
        print(
            f"No source met threshold after probe rounds. "
            f"Continuing to preflight with best '{best_name}' ({best_video} frames)."
        )

    print("Ranked candidates:", ", ".join(f"{n}={v}" for n, v in scored))
    return scored


def pick_verified_source(args: argparse.Namespace, candidates: list[tuple[str, int]]) -> str | None:
    """Immediately re-verify candidate sources before launching UI stream."""
    ndi = ndi_video.ndi
    best_name: str | None = None
    best_observed = -1

    for name, probe_score in candidates:
        rounds = max(1, args.verify_rounds)
        for round_idx in range(1, rounds + 1):
            print(
                f"Preflight verify: {name} round={round_idx}/{rounds} "
                f"(probe_score={probe_score}, timeout={args.verify_timeout_sec}s, "
                f"min_frames={args.verify_min_frames})"
            )
            video_frames, none_frames, other_frames = probe_source(
                ndi,
                name,
                args.bandwidth,
                args.verify_timeout_sec,
                args.capture_timeout_ms,
            )
            print(
                f"Preflight {name}: video={video_frames} none={none_frames} other={other_frames}"
            )

            if video_frames > best_observed:
                best_observed = video_frames
                best_name = name

            if video_frames >= args.verify_min_frames:
                print(f"Selected verified source: {name}")
                return name

    if best_name is not None:
        print(
            f"No source passed preflight verification. "
            f"Falling back to best observed source: {best_name} (video_frames={best_observed})."
        )
        return best_name

    print("No source passed preflight verification.")
    return None


def configure_interface(args: argparse.Namespace) -> None:
    if args.ndi_interface_ip:
        ndi_video.set_preferred_network_interface(args.ndi_interface_ip)
        print(f"NDI interface (forced): {args.ndi_interface_ip}")
        return

    try:
        config = ConfigManager()
        selected = config.get_preferred_network_interface()
        ndi_video.set_preferred_network_interface(selected)
        if selected:
            print(f"NDI interface (config): {selected}")
        else:
            print("NDI interface: default")
    except Exception:
        ndi_video.set_preferred_network_interface(None)
        print("NDI interface: default")


class NDITestWindow(QMainWindow):
    def __init__(self, source_name: str, args: argparse.Namespace):
        super().__init__()
        self.source_name = source_name
        self.args = args
        self.thread = None
        self.frame_count = 0
        self.render_count = 0
        self.start_time = time.time()
        self.baseline_rss = get_rss_mb()
        self.last_rss = self.baseline_rss
        self.rss_samples: list[tuple[float, float]] = []
        if self.baseline_rss is not None:
            self.rss_samples.append((0.0, self.baseline_rss))

        self.setWindowTitle(f"NDI UI Test - {source_name}")
        self.resize(960, 600)

        container = QWidget(self)
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)

        self.info_label = QLabel("Initializing...")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.info_label)

        self.video_label = QLabel("Waiting for video...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setMinimumSize(640, 360)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        layout.addWidget(self.video_label, stretch=1)
        self._latest_frame = None
        self._display_pixmap = QPixmap()

        self.render_timer = QTimer(self)
        self.render_timer.setInterval(33)
        self.render_timer.timeout.connect(self._render_latest_frame)
        self.render_timer.start()

        self.report_timer = QTimer(self)
        self.report_timer.timeout.connect(self._report)
        self.report_timer.start(max(1000, self.args.report_every_sec * 1000))

        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.close)
        self.stop_timer.start(self.args.duration_sec * 1000)

        self._start_thread()

    def _start_thread(self):
        self.thread = ndi_video.NDIVideoThread(
            self.source_name,
            frame_skip=self.args.frame_skip,
            bandwidth=self.args.bandwidth,
            color_format=self.args.color_format,
        )
        self.thread.frame_ready.connect(self._on_frame)
        self.thread.error.connect(self._on_error)
        self.thread.connected.connect(self._on_connected)
        self.thread.start()
        self.info_label.setText("Connected. Receiving frames...")

    def _on_connected(self, web_url: str):
        if web_url:
            self.info_label.setText(f"Connected. Web URL: {web_url}")

    def _on_error(self, message: str):
        self.info_label.setText(f"NDI error: {message}")

    def _on_frame(self, qimage):
        self.frame_count += 1
        self._latest_frame = qimage

    def _render_latest_frame(self):
        if self._latest_frame is None:
            return

        qimage = self._latest_frame
        self._latest_frame = None
        self.render_count += 1

        scaled = qimage.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._display_pixmap.convertFromImage(scaled)
        self.video_label.setPixmap(self._display_pixmap)

    def _report(self):
        now = time.time()
        elapsed = now - self.start_time
        fps = self.frame_count / elapsed if elapsed > 0 else 0.0
        rss = get_rss_mb()

        if rss is not None and self.baseline_rss is not None and self.last_rss is not None:
            delta = rss - self.baseline_rss
            step = rss - self.last_rss
            self.last_rss = rss
            self.rss_samples.append((elapsed, rss))
            print(
                f"t={elapsed:6.1f}s frames={self.frame_count:7d} fps={fps:6.1f} "
                f"rss={rss:7.1f}MB delta={delta:+7.1f}MB step={step:+6.1f}MB"
            )
            self.info_label.setText(
                f"source={self.source_name} fps={fps:.1f} rss={rss:.1f}MB delta={delta:+.1f}MB"
            )
        else:
            print(f"t={elapsed:6.1f}s frames={self.frame_count:7d} fps={fps:6.1f}")

    def closeEvent(self, event):
        try:
            self.report_timer.stop()
            self.stop_timer.stop()
            self.render_timer.stop()
            self._display_pixmap = QPixmap()

            if self.thread:
                self.thread.stop()
                self.thread.wait(2000)
                self.thread = None
        finally:
            ndi_video.cleanup_ndi()
            super().closeEvent(event)


def compute_tail_slope_mb_per_min(samples: list[tuple[float, float]], tail_sec: float = 30.0) -> float | None:
    if len(samples) < 2:
        return None
    end_t = samples[-1][0]
    start_t = max(0.0, end_t - tail_sec)
    tail = [s for s in samples if s[0] >= start_t]
    if len(tail) < 2:
        tail = samples[-2:]

    t0, r0 = tail[0]
    t1, r1 = tail[-1]
    dt = t1 - t0
    if dt <= 0:
        return None
    return (r1 - r0) / (dt / 60.0)


def samples_after_warmup(
    samples: list[tuple[float, float]],
    warmup_sec: float,
) -> list[tuple[float, float]]:
    if not samples:
        return []

    filtered = [sample for sample in samples if sample[0] >= max(0.0, warmup_sec)]
    if len(filtered) >= 2:
        return filtered

    return samples


def classify_memory_behavior(
    samples: list[tuple[float, float]],
    tail_slope_mb_per_min: float | None,
) -> str:
    if len(samples) < 3 or tail_slope_mb_per_min is None:
        return "insufficient-data"

    rss_values = [rss for _, rss in samples]
    rss_band = max(rss_values) - min(rss_values)

    # Heuristic interpretation:
    # - <= 0.25 MB/min in tail: plateau/steady churn
    # - 0.25..1.0 MB/min: mild upward trend
    # - > 1.0 MB/min: growing
    if abs(tail_slope_mb_per_min) <= 0.25:
        return f"plateau (band={rss_band:.1f}MB)"
    if tail_slope_mb_per_min <= 1.0:
        return f"mild-growth (band={rss_band:.1f}MB)"
    return f"growing (band={rss_band:.1f}MB)"


def memory_analysis_ready(
    samples: list[tuple[float, float]],
    warmup_sec: float,
    min_analysis_sec: float = 60.0,
) -> tuple[bool, str]:
    if len(samples) < 3:
        return (False, "insufficient-data (too-few-samples)")

    total_duration = samples[-1][0]
    if total_duration < max(min_analysis_sec, warmup_sec + 15.0):
        return (
            False,
            f"insufficient-data (short-run={total_duration:.1f}s, warmup={warmup_sec:.0f}s)",
        )

    return (True, "")


def main() -> int:
    args = parse_args()

    if not ndi_video.ndi_available:
        print("NDI not available. Install NDI Runtime and verify wrapper import.")
        return 1

    configure_interface(args)
    candidates = choose_source_candidates(args)
    source_name = pick_verified_source(args, candidates)
    if not source_name:
        print("No responsive source available for UI test.")
        ndi_video.cleanup_ndi()
        return 1

    print(f"Using source: {source_name}")

    stop_requested = False

    def _handle_signal(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    app = QApplication(sys.argv)
    win = NDITestWindow(source_name, args)
    win.show()

    rc = app.exec()

    end_rss = get_rss_mb()
    if win.baseline_rss is not None and end_rss is not None:
        print("\n=== UI Test Complete ===")
        print(f"Source: {source_name}")
        print(f"Duration: {time.time() - win.start_time:.1f}s")
        print(f"Frames received: {win.frame_count}")
        print(f"Frames rendered: {win.render_count}")
        total_elapsed = max(0.001, time.time() - win.start_time)
        print(f"Average FPS: {win.frame_count / total_elapsed:.1f}")
        print(
            f"RSS start={win.baseline_rss:.1f}MB end={end_rss:.1f}MB "
            f"delta={end_rss - win.baseline_rss:+.1f}MB"
        )

        if win.rss_samples:
            analysis_ready, analysis_note = memory_analysis_ready(
                win.rss_samples,
                args.warmup_sec,
            )
            rss_values = [rss for _, rss in win.rss_samples]
            rss_min = min(rss_values)
            rss_max = max(rss_values)
            rss_avg = sum(rss_values) / len(rss_values)
            tail_slope = compute_tail_slope_mb_per_min(win.rss_samples, tail_sec=30.0)
            verdict = (
                classify_memory_behavior(win.rss_samples, tail_slope)
                if analysis_ready
                else analysis_note
            )

            steady_samples = samples_after_warmup(win.rss_samples, args.warmup_sec)
            steady_tail_slope = compute_tail_slope_mb_per_min(steady_samples, tail_sec=30.0)
            steady_verdict = (
                classify_memory_behavior(steady_samples, steady_tail_slope)
                if analysis_ready
                else analysis_note
            )

            print(
                f"RSS stats min={rss_min:.1f}MB max={rss_max:.1f}MB "
                f"avg={rss_avg:.1f}MB band={rss_max - rss_min:.1f}MB"
            )
            if tail_slope is not None:
                print(f"RSS tail_slope(30s)={tail_slope:+.2f} MB/min")
            print(f"Memory verdict: {verdict}")
            if len(steady_samples) != len(win.rss_samples):
                print(
                    f"Steady-state samples: {len(steady_samples)}/{len(win.rss_samples)} "
                    f"(warmup={args.warmup_sec}s)"
                )
                if steady_tail_slope is not None:
                    print(
                        "Steady-state RSS tail_slope(30s)="
                        f"{steady_tail_slope:+.2f} MB/min"
                    )
                print(f"Steady-state verdict: {steady_verdict}")

    return rc


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        print(f"UI test exited with code {exit_code}")
