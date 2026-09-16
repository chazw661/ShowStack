# ShowStack Listen — A2 beltpack monitoring (Issue #74)

Streams a single beltpack channel to an A2's phone/tablet over the local Wi‑Fi
so they can confirm the right pack and catch headset rattle / lav rub away from
the RF rack.

**Audio never touches ShowStack.** The **ShowStack Listen** Mac app runs on a
wired Mac at the A2 rack, captures an audio input (Dante Virtual Soundcard, a
USB preamp, MADI…), and streams one selected channel to the phone browser via
WebRTC/Opus. ShowStack only authenticates the app to a show and hands it the
slot → channel → presenter mapping.

```
 Axient/DVS ──Dante──▶ Mac (Core Audio) ──▶ ShowStack Listen (menu bar)
                                                   │ WebRTC/Opus (LAN, HTTPS)
                                                   ▼
                                            A2 phone browser
```

---

## 1. Install the app on the rack Mac (once)

1. Unzip `ShowStack-Listen-mac-arm64.zip` and drag **ShowStack Listen.app** to
   **Applications**.
2. Double-click to open it (the release zip is signed with ShowStack's Developer ID
   and notarized by Apple, so macOS opens it normally).
3. When macOS asks, **allow microphone access** — that's how macOS labels access
   to every audio input, including DVS. Without it the app receives silence.
   (Changed your mind? System Settings → Privacy & Security → Microphone.)

A 🎧 icon appears in the menu bar. There's no Dock icon.

## 2. Start it for a show

In ShowStack: **Mic Tracker → A2 view → 🎧 Listen Setup → ▶ Start on this Mac**.
Your browser asks to open ShowStack Listen; the app asks you to confirm the show,
then starts. The Listen Setup status line turns green:
*Connected · Dante Virtual Soundcard · 16 ch · 48 kHz · 0 listeners*.

The app remembers the show and restarts it next time it opens. Turn on
**🎧 menu → Open at Login** for a rack Mac that should always be ready.

## 3. Choose the audio input

**🎧 menu → Audio Input** lists every input on the Mac; the choice is saved.
If there's exactly one Dante input it's picked automatically.

Any Core Audio input works:

* **Dante Virtual Soundcard** (receiver Dante outputs routed to DVS in Dante Controller)
* **USB / Thunderbolt interface** fed from receiver analog or AES outs (RME, MOTU, Focusrite, UAD…)
* **MADI** (e.g. RME MADIface), **AVB**, **SoundGrid**
* An **Aggregate Device** from Audio MIDI Setup if packs are spread across several interfaces

**Channel numbers are the input's numbers.** "Audio ch 12" means input 12 on
that device — use the Mic Tracker **Audio Ch** override when an RF slot isn't
patched to the matching input.

## 4. Set up a phone (once per phone)

iOS Safari only plays this audio over HTTPS with a trusted certificate. The app
makes its own certificate automatically; each phone just trusts it once:

1. **🎧 menu → Set up a phone…** opens a page with QR codes.
2. Scan **Install the certificate** with the phone camera → **Allow** →
   **Settings → Profile Downloaded → Install**.
3. **Settings → General → About → Certificate Trust Settings** → turn on
   **ShowStack Listen**.
4. Scan **Open Listen**, or in ShowStack on the phone open 🎧 Listen Setup →
   **Advanced** and paste the phone Listen address (e.g. `https://192.168.1.42:8443`).
   Then tap **Listen** on any A2 card.

The certificate is limited to local network addresses (`10.x`, `172.16–31.x`,
`192.168.x`, `.local`, `localhost`), so it can't be misused for real websites.
If the Mac's IP changes, the app reissues its server certificate automatically —
phones keep trusting it, only the Listen address changes.

> Venue Wi‑Fi tip: the phone must be on a network that can reach the rack Mac.
> Guest networks with client isolation block this (and Dante‑over‑Wi‑Fi) —
> use a production SSID.

---

## How it behaves

* **Switch channels instantly** from the Listen page dropdown — over a data
  channel with no reconnect, never touching the console signal path.
* **Any sample rate.** The input is opened at whatever rate it's already set to
  (44.1 / 48 / 96 kHz…) and each listener's channel is resampled to 48 kHz for
  Opus. The app never changes a device's rate — on DVS that would retime the
  Dante network.
* **Reconfigure live.** Change DVS channel count or sample rate, restart DVS, or
  unplug/replug an interface: the app notices within ~1 s, reopens the input, and
  logs what changed. Listeners stay connected — they hear silence and see
  *"Audio source lost — waiting for the device…"* until it's back.
* **Ports:** `8443` HTTPS for phones on the LAN; `8480` plain HTTP for this Mac
  only (ShowStack's Start button + status). From other machines, `8480` serves
  only the certificate profile.
* **Logs:** 🎧 menu → Show Log (`~/Library/Logs/ShowStack Listen/companion.log`).
  Settings and certificates live in `~/Library/Application Support/ShowStack Listen/`.

### Security notes

* Start links (`showstack-listen://start?token=…&api=…`) are only accepted from
  `https://showstack.io` (plus `localhost` for development), and switching
  shows always asks for confirmation.
* Every audio/status endpoint requires the show's pairing token.

---

## Building the app

```bash
cd companion
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-app.txt
./build_app.sh            # -> dist/ShowStack Listen.app + dist/ShowStack-Listen-mac-<arch>.zip
```

PyAV (pulled in by `aiortc`) needs FFmpeg libraries: `brew install ffmpeg`.
Plain `./build_app.sh` is ad‑hoc signed (this Mac only). **Release build** —
signed with the Developer ID, notarized and stapled:

```bash
SIGN_IDENTITY="Developer ID Application: charles lawson (D7ZDF3V7MU)" \
NOTARY_PROFILE=showstack-notary ./build_app.sh
```

Needs the Developer ID certificate + private key in the login keychain and the
`showstack-notary` notarytool profile (`xcrun notarytool store-credentials
showstack-notary --apple-id <apple id> --team-id D7ZDF3V7MU`). Builds are for
this Mac's architecture (arm64). A differently-signed build is a new app to
macOS, so it asks for microphone permission again.

Run the menu bar app without building: `python menubar_app.py`.

---

## Advanced — terminal companion

`listen_companion.py` is the same server without the menu bar, handy for testing.

```bash
python listen_companion.py --token <SHOW_LISTEN_TOKEN> --api https://showstack.io
```

* Without `--device` it uses the only Dante input, otherwise lists the inputs and
  asks (and refuses to guess when unattended). A named device that isn't present
  yet is waited for.
* HTTPS uses the same automatic certificate as the app unless you pass
  `--cert`/`--key`. The phone certificate profile is served at
  `http://<mac-ip>:8480/ca.mobileconfig`, and `http://localhost:8480/setup`
  shows the phone setup QR codes.
* **Quick local test, no hardware:** `--test-tone --http` synthesizes a tone per
  channel and serves plain HTTP on `localhost:8443` (WebRTC allows HTTP on
  localhost only). In 🎧 Listen Setup → Advanced, save `http://localhost:8443`.

| Flag | Default | Meaning |
|---|---|---|
| `--token` | *(required)* | Show pairing token (`Project.listen_token`) |
| `--device` | only Dante input, else ask | Input device name (or unique part) or index |
| `--api` | `https://showstack.io` | ShowStack base URL |
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `8443` | HTTPS port (or the HTTP port with `--http`) |
| `--local-port` | `8480` | Plain HTTP for this Mac + certificate profile (0 = off) |
| `--channels` | all device inputs | Capture only the first N inputs |
| `--cert` / `--key` | automatic | Use your own TLS files instead |
| `--no-verify-tls` | off | Skip TLS verify when calling ShowStack |
| `--test-tone` | off | Synthesize a tone per channel (no audio device needed) |
| `--http` | off | Serve plain HTTP only (localhost testing; phones need HTTPS) |
| `--list-devices` | — | List audio devices and exit |

---

## How the mapping works

The app GETs `/audiopatch/api/listen/session/?token=…` from ShowStack and
receives `{ "show": …, "channels": [ {channel, rf_number, presenter, mic_type,
session, day, is_micd}, … ] }`. `channel` is each slot's **effective input
channel** — the RF/slot number unless an A2 overrode it in the Mic Tracker
("Audio Ch" field), so the rack patch does not have to be 1:1. If ShowStack is
briefly unreachable the app still serves audio with generic channel labels.

## Latency & scope

* Target ≤ 200 ms mouth‑to‑ear on a quiet LAN; Opus @ 48 kHz, 20 ms frames.
* One input stream fans out to many listeners; each listener hears one channel.
* Out of scope (later issues): instant replay, RF/battery status, automatic
  rubbing detection, PFL solo, recording.

## Troubleshooting

* **Start on this Mac does nothing** — the app isn't installed/opened once yet
  (right-click → Open), or the browser's "Open ShowStack Listen?" prompt was
  dismissed. Click Start again.
* **Status says "running for a different show"** — click Start on this Mac in the
  show you want; the app asks to switch.
* **"Port 8443 or 8480 is already in use"** — a terminal companion is still
  running; stop it.
* **Meter moves but silence / Source shows but no audio** — check microphone
  permission for ShowStack Listen (System Settings → Privacy & Security → Microphone).
* **Safari "Not Secure" / won't play** — the certificate isn't trusted on the
  phone yet (§4), or you opened it by an address the Mac no longer has.
* **Rejected (403) on the Listen page** — the pairing token is stale; open Listen
  from the A2 view again.
* **No audio / wrong pack** — check the "Audio Ch" override for that slot and the
  🎧 menu's Audio Input.
* **"Audio source lost" on the Listen page** — the input device disappeared
  (DVS stopped/restarting, interface unplugged). It reconnects on its own once
  the device is back; Show Log says what changed.
