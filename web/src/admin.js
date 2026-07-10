(function () {
  "use strict";

  // ══════════ 選單結構（設計稿：5 組 11 頁 + 設定） ══════════
  const NAV = [
    { group: "營運總覽", items: [
      { id: "overview", ico: "◈", label: "總覽儀表板" },
      { id: "growth", ico: "📈", label: "產品成長指標" },
    ]},
    { group: "用戶與守護", items: [
      { id: "users", ico: "👥", label: "用戶管理" },
      { id: "safety", ico: "🛡", label: "安全守護警示", badge: "safety" },
      { id: "reminders", ico: "💊", label: "用藥·回診提醒" },
      { id: "mood", ico: "💗", label: "心情與健康" },
    ]},
    { group: "營收與用量", items: [
      { id: "subscription", ico: "💳", label: "訂閱與點數" },
      { id: "usage", ico: "🎙", label: "AI 陪伴用量" },
    ]},
    { group: "內容與服務", items: [
      { id: "characters", ico: "🎭", label: "AI 角色與內容" },
      { id: "support", ico: "📮", label: "客服與回饋工單", badge: "support" },
    ]},
    { group: "系統維運", items: [
      { id: "system", ico: "🖥", label: "系統狀態告警", badge: "system" },
    ]},
    { group: "設定", items: [
      { id: "settings", ico: "⚙", label: "連線設定" },
    ]},
  ];
  const CRUMB = {};
  const TITLE = {};
  NAV.forEach((g) => g.items.forEach((it) => { CRUMB[it.id] = g.group; TITLE[it.id] = it.label; }));

  // ══════════ 線條圖標（stroke SVG，對齊 App 設計語言） ══════════
  const ICON_PATHS = {
    overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    growth: '<path d="M3 17l6-6 4 4 8-8"/><path d="M17 7h4v4"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M17 3.13a4 4 0 0 1 0 7.75"/>',
    safety: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    reminders: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    mood: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 1 0-7.8 7.8L12 21.2l8.8-8.8a5.5 5.5 0 0 0 0-7.8z"/>',
    subscription: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/>',
    usage: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><path d="M12 17v4"/>',
    characters: '<path d="M12 3l1.6 4.8L18 9l-4.4 1.2L12 15l-1.6-4.8L6 9l4.4-1.2z"/><path d="M18 15l.7 2.1L21 18l-2.3.9L18 21l-.7-2.1L15 18l2.3-.9z"/>',
    support: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    system: '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  };
  function icon(id, cls){ return `<svg class="${cls||"nav-ico"}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[id]||""}</svg>`; }

  // ══════════ 狀態 ══════════
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
  const ADMIN_TOKEN_KEY = "munea.admin.token";
  const ACK_KEY = "munea.admin.ack";
  const ASSUME_KEY = "munea.admin.assumptions";
  const DEFAULT_LOCAL_API = "http://127.0.0.1:8200";
  const state = { data: null, errors: {}, connected: false, page: "overview", tabs: {} };

  // codex 後端接口清單（連線時一次抓）
  const EP_LIST = {
    northStar: ["/admin/north-star", { days: 30 }],
    usage: ["/admin/usage", { days: 90 }],
    accounts: ["/admin/accounts", { limit: 25 }],
    credits: ["/admin/credits", { limit: 12 }],
    subscriptionMetrics: ["/admin/subscription-metrics", { days: 30 }],
    feedback: ["/admin/feedback", { limit: 12 }],
    safety: ["/admin/safety-events", { days: 30, limit: 20 }],
    privacy: ["/admin/privacy-requests", { limit: 10 }],
    audit: ["/admin/audit-events", { limit: 12 }],
  };

  const CHART = { teal: "#1AA093", coral: "#D98841", gold: "#E0B354", prev: "#C9C0B0", grid: "#ECE6DA", ink: "#33403D", muted: "#6B7772" };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  const n = (v) => (v==null||v===""||isNaN(v))?"–":Number(v).toLocaleString("en-US");

  // ══════════ 設計稿示範數據（預設顯示，讓後台一開就長得像設計稿） ══════════
  const S = {
    overview: {
      highlight: "本月亮點：付費家庭圈成長 <b>+8.4%</b>，AI 通話總時長創新高；有 <b>3 筆</b>安全警示待處理，其中 1 筆為高風險，建議優先確認。",
      kpi: [
        { label:"北極星 · 每週有意義陪伴天數", value:"26,200", delta:"+7.4%", dir:"up", sub:"近 7 天 · 平均每位長輩 4.2 天/週", accent:true, info:"我們最重要的指標。把「某位長輩某天真的有跟沐寧互動」去重後、近 7 天加總。算數的互動：滿 60 秒的語音通話、完成的視訊臉通話、做到的吃藥／回診提醒、家人傳話。只點開看一眼不算。" },
        { label:"週活躍長輩 WAU", value:"6,240", delta:"+5.1%", dir:"up", sub:"近 7 天有真互動的長輩" },
        { label:"語音接通成功率", value:"93%", delta:"未達標", dir:"down", sub:"目標 95% · 撥了有講到話的比例", info:"撥出的語音通話裡真的接通、講到話的比例。健康線 ≥ 95%，低於代表撥接體驗有問題。" },
        { label:"免費→付費轉換率", value:"22.1%", delta:"+1.4%", dir:"up", sub:"免費用戶變成付費的比例", info:"健康線 ≥ 8%（子女代付、付費意願通常較高）。" },
      ],
      callDaily: [["週一",9800],["週二",10400],["週三",9100],["週四",11200],["週五",11900],["週六",13600],["週日",12480]],
      newUsers: [["2月",310],["3月",395],["4月",470],["5月",540],["6月",602],["7月",640]],
      chars: [["寧寧",38],["小昀",18],["阿宏",14],["咪咪",12],["阿原",11],["旺財",7]],
    },
    growth: {
      highlight:"成長健康度良好：黏著度 <b>38%</b>、次月留存 <b>62%</b> 且逐月改善。單位經濟（LTV:CAC）要你填了行銷花費才算得出——填在「連線設定」。",
      kpi:[
        { label:"日活躍 DAU", value:"3,180", delta:"+4.2%", dir:"up", sub:"今天有真互動的人", info:"當日有真互動的不重複人數。" },
        { label:"週活躍 WAU", value:"6,240", delta:"+3.8%", dir:"up", sub:"近 7 天有真互動的人" },
        { label:"月活躍 MAU", value:"8,432", delta:"+6.1%", dir:"up", sub:"近 30 天有真互動的人" },
        { label:"黏著度", value:"38%", delta:"+2pt", dir:"up", sub:"DAU / MAU", info:"黏著度＝日活躍÷月活躍，越高代表用戶越常回來。40% 以上算很黏。" },
      ],
      dau: [["W1",2680],["W2",2740],["W3",2820],["W4",2910],["W5",2980],["W6",3040],["W7",3120],["W8",3180]],
      cohort: [
        ["2月",310,[100,58,44,37,33,30]],["3月",395,[100,60,46,39,35,null]],["4月",470,[100,61,47,40,null,null]],
        ["5月",540,[100,63,49,null,null,null]],["6月",602,[100,64,null,null,null,null]],["7月",640,[100,null,null,null,null,null]],
      ],
      channels: [["子女帶爸媽（口碑）",5.8,"CAC NT$820 · 44%"],["App Store 自然",4.1,"CAC NT$1,180 · 27%"],["長照通路合作",3.2,"CAC NT$1,510 · 18%"],["社群廣告",2.4,"CAC NT$1,920 · 11%"]],
    },
    users: {
      kpi:[
        { label:"總用戶", value:"8,432", delta:"+12.4%", dir:"up", sub:"長輩 5,110 · 家人 3,322" },
        { label:"今日活躍", value:"3,180", delta:"+4.2%", dir:"up", sub:"活躍率 37.7%" },
        { label:"低度使用", value:"486", delta:"需關懷", dir:"flat", sub:"7 天內未通話" },
        { label:"守護中", value:"12", delta:"3 待處理", dir:"flat", sub:"含安全網啟動戶" },
      ],
      roster:[
        ["張阿桃","張家","Pro","寧寧","82 分","活躍中","今天 08:14"],
        ["李水木","李家","Plus","阿宏","41 分","低度使用","3 天前"],
        ["吳秀蓮","吳家","Plus","小昀","67 分","守護中","昨天 22:47"],
        ["王進財","王家","免費","咪咪","12 分","活躍中","今天 10:02"],
        ["陳美惠","陳家","Pro","寧寧","95 分","活躍中","今天 09:30"],
        ["林金水","林家","Plus","阿原","38 分","活躍中","昨天 19:10"],
        ["黃阿玉","黃家","免費","旺財","8 分","低度使用","5 天前"],
        ["蔡麗雲","蔡家","Plus","小昀","54 分","活躍中","今天 07:50"],
      ],
    },
    safety: {
      principle:"守護原則：沐寧偵測到不對勁時協助聯繫指定家人並引導撥打 119／1925。系統不做醫療判讀——所有警示皆需真人確認後處理。",
      kpi:[
        { label:"待處理警示", value:"3", delta:"1 高風險", dir:"down", sub:"需 30 分內回應" },
        { label:"平均回應時間", value:"8.4", unit:"分", delta:"-21%", dir:"up", sub:"較上月更快" },
        { label:"本月已處理", value:"48", delta:"全數關閉", dir:"up", sub:"含 6 筆誤報" },
        { label:"安全網啟動", value:"12", unit:"戶", delta:"9 戶已聯繫", dir:"flat", sub:"其中 9 戶已聯繫家人" },
      ],
      queue:[
        { risk:"高風險", tone:"bad", title:"情緒危機關鍵字偵測", desc:"凌晨對話中偵測到高風險字句，寧寧已啟動安全網並暫緩結束通話。建議立即由專員確認並聯繫指定家人。", who:"張阿桃 · 張家", time:"今天 06:14", src:"AI 安全網" },
        { risk:"留意", tone:"warn", title:"連續 3 天未接起晨間問候", desc:"系統連續 3 日晨間主動致電無回應，Apple 健康步數同步亦停滯。建議提醒家人關心。", who:"李水木 · 李家", time:"今天 09:02", src:"活躍度監測" },
        { risk:"留意", tone:"warn", title:"健康數據異常波動", desc:"心率資料在夜間出現連續高值，超出個人基線。非醫療判讀，僅提示關注並建議諮詢醫師。", who:"吳秀蓮 · 吳家", time:"昨天 22:47", src:"健康同步" },
      ],
      resolved:[
        ["情緒低落連續紀錄","李水木 · 李家 · 處置：已聯繫子女，安排回診","7/8"],
        ["跌倒關鍵字（誤報）","王進財 · 王家 · 處置：確認為口誤，已關閉","7/7"],
      ],
      sop:"危機處理 SOP：① 專員 30 分鐘內確認 → ② 聯繫家庭圈指定聯絡人 → ③ 必要時引導撥打 119／1925 並記錄 → ④ 結案並回填處置。所有紀錄僅授權營運與安全團隊檢視。",
    },
    reminders: {
      kpi:[
        { label:"整體完成率", value:"84%", delta:"+1%", dir:"up", sub:"寬容不指責" },
        { label:"用藥提醒", value:"88%", delta:"+2%", dir:"up", sub:"最高完成率" },
        { label:"回診提醒", value:"81%", delta:"+3%", dir:"up", sub:"含改期協助" },
        { label:"量測類", value:"74%", delta:"-1%", dir:"down", sub:"血壓·體重" },
      ],
      byType:[["用藥提醒",88,"12,840 次","teal"],["回診提醒",81,"2,310 次","teal"],["量血壓",74,"8,920 次","gold"],["喝水·散步",69,"15,600 次","gold"]],
      trend:[["2月",79],["3月",80],["4月",82],["5月",83],["6月",83],["7月",84]],
      follow:[["張阿桃","血壓量測 · 本月完成 3/12","32%"],["李水木","用藥提醒 · 連續漏服 3 次","48%"],["王進財","回診提醒 · 已改期待確認","–"]],
      principle:"沐寧的提醒寬容不指責：漏了明天繼續，不會有紅字歸零。低完成率名單僅供關懷跟進，不作為考核。",
    },
    mood: {
      kpi:[
        { label:"平均心情球", value:"4.6", unit:"/5", delta:"+0.2", dir:"up", sub:"情緒穩定向好" },
        { label:"每日記錄率", value:"71%", delta:"+4%", dir:"up", sub:"有記心情的用戶" },
        { label:"健康同步戶", value:"2,180", delta:"+12%", dir:"up", sub:"Apple 健康連動" },
        { label:"情緒關注", value:"34", unit:"戶", delta:"已標記", dir:"flat", sub:"連續低落已標記" },
      ],
      moodTrend:[["W1",4.3],["W2",4.2],["W3",4.4],["W4",4.3],["W5",4.5],["W6",4.4],["W7",4.5],["W8",4.6],["W9",4.5],["W10",4.6],["W11",4.7],["W12",4.6]],
      dist:[["很好 😊",42,"teal"],["還不錯 🙂",31,"teal"],["普通 😐",16,"gold"],["有點累 😔",8,"gold"],["難過 😢",3,"coral"]],
      health:[["步數",86,"teal"],["心率",72,"teal"],["睡眠",58,"gold"],["血壓（手動）",41,"gold"]],
      watch:[["張阿桃","張家 · 連續 4 天偏低"],["李水木","李家 · 記錄停滯 5 天"],["吳秀蓮","吳家 · 夜間情緒波動"]],
      principle:"情緒與健康資料只留給用戶與其明確授權的家人，可隨時匯出、刪除。後台呈現為去識別化的彙總與關注提示，非醫療判讀。",
    },
    subscription: {
      kpi:[
        { label:"本月 MRR", value:"1.42M", delta:"+8.4%", dir:"up", sub:"NT$ 經常性收入" },
        { label:"付費訂閱", value:"1,860", delta:"+7.2%", dir:"up", sub:"Plus 1,540 · Pro 320" },
        { label:"點數加購", value:"312K", delta:"+8.3%", dir:"up", sub:"NT$ · 永不過期點數" },
        { label:"付費轉換率", value:"22.1%", delta:"+1.4%", dir:"up", sub:"免費→付費" },
      ],
      mrrTrend:[["2月",108],["3月",116],["4月",124],["5月",131],["6月",134],["7月",142]],
      dist:[["免費體驗",6572,78,"prev"],["Plus 家庭",1540,18.3,"teal"],["Pro 大家庭",320,3.8,"coral"]],
      points:[["2月",186],["3月",210],["4月",238],["5月",265],["6月",288],["7月",312]],
      plans:[
        ["免費體驗","綁定送 5 分鐘 · 提醒與心情先用起來","NT$0"],
        ["Plus 家庭首選","每月贈 200 點 · 家庭圈最多 4 人","NT$499/月"],
        ["Pro 大家庭","每月贈 500 點 · 家庭圈最多 12 人","NT$999/月"],
      ],
      ledger:[
        ["#TX-88214","陳美惠","Pro 訂閱","NT$999","8 分鐘前","已入帳","ok"],
        ["#TX-88213","黃國棟","點數 500","NT$500","32 分鐘前","待對帳","warn"],
        ["#TX-88212","林淑芬","Plus 訂閱","NT$499","1 小時前","已入帳","ok"],
        ["#TX-88210","吳秀蓮","點數 1000","NT$1,000","3 小時前","交易失敗","bad"],
        ["#TX-88208","王進財","Plus 訂閱","NT$499","今天 09:12","已退款","mute"],
        ["#TX-88205","蔡麗雲","Pro 訂閱","NT$999","今天 08:40","爭議","bad"],
        ["#TX-88201","張家家人","點數 200","NT$200","昨天","已入帳","ok"],
      ],
    },
    usage: {
      kpi:[
        { label:"本月通話", value:"208K", unit:"分", delta:"+9.2%", dir:"up", sub:"約 3,470 小時" },
        { label:"平均通話時長", value:"5.7", unit:"分", delta:"+0.4", dir:"up", sub:"每通對話" },
        { label:"主動致電接起率", value:"82%", delta:"+3%", dir:"up", sub:"晨問候·晚安" },
        { label:"記憶命中率", value:"76%", delta:"+5%", dir:"up", sub:"接得上上次話題" },
      ],
      byPlan:[["免費",26],["Plus",112],["Pro",168]],
      weekCall: [["週一",9800],["週二",10400],["週三",9100],["週四",11200],["週五",11900],["週六",13600],["週日",12480]],
      chars:[["寧寧",38],["小昀",18],["阿宏",14],["咪咪",12],["阿原",11],["旺財",7]],
    },
    characters: {
      principle:"角色即產品：六位夥伴各有聲音與個性，名字都能由用戶自訂。此處管理每位夥伴的問候腳本、語氣與上線狀態——溫度是沐寧的護城河。",
      list:[
        { i:"寧", name:"寧寧", color:"#37A099", calls:"4,820", quote:"「我記得」是她的口頭禪，最懂你的貼心家人", dur:"6.2", pct:"38%", score:"4.6" },
        { i:"阿", name:"阿宏", color:"#5B7A72", calls:"1,760", quote:"話不多，但一句就讓人安心的可靠肩膀", dur:"5.1", pct:"14%", score:"4.4" },
        { i:"小", name:"小昀", color:"#E0B354", calls:"2,290", quote:"開朗元氣，輕快愛笑的正能量", dur:"5.8", pct:"18%", score:"4.7" },
        { i:"阿", name:"阿原", color:"#8AA34E", calls:"1,410", quote:"像鄰家朋友，聊起來最沒壓力", dur:"6.0", pct:"11%", score:"4.5" },
        { i:"咪", name:"咪咪", color:"#D98841", calls:"1,520", quote:"傲嬌小貓，嘴上嫌你、心裡想你，喵～", dur:"4.9", pct:"12%", score:"4.3" },
        { i:"旺", name:"旺財", color:"#C77A2E", calls:"890", quote:"忠誠直球的熱情汪汪，永遠等你回家", dur:"5.4", pct:"7%", score:"4.6" },
      ],
      scripts:[["晨間問候","每日 08:00 · 全體 · 「早安！昨晚睡得好嗎？」"],["睡前晚安","每日 21:30 · 全體 · 「今天辛苦了，早點休息喔」"],["用藥提醒銜接","依個人排程 · 「記得吃飯後那顆藥，我陪你」"]],
    },
    support: {
      kpi:[
        { label:"待處理工單", value:"7", delta:"2 高優先", dir:"down", sub:"需今日回覆" },
        { label:"平均首次回覆", value:"1.8", unit:"時", delta:"-12%", dir:"up", sub:"較上月更快" },
        { label:"本月已解決", value:"142", delta:"解決率 96%", dir:"up", sub:"滿意度 4.7/5" },
        { label:"正向回饋", value:"38", unit:"則", delta:"用戶稱讚", dir:"up", sub:"用戶主動稱讚" },
      ],
      tickets:[
        { title:"點數加購後未入帳", who:"黃國棟 · 計費", pri:"高優先", tone:"bad", time:"8 分鐘前" },
        { title:"通話中聲音會斷斷續續", who:"陳美惠家人 · 技術", pri:"中優先", tone:"warn", time:"32 分鐘前" },
        { title:"想把媽媽加入家庭圈", who:"林淑芬 · 家庭圈", pri:"低優先", tone:"mute", time:"1 小時前" },
        { title:"希望能更改寧寧的稱呼", who:"吳秀蓮 · 角色", pri:"低優先", tone:"mute", time:"2 小時前" },
        { title:"如何匯出並刪除聊天紀錄", who:"蔡麗雲家人 · 隱私", pri:"中優先", tone:"warn", time:"3 小時前" },
      ],
      cats:[["技術問題",34,"teal"],["計費與點數",28,"teal"],["家庭圈設定",20,"gold"],["角色與內容",11,"gold"],["隱私與資料",7,"coral"]],
      quotes:[
        ["「媽媽每天都在等寧寧打來，謝謝你們。」","— 黃家 · 子女"],
        ["「爸爸終於願意量血壓了，用哄的真的有效。」","— 吳家 · 子女"],
        ["「深夜睡不著時有人陪，很安心。」","— 蔡麗雲"],
      ],
    },
    system: {
      highlight:"AI 全天候值守：偵測到異常會即時告警，並嘗試自動修復（切換節點、重試佇列）。目前 <b>2 項</b>服務需關注，本週已自動處理 3 起事件。",
      kpi:[
        { label:"系統可用率", value:"99.97%", delta:"SLA 99.9%", dir:"up", sub:"近 30 天" },
        { label:"平均回應延遲", value:"240", unit:"ms", delta:"-8%", dir:"up", sub:"較上週更快" },
        { label:"錯誤率", value:"0.12%", delta:"+0.04%", dir:"down", sub:"金流回呼拉高" },
        { label:"AI 偵測告警", value:"5", delta:"3 起自動修復", dir:"flat", sub:"本週" },
      ],
      services:[
        ["即時語音對話","真人般語音 · 全區正常","正常","ok","99.99%","180ms"],
        ["會動的臉渲染","部分節點延遲偏高","降級","warn","99.80%","420ms"],
        ["記憶引擎","記得你說過的話","正常","ok","99.97%","90ms"],
        ["推播·提醒排程","用藥·回診準時觸發","正常","ok","100%","—"],
        ["金流 / 點數（App Store）","Webhook 失敗率上升","異常","bad","98.90%","—"],
        ["Apple 健康同步","步數·心率自動帶入","正常","ok","99.95%","320ms"],
        ["危機安全網偵測","全天候值守中","正常","ok","100%","60ms"],
      ],
      events:[
        { title:"金流 Webhook 失敗率上升至 4.2%", tag:"AI 偵測", status:"處理中", tone:"bad", desc:"AI 偵測到 App Store 交易回呼失敗率超出基線（0.3%→4.2%），部分點數加購未即時入帳。已自動重試佇列並通知工程團隊。", who:"金流 / 點數 · 12 分鐘前" },
        { title:"會動的臉渲染延遲 +180ms", tag:"AI 偵測", status:"監控中", tone:"warn", desc:"AI 偵測到亞太渲染節點延遲高於門檻，已自動將 30% 流量切往備援節點，體驗影響輕微。", who:"會動的臉 · 34 分鐘前" },
        { title:"語音服務區域性斷線（已自癒）", tag:"AI 偵測", status:"已恢復", tone:"ok", desc:"AI 偵測到單一節點斷線後自動切換，中斷 42 秒即恢復，無用戶通報。", who:"即時語音 · 2 小時前" },
      ],
      repairs:[["自動切換渲染節點","會動的臉延遲 → 切備援","已恢復"],["重試金流回呼佇列","Webhook 失敗 → 自動重送","處理中"],["語音節點自癒","區域斷線 → 42 秒恢復","已恢復"]],
      principle:"系統告警為 App 技術健康監測（服務可用率、延遲、錯誤、金流回呼等），與「安全守護警示」（長輩危機偵測）分屬不同層級，互不混用。",
    },
  };

  // ══════════ 元件 builders ══════════
  function heroBanner(html, opts) {
    opts = opts || {};
    const cta = opts.cta ? `<button type="button" data-goto="${esc(opts.cta.to)}">${esc(opts.cta.label)}</button>` : "";
    return `<div class="hero-banner ${opts.calm?"calm":""}"><div class="hb-body">${opts.title?`<div class="hb-title">${esc(opts.title)}</div>`:""}<div class="hb-text">${html}</div></div>${cta}</div>`;
  }
  function kpiRow(items) {
    return `<div class="kpi-row">${items.map((k)=>`
      <div class="kpi ${k.accent?"kpi-accent":""}">
        <div class="kpi-top"><span class="kpi-label">${esc(k.label)}${k.info?` <span class="kpi-info" title="${esc(k.info)}">ⓘ</span>`:""}</span>${k.delta?`<span class="kpi-delta ${k.dir||"flat"}">${esc(k.delta)}</span>`:""}</div>
        <div class="kpi-value">${esc(k.value)}${k.unit?`<span class="unit">${esc(k.unit)}</span>`:""}</div>
        ${k.sub?`<div class="kpi-sub">${esc(k.sub)}</div>`:""}
      </div>`).join("")}</div>`;
  }
  function card(title, note, body, headRight) {
    return `<div class="card"><div class="card-head"><div><h3>${esc(title)}${note?"":""}</h3>${note?`<div class="card-note">${esc(note)}</div>`:""}</div>${headRight||""}</div>${body}</div>`;
  }
  function barsList(items, unitMax) {
    const max = unitMax || Math.max(...items.map((i)=>i[1]), 1);
    return `<div class="bars-list">${items.map((i)=>{
      const [name, val, sub, color] = i;
      const pct = Math.round((val/max)*100);
      const disp = typeof val==="number" && val<=100 && (String(val).indexOf(".")>-1||sub===undefined) ? val+"%" : n(val);
      return `<div class="bl"><div class="bl-top"><span class="bl-name">${esc(name)}</span><span class="bl-val">${esc(typeof val==="number"?(val+ (val<=100&&!sub?"%":"")):val)}${sub?`<span class="bl-sub">${esc(sub)}</span>`:""}</span></div><div class="track"><div class="fill ${color||""}" style="width:${pct}%"></div></div></div>`;
    }).join("")}</div>`;
  }
  function principle(text) { return `<div class="principle">${text.indexOf("<")>-1?text:esc(text)}</div>`; }
  function srcBadge() { return state.connected ? `<span class="srcbadge live">● 真資料</span>` : `<span class="srcbadge demo">● 示範數據</span>`; }

  // ══════════ 圖表引擎（純 SVG） ══════════
  const NS = "http://www.w3.org/2000/svg";
  function svg(tag, a){ const e=document.createElementNS(NS,tag); for(const k in a) e.setAttribute(k,a[k]); return e; }
  function niceMax(v){ if(!v||v<=0) return 4; const raw=v*1.12, mag=Math.pow(10,Math.floor(Math.log10(raw))); for(const m of [1,2,2.5,4,5,8,10]) if(m*mag>=raw) return m*mag; return 10*mag; }
  function tip(html,x,y){ const t=$("chartTip"); t.innerHTML=html; t.hidden=false; const r=t.getBoundingClientRect(); let px=x+14,py=y+14; if(px+r.width>innerWidth-8)px=x-r.width-14; if(py+r.height>innerHeight-8)py=y-r.height-14; t.style.left=px+"px"; t.style.top=py+"px"; }
  function hideTip(){ $("chartTip").hidden=true; }

  // 直式長條（單系列 / 或本週vs上週雙系列）
  function columnChart(box, labels, series, opts) {
    opts = opts || {};
    const W=760,H=190,L=44,R=14,T=14,B=28, pw=W-L-R, ph=H-T-B;
    const all = series.flatMap((s)=>s.values);
    const max = niceMax(Math.max(1,...all));
    const y=(v)=>T+ph-(v/max)*ph;
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img"});
    for(let t=0;t<=4;t++){ const val=max/4*t, gy=y(val); s.appendChild(svg("line",{x1:L,x2:W-R,y1:gy,y2:gy,stroke:CHART.grid,"stroke-width":1})); const tx=svg("text",{x:L-8,y:gy+4,"text-anchor":"end","font-size":11,fill:CHART.muted}); tx.textContent=n(Math.round(val)); s.appendChild(tx); }
    const band=pw/labels.length, groupW=Math.min(band*0.62, series.length*20+ (series.length-1)*4), barW=Math.min(22,(groupW-(series.length-1)*4)/series.length);
    labels.forEach((lb,i)=>{
      const cx=L+band*i+band/2, startX=cx-groupW/2;
      series.forEach((se,si)=>{
        const v=se.values[i], top=y(v), h=Math.max(0,T+ph-top), x=startX+si*(barW+4);
        const path=svg("path",{d: h<=0.5?`M ${x} ${T+ph} h ${barW}`:`M ${x} ${T+ph} V ${top+4} Q ${x} ${top} ${x+4} ${top} H ${x+barW-4} Q ${x+barW} ${top} ${x+barW} ${top+4} V ${T+ph} Z`, fill:se.color});
        path.addEventListener("mousemove",(e)=>tip(`<div>${esc(lb)}${series.length>1?" · "+esc(se.name):""}</div><b>${n(v)}</b>${opts.unit?" "+opts.unit:""}`,e.clientX,e.clientY));
        path.addEventListener("mouseleave",hideTip);
        s.appendChild(path);
      });
      const tl=svg("text",{x:cx,y:H-8,"text-anchor":"middle","font-size":11,fill:CHART.ink}); tl.textContent=lb; s.appendChild(tl);
    });
    box.innerHTML=""; box.appendChild(s);
    if(series.length>1){ const lg=document.createElement("div"); lg.className="legend"; lg.innerHTML=series.map((se)=>`<span class="key"><span class="swatch" style="background:${se.color}"></span>${esc(se.name)}</span>`).join(""); box.appendChild(lg); }
  }

  // 折線
  function lineChart(box, labels, series, opts) {
    opts=opts||{};
    const W=760,H=180,L=44,R=16,T=14,B=26, pw=W-L-R, ph=H-T-B;
    const all=series.flatMap((s)=>s.values); const maxV=opts.maxY||niceMax(Math.max(1,...all)); const minV=opts.minY||0;
    const nP=labels.length, x=(i)=>L+(nP<=1?pw/2:(i/(nP-1))*pw), y=(v)=>T+ph-((v-minV)/(maxV-minV))*ph;
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img"});
    for(let t=0;t<=4;t++){ const val=minV+(maxV-minV)/4*t, gy=y(val); s.appendChild(svg("line",{x1:L,x2:W-R,y1:gy,y2:gy,stroke:CHART.grid,"stroke-width":1})); const tx=svg("text",{x:L-8,y:gy+4,"text-anchor":"end","font-size":11,fill:CHART.muted}); tx.textContent=(maxV<=5?val.toFixed(1):n(Math.round(val))); s.appendChild(tx); }
    const step=Math.max(1,Math.ceil(nP/7));
    for(let i=0;i<nP;i+=step){ const tx=svg("text",{x:x(i),y:H-6,"text-anchor":"middle","font-size":11,fill:CHART.muted}); tx.textContent=labels[i]; s.appendChild(tx); }
    series.forEach((se)=>{
      const pts=se.values.map((v,i)=>`${x(i)},${y(v)}`).join(" ");
      if(se.wash) s.appendChild(svg("polygon",{points:`${L},${T+ph} ${pts} ${x(nP-1)},${T+ph}`,fill:se.color,opacity:.1}));
      s.appendChild(svg("polyline",{points:pts,fill:"none",stroke:se.color,"stroke-width":2,"stroke-linejoin":"round","stroke-linecap":"round"}));
      const lv=se.values[nP-1]; s.appendChild(svg("circle",{cx:x(nP-1),cy:y(lv),r:4.5,fill:se.color,stroke:"#fff","stroke-width":2}));
    });
    const overlay=svg("rect",{x:L,y:T,width:pw,height:ph,fill:"transparent"});
    const cross=svg("line",{x1:0,x2:0,y1:T,y2:T+ph,stroke:CHART.muted,"stroke-width":1,opacity:0}); s.appendChild(cross);
    const dots=series.map((se)=>{ const d=svg("circle",{r:5,fill:se.color,stroke:"#fff","stroke-width":2,opacity:0}); s.appendChild(d); return d; });
    overlay.addEventListener("mousemove",(e)=>{ const r=s.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*W; const i=Math.max(0,Math.min(nP-1,Math.round((px-L)/pw*(nP-1)))); cross.setAttribute("x1",x(i)); cross.setAttribute("x2",x(i)); cross.setAttribute("opacity",.4); const rows=series.map((se,si)=>{dots[si].setAttribute("cx",x(i));dots[si].setAttribute("cy",y(se.values[i]));dots[si].setAttribute("opacity",1);return `<span style="color:#c9d6cf">${esc(se.name)}</span> <b>${se.values[i]}</b>`;}); tip(`<div>${esc(labels[i])}</div>${rows.join("<br>")}`,e.clientX,e.clientY); });
    overlay.addEventListener("mouseleave",()=>{ cross.setAttribute("opacity",0); dots.forEach((d)=>d.setAttribute("opacity",0)); hideTip(); });
    s.appendChild(overlay);
    box.innerHTML=""; box.appendChild(s);
    if(series.length>1){ const lg=document.createElement("div"); lg.className="legend"; lg.innerHTML=series.map((se)=>`<span class="key"><span class="swatch" style="background:${se.color}"></span>${esc(se.name)}</span>`).join(""); box.appendChild(lg); }
  }

  // 甜甜圈
  function donut(box, segs, centerVal, centerLabel) {
    const W=180,r=70,cx=90,cy=90,sw=26,C=2*Math.PI*r;
    const total=segs.reduce((a,s)=>a+s.val,0)||1;
    const s=svg("svg",{viewBox:`0 0 ${W} ${W}`,width:W,height:W});
    s.appendChild(svg("circle",{cx,cy,r,fill:"none",stroke:CHART.grid,"stroke-width":sw}));
    let off=0;
    segs.forEach((seg)=>{ const frac=seg.val/total, len=frac*C; const c=svg("circle",{cx,cy,r,fill:"none",stroke:seg.color,"stroke-width":sw,"stroke-dasharray":`${len} ${C-len}`,"stroke-dashoffset":-off,transform:`rotate(-90 ${cx} ${cy})`}); s.appendChild(c); off+=len; });
    const t1=svg("text",{x:cx,y:cy-2,"text-anchor":"middle","font-size":26,"font-weight":700,fill:CHART.ink,"font-family":"Poppins,sans-serif"}); t1.textContent=centerVal; s.appendChild(t1);
    const t2=svg("text",{x:cx,y:cy+18,"text-anchor":"middle","font-size":11,fill:CHART.muted}); t2.textContent=centerLabel; s.appendChild(t2);
    const legend=`<div class="donut-legend">${segs.map((seg)=>`<div class="dl"><span class="sw" style="background:${seg.color}"></span><span class="name">${esc(seg.name)}</span><span class="val">${n(seg.val)}</span><span class="pct">${seg.pct}%</span></div>`).join("")}</div>`;
    box.innerHTML=`<div class="donut-wrap"><div style="flex:0 0 ${W}px">${""}</div>${legend}</div>`;
    box.querySelector(".donut-wrap>div").appendChild(s);
  }

  const cc = { teal:CHART.teal, coral:CHART.coral, gold:CHART.gold, prev:CHART.prev };

  // ══════════ 頁面渲染 ══════════
  function chartMount(id){ return `<div class="chart-box" id="${id}"></div>`; }
  const pending = []; // 待掛載的圖表函式

  function renderPage(id) {
    pending.length = 0;
    let html = "";
    const badge = () => srcBadge();
    const P = S[id];

    if (id === "overview") {
      html += heroBanner(P.highlight, { title:"本月概況", cta:{to:"safety", label:"前往守護中心"}, calm:true });
      html += kpiRow(P.kpi.map((k,i)=>({...k, accent:i===0})));
      html += `<div class="grid-2">`;
      html += card("每日 AI 陪伴通話時長", "過去 7 天 · 單位：分鐘", chartMount("ov-call"), badge());
      html += card("新用戶成長", "近 6 個月綁定帳號 · 月增 6.3%", chartMount("ov-new"), badge());
      html += `</div>`;
      html += `<div class="grid-3">`;
      html += card("提醒完成率", "寬容不指責", `<div class="kpi-value">84%</div><div class="kpi-sub">漏了明天繼續，無紅字歸零</div>`);
      html += card("平均每日心情球", "情緒穩定向好", `<div class="kpi-value">4.6<span class="unit">/5</span></div><div class="kpi-sub">本週較上週 +0.2</div>`);
      html += card("六位夥伴使用分布", "本月啟用角色佔比", barsList(P.chars.map((c)=>[c[0],c[1],null,"teal"])));
      html += `</div>`;
      pending.push(()=>columnChart($("ov-call"), P.overview_labels||P.callDaily.map(d=>d[0]), [{name:"通話分鐘",color:cc.teal,values:P.callDaily.map(d=>d[1])}], {unit:"分"}));
      pending.push(()=>columnChart($("ov-new"), P.newUsers.map(d=>d[0]), [{name:"新綁定",color:cc.teal,values:P.newUsers.map(d=>d[1])}]));
    }

    else if (id === "growth") {
      html += heroBanner(P.highlight, { title:"成長健康度", calm:true });
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===3})));
      html += `<div class="grid-2">`;
      html += card("每週日活躍 DAU", "近 8 週 · 穩定爬升", chartMount("gr-dau"), badge());
      html += card("什麼算「活躍用戶」", "看數字前先講清楚定義", `
        <div class="def-list">
          <div class="def"><b>活躍</b>＝當天真的有跟沐寧互動的人：滿 60 秒的語音通話、完成視訊臉通話、做到吃藥／回診提醒、家人傳話。<span class="muted">只點開 App 看一眼不算。</span></div>
          <div class="def"><b>DAU</b> 當日 ／ <b>WAU</b> 近 7 天 ／ <b>MAU</b> 近 30 天，都是「不重複人數」。</div>
          <div class="def"><b>黏著度</b>＝DAU ÷ MAU，衡量用戶多常回來（40% 以上算很黏）。</div>
        </div>`);
      html += `</div>`;
      html += card("世代留存分析", "顏色越深留存越高 · 新世代留存更好", cohortTable(P.cohort), badge());
      html += card("單位經濟 LTV / CAC", "用你在「連線設定」填的試算假設算", ltvCacHTML());
      pending.push(()=>columnChart($("gr-dau"), P.dau.map(d=>d[0]), [{name:"DAU",color:cc.teal,values:P.dau.map(d=>d[1])}], {unit:"人"}));
    }

    else if (id === "users") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      const tabsDef = ["全部","活躍中","低度使用","守護中","免費","Plus","Pro"];
      const active = state.tabs.users || "全部";
      const rows = P.roster.filter((r)=> active==="全部" ? true : (["免費","Plus","Pro"].includes(active) ? r[2]===active : r[5]===active));
      const tabsHTML = `<div class="tabs" data-tabs="users">${tabsDef.map((t)=>{
        const cnt = t==="全部" ? P.roster.length : P.roster.filter((r)=>["免費","Plus","Pro"].includes(t)?r[2]===t:r[5]===t).length;
        return `<button class="${t===active?"on":""}" data-tab="${esc(t)}">${esc(t)}<span class="n">${cnt}</span></button>`;
      }).join("")}</div>`;
      const head = `<div class="rowflex">${tabsHTML}<input class="tbl-search" id="userSearch" type="search" placeholder="搜尋名字或家庭"></div>`;
      html += card("用戶與家庭圈名冊", `顯示 ${rows.length} 筆`, head + tableHTML(
        ["用戶","家庭圈","方案","常用夥伴","本月通話","狀態","最後互動",""],
        rows.map((r,i)=>[esc(r[0]),esc(r[1]),planPill(r[2]),esc(r[3]),`<span class="num">${esc(r[4])}</span>`,statusPill(r[5]),esc(r[6]),`<button class="btn-ghost btn-sm" data-user="${esc(r[0])}">查看</button>`]),
      ), badge());
    }

    else if (id === "safety") {
      html += heroBanner(esc(P.principle), { calm:true, title:"守護原則" });
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += card("即時佇列 · 待處理警示", "標紅為高風險，需 30 分內回應", queueHTML(P.queue), badge());
      html += card("近期處理紀錄", "已結案", `<div class="rows">${P.resolved.map((r)=>`<div class="row-item done"><div class="ri-body"><div class="ri-title">${esc(r[0])} <span class="pill mute">已結案</span></div><div class="ri-desc">${esc(r[1])}</div></div><div class="ri-meta">${esc(r[2])}</div></div>`).join("")}</div>`);
      html += principle(P.sop);
    }

    else if (id === "reminders") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += `<div class="grid-2">`;
      html += card("各類提醒完成率", "本月 · 親口喊你，不是冷鈴聲", barsList(P.byType.map((b)=>[b[0],b[1],b[2],b[3]])), badge());
      html += card("完成率趨勢", "近 6 個月整體 · 單位：%", chartMount("rm-trend"), badge());
      html += `</div>`;
      html += card("需要跟進 · 低完成率名單", "僅供關懷跟進，不作為考核", `<div class="rows">${P.follow.map((f)=>`<div class="row-item tint-warn"><div class="ri-body"><div class="ri-title">${esc(f[0])}</div><div class="ri-desc">${esc(f[1])}</div></div><div class="ri-meta num" style="font-size:1.1rem;font-weight:700">${esc(f[2])}</div><div class="ri-actions"><button class="btn-ghost" type="button">提醒家人</button></div></div>`).join("")}</div>`);
      html += principle(P.principle);
      pending.push(()=>lineChart($("rm-trend"), P.trend.map(d=>d[0]), [{name:"完成率",color:cc.teal,values:P.trend.map(d=>d[1]),wash:true}], {minY:60,maxY:100}));
    }

    else if (id === "mood") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += `<div class="grid-2">`;
      html += card("全體心情趨勢", "近 12 週平均心情球（1–5）", chartMount("md-trend"), badge());
      html += card("心情分布", "本週佔比", barsList(P.dist.map((d)=>[d[0],d[1],null,d[2]])));
      html += `</div>`;
      html += `<div class="grid-2">`;
      html += card("健康數據同步", "Apple 健康自動帶入項目", barsList(P.health.map((h)=>[h[0],h[1],null,h[2]])));
      html += card("情緒關注名單", "連續低落心情球 · 已自動標記", `<div class="rows">${P.watch.map((w)=>`<div class="row-item tint-warn"><div class="ri-body"><div class="ri-title">${esc(w[0])}</div><div class="ri-desc">${esc(w[1])}</div></div><div class="ri-actions"><button class="btn-ghost" type="button">關心</button></div></div>`).join("")}</div>`);
      html += `</div>`;
      html += principle(P.principle);
      pending.push(()=>lineChart($("md-trend"), P.moodTrend.map(d=>d[0]), [{name:"心情球",color:cc.coral,values:P.moodTrend.map(d=>d[1]),wash:true}], {minY:3,maxY:5}));
    }

    else if (id === "subscription") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += `<div class="grid-2">`;
      html += card("MRR 趨勢", "近 6 個月 · 單位：萬 NT$", chartMount("sb-mrr"), badge());
      html += card("方案分布", "全體用戶訂閱結構", chartMount("sb-dist"), badge());
      html += `</div>`;
      html += `<div class="grid-2">`;
      html += card("每月點數加購額", "單位：千 NT$ · 1 點約 1 分鐘", chartMount("sb-pt"), badge());
      html += card("方案表現", "月費 · 贈點 · 家庭圈上限", tableHTML(["方案","內容","月費"], P.plans.map((p)=>[`<b>${esc(p[0])}</b>`,esc(p[1]),`<span class="num">${esc(p[2])}</span>`])));
      html += `</div>`;
      pending.push(()=>columnChart($("sb-mrr"), P.mrrTrend.map(d=>d[0]), [{name:"MRR",color:cc.teal,values:P.mrrTrend.map(d=>d[1])}], {unit:"萬"}));
      pending.push(()=>columnChart($("sb-pt"), P.points.map(d=>d[0]), [{name:"點數",color:cc.gold,values:P.points.map(d=>d[1])}]));
      pending.push(()=>donut($("sb-dist"), P.dist.map((d)=>({name:d[0],val:d[1],pct:d[2],color:cc[d[3]]||cc.prev})), "22%", "付費占比"));
    }

    else if (id === "usage") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += `<div class="grid-2">`;
      html += card("各方案平均聊聊時長", "每位用戶 / 月 · 分鐘", barsList(P.byPlan.map((b,i)=>[b[0],b[1],null,["prev","teal","coral"][i]]), 180), badge());
      html += card("每週通話時長", "週六日為高峰 · 單位：分鐘", chartMount("us-week"), badge());
      html += `</div>`;
      html += card("六位夥伴通話量佔比", "本月各角色使用", barsList(P.chars.map((c)=>[c[0],c[1],null,"teal"])));
      pending.push(()=>columnChart($("us-week"), P.weekCall.map(d=>d[0]), [{name:"通話分鐘",color:cc.teal,values:P.weekCall.map(d=>d[1])}], {unit:"分"}));
    }

    else if (id === "characters") {
      html += heroBanner(esc(P.principle), { calm:true, title:"角色即產品" });
      html += `<div class="char-grid">${P.list.map((c)=>`
        <div class="char-card">
          <div class="char-head"><span class="char-ava" style="background:${c.color}">${esc(c.i)}</span><div><div class="char-name">${esc(c.name)}</div><div class="char-status">本月 ${esc(c.calls)} 通 · 上線中</div></div></div>
          <div class="char-quote">「${esc(c.quote)}」</div>
          <div class="char-stats"><div class="cs"><div class="v">${esc(c.dur)}</div><div class="l">平均時長</div></div><div class="cs"><div class="v">${esc(c.pct)}</div><div class="l">使用佔比</div></div><div class="cs"><div class="v">${esc(c.score)}</div><div class="l">心情評分</div></div></div>
          <div class="char-actions"><button class="btn-ghost" type="button">編輯腳本</button><button class="btn-ghost" type="button">語氣設定</button></div>
        </div>`).join("")}</div>`;
      html += card("內容排程 · 主動關懷腳本", "全部腳本", `<div class="rows">${P.scripts.map((s)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(s[0])}</div><div class="ri-desc">${esc(s[1])}</div></div><span class="pill ok">啟用中</span></div>`).join("")}</div>`);
    }

    else if (id === "support") {
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += card("收件匣 · 待處理工單", "標紅為高優先，需今日回覆", `<div class="rows">${P.tickets.map((t)=>`<div class="row-item ${t.tone==="bad"?"tint-bad":t.tone==="warn"?"tint-warn":""}"><div class="ri-body"><div class="ri-title">${esc(t.title)}</div><div class="ri-meta">${esc(t.who)} · ${esc(t.time)}</div></div><span class="pill ${t.tone}">${esc(t.pri)}</span><div class="ri-actions"><button type="button">回覆</button></div></div>`).join("")}</div>`, badge());
      html += `<div class="grid-2">`;
      html += card("工單分類", "本月佔比", barsList(P.cats.map((c)=>[c[0],c[1],null,c[2]])));
      html += card("近期正向回饋", "用戶主動的溫暖話語", P.quotes.map((q)=>`<div class="quote-card"><div class="q">${esc(q[0])}</div><div class="who">${esc(q[1])}</div></div>`).join(""));
      html += `</div>`;
    }

    else if (id === "system") {
      html += heroBanner(P.highlight, { title:"AI 全天候值守", cta:{to:"system",label:"重新整理"} });
      html += kpiRow(P.kpi.map((k,i)=>({...k,accent:i===0})));
      html += card("服務健康 · 各服務狀態", "5 / 7 正常", tableHTML(
        ["服務","狀態","可用率","延遲"],
        P.services.map((s)=>[`<b>${esc(s[0])}</b><div class="kpi-sub">${esc(s[1])}</div>`,`<span class="pill ${s[3]}">${esc(s[2])}</span>`,`<span class="num">${esc(s[4])}</span>`,`<span class="num">${esc(s[5])}</span>`]),
      ), badge());
      html += card("系統告警事件", "AI 偵測 · 自動修復", `<div class="rows">${P.events.map((e)=>`<div class="row-item ${e.tone==="bad"?"tint-bad":e.tone==="warn"?"tint-warn":""}"><div class="ri-body"><div class="ri-title">${esc(e.title)} <span class="pill ${e.tone}">${esc(e.status)}</span></div><div class="ri-desc">${esc(e.desc)}</div><div class="ri-meta">${esc(e.tag)} · ${esc(e.who)}</div></div></div>`).join("")}</div>`);
      html += card("AI 自動修復紀錄", "本週 AI 值守處置", `<div class="rows">${P.repairs.map((r)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(r[0])}</div><div class="ri-desc">${esc(r[1])}</div></div><span class="pill ${r[2]==="已恢復"?"ok":"warn"}">${esc(r[2])}</span></div>`).join("")}</div>`);
      html += principle(P.principle);
    }

    else if (id === "settings") {
      html += settingsHTML();
    }

    $("pageRoot").innerHTML = html;
    pending.forEach((fn)=>{ try{ fn(); }catch(e){ console.warn("chart",e); } });
    bindPageEvents(id);
  }

  // 世代留存熱度表
  function cohortTable(rows) {
    const heads = ["加入世代","人數","M0","M1","M2","M3","M4","M5"];
    const body = rows.map((r)=>{
      const cells = r[2].map((v)=> v==null?`<td class="r">·</td>`:`<td class="cell" style="background:${cohortColor(v)}">${v}%</td>`).join("");
      return `<tr><td><b>${esc(r[0])}</b></td><td class="r">${n(r[1])} 人</td>${cells}</tr>`;
    }).join("");
    return `<div class="table-wrap"><table class="cohort"><thead><tr>${heads.map((h,i)=>`<th${i>1?' class="r"':''}>${h}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div><div class="kpi-sub" style="margin-top:8px">M0＝加入當月留存 100%；顏色越深留存越高。7 月世代 M1 尚未滿月。</div>`;
  }
  function cohortColor(v){ const t=Math.max(0,Math.min(1,(v-25)/75)); const a=0.14+t*0.78; return `rgba(46,138,131,${a.toFixed(2)})`; }

  // 單位經濟：吃「連線設定」填的試算假設（CAC 系統不可能自己知道、一律靠 Edward 填行銷花費）
  function ltvCacHTML(){
    const a=loadAssume();
    const paid=a.plusCount+a.proCount, mrr=a.plusCount*a.plusPrice+a.proCount*a.proPrice;
    const arpu=paid?mrr/paid:null, ltv=arpu!=null?arpu*a.lifeMonths:null;
    const cac=a.newPaid?a.marketing/a.newPaid:null;
    const ratio=(ltv!=null&&cac)?ltv/cac:null, payback=(cac!=null&&arpu)?cac/arpu:null;
    if(paid===0){
      return `<div class="empty-note"><b>CAC（獲客成本）＝行銷花費 ÷ 新增付費用戶</b>，這兩個數字只有你知道，系統算不出來——填了才有 LTV:CAC。</div><button class="btn-ghost" data-goto="settings" style="margin-top:12px">去設定填假設</button>`;
    }
    const cacBlock=cac!=null?`NT$${n(Math.round(cac))}`:`<span style="color:var(--coral-d)">待填</span>`;
    const health=ratio!=null?(ratio>=3?" 🟢":ratio>=1?" 🟡":" 🔴"):"";
    return `<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <div><div class="kpi-sub">LTV 終身價值</div><div class="kpi-value">${ltv!=null?"NT$"+n(Math.round(ltv)):"–"}</div></div>
      <div style="font-size:1.4rem;color:var(--muted)">÷</div>
      <div><div class="kpi-sub">CAC 獲客成本</div><div class="kpi-value">${cacBlock}</div></div>
      <div style="font-size:1.4rem;color:var(--muted)">＝</div>
      <div><div class="kpi-sub">${payback!=null?"回本約 "+payback.toFixed(1)+" 月":"回本"}</div><div class="kpi-value" style="color:var(--teal-dd)">${ratio!=null?ratio.toFixed(1)+"x":"–"}${health}</div></div>
    </div>
    <div class="kpi-sub" style="margin-top:12px">${cac==null?"CAC 還缺：到「連線設定 → 訂閱試算假設」填「本月新增付費」與「當月行銷花費」。健康門檻 LTV:CAC ≥ 3x。":"數字來自你填的試算假設。健康門檻 LTV:CAC ≥ 3x 且回本 &lt; 12 月。"}</div>`;
  }

  function tableHTML(cols, rows) {
    return `<div class="table-wrap"><table><thead><tr>${cols.map((c)=>`<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r)=>`<tr>${r.map((c)=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }
  function queueHTML(q){ return `<div class="rows">${q.map((a)=>`<div class="row-item tint-${a.tone}"><div class="ri-body"><div class="ri-title">${esc(a.title)} <span class="pill ${a.tone}">${esc(a.risk)}</span></div><div class="ri-desc">${esc(a.desc)}</div><div class="ri-meta">${esc(a.who)} · ${esc(a.time)} · ${esc(a.src)}</div></div><div class="ri-actions"><button type="button">立即處理</button><button class="btn-ghost" type="button">指派</button></div></div>`).join("")}</div>`; }
  function planPill(p){ const c=p==="Pro"?"ok":p==="Plus"?"ok":"mute"; return `<span class="pill ${c}">${esc(p)}</span>`; }
  function statusPill(s){ const c=s==="守護中"?"bad":s==="低度使用"?"warn":"ok"; return `<span class="pill ${c}">${esc(s)}</span>`; }

  // 用戶明細（點名冊「查看」開）
  function openUserDetail(name){
    const r=(S.users.roster||[]).find((x)=>x[0]===name); if(!r) return;
    const fields=[["家庭圈",r[1]],["方案",r[2]],["常用陪伴角色",r[3]],["本月通話",r[4]],["目前狀態",r[5]],["最後互動",r[6]]];
    const body=`
      <div class="modal-head"><div><div class="modal-title">${esc(r[0])}</div><div class="muted small">${esc(r[1])} · ${esc(r[2])}</div></div><button class="modal-x" data-close type="button">✕</button></div>
      <div class="detail-grid">${fields.map((f)=>`<div class="dcell"><div class="dlabel">${esc(f[0])}</div><div class="dval">${esc(f[1])}</div></div>`).join("")}</div>
      <div class="kpi-sub" style="margin-top:14px">${state.connected?"這是真實用戶資料。":"目前為示範資料——正式連線後這裡是真實用戶的家庭圈、通話與健康摘要。"}為保護隱私，健康與聊天內容需經該用戶授權才在此顯示。</div>`;
    let m=$("userModal");
    if(!m){ m=document.createElement("div"); m.id="userModal"; m.className="modal-overlay"; document.body.appendChild(m); }
    m.innerHTML=`<div class="modal-card">${body}</div>`;
    m.hidden=false;
    m.querySelectorAll("[data-close]").forEach((b)=>b.addEventListener("click",()=>{ m.hidden=true; }));
    m.addEventListener("click",(e)=>{ if(e.target===m) m.hidden=true; });
  }

  // ══════════ 連線設定頁 ══════════
  function settingsHTML() {
    const a = loadAssume();
    return `
    ${card("連線", "貼上通行碼、按「連線看真資料」，能連的頁面就會換成真的", `
      <div class="field"><span>目前看的是：<b id="envLabel">–</b> <button type="button" class="btn-ghost" id="toggleAdv" style="min-height:28px;padding:0 10px">換一台伺服器</button></span></div>
      <div class="field" id="advRow" hidden><span>伺服器網址（進階，平常不用動）</span><input id="apiBaseUrl" type="url" spellcheck="false"></div>
      <div class="field"><span>管理通行碼<small>（由蘇菲保管，跟她要一聲就好）</small></span><div class="token-wrap"><input id="adminToken" type="password" autocomplete="off" placeholder="貼上通行碼"><button type="button" class="eye-btn" id="eyeBtn">顯示</button></div></div>
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer"><input type="checkbox" id="rememberToken"><span>記住通行碼（只到關掉這個分頁，較安全）</span></label>
      <button type="button" class="primary" id="connectBtn">連線看真資料</button>
      <div class="kpi-sub" id="connectHint" style="margin-top:10px">連上後，安全警訊、用戶意見、系統健康等有真資料的頁面會換成真的；其餘暫用示範數據並標「示範」。</div>
    `)}
    ${card("訂閱試算假設", "填你的預期值，訂閱與成長頁的 MRR/LTV/CAC 可用這組即時試算（上線有真數字會自動接上）", `
      <div class="assume-grid">
        <label class="field"><span>Plus 月費 (NT$)</span><input type="number" id="aPlusPrice" value="${a.plusPrice}"></label>
        <label class="field"><span>Pro 月費 (NT$)</span><input type="number" id="aProPrice" value="${a.proPrice}"></label>
        <label class="field"><span>目前 Plus 訂閱數</span><input type="number" id="aPlusCount" value="${a.plusCount}"></label>
        <label class="field"><span>目前 Pro 訂閱數</span><input type="number" id="aProCount" value="${a.proCount}"></label>
        <label class="field"><span>本月新增付費</span><input type="number" id="aNewPaid" value="${a.newPaid}"></label>
        <label class="field"><span>當月行銷花費 (NT$)</span><input type="number" id="aMarketing" value="${a.marketing}"></label>
        <label class="field"><span>預估平均訂閱月數</span><input type="number" id="aLifeMonths" value="${a.lifeMonths}"></label>
      </div>
      <div id="assumeOut" class="kpi-sub" style="margin-top:12px"></div>
    `)}
    ${card("快速前往", "跟後台相關的其他頁面", `<div class="quick-links">
      <a href="/" target="_blank" rel="noopener">📱 App 本體</a>
      <a href="/selftest.html" target="_blank" rel="noopener">🧪 自動巡檢成績單</a>
      <a href="https://munea.net" target="_blank" rel="noopener">🌐 官網 munea.net</a>
      <a href="https://munea.net/privacy" target="_blank" rel="noopener">📄 隱私權政策</a>
    </div>`)}
    <details class="raw-panel card"><summary>🔧 工程資料（原始回應，平常不用打開）</summary><pre id="rawOut">{}</pre></details>`;
  }

  // ══════════ 連線 / 真資料 ══════════
  function initialBaseUrl(){ const s=localStorage.getItem(ADMIN_BASE_KEY); if(s) return s; if(location.protocol.startsWith("http")) return location.origin; return DEFAULT_LOCAL_API; }
  function envLabelFor(u){ if(/munea-brain-staging/.test(u))return "雲端試營運"; if(/127\.0\.0\.1|localhost/.test(u))return "這台電腦（本機）"; if(/run\.app/.test(u))return "雲端伺服器"; return u.replace(/^https?:\/\//,"")||"–"; }
  function setStatus(t,k){ const r=$("envRole"); if(r) r.textContent = state.connected? "已連線 · "+envLabelFor(localStorage.getItem(ADMIN_BASE_KEY)||"") : "尚未連線"; }

  async function postAdmin(base, token, path, body){
    const res = await fetch(base+path,{method:"POST",headers:{"Content-Type":"application/json; charset=utf-8","X-Munea-Admin-Token":token},body:JSON.stringify(body||{})});
    const txt = await res.text(); let p={}; try{ p=txt?JSON.parse(txt):{}; }catch(e){ p={ok:false,error:{code:"invalid_json"}}; }
    if(!res.ok||p.ok===false){ throw new Error((p.error&&p.error.code)||("http_"+res.status)); }
    return p;
  }

  async function connect(){
    const base=($("apiBaseUrl")?.value||initialBaseUrl()).trim().replace(/\/+$/,"");
    const token=($("adminToken")?.value||"").trim();
    if(!token){ setStatus("要先貼通行碼","error"); return; }
    localStorage.setItem(ADMIN_BASE_KEY, base);
    // 通行碼改存 sessionStorage（關掉分頁即消失），縮小外洩風險（沙利曼 P1）
    if($("rememberToken")?.checked) sessionStorage.setItem(ADMIN_TOKEN_KEY, token); else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    setStatus("讀取中…","");
    const EP=EP_LIST;
    const keys=Object.keys(EP);
    const results=await Promise.allSettled(keys.map((k)=>postAdmin(base,token,EP[k][0],EP[k][1])));
    const data={},errors={};
    results.forEach((r,i)=>{ if(r.status==="fulfilled")data[keys[i]]=r.value; else errors[keys[i]]=(r.reason&&r.reason.message)||"fail"; });
    state.data=data; state.errors=errors; state.connected=Object.keys(data).length>0;
    if($("rawOut")) $("rawOut").textContent=JSON.stringify({data,errors},null,2);
    const failed=Object.keys(errors).length;
    if(failed===0) setStatus("✅ 已連線","ok"); else if(failed===keys.length){ setStatus("❌ 連不上","error"); state.connected=false; } else setStatus("⚠ 部分讀不到","warn");
    applyLiveData();
    updateBanner(); renderSide(); renderPage(state.page);
  }

  // 把真資料覆蓋到示範數據上（只覆蓋有對應端點的）
  function applyLiveData(){
    if(!state.data) return;
    const d=state.data;
    // 北極星＋活躍（真）
    if(d.northStar){ const ns=d.northStar;
      if(ns.meaningfulCompanionDays!=null) S.overview.kpi[0].value=n(ns.meaningfulCompanionDays);
      if(ns.activePeople!=null){ S.overview.kpi[1].value=n(ns.activePeople); S.growth.kpi[2].value=n(ns.activePeople); }
      if(ns.voiceSessionSuccessRate!=null){ const pct=Math.round(ns.voiceSessionSuccessRate*100); S.overview.kpi[2].value=pct+"%"; S.overview.kpi[2].delta=pct>=95?"達標":"未達標"; S.overview.kpi[2].dir=pct>=95?"up":"down"; }
    }
    // 安全警示（真）
    if(d.safety){ const t=d.safety.totals||{}, rec=d.safety.recent||[];
      S.safety.kpi[0].value=String((t.byRiskLevel?Object.values(t.byRiskLevel).reduce((a,b)=>a+b,0):rec.length)||0);
      S.safety.kpi[2].value=String(rec.length);
      if(rec.length){ S.safety.queue = rec.slice(0,6).map((e)=>({ risk:(e.riskLevel||"留意"), tone:(String(e.riskLevel).match(/high|crit/i)?"bad":"warn"), title:(e.categories&&e.categories[0])||"安全訊號", desc:(e.summary||"聊天中偵測到需關注訊號，請真人確認。"), who:(e.personId||"用戶"), time:fmtTime(e.eventTime), src:"AI 安全網" })); }
      else S.safety.queue=[];
    }
    // 客服/意見（真）
    if(d.feedback){ const f=d.feedback, latest=f.latest||[];
      S.support.kpi[3].value=String((f.totals&&f.totals.praise)||latest.filter(x=>x.type==="praise").length||0);
      if(latest.length){ S.support.tickets=latest.slice(0,8).map((it)=>({ title:(it.text||"（無內容）").slice(0,40), who:(fbType(it.type))+" · App "+(it.appVersion||"?"), pri:(it.type==="bug"?"待處理":"回饋"), tone:(it.type==="bug"?"warn":"mute"), time:fmtTime(it.createdAt) })); }
      const praises=latest.filter(x=>x.type==="praise"&&x.text); if(praises.length) S.support.quotes=praises.slice(0,3).map((p)=>[`「${p.text}」`, "— 用戶回饋"]);
    }
    // 用戶名冊（真）
    if(d.accounts&&d.accounts.accounts&&d.accounts.accounts.length){ S.users.roster=d.accounts.accounts.slice(0,20).map((a)=>{ const p=a.primaryPerson||{},f=a.familyGroup||{},c=a.companion||{},m=a.familyMembers||{}; return [p.displayName||a.accountName||"用戶", f.name||"–", "–", c.displayName||"–", (m.count||0)+" 人", "活躍中", fmtTime(a.updatedAt||a.createdAt)]; }); }
    // 用量（真：每日通話分鐘）
    if(d.usage&&d.usage.daily&&d.usage.daily.length){ const last7=d.usage.daily.slice(-7); S.overview.callDaily=last7.map((x)=>[shortDate(x.date), Math.round(x.voiceMinutes+x.avatarMinutes)]); S.usage.weekCall=S.overview.callDaily.slice(); }
    // 訂閱營運聚合（真：新增訂閱/點數/轉換率，來自 /admin/subscription-metrics）
    if(d.subscriptionMetrics){ const sm=d.subscriptionMetrics;
      if(sm.newSubscriptions!=null) S.subscription.kpi[1].value=n(sm.newSubscriptions);
      if(sm.pointsPurchases!=null) S.subscription.kpi[2].value=n(sm.pointsPurchases)+" 筆";
      if(sm.freeToPaidConversion!=null){ const c=(sm.freeToPaidConversion*100).toFixed(1)+"%"; S.subscription.kpi[3].value=c; S.overview.kpi[3].value=c; }
      // MRR 還沒有聚合來源 → 誠實標「待接」
      S.subscription.kpi[0].value="待接"; S.subscription.kpi[0].sub="需目前有效訂閱聚合"; S.subscription.kpi[0].delta="";
    } else if(d.usage&&d.usage.eventCounts){ const ec=d.usage.eventCounts; const paid=ec.subscription_purchased||0, reg=ec.onboarding_completed||0; if(reg) S.subscription.kpi[3].value=((paid/reg*100).toFixed(1))+"%"; }
  }

  function fbType(t){ return {bug:"問題回報",idea:"功能許願",praise:"稱讚",nps:"打分數"}[t]||"意見"; }
  function fmtTime(v){ if(!v)return "–"; const d=new Date(v); if(isNaN(d))return String(v); try{ return new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);}catch(e){return String(v);} }
  function shortDate(iso){ const p=String(iso).split("-"); return p.length===3?`${+p[1]}/${+p[2]}`:iso; }

  // ══════════ 訂閱試算 ══════════
  const ASSUME_DEF={plusPrice:499,proPrice:999,plusCount:0,proCount:0,newPaid:0,marketing:0,lifeMonths:12};
  function loadAssume(){ try{ return {...ASSUME_DEF, ...JSON.parse(localStorage.getItem(ASSUME_KEY)||"{}")}; }catch(e){ return {...ASSUME_DEF}; } }
  function calcAssume(){
    const g=(id)=>Number($(id)?.value)||0;
    const a={plusPrice:g("aPlusPrice"),proPrice:g("aProPrice"),plusCount:g("aPlusCount"),proCount:g("aProCount"),newPaid:g("aNewPaid"),marketing:g("aMarketing"),lifeMonths:Math.max(1,g("aLifeMonths"))};
    localStorage.setItem(ASSUME_KEY,JSON.stringify(a));
    const paid=a.plusCount+a.proCount, mrr=a.plusCount*a.plusPrice+a.proCount*a.proPrice;
    const arpu=paid?mrr/paid:null, ltv=arpu!=null?arpu*a.lifeMonths:null, cac=a.newPaid?a.marketing/a.newPaid:null, ratio=(ltv!=null&&cac)?ltv/cac:null;
    if($("assumeOut")) $("assumeOut").innerHTML=`MRR <b>NT$${n(Math.round(mrr))}</b> · ARPU ${arpu!=null?"NT$"+n(Math.round(arpu)):"–"} · LTV ${ltv!=null?"NT$"+n(Math.round(ltv)):"–"} · CAC ${cac!=null?"NT$"+n(Math.round(cac)):"填新增付費+行銷花費"} · <b>LTV:CAC ${ratio!=null?ratio.toFixed(1)+":1"+(ratio>=3?" 🟢":ratio>=1?" 🟡":" 🔴"):"–"}</b>`;
  }

  // ══════════ 導覽 / 事件 ══════════
  function renderSide(){
    const badges={ safety:S.safety.kpi[0].value, support:S.support.kpi[0].value, system:"2" };
    $("sideNav").innerHTML = NAV.map((g)=>`<div class="nav-group"><div class="nav-group-label">${esc(g.group)}</div><div class="side-nav">${g.items.map((it)=>{
      const b= it.badge? `<span class="nav-badge">${esc(badges[it.badge]||"")}</span>`:"";
      return `<a href="#${it.id}" data-page="${it.id}">${icon(it.id)}<span class="nav-label">${esc(it.label)}</span>${b}</a>`;
    }).join("")}</div></div>`).join("");
    document.querySelectorAll("#sideNav a").forEach((a)=>a.classList.toggle("on",a.dataset.page===state.page));
  }

  function updateBanner(){ /* 示範橫幅已移除（正式串接） */ }

  function go(id){ if(!TITLE[id]) id="overview"; state.page=id; location.hash="#"+id; }

  function show(){
    const id = (location.hash||"#overview").slice(1);
    state.page = TITLE[id]?id:"overview";
    $("crumb").textContent = CRUMB[state.page]||"";
    $("pageTitle").textContent = TITLE[state.page]||"";
    document.querySelectorAll("#sideNav a").forEach((a)=>a.classList.toggle("on",a.dataset.page===state.page));
    updateBanner();
    renderPage(state.page);
  }

  function bindPageEvents(id){
    // hero CTA
    $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto)));
    // 篩選頁籤
    $("pageRoot").querySelectorAll("[data-tabs]").forEach((grp)=>grp.addEventListener("click",(e)=>{
      const b=e.target.closest("[data-tab]"); if(!b) return;
      state.tabs[grp.dataset.tabs]=b.dataset.tab; renderPage(state.page);
    }));
    // 查看用戶明細
    $("pageRoot").querySelectorAll("[data-user]").forEach((b)=>b.addEventListener("click",()=>openUserDetail(b.dataset.user)));
    // 名冊搜尋
    const us=$("userSearch"); if(us) us.addEventListener("input",()=>{
      const q=us.value.trim();
      $("pageRoot").querySelectorAll("table tbody tr").forEach((tr)=>{ tr.style.display = (!q || tr.innerText.indexOf(q)>-1) ? "" : "none"; });
    });
    if(id==="settings"){
      const base=initialBaseUrl();
      if($("apiBaseUrl")) $("apiBaseUrl").value=base;
      if($("envLabel")) $("envLabel").textContent=envLabelFor(base);
      const st=sessionStorage.getItem(ADMIN_TOKEN_KEY)||"";
      if(st&&$("adminToken")){ $("adminToken").value=st; $("rememberToken").checked=true; }
      $("connectBtn")?.addEventListener("click",connect);
      $("toggleAdv")?.addEventListener("click",()=>{ $("advRow").hidden=!$("advRow").hidden; });
      $("eyeBtn")?.addEventListener("click",()=>{ const f=$("adminToken"); const sh=f.type==="text"; f.type=sh?"password":"text"; $("eyeBtn").textContent=sh?"顯示":"隱藏"; });
      $("apiBaseUrl")?.addEventListener("input",()=>{ if($("envLabel"))$("envLabel").textContent=envLabelFor($("apiBaseUrl").value); });
      ["aPlusPrice","aProPrice","aPlusCount","aProCount","aNewPaid","aMarketing","aLifeMonths"].forEach((i)=>$(i)?.addEventListener("input",calcAssume));
      calcAssume();
      if(state.data&&$("rawOut")) $("rawOut").textContent=JSON.stringify({data:state.data,errors:state.errors},null,2);
    }
  }

  function enterDemo(){ state.connected=false; setStatus("示範模式","warn"); }

  function init(){
    if(window.MuneaVersion){} // 版本供未來顯示
    renderSide();
    window.addEventListener("hashchange",show);
    setStatus();
    show();
    // 記住通行碼就自動連（sessionStorage：僅本分頁）
    const st=sessionStorage.getItem(ADMIN_TOKEN_KEY);
    if(st){ // 需要 settings 的輸入存在才連；直接用存值連
      const base=initialBaseUrl();
      // 直接連（不需切到設定頁）
      (async()=>{ try{ const tmpToken=st; const EP=EP_LIST; const keys=Object.keys(EP); const rs=await Promise.allSettled(keys.map((k)=>postAdmin(base,tmpToken,EP[k][0],EP[k][1]))); const data={},errors={}; rs.forEach((r,i)=>{ if(r.status==="fulfilled")data[keys[i]]=r.value; else errors[keys[i]]="fail"; }); if(Object.keys(data).length){ state.data=data; state.errors=errors; state.connected=true; setStatus("✅ 已連線","ok"); applyLiveData(); updateBanner(); renderSide(); renderPage(state.page); } }catch(e){} })();
    }
  }
  document.addEventListener("DOMContentLoaded",init);
})();
