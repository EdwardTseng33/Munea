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

## Motion follow-up QA — App-style pre-call sequence

- Source visual truth: `web/avatars/motion/nening-hello.mp4`, `web/avatars/motion/nening-idle.mp4`, `web/avatars/motion/ahong-hello.mp4`, and `web/avatars/motion/ahong-idle.mp4`. Their SHA-256 hashes match the four files supplied in `C:\Users\Administrator\Desktop\Video`.
- Implementation screenshots: `b2b-motion-female-hello-v2.png`, `b2b-motion-female-idle-v3.png`, `b2b-motion-male-hello-v2.png`, and `b2b-motion-male-idle-v3.png` in the Codex visualization folder.
- Combined comparison evidence: `C:\Users\Administrator\.codex\visualizations\2026\07\18\019f7344-5f07-71a2-a700-60eb918bd6cc\b2b-motion-design-qa-comparison.png`.
- Viewport: 430 x 932.
- States: female hello, female idle, male hello, and male idle, all unlocked and not connected.

The comparison places each original App motion frame beside the B2B implementation at the same viewport. Subject, crop, scale, sharpness, background, color, and animation frame match because the exact supplied App videos are used. The B2B status row, role rail, and call controls are intentional UI overlays and remain clear without obscuring the face.

### Motion fidelity surfaces

- Fonts and typography: unchanged from the previously passed call-screen QA; the overlays remain legible across both characters and motion states.
- Spacing and layout rhythm: 430 x 932 cover crop matches the source; the top row, role rail, call bar, and close control remain stable during hello-to-idle transitions.
- Colors and visual tokens: source video colors are preserved with no filters; App-style teal, charcoal, white, and offline gray overlays remain consistent.
- Image quality and asset fidelity: exact App MP4 assets are shipped, with no regenerated or approximated motion. Two preloaded video surfaces crossfade to prevent a blank frame at the hello-to-idle boundary.
- Copy and content: role labels and call controls remain unchanged; no animation-specific text was added.

### Motion interaction evidence

- Female sequence resolved `nening-hello.mp4` then `nening-idle.mp4`.
- Male sequence resolved `ahong-hello.mp4` then `ahong-idle.mp4` after switching roles.
- Caption and microphone controls remained functional in both idle states.
- Expected behavior matches the App: hello plays once, idle repeats, role switching restarts that role's sequence, and live Avatar replaces idle motion only after the realtime video track arrives.

### Motion comparison history

1. Earlier B2B build: P1 behavior mismatch — the female greeting video looped continuously and the male role had no pre-call motion.
2. Fix: added both supplied hello/idle pairs and implemented the App's hello-to-idle sequence with two preloaded video surfaces.
3. Post-fix comparison: all four source/implementation states use the same subject, frame, and crop; no actionable P0/P1/P2 mismatch remains.

Focused region comparison was not needed because the subject, face, hands, crop edges, and all persistent UI controls are clearly visible at native 430 x 932 in the combined evidence.

## Live Avatar alignment follow-up — 2026-07-20

- Failing source screenshot: `C:\Users\ADMINI~1\AppData\Local\Temp\codex-clipboard-5d07ab56-12e9-4ff9-90f5-35f4d23e7c49.png`
- App visual reference: `C:\Users\Administrator\Desktop\App store pic\聊聊.png`
- Connected female screenshot: `C:\Users\Administrator\.codex\visualizations\2026\07\18\019f7344-5f07-71a2-a700-60eb918bd6cc\b2b-wss-clean-a05.png`
- Connected male screenshot: `C:\Users\Administrator\.codex\visualizations\2026\07\18\019f7344-5f07-71a2-a700-60eb918bd6cc\b2b-wss-sustained-a06.png`
- App/browser comparison board: `C:\Users\Administrator\.codex\generated_images\019f7344-5f07-71a2-a700-60eb918bd6cc\exec-31fbcc7c-9e3a-46d6-9b7c-5639574c7526.png`
- Verified viewport/state: 430 x 932, female `a05` and male `a06`, live FlashHead output connected and speaking.
- Root cause evidence: the deployed model used a different portrait source while the B2B overlay used a native square crop. The demo source is the App portrait crop `(0, 140, 1080, 1440)` resized to 512 x 512, and the browser inverts that transform at `top=7.291667%`, `height=75%`, `object-fit=fill` with four-edge feathering.
- ⚠ 2026-07-21 分家（修正 7/20 的副作用）：上面這個裁切**只屬於展示間**。當時為了對齊 demo，把正式線的 `a05`/`a06` 條件圖一起換成這個壓扁裁切，但 App 的貼合數字（`web/src/styles.css` `.fh-overlay`，a05 貼 `y=190`、a06 貼 `y=209`、原生正方形）沒跟著改，正式 App 的頭因此被壓成 75% 高、上移 50px、領口與立繪錯開成疊影。現在展示間改用專屬角色代號 `a05d`/`a06d`，正式線的 `a05`/`a06` 一律是原生正方形裁切，兩邊互不影響。
- Drift guard: `scripts/test-avatar-render-contract.py`（已接進 CI `Smoke` 與 `npm run test:avatar-contract`）比對三處貼合約定（兩支引擎＋機器端重建工具）、四張條件圖、以及 **App 自己的貼合數字**。7/20 那次的三種改法（只改一台引擎／兩台一起改／連素材一起換）都已實測會被擋下。
- 機器端：`deploy/runpod-avatar/sync-face-assets.py` 讓每台臉機器直接抓正式線出貨的立繪、照約定自己切條件圖，不再人工搬檔案——這是「三台機器各用各的素材」的根治。
- Transport evidence: Modal and the external TURN VM exchanged packets but ICE did not complete. The B2B browser now uses a WSS JPEG stream backed by the same FlashHead feeder/model; voice input and generated Avatar frames remain real, while browser playback uses the same returned 24 kHz PCM.
- Female final live run: connected in 2.510 s on the warm GPU, first assistant audio in 596 ms, 40 decoded frames, 294,242 audio bytes, Web Audio state `running` with 9.982 s scheduled, no console errors, no autoplay prompt, idle motion stopped.
- Male live run: connected in 2.452 s on the warm GPU, first assistant audio in 607 ms, 40 decoded frames, 208,350 audio bytes, no console errors, no autoplay prompt, idle motion stopped.
- Visual comparison: the App reference and connected browser screenshot preserve the same portrait scale, crop, face/shoulder/chest alignment, top status row, timer band, control band, close button, warm palette, and feathered compositing. The right-side role selector and B2B countdown are intentional requested differences.
- Autoplay UX: transient `AbortError` events caused by reconnect/source replacement are ignored. Only a genuine browser `NotAllowedError` can show a compact recovery pill; the former full-screen unexplained overlay is removed.
- Cold-start handling: the observed cold L4 allocation took 134 seconds, while warm calls connected in 2–3 seconds. The UI now reuses the prewarm request, keeps one calm `正在準備視訊` state for up to 165 seconds, leaves the App-style idle motion visible, and waits to open the microphone/Voice socket until the GPU is ready.

final result: passed
