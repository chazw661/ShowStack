# ShowStack Listen Beta — A2 quickstart

The beta is a second copy of ShowStack Listen with the new phone page: a grid
of channel tiles with meters, Mic'd **ON** pills, and switching with no clicks.
Your regular **ShowStack Listen** stays installed; you can go back to it at
any time (see Rollback).

**Only one of the two can run at a time.** In the menu bar the beta is
**🎧β** and the regular app is **🎧**.

## 1. First open

1. Unzip `ShowStack-Listen-Beta-mac-arm64.zip` and drag **ShowStack Listen
   Beta** into **Applications**, next to the regular app. Don't replace the
   regular app.
2. Quit the regular app: **🎧 → Quit ShowStack Listen**.
3. Open **ShowStack Listen Beta**. macOS asks whether to open an app from the
   internet: click **Open**. It's signed and notarized, so you shouldn't need
   to right-click → Open.
4. When macOS asks for **microphone** access, click **OK**. Without it the
   beta hears only silence from Dante Virtual Soundcard.

## 2. Pair with the show

If the regular app was already set up for this show, the beta starts on the
same show by itself, because they share settings. Check that **🎧β** shows
**Show: …** at the top of the menu.

Otherwise:

1. In ShowStack open **Mic Tracker → 🎧 Listen Setup → Advanced** and copy the
   show token. It's the value after `--token`.
2. Choose **🎧β → Pair with a show…**, paste the token, click **Pair**, then
   **Start**.
3. Choose **🎧β → Audio Input → Dante Virtual Soundcard** if it isn't already
   ticked.

**While the beta runs, don't click "Start on this Mac" in ShowStack.** That
button opens the regular app.

## 3. Check it works

- The **🎧β** menu shows the show name, **Source: Dante Virtual Soundcard…**
  and **Listeners**.
- On a phone, open Listen from Mic Tracker's 🎧 button as usual. You should
  see a tile for each slot, with moving meters.
- Tap a tile: you hear that pack. Tap another: it switches with no click.
- Toggle Mic'd in Mic Tracker: the tile's **ON** pill follows within about
  5 s.

Phones that already work with the regular app work with the beta too: it
uses the same certificate. For a new phone, use **🎧β → Set up a phone…**.

## 4. Rollback (2 steps)

1. **🎧β → Quit ShowStack Listen Beta.**
2. Open **ShowStack Listen** from Applications, or click **Start on this Mac**
   in ShowStack.

Phones: reload the Listen page. You're back on the regular app.

The beta saves nothing the regular app can't read, so these two steps are
enough. On its first launch it also saved a copy of the regular app's
settings, in `~/Library/Application Support/ShowStack Listen (before beta)`.
**Only if the regular app won't start or pair after a rollback**, quit both
apps and put that copy back (Terminal, one line):

```bash
cd ~/Library/Application\ Support && mv "ShowStack Listen" "ShowStack Listen (beta used)" && ditto "ShowStack Listen (before beta)" "ShowStack Listen"
```

Then open ShowStack Listen again, and tell Charlie it was needed.

## 5. Installing a hotfix

Charlie AirDrops a new `ShowStack-Listen-Beta-mac-arm64.zip`; it lands in
**Downloads**.

1. **🎧β → Quit ShowStack Listen Beta.**
2. Double-click the zip, drag the new **ShowStack Listen Beta** into
   **Applications** and choose **Replace**.
3. Open it. The first line of the **🎧β** menu shows the new build
   (e.g. *Beta 0.4.0 · build 72c4d01 2026-10-14 10:51*).
4. Reload the Listen page on the phones.

## Known issues

- **Lock-screen pause doesn't stick.** Pause on the iPhone lock screen,
  Control Center or a headphone button stops audio for a moment, then it
  plays again. To stop listening, use **⏸ Stop** on the Listen page.
- **Swiping Safari closed stops audio.** Reopen the page and tap
  **▶︎ Listen**. Locking the phone or switching apps is fine.
- If the regular app is set to **Open at Login**, it starts when the Mac
  starts. Quit it (🎧 → Quit) before opening the beta.

## If something's wrong

Roll back (§4), then send Charlie the time it happened and the log:
**🎧β → Show Log**.
