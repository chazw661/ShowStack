// Console Module — A/B input source toggle.
//
// Modern consoles offer an A and B input source per channel. The console
// input inline carries an A and a B variant of both the Source column
// (`source` / `source_b`) and the Source Hardware column (`source_hardware` /
// `source_hardware_b`). Showing all four at once makes an already-wide table
// wider, so instead we render a small "A Inputs / B Inputs" tab toggle above
// the table that flips which set of Source / Source Hardware columns is
// visible. Every other column (channel, Dante, group, …) is shared and stays
// visible in both views.
//
// Default view is A. The B input is "hardware only" (no separate Dante/Omni
// patch), so only the Source and Source Hardware columns differ between tabs.
(function () {
    'use strict';

    const GROUP_ID = 'consoleinput_set-group';

    document.addEventListener('DOMContentLoaded', function () {
        const group = document.getElementById(GROUP_ID);
        if (!group) return;
        injectStyles();
        group.classList.add('ab-show-a'); // default: show A, hide B
        insertToggle(group, buildToggle(group));
    });

    function buildToggle(group) {
        const wrap = document.createElement('div');
        wrap.className = 'ab-input-toggle';

        const label = document.createElement('span');
        label.className = 'ab-input-toggle__label';
        label.textContent = 'Input source:';
        wrap.appendChild(label);

        const btnA = makeBtn('A Inputs', true);
        const btnB = makeBtn('B Inputs', false);

        btnA.addEventListener('click', function (e) {
            e.preventDefault();
            group.classList.add('ab-show-a');
            group.classList.remove('ab-show-b');
            setActive(btnA, btnB);
        });
        btnB.addEventListener('click', function (e) {
            e.preventDefault();
            group.classList.add('ab-show-b');
            group.classList.remove('ab-show-a');
            setActive(btnB, btnA);
        });

        wrap.appendChild(btnA);
        wrap.appendChild(btnB);
        return wrap;
    }

    function makeBtn(text, active) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'ab-input-toggle__btn' + (active ? ' is-active' : '');
        b.textContent = text;
        return b;
    }

    function setActive(on, off) {
        on.classList.add('is-active');
        off.classList.remove('is-active');
    }

    function insertToggle(group, toggle) {
        // Place the tabs directly beneath the inline's heading, above the table.
        const heading = group.querySelector('h2');
        if (heading && heading.parentNode) {
            heading.parentNode.insertBefore(toggle, heading.nextSibling);
        } else {
            group.insertBefore(toggle, group.firstChild);
        }
    }

    function injectStyles() {
        const css =
            '#consoleinput_set-group.ab-show-a th.column-source_b,' +
            '#consoleinput_set-group.ab-show-a td.field-source_b,' +
            '#consoleinput_set-group.ab-show-a th.column-source_hardware_b,' +
            '#consoleinput_set-group.ab-show-a td.field-source_hardware_b{display:none;}' +
            '#consoleinput_set-group.ab-show-b th.column-source,' +
            '#consoleinput_set-group.ab-show-b td.field-source,' +
            '#consoleinput_set-group.ab-show-b th.column-source_hardware,' +
            '#consoleinput_set-group.ab-show-b td.field-source_hardware{display:none;}' +
            '.ab-input-toggle{display:flex;align-items:center;gap:6px;margin:8px 0;}' +
            '.ab-input-toggle__label{font-size:12px;font-weight:bold;color:#eee;margin-right:2px;}' +
            '.ab-input-toggle__btn{padding:3px 12px;font-size:12px;font-weight:bold;cursor:pointer;' +
                'background:#2b2b2b;color:#ccc;border:1px solid #555;border-radius:4px;}' +
            '.ab-input-toggle__btn.is-active{background:#2a73c4;color:#fff;border-color:#2a73c4;}' +
            '.ab-input-toggle__btn:hover{border-color:#2a73c4;}';
        const style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);
    }
})();
