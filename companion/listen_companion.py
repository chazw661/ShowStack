#!/usr/bin/env python3
"""ShowStack A2 Listen — local companion app (Issue #74).

Runs on a wired Mac at the A2 rack. Captures a Core Audio multichannel input
device (Dante Virtual Soundcard, Axient Digital Dante outputs, etc.) and streams
a single selected channel to a phone/tablet browser on the same LAN over
WebRTC/Opus. ShowStack never receives or relays audio — it only hands this app
the slot -> channel mapping and authenticates it to a show.

Flow:
    1.  Start with the show's pairing token:
            python listen_companion.py --token <UUID> \\
                --device "Dante Virtual Soundcard" \\
                --api https://showstack.io
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
    * HTTPS is mandatory for WebRTC playback in iOS Safari. See README.md for
      the one-time mkcert setup.
"""

import argparse
import asyncio
import json
import logging
import socket
import ssl
import sys
import time
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
    from aiortc import RTCPeerConnection, RTCSessionDescription
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

SAMPLE_RATE = 48000        # DVS / Dante standard; Opus-native
BLOCK = 960                # 20 ms @ 48 kHz -> one Opus frame per block


# ──────────────────────────────────────────────────────────────────
# Audio hub — one input stream, fanned out to every listener
# ──────────────────────────────────────────────────────────────────

class AudioHub:
    """Owns the Core Audio input stream and fans blocks out to listeners.

    The PortAudio callback runs on its own thread, so it hands blocks to the
    asyncio world via loop.call_soon_threadsafe. Each listener gets its own
    bounded queue; if a listener falls behind, its oldest block is dropped
    (audio stays live rather than drifting).
    """

    def __init__(self, device, channels, test_tone=False):
        self.device = device
        self.channels = channels
        self.test_tone = test_tone
        self.loop = None
        self._subscribers = set()          # set[asyncio.Queue]
        self._stream = None
        self._tone_task = None
        self.levels = np.zeros(channels, dtype=np.float32)  # 0..1 RMS per channel

    def start(self, loop):
        self.loop = loop
        if self.test_tone:
            # No audio device: synthesize a distinct tone per channel so the
            # whole path (WebRTC, channel switch, level meter) can be tested on
            # one machine with no mic / DVS / Dante. Channel N ~= 220*N Hz.
            self._tone_task = loop.create_task(self._tone_loop())
            log.info("TEST TONE mode: %d synthetic channels @ %d Hz (no audio device)",
                     self.channels, SAMPLE_RATE)
            return
        self._stream = sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()
        log.info("Audio stream open: device=%s channels=%d @ %d Hz",
                 self.device, self.channels, SAMPLE_RATE)

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
                for q in list(self._subscribers):
                    self._push(q, block)
                await asyncio.sleep(BLOCK / SAMPLE_RATE)
        except asyncio.CancelledError:
            pass

    def stop(self):
        if self._tone_task is not None:
            self._tone_task.cancel()
            self._tone_task = None
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status):
        if status:
            log.debug("audio status: %s", status)
        block = np.copy(indata)  # (frames, channels) float32
        # Per-channel RMS for the level meter (cheap, done once for everyone).
        rms = np.sqrt(np.mean(np.square(block), axis=0))
        self.levels = np.clip(rms, 0.0, 1.0)
        if self.loop is None:
            return
        for q in list(self._subscribers):
            self.loop.call_soon_threadsafe(self._push, q, block)

    @staticmethod
    def _push(q, block):
        if q.full():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            q.put_nowait(block)
        except asyncio.QueueFull:
            pass

    def subscribe(self):
        q = asyncio.Queue(maxsize=8)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self._subscribers.discard(q)


# ──────────────────────────────────────────────────────────────────
# Per-listener audio track — extracts one channel from the hub
# ──────────────────────────────────────────────────────────────────

class ChannelTrack(MediaStreamTrack):
    """A mono WebRTC audio track that emits the listener's selected channel.

    Real-time pacing comes for free from the hub queue: PortAudio delivers one
    block every 20 ms, so awaiting the queue paces recv() at wall-clock rate.
    Switching `self.channel` (1-based) changes which column is emitted on the
    very next block — no renegotiation.
    """

    kind = "audio"

    def __init__(self, hub, channel):
        super().__init__()
        self.hub = hub
        self.channel = channel               # 1-based
        self._queue = hub.subscribe()
        self._pts = 0

    def set_channel(self, channel):
        try:
            channel = int(channel)
        except (TypeError, ValueError):
            return
        if 1 <= channel <= self.hub.channels:
            self.channel = channel

    async def recv(self):
        block = await self._queue.get()      # (frames, channels) float32
        idx = self.channel - 1
        if 0 <= idx < block.shape[1]:
            mono = block[:, idx]
        else:
            mono = np.zeros(block.shape[0], dtype=np.float32)

        pcm = np.clip(mono, -1.0, 1.0)
        pcm16 = (pcm * 32767.0).astype(np.int16).reshape(1, -1)  # (1, samples)

        frame = av.AudioFrame.from_ndarray(pcm16, format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._pts
        frame.time_base = Fraction(1, SAMPLE_RATE)
        self._pts += mono.shape[0]
        return frame

    def stop(self):
        self.hub.unsubscribe(self._queue)
        super().stop()


# ──────────────────────────────────────────────────────────────────
# Web app
# ──────────────────────────────────────────────────────────────────

class Companion:
    def __init__(self, token, hub, mapping, show_name):
        self.token = token
        self.hub = hub
        self.mapping = mapping            # list[dict] from ShowStack (may be empty)
        self.show_name = show_name
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

    async def channels(self, request):
        if not self._check_token(request):
            return web.json_response({"error": "bad token"}, status=403)
        return web.json_response({"show": self.show_name, "channels": self.mapping})

    async def listen_page(self, request):
        # Served regardless of token; the WebRTC /offer below enforces the token.
        return web.Response(text=LISTEN_HTML, content_type="text/html")

    async def offer(self, request):
        params = await request.json()
        if not self._check_token(request, params):
            return web.json_response({"error": "bad token"}, status=403)

        channel = params.get("channel", 1)
        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        self.pcs.add(pc)
        track = ChannelTrack(self.hub, channel)
        pc.addTrack(track)

        @pc.on("datachannel")
        def on_datachannel(dc):
            # Browser opens a "control" channel: it sends {"channel": n} to
            # switch; we push {"level": x, "channel": n} back ~10x/sec.
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
                        level = float(self.hub.levels[idx]) if 0 <= idx < self.hub.channels else 0.0
                        if dc.readyState == "open":
                            dc.send(json.dumps({"level": level, "channel": track.channel}))
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
</style></head>
<body>
<header><h1>🎧 A2 Listen</h1></header>
<main>
  <div>
    <div class="who" id="who">Channel —</div>
    <div class="sub" id="sub"></div>
  </div>
  <div>
    <label for="chan">Channel</label>
    <select id="chan"></select>
  </div>
  <div>
    <label>Level</label>
    <div class="meter-wrap"><div class="meter" id="meter"></div></div>
  </div>
  <div class="status" id="status">Tap Listen to start.</div>
  <button id="go" class="big-btn">▶︎ Listen</button>
  <audio id="audio" autoplay playsinline></audio>
</main>
<script>
const qs = new URLSearchParams(location.search);
const token = qs.get('token') || '';
let channel = parseInt(qs.get('ch') || '1', 10) || 1;
const name = qs.get('name') || '';
const rf = qs.get('rf') || '';
let pc = null, dc = null, mapping = [];

const $ = id => document.getElementById(id);
function label() {
  $('who').textContent = name ? name : ('Channel ' + channel);
  const bits = [];
  if (rf) bits.push('RF ' + rf.padStart(2,'0'));
  bits.push('Audio ch ' + channel);
  $('sub').textContent = bits.join('  ·  ');
}
label();

async function loadChannels() {
  try {
    const r = await fetch('/api/channels?token=' + encodeURIComponent(token));
    if (!r.ok) return;
    const d = await r.json();
    mapping = d.channels || [];
    const sel = $('chan');
    sel.innerHTML = '';
    mapping.forEach(c => {
      const o = document.createElement('option');
      o.value = c.channel;
      o.textContent = 'Ch ' + c.channel + (c.presenter ? ' — ' + c.presenter : (c.rf_number ? ' — RF ' + String(c.rf_number).padStart(2,'0') : ''));
      sel.appendChild(o);
    });
    if (![...sel.options].some(o => +o.value === channel)) {
      const o = document.createElement('option');
      o.value = channel; o.textContent = 'Ch ' + channel; sel.appendChild(o);
    }
    sel.value = channel;
  } catch (e) {}
}
loadChannels();

$('chan').addEventListener('change', e => {
  channel = parseInt(e.target.value, 10) || channel;
  const m = mapping.find(c => c.channel === channel);
  if (m && m.presenter) { $('who').textContent = m.presenter; }
  label();
  if (dc && dc.readyState === 'open') dc.send(JSON.stringify({channel}));
});

async function start() {
  $('go').disabled = true;
  $('status').textContent = 'Connecting…';
  pc = new RTCPeerConnection();
  pc.addTransceiver('audio', {direction: 'recvonly'});
  pc.ontrack = e => { $('audio').srcObject = e.streams[0]; };
  pc.onconnectionstatechange = () => {
    $('status').textContent = pc.connectionState;
    if (['failed','disconnected','closed'].includes(pc.connectionState)) {
      $('go').disabled = false; $('go').textContent = '▶︎ Reconnect';
    }
  };
  dc = pc.createDataChannel('control');
  dc.onmessage = ev => {
    try {
      const d = JSON.parse(ev.data);
      if (typeof d.level === 'number') $('meter').style.width = Math.min(100, d.level*140).toFixed(1) + '%';
    } catch (e) {}
  };
  dc.onopen = () => dc.send(JSON.stringify({channel}));

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  const r = await fetch('/offer', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({sdp: pc.localDescription.sdp, type: pc.localDescription.type, channel, token})
  });
  if (!r.ok) { $('status').textContent = 'Rejected (' + r.status + ')'; $('go').disabled = false; return; }
  const ans = await r.json();
  await pc.setRemoteDescription(ans);
  try { await $('audio').play(); } catch (e) {}
  $('status').textContent = 'Live';
  $('go').textContent = '⏸ Stop';
}

function stop() {
  if (pc) { pc.close(); pc = null; }
  $('meter').style.width = '0%';
  $('status').textContent = 'Stopped.';
  $('go').textContent = '▶︎ Listen'; $('go').disabled = false;
}

$('go').addEventListener('click', () => {
  if (pc && pc.connectionState === 'connected') stop(); else start();
});
// Screen lock / tab backgrounding tears down WebRTC; prompt to reconnect.
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && pc &&
      ['failed','disconnected','closed'].includes(pc.connectionState)) {
    $('status').textContent = 'Reconnect to resume.';
    $('go').disabled = false; $('go').textContent = '▶︎ Reconnect';
  }
});
</script>
</body></html>
"""


# ──────────────────────────────────────────────────────────────────
# Startup helpers
# ──────────────────────────────────────────────────────────────────

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


def resolve_device(name_or_index):
    """Accept a device index, exact name, or case-insensitive substring."""
    if name_or_index is None:
        return None
    try:
        return int(name_or_index)
    except (TypeError, ValueError):
        pass
    needle = str(name_or_index).lower()
    for i, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0 and needle in dev["name"].lower():
            return i
    raise SystemExit("No input device matches %r. Use --list-devices to see options."
                     % name_or_index)


def list_devices():
    print("Available audio devices (input-capable marked with *):")
    for i, dev in enumerate(sd.query_devices()):
        star = "*" if dev.get("max_input_channels", 0) > 0 else " "
        print("  [%2d] %s  %s  (in=%d, out=%d)" % (
            i, star, dev["name"], dev.get("max_input_channels", 0),
            dev.get("max_output_channels", 0)))


def fetch_mapping(api, token, verify_tls=True):
    """Authenticate to the show and pull the channel map. Returns (show, list).

    On a bad token this exits; on a network error it warns and returns generic
    labels so the rack still works if ShowStack is briefly unreachable.
    """
    if requests is None:
        log.warning("'requests' not installed — skipping ShowStack sync.")
        return "", []
    url = api.rstrip("/") + "/audiopatch/api/listen/session/"
    try:
        r = requests.get(url, params={"token": token}, timeout=8, verify=verify_tls)
    except Exception as exc:
        log.warning("Could not reach ShowStack (%s) — serving with generic labels.", exc)
        return "", []
    if r.status_code in (401, 403):
        raise SystemExit("ShowStack rejected the pairing token (HTTP %d). Check --token."
                         % r.status_code)
    if r.status_code != 200:
        log.warning("ShowStack returned HTTP %d — serving with generic labels.", r.status_code)
        return "", []
    data = r.json()
    return data.get("show", ""), data.get("channels", [])


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


def main():
    ap = argparse.ArgumentParser(description="ShowStack A2 Listen companion app")
    ap.add_argument("--token", help="Show pairing token (Project.listen_token)")
    ap.add_argument("--device", help="Input device name (substring) or index, "
                                      "e.g. \"Dante Virtual Soundcard\"")
    ap.add_argument("--api", default="https://showstack.io",
                    help="ShowStack base URL (default: https://showstack.io)")
    ap.add_argument("--host", default="0.0.0.0", help="Bind host (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8443, help="Bind port (default 8443)")
    ap.add_argument("--channels", type=int, default=None,
                    help="Input channel count (default: device max)")
    ap.add_argument("--cert", default="cert.pem", help="TLS cert (mkcert) path")
    ap.add_argument("--key", default="key.pem", help="TLS key (mkcert) path")
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
        device = None
        channels = args.channels or 8
        log.info("TEST TONE mode — no audio device (%d synthetic channels)", channels)
    else:
        device = resolve_device(args.device)
        dev_info = sd.query_devices(device) if device is not None else sd.query_devices(kind="input")
        channels = args.channels or int(dev_info.get("max_input_channels", 0)) or 1
        log.info("Using input device: %s (%d channels)", dev_info["name"], channels)

    show, mapping = fetch_mapping(args.api, args.token, verify_tls=not args.no_verify_tls)
    if show:
        log.info("Paired with show: %s (%d channels mapped)", show, len(mapping))

    scheme = "http" if args.http else "https"
    if args.http:
        ssl_ctx = None
        log.warning("Serving plain HTTP — localhost testing only (phones need HTTPS).")
    else:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_ctx.load_cert_chain(args.cert, args.key)
        except (FileNotFoundError, ssl.SSLError) as exc:
            raise SystemExit(
                "Could not load TLS cert/key (%s).\n"
                "iOS Safari requires HTTPS. Create a local cert with mkcert (see "
                "companion/README.md), or pass --http for a same-Mac localhost test.\n"
                % exc)

    hub = AudioHub(device=device, channels=channels, test_tone=args.test_tone)
    companion = Companion(token=args.token, hub=hub, mapping=mapping, show_name=show)

    app = web.Application()
    app.router.add_get("/", companion.index)
    app.router.add_get("/listen", companion.listen_page)
    app.router.add_get("/api/channels", companion.channels)
    app.router.add_post("/offer", companion.offer)

    async def on_startup(_app):
        # Open the audio stream on the running server loop so the PortAudio
        # callback can hand blocks to it thread-safely.
        hub.start(asyncio.get_event_loop())

    app.on_startup.append(on_startup)
    app.on_shutdown.append(companion.on_shutdown)

    # For --http/localhost testing point at localhost (a secure context for
    # WebRTC); otherwise advertise the LAN IP for phones on the show Wi-Fi.
    host_for_url = "localhost" if args.http else lan_ip()
    url = "%s://%s:%d" % (scheme, host_for_url, args.port)
    print_qr(url + "/listen")
    log.info("Serving on %s  —  paste this into Mic Tracker → 🎧 Listen Setup.", url)

    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_ctx, print=None)


if __name__ == "__main__":
    main()
