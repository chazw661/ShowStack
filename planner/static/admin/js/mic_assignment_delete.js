// Issue #36: row-action buttons (insert above/below, delete) for the
// MicAssignment inline on the MicSession admin change form. All three
// hit AJAX endpoints; delete removes the row in place, insert reloads
// the page so the renumbered rf_numbers and ordering refresh.
(function () {
    'use strict';

    function getCookie(name) {
        var cookies = document.cookie ? document.cookie.split(';') : [];
        for (var i = 0; i < cookies.length; i++) {
            var c = cookies[i].trim();
            if (c.slice(0, name.length + 1) === name + '=') {
                return decodeURIComponent(c.slice(name.length + 1));
            }
        }
        return '';
    }

    function post(url) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        }).then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, data: d }; });
        });
    }

    document.addEventListener('click', function (e) {
        // ── Delete ───────────────────────────────────────────────
        var delBtn = e.target.closest('.mic-delete-x');
        if (delBtn) {
            e.preventDefault();
            if (delBtn.dataset.busy === '1') return;
            if (!window.confirm('Delete this mic? This cannot be undone.')) return;
            delBtn.dataset.busy = '1';
            delBtn.style.opacity = '0.5';
            post('/audiopatch/api/mic-assignment/' + delBtn.dataset.micId + '/delete/')
                .then(function (resp) {
                    if (resp.ok && resp.data.success) {
                        var row = delBtn.closest('tr');
                        if (row) row.parentNode.removeChild(row);
                    } else {
                        delBtn.dataset.busy = '';
                        delBtn.style.opacity = '';
                        alert('Delete failed: ' + (resp.data.error || 'unknown error'));
                    }
                })
                .catch(function (err) {
                    delBtn.dataset.busy = '';
                    delBtn.style.opacity = '';
                    alert('Delete failed: ' + err);
                });
            return;
        }

        // ── Insert above / below ─────────────────────────────────
        var insBtn = e.target.closest('.mic-insert');
        if (insBtn) {
            e.preventDefault();
            if (insBtn.dataset.busy === '1') return;
            insBtn.dataset.busy = '1';
            insBtn.style.opacity = '0.5';
            var fd = new URLSearchParams();
            fd.append('position', insBtn.dataset.position);
            fetch('/audiopatch/api/mic-assignment/' + insBtn.dataset.micId + '/insert/', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: fd.toString(),
            })
                .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
                .then(function (resp) {
                    if (resp.ok && resp.data.success) {
                        // Reload so renumbered rows + new row appear.
                        window.location.reload();
                    } else {
                        insBtn.dataset.busy = '';
                        insBtn.style.opacity = '';
                        alert('Add failed: ' + (resp.data.error || 'unknown error'));
                    }
                })
                .catch(function (err) {
                    insBtn.dataset.busy = '';
                    insBtn.style.opacity = '';
                    alert('Add failed: ' + err);
                });
        }
    });
})();
