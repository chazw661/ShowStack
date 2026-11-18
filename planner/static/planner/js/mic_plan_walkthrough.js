// Mic Planner walkthrough (#walk): one panel per showflow line, built here
// from the mp-walk-data JSON (mic_plan/walkthrough.py page_data). Every
// string from the showflow or a user goes into the page as text
// (textContent / createTextNode), never as HTML.
//
// Enter confirms the line under the cursor and moves on at once; the POST
// runs behind it. Answers update only the panels whose signature changed;
// a line that changed under the user is redrawn as it is now and pointed
// to, without an error. Locked lines need a decision (or "Looks right").
(function () {
    var box = document.getElementById('mp-walk');
    var src = document.getElementById('mp-walk-data');
    if (!box || !src) return;
    var data = JSON.parse(src.textContent);
    var canEdit = box.dataset.canEdit === '1';
    var csrf = (box.querySelector('[name=csrfmiddlewaretoken]') || {}).value || '';
    var list = document.getElementById('mp-walk-list');
    var strip = document.getElementById('mp-walk-strip');
    var prog = document.getElementById('mp-walk-progress');
    var panels = data.panels, byId = {}, cursor = 0, pointed = null, planAt = -1;
    var HOW_ON = {send: 'sent', named: 'named here', enter: 're-enters', added: 'added by you', user: 'your edit',
                  fixed: 'VOG pack'};
    var HOW_OFF = {'catch': 'caught', exit: 'exit line', added: 'added by you', fixed: 'VOG pack', end: 'assumed: end of segment'};

    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text !== undefined && text !== null) e.textContent = String(text);
        return e;
    }
    function button(text, cls, fn) {
        var b = el('button', 'mp-btn small' + (cls ? ' ' + cls : ''), text);
        b.type = 'button';
        b.addEventListener('click', fn);
        return b;
    }
    function index() {
        byId = {};
        panels.forEach(function (p, k) { byId[p.id] = k; });
    }
    function person(key) {
        for (var i = 0; i < data.people.length; i++) if (data.people[i].key === key) return data.people[i];
        return null;
    }
    function nameOf(key) { var p = person(key); return p ? p.name : key; }

    // -- Server ---------------------------------------------------------------
    function post(action, body) {
        return fetch(box.dataset.url.replace('ACTION', action), {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
            body: JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () {
                return {ok: false, why: r.status === 403 ? 'You can view this walkthrough but not change it.'
                                                         : 'That did not work. Reload and try again.'};
            });
        }, function () { return {ok: false, why: 'No connection. Your change was not saved.'}; });
    }
    // An answer with panels: replace only those whose signature changed.
    function merge(res, pointAt) {
        if (res.people) data.people = res.people;
        if (res.strip) data.strip = res.strip;
        if (res.blockers) data.blockers = res.blockers;
        var incoming = res.panels || [];
        var whole = res.ok && res.strip !== undefined;
        if (whole && (incoming.length !== panels.length || incoming.some(function (p, k) { return panels[k].id !== p.id; }))) {
            var at = panels[cursor] ? panels[cursor].id : null;
            panels = incoming;
            index();
            cursor = at in byId ? byId[at] : 0;
            renderAll();
            return;
        }
        incoming.forEach(function (p) {
            var k = byId[p.id];
            if (k === undefined || panels[k].sig === p.sig) return;
            panels[k] = p;
            redraw(k);
        });
        if (pointAt !== undefined) point(pointAt);
        renderTop();
    }
    function act(action, body, row) {
        if (!canEdit) return;
        box.classList.add('mp-busy');
        return post(action, body).then(function (res) {
            box.classList.remove('mp-busy');
            if (res.ok === false && res.why === 'close') return res;
            if (res.ok === false && !res.panels) { say(res.why); return res; }
            merge(res, res.ok ? undefined : row);
            if (!res.ok) say(res.why);
            return res;
        });
    }
    function say(text) {
        var t = document.getElementById('mp-edit-msg');
        if (!t) return;
        t.textContent = text || '';
        t.hidden = !text;
        if (text) setTimeout(function () { if (t.textContent === text) t.hidden = true; }, 5000);
    }

    // -- Progress and the day strip -------------------------------------------
    function progress() {
        var done = 0, reopened = 0;
        panels.forEach(function (p) {
            if (p.state === 'confirmed' || p.state === 'auto') done++;
            else if (p.state === 'reopened') reopened++;
        });
        return {done: done, total: panels.length, reopened: reopened,
                open: panels.length - done - reopened,
                plan: panels.filter(function (p) { return p.badges.length; })};
    }
    function renderTop() {
        var pr = progress();
        prog.textContent = '';
        prog.appendChild(el('b', null, pr.done + ' of ' + pr.total + ' confirmed'));
        if (pr.reopened) prog.appendChild(el('span', 'mp-walk-reopened', ' · ' + pr.reopened + ' reopened'));
        if (!pr.open && !pr.reopened) prog.appendChild(el('span', 'mp-walk-done', ' · walkthrough done'));
        if (pr.plan.length) {
            var n = pr.plan.reduce(function (s, p) { return s + p.badges.length; }, 0);
            prog.appendChild(button(n + ' plan issue' + (n === 1 ? '' : 's') + ' ›', 'mp-walk-step', stepPlan))
                .title = 'Step to the next line with a plan issue';
        }
        if (pointed !== null && byId[pointed] !== undefined) {
            prog.appendChild(button('Line ' + panels[byId[pointed]].line + ' changed — check it', 'mp-walk-step warn',
                                    function () { var k = byId[pointed]; pointed = null; move(k); renderTop(); }));
        }
        var count = document.getElementById('mp-walk-count');
        if (count) count.textContent = pr.done + ' of ' + pr.total;
        var tile = document.getElementById('mp-tocheck');
        if (tile) {
            tile.querySelector('b').textContent = String(pr.open + pr.reopened);
            tile.classList.toggle('warn', pr.open + pr.reopened > 0);
        }
        var stats = document.getElementById('mp-stats');
        if (stats) stats.classList.toggle('unverified', pr.open + pr.reopened > 0);
        renderStrip();
    }
    function renderStrip() {
        strip.textContent = '';
        (data.blockers || []).forEach(function (b) {
            var item = el('div', 'mp-walk-issue crit');
            item.appendChild(el('span', 'mp-kind', b.label));
            item.appendChild(el('span', 'what', b.text));
            item.appendChild(el('span', 'mp-blocks', 'Blocks Send to Mic Tracker.'));
            if (b.panel in byId) item.appendChild(button('Go to line ' + b.line, '', function () { move(byId[b.panel]); }));
            strip.appendChild(item);
        });
        (data.strip || []).forEach(function (i) {
            var item = el('div', 'mp-walk-issue' + (i.kind === 'override_changed' ? ' warn' : ''));
            item.appendChild(el('span', 'mp-kind', i.label));
            item.appendChild(el('span', 'what', i.text));
            if (i.kind === 'override_changed') {
                var wn = el('div', 'mp-walk-was');
                wn.appendChild(el('div', null, 'Was: ' + i.was));
                wn.appendChild(el('div', null, 'Now: ' + i.now));
                item.appendChild(wn);
            }
            if (i.mics) {
                var ul = el('ul', 'mp-mics');
                i.mics.forEach(function (t) { ul.appendChild(el('li', null, t)); });
                item.appendChild(ul);
                if (i.can_use && box.dataset.useUrl) item.appendChild(button("Use the showflow's numbers", '', useShowflow));
            }
            if (canEdit) {
                if (i.kind === 'rejected') {
                    item.appendChild(button('Undo', '', function () { act('unreject', {key: i.key}); }));
                } else if (i.kind === 'override_changed') {
                    item.appendChild(button('Accept', '', function () { act('override', {part: i.part, entry: i.entry, do: 'accept'}); }));
                    item.appendChild(button('Drop', '', function () { act('override', {part: i.part, entry: i.entry, do: 'drop'}); }));
                } else if (i.kind === 'override_gone' || i.kind === 'override_person') {
                    item.appendChild(button('Drop', '', function () { act('override', {part: i.part, entry: i.entry, do: 'drop'}); }));
                }
            }
            strip.appendChild(item);
        });
        strip.hidden = !strip.childNodes.length;
    }
    function useShowflow() {
        var form = new FormData();
        form.append('csrfmiddlewaretoken', csrf);
        form.append('version', box.dataset.version);
        fetch(box.dataset.useUrl, {method: 'POST', body: form, credentials: 'same-origin'}).then(function (r) {
            if (r.ok) location.reload();
            else r.json().then(function (j) { say(j.error || 'That did not work.'); }, function () { say('That did not work.'); });
        });
    }
    function stepPlan() {
        var pr = progress();
        if (!pr.plan.length) return;
        var next = pr.plan.find(function (p) { return byId[p.id] > planAt; }) || pr.plan[0];
        planAt = byId[next.id];
        move(planAt);
    }

    // -- One panel -------------------------------------------------------------
    // A cell's text with its marks: name words, leftover text, notes, companies.
    var MARK_TITLES = {leftover: 'Not a person ShowStack recognised', note: 'A note, not a person',
                       company: 'A company, not a person', name: 'Read as a name'};
    function cellText(text, marks) {
        var out = el('span', 'txt');
        var cuts = marks.slice().sort(function (a, b) { return a.start - b.start; });
        var at = 0;
        cuts.forEach(function (m) {
            if (m.start < at) return;           // overlapping marks: the first wins
            if (m.start > at) out.appendChild(document.createTextNode(text.slice(at, m.start)));
            var mk = el('mark', 'mp-mk ' + m.kind, text.slice(m.start, m.end));
            if (m.person) mk.dataset.who = String(m.person);
            mk.title = MARK_TITLES[m.kind] || MARK_TITLES.name;
            out.appendChild(mk);
            at = m.end;
        });
        if (at < text.length) out.appendChild(document.createTextNode(text.slice(at)));
        return out;
    }
    var CELLS = [['description', ''], ['speaker', 'Speaker'], ['bsm', 'BSM'], ['audio', 'Audio'], ['notes', 'Notes']];
    function chip(o, off) {
        var c = el('span', 'mp-wchip ' + (off ? 'off' : 'on') + (o.first ? ' first' : '') + (o.how === 'end' ? ' assumed' : ''));
        c.appendChild(el('b', null, o.name));
        var bits = [];
        if (!off && o.mic === 'HH') bits.push('HH' + (o.mic_how === 'hint' ? ' (inferred)' : ''));
        if (!off && o.backup) bits.push('+ backup');
        if (o.host) bits.push('host');
        bits.push((off ? HOW_OFF : HOW_ON)[o.how] || o.how);
        c.appendChild(el('small', null, bits.join(' · ')));
        if (o.first) c.title = 'First line for ' + o.name;
        return c;
    }
    function panelEl(p, k) {
        var li = el('li', 'mp-wp s-' + p.state + (p.segment ? ' seg' : '') +
                    (p.locks.length || p.person_locks.length ? ' locked' : ''));
        li.id = 'wp-' + p.id;
        li.tabIndex = -1;
        li.dataset.k = String(k);
        var head = el('div', 'mp-wp-head');
        head.appendChild(el('span', 'line', p.line));
        if (p.time) head.appendChild(el('span', 'time', p.time));
        if (data.parts.length > 1) head.appendChild(el('span', 'part', 'Part ' + p.part_no));
        head.appendChild(el('span', 'page', 'p. ' + p.page));
        var state = {confirmed: 'Confirmed' + (p.by ? ' by ' + p.by : ''), reopened: 'Reopened',
                     auto: 'No change of people', open: ''}[p.state];
        if (state) head.appendChild(el('span', 'state', state));
        p.badges.forEach(function (b) {
            var a = el('a', 'mp-wbadge k-' + b.kind, b.label);
            a.href = box.dataset.planUrl + '&part=' + encodeURIComponent(p.part) + '#showflow:row-' + p.rows[0].order;
            a.title = 'Show in plan';
            head.appendChild(a);
        });
        li.appendChild(head);

        var body = el('div', 'mp-wp-body');
        p.rows.forEach(function (r, n) {
            if (n) body.appendChild(el('div', 'mp-wp-cont', 'continues on page ' + r.page));
            CELLS.forEach(function (c) {
                var text = r.cells[c[0]];
                if (!text) return;
                var line = el('div', 'cell c-' + c[0]);
                if (c[1]) line.appendChild(el('span', 'lab', c[1]));
                line.appendChild(cellText(text, r.marks.filter(function (m) { return m.col === c[0]; })));
                body.appendChild(line);
            });
        });
        li.appendChild(body);

        if (p.on.length || p.off.length) {
            var who = el('div', 'mp-wp-who');
            if (p.on.length) {
                var on = el('div', 'on');
                on.appendChild(el('span', 'lab', 'On'));
                p.on.forEach(function (o) { on.appendChild(chip(o, false)); });
                who.appendChild(on);
            }
            if (p.off.length) {
                var off = el('div', 'off');
                off.appendChild(el('span', 'lab', 'Off'));
                p.off.forEach(function (o) { off.appendChild(chip(o, true)); });
                who.appendChild(off);
            }
            li.appendChild(who);
        }
        if (p.issues.length) {
            var iss = el('ul', 'mp-wp-issues');
            p.issues.forEach(function (i) {
                var item = el('li');
                item.appendChild(el('span', 'mp-kind', i.label));
                item.appendChild(document.createTextNode(' ' + i.text));
                iss.appendChild(item);
            });
            li.appendChild(iss);
        }
        if (p.was && p.was.length) {
            var was = el('ul', 'mp-walk-was');
            p.was.forEach(function (w) { was.appendChild(el('li', null, w.what + ': was ' + w.was + ' → now ' + w.now)); });
            li.appendChild(was);
        }
        p.person_locks.forEach(function (pl) { li.appendChild(personLock(p, pl)); });
        if (p.locks.length) {
            var locks = el('div', 'mp-wp-locks');
            p.locks.forEach(function (l) { locks.appendChild(el('div', 'lock k-' + l.kind, l.text)); });
            if (canEdit && !p.person_locks.length && p.state !== 'confirmed') {
                locks.appendChild(button('Looks right', 'primary', function () { confirm(byId[p.id], true); }));
            }
            li.appendChild(locks);
        }
        if (canEdit) li.appendChild(tools(p));
        return li;
    }
    function personLock(p, pl) {
        var d = el('div', 'mp-wp-plock');
        d.appendChild(el('span', 'q', 'Is "' + pl.name + '" a person?'));
        if (!canEdit) return d;
        d.appendChild(button('Person', '', function () { act('person', {row: p.id, person: pl.person, decision: 'person'}, p.id); }));
        d.appendChild(button('Not a person', '', function () { act('person', {row: p.id, person: pl.person, decision: 'not'}, p.id); }));
        var same = el('details', 'mp-wp-same');
        same.appendChild(el('summary', 'mp-btn small', 'Same as…'));
        var sel = el('select');
        sel.appendChild(el('option', null, '— someone on this day —')).value = '';
        data.people.forEach(function (x) {
            if (x.pk !== pl.person) sel.appendChild(el('option', null, x.name)).value = String(x.pk);
        });
        sel.setAttribute('aria-label', 'Same as');
        var typed = el('input');
        typed.type = 'text';
        typed.placeholder = 'or type a name';
        typed.maxLength = 200;
        typed.setAttribute('aria-label', 'Same as, typed');
        var hint = el('div', 'mp-wp-close');
        function send(force, target) {
            var body = {row: p.id, person: pl.person, decision: 'same', name: typed.value, force: !!force};
            if (target || sel.value) body.target = target || sel.value;
            act('person', body, p.id).then(function (res) {
                if (!res || res.why !== 'close') return;
                hint.textContent = '';
                hint.appendChild(el('span', null, 'Did you mean '));
                res.close.forEach(function (c) {
                    hint.appendChild(button(c.name, '', function () { send(false, String(c.pk)); }));
                });
                hint.appendChild(button('No, "' + typed.value + '" is someone new', '', function () { send(true); }));
            });
        }
        same.appendChild(sel);
        same.appendChild(typed);
        same.appendChild(button('Save', 'primary', function () { send(false); }));
        same.appendChild(hint);
        d.appendChild(same);
        return d;
    }
    function tools(p) {
        var t = el('div', 'mp-wp-tools');
        if (p.state === 'open' || p.state === 'reopened') {
            if (!p.locks.length && !p.person_locks.length) {
                t.appendChild(button('Confirm', 'primary', function () { confirm(byId[p.id], false); }));
            }
        } else if (p.state === 'confirmed') {
            t.appendChild(button('Reopen', '', function () { act('unconfirm', {row: p.id}, p.id); }));
        }
        var edit = el('details', 'mp-wp-edit');
        edit.appendChild(el('summary', 'mp-btn small', 'Edit'));
        edit.addEventListener('toggle', function () { if (edit.open && !edit.dataset.built) { buildEditor(edit, p); edit.dataset.built = '1'; } });
        t.appendChild(edit);
        if (p.can_add) {
            var add = el('details', 'mp-wp-add');
            add.appendChild(el('summary', 'mp-btn small', 'Add people from this line'));
            var inputs = [];
            (p.leftovers || []).concat(['', '']).forEach(function (n, i) {
                var inp = el('input');
                inp.type = 'text';
                inp.value = n;
                inp.maxLength = 200;
                inp.placeholder = 'Another name';
                inp.setAttribute('aria-label', 'Name ' + (i + 1));
                inputs.push(inp);
                add.appendChild(inp);
            });
            add.appendChild(button('Add these people', 'primary', function () {
                act('add', {row: p.id, names: inputs.map(function (i) { return i.value; })}, p.id);
            }));
            t.appendChild(add);
        }
        return t;
    }
    // The row's overrides as the user would leave them: chips can be taken
    // off (not on / not off), types switched, people added on or off.
    function buildEditor(box_, p) {
        var o = p.override || {};
        var state = {on: (o.on || []).slice(), off: (o.off || []).slice(), not_on: (o.not_on || []).slice(),
                     not_off: (o.not_off || []).slice(), mic: Object.assign({}, o.mic || {})};
        function drop(listName, notName, key) {
            var k = state[listName].indexOf(key);
            if (k >= 0) state[listName].splice(k, 1);
            else if (state[notName].indexOf(key) < 0) state[notName].push(key);
        }
        function addTo(listName, notName, key) {
            var k = state[notName].indexOf(key);
            if (k >= 0) state[notName].splice(k, 1);
            else if (state[listName].indexOf(key) < 0) state[listName].push(key);
        }
        var form = el('div', 'mp-wp-editor');
        p.on.forEach(function (x) {
            var r = el('div', 'erow');
            r.appendChild(el('span', null, x.name + ' on'));
            var mic = el('select');
            [['body', 'Body pack'], ['HH', 'Handheld']].forEach(function (m) {
                var opt = el('option', null, m[1]);
                opt.value = m[0];
                mic.appendChild(opt);
            });
            mic.value = state.mic[x.key] || x.mic;
            mic.setAttribute('aria-label', 'Mic for ' + x.name);
            mic.addEventListener('change', function () { state.mic[x.key] = mic.value; });
            r.appendChild(mic);
            r.appendChild(button('Not on here', '', function () { drop('on', 'not_on', x.key); r.classList.add('gone'); }));
            form.appendChild(r);
        });
        p.off.forEach(function (x) {
            var r = el('div', 'erow');
            r.appendChild(el('span', null, x.name + ' off'));
            r.appendChild(button('Not off here', '', function () { drop('off', 'not_off', x.key); r.classList.add('gone'); }));
            form.appendChild(r);
        });
        ['on', 'off'].forEach(function (which) {
            var r = el('div', 'erow');
            var sel = el('select');
            sel.appendChild(el('option', null, which === 'on' ? '+ someone comes on here' : '+ someone goes off here')).value = '';
            data.people.forEach(function (x) { sel.appendChild(el('option', null, x.name)).value = x.key; });
            sel.setAttribute('aria-label', which === 'on' ? 'Comes on here' : 'Goes off here');
            sel.addEventListener('change', function () {
                if (!sel.value) return;
                addTo(which, 'not_' + which, sel.value);
                r.insertBefore(el('span', 'added', nameOf(sel.value) + ' ' + which), sel);
                sel.value = '';
            });
            r.appendChild(sel);
            form.appendChild(r);
        });
        form.appendChild(button('Save this line', 'primary', function () {
            act('row', {row: p.id, on: state.on, off: state.off, not_on: state.not_on, not_off: state.not_off,
                        mic: state.mic}, p.id);
        }));
        box_.appendChild(form);
    }

    function renderAll() {
        list.textContent = '';
        var lastPart = null;
        panels.forEach(function (p, k) {
            if (data.parts.length > 1 && p.part !== lastPart) {
                var part = data.parts.filter(function (x) { return x.pk === p.part; })[0];
                list.appendChild(el('li', 'mp-wp-part', 'Part ' + p.part_no + (part ? ' · ' + part.name : '')));
                lastPart = p.part;
            }
            list.appendChild(panelEl(p, k));
        });
        markCursor(false);
        renderTop();
    }
    function redraw(k) {
        var old = document.getElementById('wp-' + panels[k].id);
        var fresh = panelEl(panels[k], k);
        if (old) old.replaceWith(fresh);
        if (k === cursor) markCursor(false);
    }

    // -- Cursor and keys -----------------------------------------------------
    function markCursor(focus) {
        var cur = list.querySelector('.mp-wp.cursor');
        if (cur) cur.classList.remove('cursor');
        var p = panels[cursor];
        var li = p && document.getElementById('wp-' + p.id);
        if (!li) return;
        li.classList.add('cursor');
        if (focus) {
            li.focus({preventScroll: true});
            li.scrollIntoView({block: 'center'});
        }
    }
    function move(k) {
        if (k < 0 || k >= panels.length) return;
        cursor = k;
        markCursor(true);
    }
    function nextOpen(from) {
        for (var k = from + 1; k < panels.length; k++) if (panels[k].state === 'open' || panels[k].state === 'reopened') return k;
        for (k = 0; k <= from; k++) if (panels[k].state === 'open' || panels[k].state === 'reopened') return k;
        return -1;
    }
    function point(id) {
        if (id === undefined || id === null || byId[id] === undefined) return;
        pointed = id;
        var li = document.getElementById('wp-' + id);
        if (li) li.classList.add('changed');
    }
    // Confirm panel k now, as shown; the server agrees or sends the line back.
    function confirm(k, ack) {
        var p = panels[k];
        if (!canEdit || !p || p.person_locks.length || (p.locks.length && !ack)) return;
        if (p.state !== 'open' && p.state !== 'reopened') return;
        var digest = p.digest;
        p.state = 'confirmed';
        p.was = [];
        redraw(k);
        var n = nextOpen(k);
        move(n < 0 ? Math.min(k + 1, panels.length - 1) : n);
        renderTop();
        post('confirm', {row: p.id, digest: digest, ack: !!ack}).then(function (res) {
            if (res.ok === false && !res.panels) {
                p.state = 'open';
                redraw(byId[p.id]);
                renderTop();
                say(res.why);
                return;
            }
            merge(res, res.ok ? undefined : p.id);
        });
    }
    function typing(t) {
        return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON|SUMMARY|A)$/.test(t.tagName));
    }
    document.addEventListener('keydown', function (e) {
        var view = document.getElementById('v-walk');
        if (!view || view.hidden || e.altKey || e.ctrlKey || e.metaKey || typing(e.target)) return;
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            move(cursor + (e.key === 'ArrowDown' ? 1 : -1));
        } else if (e.key === 'Enter') {
            var p = panels[cursor];
            if (!p) return;
            e.preventDefault();
            if (p.person_locks.length || p.locks.length) {
                // Locked: Enter takes you to its decision, it never decides.
                var li = document.getElementById('wp-' + p.id);
                var first = li && li.querySelector('.mp-wp-plock button, .mp-wp-plock summary, .mp-wp-locks button');
                if (first) first.focus();
            } else if (p.state === 'open' || p.state === 'reopened') {
                confirm(cursor, false);
            } else {
                var n = nextOpen(cursor);
                if (n >= 0) move(n);
            }
        }
    });
    list.addEventListener('click', function (e) {
        var li = e.target.closest('.mp-wp');
        if (li && !e.target.closest('button, a, details, input, select')) { cursor = +li.dataset.k; markCursor(false); }
    });
    document.addEventListener('mp-walk-shown', function () { markCursor(true); });

    index();
    var first = panels.findIndex(function (p) { return p.state === 'open' || p.state === 'reopened'; });
    cursor = first < 0 ? 0 : first;
    renderAll();
})();
