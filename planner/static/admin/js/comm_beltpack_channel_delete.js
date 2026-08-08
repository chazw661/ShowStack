// Issue #66: one-click delete for the CommBeltPackChannel inline on the
// CommBeltPack admin change form. Clicking the × immediately POSTs to
// /audiopatch/api/comm-beltpack-channel/<id>/delete/ and removes the row;
// no "Delete?" checkbox + save round-trip required. Mirrors
// mic_assignment_delete.js (#36).
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
        var btn = e.target.closest('.bpchannel-delete-x');
        if (!btn) return;
        e.preventDefault();
        if (btn.dataset.deleting === '1') return;

        var channelId = btn.dataset.bpchannelId;
        if (!channelId) return;
        if (!window.confirm('Delete this channel? This cannot be undone.')) return;

        btn.dataset.deleting = '1';
        btn.style.opacity = '0.5';

        fetch('/audiopatch/api/comm-beltpack-channel/' + channelId + '/delete/', {
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
