# Munea B2B pre-sales site

Vercel project: `munea-b2b` (`https://munea-b2b.vercel.app/`).

## ⚠ `index.html` is generated — edit `b2b-src/`, not the output

The pre-sales page ships in four languages from one template:

- **Source of truth**: `b2b-src/index.html` (layout, `{{key}}` placeholders) + `b2b-src/i18n/{zh,en,ja,es}.json` (copy) + `b2b-src/config.json`.
- **Output**: `munea-b2b/index.html` (zh), `munea-b2b/{en,ja,es}/index.html`, plus `sitemap.xml` and `robots.txt`.
- **Build**: `npm run b2b:build`. **Guard**: `npm run test:b2b-i18n` (rebuilds first, so direct edits to the output are overwritten and caught).

Four real URLs with hreflang cross-links, not JS switching — search engines only index the version they can see. Chinese lives at `/`; the others at `/en`, `/ja`, `/es` (no trailing slash, matching the main site's convention).

Two things deliberately stay Chinese on every language: the brand mark (`沐寧`) and the form's submitted `value=""` attributes, so leads land in one consistent format regardless of the visitor's language. The submitted payload carries a `lang` field instead.

`call.html` (the live demo) is Chinese-only — the companion speaks Traditional Chinese, and every language's demo copy says so.

## Voice/avatar demo contract

The public pre-sales page exposes one interactive path only:

1. The visitor unlocks the partner preview.
2. `call.html` requests runtime configuration from `/api/call-key`.
3. The page connects to the configured Voice WebSocket with `demo=1` and to the configured FlashHead avatar service.
4. The browser sends microphone audio and renders generated voice plus avatar video. There is no text-chat fallback.

The call UI follows the App's full-screen `聊聊` pattern: one immersive person view, a compact back/status row, two portrait selectors on the right, and one call button at the bottom.

A successful dial is stricter than `/health` returning 200. It requires microphone permission, Avatar health, a connected WebRTC candidate pair, at least one decoded video frame, an open Avatar audio WebSocket, Voice `ready`, and the visible `在線` state.

`demo=1` must be deployed in `engine/live_voice_server.py` before this site version goes live. Demo mode does not read user memory or health context, expose reminder/event tools, or persist the conversation.

Required Vercel environment variables:

- `DEMO_AVATAR_HTTP`
- `DEMO_AVATAR_KEY`
- `DEMO_VOICE_WS`
- `DEMO_CAP_SECONDS` (recommended: `180`)

The hard-coded fallback values in `api/call-key.js` are temporary compatibility only. Remove them after the Vercel environment is confirmed; do not treat a shared static key as a production guest-session design.

## Production guest-session gap

The current B2B route reaches the real realtime Voice and avatar engines, but it is not the App production Gateway call-control path. Before broadly opening the demo, add a Gateway-issued short-lived guest call token with:

- one-time or short-lived lease binding;
- per-IP/device daily limits;
- a whole-site daily minute cap;
- a visitor-specific capacity pool with production users prioritized;
- separate cost metering and no user-account persistence.

Until that control plane exists, keep the demo behind the partner passphrase and a small invite-only audience.

## Checks

```powershell
node munea-b2b\test-static.mjs
python engine\test_b2b_demo_voice_isolation.py
python -m py_compile engine\live_voice_server.py engine\test_b2b_demo_voice_isolation.py
```

`test-call-browser.mjs` performs the real Chrome acceptance check with fake microphone input. Set `B2B_DEMO_PASS`; optional variables include `B2B_CALL_URL`, `B2B_TEST_CHAR` (`a05` or `a06`), `B2B_CALL_SCREENSHOT`, `PLAYWRIGHT_MODULE`, and `B2B_CALL_CONFIG_JSON` for a local static server.
