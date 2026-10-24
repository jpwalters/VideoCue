"""
BirdDog REST API probe.

Reads all color-related endpoints and verifies POST round-trips by writing the
current value back, then a +1 change, then restoring the original.

Usage:
    python tools/birddog_api_probe.py 192.168.1.102 192.168.1.103 192.168.1.104
    python tools/birddog_api_probe.py --read-only 192.168.1.104
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from videocue.constants import BirdDogConstants  # noqa: E402
from videocue.controllers.birddog_api import (  # noqa: E402
    BirdDogAPI,
    BirdDogAPIError,
    BirdDogModel,
)

PROBE_FIELDS = {
    BirdDogModel.P400: ("birddogwbsetup", "Level"),
    BirdDogModel.P200: ("birddogcmsetup", "ColourGain"),
}


def read_all(api: BirdDogAPI) -> dict:
    result = {}
    for endpoint in sorted(BirdDogConstants.ALLOWED_ENDPOINTS):
        start = time.perf_counter()
        try:
            result[endpoint] = api.get_endpoint(endpoint)
        except BirdDogAPIError as e:
            result[endpoint] = {"_error": str(e)}
        result[endpoint]["_ms"] = round((time.perf_counter() - start) * 1000, 1)
    return result


def round_trip(api: BirdDogAPI, endpoint: str, field: str) -> dict:
    report: dict = {"endpoint": endpoint, "field": field}
    original = api.get_endpoint(endpoint).get(field)
    report["original"] = original
    if original is None:
        report["error"] = "field not present"
        return report
    try:
        start = time.perf_counter()
        report["post_same_response"] = api.post_endpoint(endpoint, {field: original})
        report["post_ms"] = round((time.perf_counter() - start) * 1000, 1)
        report["after_same"] = api.get_endpoint(endpoint).get(field)

        changed = str(int(original) + 1)
        report["post_changed_response"] = api.post_endpoint(endpoint, {field: changed})
        time.sleep(0.3)
        report["after_changed"] = api.get_endpoint(endpoint).get(field)
        report["write_works"] = report["after_changed"] == changed
    finally:
        api.post_endpoint(endpoint, {field: original})
        time.sleep(0.3)
        report["restored"] = api.get_endpoint(endpoint).get(field)
        report["restore_ok"] = report["restored"] == original
    return report


def probe_range(api: BirdDogAPI, endpoint: str, field: str) -> dict:
    """Write out-of-range extremes and read back what the camera keeps."""
    original = api.get_endpoint(endpoint).get(field)
    report: dict = {"original": original}
    try:
        for label, value in (("high", 999), ("low", -999)):
            response = api.post_endpoint(endpoint, {field: value})
            report[label] = response.get(field, api.get_endpoint(endpoint).get(field))
    finally:
        api.post_endpoint(endpoint, {field: original})
        report["restore_ok"] = api.get_endpoint(endpoint).get(field) == original
    return report


RANGE_FIELDS = {
    BirdDogModel.P400: [
        ("birddogwbsetup", f) for f in ("Level", "Phase", "Offset", "RG", "RB", "GR", "BG")
    ],
    BirdDogModel.P200: [
        ("birddogcmsetup", f) for f in ("ColourGain", "HuePhase", "RedGain", "RedHue")
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="BirdDog REST API probe")
    parser.add_argument("ips", nargs="+")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--ranges", action="store_true", help="probe field limits (restores)")
    args = parser.parse_args()

    ok = True
    output = {}
    for ip in args.ips:
        api = BirdDogAPI(ip)
        entry: dict = {}
        try:
            model = api.detect_model()
            entry["model"] = model.value
            entry["endpoints"] = read_all(api)
            if not args.read_only and model in PROBE_FIELDS:
                entry["round_trip"] = round_trip(api, *PROBE_FIELDS[model])
                ok = ok and entry["round_trip"].get("restore_ok", False)
            if args.ranges and not args.read_only:
                entry["ranges"] = {}
                for endpoint, field in RANGE_FIELDS.get(model, []):
                    result = probe_range(api, endpoint, field)
                    entry["ranges"][field] = result
                    ok = ok and result["restore_ok"]
        except BirdDogAPIError as e:
            entry["error"] = str(e)
            ok = False
        output[ip] = entry

    print(json.dumps(output, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
