# RunPod 4090 · 寧寧臉引擎部署包（測試＝正式縮小版）

> 對應計畫：`docs/4090上雲測試計畫-2026-07-08.md`
> 狀態：骨架已備、D1 開卡後現場補完（Ditto 版本/權重下載細節以官方 repo 當日為準）

## 元件

| 檔案 | 用途 |
|---|---|
| `bootstrap.sh` | 開卡後一鍵裝機：Ditto + TensorRT + 我們的串流橋 |
| `.env.example` | 需要的鑰匙清單（真值不進程式庫） |
| （D1 現場補）`avatar_cloud_server.py` | 雲端版臉服務：Ditto 生成 → WebRTC；沿用本機版的對時/羽化/門禁設計 |

## 開卡規格（拍板）

- GPU：RTX 4090 24GB（Secure Cloud 優先、按需計費 ~US$0.69/hr）
- 模板：官方 PyTorch 2.x + CUDA 12.x 映像
- 開放的門：443（發碼+信令）、TURN 中繼埠（手機穿牆用）
- 磁碟：50GB（模型權重＋TensorRT 引擎檔）

## 安全規矩（測試也照正式）

1. 所有鑰匙（GEMINI_API_KEY / RUNPOD_API_KEY / DEMO_CODE）只放環境變數
2. 對外連線必帶短效通行碼（沿用 demo-cloud 發碼窗口模式）
3. 測試預算 US$15 到頂自動關卡（控制器腳本監控）
4. 上線前過沙利曼信任關卡

## 成本紀錄

每次開卡在本 README 底部記一行：日期／時長／花費／做了什麼。回填毛利表。

---
*骨架 2026-07-08 · 蘇菲。D1 現場補完後此行刪除。*

## 成本紀錄

| 日期 | podId | 開始(TST) | 結束 | 時長 | 費用 | 內容 |
|---|---|---|---|---|---|---|
| 7/8 | j5r4dj78m8jtdn | 19:29 | 20:11 | 0.7hr | ~US$0.48 | D1 全達成：裝機+寧寧離線影片（基礎0.16x/加速1.1x即時）+配方固化，已銷毀 |
| 7/8 | cxka4f46939pjr | 21:03 | 21:27 | 0.4hr | ~US$0.28 | D2 核心：串流模式實測——每塊 45ms/預算 200ms（22%）、單卡理論 3-4 路、畫質同離線版；已銷毀 |
| 7/8 | l0zqjn8zpmy1mt | 21:23 | 跑著(Edward試玩) | — | $0.69/hr | D2b：雲端通話服務雛形通——本機聲音×雲端臉×穿牆中繼、端對端 214 幀 |
| 7/8-9 | ro3x0qw4n27vhq | 23:40 | 00:05 | 0.4hr | ~US$0.28 | 暫停⇄喚醒實測：暫停3秒✓；**喚醒失敗（睡15分鐘後原主機GPU被租走、無法啟動）**——暫停不保留顯卡＝此路線不可當主機制；已銷毀 |
| 7/8-9 | 6i23actp1oe76v | 22:58 | 00:08 | 1.2hr | ~US$0.83 | ⚠ 教訓：Edward 中斷裝機後這張卡沒被收、白跑 1 小時——已補「開卡必掛看門狗」規矩；已銷毀 |
| 7/9 | x0mpl07vw0qlg6 | (中斷) | (Edward手動terminate) | 0.2hr | ~US$0.14 | 上輪 session 中斷未收尾，Edward 手動止血；已銷毀 |
| 7/9 | 3m6ds37710cww7 | 22:42 | 22:49 | 0.1hr | ~US$0.07 | D阿原demo：掛置物櫃erzzyyuen4零重裝、阿原(Algenib聲)對嘴demo成片15.6s，已下載+已銷毀 |
| 7/9-10 | 9wsg1utzpb8tei | 00:12 | 00:21 | 0.15hr | ~US$0.10 | D擬真女+插畫女對嘴demo：掛置物櫃erzzyyuen4零重裝（清stale pyxbld重編）→realfemale(avatar-05·Leda寧寧聲·13.0s)+illustfemale(avatar-02·Callirrhoe小昀聲·11.84s)兩支512×512 h264+aac對嘴demo一次生完，抽幀確認嘴型開合正常/畫面乾淨，已下載+已銷毀 |
| 7/9-10 | k0dso2qrmcxrgu | 01:46 | 01:54 | 0.13hr | ~US$0.09 | D擬真男對嘴demo：掛置物櫃erzzyyuen4零重裝（清stale pyxbld重編+裝ffmpeg）→realmale(avatar-06·Algenib阿原沉穩男聲·12.72s)對嘴demo，Ditto輸出原生1080×1080再ffmpeg降到512×512(h264+aac)對齊既有規格，抽幀確認嘴型開合(3張皆不同開合幅度)/畫面乾淨/眼鏡位置穩定，已下載+已銷毀 |
| 7/10 | jc6wwtunellsud | 18:09 | 18:19 | 0.16hr | ~US$0.11 | D頭到胸放寬重裁demo：掛置物櫃erzzyyuen4零重裝（清stale pyxbld+裝ffmpeg一次到位）→裁切放寬「頭頂到胸」box(0,260,1080,1340)套avatar-05/06兩張源圖（三支同框對齊）→realfemale-talk-demo（Leda寧寧聲·14.76s）+realmale-talk-demo（Algenib阿原聲·14.92s）+realfemale-hero-idle（短招呼1.76s+尾端8.5s靜音·10.28s·打招呼→自然待機）三支512×512 h264+aac一次生完，抽幀9張全PASS（肩膀/胸口皆入鏡、嘴型3態各異、待機段嘴閉合微笑+自然頭部微姿態），已下載+已銷毀 |
| 7/10 | dpfq8g4j5kdnb0 | 18:34 | 18:43 | 0.14hr | ~US$0.10 | D改直式露胸demo（Edward「上一版方形只到肩膀，要露到胸口」）：掛置物櫃erzzyyuen4零重裝（清stale pyxbld+裝ffmpeg+查cudnn8路徑三項排雷照跑無踩雷）→本機先用Gemini TTS生新台詞wav（同一句「欸，你來啦...我都在」，寧寧Leda 11.49s／阿原Algenib 12.05s）→裁切改**直式**box(0,140,1080,1580)＝1080×1440(3:4)（比上輪(0,260,1080,1340)方形往下多帶、頭頂留空、下緣到胸口明顯below鎖骨，同box套avatar-05/06兩張源圖對齊）→Ditto TRT對嘴輸出原生1080×1440→ffmpeg scale=810:1080降尺寸(h264+aac)＝**兩支直式810×1080**，抽幀各3張(共6張)全PASS：胸口/上胸清楚入鏡(不只肩膀)、嘴型3態各異、眼鏡髮型穩定、兩支框線對齊，已下載覆蓋`web/avatars/motion/realfemale-talk-demo.mp4`+`realmale-talk-demo.mp4`+已銷毀 |
| 7/10 | ibxeaxl3qcqom5 | 18:19 | 18:50 | 0.51hr | ~US$0.35 | **FlashHead PoC**：全新裝機（torch2.7.1+cu12.8.1官方映像零重裝命中、免裝torch/ffmpeg）+SoulX-FlashHead-1_3B Lite權重(6.1GB)+VAE_LTX(1.68GB)+wav2vec2(377MB)下載+flash-attn 2.8.0.post2預編譯wheel裝機，共9分鐘環境就緒→avatar-05×poc-mandarin(20.68s主測)+avatar-05×poc-taiwanese(7.16s)+avatar-05×poc-greet-idle(10s打招呼→待機)+avatar-06×poc-mandarin(20.68s)+avatar-05×poc-drift-long(255.36s/4.3分鐘長講)共5支512×512@25fps影片全部生完，穩態96FPS/3.8x即時（與官方README「Lite 96FPS」宣稱吻合）、VRAM峰值僅~6.3GB（單卡24GB可容3路），4.3分鐘長講266塊全程0.25s/塊零漂移、10s/120s/240s抽幀肉眼確認人物不跑版；已下載5支mp4+16張抽幀+已銷毀 |
| 7/10 | 9dgo01roe50aq8 | 19:15 | 19:21 | 0.09hr(壞卡) | ~US$0.06 | **FlashHead 第二輪-A**：Secure/Community 4090 一度連續 500「無資源」錯誤（RunPod當時4090緊繃，重試5次才開成功）→開成功後卡在同一實體機`2pq5f32wv38g`、RUNNING狀態但`machine`欄位空、5分鐘拿不到IP，判定壞卡，未跑任何工作，已銷毀止血 |
| 7/10 | gap8fvzuo1e80h | 19:21 | 19:25 | 0.06hr(壞卡) | ~US$0.04 | **FlashHead 第二輪-B**：重開又分到同一實體機`2pq5f32wv38g`、再度3.5分鐘拿不到IP，判定同一台機器有問題、未跑工作已銷毀，改寫成帶「壞機器黑名單+逾時自動重試」的開卡迴圈 |
| 7/10 | or03mcffidspvu | 19:26 | 19:38 | 0.20hr | ~US$0.14 | **FlashHead 第二輪-C（成功）**：換到`bm2w3s5hasac`（EU-RO-1）正常開機，沿用同配方裝機零重踩雷（requirements 3 修法+flash-attn wheel 一次成功）→Edward看片打回「頭部大擺動頭頂融合帶」問題，用新裁切框(頭頂多留白)+512×512現成圖驗證：gen6(a05-inA×mandarin,頭部大幅低頭動作全程無融合帶✓)+gen7(a05-inA×greet-idle,回待機自然)+gen8(a05-inB壓扁圖×mandarin,臉偏寬但無破圖/嘴型正常)+gen9(a06-inA×mandarin)+gen10(a06-inB壓扁圖×mandarin)共5支512×512@25fps一次生完，穩態0.223s/塊(比第一輪0.25s快、不同機器GPU時脈差異)，已下載5支mp4+15張抽幀+已銷毀 |
| 7/10 | vxktxufrybeqze | 20:13 | 20:46 | 0.55hr | ~US$0.38 | **動物臉 PoC（FasterLivePortrait animal 模式）**：直接拿 `shaoguo/faster_liveportrait:v3` Docker 映像當 pod 映像＋`dockerStartCmd` 自帶 sshd（TRT 8.6.1.6/torch2.0.1cu117/XPose op 全預裝、零編譯）→ HF 抓 3GB 權重子集＋9 顆 TRT 引擎現場轉（~13 分鐘）→ 咪咪(avatar-03 卡通貓)×gen1 真人說話驅動：**XPose 認得卡通貓臉、嘴型開合/吐舌/頭部跟動全有**；旺財(avatar-04 卡通狗)也認得＋會動，但源圖本來就開口吐舌→嘴型變化幅度小（driving_multiplier 1.5 加碼輪也只小改善）＝**狗要重繪閉嘴版源圖**。速度：median 18.3ms/幀(54FPS)、mean 34ms/幀(29FPS≈1.2x即時)、整支 20.68s 成片含載模端到端 ~57s；VRAM 峰值 3.65GB。3 支成片＋18 抽幀已下載 `flashhead-poc/outputs/animal-poc/`，已銷毀 |

## 排雷追加（7/9-10 這輪確認）

- **stale pyxbld 陷阱再現**：這次掛置物櫃時 `/workspace/pyxbld` 已是前一輪（不同 pod）留下的編譯快取，直接用會炸——已照 SOP `mv pyxbld pyxbld.stale-$(date +%s) && mkdir -p pyxbld` 清乾淨重編，正常。**新卡務必先跑這步，不能省。**
- **新卡沒 ffmpeg**（教訓）：`apt-get install ffmpeg` 是裝進**容器磁碟**、不是置物櫃，所以**每張新卡都要重裝**（`bootstrap-volume.sh` 的 `wake.sh` 本來就有這行，這次圖快手動下指令漏了這步，導致 `inference.py` 的 mux 步驟先失敗一次，事後 `apt-get update && apt-get install -y ffmpeg` 補上、直接對 `.tmp.mp4` 手動 `ffmpeg -map` 補混音救回，沒有重跑昂貴的 DIT 推論）。**下次直接跑 `wake.sh` 或先確認 `which ffmpeg` 再進 inference，別漏。**
- **cudnn8-pkgs 路徑陷阱（本輪新發現）**：`bootstrap.sh` 裝 cuDNN8 是 `pip install --target /opt/cudnn8-pkgs`——但 `/opt` 在**容器磁碟**、不在置物櫃，新卡上 `/opt/cudnn8-pkgs` 根本不存在！這次能跑是因為某輪手動把它搬到了 `/workspace/cudnn8-pkgs`（置物櫃、跨卡常駐）。**LD_LIBRARY_PATH 要指 `/workspace/cudnn8-pkgs/nvidia/cudnn/lib`，不是 `/opt/...`**——先跑 `find /workspace -iname 'libcudnn.so*'` 確認實際路徑再下 inference 指令，別假設在 /opt。
- **來源照片先裁好可直接沿用**：`avatar-06` 已有現成 1080×1080 臉+肩置中裁圖（`/workspace/realmale-square.jpg`，MD5 與本機 scratchpad 版一致），跨 pod 常駐、不必重裁。
- **Ditto 輸出解析度＝來源圖解析度**：這次來源圖是 1080×1080，Ditto 直接吐 1080×1080（非固定 512×512）——要對齊既有規格得**額外一道 `ffmpeg -vf scale=512:512 -c:v libx264 -c:a aac` 降尺寸**，會多花幾秒 but 不必重跑 GPU 推論。

## 排雷追加（7/10 這輪新發現：裁切放寬 + 待機動態做法）

- **「頭到胸」裁切公式**：來源 9:16 直式圖（1080×1920）→ 用 `box = (0, 260, 1080, 1340)`（即左上 (0,260)、1080×1080 正方形）一刀裁到底，頭頂留約 20-40px 空、下緣落在鎖骨下方露出肩膀+胸口/衣領——**同一 box 套 avatar-05、avatar-06 兩張源圖框線就對齊**（兩張源圖構圖比例本就相近）。之前demo裁太緊只剩臉，這次放寬後三支並排一致。
- **「打招呼→待機」單支動態怎麼做**：不用另外找待機演算法——**餵一段「短招呼語音（1-2秒）+ 尾端補靜音（7-9秒）」的單一 wav** 給 `inference.py` 正常跑，Ditto 會在有聲段自然對嘴開口、靜音段自動回到嘴閉合+微笑+自然眨眼/頭部微擺（emo/eye_f0等內建微動態沒被音訊蓋掉），抽幀驗證效果正是「有講話→回到活著的待機」，不需要額外工具或訓練。純靜音（不含招呼語音）版尚未實測，但這個「短招呼+靜音尾」組合已驗證可行、成本低（多花幾秒生成時間，不必重跑模型）。
- **本輪零意外**：置物櫃 SOP（清stale pyxbld、裝ffmpeg、cudnn8路徑）三項排雷清單全部沿用無踩雷，流程已穩定。

## 排雷追加（7/10 第二輪：改直式露胸 + 冷啟先做的事）

- **直式裁切公式（本輪定案）**：`box = (0, 140, 1080, 1580)` 套 1080×1920 源圖 → 裁出 1080×1440（3:4）→ Ditto 原生輸出同尺寸 → `ffmpeg -vf scale=810:1080` 降到最終規格。這個公式比上輪方形 box 往下多帶 240px、頭頂留空稍多，兩張源圖（avatar-05/06）構圖一致故同 box 直接對齊，不用個別微調。
- **正式跑 GPU 前，先在本機用 PIL 裁幾個候選 box 存圖、用 Read 工具肉眼比對再定案**——比在 4090 上試錯划算太多（裁切/構圖決策不吃 GPU、純 CPU 幾秒完成，省下的是整輪 inference 的分鐘數，這次靠本機比對一次就抓對 box，沒有重跑）。
- **TTS 也是先在本機做**：`google-genai` 套件本機已裝、`engine/.env.local` 有 `GEMINI_API_KEY` 可直接用（`engine/env_loader.load_engine_env()` 讀鑰匙），本機生完 wav 再一次 scp 上機，不佔用 GPU 計費時間等 TTS。
- **本輪零意外**：置物櫃 SOP（清 stale pyxbld、裝 ffmpeg、cudnn8 路徑）三項排雷清單全部沿用無踩雷；舊 volume 上遺留一批同名相關的 `*-headchest.*` 檔案（另一輪嘗試留下、經查仍是 1080×1080 方形，非本輪要的直式），本輪改用新檔名（`*-portrait-src.jpg`／`*-line-new.wav`）上傳，避免跟舊檔混淆，未刪舊檔（不影響本輪）。

## 排雷追加（7/10 第三輪：FlashHead PoC 全新開卡踩雷清單）

- **選對官方新映像可省掉整個 torch/ffmpeg/torchvision 安裝步驟**：`runpod/pytorch:1.0.7-rc.138-cu1281-torch271-ubuntu2204`（Docker Hub 查得，2026-07-08 剛更新）已預裝 torch 2.7.1+cu128、torchvision 0.22.1+cu128、ffmpeg，跟 FlashHead 官方要求版本一致，直接省下最耗時的兩步——**開新卡前先查 `hub.docker.com/v2/repositories/runpod/pytorch/tags` 找精確匹配版本號的映像，別無腦沿用舊映像再手動裝。**
- **requirements.txt 別無腦整包裝**：SoulX-FlashHead 的 `requirements.txt` 有 3 個地雷，都要修過才裝得起來——① `mediapipe==0.10.9` 在 py3.12 無 wheel（要放寬到 `>=0.10.13`）② `nvidia-nccl-cu12==2.27.3` 跟 `torch==2.7.1` 自帶依賴的 `2.26.2` 衝突（直接刪掉這行讓 torch 自己帶）③ 系統自帶的 `blinker`（distutils 裝的）擋 uninstall（`pip install --ignore-installed blinker -r requirements.txt` 繞過）。
- **⚠ pip 會偷偷把預裝的 cu128 torch 換成 PyPI 預設 cu126 版**：即使版本號都寫 `torch==2.7.1`（沒鎖 cu128 tag），resolver 解 `xformers==0.0.31` 依賴時還是從 PyPI 抓了純 `torch-2.7.1`（cu126 flavor）蓋掉映像自帶的 `2.7.1+cu128`，而 `torchvision` 沒被動（維持 +cu128）。**這次實測兩個 cu 版本混用（torch cu126 + torchvision cu128）沒有炸、GPU tensor 運算/`torchvision.ops` 都正常**，但這是僥倖不是保證——**若要根治，裝完 requirements.txt 後應再 `pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128 --no-deps` 強制換回**（這次為省時間沒補，PoC 結果不受影響但正式上線前要修）。
- **flash-attn 直接抓 GitHub release wheel、別自己編**：`flash_attn-2.8.0.post2+cu12torch2.7cxx11abiTRUE-cp312-cp312-linux_x86_64.whl`（用 `torch.compiled_with_cxx11_abi()` 先確認 True/False 再選對應 wheel）下載 12 秒、裝立即成功，完全不用碰 nvcc/編譯——**下載下來的檔名若被存成別的名字（如 `flash_attn.whl`）要先改回原始完整檔名（含 wheel tag）`pip` 才認得，不然報「Invalid wheel filename」。**
- **官方 `--use_face_crop True` 這次踩雷失效**：內建 `flash_head/utils/facecrop.py` 呼叫 `mediapipe.solutions`，但目前 PyPI 最新 mediapipe（0.10.35，requirements 放寬版本撞到的）已把舊版 `solutions` API 拿掉，跑起來直接 `Error processing xxx.png: module 'mediapipe' has no attribute 'solutions'`（被程式內建 try/except 吃掉、靜默退回用整張未裁圖硬塞 `resize_and_centercrop`，構圖可能跑掉但不會報錯崩潰）。**繞過法：直接沿用本案已驗證過的「頭到胸」1080×1080 裁切公式（`box=(0,260,1080,1340)`）在本機用 PIL 先裁好方圖再上傳，`--use_face_crop` 留 False**，構圖跟 Ditto demo 一樣穩、不必修 mediapipe。
- **一次 process 裝一次 pipeline、跑多支省大量時間**：`generate_video.py` 是 one-shot CLI，每次重跑都要重付一次 torch.compile 冷啟成本（本輪首見 170 秒！第二個獨立 process 因磁碟編譯快取殘留降到 40 秒）——**若要測多組圖/音檔，自己寫一支 batch script 把 `get_pipeline()` 只呼叫一次、迴圈呼叫 `get_base_data()`+串流生成迴圈**，同一 process 內切換角色圖或音檔完全不用重付編譯稅（本輪第 2-4 支冷啟直接降到跟穩態一樣 ~0.25秒/塊），4 支測試省下來的時間換算約 8-9 分鐘 GPU 時間（~US\$0.10）。
- **VRAM 峰值很低**：單串流峰值僅 ~6.3GB（24GB 卡的 26%），跟官方「單卡 3 並發」宣稱（3×6.3≈18.9GB＜24GB）數字對得上。


## 排雷追加（7/10 第四輪：FlashHead PoC 第二輪開卡踩雷——RunPod 容量緊繃 + 壞機器偵測）

- **4090 Secure/Community 一度連續 500 錯誤**：`create pod: This machine does not have the resources to deploy your pod`——這不是我方 spec 問題（連用第一輪已驗證成功的舊 spec 重試也一樣噴），是 RunPod 當下 4090 庫存緊繃，**單純重試（間隔 8-12 秒）5 次內通常會成功**，不用切 GPU 型號。
- **開卡成功但「machine 欄位空、拿不到 IP」＝壞卡徵兆**：這次連兩次分到同一台實體機（`machineId=2pq5f32wv38g`）都卡在 `desiredStatus=RUNNING` 但 `machine:{}`、`publicIp` 一直是空字串，分別等了 ~100s 和 ~210s 都沒解——**這不是「還在開機」而是那台實體機當下有問題**（可能是宿主機資源分配失敗但 API 仍回報 RUNNING）。**判斷基準：正常開機通常 15-80 秒內 `machine` 欄位就會填好 dataCenterId 等資訊；超過 2 分鐘 `machine` 仍是空的，直接判定壞卡、terminate 重開，不要繼續等。**
- **重開會重新排機、不會卡在同一台壞機器上**：兩次壞卡都是 `2pq5f32wv38g`，但第三次重開後配到了完全不同的機器（`bm2w3s5hasac`，換了機房 EU-RO-1）就正常，**RunPod 的排機是每次 create 都重新分配，不用自己選黑名單機制也會自然換機**，但寫個「拿到 machineId 後檢查是否等於已知壞ID、是的話立刻 terminate 重開」的迴圈可以更快切乾淨。
- **開卡失敗/卡住不算成功也會計費**：兩次壞卡分別燒了 ~US\$0.06／US\$0.04（RUNNING 狀態即計費，即使拿不到 IP 沒做任何工作）——**看門狗鐵律再次驗證重要：發現異常立刻 terminate，別猶豫等待，浪費的是純損耗的錢。**

## 排雷追加（7/10 第五輪：動物臉 PoC——自訂 Docker 映像當 pod 映像的做法）

- **任意 Docker Hub 映像都能直接當 RunPod pod 映像**：REST API `POST /pods` 支援 `dockerEntrypoint`（陣列）＋ `dockerStartCmd`（陣列）覆蓋 ENTRYPOINT/CMD——這輪用 `["/bin/bash","-lc"]` ＋「寫 authorized_keys → 裝 openssh-server → `/usr/sbin/sshd -D`」一條命令，讓沒有 RunPod handler 的第三方映像（`shaoguo/faster_liveportrait:v3`，13.8GB）也能 SSH 進去操作。13.8GB 映像從 create 到 SSH ready 只花 **193 秒**（RunPod 拉像速度夠快，別因映像大就放棄這條路）。
- **省下的是整條編譯地獄**：FasterLivePortrait 的 TRT 路徑要 TensorRT 8.x（≥10 不相容）＋ grid_sample3d TRT plugin＋XPose CUDA op；onnxruntime-gpu 路徑更要從 source 編 ort（liqun 分支）。官方映像三樣全預裝（TRT 8.6.1.6／plugin 在 HF 權重包裡有預編 .so／MSDA op 已裝進 site-packages），現場只需 git clone＋下權重＋轉 9 顆 TRT 引擎（4090 上共約 13 分鐘，warping_spade 最久 ~5 分鐘）。
- **非 login shell 沒有 PATH/LD_LIBRARY_PATH**：這映像的環境變數都在 `/root/.bashrc`，ssh 非互動指令要自帶 `export PATH=/root/miniconda3/bin:/usr/local/cuda/bin:$PATH; export LD_LIBRARY_PATH=/opt/TensorRT-8.6.1.6/lib:/usr/local/cuda/lib64:$LD_LIBRARY_PATH`，不然 python/tensorrt/torch 全找不到。
- **驗 torch CUDA extension 是否已裝，要先 `import torch` 再 import op**：直接 `python -c "import MultiScaleDeformableAttention"` 會因 libc10.so 找不到而誤判沒裝（op 的 .so 連著 torch 的 lib、torch 先載才找得到）——這輪差點因此白編一次 XPose op（而且 cu117 的 nvcc 不認 sm_89，用 `TORCH_CUDA_ARCH_LIST=8.6` 才編得過；所幸映像本來就裝好、免編）。
- **映像裡沒有 bc**：算浮點用 `python -c` 別用 `bc`（計時/抽幀腳本這輪踩到，量測值改從 run log 的 `inference median/mean time` 行拿，更準）。
- **動物模式駕駛端吃的是「人臉」影片**：source 用 XPose（動物臉 9 點），driving 用 retinaface+landmark（人臉）——正好可以直接餵我們 Ditto 產的真人說話影片；跑一次還會存 `drive.mp4.pkl` 動作檔，之後同一段駕駛動作可重用（`run_with_pkl`）、不必每次重跑人臉偵測。

## FlashHead Modal 試作版部署紀錄（7/10 · 跟 RunPod PoC 分開記帳）

- 服務網址：https://edwardt0303--munea-flashhead-avatar-dev-flashhead-web.modal.run
- App：munea-flashhead-avatar-dev（跟現役 munea-nening-avatar[-dev] 完全分開、不同置物櫃）
- 今日 Modal 費用（`modal billing report --for today`）：flashhead-dev 合計 **US$0.917**（含一次踩雷：
  torch.compile 在 L4 冷編譯 1010 秒且 Modal GPU 快照存不進去、自動重試燒了約 US$0.70，
  改 eager 模式後修好，之後測試僅約 US$0.22）——預算 US$1-3、在範圍內。

## FlashHead 真機測試前哨（7/10 二輪 · 卡西法接力）

- 沿用前手已部署的 Modal L4 eager 服務（`munea-flashhead-avatar-dev`），加：
  1. `/switch` 端點（換角色不必重開 WebRTC，實測 ~40-50ms／次，穩定）
  2. 修正 client 端只 offer video transceiver 的老問題——`web/flashhead-live-test.html` 改成同時 offer audio+video 兩個 recvonly transceiver，answer SDP 真的兩條都給（用 aiortc 當假瀏覽器實測驗證：video 512x512 持續出格、audio track 真的帶得動語音能量，RMS 峰值 11464、非全靜音）
  3. 語音橋（`munea-voice-staging`）client relay：收到的聲音 bytes 不在頁面本地播放，改轉送進 FlashHead `/audio`，讓「同一份聲音」跟它生出的嘴型影格走同一條 PeerConnection 送出（解「聲音先出、臉慢 3-5 秒」的根——舊架構是猜 900ms 固定延遲硬對，這版是同源生成、理論上不再有系統性落後）
  4. 回合邊界：`turn_complete`／`interrupted` 都會送 `reset`（清 feeder 積壓＋時間戳重錨）
  5. 開場遮蓋：a05 用現成 `realfemale-hero-idle.mp4` 打招呼→待機片蓋首塊延遲；a06 目前沒有對應片，退回靜態圖
- 新增獨立 Modal 靜態小站 `munea-flashhead-test-page`（不碰 Cloud Run、不碰任何現役服務）端測試頁：
  https://edwardt0303--munea-flashhead-test-page-web.modal.run
- 端到端真實測試（文字觸發語音橋，非假音檔）：3 輪對話全程 pass，round_latencies 沒有隨輪數變慢的跡象；
  但發現一個真邊界案例——LLM 查詢工具（Google 搜尋）在句子講到一半觸發時，中間的停頓會被判定成新一輪，
  導致該輪 sink/audio_out 被清一次（可能有一次輕微卡頓），寫進「上線前還缺」清單。
- 費用（Modal billing report，本輪估算）：約 US$0.4-0.5（含兩次 L4 冷啟、多輪真實生成測試、L40S 可用性快篩一次），
  遠低於 US$5 預算天花板；L40S 仍因帳號未設付款方式被 Modal 擋（快篩秒回，零 GPU 成本）。

