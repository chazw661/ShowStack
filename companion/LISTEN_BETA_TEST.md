# Listen grid Phase 1 — beta test from source

Branch `listen-grid-phase1`, companion **0.4.0**. This round runs from source on
the MacBook Air. **Do not run `./build_app.sh`.** It rebuilds
`companion/dist/ShowStack Listen.app`, and that 0.3.2 build is the rollback
copy (there is no copy in /Applications on this Mac).

What's new on the phone: a channel grid (name, meter and Mic'd **ON** pill per
slot), a collapsed **Other channels (N)** section for inputs that aren't in the
show's map, a click-free channel switch, a "Mic'd state stale" note when
ShowStack can't be reached, and a "Listen app offline — meters held" banner
when the Mac stops sending meters.

Nothing changes on showstack.io: no Django, template, migration or static files
are touched.

---

## 0. What runs where

|                     | Installed app (0.3.2)                        | Source build (this branch)               |
|---------------------|----------------------------------------------|------------------------------------------|
| Started from        | `companion/dist/ShowStack Listen.app`        | `companion/venv/bin/python listen_companion.py` |
| Phones (HTTPS)      | `:8443`                                      | `:8444` (`--port 8444`)                  |
| This Mac (HTTP)     | `:8480`                                      | `:8481` (`--local-port 8481`)            |
| ShowStack 🎧 buttons | point here (`localhost:8480` on the Mac, saved `:8443` on phones) | not used — open the page directly |
| Certificate         | `~/Library/Application Support/ShowStack Listen/` | **the same files**                  |

Because the certificate is shared, a phone that already trusts *ShowStack
Listen* trusts the source build too. There's nothing to install on the phone.

**Can both run at once?** Yes, as far as ports go: they use different ones.
For DVS, Core Audio normally lets several apps capture the same input device,
but this has **not been verified with DVS** (DVS isn't installed on the Air
right now). That's the first thing to check at the venue (§3). If the two
can't share DVS, swap them (§4).

While the source build runs, ShowStack's Listen Setup lists a second rack for
the show with the same Mac name. It shows as not running about 20 s after you
stop it, and drops off the list after 10 min.

---

## 1. One-time setup (MacBook Air)

```bash
cd ~/DjangoProjects/audiopatch
git fetch origin
git checkout listen-grid-phase1
cd companion

# The venv already exists here (Python 3.14). This is a no-op if it's current:
venv/bin/pip install -r requirements.txt
# Only if venv/ is missing:
#   python3 -m venv venv && venv/bin/pip install -r requirements.txt

# Headless tests — expect "Ran 26 tests ... OK"
venv/bin/python -m unittest discover -s tests
```

The show token is in ShowStack → **Mic Tracker → 🎧 Listen Setup → Advanced**
(it's the `--token` value in the launch command there):

```bash
export TOKEN=paste-the-show-token-here
```

---

## 2. Home test — `--simulate` (no DVS needed)

Pick a test show with a few slots and Mic'd set on some of them.

```bash
cd ~/DjangoProjects/audiopatch/companion
venv/bin/python listen_companion.py --token "$TOKEN" --api https://showstack.io \
    --simulate 24 --port 8444 --local-port 8481
```

Open it on the phone (same Wi-Fi as the Mac) in either of these ways:
- Scan the QR the terminal prints. It now includes the token.
- On the Mac, open <http://localhost:8481/setup> and scan **Open Listen**.
- Or type `https://<mac-ip>:8444/listen?token=<TOKEN>`. To find the IP, run
  `ipconfig getifaddr en0`.

On the Mac itself: <http://localhost:8481/listen?token=...>.

### What `--simulate 24` plays

The pattern repeats every 8 channels. The last channel is always the
near-clip one.

| Channels       | Behaviour                                                                    |
|----------------|------------------------------------------------------------------------------|
| 1, 9, 17       | steady tone, −12 dBFS peak                                                   |
| 2, 10, 18      | pink noise, −20 dBFS RMS                                                     |
| 3, 11, 19      | silent                                                                       |
| 4, 12, 20      | bursts: −18 dBFS tone, 6 s on in every 24 s, starting at 3 s × channel        |
| 5, 13, 21      | quiet tone, −40 dBFS                                                         |
| 6, 14, 22      | speech-like: pink noise in 4 Hz syllables, 3 s on / 1 s off                  |
| 7, 15, 23      | late joiner: silent until 15 s + 2 s × channel after start, then −24 dBFS tone |
| 8, 16          | silent                                                                       |
| 24             | near clip: −0.5 dBFS tone (meter goes into the red)                          |

Which channels land in **Other channels** depends on how many slots the show
maps. With a 16-slot show it's 17–24.

### Checklist

1. **Grid.** One tile per slot in the selected session. Names and RF numbers
   match the Mic Tracker. ON pills match the Mic'd toggles. The Session picker
   still switches sessions.
2. **Tap to listen.** Tapping any tile starts audio. Tapping another switches
   with no reconnect.
3. **No click on switch.** Use headphones with Boost at +12 dB. Switch back and
   forth between a tone (ch 1) and pink noise (ch 2) a dozen times. You should
   hear a fast blend, never a tick or pop.
4. **ON-pill freshness.** Toggle Mic'd on a slot in the Mic Tracker. The pill
   should follow within about 5 s (measured locally at 0.7–5.1 s).
5. **Other channels.** Open the section. Tiles stay in channel order and
   never move. Each has a dot that lights while the input is above −50 dB and
   goes dark within about 1 s of it stopping. A burst channel (4/12/20) lights
   for its 6 s and goes dark; a late joiner (7/15/23) lights once its start
   time passes and stays lit; silent ones (3/8/11/16/19) stay dark.
6. **Not in map.** Tap a tile under Other channels. It moves to the top of the
   main grid with a **NOT IN MAP** tag.
7. **Near clip.** Ch 24's meter runs into amber, then red.
8. **Offline banner.** Press Ctrl-C on the Mac. Within about 1 s the phone
   shows **Listen app offline — meters held**, the grid dims, and the meters
   freeze instead of dropping to zero. Restart the command and tap
   **▶︎ Reconnect**. The banner clears when the first meters arrive.
9. **Stale note** (optional). Unplug the router's internet (WAN) cable and
   leave the Wi-Fi up. After about 30 s the page says **Mic'd state stale —
   can't reach ShowStack. Listening still works.** Audio and meters carry on.
   Plug it back in; the note clears within about 30 s (retries back off
   5 → 10 → 30 s).
10. **Sleep/wake.** Lock the phone for 30 s and unlock it. Audio recovers as in
    0.3.2, or you get *Tap for sound*.

Stop with Ctrl-C.

---

## 3. Venue test — DVS

DVS running at its usual rate. The installed app can stay running.

```bash
cd ~/DjangoProjects/audiopatch/companion
venv/bin/python listen_companion.py --list-devices          # DVS should be listed with in=N
venv/bin/python listen_companion.py --token "$TOKEN" --api https://showstack.io \
    --device "Dante Virtual Soundcard" --port 8444 --local-port 8481
```

Expect `Audio stream open: Dante Virtual Soundcard  channels=N @ R Hz` in the
log.

**First, the sharing check.** With both running, confirm that:
- a phone on the installed app (normal 🎧 Listen from ShowStack, `:8443`) still
  hears audio, **and**
- a phone on the source build (`:8444`) hears audio.

If either goes silent, or the source build keeps logging `Could not open` or
`has not responded`, go to §4.

Then run checklist items 1–8 from §2 with real packs, plus:
- Real mic'd state: the A2 toggles Mic'd during the show and the pills follow
  within about 5 s.
- A live pack that isn't in the map floats to the top of Other channels.
- Switching between two live lavs at 96 kHz is click-free.
- Walk the phone out of Wi-Fi range and back. You get the offline banner, then
  Reconnect.

---

## 4. Swap — only if the two can't share DVS

1. Quit the installed app: menu bar 🎧 → **Quit**.
2. Start the source build on the **default** ports, so ShowStack's 🎧 buttons
   and phones' saved addresses reach it:
   ```bash
   venv/bin/python listen_companion.py --token "$TOKEN" --api https://showstack.io \
       --device "Dante Virtual Soundcard"
   ```
3. Hard-reload the Listen page on every phone. The page comes from the
   companion, so an already-open tab keeps the old page.
4. While swapped, **don't press "Start on this Mac"** in ShowStack. It launches
   the installed app, which then can't get its ports.

## 5. Rollback

- **Source build alongside the app:** press Ctrl-C. The installed app was
  never touched.
- **After a swap:** press Ctrl-C, then
  ```bash
  open ~/DjangoProjects/audiopatch/companion/dist/"ShowStack Listen.app"
  ```
  and hard-reload the Listen page on the phones. They're back on 0.3.2.
- **If `dist/` was lost:** download the last notarized release from the
  ShowStack GitHub releases page (`ShowStack-Listen-mac-arm64.zip`, "latest").
- **Code:** `git checkout main`.
- **showstack.io:** nothing to undo. This PR changes no server code or data.

## 6. Send back

- Pass/fail for each checklist item, plus the DVS sharing result (both at once,
  or swapped).
- Any click on switching: which two channels, and at what sample rate.
- How long the ON pill took after a Mic'd toggle (rough seconds).
- The source build's log if anything looked wrong (the terminal output).
