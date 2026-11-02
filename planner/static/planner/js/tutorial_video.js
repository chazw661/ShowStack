/* Tutorial video player.
 *
 * Buttons ({% tutorial_button %}) carry the embed URL; this builds one modal
 * <dialog> the first time any of them is pressed. The iframe is created on
 * open and removed on close, so the page fetches nothing from YouTube until
 * someone asks for a video, and closing it stops playback.
 *
 * Esc closes (the dialog's own cancel), so does a click on the backdrop, and
 * focus goes back to the button that opened it.
 */
(function () {
    'use strict';
    if (window.ShowStackTutorial) return;

    var dialog = null, frameBox = null, heading = null, opener = null;

    function build() {
        dialog = document.createElement('dialog');
        dialog.className = 'ss-tutorial-dialog';
        dialog.setAttribute('aria-labelledby', 'ss-tutorial-title');

        var bar = document.createElement('div');
        bar.className = 'ss-tutorial-bar';
        heading = document.createElement('h2');
        heading.id = 'ss-tutorial-title';
        heading.className = 'ss-tutorial-title';
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'ss-tutorial-close';
        close.setAttribute('aria-label', 'Close video');
        close.textContent = '×';
        close.addEventListener('click', closeDialog);
        bar.appendChild(heading);
        bar.appendChild(close);

        frameBox = document.createElement('div');
        frameBox.className = 'ss-tutorial-frame';

        dialog.appendChild(bar);
        dialog.appendChild(frameBox);

        // A click whose target is the dialog itself landed on the backdrop:
        // the content fills the dialog's box, so it is never the target.
        dialog.addEventListener('click', function (e) {
            if (e.target === dialog) closeDialog();
        });
        // Esc fires 'cancel'; route it through closeDialog so the iframe goes.
        dialog.addEventListener('cancel', function (e) {
            e.preventDefault();
            closeDialog();
        });
        document.body.appendChild(dialog);
    }

    function openDialog(button) {
        if (!dialog) build();
        opener = button;
        heading.textContent = button.dataset.tutorialTitle || 'Tutorial';

        var iframe = document.createElement('iframe');
        iframe.src = button.dataset.tutorialSrc + '?autoplay=1&rel=0&modestbranding=1';
        iframe.title = heading.textContent;
        iframe.allow = 'autoplay; encrypted-media; picture-in-picture; fullscreen';
        iframe.setAttribute('allowfullscreen', '');
        // The site's Referrer-Policy is same-origin, which sends YouTube no
        // Referer, and the embed then refuses to play (error 153). Send just
        // the origin for this one request.
        iframe.referrerPolicy = 'strict-origin-when-cross-origin';
        frameBox.replaceChildren(iframe);

        if (typeof dialog.showModal === 'function') {
            dialog.showModal();
        } else {
            dialog.setAttribute('open', '');
        }
        dialog.querySelector('.ss-tutorial-close').focus();
    }

    function closeDialog() {
        if (!dialog) return;
        frameBox.replaceChildren();          // removes the iframe: playback stops
        if (typeof dialog.close === 'function' && dialog.open) {
            dialog.close();
        } else {
            dialog.removeAttribute('open');
        }
        if (opener && document.contains(opener)) opener.focus();
        opener = null;
    }

    document.addEventListener('click', function (e) {
        var button = e.target.closest && e.target.closest('.ss-tutorial-btn[data-tutorial-src]');
        if (!button) return;
        e.preventDefault();
        openDialog(button);
    });

    window.ShowStackTutorial = {open: openDialog, close: closeDialog};
})();
