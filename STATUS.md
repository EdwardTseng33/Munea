# STATUS · 2026-07-03 深夜（Windows 機 · 蘇菲）
- 今日：提醒彈窗化＋排程、家庭同步底座（A說B見）、錢包上雲＋1點/分修正、問答真排名、聊聊代辦/傳話、成本護欄前端層、破框制度、兩機協作制度。全數已推 GitHub main。
- 聊聊計分卡：4🟢2🟡4🔴（#6 今晚轉綠）；紅=真鑰匙/延遲/打斷/動臉（多數待 Mac+真機階段）。
- 下一步（本機）：角色照重畫（生圖之手）＋女巫把關；Codex：/chat 鑰匙載入確認、正式帳本；Mac 開工首日清單見 docs/兩機協作。

## 2026-07-03 Update - Codex AI key doctor

**Status:** completed for the `/chat` key-loading verification lane.

- Added `scripts/ai-key-doctor.ps1`, `npm run ai:doctor`, and `npm run ai:doctor:live` so Munea can verify backend AI key visibility without exposing secret values.
- The doctor distinguishes process environment variables, `engine/.env.local`, and keys blocked by `MUNEA_SKIP_ENV_LOCAL`, matching the real engine loader behavior.
- Updated staging and infrastructure docs so `/chat` / real Gemini validation has a clear preflight before Claude runs boundary or dialogue acceptance tests.
- Avoided `engine/server.py`, `engine/chat_engine.py`, `engine/memory_engine.py`, `engine/perception_engine.py`, `web/`, and `supabase/sql/` to stay out of Claude / Edward active lanes.

## 2026-07-03 Update - Avatar asset rename guard

**Status:** completed for asset stability.

- Synced the new companion avatar asset names across onboarding, landing, settings, companion profile adapter, and persona templates.
- Added a release smoke check that scans avatar references in web/persona files and fails if any referenced image is missing.
- Verified `npm run release:check`; the new avatar asset check found 34 references and all referenced files exist.

## 2026-07-03 Update - Codex Mac day-one doctor

**Status:** completed for the TestFlight handoff lane.

- Added `scripts/mac-day-one-check.sh` and `npm run mac:doctor` so the Mac can verify Git, Node/npm, PowerShell, Xcode, xcrun, repo state, and Capacitor config before generating the iOS project.
- Updated `docs/TESTFLIGHT-MAC-HANDOFF-2026-07-02.md` with `npm run mac:doctor` and the PowerShell install note needed for repo smoke scripts on macOS.
- Updated `docs/APP-STORE-PRODUCTION-READINESS.md` so Mac prerequisite verification is an explicit TestFlight readiness step.
- Avoided memory, perception, Supabase schema, backend behavior, and main product UI lanes while Claude / Edward continue active feature work.
