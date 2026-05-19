# Stack Research: v2.2 Signal Flow Diagrammer

**Domain:** Vanilla-JS diagramming module added to existing Django 5.x SaaS
**Researched:** 2026-05-19
**Confidence:** HIGH (JointJS core), HIGH (Python layer), MEDIUM (PNG export path)

---

## Scope Boundary

This document covers ONLY the net-new dependencies for the v2.2 Signal Flow Diagrammer.
The existing stack (Django 5.x, PostgreSQL, Whitenoise 6.x, gunicorn, Resend,
ReportLab, lxml, Sortable.min.js) is locked and not re-evaluated here.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `@joint/core` | 4.2.4 | Diagram canvas — nodes, edges, drag-drop, serialisation | MIT was the assumption; actual license is MPL-2.0 (see License section). Dependency-free since v4.0; no Backbone/jQuery/lodash. Drop-in `<script>` tag via CDN. Single UMD bundle + no required CSS. |
| `html-to-image` | 1.11.11 | Client-side PNG export (SVG → canvas → PNG data URL) | dom-to-image is unmaintained; html-to-image is the maintained fork with identical API. Available as a single UMD min file on cdnjs — no build step. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Django `models.JSONField` | built-in (Django 3.1+, used here on Django 5.2) | Store diagram canvas state (nodes, edges, positions) as a JSON blob on the `SignalFlowDiagram` model | Always — no third-party dep needed. PostgreSQL stores it as native `jsonb`. |
| `django.contrib.contenttypes` | built-in | `GenericForeignKey` (`content_type` + `object_id`) on diagram nodes linking to live ShowStack equipment records | Already in `INSTALLED_APPS` for the existing admin; just use it. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| jsDelivr CDN (dev) | Serve `@joint/core` and `html-to-image` during local development | Pin the exact version in the URL (`/npm/@joint/core@4.2.4/dist/joint.min.js`) so local and production behaviour match |
| Vendored copy (production) | `planner/static/planner/js/vendor/` — same pattern as `Sortable.min.js` | Download once, commit, serve via Whitenoise — eliminates CDN availability as a production dependency |

---

## License: MPL-2.0 (Not MIT) — What This Means

`@joint/core` is licensed under **Mozilla Public License 2.0**, not MIT.

MPL-2.0 is a **file-level weak copyleft** licence:

- Commercial use and SaaS deployment: **permitted** (confirmed via Mozilla MPL FAQ)
- Running on Railway and charging subscription fees: **permitted**
- Obligation: if you **modify the `@joint/core` source files themselves**, those modified files must be re-released under MPL-2.0. ShowStack's own code (views, templates, diagram JS) is in separate files and is **not** subject to the copyleft requirement.
- Attribution: include the MPL-2.0 licence notice alongside the vendored `joint.min.js` file (a `LICENSE` file or a comment in a `THIRD_PARTY_LICENSES.txt` at project root satisfies this).

**Practical implication:** vendor the file, add a `THIRD_PARTY_LICENSES.txt`, do not modify `joint.min.js` directly — all constraints are trivially satisfied.

---

## Static File Layout

Follow the `Sortable.min.js` precedent:

```
planner/static/planner/js/vendor/
    Sortable.min.js                ← existing
    joint.min.js                   ← new (@joint/core 4.2.4 UMD bundle)
    html-to-image.min.js           ← new (html-to-image 1.11.11 UMD bundle)
```

Companion CSS: `@joint/core` 4.x does **not** require a `joint.css` stylesheet.
The UMD examples in the official docs show the stylesheet commented out. No CSS file
is needed unless you adopt JointJS+ in a future milestone.

Template `<script>` tag load order:

```html
{# Diagram canvas — no CSS needed #}
<script src="{% static 'planner/js/vendor/joint.min.js' %}"></script>

{# PNG export helper — loaded lazily in the export handler is fine #}
<script src="{% static 'planner/js/vendor/html-to-image.min.js' %}"></script>

{# Diagram module #}
<script src="{% static 'planner/js/signal_flow_diagram.js' %}"></script>
```

Whitenoise serves everything under `STATIC_ROOT` after `collectstatic`. No special
configuration needed — `.js` files are served with `application/javascript` (Whitenoise
ships its own MIME table, independent of the OS `/etc/mime.types`).

---

## JointJS Core: Package Details

| Attribute | Value | Source |
|-----------|-------|--------|
| Package name | `@joint/core` (renamed from `jointjs` in v4.0.0, Feb 2024) | npm |
| Current stable version | 4.2.4 (published ~Feb 2026) | npmjs.com/@joint/core |
| Previous stable | 4.1.4 (Mar 2025) | npm |
| License | MPL-2.0 | npmjs.com/@joint/core |
| Peer dependencies | **None** — v4.0 removed Backbone, jQuery, lodash | jointjs.com/blog/introducing-version-4 |
| UMD bundle (CDN) | `https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js` | jsDelivr |
| CSS required | No | Official docs JS integration guide |
| Bundle size (total, no deps) | ~1.1 MB unminified (44% reduction vs v3 + deps) | jointjs.com v4.0 announcement |
| Global variable exposed | `joint` (UMD build exposes `joint` on `window`) | Official docs |
| Browser support | Latest Chrome/Firefox/Safari/Edge/Opera (including mobile) | docs.jointjs.com FAQ |

**v4.x removed Backbone internals** but replaced them with an internal `mvc` namespace
(`mvc.Model`, `mvc.View`, `mvc.Collection`, `mvc.Events`). These are bundled inside
`joint.min.js` — there is nothing to install separately.

---

## PNG Export: Strategy

### Built-in JointJS raster export

`format.toPNG()` / `format.toJPEG()` / `format.toDataURL()` exist in the official docs
but are documented exclusively under **JointJS+** (the paid tier). They are NOT part of
`@joint/core`. Do not use them.

### Recommended: manual SVG → canvas → PNG (two options)

**Option A — `html-to-image` (recommended)**

`html-to-image` 1.11.11 is available as a UMD min file on cdnjs
(`https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js`).
Drop it in `vendor/`, call `htmlToImage.toPng(paperElement)` — it serialises the SVG
DOM to a `<canvas>`, then calls `canvas.toBlob()`. Returns a Promise resolving to a PNG
data URL. Works in Chrome, Firefox, Edge. Safari has `foreignObject` restrictions but
JointJS renders pure SVG (no HTML inside foreignObject), so the restriction does not
apply here.

```js
// signal_flow_diagram.js — export handler
document.getElementById('btn-export-png').addEventListener('click', async () => {
    const paperEl = document.getElementById('paper');
    const dataUrl = await htmlToImage.toPng(paperEl);
    const a = document.createElement('a');
    a.download = diagramName + '.png';
    a.href = dataUrl;
    a.click();
});
```

**Option B — native SVG serialise → canvas (no extra library)**

JointJS renders to SVG. You can serialise the SVG element to a string, create a Blob
URL, draw it into a `<canvas>` via `drawImage`, then call `canvas.toDataURL('image/png')`.
This requires ~20 lines of vanilla JS with no extra file to vendor. The tradeoff is
more manual handling of embedded fonts, `<image>` elements, and canvas tainting.

For v2.2 (smart shapes, cable connectors, text labels — no embedded images), Option B
is feasible. Option A is more robust and only costs one extra vendored file.

**Recommendation: use Option A (`html-to-image`) for v2.2.** The extra vendored file
is cheap insurance against SVG serialisation edge cases as the shape library grows.

---

## Python-Side: No New Dependencies Required

| Need | How Served | New dep? |
|------|-----------|---------|
| Store canvas JSON | `models.JSONField` — built into Django 3.1+, works on PostgreSQL as `jsonb` | No |
| Generic FK to equipment records | `django.contrib.contenttypes.fields.GenericForeignKey` — already in `INSTALLED_APPS` | No |
| Autosave endpoint | Plain Django `JsonResponse` view returning `{"ok": true}` — no DRF needed | No |
| PNG export trigger | Client-side only (Option A above) — server never touches image data in v2.2 | No |

**No additions to `requirements.txt`.**

---

## Autosave Endpoint: CSRF Integration

The autosave view is a vanilla `fetch` POST. Django's CSRF middleware is already active.
No special config needed — read the token from the `csrftoken` cookie (set automatically
by Django when any page with `{% csrf_token %}` is rendered) and send it as the
`X-CSRFToken` header:

```js
// Minimal CSRF-safe fetch helper — add to signal_flow_diagram.js
function getCsrfToken() {
    return document.cookie.split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
}

async function autosave(diagramId, graphJson) {
    await fetch(`/audiopatch/signal-flow/${diagramId}/save/`, {
        method: 'POST',
        mode: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({ graph: graphJson }),
    });
}
```

If the diagrammer page doesn't contain a `<form>` with `{% csrf_token %}`, decorate the
view with `@ensure_csrf_cookie` so Django sets the cookie on the GET request.

---

## Existing Stack Conflict Check

| Potential Conflict | Status | Detail |
|--------------------|--------|--------|
| CSP headers | No conflict | ShowStack does not configure CSP headers (not in `requirements.txt`, not in `MIDDLEWARE` in codebase). No `django-csp` or `Content-Security-Policy` response header in place. JointJS inline SVG and the PNG canvas path do not require `unsafe-inline` script allowances. |
| X-Frame-Options | No conflict | `X-Frame-Options: SAMEORIGIN` (Django default) only affects embedding ShowStack pages in iframes from other origins. The diagrammer runs inside the ShowStack page, not in an iframe. |
| CSRF on autosave | Handled | See pattern above — standard Django cookie + `X-CSRFToken` header pattern used by all other AJAX POST calls in the existing codebase. |
| Whitenoise static serving | No conflict | Whitenoise serves all files under `STATIC_ROOT` with correct MIME types from its own bundled MIME table. `.js` files get `application/javascript`. No SVG MIME-type quirk applies since the JointJS bundle is a `.js` file, not a `.svg` static asset. |
| Admin dark theme | Minor care needed | Templates for the diagrammer should extend `admin/base_site.html` (same as all other planner views) to inherit the dark theme. JointJS renders into a user-supplied `<div>` — set a white or light background on the paper container div explicitly, since the dark theme CSS does not know about JointJS internal SVG. |
| `django.contrib.contenttypes` | Already installed | Used by existing admin; no migration needed to add `GenericForeignKey` to the new model. |
| Sortable.js coexistence | No conflict | Sortable is used in other views (Crew Rosters). The diagrammer page loads its own JS files and does not share a page with Sortable. No global namespace collision; Sortable exposes `Sortable`, JointJS exposes `joint`. |
| Mobile `/m/` interface | Not in scope for v2.2; plan for v2.3 | JointJS "supports latest mobile Chrome and Safari" (from the docs FAQ) but touch-drag on mobile requires `dia.PaperScroller` or custom pointer event handling — that is a v2.3 concern. The `/m/` routes do not load the diagrammer in v2.2. |

---

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| `@joint/core` 4.2.4 (locked decision) | draw.io iframe embed | Loses native ShowStack UX; click-through-to-equipment-record not feasible across iframe boundary; already rejected in PROJECT.md key decisions |
| `@joint/core` 4.2.4 (locked decision) | maxGraph (mxGraph fork) | Requires TypeScript build step; no-build constraint from PROJECT.md |
| `@joint/core` 4.2.4 (locked decision) | Konva.js | Canvas-based (not SVG); hit-testing and label rendering are harder; no built-in graph model |
| `html-to-image` (Option A) | Option B: native SVG serialise | Works but more fragile for embedded images in future shapes; requires ~20 lines of careful canvas-tainting handling |
| `html-to-image` | `dom-to-image` | Unmaintained (last release 2019); html-to-image is the active maintained fork with same API |
| `html-to-image` | JointJS+ `format.toPNG` | Requires paid JointJS+ licence; not available in `@joint/core` |
| `models.JSONField` (built-in) | `django-jsonfield` (third-party) | Unnecessary — Django 3.1+ includes JSONField natively for all backends including PostgreSQL |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| JointJS+ (`@joint/plus`) | Commercial licence (separate paid SKU); `@joint/core` covers all v2.2 features | `@joint/core` 4.2.4 |
| `dom-to-image` | Unmaintained since 2019; unresolved bugs | `html-to-image` 1.11.11 |
| `canvg` | Heavy dependency for SVG→canvas; overkill since html-to-image handles it | `html-to-image` |
| React / Vue / Svelte | PROJECT.md constraint: vanilla JS only, no framework, no build step | vanilla JS + `@joint/core` |
| Any npm build toolchain (webpack, vite, rollup) | No-build constraint from PROJECT.md | vendor the pre-built UMD bundles |
| `django-csp` | ShowStack has no CSP today; adding it mid-milestone would require auditing every inline script and style across all existing views — massive scope expansion | Defer CSP hardening to a dedicated security milestone |
| `django-jsonfield` (PyPI) | Redundant — Django 5.x ships `models.JSONField` natively | `models.JSONField` |
| Celery / Redis | Not needed; autosave is a synchronous POST, not a background task | Django view + `JsonResponse` |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `@joint/core` 4.2.4 | Django 5.x (irrelevant — client-side only) | No server-side interaction beyond JSON blob read/write |
| `@joint/core` 4.2.4 | Whitenoise 6.11 | Whitenoise serves the `.js` file; no interaction with library internals |
| `@joint/core` 4.2.4 | Sortable.min.js (any version) | Both are UMD globals (`joint` vs `Sortable`); no namespace collision |
| `html-to-image` 1.11.11 | `@joint/core` 4.2.4 | html-to-image operates on a DOM element; JointJS renders its paper to a `<div>` containing an `<svg>` — fully compatible |
| `models.JSONField` | Django 5.2 / PostgreSQL (Railway) | Native support; stored as `jsonb` on PostgreSQL. Local SQLite dev also works (stored as text, Django deserialises transparently) |

---

## Acquisition

```bash
# Download vendored JS files (do this once, commit the files)
# @joint/core 4.2.4 UMD minified
curl -L "https://cdn.jsdelivr.net/npm/@joint/core@4.2.4/dist/joint.min.js" \
     -o planner/static/planner/js/vendor/joint.min.js

# html-to-image 1.11.11 UMD minified
curl -L "https://cdnjs.cloudflare.com/ajax/libs/html-to-image/1.11.11/html-to-image.min.js" \
     -o planner/static/planner/js/vendor/html-to-image.min.js
```

No `npm install`, no `package.json`, no build step. Consistent with the Sortable.min.js
precedent.

Add a `THIRD_PARTY_LICENSES.txt` at project root (or in `planner/static/`) citing:
- `@joint/core` 4.2.4 — Mozilla Public License 2.0 — https://github.com/clientIO/joint
- `html-to-image` 1.11.11 — MIT — https://github.com/bubkoo/html-to-image

---

## Sources

- [@joint/core on npm](https://www.npmjs.com/package/@joint/core) — version 4.2.4, license MPL-2.0 confirmed
- [JointJS v4.0 "Dependency-Free" announcement](https://www.jointjs.com/blog/introducing-version-4) — Backbone/jQuery/lodash removal confirmed
- [JointJS v4.2 docs: JavaScript integration](https://docs.jointjs.com/learn/integration/javascript/) — UMD script-tag installation, no CSS required
- [JointJS v4.2 release notes](https://docs.jointjs.com/learn/release-notes/) — current stable is 4.2.x
- [JointJS Raster export docs](https://docs.jointjs.com/api/format/Raster/) — documents `format.toPNG`; confirmed available under JointJS+ namespace only
- [JointJS SVG export docs](https://docs.jointjs.com/api/format/SVG/) — `format.toSVG` path
- [@joint/core on jsDelivr CDN](https://www.jsdelivr.com/package/npm/@joint/core) — CDN availability confirmed
- [Mozilla MPL 2.0 FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/) — commercial SaaS use permitted; file-level copyleft only
- [html-to-image on npm](https://www.npmjs.com/package/html-to-image) — v1.11.11, MIT, active maintenance
- [html-to-image on cdnjs](https://cdnjs.com/libraries/html-to-image) — CDN distribution confirmed
- [dom-to-image vs html-to-image comparison](https://npm-compare.com/dom-to-image,html-to-image,html2canvas) — html-to-image recommended as maintained fork (2025)
- [Django 3.1 JSONField release notes](https://docs.djangoproject.com/en/5.2/releases/3.1/) — built-in JSONField, no third-party dep needed
- [Django CSRF with fetch API](https://docs.djangoproject.com/en/5.2/howto/csrf/) — `X-CSRFToken` header pattern
- [Whitenoise documentation](https://whitenoise.readthedocs.io/en/stable/django.html) — ships own MIME table, no SVG/JS serving quirks

---

*Stack research for: ShowStack v2.2 Signal Flow Diagrammer*
*Researched: 2026-05-19*
