const DEFAULT_AVATAR_HTTP = 'https://u4w3w47kag90bf-8188.proxy.runpod.net';
const DEFAULT_VOICE_WS = 'wss://munea-voice-staging-491603544409.asia-east1.run.app/';

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

  const avatarHttp = String(process.env.DEMO_AVATAR_HTTP || DEFAULT_AVATAR_HTTP)
    .trim()
    .replace(/\/$/, '');

  try {
    const sessionResponse = await fetch(`${avatarHttp}/demo/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pass }),
      signal: AbortSignal.timeout(12_000),
    });
    const session = await sessionResponse.json().catch(() => ({}));
    if (!sessionResponse.ok || !session.token) {
      return res.status(503).json({ error: 'avatar_unavailable' });
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
    return res.status(503).json({ error: 'avatar_unavailable' });
  }
}
