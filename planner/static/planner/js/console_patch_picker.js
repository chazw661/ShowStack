/* Console page: patch an I/O device port from a channel's Patch cell.
 *
 * Tap a cell (owner / editor only: viewers get the read-only cell, which has
 * no .ss-patch-edit button) -> a panel: the channel's current patch with
 * Unpatch, then the project's I/O devices with their free counts, then a
 * device's ports. Free ports are buttons; used ports are dimmed with their
 * name. If the channel already has a patch, a free port asks Replace or Add
 * before anything is sent. Rules and storage: planner/utils/console_patch_edit.py.
 *
 * What this must never do: submit the console form, or touch anything on the
 * page but the one cell and the free-ports block. The panel lives on <body>,
 * outside the form; every control is type="button"; a reply swaps exactly
 * those two elements. Unsaved edits anywhere else stay where they are.
 *
 * Every reply carries the channel's fresh cell and `state`; a write sends the
 * state back and the server refuses (409) if the channel changed meanwhile.
 * Opening the picker refreshes the cell too, so a stale row corrects itself
 * the moment it is touched.
 */
(function () {
    'use strict';

    var panel = null;      // {root, dialog, body, msg}
    var ctx = null;        // {btn, host, url, data, device, pending, busy}
    var lastFocus = null;

    function csrfToken() {
        var input = document.querySelector('input[name=csrfmiddlewaretoken]');
        if (input && input.value) return input.value;
        var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        if (text != null) n.textContent = text;
        return n;
    }

    function button(cls, text, onTap) {
        var b = el('button', 'ss-pp-btn ' + (cls || ''), text);
        b.type = 'button';
        if (onTap) b.addEventListener('click', function (e) {
            e.preventDefault();
            if (!ctx || ctx.busy) return;
            onTap(e);
        });
        return b;
    }

    // -- swapping the two page fragments ------------------------------------

    function swapCell(html) {
        if (!ctx || !html || !ctx.host) return;
        ctx.host.innerHTML = html;
        ctx.btn = ctx.host.querySelector('.ss-patch-edit');
    }

    function swapFree(html) {
        var old = document.querySelector('.ss-patch-free');
        if (!old || !html) return;
        var tmp = document.createElement('div');
        tmp.innerHTML = html.trim();
        var fresh = tmp.firstElementChild;
        if (!fresh) return;
        fresh.open = old.open;
        old.parentNode.replaceChild(fresh, old);
    }

    function flash(host) {
        if (!host) return;
        host.classList.remove('ss-pp-flash');
        void host.offsetWidth;
        host.classList.add('ss-pp-flash');
    }

    // -- panel ----------------------------------------------------------------

    function ensurePanel() {
        if (panel) return panel;
        var root = el('div', 'ss-pp-backdrop');
        root.hidden = true;
        var dialog = el('div', 'ss-pp');
        dialog.setAttribute('role', 'dialog');
        dialog.setAttribute('aria-modal', 'true');
        dialog.setAttribute('aria-labelledby', 'ss-pp-title');
        var head = el('div', 'ss-pp-head');
        var title = el('div', 'ss-pp-title');
        title.id = 'ss-pp-title';
        var close = button('ss-pp-close', '×', closePanel);
        close.setAttribute('aria-label', 'Close');
        head.appendChild(title);
        head.appendChild(close);
        var msg = el('div', 'ss-pp-msg');
        msg.setAttribute('role', 'status');
        msg.hidden = true;
        var body = el('div', 'ss-pp-body');
        dialog.appendChild(head);
        dialog.appendChild(msg);
        dialog.appendChild(body);
        root.appendChild(dialog);
        root.addEventListener('click', function (e) { if (e.target === root) closePanel(); });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !root.hidden) { e.preventDefault(); closePanel(); }
        });
        document.body.appendChild(root);
        // console_patch.css is not hashed under runserver, so a browser can keep
        // Phase A's copy, which has no panel rules: the panel then lands unstyled
        // at the foot of the page and a tap seems to do nothing. Pin it on screen
        // anyway, and say why.
        if (getComputedStyle(root).position !== 'fixed') {
            console.warn('console_patch.css is out of date (cached copy?): reload ignoring cache.');
            [[root, 'position:fixed;inset:0;z-index:2000;overflow:auto;padding:16px;' +
                    'background:rgba(0,0,0,.6)'],
             [dialog, 'max-width:560px;margin:0 auto;padding:12px;background:#1e1e1e;color:#eee']
            ].forEach(function (pair) { pair[0].style.cssText = pair[1]; });
        }
        panel = { root: root, dialog: dialog, title: title, body: body, msg: msg };
        return panel;
    }

    function say(text, kind) {
        panel.msg.textContent = text || '';
        panel.msg.hidden = !text;
        panel.msg.className = 'ss-pp-msg' + (kind ? ' is-' + kind : '');
    }

    function openPanel(btn) {
        ensurePanel();
        lastFocus = btn;
        ctx = { btn: btn, host: btn.parentNode, url: btn.getAttribute('data-patch-url'),
                data: null, device: null, pending: null, busy: false };
        panel.title.textContent = 'Patch';
        panel.body.textContent = '';
        panel.body.appendChild(el('p', 'ss-pp-loading', 'Loading…'));
        say('');
        panel.root.hidden = false;
        document.documentElement.classList.add('ss-pp-open');
        panel.dialog.querySelector('.ss-pp-close').focus();
        request('GET');
    }

    function closePanel() {
        if (!panel) return;
        panel.root.hidden = true;
        document.documentElement.classList.remove('ss-pp-open');
        var back = ctx && ctx.host && ctx.host.querySelector('.ss-patch-edit');
        ctx = null;
        if (back) back.focus(); else if (lastFocus && lastFocus.isConnected) lastFocus.focus();
    }

    // -- talking to the server ---------------------------------------------

    function request(method, payload) {
        var c = ctx;
        c.busy = true;
        panel.dialog.classList.add('is-busy');
        var opts = { method: method, credentials: 'same-origin',
                     headers: { 'Accept': 'application/json' } };
        if (method === 'POST') {
            opts.headers['Content-Type'] = 'application/json';
            opts.headers['X-CSRFToken'] = csrfToken();
            opts.body = JSON.stringify(payload);
        }
        fetch(c.url, opts).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (data) {
                return { status: r.status, data: data };
            });
        }).then(function (res) {
            if (ctx !== c) return;   // closed or reopened meanwhile
            c.busy = false;
            panel.dialog.classList.remove('is-busy');
            handle(method, payload, res.status, res.data);
        }).catch(function () {
            if (ctx !== c) return;
            c.busy = false;
            panel.dialog.classList.remove('is-busy');
            say('Could not reach ShowStack. Nothing was changed; try again.', 'error');
        });
    }

    function handle(method, payload, status, data) {
        if (data.cell_html) swapCell(data.cell_html);
        if (data.free_html) swapFree(data.free_html);
        if (data.state) ctx.data = data;

        if (status === 200 && method === 'POST') {
            flash(ctx.host);
            if (payload.action === 'patch') { closePanel(); return; }
            ctx.pending = null;
            render();
            say('Unpatched.', 'ok');
            return;
        }
        if (status === 200) { render(); return; }
        if (status === 403) {
            panel.body.textContent = '';
            say(data.message || 'Read-only access.', 'error');
            return;
        }
        if (status === 404 || !data.state) {
            panel.body.textContent = '';
            say(data.message || 'This channel or port is no longer here. Reload the page.', 'error');
            return;
        }
        // 409 / 422 / 400: nothing was written; show what is true now.
        ctx.pending = null;
        render();
        say(data.message || 'Nothing was changed.', status === 409 ? 'warn' : 'error');
    }

    function send(action, port, mode) {
        say('');
        request('POST', { action: action, port: port, mode: mode || '', state: ctx.data.state });
    }

    // -- rendering ------------------------------------------------------------

    function portLabel(side, d, number) { return d + ' · ' + side + ' ' + number; }

    function render() {
        var d = ctx.data;
        panel.title.textContent = d.channel.console + ' · ' + d.channel.label +
            (d.channel.name ? ' · ' + d.channel.name : '');
        var body = panel.body;
        body.textContent = '';
        body.appendChild(renderCurrent(d));
        if (ctx.pending) {
            body.appendChild(renderChoice(d, ctx.pending));
        } else if (ctx.device != null && findDevice(d, ctx.device)) {
            body.appendChild(renderPorts(d, findDevice(d, ctx.device)));
        } else {
            ctx.device = null;
            body.appendChild(renderDevices(d));
        }
    }

    function findDevice(d, id) {
        for (var i = 0; i < d.devices.length; i++) if (d.devices[i].id === id) return d.devices[i];
        return null;
    }

    function renderCurrent(d) {
        var sec = el('section', 'ss-pp-current');
        sec.appendChild(el('h3', 'ss-pp-h', 'Patched here'));
        if (!d.feeds.length) {
            sec.appendChild(el('p', 'ss-pp-empty', 'Nothing yet.'));
            return sec;
        }
        d.feeds.forEach(function (f) {
            var row = el('div', 'ss-pp-feed' + (f.conflict ? ' is-conflict' : '') + ' is-' + f.how);
            var a = el('a', 'ss-pp-feed-link', portLabel(d.side, f.device, f.number));
            a.href = f.url;
            a.target = '_blank';      // a new tab: leaving would drop unsaved edits here
            a.rel = 'noopener';
            a.title = 'Open ' + f.device + ' in a new tab';
            var text = el('div', 'ss-pp-feed-text');
            text.appendChild(a);
            var notes = [];
            if (f.slot === 'B') notes.push('B input — by name, edit it on the device page');
            else if (f.how === 'by_name') notes.push('by name, not linked');
            else if (f.how === 'ambiguous') notes.push('ambiguous (' + f.others.join(', ') + ') — not this channel’s');
            if (f.conflict) notes.push('CONFLICT: more than one port linked');
            if (f.lock) notes.push(f.lock);
            if (notes.length) text.appendChild(el('div', 'ss-pp-note', notes.join(' · ')));
            row.appendChild(text);
            if (f.can_unpatch) {
                var un = button('ss-pp-unpatch', 'Unpatch', function () { send('unpatch', f.port); });
                un.setAttribute('aria-label', 'Unpatch ' + portLabel(d.side, f.device, f.number));
                row.appendChild(un);
            }
            sec.appendChild(row);
        });
        return sec;
    }

    function renderDevices(d) {
        var sec = el('section', 'ss-pp-devices');
        sec.appendChild(el('h3', 'ss-pp-h', 'Choose an I/O device'));
        if (!d.devices.length) {
            sec.appendChild(el('p', 'ss-pp-empty', 'No I/O devices with ' +
                (d.side === 'In' ? 'inputs' : 'outputs') + ' in this project.'));
            return sec;
        }
        var list = el('div', 'ss-pp-device-list');
        d.devices.forEach(function (dev) {
            var b = button('ss-pp-device' + (dev.free ? '' : ' is-full'), '', function () {
                ctx.device = dev.id;
                render();
            });
            b.appendChild(el('span', 'ss-pp-device-name', dev.name));
            b.appendChild(el('span', 'ss-pp-device-free',
                dev.free ? dev.free + ' free of ' + dev.total : 'full (' + dev.total + ')'));
            list.appendChild(b);
        });
        sec.appendChild(list);
        return sec;
    }

    function renderPorts(d, dev) {
        var sec = el('section', 'ss-pp-ports');
        var head = el('div', 'ss-pp-ports-head');
        head.appendChild(button('ss-pp-back', '‹ Devices', function () {
            ctx.device = null;
            render();
        }));
        head.appendChild(el('h3', 'ss-pp-h', dev.name + ' · ' + dev.free + ' free'));
        sec.appendChild(head);
        var grid = el('div', 'ss-pp-grid');
        dev.ports.forEach(function (p) {
            var cls = 'ss-pp-port' + (p.free ? ' is-free' : ' is-used') + (p.mine ? ' is-mine' : '');
            var b = button(cls, '', p.free ? function () { pick(d, dev, p); } : null);
            b.appendChild(el('span', 'ss-pp-port-n', String(p.number)));
            var name = p.mine ? 'here' : (p.name || (p.linked ? '(linked)' : ''));
            if (!p.free) b.appendChild(el('span', 'ss-pp-port-name', name));
            if (!p.free) {
                b.disabled = true;
                b.setAttribute('aria-disabled', 'true');
            }
            b.title = portLabel(d.side, dev.name, p.number) +
                (p.lock ? ' — ' + p.lock : p.free ? ' — free' : ' — ' + name);
            grid.appendChild(b);
        });
        sec.appendChild(grid);
        return sec;
    }

    function pick(d, dev, p) {
        if (!d.has_current) { send('patch', p.id, ''); return; }
        ctx.pending = { device: dev, port: p };
        render();
    }

    function renderChoice(d, pending) {
        var sec = el('section', 'ss-pp-choice');
        var target = portLabel(d.side, pending.device.name, pending.port.number);
        var current = d.feeds.filter(function (f) { return f.can_unpatch; })
            .map(function (f) { return portLabel(d.side, f.device, f.number); });
        sec.appendChild(el('p', 'ss-pp-choice-text',
            d.channel.label + ' is already patched to ' + current.join(' and ') + '.'));
        var row = el('div', 'ss-pp-choice-row');
        row.appendChild(button('ss-pp-primary', 'Replace with ' + target, function () {
            send('patch', pending.port.id, 'replace');
        }));
        if (d.side === 'In') {
            row.appendChild(button('ss-pp-warn', 'Add as second (conflict)', function () {
                send('patch', pending.port.id, 'add');
            }));
        } else {
            row.appendChild(button('', 'Add — feed both', function () {
                send('patch', pending.port.id, 'add');
            }));
        }
        row.appendChild(button('ss-pp-cancel', 'Cancel', function () {
            ctx.pending = null;
            render();
        }));
        sec.appendChild(row);
        if (d.side === 'In') {
            sec.appendChild(el('p', 'ss-pp-note',
                'Replace frees ' + current.join(' and ') + '. Add keeps both: two ports on one input is shown as a conflict.'));
        }
        return sec;
    }

    // One listener for the page: cells are swapped in and out, so bind high.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('.ss-patch-edit');
        if (!btn) return;
        e.preventDefault();
        openPanel(btn);
    });
})();
