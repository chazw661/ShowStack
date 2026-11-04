/* A2 schedule (templates/planner/mic_plan_a2.html).
 *
 * The current segment is the one the A2 tapped, kept in this browser
 * (localStorage, per day and A2); the clock never moves it. Earlier segments
 * dim, the next segment with actions is marked NEXT.
 *
 * Every 30 s plan.json?head=1 is fetched. A different version raises the
 * "Plan updated" banner; the list is only rebuilt when the A2 taps it.
 */
(function () {
    'use strict';
    var POLL_MS = 30000;
    var root = document.getElementById('a2-root');
    if (!root) return;

    // PDF links carry the browser's time zone, for the printed clock times.
    var zone = '';
    try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) { /* UTC on the server */ }
    if (zone) {
        Array.prototype.forEach.call(document.querySelectorAll('a[data-tz-link]'), function (a) {
            a.href += (a.href.indexOf('?') < 0 ? '?' : '&') + 'tz=' + encodeURIComponent(zone);
        });
    }

    if (!root.dataset.version) return;
    var segs = Array.prototype.slice.call(root.querySelectorAll('.a2-seg'));
    var bar = document.getElementById('a2-bar');

    function load() {
        try { return window.localStorage.getItem(root.dataset.store) || ''; } catch (e) { return ''; }
    }
    function save(key) {
        try { window.localStorage.setItem(root.dataset.store, key); } catch (e) { /* this view only */ }
    }

    // The sticky bar's height, so the current heading sticks just under it.
    function barHeight() {
        root.style.setProperty('--a2-bar-h', bar.offsetHeight + 'px');
    }

    function mark(key, scroll) {
        var cur = -1;
        segs.forEach(function (s) { if (s.dataset.key === key) cur = +s.dataset.i; });
        var next = -1;
        if (cur >= 0) {
            for (var k = 0; k < segs.length; k++) {
                var i = +segs[k].dataset.i;
                if (i > cur && +segs[k].dataset.acts > 0 && (next < 0 || i < next)) next = i;
            }
        }
        segs.forEach(function (s) {
            var i = +s.dataset.i;
            s.classList.toggle('current', i === cur);
            s.classList.toggle('past', cur >= 0 && i < cur);
            s.classList.toggle('next', i === next);
            s.querySelector('.a2-seg-head').setAttribute('aria-pressed', i === cur ? 'true' : 'false');
            if (i === cur && scroll) {
                window.scrollTo({ top: s.getBoundingClientRect().top + window.pageYOffset - bar.offsetHeight - 6 });
            }
        });
    }

    segs.forEach(function (s) {
        s.querySelector('.a2-seg-head').addEventListener('click', function () {
            save(s.dataset.key);
            mark(s.dataset.key, true);
        });
    });

    // Pure: what the banners show for a poll answer.
    function banners(pageVersion, head) {
        return { updated: head.version !== pageVersion, stale: !!head.stale };
    }
    window.mpA2Banners = banners;   // for checks from the console

    var updated = document.getElementById('a2-updated');
    var stale = document.getElementById('a2-stale');
    document.getElementById('a2-refresh').addEventListener('click', function () { window.location.reload(); });

    function poll() {
        fetch(root.dataset.head, { credentials: 'same-origin', cache: 'no-store',
                                   headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (head) {
                if (!head) return;
                var b = banners(+root.dataset.version, head);
                updated.hidden = !b.updated;
                stale.hidden = !b.stale;
                barHeight();
            })
            .catch(function () { /* venue Wi-Fi: try again next time */ });
    }

    barHeight();
    window.addEventListener('resize', barHeight);
    mark(load(), true);
    setInterval(poll, POLL_MS);
})();
