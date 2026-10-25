"""
Read-only tally client for Blackmagic ATEM switchers (UDP port 9910).

Packet and command layouts follow Sofie atem-connection (MIT):
https://github.com/nrkno/sofie-atem-connection
The client only listens and acknowledges; it never sends switching commands.
"""

import logging
import socket
import struct
import time
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)

ATEM_PORT = 9910
HEADER_LEN = 12
MAX_PACKET_ID = 1 << 15

FLAG_ACK_REQUEST = 0x01
FLAG_NEW_SESSION = 0x02
FLAG_RETRANSMIT = 0x04
FLAG_RETRANSMIT_REQUEST = 0x08
FLAG_ACK_REPLY = 0x10

HELLO_PACKET = bytes(
    [0x10, 0x14, 0x53, 0xAB, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3A]
    + [0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
)

HELLO_RETRY_S = 1.0
CONNECT_TIMEOUT_S = 5.0
RECEIVE_TIMEOUT_S = 5.0
RECONNECT_DELAY_S = 5.0
SOCKET_POLL_S = 0.1

TallyMap = dict[int, tuple[bool, bool]]


@dataclass(frozen=True)
class PacketHeader:
    flags: int
    length: int
    session_id: int
    ack_id: int
    packet_id: int


@dataclass(frozen=True)
class AtemInput:
    input_id: int
    long_name: str
    short_name: str
    names_default: bool
    external: bool

    def label(self) -> str:
        return self.long_name or self.short_name or str(self.input_id)


def parse_header(data: bytes) -> PacketHeader | None:
    """Parse the 12-byte packet header; None if the packet is malformed."""
    if len(data) < HEADER_LEN:
        return None
    word, session_id, ack_id = struct.unpack_from(">HHH", data, 0)
    (packet_id,) = struct.unpack_from(">H", data, 10)
    length = word & 0x07FF
    if length != len(data):
        return None
    return PacketHeader(word >> 11, length, session_id, ack_id, packet_id)


def build_packet(
    flags: int, session_id: int, packet_id: int = 0, payload: bytes = b"", ack_id: int = 0
) -> bytes:
    length = HEADER_LEN + len(payload)
    header = struct.pack(">HHH4xH", (flags << 11) | length, session_id, ack_id, packet_id)
    return header + payload


def build_ack(session_id: int, packet_id: int) -> bytes:
    return build_packet(FLAG_ACK_REPLY, session_id, ack_id=packet_id)


def build_command(name: str, body: bytes) -> bytes:
    return struct.pack(">H2x4s", 8 + len(body), name.encode("ascii")) + body


def iter_commands(payload: bytes):
    """Yield (name, body) for each command in a packet payload."""
    offset = 0
    while offset + 8 <= len(payload):
        (size,) = struct.unpack_from(">H", payload, offset)
        if size < 8 or offset + size > len(payload):
            break
        name = payload[offset + 4 : offset + 8].decode("ascii", errors="replace")
        yield name, payload[offset + 8 : offset + size]
        offset += size


def _c_string(data: bytes, start: int, size: int) -> str:
    raw = data[start : start + size].split(b"\x00", 1)[0]
    return raw.decode("utf-8", errors="replace").strip()


class AtemState:
    """Subset of switcher state needed for tally."""

    def __init__(self) -> None:
        self.me_count = 0
        self.inputs: dict[int, AtemInput] = {}
        self.tally_by_source: TallyMap | None = None
        self.program: dict[int, int] = {}
        self.preview: dict[int, int] = {}
        self.in_transition: dict[int, bool] = {}
        self.keyer_on_air: dict[tuple[int, int], bool] = {}
        self.keyer_fill: dict[tuple[int, int], int] = {}
        self.init_complete = False
        self.inputs_dirty = False
        self.tally_dirty = False

    def apply(self, name: str, body: bytes) -> None:
        handler = _HANDLERS.get(name)
        if handler is None:
            return
        try:
            handler(self, body)
        except (struct.error, IndexError):
            logger.debug("Ignoring malformed ATEM %s command (%d bytes)", name, len(body))

    def _on_topology(self, body: bytes) -> None:
        self.me_count = body[0]
        self.tally_dirty = True

    def _on_input_properties(self, body: bytes) -> None:
        (input_id,) = struct.unpack_from(">H", body, 0)
        self.inputs[input_id] = AtemInput(
            input_id=input_id,
            long_name=_c_string(body, 2, 20),
            short_name=_c_string(body, 22, 4),
            names_default=body[26] == 1,
            external=body[32] == 0,
        )
        self.inputs_dirty = True

    def _on_tally_by_source(self, body: bytes) -> None:
        (count,) = struct.unpack_from(">H", body, 0)
        tally: TallyMap = {}
        for i in range(count):
            source, flags = struct.unpack_from(">HB", body, 2 + i * 3)
            if flags & 0x03:
                tally[source] = (bool(flags & 0x01), bool(flags & 0x02))
        self.tally_by_source = tally
        self.tally_dirty = True

    def _on_program_input(self, body: bytes) -> None:
        self.program[body[0]] = struct.unpack_from(">H", body, 2)[0]
        self.tally_dirty = True

    def _on_preview_input(self, body: bytes) -> None:
        self.preview[body[0]] = struct.unpack_from(">H", body, 2)[0]
        self.tally_dirty = True

    def _on_transition_position(self, body: bytes) -> None:
        self.in_transition[body[0]] = body[1] == 1
        self.tally_dirty = True

    def _on_keyer_on_air(self, body: bytes) -> None:
        self.keyer_on_air[(body[0], body[1])] = body[2] == 1
        self.tally_dirty = True

    def _on_keyer_properties(self, body: bytes) -> None:
        self.keyer_fill[(body[0], body[1])] = struct.unpack_from(">H", body, 6)[0]
        self.tally_dirty = True

    def _on_init_complete(self, _body: bytes) -> None:
        self.init_complete = True
        self.tally_dirty = True

    def effective_me(self, requested_me: int) -> int:
        """Fall back to M/E 1 when the switcher has fewer M/Es than requested."""
        if self.me_count and requested_me >= self.me_count:
            return 0
        return requested_me

    def tally_for_me(self, me: int) -> TallyMap:
        """Return {source: (program, preview)} for sources with any tally on the given M/E."""
        if me == 0 and self.tally_by_source is not None:
            return dict(self.tally_by_source)

        on_program: set[int] = set()
        on_preview: set[int] = set()
        program_source = self.program.get(me)
        preview_source = self.preview.get(me)
        if program_source is not None:
            on_program.add(program_source)
        if preview_source is not None:
            on_preview.add(preview_source)
            # Mid-transition the incoming source is already on air.
            if self.in_transition.get(me):
                on_program.add(preview_source)
        for (key_me, keyer), on_air in self.keyer_on_air.items():
            fill = self.keyer_fill.get((key_me, keyer))
            if key_me == me and on_air and fill is not None:
                on_program.add(fill)
        return {
            source: (source in on_program, source in on_preview)
            for source in on_program | on_preview
        }


_HANDLERS = {
    "_top": AtemState._on_topology,
    "InPr": AtemState._on_input_properties,
    "TlSr": AtemState._on_tally_by_source,
    "PrgI": AtemState._on_program_input,
    "PrvI": AtemState._on_preview_input,
    "TrPs": AtemState._on_transition_position,
    "KeOn": AtemState._on_keyer_on_air,
    "KeBP": AtemState._on_keyer_properties,
    "InCm": AtemState._on_init_complete,
}


class AtemTallyClient(QThread):
    """Background thread that keeps a session open to an ATEM and emits tally changes."""

    tally_changed = pyqtSignal(object)  # TallyMap
    connection_changed = pyqtSignal(bool)
    inputs_discovered = pyqtSignal(object)  # dict[int, AtemInput]
    me_count_discovered = pyqtSignal(int)

    def __init__(self, ip: str, tally_me: int = 0, port: int = ATEM_PORT, reconnect: bool = True):
        super().__init__()
        self.setObjectName(f"AtemTallyClient-{ip}")
        self.ip = ip
        self.port = port
        self.reconnect = reconnect
        self._requested_me = tally_me
        self._running = False

    def set_tally_me(self, me: int) -> None:
        self._requested_me = me

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        while self._running:
            try:
                self._run_session()
            except OSError as e:
                logger.warning("ATEM %s: network error: %s", self.ip, e)
            except Exception:
                logger.exception("ATEM %s: unexpected error in tally session", self.ip)
            if not self.reconnect:
                break
            deadline = time.monotonic() + RECONNECT_DELAY_S
            while self._running and time.monotonic() < deadline:
                time.sleep(SOCKET_POLL_S)

    def _run_session(self) -> None:
        state = AtemState()
        target = (socket.gethostbyname(self.ip), self.port)
        connected = False
        handshake_done = False
        session_id = 0
        last_packet_id = 0
        started = time.monotonic()
        last_hello = 0.0
        last_receive = started
        emitted_me: int | None = None
        emitted_tally: TallyMap | None = None

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(SOCKET_POLL_S)
            try:
                while self._running:
                    now = time.monotonic()
                    if not state.init_complete and now - started > CONNECT_TIMEOUT_S:
                        logger.info("ATEM %s: no response on UDP %d", self.ip, self.port)
                        return
                    if handshake_done and now - last_receive > RECEIVE_TIMEOUT_S:
                        logger.warning("ATEM %s: connection lost", self.ip)
                        return
                    if not handshake_done and now - last_hello >= HELLO_RETRY_S:
                        sock.sendto(HELLO_PACKET, target)
                        last_hello = now

                    data = self._receive(sock, target[0])
                    header = parse_header(data) if data else None
                    if header is not None:
                        last_receive = now
                        session_id = header.session_id
                        if header.flags & FLAG_NEW_SESSION:
                            handshake_done = True
                            last_packet_id = header.packet_id
                            sock.sendto(build_ack(session_id, last_packet_id), target)
                            continue
                        if handshake_done and header.flags & FLAG_ACK_REQUEST:
                            if header.packet_id == (last_packet_id + 1) % MAX_PACKET_ID:
                                last_packet_id = header.packet_id
                                for name, body in iter_commands(data[HEADER_LEN:]):
                                    state.apply(name, body)
                            # Out-of-order packets are re-acked; the switcher retransmits the gap.
                            sock.sendto(build_ack(session_id, last_packet_id), target)

                    if not state.init_complete:
                        continue
                    if not connected:
                        connected = True
                        logger.info("ATEM %s: connected (%d M/E)", self.ip, state.me_count)
                        self.me_count_discovered.emit(state.me_count)
                        self.connection_changed.emit(True)
                    if state.inputs_dirty:
                        state.inputs_dirty = False
                        self.inputs_discovered.emit(dict(state.inputs))
                    me = state.effective_me(self._requested_me)
                    if state.tally_dirty or me != emitted_me:
                        state.tally_dirty = False
                        emitted_me = me
                        tally = state.tally_for_me(me)
                        if tally != emitted_tally:
                            emitted_tally = tally
                            self.tally_changed.emit(tally)
            finally:
                if connected:
                    self.connection_changed.emit(False)

    @staticmethod
    def _receive(sock: socket.socket, expected_ip: str) -> bytes | None:
        try:
            data, address = sock.recvfrom(2048)
        except (TimeoutError, ConnectionResetError):
            # Windows reports ICMP port-unreachable as ConnectionResetError on UDP.
            return None
        return data if address[0] == expected_ip else None
