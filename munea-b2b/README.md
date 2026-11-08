# Munea B2B pre-sales site

Vercel project: `munea-b2b` (`https://munea-b2b.vercel.app/`).

## ⚠ `index.html` is generated — edit `b2b-src/`, not the output

The pre-sales page ships in four languages from one template:

- **Source of truth**: `b2b-src/index.html` (layout, `{{key}}` placeholders) + `b2b-src/i18n/{zh,en,ja,es}.json` (copy) + `b2b-src/config.json`.
- **Output**: `munea-b2b/index.html` (zh), `munea-b2b/{en,ja,es}/index.html`, plus `sitemap.xml` and `robots.txt`.
- **Build**: `npm run b2b:build`. **Guard**: `npm run test:b2b-i18n` (rebuilds first, so direct edits to the output are overwritten and caught).

Four real URLs with hreflang cross-links, not JS switching — search engines only index the version they can see. Chinese lives at `/`; the others at `/en`, `/ja`, `/es` (no trailing slash, matching the main site's convention).

Two things deliberately stay Chinese on every language: the brand mark (`沐寧`) and the form's submitted `value=""` attributes, so leads land in one consistent format regardless of the visitor's language. The submitted payload carries a `lang` field instead.

## No web call demo (removed 2026-11-05)

The browser "try a call" demo (`call.html`, `api/call-key.js`, `flashhead/`, `test-call-browser.mjs`) was removed on Edward's decision: the iPhone app is live, so the page now points visitors to the App Store ("download the app and try it", section `#try-app`). The Ningning / Mumu demo videos in `#demo` stay.

Old links to `/call.html` and `/call` are redirected to the home page by `vercel.json` (added in PR #663). Do not re-add a web call page without a new decision; it would need its own guest-session control plane (short-lived tokens, per-visitor limits, separate cost metering) rather than a shared passphrase.

`api/lead.js` (the booking form) is unchanged.

## Checks

```powershell
npm run test:b2b-i18n
```
