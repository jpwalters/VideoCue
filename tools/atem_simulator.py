"""
Minimal ATEM switcher simulator for testing VideoCue tally without hardware.

Speaks enough of the ATEM UDP protocol for a read-only client: handshake,
initial state dump, keepalives, retransmission of unacknowledged packets and
live Program/Preview/transition/keyer changes on two M/Es.

Usage:
    python tools/atem_simulator.py                 # demo cycle on 127.0.0.1:9910
    python tools/atem_simulator.py --interval 1 --host 0.0.0.0
    python tools/atem_simulator.py --inputs 8      # smaller switcher
Then set the switcher IP to 127.0.0.1 in VideoCue Preferences -> Switcher.
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from videocue.controllers.atem_tally import (  # noqa: E402
    ATEM_PORT,
    FLAG_ACK_REPLY,
    FLAG_ACK_REQUEST,
    FLAG_NEW_SESSION,
    FLAG_RETRANSMIT,
    MAX_PACKET_ID,
    build_command,
    build_packet,
    parse_header,
)

KEEPALIVE_S = 0.5
RETRANSMIT_S = 0.3
CLIENT_TIMEOUT_S = 5.0


@dataclass
class _Client:
    session_id: int
    next_packet_id: int = 1
    last_seen: float = field(default_factory=time.monotonic)
    last_sent: float = 0.0
    dump_sent: bool = False
    unacked: dict[int, tuple[float, bytes]] = field(default_factory=dict)


class AtemSimulator:
    """Thread-based fake ATEM. Mutator methods are thread-safe and push updates to clients."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = ATEM_PORT,
        me_count: int = 2,
        input_count: int = 20,
        keyers_per_me: int = 1,
    ):
        self.host = host
        self.port = port
        self.me_count = me_count
        self.input_names = {i: (f"Camera {i}", f"CAM{i}") for i in range(1, input_count + 1)}
        self.program = dict.fromkeys(range(me_count), 1)
        self.preview = dict.fromkeys(range(me_count), 2)
        self.in_transition = dict.fromkeys(range(me_count), False)
        self.keyers = {(me, k): [False, 3] for me in range(me_count) for k in range(keyers_per_me)}
        self.drop_next = 0
        self._clients: dict[tuple[str, int], _Client] = {}
        self._next_session = 0x8001
        self._lock = threading.RLock()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((self.host, self.port))
        self.port = self._sock.getsockname()[1]
        self._sock.settimeout(0.05)
        self._running = True
        self._thread = threading.Thread(target=self._serve, name="AtemSimulator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(2)
        if self._sock is not None:
            self._sock.close()
        self._clients.clear()

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    # ---- switcher operations --------------------------------------------

    def cut(self, me: int, source: int) -> None:
        with self._lock:
            self.program[me] = source
            self._broadcast(self._program_cmd(me) + self._tally_cmd())

    def set_preview(self, me: int, source: int) -> None:
        with self._lock:
            self.preview[me] = source
            self._broadcast(self._preview_cmd(me) + self._tally_cmd())

    def set_transition(self, me: int, in_transition: bool) -> None:
        with self._lock:
            self.in_transition[me] = in_transition
            self._broadcast(self._transition_cmd(me) + self._tally_cmd())

    def set_keyer(self, me: int, keyer: int, on_air: bool, fill: int | None = None) -> None:
        with self._lock:
            self.keyers[(me, keyer)][0] = on_air
            if fill is not None:
                self.keyers[(me, keyer)][1] = fill
            payload = self._keyer_props_cmd(me, keyer) + self._keyer_on_air_cmd(me, keyer)
            self._broadcast(payload + self._tally_cmd())

    def rename_input(self, input_id: int, long_name: str, short_name: str) -> None:
        with self._lock:
            self.input_names[input_id] = (long_name, short_name)
            self._broadcast(self._input_cmd(input_id))

    # ---- commands ----------------------------------------------------------

    def _program_cmd(self, me: int) -> bytes:
        return build_command("PrgI", struct.pack(">Bx H", me, self.program[me]))

    def _preview_cmd(self, me: int) -> bytes:
        return build_command("PrvI", struct.pack(">Bx H 4x", me, self.preview[me]))

    def _transition_cmd(self, me: int) -> bytes:
        return build_command(
            "TrPs", struct.pack(">BBBx H 2x", me, int(self.in_transition[me]), 0, 0)
        )

    def _keyer_on_air_cmd(self, me: int, keyer: int) -> bytes:
        return build_command(
            "KeOn", struct.pack(">BBBx", me, keyer, int(self.keyers[(me, keyer)][0]))
        )

    def _keyer_props_cmd(self, me: int, keyer: int) -> bytes:
        fill = self.keyers[(me, keyer)][1]
        return build_command("KeBP", struct.pack(">BBBxBB HH 14x", me, keyer, 0, 0, 0, fill, 0))

    def _input_cmd(self, input_id: int) -> bytes:
        long_name, short_name = self.input_names[input_id]
        body = struct.pack(
            ">H20s4sBx HH BxBB",
            input_id,
            long_name.encode(),
            short_name.encode(),
            0,  # names are custom
            1,  # external ports
            1,  # external port type
            0,  # internal port type: external
            0x1F,
            0x03,
        )
        return build_command("InPr", body)

    def _tally_cmd(self) -> bytes:
        """Main program output tally, which is M/E 1."""
        program = {self.program[0]}
        preview = {self.preview[0]}
        if self.in_transition[0]:
            program.add(self.preview[0])
        for (me, _keyer), (on_air, fill) in self.keyers.items():
            if me == 0 and on_air:
                program.add(fill)
        sources = sorted(self.input_names)
        body = struct.pack(">H", len(sources))
        for source in sources:
            flags = (1 if source in program else 0) | (2 if source in preview else 0)
            body += struct.pack(">HB", source, flags)
        return build_command("TlSr", body)

    def _state_dump(self) -> list[bytes]:
        topology = struct.pack(">BBBBBB18x", self.me_count, len(self.input_names) + 10, 2, 6, 0, 2)
        packets = [
            build_command("_ver", struct.pack(">HH", 2, 30)) + build_command("_top", topology),
            b"".join(self._input_cmd(i) for i in sorted(self.input_names)),
        ]
        me_payload = b""
        for me in range(self.me_count):
            me_payload += self._program_cmd(me) + self._preview_cmd(me) + self._transition_cmd(me)
        for me, keyer in self.keyers:
            me_payload += self._keyer_props_cmd(me, keyer) + self._keyer_on_air_cmd(me, keyer)
        packets.append(me_payload)
        packets.append(self._tally_cmd() + build_command("InCm", b"\x01\x00\x00\x00"))
        return packets

    # ---- transport ---------------------------------------------------------

    def _send_reliable(self, address: tuple[str, int], client: _Client, payload: bytes) -> None:
        packet_id = client.next_packet_id
        client.next_packet_id = (packet_id + 1) % MAX_PACKET_ID
        packet = build_packet(FLAG_ACK_REQUEST, client.session_id, packet_id, payload)
        client.unacked[packet_id] = (time.monotonic(), packet)
        client.last_sent = time.monotonic()
        if self.drop_next > 0:
            self.drop_next -= 1
            return
        self._sock.sendto(packet, address)

    def _broadcast(self, payload: bytes) -> None:
        for address, client in list(self._clients.items()):
            if client.dump_sent:
                self._send_reliable(address, client, payload)

    def _serve(self) -> None:
        while self._running:
            try:
                data, address = self._sock.recvfrom(2048)
            except (TimeoutError, ConnectionResetError):
                data = None
            except OSError:
                if not self._running:
                    return
                raise
            with self._lock:
                if data:
                    self._handle(data, address)
                self._housekeeping()

    def _handle(self, data: bytes, address: tuple[str, int]) -> None:
        header = parse_header(data)
        if header is None:
            return
        if header.flags & FLAG_NEW_SESSION:
            client = _Client(session_id=self._next_session)
            self._next_session += 1
            self._clients[address] = client
            reply = build_packet(FLAG_NEW_SESSION, header.session_id, 0, bytes(8))
            self._sock.sendto(reply, address)
            return
        client = self._clients.get(address)
        if client is None:
            return
        client.last_seen = time.monotonic()
        if header.flags & FLAG_ACK_REPLY:
            for packet_id in [p for p in client.unacked if p <= header.ack_id]:
                del client.unacked[packet_id]
            if not client.dump_sent:
                client.dump_sent = True
                for payload in self._state_dump():
                    self._send_reliable(address, client, payload)

    def _housekeeping(self) -> None:
        now = time.monotonic()
        for address, client in list(self._clients.items()):
            if now - client.last_seen > CLIENT_TIMEOUT_S:
                del self._clients[address]
                continue
            for packet_id in sorted(client.unacked):
                sent_at, packet = client.unacked[packet_id]
                if now - sent_at > RETRANSMIT_S:
                    flagged = bytes([packet[0] | (FLAG_RETRANSMIT << 3)]) + packet[1:]
                    client.unacked[packet_id] = (now, packet)
                    self._sock.sendto(flagged, address)
            if client.dump_sent and now - client.last_sent > KEEPALIVE_S:
                self._send_reliable(address, client, b"")


def _demo(sim: AtemSimulator, interval: float) -> None:
    inputs = sorted(sim.input_names)
    step = 0
    while True:
        time.sleep(interval)
        step += 1
        me1_program = inputs[step % 4]
        sim.cut(0, me1_program)
        sim.set_preview(0, inputs[(step + 1) % 4])
        sim.cut(1, inputs[4 + step % 4] if len(inputs) > 7 else me1_program)
        sim.set_preview(1, inputs[4 + (step + 1) % 4] if len(inputs) > 7 else me1_program)
        keyer_on = step % 3 == 0
        sim.set_keyer(1, 0, keyer_on, fill=inputs[min(7, len(inputs) - 1)])
        print(
            f"[{time.strftime('%H:%M:%S')}] M/E1 PGM {sim.program[0]} PVW {sim.preview[0]} | "
            f"M/E2 PGM {sim.program[1]} PVW {sim.preview[1]} key {'ON' if keyer_on else 'off'} | "
            f"clients {sim.client_count}",
            flush=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=ATEM_PORT)
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between changes")
    parser.add_argument("--inputs", type=int, default=20, help="number of external inputs")
    args = parser.parse_args()

    sim = AtemSimulator(args.host, args.port, input_count=args.inputs)
    sim.start()
    print(f"ATEM simulator listening on {args.host}:{sim.port} (Ctrl+C to stop)", flush=True)
    try:
        _demo(sim, args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
