// Munea B2B 預約／試辦名單 · 直送接口（Vercel Serverless）
// 設了 RESEND_API_KEY 就把名單直接寄到 LEAD_TO 信箱（訪客不必有信箱 App）；
// 沒設就回 {ok:false, fallback:'mailto'}，前端自動退回「開啟寄信」舊行為，不會壞。
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', 'https://munea-b2b.vercel.app');
  res.setHeader('Access-Control-Allow-Headers', 'content-type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ ok: false, error: 'method' });

  const b = req.body || {};
  const name = String(b.name || '').trim().slice(0, 80);
  const org = String(b.org || '').trim().slice(0, 120);
  const email = String(b.email || '').trim().slice(0, 120);
  if (!name || !org || !email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ ok: false, error: 'invalid' });
  }
  const role = String(b.role || '').trim().slice(0, 40);
  const phone = String(b.phone || '').trim().slice(0, 40);
  const msg = String(b.msg || '').trim().slice(0, 1000);
  const plans = Array.isArray(b.plans) ? b.plans.map(p => String(p).slice(0, 20)).slice(0, 8) : [];
  const mode = b.mode === 'trial' ? '申請試辦' : '預約展示';

  const key = process.env.RESEND_API_KEY;
  const to = process.env.LEAD_TO || 'edwardt0303@gmail.com';
  // 沒設寄信鑰匙 → 告訴前端退回 mailto（開啟訪客信箱），維持現行可用
  if (!key) return res.status(200).json({ ok: false, fallback: 'mailto' });

  const subject = `【${mode}】${org}－Munea B2B 合作`;
  const lines = [
    `姓名：${name}`, `單位名稱：${org}`, `身分：${role || '未填'}`,
    `電話：${phone || '未填'}`, `Email：${email}`,
    `想了解的方案：${plans.length ? plans.join('、') : '未勾選'}`,
    `留言：${msg || '無'}`, '', `（由 Munea B2B 合作頁「${mode}」表單直送）`
  ];
  const html = lines.map(l => l ? `<p style="margin:2px 0">${l.replace(/</g, '&lt;')}</p>` : '<br>').join('');

  try {
    const r = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${key}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from: process.env.LEAD_FROM || 'Munea B2B <onboarding@resend.dev>',
        to: [to], reply_to: email, subject, html
      })
    });
    if (!r.ok) {
      const t = await r.text();
      console.error('resend error', r.status, t.slice(0, 300));
      return res.status(200).json({ ok: false, fallback: 'mailto' });
    }
    return res.status(200).json({ ok: true, delivered: 'email' });
  } catch (e) {
    console.error(e);
    return res.status(200).json({ ok: false, fallback: 'mailto' });
  }
}
