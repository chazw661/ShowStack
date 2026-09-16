# ShowStack A2 Listen — companion app

Streams a single beltpack channel to an A2's phone/tablet over the local Wi‑Fi
so they can confirm the right pack and catch headset rattle / lav rub away from
the RF rack. Built for Issue #74.

**Audio never touches ShowStack.** This app runs on a wired Mac at the A2 rack,
captures a Core Audio multichannel device (Dante Virtual Soundcard or Axient
Digital Dante outputs), and streams one selected channel to the phone browser
via WebRTC/Opus. ShowStack only authenticates the app to a show and hands it the
slot → channel → presenter mapping.

```
 Axient/DVS ──Dante──▶ Mac (Core Audio) ──sounddevice──▶ this app
                                                           │ WebRTC/Opus (LAN)
                                                           ▼
                                                    A2 phone browser
```

---

## 1. One-time setup on the rack Mac

```bash
cd companion
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

PyAV (pulled in by `aiortc`) needs FFmpeg libraries. On macOS:

```bash
brew install ffmpeg
```

### HTTPS is required (iOS Safari)

iOS Safari refuses WebRTC audio on plain HTTP, so the companion serves HTTPS
with a locally‑trusted certificate made by [mkcert](https://github.com/FiloSottile/mkcert):

```bash
brew install mkcert nss
mkcert -install                       # installs a local root CA on the Mac

# Issue a cert for this Mac's LAN name/IP. List every address the phone might use.
mkcert -cert-file cert.pem -key-file key.pem \
    listen.local 192.168.1.42 localhost
```

Put `cert.pem` / `key.pem` next to `listen_companion.py` (or pass `--cert` /
`--key`).

**On each A2 phone (once):** install the mkcert **root CA** so Safari trusts the
cert. Easiest path: AirDrop/email the file printed by `mkcert -CAROOT`
(`rootCA.pem`) to the phone, open it, then
**Settings → General → VPN & Device Management → install profile**, and
**Settings → General → About → Certificate Trust Settings → enable full trust**.
This is a one‑time step per device.

> Venue Wi‑Fi tip: use the Mac's **IP address** in both the mkcert cert and the
> URL. Many guest/venue networks block mDNS (`.local`) and multicast — the same
> reason Dante‑over‑Wi‑Fi isn't viable here.

---

## 2. Choose your audio input

Any Core Audio input works — not just Dante:

* **Dante Virtual Soundcard** (receiver Dante outputs routed to DVS in Dante Controller)
* **USB / Thunderbolt interface** fed from receiver analog or AES outs (RME, MOTU, Focusrite, UAD…)
* **MADI** (e.g. RME MADIface), **AVB**, **SoundGrid**
* An **Aggregate Device** from Audio MIDI Setup if packs are spread across several interfaces

```bash
python listen_companion.py --list-devices
```

Pass the name (or a unique part of it) as `--device`. If you leave `--device`
off, the companion uses the only Dante input if there is exactly one; otherwise
it lists the inputs and asks you to pick. It never silently falls back to the
built‑in mic, and when run unattended (no terminal) it refuses to guess.

**Channel numbers are the device's input numbers.** "Audio ch 12" means input 12
on that device — use the Mic Tracker **Audio Ch** override when an RF slot isn't
patched to the matching input.

---

## 3. Run it

Get the **pairing token** and the ready‑made launch command from ShowStack:
**Mic Tracker → A2 view → 🎧 Listen Setup**.

```bash
python listen_companion.py \
    --token <SHOW_LISTEN_TOKEN> \
    --api https://showstack.io
```

With DVS as the only Dante input it's selected automatically; otherwise you're
asked to pick. Add `--device "<name>"` to skip the question (required when the
companion runs unattended, e.g. from a launch agent).

On start it authenticates to the show, opens the audio device, and
prints a **QR code + URL** (e.g. `https://192.168.1.42:8443/listen`). Hand that
to the A2.

### How the A2 connects

1. In the ShowStack A2 view, tap **🎧 Listen Setup** and paste the companion's
   address (scan the QR with the phone camera, then paste), or type it. It's
   saved on that device.
2. Tap **Listen** on any slot. The phone opens the companion's Listen page for
   that slot's audio channel, shows the presenter name + a live level meter, and
   plays the beltpack on tap.
3. Switch channels from the dropdown — it changes instantly over a data channel
   with no reconnect, and never touches the console signal path.

### Device changes, dropouts & sample rate

* **Any sample rate.** The device is opened at whatever rate it's already set to
  (44.1 / 48 / 96 kHz…) and each listener's channel is resampled to 48 kHz for
  Opus. The companion never changes a device's rate — on DVS that would retime
  the Dante network.
* **Reconfigure live.** Change DVS channel count or sample rate, restart DVS, or
  unplug/replug an interface: the companion notices within ~1 s (it watches the
  Core Audio device directly), reopens it, and logs what changed. Listeners stay
  connected — they hear silence while the device is gone and the Listen page
  shows *"Audio source lost — waiting for the device…"* until it's back.
* **Started before the device?** If `--device` names something that isn't
  present yet (DVS still starting), the companion starts anyway and waits for it.
* The Listen page shows the live source, e.g. *Source: Dante Virtual Soundcard ·
  16 ch · 48 kHz*, and warns if the chosen channel is above the device's count.

---

## Quick local test — no DVS, no mic, no cert

To prove the whole path on a single Mac without any audio hardware or HTTPS
setup, use `--test-tone` (synthesizes a distinct tone per channel) and `--http`
(plain HTTP, which WebRTC allows on `localhost`):

```bash
cd companion
source venv/bin/activate            # after the one-time pip install
python listen_companion.py \
    --test-tone --http \
    --token <SHOW_LISTEN_TOKEN> \
    --api http://127.0.0.1:8000      # your local runserver
```

It prints `http://localhost:8443`. In the ShowStack A2 view → **🎧 Listen
Setup**, paste **`http://localhost:8443`** (note: `http`, not `https`, for this
mode), then tap **Listen** on a slot and open it in Chrome on the same Mac. You
should hear a tone, see the meter move, and be able to switch channels live.

> `--http` is localhost-only — phones still need HTTPS (the mkcert steps above).

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--token` | *(required)* | Show pairing token (`Project.listen_token`) |
| `--device` | only Dante input, else ask | Input device name (or unique part) or index |
| `--api` | `https://showstack.io` | ShowStack base URL |
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `8443` | Bind port |
| `--channels` | all device inputs | Capture only the first N inputs |
| `--cert` / `--key` | `cert.pem` / `key.pem` | mkcert TLS files |
| `--no-verify-tls` | off | Skip TLS verify when calling ShowStack |
| `--test-tone` | off | Synthesize a tone per channel (no audio device needed) |
| `--http` | off | Serve plain HTTP (localhost testing only; phones need HTTPS) |
| `--list-devices` | — | List audio devices and exit |

---

## How the mapping works

The companion GETs `/audiopatch/api/listen/session/?token=…` from ShowStack and
receives `{ "show": …, "channels": [ {channel, rf_number, presenter, mic_type,
session, day, is_micd}, … ] }`. `channel` is each slot's **effective input
channel** — the RF/slot number unless an A2 overrode it in the Mic Tracker
("Audio Ch" field), so the rack patch does not have to be 1:1. If ShowStack is
briefly unreachable the app still serves audio with generic channel labels.

---

## Latency & scope

* Target ≤ 200 ms mouth‑to‑ear on a quiet LAN; Opus @ 48 kHz, 20 ms frames.
* One input stream fans out to many listeners; each listener hears one channel.
* Out of scope (later issues): instant replay, RF/battery status, automatic
  rubbing detection, PFL solo, recording.

## Troubleshooting

* **"Could not load TLS cert/key"** — create `cert.pem`/`key.pem` with mkcert (§1).
* **Safari "Not Secure" / won't play** — the mkcert root CA isn't trusted on the
  phone yet, or you reached it by an address not listed in the cert.
* **Rejected (403) on the Listen page** — the pairing token is stale; re‑copy it
  from 🎧 Listen Setup.
* **No audio / wrong pack** — check the "Audio Ch" override for that slot and
  confirm the Dante patch into the capture device with `--list-devices`.
* **"Audio source lost" on the Listen page** — the input device disappeared
  (DVS stopped/restarting, interface unplugged). It reconnects on its own once
  the device is back; check the companion log for what changed.
