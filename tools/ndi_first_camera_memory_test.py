"""
Minimal NDI memory growth test.

Purpose:
- Discover NDI cameras
- Connect to the first discovered source
- Stream frames for a fixed duration
- Report process memory over time

This isolates NDI receive behavior from the full VideoCue UI/application stack.
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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from videocue.controllers import ndi_video  # noqa: E402
from videocue.models.config_manager import ConfigManager  # noqa: E402
from videocue.utils.network_interface import (  # noqa: E402
    get_network_interfaces,
    get_preferred_interface_ip,
)


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
    parser = argparse.ArgumentParser(description="Minimal NDI memory growth test")
    parser.add_argument("--duration-sec", type=int, default=180)
    parser.add_argument("--report-every-sec", type=int, default=2)
    parser.add_argument("--discovery-timeout-ms", type=int, default=5000)
    parser.add_argument("--capture-timeout-ms", type=int, default=100)
    parser.add_argument("--max-no-frame-attempts", type=int, default=200)
    parser.add_argument("--bandwidth", choices=["low", "high"], default="low")
    parser.add_argument("--source-name", type=str, default="")
    parser.add_argument("--select-mode", choices=["first", "responsive"], default="responsive")
    parser.add_argument("--probe-timeout-sec", type=int, default=3)
    parser.add_argument("--probe-min-frames", type=int, default=5)
    parser.add_argument("--ndi-interface-ip", type=str, default="")
    parser.add_argument("--convert", action="store_true", help="Enable UYVY->RGB conversion on each video frame")
    return parser.parse_args()


def frame_to_bytes(video_frame) -> bytes:
    if hasattr(video_frame.data, "tobytes"):
        return video_frame.data.tobytes()
    if hasattr(video_frame.data, "__array__"):
        import numpy as np

        return bytes(np.array(video_frame.data).flatten())
    return bytes(video_frame.data)


def uyvy_to_rgb(uyvy_data: bytes, width: int, height: int, line_stride: int) -> bytes:
    """Convert UYVY422 to RGB888 (same approach as app, no UI rendering)."""
    import numpy as np

    frame = np.frombuffer(uyvy_data, dtype=np.uint8)

    if line_stride != width * 2:
        frame = frame.reshape(height, line_stride)[:, : width * 2].flatten()

    uyvy = frame.reshape(height, width // 2, 4)

    u = uyvy[:, :, 0].astype(np.int16) - 128
    y0 = uyvy[:, :, 1].astype(np.int16)
    v = uyvy[:, :, 2].astype(np.int16) - 128
    y1 = uyvy[:, :, 3].astype(np.int16)

    del uyvy
    del frame

    r0 = y0 + 1.402 * v
    g0 = y0 - 0.344 * u - 0.714 * v
    b0 = y0 + 1.772 * u

    r1 = y1 + 1.402 * v
    g1 = y1 - 0.344 * u - 0.714 * v
    b1 = y1 + 1.772 * u

    del u, v, y0, y1

    r0 = np.clip(r0, 0, 255).astype(np.uint8)
    g0 = np.clip(g0, 0, 255).astype(np.uint8)
    b0 = np.clip(b0, 0, 255).astype(np.uint8)
    r1 = np.clip(r1, 0, 255).astype(np.uint8)
    g1 = np.clip(g1, 0, 255).astype(np.uint8)
    b1 = np.clip(b1, 0, 255).astype(np.uint8)

    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    rgb[:, 0::2, 0] = r0
    rgb[:, 0::2, 1] = g0
    rgb[:, 0::2, 2] = b0
    rgb[:, 1::2, 0] = r1
    rgb[:, 1::2, 1] = g1
    rgb[:, 1::2, 2] = b1

    del r0, g0, b0, r1, g1, b1

    out = rgb.tobytes()
    del rgb
    return out


def configure_ndi_interface(args: argparse.Namespace) -> tuple[str | None, list[str]]:
    """Configure NDI preferred interface similarly to main app startup."""
    camera_ips: list[str] = []
    selected_ip: str | None = None

    if args.ndi_interface_ip:
        selected_ip = args.ndi_interface_ip
        ndi_video.set_preferred_network_interface(selected_ip)
        print(f"NDI interface (forced): {selected_ip}")
        return selected_ip, camera_ips

    try:
        config = ConfigManager()
        cameras = config.get_cameras()
        camera_ips = [
            cam.get("visca_ip")
            for cam in cameras
            if cam.get("visca_ip") and cam.get("visca_ip") != ""
        ]

        if camera_ips:
            print(f"Camera IPs from config: {camera_ips}")

        saved = config.get_preferred_network_interface()
        if saved:
            selected_ip = saved
        elif camera_ips:
            selected_ip = get_preferred_interface_ip(camera_ips)

        if selected_ip:
            ndi_video.set_preferred_network_interface(selected_ip)
            print(f"NDI interface (selected): {selected_ip}")
        else:
            ndi_video.set_preferred_network_interface(None)
            print("NDI interface: default (no binding)")

        interfaces = get_network_interfaces()
        if interfaces:
            iface_text = ", ".join(f"{iface.name}:{iface.ip}/{iface.netmask}" for iface in interfaces)
            print(f"Local interfaces: {iface_text}")
    except Exception as exc:
        print(f"Interface selection warning: {exc}")
        ndi_video.set_preferred_network_interface(None)

    return selected_ip, camera_ips


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


def source_object(ndi: object, source_name: str):
    source = ndi.Source()
    source.ndi_name = source_name.encode("utf-8") if isinstance(source_name, str) else source_name
    return source


def probe_source(
    ndi: object,
    receiver: object,
    timeout_sec: int,
    capture_timeout_ms: int,
) -> tuple[int, int, int]:
    """Return (video_frames, none_frames, other_frames) seen during probe window."""
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

    return video_frames, none_frames, other_frames


def choose_source(ndi: object, cameras: list[str], args: argparse.Namespace) -> str | None:
    if args.source_name:
        if args.source_name in cameras:
            return args.source_name
        print(f"Requested source '{args.source_name}' not found in discovery list.")
        return None

    if args.select_mode == "first":
        return cameras[0]

    print(
        f"Probing {len(cameras)} discovered source(s) for responsiveness "
        f"(timeout={args.probe_timeout_sec}s, min_frames={args.probe_min_frames})..."
    )
    best_name: str | None = None
    best_video_frames = -1

    for name in cameras:
        receiver = None
        try:
            print(f"Probe start: {name}")
            receiver = create_receiver(ndi, args.bandwidth)
            if not receiver:
                print(f"Probe skip (receiver create failed): {name}")
                continue

            # Use fresh source object by name for test harness stability.
            # (Avoids potential native-lifetime edge cases with cached source objects.)
            source = source_object(ndi, name)
            ndi.recv_connect(receiver, source)
            video_frames, none_frames, other_frames = probe_source(
                ndi,
                receiver,
                args.probe_timeout_sec,
                args.capture_timeout_ms,
            )
            print(
                f"Probe {name}: video={video_frames} none={none_frames} other={other_frames}"
            )

            if video_frames > best_video_frames:
                best_video_frames = video_frames
                best_name = name

        except Exception as exc:
            print(f"Probe failed for {name}: {exc}")
        finally:
            if receiver:
                with contextlib.suppress(Exception):
                    ndi.recv_destroy(receiver)

    if best_name is None:
        return None

    if best_video_frames < args.probe_min_frames:
        print(
            f"No source met responsiveness threshold. Best was '{best_name}' with {best_video_frames} video frames."
        )
        return None

    print(f"Selected responsive source: {best_name} (probe_video_frames={best_video_frames})")
    return best_name


def main() -> int:
    args = parse_args()

    if not ndi_video.ndi_available:
        print("NDI not available. Install NDI Runtime and verify wrapper import.")
        return 1

    stop_requested = False
    selected_interface_ip, camera_ips_from_config = configure_ndi_interface(args)

    def _handle_signal(_sig, _frame):
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    print("Discovering NDI cameras...")
    expected_count = 0
    try:
        config_for_expected = ConfigManager()
        expected_count = len(config_for_expected.get_cameras())
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
        print("No NDI cameras found.")
        ndi_video.cleanup_ndi()
        return 1

    source_name = choose_source(ndi_video.ndi, cameras, args)
    if not source_name:
        print("No responsive source available for memory test.")
        ndi_video.cleanup_ndi()
        return 1
    print(f"Using source: {source_name}")

    try:
        config = ConfigManager()
        matched = config.get_camera_by_ndi_name(source_name)
        if matched:
            print(
                f"Matched config camera: visca_ip={matched.get('visca_ip')} "
                f"ndi_source_name={matched.get('ndi_source_name')}"
            )
        else:
            print("Matched config camera: none")
    except Exception as exc:
        print(f"Config match warning: {exc}")

    ndi = ndi_video.ndi
    receiver = None
    frames = 0
    no_frame_attempts = 0
    none_frames = 0
    error_frames = 0
    other_frames = 0
    converted_frames = 0
    conversion_failures = 0
    converted_rgb_mb = 0.0
    conversion_time_s = 0.0

    try:
        # Use fresh source object by name for test harness stability.
        source = source_object(ndi, source_name)
        receiver = create_receiver(ndi, args.bandwidth)

        if not receiver:
            print("Failed to create NDI receiver")
            return 1

        ndi.recv_connect(receiver, source)
        print("Connected. Streaming...")
        try:
            web_url = ndi.recv_get_web_control(receiver)
            if web_url:
                if isinstance(web_url, bytes):
                    web_url = web_url.decode("utf-8", errors="replace")
                print(f"Receiver web control URL: {web_url}")
            else:
                print("Receiver web control URL: <none>")
        except Exception as exc:
            print(f"Receiver web control URL query failed: {exc}")

        print(
            f"Test context: interface_ip={selected_interface_ip} "
            f"camera_ips_from_config={camera_ips_from_config}"
        )
        print(f"Conversion mode: {'UYVY->RGB enabled' if args.convert else 'disabled'}")

        start = time.time()
        last_report = start
        baseline_rss = get_rss_mb()
        last_rss = baseline_rss

        print(
            f"Baseline RSS: {baseline_rss:.1f} MB"
            if baseline_rss is not None
            else "Baseline RSS: n/a"
        )

        while not stop_requested:
            now = time.time()
            elapsed = now - start
            if elapsed >= args.duration_sec:
                break

            t, v, a, m = ndi.recv_capture_v3(receiver, args.capture_timeout_ms)
            if t == ndi.FRAME_TYPE_VIDEO:
                frames += 1
                no_frame_attempts = 0
                try:
                    if args.convert:
                        started = time.perf_counter()
                        if v.FourCC != ndi.FOURCC_VIDEO_TYPE_UYVY:
                            conversion_failures += 1
                        else:
                            frame_data = frame_to_bytes(v)
                            rgb_data = uyvy_to_rgb(
                                frame_data,
                                int(v.xres),
                                int(v.yres),
                                int(v.line_stride_in_bytes),
                            )
                            converted_frames += 1
                            converted_rgb_mb += len(rgb_data) / (1024 * 1024)
                            del rgb_data
                            del frame_data
                        conversion_time_s += time.perf_counter() - started
                except Exception:
                    conversion_failures += 1
                finally:
                    ndi.recv_free_video_v2(receiver, v)
            elif t == ndi.FRAME_TYPE_AUDIO:
                ndi.recv_free_audio_v3(receiver, a)
            elif t == ndi.FRAME_TYPE_METADATA:
                ndi.recv_free_metadata(receiver, m)
            elif t == ndi.FRAME_TYPE_NONE:
                none_frames += 1
                no_frame_attempts += 1
                if no_frame_attempts >= args.max_no_frame_attempts:
                    print(
                        f"No video frames for {no_frame_attempts} attempts; stopping test."
                    )
                    break
            elif hasattr(ndi, "FRAME_TYPE_ERROR") and t == ndi.FRAME_TYPE_ERROR:
                error_frames += 1
            else:
                other_frames += 1

            if now - last_report >= args.report_every_sec:
                rss = get_rss_mb()
                fps = frames / elapsed if elapsed > 0 else 0.0

                if rss is not None and baseline_rss is not None and last_rss is not None:
                    print(
                        f"t={elapsed:6.1f}s frames={frames:7d} fps={fps:6.1f} "
                        f"rss={rss:7.1f}MB delta={rss - baseline_rss:+7.1f}MB "
                        f"step={rss - last_rss:+6.1f}MB"
                    )
                    last_rss = rss
                else:
                    print(f"t={elapsed:6.1f}s frames={frames:7d} fps={fps:6.1f}")

                if hasattr(ndi, "debug_get_counters"):
                    counters = ndi.debug_get_counters()
                    recv_out = int(counters.get("recv_instances_outstanding", 0))
                    find_out = int(counters.get("find_instances_outstanding", 0))
                    cap_vid = int(counters.get("recv_capture_video_frames_total", 0))
                    free_v = int(counters.get("recv_free_video_total", 0))
                    print(
                        f"  wrapper: recv_out={recv_out} find_out={find_out} "
                        f"cap_vid={cap_vid} free_v={free_v} vid_imb={cap_vid - free_v:+d}"
                    )
                print(
                    f"  frame_types: video={frames} none={none_frames} "
                    f"error={error_frames} other={other_frames}"
                )
                if args.convert:
                    avg_conv_ms = (
                        (conversion_time_s / converted_frames) * 1000
                        if converted_frames > 0
                        else 0.0
                    )
                    print(
                        f"  conversion: frames={converted_frames} failures={conversion_failures} "
                        f"rgb_total={converted_rgb_mb:.1f}MB avg_ms={avg_conv_ms:.3f}"
                    )

                last_report = now

        total = time.time() - start
        end_rss = get_rss_mb()
        print("\n=== Test Complete ===")
        print(f"Source: {source_name}")
        print(f"Duration: {total:.1f}s")
        print(f"Frames: {frames}")
        print(f"Average FPS: {frames / total:.1f}" if total > 0 else "Average FPS: n/a")
        if baseline_rss is not None and end_rss is not None:
            print(
                f"RSS start={baseline_rss:.1f}MB end={end_rss:.1f}MB "
                f"delta={end_rss - baseline_rss:+.1f}MB"
            )
        print(
            f"Final frame_types: video={frames} none={none_frames} "
            f"error={error_frames} other={other_frames}"
        )
        if args.convert:
            avg_conv_ms = (
                (conversion_time_s / converted_frames) * 1000
                if converted_frames > 0
                else 0.0
            )
            print(
                f"Final conversion: frames={converted_frames} failures={conversion_failures} "
                f"rgb_total={converted_rgb_mb:.1f}MB avg_ms={avg_conv_ms:.3f}"
            )

    finally:
        try:
            if receiver:
                ndi.recv_destroy(receiver)
                receiver = None
        finally:
            ndi_video.cleanup_ndi()

    return 0


if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        print(f"Test exited with code {exit_code}")
