"""Headless tests for the Listen companion (no audio device, no network).

Run from companion/:
    venv/bin/python -m unittest discover -s tests -v
"""

import asyncio
import json
import math
import os
import sys
import time
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import listen_companion as lc  # noqa: E402


def page_percent(lin):
    """The Listen page's meterPercent(), ported: -60..0 dBFS -> 0..100."""
    if not lin > 0:
        return 0.0
    db = 20 * math.log10(lin)
    if db <= -60:
        return 0.0
    return min(100.0, (db + 60) / 60 * 100)


# ── meter encoder ───────────────────────────────────────────────────

class MeterBytesTest(unittest.TestCase):

    def test_one_byte_per_channel(self):
        self.assertEqual(len(lc.meter_bytes(np.zeros(64, dtype=np.float32))), 64)
        self.assertIsInstance(lc.meter_bytes(np.zeros(2)), bytes)

    def test_end_points(self):
        b = lc.meter_bytes(np.array([0.0, 1e-9, 0.001, 1.0, 4.0], dtype=np.float32))
        self.assertEqual(list(b), [0, 0, 0, 255, 255])  # silence/floor -> 0, >= 0 dBFS -> 255

    def test_db_scale(self):
        # -30 dBFS is half way up a -60..0 scale.
        v = lc.meter_bytes(np.array([10 ** (-30 / 20)], dtype=np.float32))[0]
        self.assertIn(v, (127, 128))
        # -6 dBFS
        v = lc.meter_bytes(np.array([0.5], dtype=np.float32))[0]
        self.assertEqual(v, round((20 * math.log10(0.5) + 60) * 255 / 60))

    def test_monotonic(self):
        lin = np.logspace(-4, 0, 400).astype(np.float32)
        b = np.frombuffer(lc.meter_bytes(lin), dtype=np.uint8)
        self.assertTrue(np.all(np.diff(b.astype(int)) >= 0))

    def test_matches_page_meter_within_a_step(self):
        # The page draws byte/255*100 for the tiles and meterPercent(peak) for
        # the big meter; the two must agree to within one byte step (0.4 %).
        for lin in np.logspace(-3.5, 0, 50):
            byte = lc.meter_bytes(np.array([lin], dtype=np.float32))[0]
            self.assertAlmostEqual(byte / 255 * 100, page_percent(lin), delta=100 / 255)


# ── crossfade ───────────────────────────────────────────────────────

class _Hub:
    """Just enough of AudioHub for ChannelTrack."""
    def __init__(self):
        self.q = asyncio.Queue()

    def subscribe(self):
        return self.q

    def unsubscribe(self, q):
        pass


def two_mics(blocks, rate=48000):
    """Ch 1: 440 Hz, ch 2: 1 kHz a quarter cycle out — chosen so a hard cut at
    the first block boundary is a ~1.0 step (-0.475 -> +0.5)."""
    n = lc.BLOCK
    t = np.arange(n * blocks) / rate
    a = 0.5 * np.sin(2 * np.pi * 440 * t)
    b = 0.5 * np.sin(2 * np.pi * 1000 * t + np.pi / 2)
    data = np.stack([a, b], axis=1).astype(np.float32)
    return [data[i * n:(i + 1) * n] for i in range(blocks)]


async def play(switches, blocks=3):
    """Run blocks through a ChannelTrack, applying {block_index: [channels]}."""
    hub = _Hub()
    track = lc.ChannelTrack(hub, 1)
    out = []
    for i, blk in enumerate(two_mics(blocks)):
        for ch in switches.get(i, []):
            track.set_channel(ch)
        hub.q.put_nowait((blk, 48000))
        frame = await track.recv()
        out.append(frame.to_ndarray().reshape(-1).astype(np.float32) / 32767.0)
    return np.concatenate(out)


class CrossfadeTest(unittest.TestCase):

    def test_equal_power_law(self):
        n = 384
        ones = np.ones(1000, dtype=np.float32)
        fade_in = lc.equal_power_crossfade(np.zeros(1000, np.float32), ones, n)[:n]
        fade_out = lc.equal_power_crossfade(ones, np.zeros(1000, np.float32), n)[:n]
        np.testing.assert_allclose(fade_in ** 2 + fade_out ** 2, 1.0, atol=1e-5)
        self.assertTrue(np.all(np.diff(fade_in) > 0))

    def test_fade_length_and_tail(self):
        old = np.full(960, 0.3, np.float32)
        new = np.full(960, -0.2, np.float32)
        out = lc.equal_power_crossfade(old, new, 384)
        np.testing.assert_array_equal(out[384:], new[384:])   # all new after the fade
        self.assertAlmostEqual(float(out[0]), 0.3, delta=0.01)  # starts on the old mic
        np.testing.assert_array_equal(lc.equal_power_crossfade(old, new, 0), new)
        self.assertEqual(len(lc.equal_power_crossfade(old, new, 5000)), 960)

    def test_fade_is_5_to_10_ms(self):
        self.assertGreaterEqual(lc.XFADE_SECONDS, 0.005)
        self.assertLessEqual(lc.XFADE_SECONDS, 0.010)

    def _boundary_step(self, audio):
        i = lc.BLOCK                                   # first sample of the switched block
        return float(np.max(np.abs(np.diff(audio[i - 2:i + 400]))))

    def test_switch_is_clickless(self):
        faded = asyncio.run(play({1: [2]}))
        with mock.patch.object(lc, "XFADE_SECONDS", 0.0):
            hard = asyncio.run(play({1: [2]}))
        # The largest sample-to-sample step a 0.5-amplitude 1 kHz sine makes
        # on its own is 2*pi*1000*0.5/48000 = 0.065. A hard cut here steps ~1.0.
        natural = 2 * np.pi * 1000 * 0.5 / 48000
        self.assertGreater(self._boundary_step(hard), 0.5)
        self.assertLess(self._boundary_step(faded), natural * 1.25)

    def test_switch_has_no_splatter(self):
        # A click is broadband energy. Above 6 kHz neither mic has anything,
        # so whatever is there around the switch is the switch itself.
        def hf_energy(audio):
            seg = audio[lc.BLOCK - 480:lc.BLOCK + 480] * np.hanning(960)
            spec = np.abs(np.fft.rfft(seg)) ** 2
            freqs = np.fft.rfftfreq(960, 1 / 48000)
            return float(spec[freqs > 6000].sum())
        faded = asyncio.run(play({1: [2]}))
        with mock.patch.object(lc, "XFADE_SECONDS", 0.0):
            hard = asyncio.run(play({1: [2]}))
        self.assertLess(hf_energy(faded), hf_energy(hard) / 100)   # >= 20 dB less

    def test_fast_switch_back_is_no_fade(self):
        # 1 -> 2 -> 1 before the next block: the A2 never heard 2, so nothing changes.
        straight = asyncio.run(play({}))
        bounced = asyncio.run(play({1: [2, 1]}))
        np.testing.assert_array_equal(straight, bounced)

    def test_fades_from_what_was_heard(self):
        # 1 -> 2 -> 3(silent: beyond the device) before the next block fades
        # from 1, the channel actually playing, into silence.
        out = asyncio.run(play({1: [2, 3]}))
        i = lc.BLOCK
        self.assertLess(float(np.max(np.abs(np.diff(out[i - 2:i + 400])))), 0.08)
        self.assertLess(float(np.max(np.abs(out[i + 400:i + 900]))), 1e-4)


# ── per-phone meter loop ────────────────────────────────────────────

class _DC:
    def __init__(self, state="open"):
        self.readyState = state
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


class _PC:
    connectionState = "connected"


class _Track:
    channel = 1


def make_companion(channels=4):
    hub = lc.AudioHub(device_name=None, test_tone=True, channels=channels)
    hub.peaks = np.full(channels, 0.5, dtype=np.float32)
    return lc.Companion(token="t", hub=hub, mapping=[{"channel": 1, "is_micd": True}],
                        show_name="Show", sessions=[])


class MeterLoopTest(unittest.TestCase):

    def _run_until(self, comp, dc, pc, stop):
        async def go():
            task = asyncio.ensure_future(comp.meter_loop(dc, _Track(), pc, interval=0.01))
            await asyncio.sleep(0.05)
            stop()
            await asyncio.wait_for(task, 1.0)       # raises if the loop never ends
            return task.done()
        return asyncio.run(go())

    def test_ends_when_channel_closes(self):
        dc = _DC()
        self.assertTrue(self._run_until(make_companion(), dc, _PC(),
                                        lambda: setattr(dc, "readyState", "closed")))

    def test_ends_when_peer_closes(self):
        # A peer that dies without the channel ever reporting closed.
        pc = _PC()
        self.assertTrue(self._run_until(make_companion(), _DC(), pc,
                                        lambda: setattr(pc, "connectionState", "closed")))

    def test_ends_when_never_opened(self):
        dc = _DC("connecting")
        self.assertTrue(self._run_until(make_companion(), dc, _PC(),
                                        lambda: setattr(dc, "readyState", "closed")))
        self.assertEqual(dc.sent, [])

    def test_message_order_and_map_resend(self):
        comp = make_companion()
        dc = _DC()

        async def go():
            task = asyncio.ensure_future(comp.meter_loop(dc, _Track(), _PC(), interval=0.01))
            await asyncio.sleep(0.05)
            comp.set_mapping("Show", [{"channel": 1, "is_micd": False}], [])   # mic'd off
            await asyncio.sleep(0.05)
            comp.set_mapping("Show", [{"channel": 1, "is_micd": False}], [])   # unchanged
            await asyncio.sleep(0.05)
            dc.readyState = "closed"
            await task
        asyncio.run(go())

        first = json.loads(dc.sent[0])
        self.assertTrue(first["map"]["channels"][0]["is_micd"])
        self.assertIsInstance(dc.sent[1], bytes)
        self.assertEqual(len(dc.sent[1]), 4)
        self.assertIn("peak", json.loads(dc.sent[2]))
        maps = [json.loads(m)["map"] for m in dc.sent
                if isinstance(m, str) and m.startswith('{"map"')]
        self.assertEqual(len(maps), 2)                 # initial + the one real change
        self.assertFalse(maps[1]["channels"][0]["is_micd"])

    def test_real_peer_close_ends_loop(self):
        # aiortc end to end: when the phone closes its peer, the server-side
        # data channel goes "closed" and the loop exits.
        from aiortc import RTCPeerConnection, RTCConfiguration

        comp = make_companion()

        async def go():
            phone = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            server = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            tasks, opened = [], asyncio.Event()

            @server.on("datachannel")
            def on_dc(dc):
                tasks.append(asyncio.ensure_future(
                    comp.meter_loop(dc, _Track(), server, interval=0.02)))

            ch = phone.createDataChannel("control")
            got = []
            # Opened = a meter frame arrived (the map comes first).
            ch.on("message", lambda m: (got.append(m), isinstance(m, bytes) and opened.set()))
            await phone.setLocalDescription(await phone.createOffer())
            await server.setRemoteDescription(phone.localDescription)
            await server.setLocalDescription(await server.createAnswer())
            await phone.setRemoteDescription(server.localDescription)
            await asyncio.wait_for(opened.wait(), 15)
            await phone.close()
            await asyncio.wait_for(asyncio.gather(*tasks), 15)
            await server.close()
            return got
        got = asyncio.run(go())
        self.assertTrue(any(isinstance(m, bytes) for m in got))


# ── map freshness ───────────────────────────────────────────────────

class MapStateTest(unittest.TestCase):

    def test_version_bumps_only_on_change(self):
        comp = make_companion()
        v = comp.map_version
        comp.set_mapping("Show", [{"channel": 1, "is_micd": True}], [])
        self.assertEqual(comp.map_version, v)
        comp.set_mapping("Show", [{"channel": 1, "is_micd": False}], [])
        self.assertEqual(comp.map_version, v + 1)

    def test_stale_after_30s_without_a_good_fetch(self):
        comp = make_companion()
        now = time.monotonic()
        comp.map_ok_at = now
        with mock.patch.object(lc.time, "monotonic", return_value=now + 29):
            self.assertFalse(comp.map_stale)
        with mock.patch.object(lc.time, "monotonic", return_value=now + 31):
            self.assertTrue(comp.map_stale)
        comp.map_ok_at = None                          # never reached ShowStack
        self.assertTrue(comp.map_stale)

    def test_backoff_schedule(self):
        server = lc.CompanionServer("t", "http://127.0.0.1:9", device_name=None, test_tone=True)
        outcomes = iter([False, False, False, False, True, True])
        delays = []

        async def refresh():
            if not next(outcomes):
                raise lc.MappingUnavailable("down")

        async def fake_sleep(d):
            delays.append(d)
            if len(delays) > 6:
                raise asyncio.CancelledError

        server._refresh_mapping = refresh
        with mock.patch.object(lc.asyncio, "sleep", fake_sleep):
            asyncio.run(server._mapping_loop())
        # ok poll, then four failures backing off 5 -> 10 -> 30 -> 30, then recovered.
        self.assertEqual(delays[:7], [5, 5, 10, 30, 30, 5, 5])

    def test_hung_fetch_never_blocks_and_never_stacks(self):
        server = lc.CompanionServer("t", "http://127.0.0.1:9", device_name=None, test_tone=True)
        server.companion = make_companion()
        server.MAPPING_TIMEOUT = 0.2
        calls = []

        def hang(*a, **k):
            calls.append(1)
            time.sleep(3)
            return "Show", [], []

        async def go():
            with mock.patch.object(lc, "fetch_mapping", hang):
                t0 = time.monotonic()
                with self.assertRaises(lc.MappingUnavailable):
                    await server._refresh_mapping()
                took = time.monotonic() - t0
                with self.assertRaises(lc.MappingUnavailable):   # still hanging: no 2nd thread
                    await server._refresh_mapping()
                return took
        took = asyncio.run(go())
        server._mapping_executor.shutdown(wait=True)
        # Deadline is the request timeout + 1 s grace, far short of the 3 s hang.
        self.assertLess(took, server.MAPPING_TIMEOUT + 1.5)
        self.assertEqual(len(calls), 1)


# ── --simulate ──────────────────────────────────────────────────────

class SimulatorTest(unittest.TestCase):

    def window(self, sim, at_seconds, seconds=0.5):
        """Peak per channel over `seconds` starting at `at_seconds`."""
        sim.n = int(at_seconds * sim.rate)
        return np.max(np.abs(sim.block(int(seconds * sim.rate))), axis=0)

    def db(self, x):
        return 20 * np.log10(max(float(x), 1e-9))

    def test_levels(self):
        sim = lc.Simulator(16)
        p = self.window(sim, 1.0)
        self.assertAlmostEqual(self.db(p[0]), -12, delta=0.2)     # ch1 tone
        self.assertEqual(float(p[2]), 0.0)                        # ch3 silent
        self.assertAlmostEqual(self.db(p[4]), -40, delta=0.2)     # ch5 quiet
        self.assertEqual(float(p[7]), 0.0)                        # ch8 silent
        self.assertAlmostEqual(self.db(p[15]), -0.5, delta=0.1)   # last ch: near clip
        self.assertLess(float(p[15]), 1.0)
        sim.n = sim.rate
        rms = np.sqrt(np.mean(sim.block(sim.rate)[:, 1] ** 2))
        self.assertAlmostEqual(self.db(rms), -20, delta=1.5)      # ch2 pink

    def test_channels_come_alive(self):
        sim = lc.Simulator(16)
        # ch4 bursts: 6 s on in every 24 s, starting at 3*4 = 12 s.
        self.assertEqual(float(self.window(sim, 5.0)[3]), 0.0)
        self.assertGreater(self.db(self.window(sim, 13.0)[3]), -19)
        self.assertEqual(float(self.window(sim, 19.0)[3]), 0.0)
        # ch7 late joiner: silent until 15 + 2*7 = 29 s, then stays.
        self.assertEqual(float(self.window(sim, 20.0)[6]), 0.0)
        self.assertGreater(self.db(self.window(sim, 30.0)[6]), -25)
        self.assertGreater(self.db(self.window(sim, 300.0)[6]), -25)

    def test_pink_is_pink(self):
        x = lc.Simulator._pink_noise(48000 * 4, seed=1)
        spec = np.abs(np.fft.rfft(x)) ** 2
        f = np.fft.rfftfreq(len(x), 1 / 48000)
        low = spec[(f > 100) & (f < 200)].mean()
        high = spec[(f > 1000) & (f < 2000)].mean()
        self.assertAlmostEqual(10 * np.log10(low / high), 10, delta=2)   # -10 dB/decade

    def test_deterministic_and_block_size_independent(self):
        a, b = lc.Simulator(8), lc.Simulator(8)
        one = a.block(4800)
        many = np.concatenate([b.block(960) for _ in range(5)])
        np.testing.assert_allclose(one, many, atol=1e-6)

    def test_hub_label(self):
        hub = lc.AudioHub(device_name=None, simulate=24)
        self.assertEqual(hub.channels, 24)
        self.assertIn("Simulated", hub.source_label)


if __name__ == "__main__":
    unittest.main()
