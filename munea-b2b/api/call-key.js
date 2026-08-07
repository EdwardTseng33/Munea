// B2B Demo 鑰匙發放 + 展示機自動開關（auto-wake v1 · 2026-07-23）
//
// 隔離鐵律（Edward 2026-07-23）：Demo 與 App 正式聊聊互不影響。
// 本檔對 RunPod 只碰「名字完全等於 DEMO_POD_NAME」的機器；
// App 正式線 / 備援線（munea-vocaframe-*）永遠不在射程內。
// 機器規格與 deploy/runpod-demo/democtl.py 保持同一份內容（改一邊要同步另一邊）。
//
// 2026-08-10 三修（Edward 追究「為什麼沒有人去關」）：
//   ① 機器名不再帶顯卡型號。舊名 munea-flashhead-demo-768-r6000ada 寫死了
//      RTX 6000 Ada，但規格本來就允許 4090——實際開到哪張卡看主控台為準，
//      名字帶型號只會騙人。更糟的是 democtl.py 用的是不帶型號的名字，兩邊
//      **看不到彼此的機器**：已經有一台在跑，官網還會再開第二台，誰也收不掉誰。
//   ② TTL 從 3 小時砍到 30 分鐘。展示通話上限 180 秒，3 小時等於一次展示要付
//      2.2 美金；而且下面那個 reap 只有「下一個客人來訪」才會跑——沒人再來，
//      機器就永遠開著（$0.74/hr ≈ 一個月 NT$17,000）。
//   ③ 真正的收機器改由 munea-runpod-controller 每 15 秒巡一次（見
//      deploy/runpod-avatar/runpod_backup.py 的 demo reaper）。這裡這段留著
//      當第二層保險——兩邊用同一個 TTL，誰先看到誰收。
const DEMO_POD_NAME = 'munea-flashhead-demo-768';
const DEMO_VOLUME_ID = '7d3vqi99dm';
const DEMO_IMAGE = 'runpod/pytorch:1.0.7-rc.138-cu1281-torch271-ubuntu2204';
const RUNPOD_BASE = 'https://rest.runpod.io/v1';
const DEFAULT_AVATAR_HTTP = 'https://1g3fl1fsjzfzul-8188.proxy.runpod.net';
const DEFAULT_VOICE_WS = 'wss://munea-voice-staging-491603544409.asia-east1.run.app/';
const WAKE_ETA_SECONDS = 360; // 全冷實測 6-9 分鐘；密語門每 20 秒自動重試會自己接上
const DEFAULT_TTL_SECONDS = 1800; // 30 分鐘。跟 MUNEA_DEMO_POD_TTL_SECONDS 保持同一個數字

async function runpod(key, method, path, body) {
  const response = await fetch(RUNPOD_BASE + path, {
    method,
    headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20_000),
  });
  const raw = await response.text();
  if (!response.ok) {
    throw new Error(`runpod ${method} ${path} HTTP ${response.status}: ${raw.slice(0, 200)}`);
  }
  return raw ? JSON.parse(raw) : {};
}

const isDemoPod = pod => Boolean(pod) && pod.name === DEMO_POD_NAME;
const proxyUrl = id => `https://${id}-8188.proxy.runpod.net`;

async function listDemoPods(key) {
  const pods = await runpod(key, 'GET', '/pods');
  return (Array.isArray(pods) ? pods : []).filter(isDemoPod);
}

// RunPod 的時間長相是 "2026-07-23 09:01:55.866 +0000 UTC"，先整型再解析。
function podAgeSeconds(pod) {
  const stamp = String(pod && pod.lastStartedAt || '')
    .replace(' +0000 UTC', 'Z')
    .replace(' ', 'T');
  const started = Date.parse(stamp);
  if (!Number.isFinite(started)) return null;
  return Math.max(0, (Date.now() - started) / 1000);
}

async function wakeDemoPod(key) {
  const spec = {
    name: DEMO_POD_NAME,
    computeType: 'GPU',
    gpuTypeIds: ['NVIDIA RTX 6000 Ada Generation', 'NVIDIA GeForce RTX 4090'],
    gpuTypePriority: 'availability',
    gpuCount: 1,
    cloudType: 'SECURE',
    interruptible: false,
    locked: false,
    supportPublicIp: true,
    containerDiskInGb: 60,
    networkVolumeId: DEMO_VOLUME_ID,
    volumeMountPath: '/workspace',
    ports: ['8188/http', '8888/http', '22/tcp'],
    allowedCudaVersions: ['12.8'],
    dataCenterIds: ['US-IL-1'],
    dataCenterPriority: 'custom',
    imageName: DEMO_IMAGE,
    dockerStartCmd: [
      'bash',
      '-lc',
      'ln -sf /workspace/munea-demo/current/post_start.sh /post_start.sh; exec /start.sh',
    ],
  };
  const made = await runpod(key, 'POST', '/pods', spec);
  // 撞車保險：同一秒兩位訪客可能各開一台。留 id 排序最小那台；
  // 只刪「自己剛開出來」的那台，絕不動別人 / 別條線的機器。
  try {
    const pods = await listDemoPods(key);
    if (pods.length > 1 && made && made.id) {
      const keep = pods.map(pod => pod.id).sort()[0];
      if (made.id !== keep) await runpod(key, 'DELETE', '/pods/' + made.id);
    }
  } catch (error) {
    console.error('demo wake dedupe skipped', error && error.message);
  }
  return made;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', 'https://munea-b2b.vercel.app');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'method' });

  const { key } = req.body || {};
  const pass = String(key || '').replace(/\s+/g, '').toLowerCase();
  const expectedPass = String(process.env.DEMO_ACCESS_PASSWORD || 'munea666')
    .replace(/\s+/g, '')
    .toLowerCase();
  if (!expectedPass || pass !== expectedPass) {
    return res.status(401).json({ error: 'key' });
  }

  let avatarHttp = String(process.env.DEMO_AVATAR_HTTP || DEFAULT_AVATAR_HTTP)
    .trim()
    .replace(/\/$/, '');

  // 展示機自動開關：密語過了才會走到這裡（陌生人碰不到開機鈕）。
  // 任何一步失敗都退回上面的固定門牌，行為跟 auto-wake 之前一模一樣。
  const runpodKey = String(process.env.RUNPOD_API_KEY || '').trim();
  if (runpodKey) {
    try {
      let pods = await listDemoPods(runpodKey);

      // 太久沒換班的展示機整台刪掉換新（RunPod 暫停=死路、只能刪了重開）。
      // 展示通話上限 180 秒，TTL 到點頂多切斷一通收尾中的體驗。
      // ⚠ 這段只有「有客人來訪」才會跑到——沒人再來就永遠不會收。真正的定時收機器
      //    在 munea-runpod-controller（每 15 秒一輪），這裡是第二層保險。
      const ttlSeconds = Number(process.env.DEMO_POD_TTL_SECONDS || DEFAULT_TTL_SECONDS);
      if (pods.length) {
        const age = podAgeSeconds(pods[0]);
        if (age != null && age > ttlSeconds) {
          for (const pod of pods) await runpod(runpodKey, 'DELETE', '/pods/' + pod.id);
          pods = [];
        }
      }

      if (!pods.length) {
        try {
          await wakeDemoPod(runpodKey);
        } catch (error) {
          // 常見=機房缺卡。密語門每 20 秒重試、每次重試都會再搶一次。
          console.error('demo wake attempt failed', error && error.message);
        }
        return res.status(503).json({ error: 'avatar_waking', etaSeconds: WAKE_ETA_SECONDS });
      }

      avatarHttp = proxyUrl(pods[0].id);
    } catch (error) {
      console.error('demo autowake lookup failed', error && error.message);
    }
  }

  try {
    const sessionResponse = await fetch(`${avatarHttp}/demo/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pass }),
      signal: AbortSignal.timeout(12_000),
    });
    const session = await sessionResponse.json().catch(() => ({}));
    if (!sessionResponse.ok || !session.token) {
      // 機器在、服務還在暖機（開機後模型要載幾分鐘）→ 回「喚醒中」讓門口繼續等。
      return res.status(503).json({ error: 'avatar_waking', etaSeconds: WAKE_ETA_SECONDS });
    }

    // The current staging voice bridge still uses its existing browser-demo key.
    // Avatar access is no longer tied to that long-lived key.
    const voiceKey = String(
      process.env.DEMO_VOICE_KEY || 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5'
    ).trim();
    if (!voiceKey) return res.status(503).json({ error: 'voice_unavailable' });

    return res.status(200).json({
      avatarToken: session.token,
      avatarTokenExpiresIn: Number(session.expiresIn || 300),
      voiceKey,
      avatarHttp,
      voiceWs: process.env.DEMO_VOICE_WS || DEFAULT_VOICE_WS,
      capSeconds: Number(process.env.DEMO_CAP_SECONDS || 180),
    });
  } catch (error) {
    console.error('demo bootstrap failed', error && error.message);
    return res.status(503).json({ error: 'avatar_waking', etaSeconds: WAKE_ETA_SECONDS });
  }
}
