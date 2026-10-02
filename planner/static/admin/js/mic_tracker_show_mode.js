/* planner/static/admin/js/mic_tracker_show_mode.js
 *
 * Mic Tracker "Show Mode" -- a red-light night-vision theme for running a live
 * show from a dark FOH position. Shared by the Tracker and Overview pages.
 *
 * Loaded from {% block extrahead %}, i.e. inside <head> and NOT deferred, so
 * the first statement below runs before <body> is parsed. That ordering is the
 * whole point: the tracker reloads itself whenever the 5-second checksum poll
 * sees someone else's edit, and a class applied on DOMContentLoaded would let
 * the normal dark-blue theme paint for a frame first. Mid-show, that frame is
 * a flash of blue light at the console. Setting it on <html> pre-paint means
 * the page only ever renders in one theme.
 *
 * The class lives on <html> (not <body>) for the same reason -- it exists
 * before any body content does.
 *
 * Nothing here touches show data, polling or saving. The mode is a per-browser
 * display preference in localStorage; it is deliberately NOT stored on the
 * project, because two engineers on one show want it set independently (A2 on
 * a bright stage deck, A1 in the dark).
 */
(function () {
    'use strict';

    var KEY = 'micTrackerShowMode';
    var CLASS = 'mtt-show-mode';
    var root = document.documentElement;

    function stored() {
        try { return localStorage.getItem(KEY) === '1'; } catch (e) { return false; }
    }

    /* ── Pre-paint: this is the line that prevents the refresh flash ── */
    if (stored()) root.classList.add(CLASS);

    function isOn() { return root.classList.contains(CLASS); }

    /* ── Screen Wake Lock ───────────────────────────────────────────────
     * A laptop or iPad that sleeps mid-show has to be woken and unlocked
     * before the next mic cue, so hold the screen awake while Show Mode is
     * on. Best-effort: unsupported browsers (and a refused request) just
     * carry on without it -- the lock is a convenience, never a dependency.
     *
     * The platform releases the lock whenever the page is hidden, so it has
     * to be re-requested on visibilitychange rather than only once at start.
     */
    var wakeLock = null;

    function releaseWakeLock() {
        if (!wakeLock) return;
        var l = wakeLock;
        wakeLock = null;
        try { l.release(); } catch (e) {}
    }

    function requestWakeLock() {
        if (!isOn() || wakeLock) return;
        if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
        navigator.wakeLock.request('screen').then(function (lock) {
            if (!isOn()) { try { lock.release(); } catch (e) {} return; }
            wakeLock = lock;
            lock.addEventListener('release', function () { wakeLock = null; });
        }).catch(function () { /* denied, low battery, unsupported mode */ });
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') requestWakeLock();
    });

    /* ── Button label / pressed state ───────────────────────────────── */
    function syncButtons() {
        var on = isOn();
        var btns = document.querySelectorAll('.mtt-show-mode-btn');
        for (var i = 0; i < btns.length; i++) {
            btns[i].setAttribute('aria-pressed', on ? 'true' : 'false');
            btns[i].title = on
                ? 'Show Mode is on — tap to return to the normal theme'
                : 'Show Mode: red-light theme for a dark FOH position';
        }
    }

    window.toggleShowMode = function () {
        var on = !isOn();
        root.classList.toggle(CLASS, on);
        try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) {}
        syncButtons();
        if (on) requestWakeLock(); else releaseWakeLock();
    };

    function init() {
        syncButtons();
        requestWakeLock();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
