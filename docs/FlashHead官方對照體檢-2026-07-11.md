# FlashHead 官方 S2S 對照體檢報告（2026-07-11）

> Edward 拍板：停止修表面、拿官方即時串流做法當尺，逐段體檢我們的通話管線。
> 體檢對象：`deploy/runpod-avatar/flashhead_server.py`（獨立版）＋ `deploy/modal-avatar/flashhead_modal_dev.py`（Modal 版，關鍵邏輯經 grep 確認與獨立版一字不差）＋ `web/src/app.js` 通話整合面。
> 官方尺：台灣機 `/root/SoulX-FlashHead/` 的 `gradio_app_streaming.py`（官方唯一即時串流範例）、`flash_head/inference.py`、`flash_head/src/pipeline/flash_head_pipeline.py`、`flash_head/configs/infer_params.yaml`、`README.md`。全程只讀、未動任何服務。

**一句話總結：模型的餵法我們抄對了（audio_dq／索引窗／丟 motion 幀全對），錯的是官方根本沒教的那一段——官方把「同一塊的畫面和聲音」封進同一個檔案物理綁死，我們卻拆成兩條各自計時的水管，漂移、斷糧、殘留全是這裡漏的水。25 版補丁都在修水漬，沒修水管。**

---

## 一、確定做錯／漏掉（按影響排序）

### 🔴 第 1 名：影音沒有共同時鐘——「嘴聲不同步」的結構性根源

**官方怎麼做**：`gradio_app_streaming.py` 的 `save_video_with_audio()`——每一塊生成的 24 幀，跟這一塊自己的那 0.96 秒音訊，用 ffmpeg 封進**同一個 mp4 段**再交給播放器。畫面和聲音在檔案層就綁死，物理上不可能漂移。

**我們怎麼做**：畫面走 `FrameSink`（純 FIFO，`flashhead_server.py` L87-118），聲音走 `AudioOutBuffer`（20ms 幀，L178-213），WebRTC 兩軌**各自從連線起點鋪自己的時間軸**（影像軌 L365-376 恆速 25fps；聲音軌 L398-413 恆速 20ms），中間沒有任何機制把「這幀屬於哪 20ms 聲音」對起來。

**三個具體漏水口（都有行號）**：

1. **聲音斷糧塞零但不消耗**（L209-213）：`pop_frame()` 缺料時回傳 20ms 靜音、真音留在緩衝裡 → 每斷糧一次，真音**永久後移 20ms**。畫面斷糧則是重播上一幀（L379-386），內容**永久後移 40ms**。兩邊獨立發生、互不知情 → 偏移量隨機漫步，通話越久越歪。
2. **塞車修剪只丟畫不丟聲**（L104-107）：`FrameSink` 佇列超過 2 秒就從頭剪回 1.5 秒——畫面直接跳進未來 0.5 秒，聲音緩衝無上限、一格都不丟。網路一卡（WebRTC 停拉），恢復後就是「畫面跳過去了、聲音把積壓全部補播」＝一次性大漂移。
3. **0.3 秒 prebuffer 只墊聲音不墊畫面**（L51、L199、L203）：每次 `reset` 後 `hold_until_ts` 讓聲音先憋 0.3 秒、畫面照播 → **每一輪開頭，嘴先動、聲音晚 0.3 秒**，而且這 0.3 秒積壓整輪都還不掉。這正是 Edward 抓的「嘴巴跑在聲音前面」（app.js L1391 註解裡的症狀④）。

**對應症狀**：嘴聲不同步（結構性 0.3s ＋ 隨機漫步 ＋ 網路卡頓後大跳）。

**建議修法（塊級共同時間軸）**：chunk 是天然的同步單位——`_gen_chunk` 裡同一塊的 24 幀和 15360 個聲音樣本本來就一起出爐（L258-272）。讓兩軌共用一個「塊時鐘」：第 i 塊的畫面 pts 基準＝聲音 pts 基準＝`i × 0.96s`＋同一個起播偏移；斷糧時**兩軌一起**墊（畫面重播幀、聲音塞零，但各自把積壓內容的 pts 一起往後推）；修剪時**成對丟**（丟 0.5s 畫就丟 0.5s 聲）。做到這件事，其他 24 個同步補丁大多可以退役。

---

### 🔴 第 2 名：零起播緩衝——「嘴巴定格」的根源，官方白紙黑字警告過

**官方怎麼做**：`gradio_app_streaming.py` 開頭註解原話——「gr.Video 的 streaming=True 要求视频片段大于1s，**实际需要接近3s才能不卡顿**。为了适配，每 3 个 chunk 合并为一段视频」（`CHUNKS_PER_SEGMENT = 3`）。官方自己的即時 demo 都得靠約 3 秒的播放緩衝才順。

**我們怎麼做**：影像軌第一幀到就開播、佇列深度 0 起跑（`FlashHeadTrack.recv` L377-390 直接 pop）。而我們的 Feeder 是牆鐘節奏（L285 `due = t0 + consumed/SR`）＋每塊生成耗時 0.3-0.7s 有抖動 → 每個塊邊界，佇列剛好見底，下一塊晚到幾十 ms 就斷糧一次。Edward 實測「畫面斷糧 468 次＝嘴定格」就是這個；斷糧超過 0.35 秒還會退回海報（L384）＝講話講到一半臉變照片。

**對應症狀**：嘴巴定格、臉閃回照片。

**建議修法**：起播前先蓄 1 塊（0.96s，官方標準是最多 3s，我們是真即時通話、1 塊是延遲和順暢的平衡點），而且**兩軌一起蓄**（單墊一軌就是第 1 名的漏水口 3）。搭配第 1 名的共同時鐘一起做，等於把官方「3 chunk 合一段」的智慧搬進 WebRTC。

---

### 🔴 第 3 名：turn reset 重置不完整——「開頭嘴亂動／重撥繼續講上一段」的根源

**官方怎麼做**：每次 run 開始＝乾淨狀態。兩件事：
1. `audio_dq` 用**全零**新建（`inference_worker` 內 `deque([0.0] * cached_audio_length_sum)`）——音訊上下文窗從純靜音起步；
2. `get_base_data` → `prepare_params` → `reset_person_name()`（`flash_head_pipeline.py` L196-203）——把 motion cache（`latent_motion_frames`）重置回底圖 latent。

**我們怎麼做**：`feeder.reset()`（L249-256）只清 `acc`／`sink`／`audio_out` 三個緩衝，**`audio_dq` 和 pipeline 狀態一個都沒碰**。兩個後果：

1. **audio_dq 留著上一輪的音尾**：模型每塊實際讀的是 8 秒窗的最後 33 個影格位（`audio_start_idx=167, audio_end_idx=200`，L81-82）≈ 最後 1.32 秒。新一輪第一塊只帶 0.96 秒新音，剩下 0.36 秒是**上一輪被丟掉沒播的舊音** → 開頭嘴型被舊語音牽著走＝「下一輪開頭嘴亂動／像在接上一段」。
2. **in-flight 塊沒有世代檢查**：`reset()` 清緩衝的瞬間，若 `_gen_chunk` 正在 GPU 上跑（最長 0.7 秒），跑完照樣把 24 幀＋0.96 秒**舊音**推進剛清空的佇列（L270-272 沒有任何「這塊已作廢」判斷）→ 掛斷重撥（/offer 的 pre-call reset，L477-482）、用戶插話（app.js L1319 `Avatar.reset()`）都可能漏 0.96 秒舊聲畫進新回合＝「一接通就繼續播上一段」「插話後她又冒出半句舊話」。

**motion cache 要不要也重置？** 官方語意：run 內連續滾動（`generate()` 每塊拿結尾 9 幀 encode 成下一塊開頭，pipeline L300-308）、run 之間重置。我們的通話是「無限 run」＋idle 靜音塊維持連續性（L302-307），**motion cache 不重置是對的**（重置反而會讓臉跳回底圖姿勢）；要補的是音訊側——reset 時把 `audio_dq` 重填全零，讓模型跟官方 run 起點一樣「認為之前是靜音」。

**對應症狀**：下一輪開頭嘴亂動、掛斷重撥繼續講上一段、插話後殘句。

**建議修法**：`reset()` 加兩行——① `audio_dq` 重填 `cached_len_sum` 個 0；② 世代計數器 `self._gen_epoch += 1`，`_gen_chunk` 開跑前記下世代、push 前比對，不同就整塊丟棄。

---

### 🟡 第 4 名：0.8 秒到貨空窗誤判新回合——會整包吃字

**官方怎麼做**：沒有這種機制（官方是整檔輸入）。turn 邊界在 serving 場景應該只認**明確訊號**。

**我們怎麼做**：`push24k`（L238-245）看到「距上一包超過 0.8 秒」就自動開新回合、**`acc` 清空**——把還沒生成的音訊整包丟掉。語音腦是爆發式到貨（TTS 比即時快、囤了好幾秒 backlog 是常態），只要腦端／網路中途卡 0.8 秒，累積待播的話全被丟＝**句子中間直接吃字**，之後畫面聲音一起斷糧。而 app.js 明明已經有明確的 turn 訊號（`interrupted` → `Avatar.reset()`，L1315-1319）。

**對應症狀**：話講一半跳掉、之後嘴定格；也會放大「自問自答」觀感（她的話被吃掉半句，聽起來像沒頭沒尾自己接話）。

**建議修法**：拿掉 0.8 秒自動清 `acc` 的行為（保留開新 round 計數無妨），turn 邊界一律走 ws `reset` 明確訊號；或至少把判準從「到貨間隔」改成「播放連續性」（acc 已耗盡且靜音超過 N 秒才算新回合）。

---

### 🟡 第 5 名：np.interp 線性重採樣——嘴型輸入和用戶耳朵聽的都是髒的

**官方怎麼做**：`librosa.load(audio_path, sr=16000)`（soxr 高品質重採樣、帶抗混疊低通）；範例音檔本身就是 16k（`podcast_sichuan_16k.wav`）；wav2vec2-base-960h 訓練資料是乾淨 16k 語音。

**我們怎麼做**：`push24k` 用 `np.interp` 線性插值 24k→16k（L230-235）——沒有低通，8-12kHz 的內容會鏡像折返到 4-8kHz（混疊）；而且**逐 ws 訊息獨立插值**、訊息邊界不連續。雙重代價：① wav2vec 吃到帶混疊噪聲的輸入，嘴型判讀精度打折；② 同線模式下**用戶聽到的就是這條 16k**（L271-272 推進 audio_out 的正是它）——音質也一起犧牲。

**對應症狀**：嘴型「怪、對不太準」的殘餘感；聲音略毛糙。

**建議修法（一石二鳥）**：① embedding 路徑改用有狀態的串流重採樣（`scipy.signal.resample_poly` 按塊處理＋銜接、或 soxr 串流模式）；② 更好的一步——**audio_out 直接改播 24k 原音**（AudioOutBuffer 開 24k、原始 bytes 直通），16k 只餵模型。用戶耳朵拿回原音質，混疊只剩 embedding 一處要治。

---

### 🟢 第 6 名（已知、非 bug）：compile 預設關 vs 官方 96FPS 前提

**官方**：`flash_head_pipeline.py` L19-20 `COMPILE_MODEL = True`／`COMPILE_VAE = True` 是**預設值**——README 的「Lite 96 FPS／單卡 4090 三路併發 25+ FPS」是 compile＋flash_attn＋512×512＋4 步蒸餾採樣的數字。
**我們**：獨立版預設 eager（L35-37，`MUNEA_FH_COMPILE=1` 才開）。實測 eager 305ms/塊≈79FPS、渦輪載客 0.51s/塊≈47FPS——高於 25FPS 及格線但距官方 96 有差，主因就是 compile 開關與機器共載。
**官方有沒有我們沒做的管線並行？沒有。** 官方 worker 執行緒裡 `get_audio_embedding` → `run_pipeline` 也是**串行**，執行緒只把「存檔/封裝」跟生成平行化；我們的 Feeder 執行緒本質相同。逐塊重算整個 8 秒窗的 wav2vec 也是官方原設計，我們沒多花冤枉錢。
**建議**：常駐機（RunPod/Glows）一律 `MUNEA_FH_COMPILE=1`（開機稅一次性）；短命容器（Modal dev）維持 eager。此項已在 7/11 拍板執行中，列此為存證。

---

## 二、逐項對照表（A-G 完整回答）

### A. 音訊餵法 ✅ 過關（一字不差）

| 項目 | 官方（gradio_app_streaming.py） | 我們（flashhead_server.py） | 判定 |
|---|---|---|---|
| 每塊樣本數 | `slice_len * sample_rate // tgt_fps` ＝ 24×16000/25 ＝ **15360**（0.96s） | L80 同公式同值 | ✅ |
| 塊間重疊窗 | **沒有**——塊與塊音訊不重疊；上下文靠 8 秒 `audio_dq` 環形窗＋`audio_start_idx = end−frame_num`（每塊 embedding 自然回看前一塊尾 0.36s，正好覆蓋 9 個 motion 幀的音訊位置） | L81-84 完全相同 | ✅ |
| audio_dq | `deque([0.0]*128000, maxlen=128000)`，每塊 `extend` 後整窗餵 wav2vec | L84、L260-262 相同 | ✅ |
| 索引 | `audio_end_idx=200, audio_start_idx=167`；`get_audio_embedding` 取 ±2 幀上下文、clamp 到窗內（inference.py L60-70） | 同一函式直接呼叫 | ✅ |

塊邊界處理本身不是嘴慢半拍的元凶——那在 C。

### B. 節奏（pacing）⚠️ 我們自創、方向可守但要補緩衝

**官方**：inference worker「有塊就跑、跑完立刻下一塊」＝**爆發式**，完全不看牆鐘；即時感靠播放端 3 塊緩衝消化。
**我們**：Feeder 牆鐘節奏（L285），TTS 爆發到貨先囤 `acc`、照播放速率放行。
**評**：無限雙向通話不能學官方無限超前生成（插話會浪費算力＋加重截斷badge），牆鐘節奏本身合理；**但**牆鐘節奏＋零播放緩衝＝把 GPU 抖動全部直通到畫面（第 2 名）。建議折衷：允許 Feeder **領先牆鐘 1 塊**（bounded lookahead）——把 TTS 爆發轉成 1 塊的緩衝深度，GPU 尖峰有地方吸收，插話最多多丟 1 塊已生成內容。

### C. 影音同步 🔴 最大偏差（見第 1、2 名）

官方 pts 做法＝mp4 容器時間戳（ffmpeg 封裝時每幀 1/25s、音訊原生取樣率，同段共基準）。我們兩軌各自從連線起點鋪軸、無內容級配對 → 三個漂移源（斷糧不對稱、修剪不對稱、prebuffer 不對稱）。掉拍風險不是「有沒有」而是「結構保證會掉」。

### D. 首塊／motion_frames／reset ⚠️ 首塊對、reset 錯（見第 3 名）

- 丟前 `motion_frames_num`（lite＝9）幀：官方 streaming 每塊都丟（含第一塊），我們 L265 相同 ✅。
- 官方 run 起點＝audio_dq 全零＋`reset_person_name()`；我們 reset 兩者皆缺＋in-flight 漏塊 🔴。
- motion cache 在連續通話中**不應**重置（idle 靜音塊已維持官方語意的連續性）✅ 這點我們反而是對的。

### E. 取樣率鏈 🟡 偏差（見第 5 名）

官方期望 16k 乾淨語音（librosa/soxr 重採樣）；我們 np.interp 無抗混疊＋逐訊息獨立插值。影響嘴型精度（wav2vec 輸入髒）＋用戶聽感（同線模式聽的就是這條）。

### F. 效能 🟢 差距已解釋、無漏做的並行（見第 6 名）

96FPS＝compile+flash_attn+512²+4步 的 lite 數字；我們渦輪載客 0.51s/塊≈47FPS>25 及格。官方無音訊嵌入×視訊生成重疊，我們沒漏。

### G. 其他官方注意事項盤點

1. **「實際需要接近 3s 才不卡頓」**——官方 streaming 註解對 serving 最重要的一句話，我們違反（第 2 名）。
2. `loudness_norm` 官方自己註解掉（inference.py L58）——我們不做響度歸一化＝跟官方一致 ✅。
3. streaming 僅支援單 GPU（README）——我們單卡跑 ✅。
4. 環境：torch 2.7.1+cu128、flash_attn 2.8.0.post2、SageAttention 選配——與安裝腳本一致，未列異常。
5. `use_face_crop`：官方選配；我們 512² 預裁底圖傳 False ✅。
6. 官方 `torch.cuda.synchronize()` 僅為計時；我們 `.cpu()` 已隱含同步，無正確性差異 ✅。

---

## 三、症狀 ↔ 根因對照（25 版補丁在修誰）

| 症狀 | 根因（本報告編號） |
|---|---|
| 嘴聲不同步／嘴跑在聲音前面 | 第 1 名（0.3s prebuffer 不對稱＋斷糧隨機漫步＋修剪不對稱） |
| 嘴巴定格／臉閃回照片 | 第 2 名（零緩衝＋塊邊界見底）＋第 4 名（backlog 被丟後斷糧） |
| 她自問自答 | 主因在 client 回音（app.js speechActive 半雙工已治）；伺服器殘餘＝第 3 名 in-flight 漏塊讓她「講完又冒半句」 |
| 掛斷重撥繼續講上一段 | 第 3 名（/offer reset 已加但 in-flight race 沒擋＋audio_dq 殘留） |
| 下一輪開頭嘴亂動 | 第 3 名（audio_dq 留舊音、embedding 窗前 0.36s 被舊語音牽動） |
| 話講一半跳掉 | 第 4 名（0.8s 到貨空窗整包丟 acc） |

## 四、施工順序建議

1. **第 3 名（reset 補完）**：兩行級改動、風險最低、立刻治「重撥殘留／開頭亂動」→ 先上。
2. **第 4 名（拿掉 0.8s 丟包）**：一行級、治吃字 → 同批上。
3. **第 1＋2 名（塊級共同時鐘＋雙軌同蓄 1 塊）**：一次架構手術、治同步和定格的根 → 單獨一版、真機驗收「30 分鐘長通話不漂移」。上線後可退役大部分歷史同步補丁（faceSyncMs 殘餘、SYNC_BUFFER_MS 佔位常數等）。
4. **第 5 名（重採樣）**：跟 3 一起或次批；audio_out 直通 24k 是加分項。

---

## 附錄：證據行號索引

**我們（flashhead_server.py 獨立版；Modal 版 flashhead_modal_dev.py 對應行括號註）**
- L50-51 SR 常數＋AUDIO_PREBUFFER_S（Modal L91）
- L80-84 chunk_samples／audio_start_idx／audio_end_idx／audio_dq（Modal L152）
- L91-92／L104-107 FrameSink 深度與修剪（Modal L166-167／L179-180）
- L199／L203／L209-213 AudioOutBuffer hold 與 underrun 塞零不消耗（Modal L290/300/303）
- L230-235 np.interp 24k→16k（Modal L335）
- L238-245 0.8s 空窗開新回合＋清 acc（Modal L339）
- L249-256 reset 只清三緩衝（Modal L350-357）
- L258-277 _gen_chunk：dq.extend→embedding→run_pipeline→丟 motion 幀→雙推（Modal L361 起）
- L285 牆鐘 due（Modal L386）
- L302-307 idle 靜音餵食
- L365-390 影像軌恆速＋0.35s 退海報（Modal L498）
- L398-413 聲音軌自鋪時間軸
- L477-482 /offer pre-call reset（Modal L426）

**官方（/root/SoulX-FlashHead/）**
- gradio_app_streaming.py：頭部註解 CHUNKS_PER_SEGMENT=3（「实际需要接近3s才能不卡顿」）；`save_video_with_audio()` 同塊聲畫封裝；`inference_worker()` 爆發式生成＋audio_dq 全零起步＋`video[motion_frames_num:]`
- flash_head/inference.py：`get_audio_embedding` 索引窗（±2 clamp）；`loudness_norm` 註解掉
- flash_head/src/pipeline/flash_head_pipeline.py：L19-20 COMPILE 預設 True；L196-203 `reset_person_name`（motion cache 重置回底圖 latent）；L300-308 motion cache 滾動（結尾 9 幀→vae.encode→下塊開頭）
- flash_head/configs/infer_params.yaml：frame_num 33／tgt_fps 25／sample_rate 16000／cached_audio_duration 8
- README.md：Lite 96FPS／三路 25+FPS 單 4090；streaming 單 GPU

**App 端（web/src/app.js）**
- L1354 `Avatar.feed(ev.data)` 24k 原封轉送臉
- L1315-1319 `interrupted` → 停播＋`Avatar.reset()`
- L1297-1306 半雙工閉麥（speechActive 單一真相）
- L1093-1106 同線兩軌（聲音由影像播放器出）
- L1382-1399 非同線本地播放＋faceSyncMs 補償（同線模式無法用此補償 → 更依賴伺服器側對時）

*體檢執行：城堡架構稽核 · 2026-07-11 · 只讀不改，官方碼經 SSH（BatchMode）讀取*
