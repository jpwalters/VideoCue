"""
Tests for the ATEM tally client: protocol parsing, M/E 2 tally logic and an
end-to-end session against tools/atem_simulator.py.

Run: python -m unittest tests.test_atem_tally -v
"""

import struct
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from atem_simulator import AtemSimulator  # noqa: E402
from PyQt6.QtCore import QCoreApplication, Qt  # noqa: E402

from videocue.controllers import atem_tally  # noqa: E402
from videocue.controllers.atem_tally import (  # noqa: E402
    FLAG_ACK_REQUEST,
    AtemState,
    AtemTallyClient,
    build_ack,
    build_command,
    build_packet,
    iter_commands,
    parse_header,
)


def _state(*commands: tuple[str, bytes]) -> AtemState:
    state = AtemState()
    for name, body in commands:
        state.apply(name, body)
    return state


class ProtocolTests(unittest.TestCase):
    def test_header_round_trip(self):
        packet = build_packet(FLAG_ACK_REQUEST, 0x8123, 42, b"abcd")
        header = parse_header(packet)
        self.assertEqual(header.flags, FLAG_ACK_REQUEST)
        self.assertEqual(header.length, 16)
        self.assertEqual(header.session_id, 0x8123)
        self.assertEqual(header.packet_id, 42)

    def test_ack_matches_atem_connection_layout(self):
        self.assertEqual(build_ack(0x8001, 7).hex(), "800c8001000700000000" + "0000")

    def test_header_rejects_length_mismatch(self):
        packet = build_packet(FLAG_ACK_REQUEST, 1, 1, b"abcd")
        self.assertIsNone(parse_header(packet[:-1]))
        self.assertIsNone(parse_header(b"\x00" * 5))

    def test_iter_commands_splits_and_stops_on_garbage(self):
        payload = build_command("PrgI", b"\x00\x00\x00\x05") + build_command("InCm", b"")
        payload += b"\x00\x03junk"
        self.assertEqual(
            list(iter_commands(payload)), [("PrgI", b"\x00\x00\x00\x05"), ("InCm", b"")]
        )

    def test_tally_by_source(self):
        body = struct.pack(">H", 3) + struct.pack(">HB", 1, 1) + struct.pack(">HB", 2, 2)
        body += struct.pack(">HB", 3, 0)
        state = _state(("TlSr", body))
        self.assertEqual(state.tally_for_me(0), {1: (True, False), 2: (False, True)})

    def test_me1_trusts_switcher_tally_even_when_nothing_is_lit(self):
        no_tally = struct.pack(">H", 2) + struct.pack(">HB", 1, 0) + struct.pack(">HB", 2, 0)
        state = _state(("PrgI", struct.pack(">BxH", 0, 1)), ("TlSr", no_tally))
        self.assertEqual(state.tally_for_me(0), {})

    def test_input_properties(self):
        body = struct.pack(">H20s4sBx HH BxBB", 4, b"Pulpit", b"PLPT", 0, 1, 1, 0, 0x1F, 3)
        state = _state(("InPr", body))
        inp = state.inputs[4]
        self.assertEqual((inp.long_name, inp.short_name), ("Pulpit", "PLPT"))
        self.assertTrue(inp.external)
        self.assertFalse(inp.names_default)

    def test_malformed_command_is_ignored(self):
        state = _state(("PrgI", b"\x01"))
        self.assertEqual(state.program, {})


class MixEffect2TallyTests(unittest.TestCase):
    def _me2(self, *extra: tuple[str, bytes]) -> AtemState:
        return _state(
            ("_top", bytes([2]) + bytes(23)),
            ("PrgI", struct.pack(">BxH", 1, 5)),
            ("PrvI", struct.pack(">BxH4x", 1, 6)),
            ("KeBP", struct.pack(">BBBxBBHH14x", 1, 0, 0, 0, 0, 8, 0)),
            *extra,
        )

    def test_program_and_preview(self):
        self.assertEqual(self._me2().tally_for_me(1), {5: (True, False), 6: (False, True)})

    def test_mid_transition_puts_preview_on_air(self):
        state = self._me2(("TrPs", struct.pack(">BBBxH2x", 1, 1, 10, 5000)))
        self.assertEqual(state.tally_for_me(1), {5: (True, False), 6: (True, True)})

    def test_keyer_on_air_adds_fill(self):
        state = self._me2(("KeOn", struct.pack(">BBBx", 1, 0, 1)))
        self.assertEqual(state.tally_for_me(1)[8], (True, False))

    def test_keyer_off_air(self):
        state = self._me2(("KeOn", struct.pack(">BBBx", 1, 0, 0)))
        self.assertNotIn(8, state.tally_for_me(1))

    def test_me2_falls_back_to_me1_on_single_me_switcher(self):
        state = _state(("_top", bytes([1]) + bytes(23)))
        self.assertEqual(state.effective_me(1), 0)
        self.assertEqual(self._me2().effective_me(1), 1)


class SimulatorSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self._saved = (atem_tally.RECEIVE_TIMEOUT_S, atem_tally.RECONNECT_DELAY_S)
        atem_tally.RECEIVE_TIMEOUT_S = 1.0
        atem_tally.RECONNECT_DELAY_S = 0.5
        self.sim = AtemSimulator(port=0)
        self.sim.start()
        self.events: list[tuple[str, object]] = []
        self.client = AtemTallyClient("127.0.0.1", port=self.sim.port)
        direct = Qt.ConnectionType.DirectConnection
        self.client.connection_changed.connect(lambda c: self.events.append(("conn", c)), direct)
        self.client.tally_changed.connect(lambda t: self.events.append(("tally", t)), direct)
        self.client.inputs_discovered.connect(lambda i: self.events.append(("inputs", i)), direct)
        self.client.start()

    def tearDown(self):
        self.client.stop()
        self.client.wait(3000)
        self.sim.stop()
        atem_tally.RECEIVE_TIMEOUT_S, atem_tally.RECONNECT_DELAY_S = self._saved

    def _wait_for(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return False

    def _last(self, kind: str):
        values = [value for k, value in self.events if k == kind]
        return values[-1] if values else None

    def test_connects_and_reports_me1_tally(self):
        self.assertTrue(self._wait_for(lambda: self._last("conn") is True))
        self.assertTrue(self._wait_for(lambda: self._last("tally") is not None))
        self.assertEqual(self._last("tally"), {1: (True, False), 2: (False, True)})
        self.assertEqual(self._last("inputs")[3].long_name, "Camera 3")

    def test_cut_updates_tally(self):
        self.assertTrue(self._wait_for(lambda: self._last("tally") is not None))
        self.sim.cut(0, 4)
        self.assertTrue(
            self._wait_for(lambda: self._last("tally") == {4: (True, False), 2: (False, True)})
        )

    def test_switch_to_me2(self):
        self.assertTrue(self._wait_for(lambda: self._last("tally") is not None))
        self.sim.cut(1, 6)
        self.sim.set_preview(1, 7)
        self.sim.set_keyer(1, 0, True, fill=8)
        self.client.set_tally_me(1)
        expected = {6: (True, False), 7: (False, True), 8: (True, False)}
        self.assertTrue(self._wait_for(lambda: self._last("tally") == expected))

    def test_recovers_from_lost_packet(self):
        self.assertTrue(self._wait_for(lambda: self._last("tally") is not None))
        self.sim.drop_next = 1
        self.sim.cut(0, 5)
        self.sim.set_preview(0, 6)
        expected = {5: (True, False), 6: (False, True)}
        self.assertTrue(self._wait_for(lambda: self._last("tally") == expected))

    def test_stays_connected_on_keepalives_then_detects_loss(self):
        self.assertTrue(self._wait_for(lambda: self._last("conn") is True))
        time.sleep(atem_tally.RECEIVE_TIMEOUT_S * 2)
        self.assertEqual(self._last("conn"), True)
        self.sim.stop()
        self.assertTrue(self._wait_for(lambda: self._last("conn") is False))


if __name__ == "__main__":
    unittest.main()
