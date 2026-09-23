#!/usr/bin/env python3
"""ShowStack A2 Listen — local companion app (Issue #74).

Runs on a wired Mac at the A2 rack. Captures a Core Audio multichannel input
device (Dante Virtual Soundcard, a USB/MADI/AVB interface, etc.) and streams
a single selected channel to a phone/tablet browser on the same LAN over
WebRTC/Opus. ShowStack never receives or relays audio — it only hands this app
the slot -> channel mapping and authenticates it to a show.

Flow:
    1.  Start with the show's pairing token:
            python listen_companion.py --token <UUID> \\
                --api https://showstack.io          # add --device "<name>" to skip the picker
    2.  The app validates the token against ShowStack, pulls the channel map,
        opens the audio device, and serves an HTTPS page on the LAN. It prints
        (and renders as a QR code) the URL to hand to the A2's phone.
    3.  The A2 opens ShowStack's Mic Tracker A2 view and taps "Listen" on a
        slot, which opens  https://<this-host>:<port>/listen?ch=N  in the
        phone browser. Audio + a live level meter start on tap.

Design notes:
    * A single input stream fans out to every listener (multiple A2s allowed).
    * Each listener picks ONE channel at a time; switching is done over a
      WebRTC data channel (no renegotiation) so it takes well under a second
      and never touches the console signal path.
    * The input device is tracked by name, opened at its native sample rate
      (resampled to 48 kHz per listener) and reopened automatically when it
      changes, disappears, or comes back — see AudioHub / CoreAudioProbe.
    * HTTPS is mandatory for WebRTC playback in iOS Safari; certificates are
      automatic (certs.py) and phones trust them once — see README.md.
"""

import argparse
import asyncio
import json
import logging
import socket
import ssl
import struct
import sys
import threading
import time
import uuid
from fractions import Fraction

import numpy as np

try:
    import sounddevice as sd
except Exception as exc:  # pragma: no cover - dependency guidance
    sys.stderr.write(
        "Missing/broken dependency 'sounddevice' (%s).\n"
        "Install requirements first:  pip install -r requirements.txt\n" % exc
    )
    raise

try:
    import av
    from aiohttp import web
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import MediaStreamTrack
except Exception as exc:  # pragma: no cover - dependency guidance
    sys.stderr.write(
        "Missing/broken dependency (%s).\n"
        "Install requirements first:  pip install -r requirements.txt\n" % exc
    )
    raise

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import qrcode
except Exception:  # pragma: no cover
    qrcode = None


logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("listen")

__version__ = "0.3.0"

SAMPLE_RATE = 48000        # WebRTC/Opus output rate
BLOCK = 960                # 20 ms @ 48 kHz -> one Opus frame
WATCH_INTERVAL = 1.0       # seconds between device health checks
STALL_SECONDS = 2.0        # no audio callbacks for this long -> reopen


# ──────────────────────────────────────────────────────────────────
# Core Audio probe — live device state straight from the HAL (macOS)
# ──────────────────────────────────────────────────────────────────

def _fourcc(code):
    return int.from_bytes(code.encode("ascii"), "big")


class CoreAudioProbe:
    """Reads live input-device state from the Core Audio HAL via ctypes.

    PortAudio caches its device list at init, so it never learns that DVS
    changed channel count, changed sample rate, or restarted. Worse, when the
    device an input stream is bound to goes away, Core Audio's AUHAL quietly
    follows the system default input (the laptop mic) — callbacks keep coming,
    so a stall check alone can't notice. Polling the HAL catches all of it.
    """

    def __init__(self):
        import ctypes
        self._ct = ctypes
        self._ca = ctypes.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self._cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

        class Address(ctypes.Structure):
            _fields_ = [("selector", ctypes.c_uint32),
                        ("scope", ctypes.c_uint32),
                        ("element", ctypes.c_uint32)]
        self._Address = Address

        u32p = ctypes.POINTER(ctypes.c_uint32)
        addrp = ctypes.POINTER(Address)
        self._ca.AudioObjectGetPropertyDataSize.argtypes = [
            ctypes.c_uint32, addrp, ctypes.c_uint32, ctypes.c_void_p, u32p]
        self._ca.AudioObjectGetPropertyDataSize.restype = ctypes.c_int32
        self._ca.AudioObjectGetPropertyData.argtypes = [
            ctypes.c_uint32, addrp, ctypes.c_uint32, ctypes.c_void_p, u32p, ctypes.c_void_p]
        self._ca.AudioObjectGetPropertyData.restype = ctypes.c_int32
        self._cf.CFStringGetCString.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        self._cf.CFStringGetCString.restype = ctypes.c_bool
        self._cf.CFRelease.argtypes = [ctypes.c_void_p]

    def _get(self, obj, selector, scope="glob"):
        ct = self._ct
        addr = self._Address(_fourcc(selector), _fourcc(scope), 0)
        size = ct.c_uint32(0)
        if self._ca.AudioObjectGetPropertyDataSize(obj, ct.byref(addr), 0, None, ct.byref(size)):
            return None
        buf = ct.create_string_buffer(size.value)
        if self._ca.AudioObjectGetPropertyData(obj, ct.byref(addr), 0, None, ct.byref(size), buf):
            return None
        return buf.raw[:size.value]

    def _name(self, obj):
        raw = self._get(obj, "lnam")                     # CFStringRef (+1 retained)
        if not raw or len(raw) != 8:
            return ""
        ref = struct.unpack("Q", raw)[0]
        if not ref:
            return ""
        out = self._ct.create_string_buffer(512)
        ok = self._cf.CFStringGetCString(ref, out, 512, 0x08000100)  # UTF-8
        self._cf.CFRelease(ref)
        return out.value.decode("utf-8", "replace") if ok else ""

    def input_devices(self):
        """{name: (object_id, input_channels, sample_rate)}, or None on error."""
        raw = self._get(1, "dev#")                        # kAudioObjectSystemObject
        if raw is None:
            return None
        devices = {}
        for (obj,) in struct.iter_unpack("I", raw):
            # AudioBufferList: UInt32 count, pad, then 16-byte AudioBuffers
            # whose first field is mNumberChannels.
            cfg = self._get(obj, "slay", "inpt")
            channels = 0
            if cfg and len(cfg) >= 4:
                (count,) = struct.unpack_from("I", cfg, 0)
                for i in range(count):
                    off = 8 + 16 * i
                    if off + 4 <= len(cfg):
                        channels += struct.unpack_from("I", cfg, off)[0]
            if not channels:
                continue
            rate_raw = self._get(obj, "nsrt")
            rate = struct.unpack("d", rate_raw)[0] if rate_raw and len(rate_raw) == 8 else 0.0
            devices[self._name(obj)] = (obj, channels, int(round(rate)))
        return devices

    def fingerprint(self, name):
        devices = self.input_devices()
        if devices is None:
            return None
        return devices.get(name, "missing")


def make_probe():
    if sys.platform != "darwin":
        return None
    try:
        probe = CoreAudioProbe()
        if probe.input_devices() is None:
            return None
        return probe
    except Exception as exc:
        log.warning("Core Audio probe unavailable (%s) — device-change detection "
                    "limited to stall checks.", exc)
        return None


# ──────────────────────────────────────────────────────────────────
# Audio hub — one input stream, fanned out to every listener
# ──────────────────────────────────────────────────────────────────

class AudioHub:
    """Owns the input stream and fans blocks out to listeners.

    The device is tracked by NAME and opened at its own native sample rate
    (the companion never changes a device's rate — on DVS that would retime
    the Dante network). A watchdog reopens the stream whenever the device's
    channel count / sample rate / identity changes, it disappears and comes
    back, or its callbacks stall. While the device is gone, listeners get
    silence so their WebRTC connections stay up.

    The PortAudio callback runs on its own thread, so it hands blocks to the
    asyncio world via loop.call_soon_threadsafe. Each listener gets its own
    bounded queue; if a listener falls behind, its oldest block is dropped
    (audio stays live rather than drifting). Blocks are (ndarray, rate) pairs.
    """

    def __init__(self, device_name, channels=None, test_tone=False):
        self.device_name = device_name
        self.channels_override = channels
        self.test_tone = test_tone
        self.channels = channels or 8 if test_tone else 0
        self.rate = SAMPLE_RATE
        self.loop = None
        self._subscribers = set()          # set[asyncio.Queue]
        self._stream = None
        self._tasks = []
        self._probe = None
        self._fingerprint = None
        self._last_callback = 0.0
        self._waiting_logged = False
        self._reopen_lock = threading.Lock()
        self.levels = np.zeros(self.channels, dtype=np.float32)  # 0..1 RMS per channel
        # Peak per channel with a decay, which is what a receiver's meter shows.
        # RMS alone reads 12-20 dB low on speech and made the page look quiet
        # next to the Shure unit.
        self.peaks = np.zeros(self.channels, dtype=np.float32)

    @property
    def source_label(self):
        """Human-readable source for the Listen page, or None while lost."""
        if self.test_tone:
            return "Test tone · %d ch · 48 kHz" % self.channels
        if self._stream is None:
            return None
        return "%s · %d ch · %s kHz" % (
            self.device_name, self.channels, ("%g" % (self.rate / 1000.0)))

    def start(self, loop):
        self.loop = loop
        if self.test_tone:
            # No audio device: synthesize a distinct tone per channel so the
            # whole path (WebRTC, channel switch, level meter) can be tested on
            # one machine with no mic / DVS / Dante. Channel N ~= 220*N Hz.
            self._tasks.append(loop.create_task(self._tone_loop()))
            log.info("TEST TONE mode: %d synthetic channels @ %d Hz (no audio device)",
                     self.channels, SAMPLE_RATE)
            return
        self._probe = make_probe()
        # Opening a Core Audio device can block for a long time when the HAL or
        # the driver is wedged (a half-dead DVS blocks in Pa_OpenStream ->
        # mach_msg for minutes). On the event loop that freezes the whole web
        # server — the Listen page, /setup and the status polls all hang — so
        # the first open goes to a worker thread like every reopen does.
        # Listeners get silence until it succeeds.
        self._tasks.append(loop.create_task(self._open_initial()))
        self._tasks.append(loop.create_task(self._watch()))
        self._tasks.append(loop.create_task(self._silence_loop()))

    async def _open_initial(self):
        try:
            await self.loop.run_in_executor(None, self._reopen)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.warning("Could not open %r (%s) — the watchdog keeps retrying.",
                        self.device_name, exc)

    # ── device open / close ──────────────────────────────────────

    def _open(self, refresh=True):
        """Open the named device at its native rate. Returns True on success."""
        if refresh:
            # PortAudio only enumerates devices at init; re-init to see changes.
            sd._terminate()
            sd._initialize()
        index = find_device_index(self.device_name)
        if index is None:
            if not self._waiting_logged:
                log.warning("Input device %r not available — sending silence and "
                            "waiting for it to come back…", self.device_name)
                self._waiting_logged = True
            return False

        info = sd.query_devices(index)
        rate = int(round(info.get("default_samplerate") or SAMPLE_RATE))
        max_in = int(info.get("max_input_channels", 0))
        channels = max_in
        if self.channels_override:
            if self.channels_override > max_in:
                log.warning("--channels %d is more than %r has (%d); using %d.",
                            self.channels_override, self.device_name, max_in, max_in)
            channels = min(self.channels_override, max_in)
        if channels < 1:
            return False

        # Fingerprint BEFORE opening, so a change during open still reads as new.
        self._fingerprint = self._probe.fingerprint(self.device_name) if self._probe else None
        try:
            stream = sd.InputStream(
                device=index,
                channels=channels,
                samplerate=rate,
                blocksize=max(1, rate // 50),   # 20 ms at any rate
                dtype="float32",
                callback=self._on_audio,
            )
            stream.start()
        except Exception as exc:
            log.warning("Could not open %r (%s) — retrying.", self.device_name, exc)
            return False

        self.channels = channels
        self.rate = rate
        self.levels = np.zeros(channels, dtype=np.float32)
        self.peaks = np.zeros(channels, dtype=np.float32)
        self._last_callback = time.monotonic()
        self._stream = stream
        self._waiting_logged = False
        log.info("Audio stream open: %s  channels=%d @ %d Hz%s",
                 self.device_name, channels, rate,
                 "" if rate == SAMPLE_RATE else "  (resampling to 48 kHz for listeners)")
        return True

    def _close(self):
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.levels = np.zeros(self.channels, dtype=np.float32)
        self.peaks = np.zeros(self.channels, dtype=np.float32)

    def _reopen(self):
        # Serialised: the watchdog and a user device switch can race.
        with self._reopen_lock:
            self._close()
            return self._open(refresh=True)

    async def switch_device(self, name):
        """Capture from a different input device, keeping every listener connected."""
        if self.test_tone or name == self.device_name:
            return
        log.info("Switching input device: %r -> %r", self.device_name, name)
        self.device_name = name
        self._waiting_logged = False
        await self.loop.run_in_executor(None, self._reopen)

    async def _watch(self):
        """Reopen the stream whenever the device changes, vanishes, or stalls."""
        try:
            while True:
                await asyncio.sleep(WATCH_INTERVAL)
                if self._reopen_lock.locked():
                    continue        # an open is already in flight (maybe stuck)
                reason = None
                if self._stream is None:
                    reason = "retry"
                else:
                    if self._probe is not None:
                        fp = self._probe.fingerprint(self.device_name)
                        if fp is not None and fp != self._fingerprint:
                            reason = "changed %s -> %s" % (
                                _describe_fp(self._fingerprint), _describe_fp(fp))
                    if reason is None and time.monotonic() - self._last_callback > STALL_SECONDS:
                        reason = "no audio for %.0fs" % STALL_SECONDS
                    if reason is None and not self._stream.active:
                        reason = "stream stopped"
                if reason is None:
                    continue
                if reason != "retry":
                    log.warning("Input device %r %s — reopening.", self.device_name, reason)
                elif self._probe is not None and \
                        self._probe.fingerprint(self.device_name) == "missing":
                    continue    # still gone; don't churn PortAudio every second
                await self.loop.run_in_executor(None, self._reopen)
        except asyncio.CancelledError:
            pass

    async def _silence_loop(self):
        """Keep listeners fed with silence while the device is unavailable."""
        try:
            while True:
                await asyncio.sleep(BLOCK / SAMPLE_RATE)
                if self._stream is None and self._subscribers:
                    block = np.zeros((BLOCK, max(1, self.channels)), dtype=np.float32)
                    for q in list(self._subscribers):
                        self._push(q, (block, SAMPLE_RATE))
        except asyncio.CancelledError:
            pass

    async def _tone_loop(self):
        base = np.arange(BLOCK, dtype=np.float32)
        freqs = [220.0 * (c + 1) for c in range(self.channels)]
        n = 0
        try:
            while True:
                block = np.zeros((BLOCK, self.channels), dtype=np.float32)
                for c in range(self.channels):
                    phase = 2.0 * np.pi * freqs[c] * (n + base) / SAMPLE_RATE
                    block[:, c] = 0.2 * np.sin(phase)
                n += BLOCK
                self.levels = np.clip(np.sqrt(np.mean(np.square(block), axis=0)), 0.0, 1.0)
                self.peaks = np.clip(np.max(np.abs(block), axis=0), 0.0, 1.0)
                for q in list(self._subscribers):
                    self._push(q, (block, SAMPLE_RATE))
                await asyncio.sleep(BLOCK / SAMPLE_RATE)
        except asyncio.CancelledError:
            pass

    def stop(self):
        for task in self._tasks:
            task.cancel()
        self._tasks = []
        self._close()

    def _on_audio(self, indata, frames, time_info, status):
        if status:
            log.debug("audio status: %s", status)
        self._last_callback = time.monotonic()
        block = np.copy(indata)  # (frames, channels) float32
        # Per-channel RMS for the level meter (cheap, done once for everyone).
        rms = np.sqrt(np.mean(np.square(block), axis=0))
        self.levels = np.clip(rms, 0.0, 1.0)
        peak = np.max(np.abs(block), axis=0)
        if self.peaks.shape != peak.shape:
            self.peaks = np.zeros_like(peak)
        self.peaks = np.clip(np.maximum(peak, self.peaks * 0.85), 0.0, 1.0)
        if self.loop is None:
            return
        item = (block, self.rate)
        for q in list(self._subscribers):
            self.loop.call_soon_threadsafe(self._push, q, item)

    @staticmethod
    def _push(q, item):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            pass

    def subscribe(self):
        q = asyncio.Queue(maxsize=8)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self._subscribers.discard(q)


def _describe_fp(fp):
    if fp == "missing":
        return "gone"
    if not fp:
        return "unknown"
    _obj, channels, rate = fp
    return "%d ch @ %d Hz (id %d)" % (channels, rate, _obj)


# ──────────────────────────────────────────────────────────────────
# Per-listener audio track — extracts one channel from the hub
# ──────────────────────────────────────────────────────────────────

MAX_CHANNEL = 512


class ChannelTrack(MediaStreamTrack):
    """A mono 48 kHz WebRTC audio track that emits the listener's channel.

    Real-time pacing comes for free from the hub queue: the device delivers
    one 20 ms block at a time, so awaiting the queue paces recv() at wall-clock
    rate. Switching `self.channel` (1-based) changes which column is emitted on
    the very next block — no renegotiation. Blocks from a non-48 kHz device are
    resampled here (per listener, one channel only); the resampler is rebuilt
    if the device's rate changes mid-stream.
    """

    kind = "audio"

    def __init__(self, hub, channel):
        super().__init__()
        self.hub = hub
        self.channel = 1
        self.set_channel(channel)
        self._queue = hub.subscribe()
        self._pts = 0
        self._resampler = None
        self._resampler_rate = None
        self._in_pts = 0
        self._pending = []                   # resampled (1, BLOCK) int16 arrays

    def set_channel(self, channel):
        # Not bounded by the device's current channel count: the device may be
        # mid-reopen. Channels it doesn't have simply play silence.
        try:
            channel = int(channel)
        except (TypeError, ValueError):
            return
        if 1 <= channel <= MAX_CHANNEL:
            self.channel = channel

    def _to_48k(self, pcm16, rate):
        if rate == SAMPLE_RATE:
            self._resampler = None
            self._resampler_rate = None
            return [pcm16]
        if self._resampler_rate != rate:
            self._resampler = av.AudioResampler(
                format="s16", layout="mono", rate=SAMPLE_RATE, frame_size=BLOCK)
            self._resampler_rate = rate
            self._in_pts = 0
        frame = av.AudioFrame.from_ndarray(pcm16, format="s16", layout="mono")
        frame.sample_rate = rate
        frame.pts = self._in_pts
        frame.time_base = Fraction(1, rate)
        self._in_pts += pcm16.shape[1]
        return [f.to_ndarray().reshape(1, -1) for f in self._resampler.resample(frame)]

    async def recv(self):
        while not self._pending:
            block, rate = await self._queue.get()      # (frames, channels) float32
            idx = self.channel - 1
            if 0 <= idx < block.shape[1]:
                mono = block[:, idx]
            else:
                mono = np.zeros(block.shape[0], dtype=np.float32)
            pcm = np.clip(mono, -1.0, 1.0)
            pcm16 = (pcm * 32767.0).astype(np.int16).reshape(1, -1)  # (1, samples)
            self._pending.extend(self._to_48k(pcm16, rate))

        pcm16 = self._pending.pop(0)
        frame = av.AudioFrame.from_ndarray(pcm16, format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._pts
        frame.time_base = Fraction(1, SAMPLE_RATE)
        self._pts += pcm16.shape[1]
        return frame

    def stop(self):
        self.hub.unsubscribe(self._queue)
        super().stop()


# ──────────────────────────────────────────────────────────────────
# Web app
# ──────────────────────────────────────────────────────────────────

class Companion:
    def __init__(self, token, hub, mapping, show_name, sessions=None, extra_status=None):
        self.token = token
        self.hub = hub
        self.sessions = sessions or []    # [{id, name, day, channels: [...]}]
        self.mapping = mapping            # list[dict] from ShowStack (may be empty)
        self.show_name = show_name
        self.extra_status = extra_status  # callable -> dict merged into /api/status
        self.pcs = set()

    def _check_token(self, request, body=None):
        supplied = request.query.get("token") or (body or {}).get("token") or ""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth[7:].strip()
        return supplied == self.token

    async def index(self, request):
        return web.Response(
            text="ShowStack A2 Listen companion is running.\n"
                 "Open /listen?ch=<channel> from the Mic Tracker A2 view.\n",
            content_type="text/plain",
        )

    async def status(self, request):
        """What the companion is doing — polled by ShowStack's Listen Setup."""
        if not self._check_token(request):
            return web.json_response({"error": "bad token"}, status=403)
        return web.json_response(self.status_dict())

    def status_dict(self):
        hub = self.hub
        data = {
            "version": __version__,
            "show": self.show_name,
            "device": hub.device_name or "Test tone",
            "source": hub.source_label,          # null while the device is lost
            "channels": hub.channels,
            "sample_rate": hub.rate,
            "listeners": len(self.pcs),
        }
        if self.extra_status:
            data.update(self.extra_status())
        return data

    async def channels(self, request):
        if not self._check_token(request):
            return web.json_response({"error": "bad token"}, status=403)
        return web.json_response({"show": self.show_name, "channels": self.mapping,
                                  "sessions": self.sessions})

    async def listen_page(self, request):
        # Served regardless of token; the WebRTC /offer below enforces the token.
        return web.Response(text=LISTEN_HTML, content_type="text/html")

    async def offer(self, request):
        params = await request.json()
        if not self._check_token(request, params):
            return web.json_response({"error": "bad token"}, status=403)

        channel = params.get("channel", 1)
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        # LAN only: no STUN. aiortc's default Google STUN server makes every
        # answer wait ~5 s for gathering to time out on isolated show networks
        # (and pushes the phone's play() outside iOS's tap window).
        pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.pcs.add(pc)
        track = ChannelTrack(self.hub, channel)
        pc.addTrack(track)

        @pc.on("datachannel")
        def on_datachannel(dc):
            # Browser opens a "control" channel: it sends {"channel": n} to
            # switch; we push {"level": x, "channel": n, "src": label|null}
            # back ~10x/sec (src is null while the input device is gone).
            @dc.on("message")
            def on_message(msg):
                try:
                    data = json.loads(msg)
                except (ValueError, TypeError):
                    return
                if "channel" in data:
                    track.set_channel(data["channel"])

            async def meter():
                try:
                    while True:
                        idx = track.channel - 1
                        levels = self.hub.levels
                        peaks = self.hub.peaks
                        level = float(levels[idx]) if 0 <= idx < len(levels) else 0.0
                        peak = float(peaks[idx]) if 0 <= idx < len(peaks) else 0.0
                        if dc.readyState == "open":
                            dc.send(json.dumps({"level": level, "peak": peak,
                                                "channel": track.channel,
                                                "src": self.hub.source_label,
                                                "channels": self.hub.channels}))
                        await asyncio.sleep(0.1)
                except Exception:
                    pass
            asyncio.ensure_future(meter())

        @pc.on("connectionstatechange")
        async def on_state():
            log.info("peer %s -> %s", id(pc), pc.connectionState)
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await pc.close()
                self.pcs.discard(pc)

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return web.json_response({
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        })

    async def on_shutdown(self, app):
        for pc in list(self.pcs):
            await pc.close()
        self.pcs.clear()
        self.hub.stop()


# ──────────────────────────────────────────────────────────────────
# Browser page (self-contained: WebRTC playback + level meter + switch)
# ──────────────────────────────────────────────────────────────────

LISTEN_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>A2 Listen</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:-apple-system,system-ui,sans-serif; background:#0d0d1a; color:#eee;
         display:flex; flex-direction:column; min-height:100vh; }
  header { padding:16px; border-bottom:1px solid #2a2a45; }
  h1 { margin:0; font-size:15px; letter-spacing:.08em; text-transform:uppercase; color:#aaa; }
  main { flex:1; padding:20px; display:flex; flex-direction:column; gap:20px; }
  .who { font-size:26px; font-weight:700; }
  .sub { color:#8a8ab0; font-size:13px; margin-top:2px; }
  select { width:100%; padding:12px; font-size:16px; border-radius:8px; background:#1a1a2e;
           color:#eee; border:1px solid #2a2a45; }
  label { font-size:11px; text-transform:uppercase; letter-spacing:.08em; color:#8a8ab0; }
  .meter-wrap { height:26px; background:#16162a; border:1px solid #2a2a45; border-radius:6px; overflow:hidden; }
  .meter { height:100%; width:0%; background:linear-gradient(90deg,#00e676,#ffab00 75%,#ff5252); transition:width .06s linear; }
  button { padding:16px; font-size:17px; font-weight:700; border:none; border-radius:10px;
           background:#4a9eff; color:#fff; cursor:pointer; }
  button:disabled { opacity:.5; }
  .status { font-size:13px; color:#8a8ab0; text-align:center; min-height:18px; }
  .big-btn { position:sticky; bottom:0; }
  .tap { background:#00c853; }
  [hidden] { display:none !important; }
  .src { color:#6a6a90; font-size:12px; margin-top:6px; min-height:16px; }
  .src.lost { color:#ffab00; }
  .meter-db { float:right; color:#8a8ab0; font-variant-numeric:tabular-nums; }
  .scale { display:flex; justify-content:space-between; color:#5a5a78; font-size:10px; margin-top:3px; }
  /* Big enough to grab with a thumb in the dark at FOH. */
  input[type=range] { width:100%; height:38px; accent-color:#4a9eff; }
</style></head>
<body>
<header><h1>🎧 A2 Listen</h1></header>
<main>
  <div>
    <div class="who" id="who">Channel —</div>
    <div class="sub" id="sub"></div>
    <div class="src" id="src"></div>
  </div>
  <div id="sess-row" hidden>
    <label for="sess">Session</label>
    <select id="sess"></select>
  </div>
  <div>
    <label for="chan">Channel</label>
    <select id="chan"></select>
    <div class="src" id="chan-note" hidden>Waiting for the channel list from ShowStack…</div>
  </div>
  <div>
    <label>Level <span id="meter-db" class="meter-db">--</span></label>
    <div class="meter-wrap"><div class="meter" id="meter"></div></div>
    <div class="scale"><span>-60</span><span>-40</span><span>-20</span><span>-6</span><span>0</span></div>
  </div>
  <div>
    <label for="gain">Boost <span id="gain-val">+12 dB</span></label>
    <input type="range" id="gain" min="0" max="36" step="3" value="12">
    <div class="src" id="gain-note"></div>
  </div>
  <div class="status" id="status">Tap Listen to start.</div>
  <button id="tap" class="big-btn tap" hidden>🔊 Tap for sound</button>
  <button id="go" class="big-btn">▶︎ Listen</button>
  <audio id="audio" autoplay playsinline></audio>
</main>
<script>
const qs = new URLSearchParams(location.search);
const token = qs.get('token') || '';
let channel = parseInt(qs.get('ch') || '1', 10) || 1;
let name = qs.get('name') || '';
let rf = qs.get('rf') || '';
let sessionId = qs.get('session') || '';
let pc = null, dc = null, mapping = [], sessions = [];

const $ = id => document.getElementById(id);
function label() {
  $('who').textContent = name ? name : ('Channel ' + channel);
  const bits = [];
  if (rf) bits.push('RF ' + String(rf).padStart(2,'0'));
  bits.push('Audio ch ' + channel);
  // Name the session on a multi-session show: several slots carry the same
  // person in every session, so without this a switch can look like nothing
  // happened at all.
  const s = sessions.length > 1 ? currentSession() : null;
  if (s && s.name) bits.push(s.name);
  $('sub').textContent = bits.join('  ·  ');
}
label();

var METER_FLOOR_DB = -60;
function meterPercent(lin) {
  if (!(lin > 0)) return 0;
  var db = 20 * Math.log10(lin);
  if (db <= METER_FLOOR_DB) return 0;
  return Math.min(100, (db - METER_FLOOR_DB) / (0 - METER_FLOOR_DB) * 100);
}

const STALE_MSG = 'This Listen link is for a different show. Open 🎧 Listen from ShowStack again, ' +
                  'or rescan the QR code from 📱 Set up phones.';
function staleLink() {
  $('status').textContent = STALE_MSG;
  $('status').style.color = '#ffab00';
  $('go').disabled = true;
}
function optionText(c) {
  return 'Ch ' + c.channel + (c.presenter ? ' — ' + c.presenter
    : (c.rf_number ? ' — RF ' + String(c.rf_number).padStart(2,'0') : ''));
}
function sessionText(s) {
  const day = s.day ? s.day.slice(5).replace('-', '/') + ' · ' : '';
  return day + (s.name || 'Session');
}
function currentSession() {
  return sessions.find(s => String(s.id) === String(sessionId)) || sessions[0] || null;
}
// One RF slot is a different presenter in each session, so the channel list is
// always a single session's — never a merge of all of them.
function currentRows() {
  const s = currentSession();
  return s ? s.channels : mapping;
}
function renderSessions() {
  const row = $('sess-row'), sel = $('sess');
  row.hidden = sessions.length < 2;
  if (row.hidden) return;
  const signature = sessions.map(s => s.id + ':' + sessionText(s)).join('|');
  if (sel.dataset.signature !== signature) {
    sel.innerHTML = '';
    sessions.forEach(s => {
      const o = document.createElement('option');
      o.value = s.id; o.textContent = sessionText(s);
      sel.appendChild(o);
    });
    sel.dataset.signature = signature;
  }
  const s = currentSession();
  if (s) { sessionId = s.id; sel.value = s.id; }
}
function renderChannels() {
  const sel = $('chan');
  const rows = currentRows().slice();
  if (!rows.some(c => +c.channel === channel)) rows.push({channel: channel});
  rows.sort((a, b) => a.channel - b.channel);
  const signature = rows.map(optionText).join('|');
  if (sel.dataset.signature !== signature) {
    sel.innerHTML = '';
    rows.forEach(c => {
      const o = document.createElement('option');
      o.value = c.channel;
      o.textContent = optionText(c);
      sel.appendChild(o);
    });
    sel.dataset.signature = signature;
  }
  sel.value = channel;
  $('chan-note').hidden = currentRows().length > 0;
}
function applyChannelLabel() {
  const m = currentRows().find(c => +c.channel === channel);
  name = m ? (m.presenter || '') : '';
  rf = m && m.rf_number ? m.rf_number : '';
  label();
}
// The map can be empty at launch (ShowStack unreachable on a show network) and
// names change during the day, so keep polling rather than loading it once.
async function loadChannels() {
  try {
    const r = await fetch('/api/channels?token=' + encodeURIComponent(token), {cache: 'no-store'});
    if (r.status === 403) { staleLink(); return; }
    if (!r.ok) return;
    const d = await r.json();
    mapping = (d.channels || []).filter(c => c && c.channel);
    sessions = (d.sessions || []).filter(s => s && s.channels && s.channels.length);
  } catch (e) {}
  renderSessions();
  renderChannels();
  label();          // the session name may only now be known
}
loadChannels();
setInterval(loadChannels, 15000);

$('chan').addEventListener('change', e => {
  channel = parseInt(e.target.value, 10) || channel;
  // The name/RF in the URL describe the card that was tapped; once the A2
  // switches channels here, the session's map is what's on air.
  applyChannelLabel();
  if (dc && dc.readyState === 'open') dc.send(JSON.stringify({channel}));
});

$('sess').addEventListener('change', e => {
  sessionId = e.target.value;
  // Stay on the same RF slot across the switch when that session has it —
  // that's the same beltpack, just a different presenter on it.
  const rows = currentRows();
  const sameRf = rf && rows.find(c => String(c.rf_number) === String(rf));
  if (sameRf) channel = sameRf.channel;
  else if (!rows.some(c => +c.channel === channel) && rows.length) channel = rows[0].channel;
  renderChannels();
  applyChannelLabel();
  if (dc && dc.readyState === 'open') dc.send(JSON.stringify({channel}));
});

// iOS Safari only lets audio start from inside the tap. The WebRTC answer comes
// back after the tap, so start the <audio> element NOW on an empty stream and add
// the remote track to that same stream when it arrives.
let remote = null;
// Boost lives in Web Audio: an <audio> element can only attenuate (and on iOS
// its volume is read-only), but hunting a rubbing mic or a loose pack needs
// gain well above unity. A limiter after it keeps a sudden shout from hurting.
const GAIN_KEY = 'a2listen.gainDb';
let gainDb = 12;
try {
  const saved = parseInt(localStorage.getItem(GAIN_KEY), 10);
  if (!isNaN(saved) && saved >= 0 && saved <= 36) gainDb = saved;
} catch (e) {}
let actx = null, gainNode = null, srcNode = null, limiter = null, graphOk = false;
function dbToLin(db) { return Math.pow(10, db / 20); }

function unlockAudio() {
  const audio = $('audio');
  remote = new MediaStream();
  audio.srcObject = remote;
  audio.muted = false;
  audio.play().catch(() => {});
  // iOS only allows an AudioContext to start inside the tap, so make it here
  // even though the track arrives later.
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC && !actx) actx = new AC();
    if (actx && actx.state === 'suspended') actx.resume();
  } catch (e) { actx = null; }
}

function buildAudioGraph() {
  if (!actx || graphOk || !remote) return;
  try {
    srcNode = actx.createMediaStreamSource(remote);
    gainNode = actx.createGain();
    gainNode.gain.value = dbToLin(gainDb);
    limiter = actx.createDynamicsCompressor();
    limiter.threshold.value = -6;
    limiter.knee.value = 0;
    limiter.ratio.value = 20;
    limiter.attack.value = 0.003;
    limiter.release.value = 0.15;
    srcNode.connect(gainNode);
    gainNode.connect(limiter);
    limiter.connect(actx.destination);
    // Web Audio is doing the playback now; leaving the element audible as well
    // would play everything twice.
    $('audio').muted = true;
    graphOk = true;
    $('gain-note').textContent = '';
  } catch (e) {
    // Fall back to plain playback — quieter, but never silent.
    graphOk = false;
    $('audio').muted = false;
    $('gain-note').textContent = 'Boost unavailable on this browser — use the device volume.';
  }
}

function teardownAudioGraph() {
  [srcNode, gainNode, limiter].forEach(function(n) { if (n) { try { n.disconnect(); } catch (e) {} } });
  srcNode = gainNode = limiter = null;
  graphOk = false;
}

function applyGain() {
  $('gain-val').textContent = (gainDb > 0 ? '+' : '') + gainDb + ' dB';
  if (gainNode && actx) {
    // Ramp rather than jump, so changing it mid-show isn't a click in the ear.
    try { gainNode.gain.setTargetAtTime(dbToLin(gainDb), actx.currentTime, 0.02); }
    catch (e) { gainNode.gain.value = dbToLin(gainDb); }
  }
}
$('gain').value = gainDb;
applyGain();
$('gain').addEventListener('input', e => {
  const v = parseInt(e.target.value, 10);
  if (isNaN(v)) return;
  gainDb = v;
  applyGain();
  try { localStorage.setItem(GAIN_KEY, String(gainDb)); } catch (e) {}
});
function needTap() {
  // Still blocked (or paused by iOS): one more direct tap always works.
  $('tap').hidden = false;
}
$('tap').addEventListener('click', () => {
  if (actx && actx.state === 'suspended') { actx.resume().catch(() => {}); }
  buildAudioGraph();
  $('audio').play().then(() => { $('tap').hidden = true; }).catch(() => {});
  if (graphOk && actx && actx.state === 'running') $('tap').hidden = true;
});

async function start() {
  unlockAudio();                       // must stay before the first await
  $('go').disabled = true;
  $('tap').hidden = true;
  $('status').textContent = 'Connecting…';
  pc = new RTCPeerConnection();
  pc.addTransceiver('audio', {direction: 'recvonly'});
  pc.ontrack = e => {
    remote.addTrack(e.track);
    buildAudioGraph();
    $('audio').play().catch(function() { if (!graphOk) needTap(); });
    if (actx && actx.state === 'suspended') needTap();
  };
  pc.onconnectionstatechange = () => {
    if (!pc) return;                   // already torn down by stop()
    $('status').textContent = pc.connectionState;
    if (['failed','disconnected','closed'].includes(pc.connectionState)) {
      pc = null; dc = null;
      $('meter').style.width = '0%';
      $('go').disabled = false; $('go').textContent = '▶︎ Reconnect';
    }
  };
  dc = pc.createDataChannel('control');
  dc.onmessage = ev => {
    try {
      const d = JSON.parse(ev.data);
      // Peak on a dBFS scale. The old bar was linear RMS, which read ~20 dB
      // low against the Shure unit on speech.
      var lin = (typeof d.peak === 'number') ? d.peak : d.level;
      if (typeof lin === 'number') {
        $('meter').style.width = meterPercent(lin).toFixed(1) + '%';
        $('meter-db').textContent = lin > 0.0005
          ? (20 * Math.log10(lin)).toFixed(0) + ' dB' : '-inf';
      }
      if ('src' in d) {
        const lost = !d.src;
        const over = !lost && d.channels && channel > d.channels;
        $('src').textContent = lost ? '⚠︎ Audio source lost — waiting for the device…'
          : over ? '⚠︎ ' + d.src + ' has no channel ' + channel
          : 'Source: ' + d.src;
        $('src').classList.toggle('lost', lost || over);
      }
    } catch (e) {}
  };
  dc.onopen = () => dc.send(JSON.stringify({channel}));

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  const r = await fetch('/offer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sdp: pc.localDescription.sdp, type: pc.localDescription.type, channel, token})
  });
  if (r.status === 403) { stop(); staleLink(); return; }
  if (!r.ok) { $('status').textContent = 'Rejected (' + r.status + ')'; $('go').disabled = false; return; }
  const ans = await r.json();
  await pc.setRemoteDescription(ans);
  try { await $('audio').play(); } catch (e) { needTap(); }
  setTimeout(() => { if (pc && $('audio').paused) needTap(); }, 1500);
  $('status').textContent = 'Live';
  $('go').textContent = '⏸ Stop';
  $('go').disabled = false;            // it's the Stop button now — must stay live
}

function stop() {
  const old = pc;
  pc = null; dc = null;                // before close(), so the state handler no-ops
  if (old) { try { old.close(); } catch (e) {} }
  teardownAudioGraph();
  $('tap').hidden = true;
  $('meter').style.width = '0%';
  $('meter-db').textContent = '--';
  $('status').textContent = 'Stopped.';
  $('go').textContent = '▶︎ Listen'; $('go').disabled = false;
}

$('go').addEventListener('click', () => {
  // Any live peer means the button is Stop, whatever the ICE state is: waiting
  // for 'connected' left it dead while connecting, and a second click used to
  // open a second peer.
  if (pc) { stop(); return; }
  start().catch(e => {
    $('status').textContent = 'Could not start (' + (e && e.message ? e.message : e) + ')';
    stop();
  });
});
// Screen lock / tab backgrounding tears down WebRTC; prompt to reconnect.
document.addEventListener('visibilitychange', () => {
  // The teardown already reset the button; just say why it stopped.
  if (document.visibilityState === 'visible' && !pc &&
      $('go').textContent.indexOf('Reconnect') !== -1) {
    $('status').textContent = 'Reconnect to resume.';
  }
});
</script>
</body></html>
"""


SETUP_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Set up a phone — ShowStack Listen</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family:-apple-system,system-ui,sans-serif; background:#0d0d1a; color:#eee; }
  main { max-width:760px; margin:0 auto; padding:28px 20px 48px; }
  h1 { font-size:20px; margin:0 0 4px; } .show { color:#8a8ab0; font-size:13px; margin-bottom:24px; }
  section { display:flex; gap:16px; padding:18px; margin-bottom:14px; background:#16162a;
            border:1px solid #2a2a45; border-radius:10px; }
  .n { flex:0 0 30px; height:30px; border-radius:50%%; background:#4a9eff; color:#fff; font-weight:700;
       display:flex; align-items:center; justify-content:center; }
  h2 { font-size:15px; margin:3px 0 6px; } p { color:#aaa; font-size:13px; line-height:1.5; margin:0 0 10px; }
  b { color:#eee; } .qr { background:#fff; border-radius:8px; padding:6px; width:184px; max-width:100%%; }
  .qr svg { width:100%%; height:auto; display:block; }
  code { display:block; margin-top:8px; font-size:12px; color:#8a8ab0; word-break:break-all; }
  .note { color:#6a6a90; font-size:12px; line-height:1.5; }
</style></head><body><main>
<h1>🎧 Set up a phone</h1>
<div class="show">Show: %(show)s · phone must be on the same Wi-Fi as this Mac</div>
%(step1)s
%(step2)s
%(step3)s
<p class="note">The certificate only works for local network addresses — it can't be used for
any website. If this Mac's IP address changes, the phone's Listen address changes too
(the certificate stays valid).</p>
</main>
<script>
  // QR codes embed this show's token: refresh when the app switches shows.
  const token = %(token_js)s;
  setInterval(async () => {
    try {
      const r = await fetch('/api/status?token=' + encodeURIComponent(token), {cache: 'no-store'});
      if (r.status === 403) location.reload();
    } catch (e) {}
  }, 5000);
</script>
</body></html>
"""


# ──────────────────────────────────────────────────────────────────
# Startup helpers
# ──────────────────────────────────────────────────────────────────

def computer_name():
    """The Mac's friendly name, for telling racks apart in ShowStack."""
    try:
        import subprocess
        name = subprocess.run(["scutil", "--get", "ComputerName"],
                              capture_output=True, text=True, timeout=2).stdout.strip()
        if name:
            return name[:60]
    except Exception:
        pass
    try:
        return socket.gethostname().replace(".local", "")[:60]
    except Exception:
        return ""


def lan_ip():
    """Best-effort primary LAN IPv4 (no packets actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def input_devices():
    """[(index, info)] for every input-capable device PortAudio can see."""
    return [(i, dev) for i, dev in enumerate(sd.query_devices())
            if dev.get("max_input_channels", 0) > 0]


def find_device_index(name):
    """Current PortAudio index for a device name (exact, else substring)."""
    inputs = input_devices()
    for i, dev in inputs:
        if dev["name"] == name:
            return i
    needle = name.lower()
    for i, dev in inputs:
        if needle in dev["name"].lower():
            return i
    return None


def _print_inputs(inputs, suggested=None):
    for n, (_i, dev) in enumerate(inputs, 1):
        print("  %2d) %s  (%d in @ %g kHz)%s" % (
            n, dev["name"], dev["max_input_channels"],
            dev.get("default_samplerate", 0) / 1000.0,
            "   <- suggested" if suggested is not None and n == suggested else ""))


def pick_device(requested):
    """Resolve --device to a device NAME (the hub reopens by name).

    * --device given: index or name/substring. A name that isn't present yet
      is kept — the companion waits for it (e.g. DVS still starting).
    * No --device: auto-pick when exactly one Dante device exists; otherwise
      ask interactively. Never silently falls back to the built-in mic.
    """
    inputs = input_devices()

    if requested is not None:
        try:
            index = int(requested)
        except (TypeError, ValueError):
            index = None
        if index is not None:
            match = [dev for i, dev in inputs if i == index]
            if not match:
                raise SystemExit("No input device at index %d. Use --list-devices." % index)
            return match[0]["name"]
        found = find_device_index(requested)
        if found is not None:
            return sd.query_devices(found)["name"]
        log.warning("Input device %r isn't available right now — will wait for it. "
                    "Inputs currently present:", requested)
        _print_inputs(inputs)
        return requested

    dante = [dev for _i, dev in inputs if "dante" in dev["name"].lower()]
    if len(dante) == 1:
        log.info("No --device given; using the only Dante input: %s", dante[0]["name"])
        return dante[0]["name"]

    if not inputs:
        raise SystemExit("No audio input devices found. Connect/start your interface "
                         "(or DVS) and try again, or pass --device to wait for it.")
    if not sys.stdin.isatty():
        print("Audio inputs:")
        _print_inputs(inputs)
        raise SystemExit('No --device given. Re-run with --device "<name>" '
                         "(the companion won't guess when unattended).")

    suggested = max(range(len(inputs)),
                    key=lambda n: inputs[n][1]["max_input_channels"]) + 1
    print("\nWhich audio input carries the beltpack channels?")
    _print_inputs(inputs, suggested)
    while True:
        try:
            answer = input("Choose 1-%d [%d]: " % (len(inputs), suggested)).strip()
        except EOFError:
            raise SystemExit("No device chosen.")
        choice = suggested if not answer else (int(answer) if answer.isdigit() else 0)
        if 1 <= choice <= len(inputs):
            name = inputs[choice - 1][1]["name"]
            print('Tip: next time pass  --device "%s"  to skip this question.\n' % name)
            return name
        print("Please enter a number from the list.")


def list_devices():
    print("Available audio devices (input-capable marked with *):")
    for i, dev in enumerate(sd.query_devices()):
        star = "*" if dev.get("max_input_channels", 0) > 0 else " "
        print("  [%2d] %s  %s  (in=%d, out=%d)" % (
            i, star, dev["name"], dev.get("max_input_channels", 0),
            dev.get("max_output_channels", 0)))


class PairingError(Exception):
    """ShowStack rejected the pairing token."""


def fetch_mapping(api, token, verify_tls=True):
    """Authenticate to the show and pull the channel map.

    Returns (show, channels, sessions): `channels` is one entry per audio
    channel, `sessions` is every session with its own labels (the same RF slot
    is a different presenter in each session, so the picker needs both).

    On a bad token this raises PairingError; on a network error it warns and
    returns generic labels so the rack still works if ShowStack is briefly
    unreachable.
    """
    if requests is None:
        log.warning("'requests' not installed — skipping ShowStack sync.")
        return "", [], []
    url = api.rstrip("/") + "/audiopatch/api/listen/session/"
    try:
        r = requests.get(url, params={"token": token}, timeout=8, verify=verify_tls)
    except Exception as exc:
        log.warning("Could not reach ShowStack (%s) — serving with generic labels.", exc)
        return "", [], []
    if r.status_code in (401, 403):
        raise PairingError("ShowStack rejected the pairing token (HTTP %d)." % r.status_code)
    if r.status_code != 200:
        log.warning("ShowStack returned HTTP %d — serving with generic labels.", r.status_code)
        return "", [], []
    data = r.json()
    return (data.get("show", ""), data.get("channels", []),
            data.get("sessions", []))


def print_qr(url):
    print("\n  Listen URL:  %s\n" % url)
    if qrcode is None:
        print("  (install 'qrcode' to render a scannable QR here)\n")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    print()


class CompanionServer:
    """The whole companion — audio hub + web app — runnable from a CLI or an app.

    Runs on its own asyncio loop. `run()` blocks (CLI); `start()` runs it on a
    background thread and returns once the ports are bound (menu bar app, whose
    main thread belongs to Cocoa). Serves up to two sites from one app:

    * HTTPS on `https_port` (all interfaces) for phones on the show Wi-Fi.
    * Plain HTTP on `local_port` for this Mac — WebRTC treats localhost as a
      secure context, and it's what ShowStack's "Start on this Mac" button
      polls. From other machines only `/ca.*` (the phone certificate profile)
      is reachable on this port.
    """

    def __init__(self, token, api, device_name, channels=None, test_tone=False,
                 host="0.0.0.0", https_port=8443, ssl_context=None,
                 local_port=8480, local_lan_ok=False, ca_profile=None, verify_tls=True,
                 instance=None, client_id=None):
        self.token = token
        self.api = api
        # Who this rack is. `instance` is stable for this Mac; `client_id` is
        # the browser that pressed "Start on this Mac" — several Macs can run
        # Listen for one show, and ShowStack keeps their statuses apart.
        self.instance = instance or uuid.uuid4().hex
        self.client_id = client_id or ""
        self.host = host
        self.https_port = https_port if ssl_context is not None else None
        self.ssl_context = ssl_context
        self.local_port = local_port or None
        self.local_lan_ok = local_lan_ok        # CLI --http: whole app on the plain port
        self.ca_profile = ca_profile            # callable -> (bytes, content_type, filename)
        self.verify_tls = verify_tls
        self.hub = AudioHub(device_name=device_name, channels=channels, test_tone=test_tone)
        self.companion = None
        self.loop = None
        self._runner = None
        self._thread = None
        self._ready = threading.Event()
        self._error = None
        self._heartbeat_task = None

    # ── pairing / urls ────────────────────────────────────────────

    def pair(self):
        """Validate the token and pull the channel map (raises PairingError)."""
        show, mapping, sessions = fetch_mapping(self.api, self.token,
                                                verify_tls=self.verify_tls)
        self.companion = Companion(token=self.token, hub=self.hub, mapping=mapping,
                                   show_name=show, sessions=sessions,
                                   extra_status=self._urls)
        if show:
            log.info("Paired with show: %s (%d channels mapped)", show, len(mapping))
        return show

    def _urls(self):
        urls = {"lan_url": None, "local_url": None}
        if self.https_port:
            urls["lan_url"] = "https://%s:%d" % (lan_ip(), self.https_port)
        if self.local_port:
            urls["local_url"] = "http://localhost:%d" % self.local_port
        return urls

    def setup_html(self):
        """'Set up a phone' page: install-certificate QR + Listen QR."""
        import html as _html
        from urllib.parse import quote, urlparse
        ip = lan_ip()
        cert_url = ("http://%s:%d/ca.mobileconfig" % (ip, self.local_port)) \
            if self.local_port and self.ca_profile else None
        lan = self._urls()["lan_url"]
        listen_url = ("%s/listen?token=%s" % (lan, quote(self.token))) if lan else None
        # Opening ShowStack with the address in the URL fragment (never sent to
        # the server) makes the phone remember this Mac for the show, so the
        # normal Listen buttons on A2 cards work. Pointless for a loopback api.
        api_host = (urlparse(self.api).hostname or "").lower()
        showstack_url = None
        if lan and api_host not in ("127.0.0.1", "localhost", "::1"):
            showstack_url = "%s/audiopatch/mic-tracker/#listen=%s&show=%s" % (
                self.api.rstrip("/"), quote(lan, safe=""), self.token[:8])
        show = self.companion.show_name if self.companion else ""

        def qr_svg(data):
            if qrcode is None:
                return ""
            from qrcode.image.svg import SvgPathFillImage
            img = qrcode.make(data, image_factory=SvgPathFillImage, box_size=8, border=2)
            return img.to_string(encoding="unicode")

        def block(n, title, body, url):
            return ('<section><div class="n">%s</div><div><h2>%s</h2><p>%s</p>%s'
                    '<code>%s</code></div></section>') % (
                n, title, body, ('<div class="qr">%s</div>' % qr_svg(url)) if url else "",
                _html.escape(url or "HTTPS is not enabled."))

        return SETUP_HTML % {
            "show": _html.escape(show or "—"),
            "step1": block(1, "Install the certificate (once per phone)",
                           "Scan with the phone camera and open it. Tap <b>Allow</b>, then go to "
                           "<b>Settings → Profile Downloaded → Install</b>.", cert_url),
            "step2": block(2, "Trust it",
                           "<b>Settings → General → About → Certificate Trust Settings</b> → turn on "
                           "<b>ShowStack Listen</b>.", None).replace("<code>HTTPS is not enabled.</code>", ""),
            # Listen first: it needs no ShowStack sign-in and is what an A2
            # scanning the next QR after the certificate expects to get.
            "step3": (block(3, "Open Listen on the phone",
                            "Scan to open the Listen page — no ShowStack sign-in needed. Pick the "
                            "channel from the picker at the top.", listen_url)
                      + block(4, "Optional — open ShowStack too",
                              "Only if this A2 wants the Mic Tracker cards: scan, sign in, and make "
                              "sure this show is the current project. The phone then remembers this "
                              "Mac, so <b>🎧 Listen</b> on any A2 card opens the page above.",
                              showstack_url))
                     if showstack_url else
                     block(3, "Open Listen",
                           "Scan to open the Listen page directly, or paste the address below into "
                           "ShowStack → Mic Tracker → 🎧 Listen Setup → Advanced on the phone.", listen_url),
            "lan": _html.escape(lan or ""),
            "token_js": json.dumps(self.token),
        }

    def status(self):
        if self.companion is None:
            return None
        return self.companion.status_dict()

    # ── app ───────────────────────────────────────────────────────

    def _build_app(self):
        companion = self.companion
        local_port = self.local_port
        local_lan_ok = self.local_lan_ok

        @web.middleware
        async def guard_and_cors(request, handler):
            # The plain-HTTP port is for this Mac only; other machines may
            # fetch the phone certificate profile from it and nothing else.
            if local_port and not local_lan_ok and not request.path.startswith("/ca."):
                sock = request.transport.get_extra_info("sockname") if request.transport else None
                peer = request.transport.get_extra_info("peername") if request.transport else None
                if sock and sock[1] == local_port and peer and \
                        peer[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                    return web.Response(status=403, text="Local access only.\n")
            # ShowStack's Listen Setup (another origin) polls /api/status from
            # the browser. Every /api route still requires the show token.
            # Chrome's Private Network Access preflight (showstack.io ->
            # LAN/localhost) also needs Allow-Private-Network.
            if request.method == "OPTIONS":
                response = web.Response()
            else:
                response = await handler(request)
            if request.path.startswith("/api/"):
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Headers"] = "Authorization"
                response.headers["Access-Control-Allow-Private-Network"] = "true"
            return response

        async def ca_profile(request):
            if self.ca_profile is None:
                raise web.HTTPNotFound()
            body, content_type, filename = self.ca_profile()
            return web.Response(body=body, content_type=content_type, headers={
                "Content-Disposition": 'attachment; filename="%s"' % filename})

        async def options(_request):
            return web.Response()

        async def setup_page(request):
            # Loopback-only (see guard): it embeds the show token.
            return web.Response(text=self.setup_html(), content_type="text/html",
                                headers={"Cache-Control": "no-store"})

        app = web.Application(middlewares=[guard_and_cors])
        app.router.add_get("/", companion.index)
        app.router.add_get("/listen", companion.listen_page)
        app.router.add_get("/api/channels", companion.channels)
        app.router.add_get("/api/status", companion.status)
        app.router.add_route("OPTIONS", "/api/{tail:.*}", options)
        app.router.add_post("/offer", companion.offer)
        app.router.add_get("/ca.mobileconfig", ca_profile)
        app.router.add_get("/setup", setup_page)
        return app

    async def _serve(self):
        if self.companion is None:
            self.pair()
        self._runner = web.AppRunner(self._build_app())
        await self._runner.setup()
        if self.https_port:
            await web.TCPSite(self._runner, self.host, self.https_port,
                              ssl_context=self.ssl_context).start()
            log.info("Phones:    https://%s:%d/listen", lan_ip(), self.https_port)
        if self.local_port:
            await web.TCPSite(self._runner, self.host, self.local_port).start()
            log.info("This Mac:  http://localhost:%d/listen", self.local_port)
        # Open audio on this loop so the PortAudio callback can hand blocks to
        # it thread-safely.
        self.hub.start(asyncio.get_running_loop())
        self._heartbeat_task = asyncio.get_running_loop().create_task(self._heartbeat_loop())

    # ── heartbeat to ShowStack ────────────────────────────────────

    HEARTBEAT_SECONDS = 5
    # The channel map is pulled again on this cadence: ShowStack is often
    # unreachable at launch on a show network (and the names change during the
    # day), and a map that stayed empty leaves the phone's channel picker with
    # nothing to pick.
    MAPPING_SECONDS = 60
    MAPPING_RETRY_SECONDS = 10

    def _client_ssl(self):
        if not self.verify_tls:
            return False
        # A packaged app's Python has no system CA store; use certifi's bundle
        # (the same one `requests` uses for pairing).
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            return ssl.create_default_context()

    async def _post_heartbeat(self, session, payload):
        from aiohttp import ClientTimeout
        url = self.api.rstrip("/") + "/audiopatch/api/listen/heartbeat/"
        if not hasattr(self, "_ssl_ctx"):
            self._ssl_ctx = self._client_ssl()
        async with session.post(url, json=payload, ssl=self._ssl_ctx,
                                headers={"Authorization": "Bearer %s" % self.token},
                                timeout=ClientTimeout(total=8)) as resp:
            return resp.status

    async def _refresh_mapping(self):
        """Pull the channel map again; returns True once we have labels.

        `fetch_mapping` is blocking (requests), so it runs in a worker thread.
        A failure keeps the map we already have — audio never depends on it.
        """
        if self.companion is None:
            return False
        loop = asyncio.get_running_loop()
        try:
            show, mapping, sessions = await loop.run_in_executor(
                None, lambda: fetch_mapping(self.api, self.token, verify_tls=self.verify_tls))
        except PairingError as exc:
            log.warning("%s — keeping the channel labels we have.", exc)
            return bool(self.companion.mapping)
        except Exception as exc:
            log.warning("Channel map refresh failed (%s) — keeping the labels we have.", exc)
            return bool(self.companion.mapping)
        if not mapping and not show:
            return bool(self.companion.mapping)
        had = len(self.companion.mapping)
        self.companion.mapping = mapping
        self.companion.sessions = sessions
        self.companion.show_name = show or self.companion.show_name
        if not had and mapping:
            log.info("Paired with show: %s (%d channels mapped)", show, len(mapping))
        return bool(mapping)

    async def _heartbeat_loop(self):
        """Tell ShowStack what this app is doing, so the Mic Tracker can show it
        in any browser (the page can't reliably reach the Mac directly)."""
        from aiohttp import ClientSession
        warned = False
        next_mapping = time.monotonic() + self.MAPPING_RETRY_SECONDS
        async with ClientSession() as session:
            try:
                while True:
                    if time.monotonic() >= next_mapping:
                        try:
                            have = await self._refresh_mapping()
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            have = False
                        next_mapping = time.monotonic() + (
                            self.MAPPING_SECONDS if have else self.MAPPING_RETRY_SECONDS)
                    try:
                        status = await self._post_heartbeat(
                            session, dict(self.status() or {}, running=True,
                                          instance=self.instance,
                                          client_id=self.client_id,
                                          host=computer_name()))
                        if status >= 400 and not warned:
                            log.warning("ShowStack heartbeat rejected (HTTP %d).", status)
                            warned = True
                        elif status < 400:
                            warned = False
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        if not warned:
                            log.warning("Can't reach ShowStack for status (%s) — audio "
                                        "keeps working; retrying.", exc)
                            warned = True
                    await asyncio.sleep(self.HEARTBEAT_SECONDS)
            except asyncio.CancelledError:
                try:
                    await asyncio.wait_for(self._post_heartbeat(
                        session, dict(self.status() or {}, running=False, listeners=0,
                                      instance=self.instance,
                                      client_id=self.client_id,
                                      host=computer_name())), 3)
                except Exception:
                    pass

    async def _shutdown(self):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except BaseException:
                pass
            self._heartbeat_task = None
        if self.companion is not None:
            for pc in list(self.companion.pcs):
                await pc.close()
            self.companion.pcs.clear()
        self.hub.stop()
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    def run(self):
        """Serve in the foreground until Ctrl-C."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
            self.loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.loop.run_until_complete(self._shutdown())
            self.loop.close()

    def start(self, timeout=15):
        """Serve on a background thread; returns once listening (or raises)."""
        def target():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._serve())
            except BaseException as exc:          # port in use, PairingError, …
                self._error = exc
                self._ready.set()
                self.loop.run_until_complete(self._shutdown())
                self.loop.close()
                return
            self._ready.set()
            self.loop.run_forever()
            self.loop.run_until_complete(self._shutdown())
            self.loop.close()

        self._thread = threading.Thread(target=target, name="listen-companion", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            raise RuntimeError("Companion did not start within %ds." % timeout)
        if self._error is not None:
            raise self._error

    def stop(self, timeout=10):
        if self.loop is None or self._thread is None:
            return
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout)
        self._thread = None

    def set_device(self, name):
        """Switch the capture device live (thread-safe)."""
        if self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.hub.switch_device(name), self.loop)


def main():
    ap = argparse.ArgumentParser(description="ShowStack A2 Listen companion app")
    ap.add_argument("--token", help="Show pairing token (Project.listen_token)")
    ap.add_argument("--device", help="Input device name (substring) or index, e.g. "
                                      "\"Dante Virtual Soundcard\" or \"MADIface\". "
                                      "Omit to choose from a list")
    ap.add_argument("--api", default="https://showstack.io",
                    help="ShowStack base URL (default: https://showstack.io)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind host (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8443, help="Bind port (default 8443)")
    ap.add_argument("--local-port", type=int, default=8480,
                    help="Also serve plain HTTP for this Mac on this port (0 = off; "
                         "ignored with --http)")
    ap.add_argument("--channels", type=int, default=None,
                    help="Capture only the first N inputs (default: all the device has)")
    ap.add_argument("--cert", default=None,
                    help="TLS cert path (default: automatic local certificate)")
    ap.add_argument("--key", default=None, help="TLS key path (with --cert)")
    ap.add_argument("--no-verify-tls", action="store_true",
                    help="Skip TLS verification when calling ShowStack")
    ap.add_argument("--test-tone", action="store_true",
                    help="Synthesize a tone per channel instead of opening an "
                         "audio device (local testing — no mic/DVS/Dante needed)")
    ap.add_argument("--http", action="store_true",
                    help="Serve plain HTTP instead of HTTPS. WebRTC allows this "
                         "on localhost only — use for same-Mac testing, never a phone")
    ap.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = ap.parse_args()

    if args.list_devices:
        list_devices()
        return
    if not args.token:
        ap.error("--token is required (get it from Mic Tracker → 🎧 Listen Setup)")

    if args.test_tone:
        device_name = None
        log.info("TEST TONE mode — no audio device (%d synthetic channels)",
                 args.channels or 8)
    else:
        device_name = pick_device(args.device)
        log.info("Using input device: %s", device_name)

    ca_profile = None
    if args.http:
        ssl_ctx = None
        log.warning("Serving plain HTTP — localhost testing only (phones need HTTPS).")
    elif args.cert and args.key:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_ctx.load_cert_chain(args.cert, args.key)
        except (FileNotFoundError, ssl.SSLError) as exc:
            raise SystemExit("Could not load TLS cert/key (%s)." % exc)
    else:
        # Automatic local CA + server cert (see certs.py). Phones install the
        # CA once from http://<this-mac>:<local-port>/ca.mobileconfig.
        import certs
        ssl_ctx, sans = certs.server_ssl_context()
        ca_profile = certs.ca_mobileconfig
        log.info("HTTPS certificate covers: %s", ", ".join(sans["ips"] + sans["dns"]))
        if args.local_port:
            log.info("Phone certificate (install once): http://%s:%d/ca.mobileconfig",
                     lan_ip(), args.local_port)

    server = CompanionServer(
        token=args.token, api=args.api, device_name=device_name,
        channels=args.channels, test_tone=args.test_tone, host=args.host,
        # --http keeps the old single-port behaviour on --port.
        https_port=None if args.http else args.port, ssl_context=ssl_ctx,
        local_port=args.port if args.http else args.local_port,
        local_lan_ok=args.http,
        ca_profile=ca_profile,
        verify_tls=not args.no_verify_tls,
    )
    try:
        server.pair()
    except PairingError as exc:
        raise SystemExit("%s Check --token." % exc)

    # For --http/localhost testing point at localhost (a secure context for
    # WebRTC); otherwise advertise the LAN IP for phones on the show Wi-Fi.
    url = ("http://localhost:%d" % args.port) if args.http else \
        ("https://%s:%d" % (lan_ip(), args.port))
    print_qr(url + "/listen")
    log.info("Serving on %s  —  paste this into Mic Tracker → 🎧 Listen Setup.", url)
    server.run()


if __name__ == "__main__":
    main()
