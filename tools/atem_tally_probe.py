"""
ATEM tally probe: connect to a switcher and print input names and live tally.

Run this on site before using VideoCue to confirm the laptop can reach the
switcher and that tally matches the switcher's buttons. Read-only.

Usage:
    python tools/atem_tally_probe.py 192.168.10.240
    python tools/atem_tally_probe.py 192.168.10.240 --me 2 --seconds 60
    python tools/atem_tally_probe.py 127.0.0.1          # against tools/atem_simulator.py
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PyQt6.QtCore import QCoreApplication, QTimer  # noqa: E402

from videocue.controllers.atem_tally import ATEM_PORT, AtemTallyClient  # noqa: E402


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("ip")
    parser.add_argument("--me", type=int, choices=(1, 2), default=1, help="M/E to take tally from")
    parser.add_argument("--port", type=int, default=ATEM_PORT)
    parser.add_argument("--seconds", type=float, default=0, help="exit after N seconds (0 = run)")
    args = parser.parse_args()

    app = QCoreApplication(sys.argv)
    client = AtemTallyClient(args.ip, tally_me=args.me - 1, port=args.port)
    names: dict[int, str] = {}

    def describe(sources: list[int]) -> str:
        return ", ".join(f"{s} ({names.get(s, '?')})" for s in sources) or "-"

    def on_connection(connected: bool) -> None:
        _log("CONNECTED" if connected else "DISCONNECTED (retrying every 5s)")

    def on_me_count(me_count: int) -> None:
        _log(f"Switcher reports {me_count} M/E")
        if args.me > me_count:
            _log(f"M/E {args.me} not available, tally falls back to M/E 1")

    def on_inputs(inputs: dict) -> None:
        names.clear()
        names.update({i: inp.label() for i, inp in inputs.items()})
        _log("Inputs:")
        for input_id in sorted(inputs):
            inp = inputs[input_id]
            kind = "external" if inp.external else "internal"
            print(f"    {input_id:>5}  {inp.long_name:<20} {inp.short_name:<4}  {kind}")

    def on_tally(tally: dict) -> None:
        program = sorted(s for s, (pgm, _) in tally.items() if pgm)
        preview = sorted(s for s, (_, pvw) in tally.items() if pvw)
        _log(f"M/E {args.me}  PROGRAM: {describe(program)}  |  PREVIEW: {describe(preview)}")

    client.connection_changed.connect(on_connection)
    client.me_count_discovered.connect(on_me_count)
    client.inputs_discovered.connect(on_inputs)
    client.tally_changed.connect(on_tally)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Wake the Qt loop periodically so Python can deliver Ctrl+C.
    wake = QTimer()
    wake.timeout.connect(lambda: None)
    wake.start(200)
    if args.seconds > 0:
        QTimer.singleShot(int(args.seconds * 1000), app.quit)

    _log(f"Connecting to ATEM {args.ip}:{args.port} (Ctrl+C to stop)...")
    client.start()
    app.exec()
    client.stop()
    client.wait(2000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
