"""
End-to-end color match test against live BirdDog cameras.

Matches each target camera to the reference using the same ColorMatchWorker as the UI,
checks the error drops and stays stable, saves before/after images, then restores every
camera's original settings and verifies they read back unchanged.

Usage:
    python tools/color_match_e2e_test.py --ref 192.168.1.104 \
        --targets 192.168.1.103,192.168.1.102 --yes
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load NDI before PyQt6: PyQt6's bundled older MSVC runtime crashes the NDI 6 extension otherwise
import videocue.ndi_wrapper  # noqa: E402

with contextlib.suppress(ImportError):
    videocue.ndi_wrapper._load_ndilib()

import numpy as np  # noqa: E402
from PyQt6.QtCore import QRect, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from videocue.constants import NetworkConstants  # noqa: E402
from videocue.controllers import ndi_video  # noqa: E402
from videocue.controllers.birddog_api import BirdDogAPI  # noqa: E402
from videocue.controllers.color_matcher import (  # noqa: E402
    ColorMatchEndpoint,
    ColorMatchWorker,
    ColorSnapshot,
    FrameSampler,
    restore_snapshot,
    take_snapshot,
    verify_snapshot,
)
from videocue.controllers.visca_ip import ViscaIP  # noqa: E402
from videocue.models.color_analysis import color_residual, residual_error  # noqa: E402
from videocue.models.config_manager import ConfigManager  # noqa: E402

TILE_W, TILE_H = 640, 360


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Color match end-to-end test")
    parser.add_argument("--ref", default="192.168.1.104", help="reference camera IP")
    parser.add_argument("--targets", default="192.168.1.103,192.168.1.102")
    parser.add_argument("--yes", action="store_true", help="don't prompt to aim cameras")
    parser.add_argument("--preset", default="", help="recall this preset name on every camera")
    parser.add_argument("--max-error", type=float, default=1.5, help="absolute pass threshold")
    parser.add_argument(
        "--min-improvement", type=float, default=0.3, help="required fractional error reduction"
    )
    parser.add_argument("--stability-wait", type=float, default=3.0)
    parser.add_argument("--frame-skip", type=int, default=3)
    parser.add_argument("--no-restore", action="store_true", help="leave matched settings")
    parser.add_argument("--output", default=str(REPO_ROOT / "tools" / "output" / "color_match"))
    return parser.parse_args()


def snapshot_json(snapshot: ColorSnapshot) -> dict:
    data = dataclasses.asdict(snapshot)
    data["model"] = snapshot.model.value
    return data


def save_side_by_side(images: list[QImage | None], labels: list[str], path: Path) -> None:
    canvas = QImage(TILE_W * len(images), TILE_H, QImage.Format.Format_RGB888)
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.setPen(Qt.GlobalColor.yellow)
    for i, (image, label) in enumerate(zip(images, labels, strict=True)):
        rect = QRect(i * TILE_W, 0, TILE_W, TILE_H)
        if image is not None:
            painter.drawImage(rect, image)
        painter.drawText(rect.adjusted(8, 8, -8, -8), Qt.AlignmentFlag.AlignLeft, label)
    painter.end()
    canvas.save(str(path))


def measure_error(sampler: FrameSampler, ref: str, tgt: str, mask, samples: int = 3) -> float:
    mask = np.array(mask, dtype=bool)
    errors = []
    for _ in range(samples):
        ref_sig, tgt_sig = sampler.signatures(ref, tgt)
        errors.append(residual_error(color_residual(ref_sig, tgt_sig, mask)))
    return float(np.mean(errors))


def recall_preset(ips: list[str], cams_by_ip: dict, viscas: dict, name: str) -> None:
    for ip in ips:
        presets = cams_by_ip[ip].get("presets", [])
        match = next((p for p in presets if p.get("name") == name), None)
        if match is None:
            raise RuntimeError(f"Preset '{name}' not found on {ip}")
        viscas[ip].recall_preset_position(int(match["preset_number"]))
    time.sleep(4.0)


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("videocue.controllers.ndi_video", "videocue.controllers.visca_ip"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    app = QApplication(sys.argv)  # noqa: F841 - QImage/QThread need an application instance
    if not ndi_video.ndi_available:
        print(f"FAIL: NDI not available: {ndi_video.get_ndi_error_message()}")
        return 1

    ref_ip = args.ref
    target_ips = [ip.strip() for ip in args.targets.split(",") if ip.strip()]
    all_ips = [ref_ip, *target_ips]

    config = ConfigManager()
    cams_by_ip = {c.get("visca_ip"): c for c in config.get_cameras()}
    missing = [ip for ip in all_ips if not cams_by_ip.get(ip, {}).get("ndi_source_name")]
    if missing:
        print(f"FAIL: no NDI source name in config.json for {missing}")
        return 1

    out_dir = Path(args.output) / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    ndi_video.set_preferred_network_interface(config.get_preferred_network_interface())
    ndi_video.discover_and_cache_all_sources(
        timeout_ms=NetworkConstants.NDI_DISCOVERY_TIMEOUT_MS, expected_count=len(all_ips)
    )

    sampler = FrameSampler()
    threads = {}
    for ip in all_ips:
        thread = ndi_video.NDIVideoThread(
            cams_by_ip[ip]["ndi_source_name"],
            frame_skip=args.frame_skip,
            bandwidth=config.get_ndi_bandwidth(),
            color_format=config.get_ndi_color_format(),
        )
        sampler.attach(ip, thread)
        thread.start()
        threads[ip] = thread

    apis = {ip: BirdDogAPI(ip) for ip in all_ips}
    viscas = {ip: ViscaIP(ip, cams_by_ip[ip].get("visca_port")) for ip in all_ips}
    names = {ip: f"{cams_by_ip[ip]['ndi_source_name']} [{ip}]" for ip in all_ips}
    snapshots: dict[str, ColorSnapshot] = {}
    report: dict = {"reference": ref_ip, "targets": {}, "started": datetime.now().isoformat()}
    passed = True

    try:
        print("Waiting for video from all cameras...")
        sampler.capture(tuple(all_ips), count=2, timeout=30.0)

        for ip in all_ips:
            snapshots[ip] = take_snapshot(apis[ip])
            print(f"  {names[ip]}: {snapshots[ip].model.value}")
        report["original_settings"] = {ip: snapshot_json(s) for ip, s in snapshots.items()}

        if args.preset:
            recall_preset(all_ips, cams_by_ip, viscas, args.preset)
        if not args.yes:
            input("Aim all cameras at the same scene, then press Enter to start...")

        save_side_by_side(
            [sampler.latest_image(ip) for ip in all_ips],
            [names[ip] for ip in all_ips],
            out_dir / "all_before.png",
        )

        ref_endpoint = ColorMatchEndpoint(names[ref_ip], ref_ip, viscas[ref_ip], ref_ip)
        for tgt_ip in target_ips:
            print(f"\n=== Matching {names[tgt_ip]} -> {names[ref_ip]} ===")
            worker = ColorMatchWorker(
                ref_endpoint,
                ColorMatchEndpoint(names[tgt_ip], tgt_ip, viscas[tgt_ip], tgt_ip),
                sampler,
            )
            worker.progress.connect(lambda value, text: print(f"  [{value:3d}%] {text}"))
            entry: dict = {}
            try:
                result = worker.execute()
            except Exception as e:
                entry = {"pass": False, "error": str(e)}
                report["targets"][tgt_ip] = entry
                passed = False
                print(f"  FAIL: {e}")
                continue

            time.sleep(args.stability_wait)
            stable_error = measure_error(sampler, ref_ip, tgt_ip, result["sector_mask"])
            before, after = result["error_before"], result["error_after"]
            improved_enough = after <= before * (1 - args.min_improvement)
            ok = result["improved"] and (after <= args.max_error or improved_enough)
            stable = stable_error <= after * 1.5 + 0.3
            entry = {
                **{k: v for k, v in result.items() if k != "snapshot"},
                "stable_error": stable_error,
                "stable": stable,
                "pass": ok and stable,
            }
            report["targets"][tgt_ip] = entry
            passed = passed and entry["pass"]
            save_side_by_side(
                [sampler.latest_image(ref_ip), sampler.latest_image(tgt_ip)],
                [names[ref_ip], f"{names[tgt_ip]} (matched)"],
                out_dir / f"match_{tgt_ip}.png",
            )
            print(
                f"  error {before:.2f} -> {after:.2f} (stable {stable_error:.2f}), "
                f"wb {result['wb_error_before']:.2f} -> {result['wb_error_after']:.2f}, "
                f"sectors {result['sectors_compared']}, {result['duration_s']}s "
                f"=> {'PASS' if entry['pass'] else 'FAIL'}"
            )

        save_side_by_side(
            [sampler.latest_image(ip) for ip in all_ips],
            [names[ip] for ip in all_ips],
            out_dir / "all_after.png",
        )
    except Exception as e:
        passed = False
        report["error"] = str(e)
        print(f"FAIL: {e}")
    finally:
        restore_report = {}
        if not args.no_restore:
            print("\nRestoring original settings...")
            for ip, snapshot in snapshots.items():
                try:
                    if ip == ref_ip:
                        mismatches = verify_snapshot(apis[ip], snapshot)
                    else:
                        mismatches = restore_snapshot(apis[ip], snapshot)
                except Exception as e:
                    mismatches = [str(e)]
                restore_report[ip] = {"ok": not mismatches, "mismatches": mismatches}
                passed = passed and not mismatches
                label = "unchanged" if ip == ref_ip else "restored"
                print(f"  {names[ip]}: {mismatches or label}")
        report["restore"] = restore_report

        sampler.detach_all()
        for thread in threads.values():
            thread.stop()
        for thread in threads.values():
            thread.wait(3000)

    report["pass"] = passed
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nReport: {report_path}")
    print("RESULT:", "PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
