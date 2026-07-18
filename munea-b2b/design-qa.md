# Design QA — B2B call screen

- Source visual truth: `C:\Users\Administrator\Desktop\App store pic\聊聊.png`
- Implementation screenshot: `C:\Users\Administrator\.codex\visualizations\2026\07\18\019f7344-5f07-71a2-a700-60eb918bd6cc\b2b-app-reference-idle-v2.png`
- Side-by-side evidence: `C:\Users\Administrator\.codex\visualizations\2026\07\18\019f7344-5f07-71a2-a700-60eb918bd6cc\b2b-design-qa-comparison.png`
- Viewport: 332 × 744
- State: unlocked, female character selected, idle / not connected

## Full-view comparison evidence

The implementation matches the reference's full-height portrait composition, top presence/status row, timer and allowance metrics, three-control call bar, lower centered close control, warm photographic palette, translucent dark secondary controls, and turquoise primary action. The browser version intentionally omits the iOS system status bar. The two portrait selectors on the right are an intentional B2B-demo addition explicitly requested by the user.

## Focused-region comparison evidence

The combined image is large enough to inspect the top status/metrics row and lower call controls at native size. The controls align at the same vertical band as the reference; button size, radius, icon weight, label density, and close-button placement are materially equivalent. A separate crop was not needed.

## Required fidelity surfaces

- Fonts and typography: system sans-serif family, bold compact status labels, tabular timer figures, and small secondary labels match the reference hierarchy. B2B copy intentionally uses `體驗 03:00` instead of App credit balance.
- Spacing and layout rhythm: full-height 332 × 744 frame, top row, subject scale, controls, and close button align with the reference. Right-side character selection is intentionally additive.
- Colors and visual tokens: warm image palette, white UI text, muted translucent charcoal controls, gray offline dot, and turquoise primary action match the App language.
- Image quality and asset fidelity: the implementation reuses Munea's supplied female/male FlashHead images and existing App icon paths; no placeholders remain.
- Copy and content: `寧寧`, `未在線`, `00:00`, `字幕`, `麥克風`, and `開始通話` match the App. Only the B2B allowance copy and requested role labels differ intentionally.

## Interaction and browser evidence

- Female and male character selectors change the active role.
- Caption and microphone controls toggle their selected/muted states.
- The call control completed microphone permission, Avatar health, WebRTC ICE, decoded first video frame, Avatar audio WebSocket, Voice `ready`, and visible `在線` gates.
- A cold Avatar start produced five expected health timeouts, then recovered and connected without a page error.
- Browser page errors: none.

## Comparison history

1. First capture: P1 full-height mismatch. The fixed 9:16 frame was vertically centered in a 332 × 744 viewport, creating black bands, shrinking the person, and placing the close control outside the photograph.
2. Fix: changed the portrait frame to fill `100dvh` while preserving the centered desktop width and cover crop.
3. Second capture: black bands removed; subject scale, top row, call controls, and close control now align with the reference. No actionable P0/P1/P2 mismatch remains.

## Follow-up polish

- P3: a production-owned TURN-over-TLS endpoint on port 443 would improve restrictive corporate-network compatibility; this is transport resilience, not a visual mismatch.

final result: passed
