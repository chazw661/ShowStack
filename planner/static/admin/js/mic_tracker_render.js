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
 *     (every Mic'd button now reads ON / OFF, from one place)
 *   · an unassigned card stayed dimmed after you typed a name, because the
 *     dimming keyed off the `value` ATTRIBUTE and JS only ever set the
 *     `.value` PROPERTY -- the attribute still said "" (the dimming is now
 *     gone entirely; the placeholder text is the only unassigned signal)
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
 * Labels follow the TEMPLATE, because a fresh reload is the reference the
 * whole exercise is measured against. Every Mic'd button -- the A1 toggle,
 * the A2 card toggle and the per-slot chip button -- now reads ON / OFF, so
 * the word states the state rather than naming the control, and a live edit
 * can't word it differently from a reload.
 */
(function (global) {
    'use strict';

    var UNASSIGNED = '— Unassigned —';
    var CHIP_UNASSIGNED = 'Unassigned';
    var GROUP_CLASSES = ['group-blue', 'group-amber', 'group-red', 'group-purple', 'group-teal'];

    /* key -> {assignmentId, slotId, presenter, presenterId, photo, isMicd,
               micType, group, isActive, slotCount} */
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
                group: '', isActive: false, slotCount: 1,
                /* Everything below is here because the SYNC carries it. The
                   renderer used to own only what a toggle could change; now
                   that another machine's edit arrives as data rather than as
                   a page reload, every field the server can change has to be
                   something this file can write, or those edits would simply
                   never appear. */
                notes: '', headsetColor: '', placement: '',
                sensitivity: '', outputLevel: '',
                /* The photo is the PRESENTER's (PresenterPhoto), carried per
                   slot as the URL the server resolved for it. presenterId is
                   what lets one upload repaint every card that presenter is
                   on -- see setPresenterPhoto. */
                presenterId: '', photo: ''
            };
        }
        return store[k];
    }

    /* ── The one rule that makes remote updates safe ──────────────────────
       Never write to the control the user is in. Everything else about that
       slot still updates, so a remote Mic'd toggle lands while you are part
       way through typing a name, and the name you are typing is not yanked
       out from under you. The field catches up on blur: setField stops
       skipping, and the focusout handler below re-renders the slot. */
    function focused(el) {
        return el && document.activeElement === el;
    }

    function setField(el, value) {
        if (!el || focused(el)) return;
        if (el.value !== value) el.value = value;
        /* The attribute as well as the property: an attribute selector or a
           form reset reads the attribute, and setting only one of them is the
           original "unassigned styling never clears" bug. */
        if (el.tagName === 'INPUT') el.setAttribute('value', value);
    }

    /* A select is written the same way, but silently ignores a value it has
       no option for rather than blanking itself. */
    function setSelect(el, value) {
        if (!el || focused(el)) return;
        for (var i = 0; i < el.options.length; i++) {
            if (el.options[i].value === value) { el.value = value; return; }
        }
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
       since the row itself is no longer dimmed, that span IS the only thing
       saying the slot is empty -- so writing the placeholder text into the
       assigned span (what applySlotData used to do) produced a row that read
       unassigned but was styled assigned. */
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
    /* The A2 photo zone. One element set per card, showing the active slot's
       photo. Every path that changes a photo -- an upload, a drag-drop, a
       presenter change, NEXT/PREV, another machine's edit -- lands here; it
       used to be four hand-written copies of this DOM work, one per path. */
    function renderPhoto(assignmentId, url, alt) {
        var zone = document.getElementById('photo-zone-' + assignmentId);
        if (!zone) return;
        var img = document.getElementById('photo-img-' + assignmentId);
        var expand = document.getElementById('photo-expand-' + assignmentId);
        var placeholder = document.getElementById('photo-placeholder-' + assignmentId);
        if (url) {
            if (!img) {
                img = document.createElement('img');
                img.id = 'photo-img-' + assignmentId;
                img.style.cssText = 'width:70px;height:70px;object-fit:cover;border-radius:5px;display:block;';
                zone.insertBefore(img, zone.firstChild);
            }
            /* Compare the attribute, not .src: .src is absolutised, and a
               needless re-set restarts the load and flickers. */
            if (img.getAttribute('src') !== url) img.setAttribute('src', url);
            img.alt = alt || '';
            img.style.display = 'block';
            if (!expand) {
                var wrapper = document.createElement('div');
                wrapper.className = 'a2-photo-expand';
                expand = document.createElement('img');
                expand.id = 'photo-expand-' + assignmentId;
                wrapper.appendChild(expand);
                zone.appendChild(wrapper);
            }
            if (expand.getAttribute('src') !== url) expand.setAttribute('src', url);
            /* Clear rather than set: the hover-expand is shown by CSS. */
            if (expand.parentNode) expand.parentNode.style.display = '';
            if (placeholder) placeholder.style.display = 'none';
        } else {
            if (img) img.style.display = 'none';
            if (expand && expand.parentNode) expand.parentNode.style.display = 'none';
            if (placeholder) placeholder.style.display = '';
        }
    }

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
            setMicdButton(row.querySelector('.a1-micd-toggle'), st.isMicd, 'ON', 'OFF');
            setTypeBadge(row.querySelector('.mic-type-badge'), st.micType);
            setField(row.querySelector('.a1-notes-input'), st.notes);
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
                setMicdButton(chip.querySelector('.a2-slot-micd-btn'), st.isMicd, 'ON', 'OFF');
                /* The chip's name is a bare text node sitting between the dot
                   and the ✕ / ON-OFF controls, so it is updated in place. */
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

        setField(card.querySelector('.a2-presenter-input'), st.presenter || '');

        /* The A2 selects are identified by what their onchange calls, which is
           how the rest of this page already finds them (applySlotData does the
           same). They show the ACTIVE slot, and the early return above means
           we only get here for it. */
        card.querySelectorAll('.a2-select').forEach(function (sel) {
            var oc = sel.getAttribute('onchange') || '';
            if (oc.indexOf('updateMicType') !== -1) setSelect(sel, st.micType || '');
            else if (oc.indexOf("'headset_color'") !== -1) setSelect(sel, st.headsetColor || '');
            else if (oc.indexOf("'placement'") !== -1) setSelect(sel, st.placement || '');
            else if (oc.indexOf("'sensitivity'") !== -1) setSelect(sel, st.sensitivity || '');
            else if (oc.indexOf("'output_level'") !== -1) setSelect(sel, st.outputLevel || '');
        });

        setField(card.querySelector('.a2-notes-input'), st.notes || '');

        setMicdButton(card.querySelector('.a2-micd-toggle'), st.isMicd, 'ON', 'OFF');

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

        renderPhoto(st.assignmentId, st.photo || '', st.presenter || '');
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

    /* A headshot belongs to the presenter, so a new one goes on every slot
       they hold -- other cards, other sessions, the same page. */
    function setPresenterPhoto(presenterId, url) {
        if (!presenterId) return;
        var pid = String(presenterId);
        for (var k in store) {
            if (store.hasOwnProperty(k) && store[k].presenterId === pid) {
                store[k].photo = url || '';
                render(store[k].assignmentId, store[k].slotId);
            }
        }
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
                slotCount: parseInt(d.slotCount || '1', 10),
                /* Seeded from the controls Django rendered, so the first sync
                   diffs against what is actually on screen. */
                notes: (row.querySelector('.a1-notes-input') || {}).value || '',
                headsetColor: '', placement: '', sensitivity: '', outputLevel: '',
                presenterId: d.presenterId || '',
                photo: d.photo || ''
            };
        });
        for (var k in store) {
            if (store.hasOwnProperty(k)) render(store[k].assignmentId, store[k].slotId);
        }
        wireFocusCatchUp();
    }

    /* ── Applying another machine's state ─────────────────────────────────
       A sync row is the server's whole truth about one slot, so it is applied
       wholesale. Rows arrive already shaped the way the template's data-*
       attributes are shaped, including the template's own quirks (a
       single-presenter row's Mic'd and notes come off the MicAssignment, a
       shared row's off the PresenterSlot) — so an in-place update and a fresh
       page load land on the same screen, which is the only definition of
       "synced" worth having. */
    function applyRemote(rows) {
        var seen = 0;
        (rows || []).forEach(function (r) {
            var k = key(r.assignment_id, r.slot_id);
            if (!store[k]) return;   /* a slot this page has no row for */
            seen++;
            patch(r.assignment_id, r.slot_id, {
                presenter: r.presenter || '',
                isMicd: !!r.is_micd,
                isActive: !!r.is_active,
                micType: r.mic_type || '',
                group: r.group || '',
                slotCount: r.slot_count,
                notes: r.notes || '',
                headsetColor: r.headset_color || '',
                placement: r.placement || '',
                sensitivity: r.sensitivity || '',
                outputLevel: r.output_level || '',
                presenterId: r.presenter_id ? String(r.presenter_id) : '',
                photo: r.photo || ''
            });
        });
        return seen;
    }

    /* Counters for every session on the page, from the same payload. */
    function applySessionStats(sessions) {
        if (!sessions) return;
        Object.keys(sessions).forEach(function (sid) {
            var el = document.querySelector('.mtt-session[data-session-id="' + sid + '"]');
            if (!el) return;
            var anchor = el.querySelector('[data-assignment-id]');
            if (anchor) {
                applyStats(anchor.dataset.assignmentId,
                           sessions[sid].stats, sessions[sid].day_stats);
            }
        });
    }

    /* The other half of the focus rule: when a field the renderer was skipping
       loses focus, re-render its slot so whatever arrived meanwhile is applied
       at once rather than waiting for the next poll. The element's own save
       has already been dispatched by then (blur handlers run first), and the
       store carries that save's result, so this shows the user's own value —
       not a stale one. */
    function wireFocusCatchUp() {
        document.addEventListener('focusout', function (e) {
            var el = e.target;
            if (!el || !/^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;
            var row = el.closest('.a1-row');
            var aid = '', sid = '';
            if (row) {
                aid = row.dataset.assignmentId;
                sid = row.dataset.slotId || '';
            } else {
                var card = el.closest('.a2-card');
                if (!card) return;
                aid = (card.id || '').replace('a2-card-', '');
                var active = slotsOf(aid).filter(function (x) { return x.isActive; })[0];
                sid = active ? active.slotId : '';
            }
            if (!aid) return;
            /* After the field's own save has had a chance to land, so we are
               rendering the post-save store rather than racing it. */
            setTimeout(function () { render(aid, sid); }, 350);
        }, true);
    }

    global.MTTSlots = {
        get: get, patch: patch, render: render, slotsOf: slotsOf,
        setMicd: setMicd, setActive: setActive, applyStats: applyStats,
        setPresenterPhoto: setPresenterPhoto,
        applyRemote: applyRemote, applySessionStats: applySessionStats,
        init: init, UNASSIGNED: UNASSIGNED
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
