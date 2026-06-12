// Issue #36: one-click delete for the MicAssignment inline on the
// MicSession admin change form. Clicking the X immediately POSTs to
// /audiopatch/api/mic-assignment/<id>/delete/ and removes the row;
// no "Delete?" checkbox + save round-trip required.
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

    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.mic-delete-x');
        if (!btn) return;
        e.preventDefault();
        if (btn.dataset.deleting === '1') return;

        var micId = btn.dataset.micId;
        if (!micId) return;
        if (!window.confirm('Delete this mic? This cannot be undone.')) return;

        btn.dataset.deleting = '1';
        btn.style.opacity = '0.5';

        fetch('/audiopatch/api/mic-assignment/' + micId + '/delete/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (resp) {
                if (resp.ok && resp.data.success) {
                    var row = btn.closest('tr');
                    if (row) row.parentNode.removeChild(row);
                } else {
                    btn.dataset.deleting = '';
                    btn.style.opacity = '';
                    alert('Delete failed: ' + (resp.data.error || 'unknown error'));
                }
            })
            .catch(function (err) {
                btn.dataset.deleting = '';
                btn.style.opacity = '';
                alert('Delete failed: ' + err);
            });
    });
})();
