/* planner/static/admin/js/mic_tracker_render.js
 *
 * One place that turns a presenter slot's DATA into its DOM STATE.
 *
 * ── Why this file exists ────────────────────────────────────────────────
 * The tracker rendered every slot twice, in two languages. Django rendered
 * it on page load; a dozen hand-written JS fragments re-rendered pieces of
 * it on each edit. The two drifted, and every drift looked like a styling
 * bug:
 *
 *   · the A2 Mic'd button said "MIC'D" after a reload and "ON" after a
 *     toggle, because the template and toggleMicd() disagreed on the label
 *   · an unassigned card stayed dimmed after you typed a name, because the
 *     dimming keyed off the `value` ATTRIBUTE and JS only ever set the
 *     `.value` PROPERTY -- the attribute still said ""
 *   · clearing a name left it on the A1 row, because assignPresenter() only
 *     synced to A1 `if (value)`
 *   · applySlotData() wrote "— Unassigned —" into a .a1-presenter-primary
 *     span instead of swapping it for .a1-unassigned, so the row kept
 *     assigned styling while reading as unassigned
 *   · assignSlotGroup() assigned `group-dot` to the .group-dot-stack
 *     container, destroying the stack
 *
 * None of those are visible in the stylesheet. They are all the same bug:
 * two renderers. So there is now one. mttRenderSlot() is the only code that
 * writes slot state to the DOM, and it runs on page load as well as on
 * every change -- so "looks like a fresh reload" is not a thing to remember
 * to do, it is the only code path there is.
 *
 * ── How it is wired ─────────────────────────────────────────────────────
 * The template emits each slot's facts as data-* attributes on its A1 row
 * (the one element that exists for every slot, single- or multi-presenter).
 * On load mttInitSlots() reads them into a store and renders every slot,
 * which normalises whatever the server painted. On a change the caller
 * patches the store through mttPatchSlot() and the same renderer runs.
 *
 * Keeping the data on the row rather than in a separate JSON blob means
 * there is no second copy of the truth to go stale, and the server stays
 * the source of it.
 *
 * The one deliberate asymmetry: labels follow the TEMPLATE, because a fresh
 * reload is the reference the whole exercise is measured against.
 *   A1 toggle   ON / —
 *   A2 toggle   MIC'D always (the fill carries the state, not the word)
 *   chip button ON / MIC'D
 */
(function (global) {
    'use strict';

    var UNASSIGNED = '— Unassigned —';
    var CHIP_UNASSIGNED = 'Unassigned';
    var GROUP_CLASSES = ['group-blue', 'group-amber', 'group-red', 'group-purple', 'group-teal'];

    /* key -> {assignmentId, slotId, presenter, isMicd, micType, group, isActive, slotCount} */
    var store = {};

    function key(assignmentId, slotId) {
        return slotId ? 's' + slotId : 'a' + assignmentId;
    }

    function get(assignmentId, slotId) {
        var k = key(assignmentId, slotId);
        if (!store[k]) {
            store[k] = {
                assignmentId: String(assignmentId),
                slotId: slotId ? String(slotId) : '',
                presenter: '', isMicd: false, micType: '',
                group: '', isActive: false, slotCount: 1
            };
        }
        return store[k];
    }

    /* Every slot belonging to one assignment, in DOM order. */
    function slotsOf(assignmentId) {
        var out = [];
        for (var k in store) {
            if (store.hasOwnProperty(k) && store[k].assignmentId === String(assignmentId)) out.push(store[k]);
        }
        return out;
    }

    function rowFor(st) {
        return (st.slotId && document.getElementById('a1-slot-row-' + st.slotId)) ||
               document.getElementById('a1-row-' + st.assignmentId);
    }

    function setGroupClass(el, color) {
        if (!el) return;
        GROUP_CLASSES.forEach(function (c) { el.classList.remove(c); });
        if (color) el.classList.add('group-' + color);
    }

    /* The type badge is one element whose class and text both come from the
       data. Written in one place so the A1 row and the A2 card header can
       never disagree about an empty type. */
    function setTypeBadge(badge, micType) {
        if (!badge) return;
        badge.className = 'mic-type-badge type-' + (micType || 'empty');
        badge.innerHTML = '<span class="type-dot"></span>' + (micType || '—');
    }

    /* The presenter cell is a SPAN SWAP, not a text update. .a1-unassigned
       and .a1-presenter-primary are different sizes, colours and styles, and
       .a1-unassigned is what the row's dimming is keyed to -- so writing the
       placeholder text into the assigned span (what applySlotData used to do)
       produced a row that read unassigned but was styled assigned. */
    function renderPresenterCell(cell, name, isActive) {
        if (!cell) return;
        var span = cell.querySelector('.a1-presenter-primary, .a1-unassigned');
        if (!span) return;
        if (name) {
            span.className = 'a1-presenter-primary' + (isActive ? ' a1-slot-active' : '');
            span.textContent = name;
        } else {
            span.className = 'a1-unassigned';
            span.textContent = UNASSIGNED;
        }
    }

    /* Mic'd buttons differ only in their two labels, so they share a writer.
       classList.toggle on BOTH classes matters: the CSS keys .on and .off
       separately and a button carrying neither falls back to unstyled. */
    function setMicdButton(btn, isMicd, onLabel, offLabel) {
        if (!btn) return;
        btn.classList.toggle('on', isMicd);
        btn.classList.toggle('off', !isMicd);
        var dot = btn.querySelector('.a2-micd-dot');
        if (dot) {
            /* Preserve the dot element, replace only the text around it. */
            Array.prototype.slice.call(btn.childNodes).forEach(function (n) {
                if (n.nodeType === 3) n.parentNode.removeChild(n);
            });
            btn.appendChild(document.createTextNode(isMicd ? onLabel : offLabel));
        } else {
            btn.textContent = isMicd ? onLabel : offLabel;
        }
    }

    /* ── The renderer ──────────────────────────────────────────────────── */
    function render(assignmentId, slotId) {
        var st = get(assignmentId, slotId);
        var assigned = !!st.presenter;

        /* ---- A1 row ---------------------------------------------------- */
        var row = rowFor(st);
        if (row) {
            row.classList.toggle('row-micd', st.isMicd);
            row.classList.toggle('is-unassigned', !assigned);
            setGroupClass(row, st.group);
            renderPresenterCell(row.querySelector('td:nth-child(4)'), st.presenter, st.isActive && st.slotCount > 1);
            setMicdButton(row.querySelector('.a1-micd-toggle'), st.isMicd, 'ON', '—');
            setTypeBadge(row.querySelector('.mic-type-badge'), st.micType);
        }

        /* ---- A2 chip for this slot ------------------------------------- */
        if (st.slotId) {
            var chip = document.querySelector('#slot-queue-' + st.assignmentId +
                                              ' .a2-slot-chip[data-slot-id="' + st.slotId + '"]');
            if (chip) {
                chip.classList.toggle('micd', st.isMicd);
                chip.classList.toggle('active', st.isActive);
                var cdot = chip.querySelector('.a2-slot-micd-dot');
                if (cdot) cdot.classList.toggle('on', st.isMicd);
                setMicdButton(chip.querySelector('.a2-slot-micd-btn'), st.isMicd, 'ON', "MIC'D");
                /* The chip's name is a bare text node sitting between the dot
                   and the ✕ / MIC'D controls, so it is updated in place. */
                for (var i = 0; i < chip.childNodes.length; i++) {
                    var n = chip.childNodes[i];
                    if (n.nodeType === 3 && n.textContent.trim()) {
                        n.textContent = ' ' + (st.presenter || CHIP_UNASSIGNED) + ' ';
                        break;
                    }
                }
            }
        }

        /* ---- A2 card: only the ACTIVE slot is on display there ---------- */
        if (!st.isActive && st.slotCount > 1) return;

        var card = document.getElementById('a2-card-' + st.assignmentId);
        if (!card) return;

        card.classList.toggle('card-micd', st.isMicd);
        card.classList.toggle('is-unassigned', !assigned);
        setGroupClass(card, st.group);

        var input = card.querySelector('.a2-presenter-input');
        if (input) {
            /* BOTH forms. The property is what the user sees and what the
               form submits; the attribute is what any attribute selector and
               a form reset read. Setting only one of them is the original
               "unassigned styling never clears" bug. */
            if (document.activeElement !== input) input.value = st.presenter || '';
            input.setAttribute('value', st.presenter || '');
        }

        setMicdButton(card.querySelector('.a2-micd-toggle'), st.isMicd, "MIC'D", "MIC'D");

        var meta = card.querySelector('.a2-card-meta');
        if (meta) {
            var badge = meta.querySelector('.mic-type-badge');
            if (st.micType) {
                if (!badge) {
                    badge = document.createElement('span');
                    badge.style.cssText = 'font-size:9px;padding:2px 7px;';
                    meta.insertBefore(badge, meta.firstChild);
                }
                setTypeBadge(badge, st.micType);
            } else if (badge) {
                badge.parentNode.removeChild(badge);
            }
        }

        var listen = card.querySelector('.a2-listen-btn');
        if (listen) listen.dataset.presenter = st.presenter || '';
    }

    /* Patch a slot's data and re-render it. The only supported way to change
       slot state -- callers never touch classes or labels themselves. */
    function patch(assignmentId, slotId, data) {
        var st = get(assignmentId, slotId);
        for (var k in data) { if (data.hasOwnProperty(k)) st[k] = data[k]; }
        render(assignmentId, slotId);
        return st;
    }

    /* Mic'd is radio-per-assignment on the server -- toggle_slot_micd clears
       every sibling slot -- so it is radio here too. Doing that in one place
       rather than in each caller is what keeps the A1 rows, the chips and the
       card from disagreeing after a toggle.

       slotId may be omitted for a single-presenter assignment, where the
       caller legitimately has no slot id to hand. */
    function setMicd(assignmentId, slotId, isMicd) {
        var slots = slotsOf(assignmentId);
        var target = slotId ? String(slotId) : (slots.length === 1 ? slots[0].slotId : '');
        slots.forEach(function (s) {
            var mine = (s.slotId || '') === (target || '');
            if (isMicd) s.isMicd = mine;       /* turning one on turns the rest off */
            else if (mine) s.isMicd = false;   /* turning one off leaves the rest alone */
            render(s.assignmentId, s.slotId);
        });
    }

    function setActive(assignmentId, slotId) {
        slotsOf(assignmentId).forEach(function (s) {
            s.isActive = (s.slotId || '') === String(slotId || '');
            render(s.assignmentId, s.slotId);
        });
    }

    /* The session and day "n/total mic'd" counters are template-derived from
       the same slot data, so they belong here too -- but the numbers come
       from the SERVER's stats payload rather than being recounted in the
       browser. Counting here would be a second definition of "mic'd", and a
       second definition of anything is how this page got into this state.

       The old updateSessionStats looked for .session-column / .session-footer,
       which this template has not had in a long time, so it silently updated
       nothing on every save. */
    function applyStats(assignmentId, sessionStats, dayStats) {
        var anchor = document.querySelector('[data-assignment-id="' + assignmentId + '"]');
        if (!anchor) return;

        if (sessionStats) {
            var session = anchor.closest('.mtt-session');
            var sEl = session && session.querySelector('.mtt-session-stats');
            if (sEl) {
                /* Joined with a newline so the rendered markup matches the
                   template's whitespace exactly, not just visually -- it
                   makes a load-vs-edit diff of textContent come out clean,
                   which is how this whole path is tested. */
                var parts = ["<span>MIC'D: <strong>" + sessionStats.micd + '</strong>/' + sessionStats.total + '</span>'];
                if (sessionStats.d_mic !== undefined) parts.push('<span>D-MIC: ' + sessionStats.d_mic + '</span>');
                if (sessionStats.shared > 0) parts.push('<span>Shared: ' + sessionStats.shared + '</span>');
                sEl.innerHTML = '\n' + parts.join('\n') + '\n';
            }
        }

        if (dayStats && dayStats.used !== undefined) {
            var day = anchor.closest('.mtt-day');
            var dEl = day && day.querySelector('.mtt-day-stats strong');
            if (dEl) dEl.textContent = String(dayStats.used);
        }
    }

    /* ── Load: read what the server rendered, then render it ourselves ──
     * Running the renderer over the server's own markup is the point. If the
     * two ever disagree again, the page silently self-corrects instead of
     * showing a state no edit path can reproduce. */
    function init() {
        document.querySelectorAll('.a1-row[data-assignment-id]').forEach(function (row) {
            var d = row.dataset;
            var aid = d.assignmentId;
            var sid = d.slotId || '';
            store[key(aid, sid)] = {
                assignmentId: String(aid),
                slotId: sid ? String(sid) : '',
                presenter: d.presenter || '',
                isMicd: d.micd === '1',
                micType: d.micType || '',
                group: d.group || '',
                isActive: d.active === '1',
                slotCount: parseInt(d.slotCount || '1', 10)
            };
        });
        for (var k in store) {
            if (store.hasOwnProperty(k)) render(store[k].assignmentId, store[k].slotId);
        }

    }

    global.MTTSlots = {
        get: get, patch: patch, render: render, slotsOf: slotsOf,
        setMicd: setMicd, setActive: setActive, applyStats: applyStats,
        init: init, UNASSIGNED: UNASSIGNED
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
