// Munea B2B 真通話體驗 · 鑰匙發放接口（Vercel Serverless）
// 目的：avatar/voice 服務的通行鑰匙不寫死在對外網頁原始碼裡；
//       瀏覽器要先過密語（munea 666）、才在通話當下拿到鑰匙。
// 註：鑰匙抵達瀏覽器後對當事人仍可見（無伺服器中繼的物理極限）——
//     防護靠：密語門 + 3 分鐘體驗上限（call.html）+ 鑰匙可隨時輪換 + 測試機隔離。
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', 'https://munea-b2b.vercel.app');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'method' });

  const { key } = req.body || {};
  const pass = String(key || '').replace(/\s+/g, '').toLowerCase();
  if (pass !== 'munea666') return res.status(401).json({ error: 'key' });

  // 環境變數優先（正式營運請設 DEMO_AVATAR_KEY 並輪換下方預設值）
  const avatarKey = process.env.DEMO_AVATAR_KEY || 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5';
  return res.status(200).json({
    avatarKey,
    avatarHttp: process.env.DEMO_AVATAR_HTTP || 'https://edwardt0303--munea-flashhead-avatar-dev-flashhead-web.modal.run',
    voiceWs: process.env.DEMO_VOICE_WS || 'wss://munea-voice-staging-491603544409.asia-east1.run.app/',
    capSeconds: Number(process.env.DEMO_CAP_SECONDS || 180)
  });
}
