// Source Hardware Options — "← Back to Console" button.
// Activated when the user arrives via the "Manage list" link on a Console
// edit page (which appends ?back_to=<console change URL>). The back target
// is persisted to sessionStorage so the button stays available across the
// changelist / add form / change form navigation while the user edits the
// list. Restricted to /admin/planner/console/<id>/change/ URLs to prevent
// open-redirect via the back_to query param.
(function () {
    'use strict';

    const STORAGE_KEY = 'showstack_source_hardware_back_to';
    const SAFE_BACK_RE = /^\/admin\/planner\/console\/\d+\/change\/?$/;
    const CONSOLE_LIST_URL = '/admin/planner/console/';

    document.addEventListener('DOMContentLoaded', function () {
        injectStyles();
        injectBackButton(resolveBackTo());
    });

    function resolveBackTo() {
        const params = new URLSearchParams(window.location.search);
        const fromUrl = params.get('back_to');
        if (fromUrl && SAFE_BACK_RE.test(fromUrl)) {
            try { sessionStorage.setItem(STORAGE_KEY, fromUrl); } catch (e) { /* ignore */ }
            return { url: fromUrl, label: '← Back to Console' };
        }
        let stored = null;
        try { stored = sessionStorage.getItem(STORAGE_KEY); } catch (e) { /* ignore */ }
        if (stored && SAFE_BACK_RE.test(stored)) {
            return { url: stored, label: '← Back to Console' };
        }
        return { url: CONSOLE_LIST_URL, label: '← Back to Consoles' };
    }

    function injectBackButton(target) {
        const link = document.createElement('a');
        link.href = target.url;
        link.textContent = target.label;
        link.className = 'source-hw-back-link';

        const objectTools = document.querySelector('.object-tools');
        if (objectTools) {
            const li = document.createElement('li');
            li.appendChild(link);
            objectTools.insertBefore(li, objectTools.firstChild);
            return;
        }
        const breadcrumbs = document.querySelector('.breadcrumbs');
        if (breadcrumbs) {
            link.classList.add('source-hw-back-link-standalone');
            breadcrumbs.parentNode.insertBefore(link, breadcrumbs.nextSibling);
        }
    }

    function injectStyles() {
        const css =
            '.object-tools li > a.source-hw-back-link {' +
                'background:#2a73c4 !important;color:#fff !important;}' +
            '.object-tools li > a.source-hw-back-link:hover {' +
                'background:#1e5a9c !important;}' +
            '.source-hw-back-link-standalone {' +
                'display:inline-block;margin:8px 20px;padding:6px 12px;' +
                'background:#2a73c4;color:#fff !important;border-radius:3px;' +
                'text-decoration:none;font-size:12px;font-weight:bold;}' +
            '.source-hw-back-link-standalone:hover {' +
                'background:#1e5a9c;text-decoration:none;}';
        const style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);
    }
})();
