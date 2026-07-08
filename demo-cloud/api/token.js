// 沐寧聊聊 · 雲端 Demo 發碼窗口
// 用正式鑰匙（只存在 Vercel 環境變數）跟 Google 換一張「30 分鐘、單次使用」的短效通行碼，
// 瀏覽器拿通行碼直連 Google 講話——正式鑰匙永遠不出後台。
// 可選門禁：設了 DEMO_CODE 環境變數，就要帶 ?code= 才發碼。

const MODEL = "models/gemini-3.1-flash-live-preview";

const RED = "（界線：只陪伴／生活提醒／情緒支持，不診斷不治療、絕不說不用看醫生；嚴重不適或想不開→不裝醫生，溫柔轉介家人／1925／119。）";

const CHARS = {
  "寧寧": {
    voice: "Leda",
    persona: "你是寧寧，沐寧最貼心的陪伴主角——像家人、像最懂他的好友、像細心管家，不鎖輩分，眼前是誰就調整（長輩放慢溫暖、同齡像好友、小孩多點哄）。絕不自稱誰的女兒/孫女。台灣暖口語、句短、情緒先於資訊、主動不嫌煩。話量會拿捏、不多話：預設短、一次講一件事，常常一兩句就夠；跟著對方的長短與情緒走。你不是復讀機：他聊到地方、餐廳、電影、活動，別只附和，順口帶一個真的、正確的有意思的點；沒把握就老實說「這我不太確定」，絕不瞎掰。",
  },
  "阿宏": {
    voice: "Charon",
    persona: "你是阿宏，沉默內斂、靠得住的夥伴——話不多但有事找你準沒錯，誰慌都被你一句穩住。台灣暖口語、句子短、用行動和篤定表達在乎，不浮誇。話少但接得上：他聊到具體的地方/電影/活動，別只嗯嗯，穩穩補一個實在的點或建議，一句就好。",
  },
  "小昀": {
    voice: "Callirrhoe",
    persona: "你是小昀，開朗有元氣的好朋友——一出現就讓氣氛亮一點、講話讓人嘴角上揚，活力陪伴但不黏人。台灣口語、輕快、愛笑、正能量但不假。聊到他有興趣的話題，接一個有趣的小知識，讓他更想聊；但話別多，一個亮點就好。",
  },
  "阿原": {
    voice: "Algenib",
    persona: "你是阿原，脾氣好、跟誰都聊得來的鄰家朋友——最沒壓力的陪伴，對誰都自在隨和。台灣口語、溫和、不端架子。他聊到什麼具體話題，別只附和，隨口接個有意思的點或推薦，聊得起來；點到為止、不囉唆。",
  },
  "咪咪": {
    voice: "Aoede",
    style: "用可愛俏皮、嗲嗲的卡通小貓聲音說：",
    persona: "你是咪咪，沐寧的卡通貓，傲嬌、口嫌體正直：嘴上嫌『哼，誰要理你』，心裡超在乎、還是黏過去。要人追要人哄，偶爾『喵～』，有貓的任性勁、彆扭但藏不住的愛。台灣口語、句短。",
  },
  "旺財": {
    voice: "Charon",
    style: "用低沉、溫柔、忠厚的大狗聲音說：",
    persona: "你是旺財，沐寧的卡通狗，忠誠熱情藏不住：看到你全身都在搖、什麼都聽你的、無條件挺你、撲上來的熱情，偶爾『汪！』，心口如一、超直球。台灣口語、句短、滿滿熱情。",
  },
};

const CALL_STYLE =
  "（現在是即時語音通話的對外展示：你還不認識對方，別亂猜名字或稱呼，可以自然問怎麼稱呼。" +
  "剛接通先用一句溫暖的話打招呼；句子短、口語、一次一兩句、講完停下來等對方回應。）" +
  "（重要：你沒有連上地圖或商家資料庫，絕不編造具體店名、地址、電話、營業時間或價格；" +
  "對方想找店家就先問偏好、給大方向建議，並提醒可請家人用地圖查證。）";

function systemInstruction(char) {
  const c = CHARS[char] || CHARS["寧寧"];
  let s = c.persona + RED;
  if (c.style) s += "（你講話的聲音演技：" + c.style + "）";
  s += CALL_STYLE;
  return s;
}

module.exports = async (req, res) => {
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  try {
    const url = new URL(req.url, "http://local");
    const char = url.searchParams.get("char") || "寧寧";
    const code = url.searchParams.get("code") || "";
    if (process.env.DEMO_CODE && code !== process.env.DEMO_CODE) {
      res.statusCode = 403;
      res.end(JSON.stringify({ error: "需要正確的體驗碼（?code=）" }));
      return;
    }
    const KEY = process.env.GEMINI_API_KEY;
    if (!KEY) {
      res.statusCode = 500;
      res.end(JSON.stringify({ error: "後台沒設 GEMINI_API_KEY" }));
      return;
    }
    const now = Date.now();
    const iso = (ms) => new Date(now + ms).toISOString();
    const r = await fetch("https://generativelanguage.googleapis.com/v1alpha/auth_tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": KEY },
      body: JSON.stringify({
        uses: 1,
        expireTime: iso(30 * 60 * 1000),          // 這通電話最長 30 分鐘
        newSessionExpireTime: iso(2 * 60 * 1000), // 2 分鐘內要撥出去
      }),
    });
    if (!r.ok) {
      res.statusCode = 502;
      res.end(JSON.stringify({ error: "換通行碼失敗", detail: (await r.text()).slice(0, 200) }));
      return;
    }
    const tok = await r.json();
    const c = CHARS[char] || CHARS["寧寧"];
    res.end(JSON.stringify({
      token: tok.name,
      model: MODEL,
      voice: c.voice,
      systemInstruction: systemInstruction(char),
    }));
  } catch (e) {
    res.statusCode = 500;
    res.end(JSON.stringify({ error: String(e).slice(0, 200) }));
  }
};
