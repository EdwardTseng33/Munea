(function () {
  "use strict";

  // ══════════ 選單：只保留「有真資料源」的頁（上線就緒·無假數據） ══════════
  const NAV = [
    { group: "營運總覽", items: [
      { id: "overview", label: "總覽儀表板" },
      { id: "carePriority", label: "最需要關心", badge: "care" },
    ]},
    { group: "用戶與守護", items: [
      { id: "users", label: "用戶管理" },
      { id: "safety", label: "安全守護警示", badge: "safety" },
      { id: "medication", label: "用藥與回診" },
      { id: "familyHealth", label: "家庭圈健康度" },
      { id: "moodTrend", label: "心情趨勢" },
      { id: "bondDepth", label: "關係深度" },
    ]},
    { group: "營收", items: [
      { id: "subscription", label: "訂閱與點數" },
    ]},
    { group: "企業客戶", items: [
      { id: "enterpriseClients", label: "客戶列表", badge: "entOverdue" },
      { id: "enterpriseImport", label: "名單匯入" },
      { id: "enterprisePayments", label: "收款登記" },
      { id: "enterpriseBillingSettings", label: "開票與收款設定", badge: "entBillingMissing" },
    ]},
    { group: "服務與紀錄", items: [
      { id: "feedback", label: "用戶意見", badge: "feedback" },
      { id: "records", label: "系統紀錄" },
    ]},
  ];
  const CRUMB = {}, TITLE = {};
  NAV.forEach((g) => g.items.forEach((it) => { CRUMB[it.id] = g.group; TITLE[it.id] = it.label; }));
  // 單一公司明細不放側欄（跟「用戶明細」一樣靠列表列「查看」進入），但要能吃 hash 路由
  TITLE.enterpriseClientDetail = "企業客戶明細"; CRUMB.enterpriseClientDetail = "企業客戶";

  const ICON_PATHS = {
    overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M17 3.13a4 4 0 0 1 0 7.75"/>',
    safety: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    subscription: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/>',
    feedback: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    records: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    medication: '<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/>',
    familyHealth: '<path d="m3 9.5 9-7.5 9 7.5"/><path d="M5 8.5V21h14V8.5"/><path d="M9 21v-6h6v6"/>',
    moodTrend: '<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01M15 9h.01"/>',
    bondDepth: '<path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.29 1.51 4.04 3 5.5l7 7Z"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    carePriority: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    enterpriseClients: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    enterpriseImport: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    enterprisePayments: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    enterpriseBillingSettings: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/><path d="M6 12h.01M18 12h.01"/>',
  };
  function icon(id, cls){ return `<svg class="${cls||"nav-ico"}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[id]||""}</svg>`; }

  // ══════════ 狀態 ══════════
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
  const ADMIN_TOKEN_KEY = "munea.admin.token";
  const ASSUME_KEY = "munea.admin.assumptions";
  const DEFAULT_LOCAL_API = "http://127.0.0.1:8200";
  const REQUEST_TIMEOUT_MS = 15000;
  const ADMIN_DATA_META_SCHEMA = "munea.admin-data-meta.v1";
  const KNOWN_ADMIN_HOSTS = ["munea-brain-staging-491603544409.asia-east1.run.app"];
  // 相容目前已部署的薄門；它不是管理憑證。部署端可在載入本檔前設定
  // window.MUNEA_ADMIN_APP_KEY，下一步即可把這個相容值從靜態資產移除。
  const LEGACY_APP_KEY = "mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5";
  const state = { data: null, errors: {}, connected: false, loading: false, page: "overview", tabs: {}, base: "", token: "" };

  const EP_LIST = {
    northStar: ["/admin/north-star", { days: 30 }],
    usage: ["/admin/usage", { days: 30 }],
    accounts: ["/admin/accounts", { limit: 50 }],
    subscriptionMetrics: ["/admin/subscription-metrics", { days: 30 }],
    credits: ["/admin/credits", { limit: 25 }],
    feedback: ["/admin/feedback", { limit: 20 }],
    safety: ["/admin/safety-events", { days: 30, limit: 30 }],
    privacy: ["/admin/privacy-requests", { limit: 20 }],
    summaries: ["/admin/conversation-summaries", { limit: 20 }],
    audit: ["/admin/audit-events", { limit: 20 }],
    medication: ["/admin/medication-adherence", { days: 30, limit: 50 }],
    familyHealth: ["/admin/family-health", { days: 30, limit: 50 }],
    moodTrend: ["/admin/mood-trend", { days: 30, limit: 50 }],
    bondDepth: ["/admin/bond-depth", { days: 30, limit: 50, stuckDays: 14 }],
  };

  const CHART = { teal: "#3AA8A0", coral: "#D98841", gold: "#E0B354", prev: "#C9C0B0", grid: "#ECE6DA", ink: "#3A352E", muted: "#5A6963" };
  const cc = { teal: CHART.teal, coral: CHART.coral, gold: CHART.gold, prev: CHART.prev };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  const n = (v) => (v==null||v===""||isNaN(v))?"–":Number(v).toLocaleString("en-US");
  function storageGet(store,key){ try{ return store.getItem(key)||""; }catch(e){ return ""; } }
  function storageSet(store,key,value){ try{ store.setItem(key,value); return true; }catch(e){ return false; } }
  function storageRemove(store,key){ try{ store.removeItem(key); }catch(e){} }
  function runtimeAppKey(){ return String(window.MUNEA_ADMIN_APP_KEY||LEGACY_APP_KEY||"").trim(); }
  function requestHeaders(extra){
    const headers=Object.assign({},extra||{}),key=runtimeAppKey();
    if(key) headers["X-Munea-Key"]=key;
    return headers;
  }
  function normalizeAdminBaseUrl(raw){
    let url;
    try{ url=new URL(String(raw||""),location.href); }catch(e){ throw new Error("invalid_admin_url"); }
    if(!/^https?:$/.test(url.protocol)) throw new Error("invalid_admin_url");
    const local=/^(localhost|127\.0\.0\.1|\[?::1\]?)$/i.test(url.hostname);
    if(url.protocol!=="https:"&&!local) throw new Error("insecure_admin_url");
    const injected=Array.isArray(window.MUNEA_ADMIN_ALLOWED_HOSTS)?window.MUNEA_ADMIN_ALLOWED_HOSTS:[];
    const allowed=local||url.origin===location.origin||KNOWN_ADMIN_HOSTS.concat(injected).includes(url.hostname);
    if(!allowed) throw new Error("untrusted_admin_host");
    return url.origin;
  }

  // 真資料取用（沒連線/沒資料一律空，不編）
  const D = () => state.data || {};
  const northStar = () => D().northStar || {};
  const usage = () => D().usage || {};
  const subM = () => D().subscriptionMetrics || {};
  const creditsSummary = () => D().credits || {};
  const daily = () => usage().daily || [];
  const ecount = () => usage().eventCounts || {};
  const medication = () => D().medication || {};
  const familyHealth = () => D().familyHealth || {};
  const moodTrend = () => D().moodTrend || {};
  const bondDepth = () => D().bondDepth || {};
  // 企業客戶（B2B 席次）：各頁進場才現查，不掛進 loadAll 的 EP_LIST（那張表跟
  // scripts/admin-smoke.ps1 有 1:1 契約測試，後端路由還沒接好前先不碰）
  function entClients(){ return ((state.tabs.entClientsList && state.tabs.entClientsList.data) || {}).clients || []; }
  function entInvoices(){ return ((state.tabs.entInvoicesList && state.tabs.entInvoicesList.data) || {}).invoices || []; }

  function missingDataMeta(endpointKey){
    return {schema:ADMIN_DATA_META_SCHEMA,metricVersion:"unknown",generatedAt:null,dataAsOf:null,status:"unverified",degraded:true,degradationReasons:["metadata_missing"],freshness:{status:"unknown",reason:"metadata_missing"},sources:[],endpointKey};
  }
  function normalizeDataMeta(payload,endpointKey){
    const meta=payload&&payload.meta;
    if(!meta||meta.schema!==ADMIN_DATA_META_SCHEMA) return missingDataMeta(endpointKey);
    return Object.assign(missingDataMeta(endpointKey),meta,{endpointKey});
  }
  function dataQualitySummary(){
    const entries=Object.entries(state.data||{}),metas=entries.map(([key,payload])=>normalizeDataMeta(payload,key));
    const degraded=metas.filter((meta)=>meta.degraded===true);
    const missing=metas.filter((meta)=>(meta.degradationReasons||[]).includes("metadata_missing"));
    const empty=metas.filter((meta)=>meta.status==="empty");
    const timestamps=metas.map((meta)=>meta.dataAsOf).filter(Boolean).sort();
    return {total:metas.length,degraded:degraded.length,missing:missing.length,empty:empty.length,dataAsOf:timestamps.length?timestamps[timestamps.length-1]:null};
  }

  function fmtMoney(v){ return (v==null||isNaN(v))?"–":"NT$"+Math.round(Number(v)).toLocaleString("en-US"); }
  function pct(v){ return (v==null||isNaN(v))?"–":Math.round(Number(v)*100)+"%"; }
  function shortDate(iso){ const p=String(iso).split("-"); return p.length===3?`${+p[1]}/${+p[2]}`:iso; }
  function fmtTime(v){ if(!v)return "–"; const d=new Date(v); if(isNaN(d))return String(v); try{ return new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);}catch(e){return String(v);} }
  function fmtDate(v){ if(!v)return "–"; const d=new Date(v); if(isNaN(d))return String(v); try{ return new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",year:"numeric",month:"numeric",day:"numeric"}).format(d);}catch(e){return String(v);} }
  function zh(map,v,f){ if(v==null||v==="")return f||"–"; return map[String(v).toLowerCase()]||String(v); }
  const RISK_ZH = { crisis:"🔴 危機", critical:"🔴 危機", high:"🔴 高風險", medium:"🟡 中風險", moderate:"🟡 中風險", low:"🟢 低風險", none:"低" };
  const FB_ZH = { bug:"問題回報", idea:"功能許願", praise:"稱讚", nps:"打分數" };
  const FB_TONE = { bug:"warn", idea:"gold", praise:"ok", nps:"mute" };
  const PV_ZH = { account_deletion:"刪除帳號", deletion:"刪除帳號", export:"資料副本", data_export:"資料副本", correction:"資料更正" };
  const ST_ZH = { pending:"待處理", open:"待處理", received:"已收到", processing:"處理中", done:"已完成", completed:"已完成", closed:"已結案" };
  const CREDIT_ZH = { subscription_monthly_allowance:"每月贈點", credit_grant:"發放點數", credit_consume:"使用點數", free_signup_voice_avatar_trial:"新用戶體驗贈點", apple_purchase:"加購點數", apple_purchase_refunded:"加購退款", apple_refund_reversed:"退款回沖", call_consume:"通話扣點" };

  // ══════════ 元件 ══════════
  function kpiRow(items){
    return `<div class="kpi-row">${items.map((k,i)=>`
      <div class="kpi ${i===0&&k.star?(k.tone==="alert"?"kpi-accent-alert":"kpi-accent"):""}">
        <div class="kpi-top"><span class="kpi-label">${esc(k.label)}${k.info?` <span class="kpi-info" title="${esc(k.info)}">ⓘ</span>`:""}</span></div>
        <div class="kpi-value">${esc(k.value)}${k.unit?`<span class="unit">${esc(k.unit)}</span>`:""}</div>
        ${k.sub?`<div class="kpi-sub">${esc(k.sub)}</div>`:""}
      </div>`).join("")}</div>`;
  }
  function card(title, note, body, headRight){
    return `<div class="card"><div class="card-head"><div><h3>${esc(title)}</h3>${note?`<div class="card-note">${esc(note)}</div>`:""}</div>${headRight||""}</div>${body}</div>`;
  }
  function principle(text){ return `<div class="principle">${text.indexOf("<")>-1?text:esc(text)}</div>`; }
  function emptyBox(text){ return `<div class="empty-note">${esc(text)}</div>`; }
  function chartMount(id){ return `<div class="chart-box" id="${id}"></div>`; }
  const pending = [];

  // ══════════ 圖表（純 SVG） ══════════
  const NS = "http://www.w3.org/2000/svg";
  function svg(tag,a){ const e=document.createElementNS(NS,tag); for(const k in a) e.setAttribute(k,a[k]); return e; }
  function niceMax(v){ if(!v||v<=0) return 4; const raw=v*1.12, mag=Math.pow(10,Math.floor(Math.log10(raw))); for(const m of [1,2,2.5,4,5,8,10]) if(m*mag>=raw) return m*mag; return 10*mag; }
  function tip(html,x,y){ const t=$("chartTip"); t.innerHTML=html; t.hidden=false; const r=t.getBoundingClientRect(); let px=x+14,py=y+14; if(px+r.width>innerWidth-8)px=x-r.width-14; if(py+r.height>innerHeight-8)py=y-r.height-14; t.style.left=px+"px"; t.style.top=py+"px"; }
  function hideTip(){ $("chartTip").hidden=true; }
  function allZero(series){ return series.every((s)=>s.values.every((v)=>!v)); }

  function columnChart(box, labels, series, opts){
    opts=opts||{};
    if(!labels.length || allZero(series)){ box.innerHTML=emptyBox(opts.empty||"還沒有資料——有用戶互動後就會長出來。"); return; }
    const W=760,H=190,L=44,R=14,T=14,B=28, pw=W-L-R, ph=H-T-B;
    const max=niceMax(Math.max(1,...series.flatMap((s)=>s.values))), y=(v)=>T+ph-(v/max)*ph;
    const chartLabel=series.map((se)=>se.name).join("、")+`，${labels.length} 個期間`;
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":chartLabel});
    for(let t=0;t<=4;t++){ const val=max/4*t,gy=y(val); s.appendChild(svg("line",{x1:L,x2:W-R,y1:gy,y2:gy,stroke:CHART.grid,"stroke-width":1})); const tx=svg("text",{x:L-8,y:gy+4,"text-anchor":"end","font-size":11,fill:CHART.muted}); tx.textContent=n(Math.round(val)); s.appendChild(tx); }
    const band=pw/labels.length, groupW=Math.min(band*0.62,series.length*20+(series.length-1)*4), barW=Math.min(22,(groupW-(series.length-1)*4)/series.length);
    const lstep=Math.max(1,Math.ceil(labels.length/8));
    labels.forEach((lb,i)=>{ const cx=L+band*i+band/2,startX=cx-groupW/2;
      series.forEach((se,si)=>{ const v=se.values[i],top=y(v),x=startX+si*(barW+4),h=Math.max(0,T+ph-top);
        const path=svg("path",{d:h<=0.5?`M ${x} ${T+ph} h ${barW}`:`M ${x} ${T+ph} V ${top+4} Q ${x} ${top} ${x+4} ${top} H ${x+barW-4} Q ${x+barW} ${top} ${x+barW} ${top+4} V ${T+ph} Z`,fill:se.color});
        path.addEventListener("mousemove",(e)=>tip(`<div>${esc(lb)}${series.length>1?" · "+esc(se.name):""}</div><b>${n(v)}</b>${opts.unit?" "+opts.unit:""}`,e.clientX,e.clientY));
        path.addEventListener("mouseleave",hideTip); s.appendChild(path); });
      if(i%lstep===0||(i===labels.length-1&&(labels.length-1)%lstep>=Math.ceil(lstep/2))){ const tl=svg("text",{x:cx,y:H-8,"text-anchor":"middle","font-size":11,fill:CHART.muted}); tl.textContent=lb; s.appendChild(tl); } });
    box.innerHTML=""; box.appendChild(s);
    if(series.length>1){ const lg=document.createElement("div"); lg.className="legend"; lg.innerHTML=series.map((se)=>`<span class="key"><span class="swatch" style="background:${se.color}"></span>${esc(se.name)}</span>`).join(""); box.appendChild(lg); }
  }

  function lineChart(box, labels, series, opts){
    opts=opts||{};
    if(!labels.length || allZero(series)){ box.innerHTML=emptyBox(opts.empty||"還沒有資料。"); return; }
    const W=760,H=180,L=44,R=16,T=14,B=26, pw=W-L-R, ph=H-T-B;
    const maxV=opts.maxY||niceMax(Math.max(1,...series.flatMap((s)=>s.values))), minV=opts.minY||0;
    const nP=labels.length, x=(i)=>L+(nP<=1?pw/2:(i/(nP-1))*pw), y=(v)=>T+ph-((v-minV)/(maxV-minV))*ph;
    const chartLabel=series.map((se)=>se.name).join("、")+`，${labels.length} 個期間`;
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img","aria-label":chartLabel});
    for(let t=0;t<=4;t++){ const val=minV+(maxV-minV)/4*t,gy=y(val); s.appendChild(svg("line",{x1:L,x2:W-R,y1:gy,y2:gy,stroke:CHART.grid,"stroke-width":1})); const tx=svg("text",{x:L-8,y:gy+4,"text-anchor":"end","font-size":11,fill:CHART.muted}); tx.textContent=n(Math.round(val)); s.appendChild(tx); }
    const step=Math.max(1,Math.ceil(nP/7));
    for(let i=0;i<nP;i+=step){ const tx=svg("text",{x:x(i),y:H-6,"text-anchor":"middle","font-size":11,fill:CHART.muted}); tx.textContent=labels[i]; s.appendChild(tx); }
    series.forEach((se)=>{ const pts=se.values.map((v,i)=>`${x(i)},${y(v)}`).join(" ");
      if(se.wash) s.appendChild(svg("polygon",{points:`${L},${T+ph} ${pts} ${x(nP-1)},${T+ph}`,fill:se.color,opacity:.1}));
      s.appendChild(svg("polyline",{points:pts,fill:"none",stroke:se.color,"stroke-width":2,"stroke-linejoin":"round","stroke-linecap":"round"}));
      const lv=se.values[nP-1]; s.appendChild(svg("circle",{cx:x(nP-1),cy:y(lv),r:4.5,fill:se.color,stroke:"#fff","stroke-width":2})); });
    const overlay=svg("rect",{x:L,y:T,width:pw,height:ph,fill:"transparent"});
    const cross=svg("line",{x1:0,x2:0,y1:T,y2:T+ph,stroke:CHART.muted,"stroke-width":1,opacity:0}); s.appendChild(cross);
    const dots=series.map((se)=>{ const d=svg("circle",{r:5,fill:se.color,stroke:"#fff","stroke-width":2,opacity:0}); s.appendChild(d); return d; });
    overlay.addEventListener("mousemove",(e)=>{ const r=s.getBoundingClientRect(); const px=(e.clientX-r.left)/r.width*W; const i=Math.max(0,Math.min(nP-1,Math.round((px-L)/pw*(nP-1)))); cross.setAttribute("x1",x(i)); cross.setAttribute("x2",x(i)); cross.setAttribute("opacity",.4); const rows=series.map((se,si)=>{dots[si].setAttribute("cx",x(i));dots[si].setAttribute("cy",y(se.values[i]));dots[si].setAttribute("opacity",1);return `<span style="color:#c9d6cf">${esc(se.name)}</span> <b>${se.values[i]}</b>`;}); tip(`<div>${esc(labels[i])}</div>${rows.join("<br>")}`,e.clientX,e.clientY); });
    overlay.addEventListener("mouseleave",()=>{ cross.setAttribute("opacity",0); dots.forEach((d)=>d.setAttribute("opacity",0)); hideTip(); });
    s.appendChild(overlay); box.innerHTML=""; box.appendChild(s);
    if(series.length>1){ const lg=document.createElement("div"); lg.className="legend"; lg.innerHTML=series.map((se)=>`<span class="key"><span class="swatch" style="background:${se.color}"></span>${esc(se.name)}</span>`).join(""); box.appendChild(lg); }
  }

  // ══════════ 頁面渲染（只吃真資料） ══════════
  function connectionNoticeHTML(){
    const failed=Object.keys(state.errors||{});
    if(!failed.length) return "";
    const paths=failed.map((key)=>EP_LIST[key]?.[0]||key).join("、");
    if(state.connected){
      return `<div class="ops-notice warn" role="status"><strong>部分資料暫時讀不到</strong>${esc(paths)}。畫面保留已成功載入的資料，請稍後重新整理。</div>`;
    }
    const first=state.errors[failed[0]];
    return `<div class="ops-notice error" role="alert"><strong>營運資料載入失敗</strong>${esc(explainErr(first))}。請稍後重試；若一直失敗請重新登入。 <button type="button" class="btn-ghost" data-retry>重新整理</button> <button type="button" class="btn-ghost" data-relogin>重新登入</button></div>`;
  }
  function dataQualityNoticeHTML(){
    if(!state.connected||state.page!=="overview") return "";
    const q=dataQualitySummary();
    const asof=q.dataAsOf?`資料更新到 ${esc(fmtTime(q.dataAsOf))}`:"資料更新時間待確認";
    if(q.missing){
      return `<div class="ops-notice warn" role="status"><strong>部分數字還沒標明來源</strong>有 ${q.missing} 個區塊還沒回報數字是從哪來、算到哪一刻；可以先看，但別當成已確認的最新值。</div>`;
    }
    if(q.degraded){
      return `<div class="ops-notice warn" role="status"><strong>部分數字目前是暫代資料</strong>有 ${q.degraded} 個區塊用的是測試／備援資料，顯示 0 不代表真的是 0。${q.dataAsOf?` ${asof}。`:""}</div>`;
    }
    return ""; // 一切正常時不再出橫幅——右上角「資料更新到 X」每頁都看得到，不重複講
  }
  function renderPage(id){
    pending.length=0;
    let html="";
    if (id==="overview") html=renderOverview();
    else if (id==="carePriority") html=renderCarePriority();
    else if (id==="users") html=renderUsers();
    else if (id==="safety") html=renderSafety();
    else if (id==="medication") html=renderMedication();
    else if (id==="familyHealth") html=renderFamilyHealth();
    else if (id==="moodTrend") html=renderMoodTrend();
    else if (id==="bondDepth") html=renderBondDepth();
    else if (id==="subscription") html=renderSubscription();
    else if (id==="feedback") html=renderFeedback();
    else if (id==="records") html=renderRecords();
    else if (id==="enterpriseClients") html=renderEnterpriseClients();
    else if (id==="enterpriseClientDetail") html=renderEnterpriseClientDetail();
    else if (id==="enterpriseImport") html=renderEnterpriseImport();
    else if (id==="enterprisePayments") html=renderEnterprisePayments();
    else if (id==="enterpriseBillingSettings") html=renderEnterpriseBillingSettings();
    $("pageRoot").innerHTML=connectionNoticeHTML()+dataQualityNoticeHTML()+html;
    pending.forEach((fn)=>{ try{ fn(); }catch(e){ console.warn("chart",e); } });
    bindPageEvents(id);
  }

  function renderOverview(){
    const ns=northStar(), u=usage(), sm=subM(), dl=daily(), ec=ecount();
    const win=u.windowDays||30;
    const vr=ns.voiceSessionSuccessRate;
    let html="";
    html+=kpiRow([
      { label:"北極星 · 有意義陪伴天數", value:n(ns.meaningfulCompanionDays), sub:`近 ${win} 天 · 真的有陪上話的「人×天」`, star:true, info:"某位長輩某天真的有跟沐寧互動（滿60秒通話、完成視訊臉、做到提醒、家人傳話）就算 1，去重加總。只點開看一眼不算。" },
      { label:"活躍人數", value:n(ns.activePeople), sub:`近 ${win} 天有真互動的人` },
      { label:"語音接通成功率", value:vr==null?"–":pct(vr), sub:"撥了有講到話的比例 · 目標 ≥95%" },
      { label:"本月新增訂閱", value:n(sm.newSubscriptions), sub:"付費訂閱新增（近30天）" },
    ]);
    html+=`<div class="grid-2">`;
    html+=card("每日有意義互動", `近 ${win} 天`, chartMount("ov-mean"));
    html+=card("每日通話與視訊臉（分鐘）", `近 ${win} 天 · 兩條線`, chartMount("ov-min"));
    html+=`</div>`;
    html+=`<div class="stat-tiles">`;
    html+=card("提醒完成", "吃藥／回診有做到", `<div class="kpi-value">${n(ns.routineCompletions)}</div><div class="kpi-sub">近 ${win} 天次數</div>`);
    html+=card("家人互動", "家庭圈傳話、查看", `<div class="kpi-value">${n(ns.familyInteractions)}</div><div class="kpi-sub">近 ${win} 天次數</div>`);
    html+=card("互動總數", "所有互動加總", `<div class="kpi-value">${n((u.totals||{}).events)}</div><div class="kpi-sub">近 ${win} 天</div>`);
    html+=`</div>`;
    const labels=dl.map((d)=>shortDate(d.date));
    pending.push(()=>columnChart($("ov-mean"), labels, [{name:"有意義互動",color:cc.teal,values:dl.map((d)=>Math.round(d.meaningfulEvents||0))}]));
    pending.push(()=>lineChart($("ov-min"), labels, [
      {name:"通話分鐘",color:cc.teal,values:dl.map((d)=>Math.round(d.voiceMinutes||0))},
      {name:"視訊臉分鐘",color:cc.coral,values:dl.map((d)=>Math.round(d.avatarMinutes||0))},
    ]));
    return html;
  }

  const AV_TINTS=[["var(--coral-soft)","var(--coral-d)"],["var(--mint)","var(--teal-dd)"],["var(--gold-soft)","#9A7B24"],["#E7E9F2","#5A6B8C"],["#F1E4EC","#9C5B84"]];
  const REL_ZH={ self:"主要使用者", primary_user:"主要使用者", elder:"長輩", senior:"長輩", child:"子女", daughter:"女兒", son:"兒子", family:"家人", caregiver:"照顧者" };
  function planPill(p){ const m={ pro:["pill pro","Pro"], plus:["pill ok","Plus"], free:["pill mute","免費"] }; const x=m[p]||m.free; return `<span class="${x[0]}">${x[1]}</span>`; }
  function statusPill(s){ const m={ on:["ok","活躍中"], idle:["warn","低度使用"], off:["mute","離線"], alert:["bad","守護中"] }; const x=m[s]||m.off; return `<span class="pill ${x[0]}"><span class="sdot"></span>${x[1]}</span>`; }
  function usageCell(u){ u=u||{}; const mins=Math.round(u.totalMinutes||0); if(!mins) return `<span class="muted">—</span>`; const h=Math.min(22,Math.max(6,mins/6)); return `<div class="use-cell"><span class="mini-bars"><i style="height:${Math.round(h*0.5)}px"></i><i style="height:${Math.round(h*0.78)}px"></i><i style="height:${Math.round(h)}px"></i></span><b class="num">${n(mins)}</b><span class="muted small">分</span></div>`; }

  // ══════════ 最需要關心：把各頁的風險訊號合成一張名單（純前端彙整，不另打後端）══════════
  const CARE_LEVELS = [
    { min: 60, cls: "bad",  label: "要立刻聯絡" },
    { min: 30, cls: "warn", label: "這週要關心" },
    { min: 1,  cls: "mute", label: "留意就好" },
  ];
  function careLevel(score){ return CARE_LEVELS.find((l)=>score>=l.min)||CARE_LEVELS[CARE_LEVELS.length-1]; }
  const looksLikeId = (v) => /^[0-9a-f]{8}-[0-9a-f]{4}/i.test(String(v||"")) || String(v||"").length>=32;

  function carePriorityRows(){
    const idx=new Map(); let unnamedAlerts=0;
    const add=(name,family,score,reason,lastAt)=>{
      const key=String(name||"").trim(); if(!key) return;
      let r=idx.get(key);
      if(!r){ r={name:key,family:family||"",score:0,reasons:[],lastAt:lastAt||null}; idx.set(key,r); }
      if(family&&!r.family) r.family=family;
      if(lastAt&&(!r.lastAt||String(lastAt)>String(r.lastAt))) r.lastAt=lastAt;
      r.score+=score; r.reasons.push(reason);
    };
    ((D().safety||{}).recent||[]).forEach((e)=>{
      const nm=e.displayName||e.personName||e.personId;
      if(!nm||looksLikeId(nm)){ unnamedAlerts++; return; }
      const s=String(e.riskLevel||"");
      if(/high|crisis|crit/i.test(s)) add(nm,"",40,"安全警示・高風險",e.eventTime);
      else if(/med|mod/i.test(s)) add(nm,"",20,"安全警示・中風險",e.eventTime);
    });
    ((D().familyHealth||{}).unwatchedList||[]).forEach((u)=>add(u.elderName,u.familyName,25,"沒人顧",u.lastFamilyActionAt));
    ((D().medication||{}).people||[]).forEach((p)=>{
      if((p.missedStreak||0)>=3) add(p.displayName,"",20,`連續漏服 ${n(p.missedStreak)} 天`,null);
      else if(p.adherenceRate!=null&&p.adherenceRate<0.6) add(p.displayName,"",15,`用藥只做到 ${Math.round(p.adherenceRate*100)}%`,null);
    });
    ((D().moodTrend||{}).watchlist||[]).forEach((w)=>{
      if((w.lowStreak||0)>=3) add(w.displayName,"",20,`連續低落 ${n(w.lowStreak)} 天`,w.lastSignalAt);
      else if((w.lowCount||0)>=3) add(w.displayName,"",10,`近 7 天低落 ${n(w.lowCount)} 次`,w.lastSignalAt);
    });
    ((D().bondDepth||{}).stuckList||[]).forEach((b)=>add(b.displayName,b.familyName,10,`用了 ${n(b.daysSinceJoin)} 天還沒熟起來`,b.lastTalkAt));
    ((D().accounts||{}).accounts||[]).forEach((a)=>{
      const nm=(a.primaryPerson||{}).displayName||a.accountName, fam=(a.familyGroup||{}).name||"", u=a.usage||{};
      if((a.status||"off")==="idle") add(nm,fam,15,"7 天以上沒通話",u.lastActiveAt);
      if(Number(a.points||0)<20) add(nm,fam,5,`點數只剩 ${n(a.points||0)} 點`,u.lastActiveAt);
    });
    const rows=[...idx.values()].sort((x,y)=>y.score-x.score||String(x.name).localeCompare(String(y.name)));
    return { rows, unnamedAlerts };
  }

  function renderCarePriority(){
    const r0=carePriorityRows(), rows=r0.rows;
    const urgent=rows.filter((r)=>r.score>=60).length, soon=rows.filter((r)=>r.score>=30&&r.score<60).length;
    let html=kpiRow([
      { label:"要立刻聯絡", value:n(urgent), sub:"警訊最多、今天就該打", star:true, tone:"alert", info:"多個警訊同時出現（60 分以上）" },
      { label:"這週要關心", value:n(soon), sub:"還不急、但別放著" },
      { label:"名單上共", value:n(rows.length), sub:"有任何一項警訊的長輩" },
      { label:"查不到姓名的警示", value:n(r0.unnamedAlerts), sub:r0.unnamedAlerts?"這些沒併進名單":"沒有" },
    ]);
    html+=principle("這張名單把「安全警示、沒人顧、用藥漏服、心情低落、關係沒建立起來、太久沒通話、點數見底」合起來看。分數只是排序用——真正要看的是「為什麼上榜」那一欄。系統不做醫療判讀，名單一律需要真人確認後處理。");
    if(!rows.length){
      html+=card("最需要關心的長輩", "把各項警訊合成一張名單", emptyBox("目前沒有人亮起警訊——很好。"));
      return html;
    }
    html+=card("最需要關心的長輩", `共 ${rows.length} 位 · 越上面越該先聯絡`, tableHTML(["長輩","家庭","程度","為什麼上榜","最近動靜"], rows.slice(0,30).map((r)=>{
      const lv=careLevel(r.score);
      return [
        `<b>${esc(r.name)}</b>`,
        esc(r.family||"–"),
        `<span class="pill ${lv.cls}"><span class="sdot"></span>${esc(lv.label)}</span>`,
        `<div class="tag-row">${r.reasons.map((x)=>`<span class="pill mute">${esc(x)}</span>`).join("")}</div>`,
        `<span class="muted small">${esc(fmtTime(r.lastAt))}</span>`,
      ];
    })));
    return html;
  }

  function renderUsers(){
    const accts=(D().accounts||{}).accounts||[];
    const safety=D().safety||{}, escalations=(safety.totals||{}).requiresHumanEscalation||0;
    const single=accts.length===1;
    const stOf=(a)=> (single&&escalations>0)?"alert":(a.status||"off");
    const people=accts.reduce((s,a)=>s+((a.familyMembers||{}).count||0),0);
    const sts=accts.map(stOf), activeC=sts.filter(s=>s==="on").length, idleC=sts.filter(s=>s==="idle").length, guardC=sts.filter(s=>s==="alert").length;
    let html=kpiRow([
      { label:"總用戶", star:true, value:n(accts.length), sub:`家庭圈 ${accts.length} · 成員 ${people} 人` },
      { label:"今日活躍", value:n(activeC), sub:accts.length?`活躍率 ${pct(activeC/accts.length)}`:"–", info:"近 3 天內有真互動的帳號" },
      { label:"低度使用", value:n(idleC), sub:"7 天以上沒通話", info:"需要關懷的沉睡帳號" },
      { label:"守護中", value:n(guardC), sub:"安全警示待處理", info:"有安全守護警示、建議優先確認" },
    ]);
    if(!accts.length){
      html+=card("用戶與家庭圈名冊", "現在有哪些人／家庭在用沐寧", emptyBox("還沒有帳號——正式開放註冊後，這裡會列出每一家。"));
      return html;
    }
    const filt=state.tabs.userFilter||"all", q=(state.tabs.userSearch||"").toLowerCase();
    const planC={free:0,plus:0,pro:0}; accts.forEach((a)=>{ const p=a.plan||"free"; planC[p]=(planC[p]||0)+1; });
    const passFilter=(a)=>{ if(["on","idle","alert"].includes(filt)) return stOf(a)===filt; if(["free","plus","pro"].includes(filt)) return (a.plan||"free")===filt; return true; };
    const rows=accts.filter((a)=>{ if(!passFilter(a))return false; if(!q)return true; const p=a.primaryPerson||{},f=a.familyGroup||{}; return ((p.displayName||a.accountName||"")+" "+(f.name||"")).toLowerCase().indexOf(q)>-1; });
    const chip=(id,label,cnt)=>`<button type="button" class="chip-filter${filt===id?" on":""}" data-ufilter="${id}" aria-pressed="${filt===id?"true":"false"}">${esc(label)} <span class="c">${cnt}</span></button>`;
    const tools=`<div class="tbl-tools">${chip("all","全部",accts.length)}${chip("on","活躍中",activeC)}${chip("idle","低度使用",idleC)}${chip("alert","守護中",guardC)}<span class="chip-sep"></span>${chip("free","免費",planC.free||0)}${chip("plus","Plus",planC.plus||0)}${chip("pro","Pro",planC.pro||0)}<span class="chip-spring"></span><input class="tbl-search" id="userSearch" type="search" aria-label="搜尋用戶名字或家庭" placeholder="搜尋名字或家庭"></div>`;
    const trows=rows.map((a)=>{ const idx=accts.indexOf(a); const p=a.primaryPerson||{},f=a.familyGroup||{},c=a.companion||{},m=a.familyMembers||{},u=a.usage||{};
      const nm=p.displayName||a.accountName||"–", initial=(String(nm).trim()[0]||"家");
      const tint=AV_TINTS[Math.abs(String(nm).split("").reduce((h,ch)=>((h<<5)-h+ch.charCodeAt(0))|0,0))%AV_TINTS.length];
      const sub=REL_ZH[String(p.relationship||"").toLowerCase()]||"成員";
      return [
        `<div class="u-cell"><span class="u-av" style="background:${tint[0]};color:${tint[1]}">${esc(initial)}</span><div class="u-meta"><div class="u-nm">${esc(nm)}</div><div class="u-sub">${esc(sub)}</div></div></div>`,
        `<span class="u-fam">${esc(f.name||"–")}</span><span class="muted small"> · ${n(m.count||0)}人</span>`,
        planPill(a.plan||"free"),
        `<span class="pts-cell"><b class="num">${n(a.points||0)}</b><span class="muted small">點</span></span>`,
        esc(c.displayName||c.templateId||"–"),
        usageCell(u),
        statusPill(stOf(a)),
        `<span class="muted small">${esc(fmtTime(u.lastActiveAt||a.updatedAt||a.createdAt))}</span>`,
        `<button type="button" class="row-act" data-acct="${idx}" aria-label="查看 ${esc(nm)} 的用戶明細">查看<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>`,
      ];
    });
    html+=`<div class="card tbl-card"><div class="card-head"><div><h3>用戶與家庭圈名冊</h3><div class="card-note">共 ${accts.length} 戶 · 點右側看單一用戶${single?"（試營運鎖定一戶）":""}</div></div></div>${tools}${tableHTML(["用戶","家庭","方案","持有點數","陪伴角色","使用量","狀態","最近活躍",""], trows)}</div>`;
    return html;
  }

  function renderSafety(){
    const s=D().safety||{}, t=s.totals||{}, rec=s.recent||[];
    const total=t.byRiskLevel?Object.values(t.byRiskLevel).reduce((a,b)=>a+b,0):rec.length;
    let html=kpiRow([
      { label:"需人工跟進", value:n(t.requiresHumanEscalation||0), sub:"建議 30 分內確認", star:true, tone:"alert" },
      { label:"近 30 天警訊", value:n(total), sub:"所有風險等級加總" },
      { label:"高風險", value:n((t.byRiskLevel||{}).high||(t.byRiskLevel||{}).crisis||0), sub:"最需優先看" },
      { label:"低風險", value:n((t.byRiskLevel||{}).low||0), sub:"情緒低落等" },
    ]);
    html+=principle("守護原則：沐寧偵測到不對勁時協助聯繫指定家人並引導撥打 119／1925。系統不做醫療判讀——所有警示皆需真人確認後處理。");
    if(!rec.length){
      html+=card("安全警訊清單", "聊天中出現高風險訊號會記在這", emptyBox("目前沒有安全警訊——是好消息。"));
    } else {
      html+=card("安全警訊清單", "標紅為高風險，需 30 分內確認", `<div class="rows">${rec.slice(0,20).map((e)=>{
        const tone=String(e.riskLevel).match(/high|crisis|crit/i)?"bad":String(e.riskLevel).match(/med|mod/i)?"warn":"mute";
        return `<div class="row-item ${tone==="bad"?"tint-bad":tone==="warn"?"tint-warn":""}"><div class="ri-body"><div class="ri-title">${esc(zh(RISK_ZH,e.riskLevel,"待查看"))} <span class="pill ${tone}">${esc((e.categories&&e.categories[0])||"訊號")}</span></div><div class="ri-desc">${esc(e.summary||"聊天中偵測到需關注訊號，請真人確認。")}</div><div class="ri-meta">${esc(e.personId||"用戶")} · ${esc(fmtTime(e.eventTime))}</div></div></div>`;
      }).join("")}</div>`);
    }
    html+=principle(`<b>出事時怎麼處理</b><div class="step-row"><span class="step"><i>1</i>30 分鐘內先確認</span><span class="step"><i>2</i>聯繫家庭圈指定的人</span><span class="step"><i>3</i>必要時引導撥 119／1925 並記錄</span><span class="step"><i>4</i>結案回填</span></div><div style="margin-top:8px">所有紀錄僅授權營運與安全團隊檢視。</div>`);
    return html;
  }

  function renderMedication(){
    const m=medication(), t=m.totals||{}, win=m.windowDays||30, rate=m.adherenceRate;
    const accts=(D().accounts||{}).accounts||[];
    const acctIndex={}; accts.forEach((a)=>{ if(a.accountId) acctIndex[a.accountId]=a; });
    const people=(m.people||[]).map((p)=>{
      const acct=acctIndex[p.accountId]||{};
      const familyName=(acct.familyGroup||{}).name||"–";
      const displayName=p.displayName||(acct.primaryPerson||{}).displayName||"長輩";
      return Object.assign({}, p, { familyName, displayName });
    });
    const concerning=people.filter((p)=>(p.missedStreak||0)>=2).length;
    let html=kpiRow([
      { label:"依從率", value:rate==null?"–":pct(rate), sub:`近 ${win} 天 · 做到 ÷（做到＋跳過＋漏服）`, star:true },
      { label:"做到次數", value:n(t.taken||0), sub:`近 ${win} 天次數` },
      { label:"漏服次數", value:n(t.missed||0), sub:`近 ${win} 天次數` },
      { label:"需要關心", value:n(concerning), sub:"連續漏服 2 天以上", info:"連續兩天以上沒做到提醒的人，建議家人主動關心一下" },
    ]);
    html+=principle(m.principle||"這裡只看「有沒有照提醒做到」，不做診斷或醫療建議——真的擔心，請家人直接跟長輩確認或聯繫醫療團隊。");
    const totalEvents=Object.values(t).reduce((a,b)=>a+(Number(b)||0),0);
    if(!totalEvents){
      html+=card("用藥依從率趨勢", `近 ${win} 天每日做到 vs 漏服`, emptyBox("還沒有用藥紀錄——有人開始用提醒後就會出現。"));
      return html;
    }
    const dl=m.daily||[], labels=dl.map((d)=>shortDate(d.date));
    html+=card("用藥依從率趨勢", `近 ${win} 天每日做到 vs 漏服`, chartMount("md-trend"));
    pending.push(()=>columnChart($("md-trend"), labels, [
      { name:"做到", color:cc.teal, values:dl.map((d)=>Math.round(d.taken||0)) },
      { name:"漏服", color:cc.coral, values:dl.map((d)=>Math.round(d.missed||0)) },
    ], { empty:"還沒有用藥紀錄——有人開始用提醒後就會出現。" }));
    const sorted=people.slice().sort((a,b)=>{
      const streakDiff=(b.missedStreak||0)-(a.missedStreak||0);
      if(streakDiff) return streakDiff;
      const ar=a.adherenceRate==null?-1:a.adherenceRate, br=b.adherenceRate==null?-1:b.adherenceRate;
      return ar-br;
    });
    html+=card("用藥名單", "依從率低或連續漏服多的排前面", sorted.length?tableHTML(["長輩","家庭","做到","漏服","依從率","連續漏服"], sorted.map((p)=>[
      `<b>${esc(p.displayName)}</b>`,
      esc(p.familyName),
      n(p.taken||0),
      n(p.missed||0),
      p.adherenceRate==null?"–":pct(p.adherenceRate),
      p.missedStreak?`<span class="pill ${p.missedStreak>=2?"bad":"warn"}">${n(p.missedStreak)} 天</span>`:`<span class="muted">—</span>`,
    ])):emptyBox("還沒有用藥紀錄——有人開始用提醒後就會出現。"));
    return html;
  }

  function renderFamilyHealth(){
    const fh=familyHealth(), t=fh.totals||{}, win=fh.windowDays||30, rate=fh.guardedRate;
    const inv=fh.invites||{};
    let html=kpiRow([
      { label:"有人顧的比例", value:rate==null?"–":pct(rate), sub:`近 ${win} 天 · ${n(t.withActiveGuardian||0)}／${n(t.households||0)} 戶`, star:true, info:"這戶除了長輩本人以外，近 N 天內至少有 1 位家人傳話、看過家庭看板或家人訊息、或參與家庭活動，就算「有人顧」。" },
      { label:"多人守護家數", value:n(t.multiGuardian||0), sub:`近 ${win} 天有 2 位以上家人在顧` },
      { label:"沒人顧家數", value:n(t.unwatched||0), sub:`近 ${win} 天沒有任何家人動作`, info:"家庭圈只有長輩本人、或家人整段時間都沒動作——流失與安全雙警訊" },
      { label:"邀請成功率", value:inv.acceptRate==null?"–":pct(inv.acceptRate), sub:`近 ${win} 天送出 ${n(inv.sent||0)} 筆邀請` },
    ]);
    html+=principle(fh.principle||"「有人顧」的算法：家人有傳話、看過家庭看板或家人訊息、或參與家庭活動任一動作，就算這家有人在顧；長輩自己的動作不算。這裡只看「有沒有動作」，不評斷家人感情好不好。");
    const dl=fh.daily||[], labels=dl.map((d)=>shortDate(d.date));
    const totalDaily=dl.reduce((s,d)=>s+(d.messages||0)+(d.views||0),0);
    if(!totalDaily && !(t.households||0)){
      html+=card("家人互動趨勢", `近 ${win} 天傳話 vs 查看`, emptyBox("還沒有家庭圈資料——有家人開始用起來後就會出現。"));
      return html;
    }
    html+=card("家人互動趨勢", `近 ${win} 天傳話 vs 查看`, chartMount("fh-trend"));
    pending.push(()=>columnChart($("fh-trend"), labels, [
      { name:"傳話", color:cc.teal, values:dl.map((d)=>Math.round(d.messages||0)) },
      { name:"查看", color:cc.coral, values:dl.map((d)=>Math.round(d.views||0)) },
    ], { empty:"還沒有家人互動紀錄。" }));
    const list=fh.unwatchedList||[];
    html+=card("沒人顧名單", "最久沒有家人動作的排前面", list.length?tableHTML(["家庭","長輩","家人數","最後一次家人動作"], list.map((it)=>[
      esc(it.familyName||"–"),
      `<b>${esc(it.elderName||"長輩")}</b>`,
      n(it.memberCount||0),
      it.lastFamilyActionAt?esc(fmtTime(it.lastFamilyActionAt)):`<span class="pill bad">從沒動作過</span>`,
    ])):emptyBox("目前每一位長輩都有家人在顧——很好。"));
    return html;
  }

  function renderMoodTrend(){
    const mt=moodTrend(), t=mt.totals||{}, win=mt.windowDays||30, avgLevel=mt.averageLevel;
    const accts=(D().accounts||{}).accounts||[];
    const acctIndex={}; accts.forEach((a)=>{ if(a.accountId) acctIndex[a.accountId]=a; });
    const watch=(mt.watchlist||[]).map((p)=>{
      const acct=acctIndex[p.accountId]||{};
      const familyName=(acct.familyGroup||{}).name||"–";
      const displayName=p.displayName||(acct.primaryPerson||{}).displayName||"長輩";
      return Object.assign({}, p, { familyName, displayName });
    });
    let html=kpiRow([
      { label:"心情平均分", value:avgLevel==null?"–":avgLevel.toFixed(1), sub:`近 ${win} 天 · 1～5 分（5 分最好）`, star:true, info:"由陪伴聊天內容推測的心情高低分（1-5），不是醫療評分。" },
      { label:"正向比例", value:mt.positiveRate==null?"–":pct(mt.positiveRate), sub:`近 ${win} 天 · ${n(t.positive||0)} 次` },
      { label:"低落比例", value:mt.lowRate==null?"–":pct(mt.lowRate), sub:`近 ${win} 天 · ${n(t.low||0)} 次` },
      { label:"需要關心", value:n(watch.length), sub:"近 7 天低落 3 次以上或連續 3 天", info:"近 7 天內出現 3 次以上低落類心情、或連續 3 天都有低落類心情，建議家人主動關心一下" },
    ]);
    html+=principle(mt.principle||"這是陪伴聊天時的心情紀錄，由 AI 依對話內容推測，不是醫療診斷、也不是健康建議；異常請由真人關心確認。");
    if(!(t.signals||0)){
      html+=card("心情趨勢", `近 ${win} 天正向 vs 低落`, emptyBox("還沒有心情紀錄——開始聊天後就會出現。"));
      return html;
    }
    const dl=mt.daily||[], labels=dl.map((d)=>shortDate(d.date));
    html+=card("心情趨勢", `近 ${win} 天每日正向 vs 低落`, chartMount("mt-trend"));
    pending.push(()=>columnChart($("mt-trend"), labels, [
      { name:"正向", color:cc.teal, values:dl.map((d)=>Math.round(d.positive||0)) },
      { name:"低落", color:cc.coral, values:dl.map((d)=>Math.round(d.low||0)) },
    ], { empty:"還沒有心情紀錄。" }));
    const sorted=watch.slice().sort((a,b)=>{
      const streakDiff=(b.lowStreak||0)-(a.lowStreak||0);
      if(streakDiff) return streakDiff;
      return (b.lowCount||0)-(a.lowCount||0);
    });
    html+=card("需要關心名單", "連續低落天數多、次數多的排前面", sorted.length?tableHTML(["長輩","家庭","低落次數","連續低落","最近一次"], sorted.map((p)=>[
      `<b>${esc(p.displayName)}</b>`,
      esc(p.familyName),
      n(p.lowCount||0),
      p.lowStreak?`<span class="pill ${p.lowStreak>=3?"bad":"warn"}">${n(p.lowStreak)} 天</span>`:`<span class="muted">—</span>`,
      p.lastSignalAt?esc(fmtTime(p.lastSignalAt)):`<span class="muted">—</span>`,
    ])):emptyBox("目前沒有人需要特別關心——很好。"));
    return html;
  }

  function renderBondDepth(){
    const bd=bondDepth(), t=bd.totals||{}, win=bd.windowDays||30, stuckDays=bd.stuckDays||14;
    const trustedPlus=(t.trusted||0)+(t.close||0);
    const stuckCount=t.stuck!=null?t.stuck:(bd.stuckList||[]).length;
    let html=kpiRow([
      { label:"平均記憶筆數", value:bd.avgMemories==null?"–":bd.avgMemories.toFixed(1), sub:`近 ${win} 天還在互動的長輩平均`, star:true, info:"沐寧幫每位長輩記住幾件事——只算筆數，不看內容。" },
      { label:"信任以上人數", value:n(trustedPlus), sub:`近 ${win} 天 · 信任＋親近` },
      { label:"卡在新認識人數", value:n(stuckCount), sub:`用了超過 ${stuckDays} 天還沒熟起來`, info:"陪伴沒建立起來，最可能默默流失，建議真人多關心。" },
      { label:"平均升級天數", value:bd.upgradeDays==null?"–":n(bd.upgradeDays), sub:"從新認識到熟悉平均花幾天" },
    ]);
    html+=principle(bd.principle||"「關係深度」看沐寧跟每位長輩處得多熟：新認識→熟悉→信任→親近。只看筆數與階段，記憶內容不會出現在這裡。");
    const dist=[
      { label:"新認識", value:t.newly||0 },
      { label:"熟悉", value:t.familiar||0 },
      { label:"信任", value:t.trusted||0 },
      { label:"親近", value:t.close||0 },
    ];
    if(!(t.people||0)){
      html+=card("關係階段分佈", `近 ${win} 天還在互動的長輩`, emptyBox("還沒有關係資料——長輩開始跟沐寧聊天後就會出現。"));
    } else {
      html+=card("關係階段分佈", `近 ${win} 天還在互動的長輩 · 共 ${n(t.people||0)} 人`, chartMount("bd-dist"));
      pending.push(()=>columnChart($("bd-dist"), dist.map((d)=>d.label), [
        { name:"人數", color:cc.teal, values:dist.map((d)=>Math.round(d.value||0)) },
      ], { empty:"還沒有關係資料。" }));
    }
    const list=bd.stuckList||[];
    html+=card("卡住名單", "用了很久卻還停在新認識，排前面最需要關心", list.length?tableHTML(["長輩","家庭","記憶筆數","用了幾天","最近聊天"], list.map((p)=>[
      `<b>${esc(p.displayName||"長輩")}</b>`,
      esc(p.familyName||"–"),
      n(p.memories||0),
      p.daysSinceJoin!=null?`<span class="pill ${p.daysSinceJoin>=stuckDays*2?"bad":"warn"}">${n(p.daysSinceJoin)} 天</span>`:"–",
      p.lastTalkAt?esc(fmtTime(p.lastTalkAt)):`<span class="muted">—</span>`,
    ])):emptyBox("目前沒有人卡在剛認識——很好。"));
    return html;
  }

  function renderSubscription(){
    const sm=subM(), win=sm.windowDays||30;
    let html=kpiRow([
      { label:"新增訂閱", value:n(sm.newSubscriptions), sub:`近 ${win} 天付費訂閱新增`, star:true },
      { label:"點數加購", value:n(sm.pointsPurchases), unit:sm.pointsPurchases?" 筆":"", sub:`共 ${n(sm.pointsTotal)} 點` },
      { label:"新註冊", value:n(sm.registrations), sub:`近 ${win} 天開通帳號` },
      { label:"免費→付費轉換率", value:sm.freeToPaidConversion==null?"–":(sm.freeToPaidConversion*100).toFixed(1)+"%", sub:"付費數 ÷ 註冊數 · 目標 ≥8%" },
    ]);
    // ══ 點數經濟：平台層用全帳號點數、明細用 /admin/credits ══
    const cAccts=(D().accounts||{}).accounts||[];
    const LOW_PTS=20;
    const ptsTotal=cAccts.reduce((s,a)=>s+Number(a.points||0),0);
    const ptsAvg=cAccts.length?Math.round(ptsTotal/cAccts.length):null;
    const lowList=cAccts.filter((a)=>Number(a.points||0)<LOW_PTS).sort((a,b)=>Number(a.points||0)-Number(b.points||0));
    html+=kpiRow([
      { label:"全平台持有點數", value:n(ptsTotal), sub:`${n(cAccts.length)} 戶合計`, star:true },
      { label:"平均每戶點數", value:ptsAvg==null?"–":n(ptsAvg), sub:"點／戶" },
      { label:"快用完", value:n(lowList.length), sub:`剩不到 ${LOW_PTS} 點`, info:"點數快見底的帳號——主動關心或提醒加購的好時機" },
      { label:"近 30 天加購", value:n(sm.pointsPurchases), unit:sm.pointsPurchases?" 筆":"", sub:`共 ${n(sm.pointsTotal)} 點` },
    ]);
    html+=card("快用完名單", `剩不到 ${LOW_PTS} 點 · 建議主動關心或提醒加購`, lowList.length?tableHTML(["用戶","家庭","方案","剩餘點數","最近活躍"], lowList.slice(0,12).map((a)=>{
      const pp=a.primaryPerson||{},ff=a.familyGroup||{},uu=a.usage||{};
      return [
        `<b>${esc(pp.displayName||a.accountName||"–")}</b>`,
        esc(ff.name||"–"),
        planPill(a.plan||"free"),
        `<span class="pts-cell"><b class="num">${n(a.points||0)}</b><span class="muted small">點</span></span>`,
        `<span class="muted small">${esc(fmtTime(uu.lastActiveAt||a.updatedAt||a.createdAt))}</span>`,
      ];
    })):emptyBox("目前沒有人點數快用完——很好。"));
    const cw=creditsSummary(), ws=cw.walletSummary||{}, ctx=cw.recentTransactions||[];
    html+=card("點數組成與最近異動", "贈點與加購的餘額、最近的發放與消耗", (ws.total!=null||ctx.length)?`
      <div style="display:flex;gap:26px;flex-wrap:wrap${ctx.length?";margin-bottom:14px":""}">
        <div><div class="kpi-sub">每月贈點餘額</div><div class="kpi-value">${n(ws.includedMonthly)}</div></div>
        <div><div class="kpi-sub">加購餘額</div><div class="kpi-value">${n(ws.purchased)}</div></div>
        <div><div class="kpi-sub">合計</div><div class="kpi-value">${n(ws.total)}</div></div>
      </div>
      ${ctx.length?`<div class="rows">${ctx.slice(0,10).map((t)=>{
        const amt=Number(t.amount||0), up=amt>=0;
        return `<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(zh(CREDIT_ZH,t.reason||t.transactionType||t.type,"點數異動"))} <span class="pill ${up?"ok":"mute"}">${up?"+":""}${n(amt)} 點</span></div><div class="ri-meta">${esc(fmtTime(t.createdAt||t.occurredAt||t.time))}</div></div></div>`;
      }).join("")}</div>`:""}`:emptyBox("還沒有點數異動紀錄——有人開始用點數後就會出現。"));
    // MRR / 流失：誠實標「待接 Apple」，不擺假數字
    const p=sm.pending||{};
    html+=card("每月經常性收入 ／ 退訂率", "App 還沒正式上架，所以還沒有真實付費訂閱", `
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div><div class="kpi-sub">每月訂閱收入</div><div class="pending-val">尚未開始<span class="pill mute">等上架</span></div></div>
        <div><div class="kpi-sub">退訂率</div><div class="pending-val">尚未開始<span class="pill mute">等上架</span></div></div>
      </div>
      <div class="kpi-sub" style="margin-top:12px">${esc(p.mrr||"App 上架、開始有人付費之後，這兩個數字就會自動長出來（用自家的訂閱紀錄算，不必另外接蘋果後台）。")}${p.churnRate?"　"+esc(p.churnRate):""}</div>`);
    html+=card("方案表現", "月費 · 贈點 · 家庭圈上限（固定資訊）", tableHTML(["方案","內容","月費"],[
      ["<b>免費體驗</b>","綁定送 5 分鐘 · 提醒與心情先用起來","<span class='num'>NT$0</span>"],
      ["<b>Plus 家庭</b>","每月贈 100 點 · 家庭圈最多 4 人","<span class='num'>NT$599/月</span>"],
      ["<b>Pro 大家庭</b>","每月贈 200 點 · 家庭圈最多 12 人","<span class='num'>NT$1,199/月</span>"],
    ]));
    html+=assumeCardHTML();
    return html;
  }

  function renderFeedback(){
    const f=D().feedback||{}, latest=f.latest||[], nps=(f.nps==null?"–":f.nps);
    let html=kpiRow([
      { label:"意見則數", value:n(latest.length), sub:"最近收到的用戶意見", star:true },
      { label:"推薦分數 NPS", value:esc(nps), sub:`共 ${n(f.npsCount||0)} 人打分` },
      { label:"稱讚", value:n((f.totals||{}).praise||latest.filter((x)=>x.type==="praise").length), sub:"用戶主動稱讚" },
      { label:"問題回報", value:n((f.totals||{}).bug||latest.filter((x)=>x.type==="bug").length), sub:"待修的問題" },
    ]);
    if(!latest.length){
      html+=card("用戶意見收件匣", "App「幫沐寧打分數」與意見都送到這", emptyBox("還沒有人留意見——上線後這裡會熱鬧起來。"));
    } else {
      html+=card("用戶意見收件匣", "最近的意見（新到舊）", `<div class="rows">${latest.slice(0,15).map((it)=>{
        const img=typeof it.image==="string"&&it.image.indexOf("data:image/")===0?`<a href="${it.image}" target="_blank" rel="noopener"><img src="${it.image}" alt="附圖" style="margin-top:8px;max-width:150px;max-height:110px;border-radius:8px;border:1px solid #ccc;display:block"></a>`:"";
        const tone=FB_TONE[String(it.type||"").toLowerCase()]||"mute";
        return `<div class="row-item"><div class="ri-body"><div class="ri-title"><span class="pill ${tone}">${esc(zh(FB_ZH,it.type,"意見"))}</span>${it.score!=null?`　${esc(it.score)} 分`:""}${img?"　📎有圖":""}</div><div class="ri-meta">${esc(it.category||"–")} · ${esc(fmtTime(it.createdAt))} · App ${esc(it.appVersion||"?")}</div><div style="margin-top:4px">${esc(it.text||"")}</div>${img}</div></div>`;
      }).join("")}</div>`);
    }
    // 隱私申請（真）
    const pv=D().privacy||{}, pvr=pv.recent||[];
    html+=card("隱私申請", "刪除帳號、要資料副本的申請", pvr.length?`<div class="rows">${pvr.slice(0,10).map((r)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(zh(PV_ZH,r.type,"申請"))} <span class="pill mute">${esc(zh(ST_ZH,r.status))}</span></div><div class="ri-meta">${esc(fmtTime(r.requestedAt))}</div><div>${esc(r.reason||"")}</div></div></div>`).join("")}</div>`:emptyBox("目前沒有人申請刪帳號或要資料。"));
    return html;
  }

  function renderRecords(){
    const sm=(D().summaries||{}).recent||[], au=(D().audit||{}).recent||[];
    let html=card("聊天摘要", "AI 記下的每段聊天重點（已去逐字、只留摘要）", sm.length?`<div class="rows">${sm.slice(0,15).map((s)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(fmtTime(s.createdAt))}</div><div class="ri-desc">${esc(s.summary||"")}</div><div class="tag-row">${(s.memoryTags||[]).map((t)=>`<span class="pill mute">${esc(t)}</span>`).join("")}${s.safetyRelevant?'<span class="pill bad">涉及安全</span>':""}</div></div></div>`).join("")}</div>`:emptyBox("還沒有聊天摘要——有人開始跟沐寧聊天後就會出現。"));
    html+=card("系統操作紀錄", "系統跟管理端動過什麼，給工程師追查用", au.length?tableHTML(["時間","事件","對象"], au.slice(0,25).map((e)=>[
      `<span class="muted small">${esc(fmtTime(e.createdAt))}</span>`,
      `<b>${esc(e.eventType||"事件")}</b>`,
      `${esc(e.targetId||e.accountId||"–")}<span class="muted small"> · ${esc(e.targetTable||"–")}</span>`,
    ])):emptyBox("還沒有操作紀錄。"));
    return html;
  }

  function tableHTML(cols, rows, rowClasses){
    return `<div class="table-wrap"><table><thead><tr>${cols.map((c)=>`<th scope="col">${c?esc(c):'<span class="sr-only">操作</span>'}</th>`).join("")}</tr></thead><tbody>${rows.map((r,i)=>`<tr class="${(rowClasses&&rowClasses[i])||""}">${r.map((c)=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  function openAcctDetail(idx){
    const a=((D().accounts||{}).accounts||[])[idx]; if(!a) return;
    const p=a.primaryPerson||{},f=a.familyGroup||{},c=a.companion||{},m=a.familyMembers||{},u=a.usage||{};
    const safety=D().safety||{}, escalations=(safety.totals||{}).requiresHumanEscalation||0;
    const single=((D().accounts||{}).accounts||[]).length===1;
    const st=(single&&escalations>0)?"alert":(a.status||"off");
    const planTxt={pro:"Pro",plus:"Plus",free:"免費"}[a.plan||"free"]||"免費";
    const stTxt={on:"活躍中",idle:"低度使用",off:"離線",alert:"守護中"}[st]||"離線";
    const mins=Math.round(u.totalMinutes||0);
    const fields=[["家庭圈",f.name||"–"],["主要使用者",p.displayName||"–"],["陪伴角色",c.displayName||c.templateId||"–"],["方案",planTxt],["持有點數",n(a.points||0)+" 點"],["活躍狀態",stTxt],["近 30 天使用",mins?mins+" 分（通話 "+Math.round(u.voiceMinutes||0)+" · 視訊 "+Math.round(u.avatarMinutes||0)+"）":"—"],["最近活躍",fmtTime(u.lastActiveAt||a.updatedAt)],["家人數",(m.count||0)+" 人"],["建立",fmtTime(a.createdAt)]];
    const body=`<div class="modal-head"><div><div class="modal-title" id="acctModalTitle">${esc(p.displayName||a.accountName||"帳號")}</div><div class="muted small">${esc(f.name||"–")}</div></div><button class="modal-x" data-close type="button" aria-label="關閉用戶明細">✕</button></div>
      <div class="detail-grid">${fields.map((x)=>`<div class="dcell"><div class="dlabel">${esc(x[0])}</div><div class="dval">${esc(x[1])}</div></div>`).join("")}</div>
      <div class="kpi-sub" style="margin-top:14px">為保護隱私，健康與聊天內容需經該用戶授權才在此顯示。</div>`;
    const previous=document.activeElement,layout=document.querySelector(".layout");
    let mo=$("acctModal"); if(!mo){ mo=document.createElement("div"); mo.id="acctModal"; mo.className="modal-overlay"; document.body.appendChild(mo); }
    mo.innerHTML=`<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="acctModalTitle">${body}</div>`; mo.hidden=false;
    if(layout)layout.inert=true;
    const onKey=(e)=>{ if(e.key==="Escape")close(); };
    const onOverlay=(e)=>{ if(e.target===mo)close(); };
    const close=()=>{ mo.hidden=true; if(layout)layout.inert=false; document.removeEventListener("keydown",onKey); mo.removeEventListener("click",onOverlay); if(previous&&previous.focus)previous.focus(); };
    mo.querySelectorAll("[data-close]").forEach((b)=>b.addEventListener("click",close));
    mo.addEventListener("click",onOverlay);
    document.addEventListener("keydown",onKey);
    mo.querySelector("[data-close]")?.focus();
  }


  // ==========================================================================================
  // 企業客戶（B2B 席次管理）—— 4 個畫面：客戶列表 / 單一公司 / 名單匯入 / 收款登記
  // 資料各頁進場才現查（不掛進 loadAll 的 EP_LIST），走同一套 postAdmin，跟登入共用同一份通行碼。
  // ==========================================================================================
  const ENT_STATUS_ZH = { ok:["ok","正常"], expiring:["warn","30 天內到期"], overdue:["bad","逾期未付"] };
  function entStatusPill(s){ const x=ENT_STATUS_ZH[s]||ENT_STATUS_ZH.ok; return `<span class="pill ${x[0]}"><span class="sdot"></span>${x[1]}</span>`; }
  const ENT_SEAT_STATUS_ZH = { pending:["mute","待開通"], waiting:["warn","等待接手"], active:["ok","使用中"], grace:["warn","緩衝期"], released:["mute","已釋出"] };
  function entSeatStatusPill(s){ const x=ENT_SEAT_STATUS_ZH[s]||ENT_SEAT_STATUS_ZH.pending; return `<span class="pill ${x[0]}">${x[1]}</span>`; }
  const ENT_INVOICE_STATUS_ZH = { draft:["mute","草稿・待確認"], issued:["warn","已寄出・待收款"], sent:["warn","已寄出・待收款"], paid:["ok","已收款"], invoiced:["ok","已開發票"], void:["mute","已作廢"] };
  function entInvoiceStatusPill(s){ const x=ENT_INVOICE_STATUS_ZH[s]||ENT_INVOICE_STATUS_ZH.draft; return `<span class="pill ${x[0]}">${x[1]}</span>`; }

  const ENT_BILLING_REQUIRED_FIELDS = [
    ["issuerCompanyName","開票公司抬頭"],
    ["bankName","收款銀行"],
    ["bankAccountName","戶名"],
    ["bankAccountNo","帳號"],
  ];
  function entBillingSettingsMissing(bs){
    bs=bs||{};
    return ENT_BILLING_REQUIRED_FIELDS.filter(([key])=>!String(bs[key]||"").trim()).map(([,label])=>label);
  }
  function entBillingSettingsMissingCount(){
    const c=state.tabs.entBillingSettings;
    if(!c||c.status!=="ready") return 0;
    return entBillingSettingsMissing((c.data&&c.data.settings)||{}).length;
  }
  function entBillingSettingsWarningHTML(){
    const c=ensureEnterpriseBillingSettingsLoaded();
    if(c.status!=="ready") return "";
    const missing=entBillingSettingsMissing((c.data&&c.data.settings)||{});
    if(!missing.length) return "";
    return `<div class="ops-notice warn" role="alert"><strong>開票與收款設定還沒填完</strong>還缺「${missing.map((x)=>esc(x)).join("、")}」——月結產出的請款單會印不出正確資訊。 <button type="button" class="btn-ghost btn-sm" data-goto="enterpriseBillingSettings" style="margin-top:8px">前往填寫</button></div>`;
  }

  function downloadTextFile(filename, text, mime){
    const blob=new Blob([text||""],{type:mime||"text/csv;charset=utf-8;"});
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a"); a.href=url; a.download=filename||"download.csv";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1200);
  }

  // 重大動作二次確認彈窗（如「已入帳」）——跟 openAcctDetail 同一套 inert/焦點回歸寫法
  function openConfirmModal(opts){
    opts=opts||{};
    const previous=document.activeElement, layout=document.querySelector(".layout");
    let mo=$("confirmModal");
    if(!mo){ mo=document.createElement("div"); mo.id="confirmModal"; mo.className="modal-overlay"; document.body.appendChild(mo); }
    mo.innerHTML=`<div class="modal-card confirm-card${opts.danger?" danger":""}" role="alertdialog" aria-modal="true" aria-labelledby="confirmModalTitle">
      <div class="modal-head"><div class="modal-title" id="confirmModalTitle">${esc(opts.title||"請再確認一次")}</div><button class="modal-x" data-cf-close type="button" aria-label="取消">✕</button></div>
      <div class="confirm-body">${opts.bodyHtml||""}</div>
      <div class="confirm-actions">
        <button type="button" class="btn-ghost" data-cf-cancel>${esc(opts.cancelLabel||"再想想")}</button>
        <button type="button" class="${opts.danger?"btn-danger":""}" data-cf-confirm>${esc(opts.confirmLabel||"確認")}</button>
      </div>
    </div>`;
    mo.hidden=false;
    if(layout) layout.inert=true;
    const onKey=(e)=>{ if(e.key==="Escape") close(); };
    const onOverlay=(e)=>{ if(e.target===mo) close(); };
    const close=()=>{ mo.hidden=true; if(layout) layout.inert=false; document.removeEventListener("keydown",onKey); mo.removeEventListener("click",onOverlay); if(previous&&previous.focus) previous.focus(); };
    mo.querySelectorAll("[data-cf-close],[data-cf-cancel]").forEach((b)=>b.addEventListener("click",close));
    mo.addEventListener("click",onOverlay);
    document.addEventListener("keydown",onKey);
    const confirmBtn=mo.querySelector("[data-cf-confirm]");
    if(confirmBtn) confirmBtn.addEventListener("click",()=>{ close(); if(typeof opts.onConfirm==="function") opts.onConfirm(); });
    const closeBtn=mo.querySelector("[data-cf-close]"); if(closeBtn) closeBtn.focus();
  }

  function entActionError(msg){
    if(msg==="no_client_selected") return `<div class="ops-notice warn" role="alert" style="margin-top:12px"><strong>請先選公司</strong>選好目標公司才能繼續。</div>`;
    return `<div class="ops-notice error" role="alert" style="margin-top:12px"><strong>沒有成功</strong>${esc(explainErr(msg))}</div>`;
  }
  function entActionNote(id,html){ const el=$(id); if(el) el.innerHTML=html||""; }
  function entLoadingOrErrorCard(status,error,title,retryAttr){
    if(status==="loading") return card(title,"讀取中",emptyBox("讀取中…"));
    if(status==="error") return `<div class="ops-notice error" role="alert"><strong>讀不到資料</strong>${esc(explainErr(error))}</div>${card(title,"",`<button type="button" class="btn-sm" ${retryAttr}>重新整理</button>`)}`;
    return null;
  }

  // ── 企業客戶清單／請款單清單：進場才查，動作完成後主動 reload ──
  function ensureEnterpriseClientsLoaded(){
    const c=state.tabs.entClientsList||(state.tabs.entClientsList={status:"idle",data:null,error:null});
    if(c.status==="idle"){
      c.status="loading";
      const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
      postAdmin(base, token, "/admin/enterprise/clients", {})
        .then((p)=>{ c.status="ready"; c.data=p; if(["enterpriseClients","enterpriseImport","enterprisePayments"].includes(state.page)) renderPage(state.page); })
        .catch((e)=>{ c.status="error"; c.error=(e&&e.message)||"fail"; if(state.page==="enterpriseClients") renderPage(state.page); });
    }
    return c;
  }
  function reloadEnterpriseClients(){ state.tabs.entClientsList={status:"idle",data:null,error:null}; return ensureEnterpriseClientsLoaded(); }
  function ensureEnterpriseInvoicesLoaded(){
    const c=state.tabs.entInvoicesList||(state.tabs.entInvoicesList={status:"idle",data:null,error:null});
    if(c.status==="idle"){
      c.status="loading";
      const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
      postAdmin(base, token, "/admin/enterprise/invoices", {})
        .then((p)=>{ c.status="ready"; c.data=p; if(state.page==="enterprisePayments") renderPage(state.page); })
        .catch((e)=>{ c.status="error"; c.error=(e&&e.message)||"fail"; if(state.page==="enterprisePayments") renderPage(state.page); });
    }
    return c;
  }
  function reloadEnterpriseInvoices(){ state.tabs.entInvoicesList={status:"idle",data:null,error:null}; return ensureEnterpriseInvoicesLoaded(); }
  function ensureEnterpriseBillingSettingsLoaded(){
    const c=state.tabs.entBillingSettings||(state.tabs.entBillingSettings={status:"idle",data:null,error:null});
    if(c.status==="idle"){
      c.status="loading";
      const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
      postAdmin(base, token, "/admin/enterprise/billing-settings", {})
        .then((p)=>{ c.status="ready"; c.data=p; if(["enterpriseClients","enterprisePayments","enterpriseBillingSettings"].includes(state.page)) renderPage(state.page); })
        .catch((e)=>{ c.status="error"; c.error=(e&&e.message)||"fail"; if(state.page==="enterpriseBillingSettings") renderPage(state.page); });
    }
    return c;
  }
  function reloadEnterpriseBillingSettings(){ state.tabs.entBillingSettings={status:"idle",data:null,error:null}; return ensureEnterpriseBillingSettingsLoaded(); }

  // ── 畫面 1・企業客戶列表 ──
  function renderEnterpriseClients(){
    const c=ensureEnterpriseClientsLoaded();
    const guard=entLoadingOrErrorCard(c.status,c.error,"企業客戶列表","data-ent-retry-clients");
    if(guard) return guard;
    const clients=entClients();
    const activeSeats=clients.reduce((s,x)=>s+Number(x.activeSeats||0),0);
    const monthly=clients.reduce((s,x)=>s+Number(x.estimatedMonthlyTwd||0),0);
    const overdue=clients.filter((x)=>x.statusLight==="overdue");
    let html=entBillingSettingsWarningHTML();
    html+=kpiRow([
      { label:"企業客戶數", value:n(clients.length), sub:"目前合作中的公司", star:true },
      { label:"累計啟用席次", value:n(activeSeats), sub:"所有公司加總" },
      { label:"本月預估金額", value:fmtMoney(monthly), sub:"依目前啟用席次估算" },
      { label:"逾期未付", value:n(overdue.length), sub:overdue.length?"要優先催收":"目前沒有" },
    ]);
    const addBtn=`<button type="button" class="btn-sm" data-ent-new-client>＋ 新增企業客戶</button>`;
    if(!clients.length){
      html+=card("企業客戶列表","公司名、合約期間、席次、狀態、金額",emptyBox("還沒有企業客戶——談成第一家公司後，這裡會列出來。"),addBtn);
      return html;
    }
    const rowClasses=clients.map((x)=>x.statusLight==="overdue"?"tr-overdue":"");
    const rows=clients.map((x)=>{
      const seatTxt=`<b class="num">${n(x.activeSeats||0)}</b><span class="muted small"> ／ 上限 ${n(x.seatQuota||0)}</span>${x.waitingSeats?`<div class="muted small">等待接手 ${n(x.waitingSeats)}</div>`:""}${x.graceSeats?`<div class="muted small">緩衝期 ${n(x.graceSeats)}</div>`:""}`;
      const overdueTxt=Number(x.outstandingTwd||0)>0
        ? `<b style="color:var(--danger)">${fmtMoney(x.outstandingTwd)}</b>${x.overdueDays?`<div class="small" style="color:var(--danger);font-weight:700">逾期 ${n(x.overdueDays)} 天</div>`:""}`
        : `<span class="muted">—</span>`;
      return [
        `<b>${esc(x.name||"–")}</b>${x.taxId?`<div class="muted small">統編 ${esc(x.taxId)}</div>`:""}`,
        `<span class="small">${esc(fmtDate(x.contractStart))} － ${esc(fmtDate(x.contractEnd))}</span>`,
        seatTxt,
        entStatusPill(x.statusLight),
        fmtMoney(x.estimatedMonthlyTwd),
        overdueTxt,
        `<button type="button" class="row-act" data-ent-view="${esc(x.id)}" aria-label="查看 ${esc(x.name||"")} 明細">查看<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg></button>`,
      ];
    });
    html+=`<div class="card tbl-card"><div class="card-head"><div><h3>企業客戶列表</h3><div class="card-note">共 ${clients.length} 家 · 逾期未付以紅色標示</div></div>${addBtn}</div>${tableHTML(["公司","合約期間","席次(已啟用／上限)","狀態","本月預估","累計欠款",""], rows, rowClasses)}</div>`;
    html+=`<div id="entClientActionNote"></div>`;
    return html;
  }

  // ── 畫面 2・單一公司（從列表「查看」進來）──
  function loadEnterpriseClientDetail(clientId){
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    state.tabs.entDetail={ clientId, status:"loading", data:null, error:null };
    renderPage(state.page);
    postAdmin(base, token, "/admin/enterprise/client/detail", { clientId })
      .then((p)=>{ if(state.tabs.entClientId!==clientId) return; state.tabs.entDetail={ clientId, status:"ready", data:p, error:null }; renderPage(state.page); })
      .catch((e)=>{ if(state.tabs.entClientId!==clientId) return; state.tabs.entDetail={ clientId, status:"error", data:null, error:(e&&e.message)||"fail" }; renderPage(state.page); });
  }
  function renderEnterpriseClientDetail(){
    const clientId=state.tabs.entClientId;
    const back=`<button type="button" class="btn-ghost btn-sm" data-goto="enterpriseClients">← 返回企業客戶列表</button>`;
    if(!clientId) return `${back}${card("企業客戶明細","",emptyBox("請先從列表選擇一家公司。"))}`;
    const ed=state.tabs.entDetail||{};
    if(ed.clientId!==clientId || ed.status==="loading") return `${back}${card("企業客戶明細","讀取中",emptyBox("讀取這家公司的資料中…"))}`;
    if(ed.status==="error") return `${back}${card("企業客戶明細","",`<div class="ops-notice error" role="alert"><strong>讀不到這家公司的資料</strong>${esc(explainErr(ed.error))}</div><button type="button" class="btn-sm" style="margin-top:10px" data-ent-retry-detail="${esc(clientId)}">重新整理</button>`)}`;
    const data=ed.data||{}, c=data.client||{}, seats=data.seats||[], invoices=data.invoices||[], reports=data.reports||data.downloads||[];
    let html=back;
    html+=card("基本資料", "可直接修改後儲存", `
      <div class="ent-form-grid">
        <label class="field"><span>公司名稱</span><input type="text" id="efName" value="${esc(c.name||"")}"></label>
        <label class="field"><span>統一編號</span><input type="text" id="efTaxId" value="${esc(c.taxId||"")}"></label>
        <label class="field field-wide"><span>帳單地址</span><input type="text" id="efBillingAddress" value="${esc(c.billingAddress||"")}"></label>
        <label class="field"><span>窗口姓名</span><input type="text" id="efContactName" value="${esc(c.contactName||"")}"></label>
        <label class="field"><span>窗口 Email</span><input type="email" id="efContactEmail" value="${esc(c.contactEmail||"")}"></label>
        <label class="field"><span>窗口電話</span><input type="text" id="efContactPhone" value="${esc(c.contactPhone||"")}"></label>
        <label class="field"><span>授予等級</span><select id="efPlanTier"><option value="plus"${c.planTier==="plus"?" selected":""}>Plus</option><option value="pro"${c.planTier==="pro"?" selected":""}>Pro</option></select></label>
        <label class="field"><span>每席月費 (NT$)</span><input type="number" id="efUnitPrice" value="${esc(c.unitPriceTwd||0)}"></label>
        <label class="field"><span>合約開始</span><input type="date" id="efContractStart" value="${esc(String(c.contractStart||"").slice(0,10))}"></label>
        <label class="field"><span>合約結束</span><input type="date" id="efContractEnd" value="${esc(String(c.contractEnd||"").slice(0,10))}"></label>
        <label class="field"><span>席次上限</span><input type="number" id="efSeatQuota" value="${esc(c.seatQuota||0)}"></label>
        <label class="field field-wide"><span>月報＋請款單收件人（可多位，逗號分隔）</span><input type="text" id="efReportRecipients" value="${esc(Array.isArray(c.reportRecipients)?c.reportRecipients.join(","):(c.reportRecipients||""))}"></label>
      </div>
      <label class="field field-wide"><span>備註</span><input type="text" id="efNotes" value="${esc(c.notes||"")}"></label>
      <button type="button" class="btn-sm" data-ent-save-client="${esc(clientId)}">儲存變更</button>
      <div id="entSaveNote"></div>
    `);
    html+=`<div class="ops-notice error" role="alert"><strong>內部限定・不可外流</strong>這一頁列出每個席次綁定的 email／狀態，只有我們自己看；企業客戶只會拿到月報上的彙總數字，永遠看不到這一頁。</div>`;
    const seatRows=seats.map((s)=>[
      `<input type="checkbox" class="ent-seat-chk" value="${esc(s.id)}" ${["active","waiting","grace"].includes(s.status)?"":"disabled"}>`,
      esc(s.inviteEmail||"–"),
      entSeatStatusPill(s.status),
      s.activatedAt?esc(fmtDate(s.activatedAt)):`<span class="muted">—</span>`,
      s.graceUntil?esc(fmtDate(s.graceUntil)):`<span class="muted">—</span>`,
      s.usageMinutes!=null?n(s.usageMinutes)+" 分":`<span class="muted">—</span>`,
    ]);
    html+=card("席次明細", `共 ${seats.length} 席 · 勾選「使用中／等待接手／緩衝期」的席次可批次授予（待開通表示 email 還沒綁定帳號，還不能授予）`, seats.length?`
      ${tableHTML(["","Email","狀態","綁定時間","緩衝期至","本月用量"], seatRows)}
      <button type="button" class="btn-sm" data-ent-grant="${esc(clientId)}" style="margin-top:10px">批次授予</button>
      <div id="entGrantNote"></div>
    `:emptyBox("這家公司還沒有匯入任何席次——先去「名單匯入」上傳名單。"));
    const invRows=invoices.map((iv)=>[
      esc(iv.invoiceNo||iv.id||"–"),
      `${esc(fmtDate(iv.periodStart))} － ${esc(fmtDate(iv.periodEnd))}`,
      fmtMoney(iv.totalTwd),
      entInvoiceStatusPill(iv.status),
      iv.paidAt?esc(fmtDate(iv.paidAt)):`<span class="muted">未收款</span>`,
    ]);
    html+=card("收款紀錄", "這家公司歷次請款與收款", invoices.length?tableHTML(["單號","期間","金額","狀態","實際入帳日"], invRows):emptyBox("這家公司還沒有請款紀錄——跑過月結後會出現。"));
    const dlItems=reports.map((r,i)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(r.label||r.title||("文件 "+(i+1)))}</div><div class="ri-meta">${esc(r.period||"")}</div></div><div class="ri-actions"><button type="button" class="btn-ghost btn-sm" data-ent-download="${i}" data-ent-client="${esc(clientId)}">下載</button></div></div>`).join("");
    html+=card("月報與請款單下載", "自動產出的 ESG 成效月報＋請款單", reports.length?`<div class="rows">${dlItems}</div><div id="entDownloadNote"></div>`:emptyBox("還沒有可下載的月報或請款單——跑過月結後會出現。"));
    return html;
  }
  function entDownloadReport(clientId, idx){
    const ed=state.tabs.entDetail||{};
    const reports=(ed.data&&(ed.data.reports||ed.data.downloads))||[];
    const r=reports[idx]; if(!r) return;
    if(r.url){ window.open(r.url,"_blank","noopener"); return; }
    if(r.html){ downloadTextFile((r.label||"report")+".html", r.html, "text/html;charset=utf-8;"); return; }
    if(r.csv){ downloadTextFile((r.label||"report")+".csv", r.csv, "text/csv;charset=utf-8;"); return; }
    entActionNote("entDownloadNote", `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>這份文件目前沒有可下載的內容</strong>後端還沒提供檔案，等接好再試一次。</div>`);
  }

  function entCollectClientForm(p){
    const g=(suffix)=>{ const el=$(p+suffix); return el?el.value:""; };
    return {
      name:g("Name").trim(), taxId:g("TaxId").trim(), billingAddress:g("BillingAddress").trim(),
      contactName:g("ContactName").trim(), contactEmail:g("ContactEmail").trim(), contactPhone:g("ContactPhone").trim(),
      planTier:g("PlanTier")||"plus", unitPriceTwd:Number(g("UnitPrice"))||0,
      contractStart:g("ContractStart"), contractEnd:g("ContractEnd"), seatQuota:Number(g("SeatQuota"))||0,
      reportRecipients:g("ReportRecipients").split(",").map((s)=>s.trim()).filter(Boolean),
      notes:g("Notes").trim(),
    };
  }
  function entSaveClient(clientId){
    const body=entCollectClientForm("ef");
    if(!body.name){ entActionNote("entSaveNote", `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>請填公司名稱</strong></div>`); return; }
    if(clientId) body.id=clientId;
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/client/save", body)
      .then(()=>{ entActionNote("entSaveNote", `<div class="ops-notice info" role="status" style="margin-top:10px"><strong>已儲存</strong></div>`); reloadEnterpriseClients(); if(clientId) setTimeout(()=>loadEnterpriseClientDetail(clientId),1500); })
      .catch((e)=>entActionNote("entSaveNote", entActionError((e&&e.message)||"fail")));
  }
  function openNewClientModal(){
    const previous=document.activeElement, layout=document.querySelector(".layout");
    let mo=$("newClientModal");
    if(!mo){ mo=document.createElement("div"); mo.id="newClientModal"; mo.className="modal-overlay"; document.body.appendChild(mo); }
    mo.innerHTML=`<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="newClientTitle" style="width:min(640px,100%)">
      <div class="modal-head"><div class="modal-title" id="newClientTitle">新增企業客戶</div><button class="modal-x" data-nc-close type="button" aria-label="關閉">✕</button></div>
      <div class="ent-form-grid">
        <label class="field"><span>公司名稱</span><input type="text" id="ncName"></label>
        <label class="field"><span>統一編號</span><input type="text" id="ncTaxId"></label>
        <label class="field field-wide"><span>帳單地址</span><input type="text" id="ncBillingAddress"></label>
        <label class="field"><span>窗口姓名</span><input type="text" id="ncContactName"></label>
        <label class="field"><span>窗口 Email</span><input type="email" id="ncContactEmail"></label>
        <label class="field"><span>窗口電話</span><input type="text" id="ncContactPhone"></label>
        <label class="field"><span>授予等級</span><select id="ncPlanTier"><option value="plus">Plus</option><option value="pro">Pro</option></select></label>
        <label class="field"><span>每席月費 (NT$)</span><input type="number" id="ncUnitPrice" value="599"></label>
        <label class="field"><span>合約開始</span><input type="date" id="ncContractStart"></label>
        <label class="field"><span>合約結束</span><input type="date" id="ncContractEnd"></label>
        <label class="field"><span>席次上限</span><input type="number" id="ncSeatQuota" value="0"></label>
        <label class="field field-wide"><span>月報＋請款單收件人（逗號分隔）</span><input type="text" id="ncReportRecipients"></label>
      </div>
      <label class="field field-wide"><span>備註</span><input type="text" id="ncNotes"></label>
      <button type="button" class="btn-sm" data-nc-submit>建立公司</button>
      <div id="newClientNote"></div>
    </div>`;
    mo.hidden=false;
    if(layout) layout.inert=true;
    const onKey=(e)=>{ if(e.key==="Escape") close(); };
    const onOverlay=(e)=>{ if(e.target===mo) close(); };
    const close=()=>{ mo.hidden=true; if(layout) layout.inert=false; document.removeEventListener("keydown",onKey); mo.removeEventListener("click",onOverlay); if(previous&&previous.focus) previous.focus(); };
    mo.querySelectorAll("[data-nc-close]").forEach((b)=>b.addEventListener("click",close));
    mo.addEventListener("click",onOverlay);
    document.addEventListener("keydown",onKey);
    const submitBtn=mo.querySelector("[data-nc-submit]");
    if(submitBtn) submitBtn.addEventListener("click",()=>{
      const body=entCollectClientForm("nc");
      if(!body.name){ entActionNote("newClientNote", `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>請填公司名稱</strong></div>`); return; }
      const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
      postAdmin(base, token, "/admin/enterprise/client/save", body)
        .then(()=>{ close(); reloadEnterpriseClients(); renderPage(state.page); })
        .catch((e)=>entActionNote("newClientNote", entActionError((e&&e.message)||"fail")));
    });
    const closeBtn=mo.querySelector("[data-nc-close]"); if(closeBtn) closeBtn.focus();
  }
  const ENT_GRANT_REASON_ZH = {
    enterprise_invoice_not_paid: "這家公司還沒有已收款的請款單，付款確認前不能開通",
    seat_has_no_bound_account: "這個席次還沒有綁定帳號（email 還沒註冊比對成功）",
    seat_must_be_active_or_waiting_to_grant_membership: "這個席次狀態還不能授予",
    enterprise_seat_not_found: "找不到這個席次",
    enterprise_client_not_found: "找不到這家公司",
  };
  function entGrantReasonZh(code){ return ENT_GRANT_REASON_ZH[code] || code || "原因不明"; }
  function entGrantSeats(clientId){
    const boxes=[...$("pageRoot").querySelectorAll(".ent-seat-chk:checked")].map((b)=>b.value);
    if(!boxes.length){ entActionNote("entGrantNote", `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>請先勾選席次</strong></div>`); return; }
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/seats/grant", { clientId, seatIds:boxes })
      .then((p)=>{
        const sm=p.summary||{}, blocked=(p.results||[]).filter((x)=>!x.ok);
        let msg=`<div class="ops-notice info" role="status" style="margin-top:10px"><strong>已處理 ${sm.total!=null?sm.total:boxes.length} 筆</strong>開通 ${sm.granted||0}${sm.waiting?`・轉為等待 ${sm.waiting}`:""}${sm.blocked?`・被擋下 ${sm.blocked}`:""}</div>`;
        if(blocked.length) msg+=`<div class="ops-notice warn" role="alert" style="margin-top:8px"><strong>被擋下的原因</strong>${blocked.map((x)=>esc(entGrantReasonZh(x.error))).join("；")}</div>`;
        entActionNote("entGrantNote", msg);
        reloadEnterpriseClients(); setTimeout(()=>loadEnterpriseClientDetail(clientId),1800);
      })
      .catch((e)=>entActionNote("entGrantNote", entActionError((e&&e.message)||"fail")));
  }

  // ── 畫面 3・名單匯入 ──
  function renderEnterpriseImport(){
    const c=ensureEnterpriseClientsLoaded();
    const guard=entLoadingOrErrorCard(c.status,c.error,"名單匯入","data-ent-retry-clients");
    if(guard) return guard;
    const clients=entClients();
    const im=state.tabs.entImport||(state.tabs.entImport={ clientId:"", fileName:"", fileText:"", previewing:false, preview:null, committing:false, result:null, error:null });
    if(!im.clientId && clients.length===1) im.clientId=String(clients[0].id);
    const clientOpts=clients.map((x)=>`<option value="${esc(x.id)}"${String(im.clientId)===String(x.id)?" selected":""}>${esc(x.name)}</option>`).join("");
    let html=card("名單匯入","先選公司，下載範本填好 email 清單，再上傳預檢", `
      <div class="ent-form-grid">
        <label class="field"><span>目標公司</span><select id="entImportClient">${clients.length?`<option value="">請選擇</option>${clientOpts}`:`<option value="">還沒有企業客戶</option>`}</select></label>
      </div>
      <div class="rowflex" style="margin-top:6px">
        <button type="button" class="btn-ghost btn-sm" data-ent-template>下載範本 CSV</button>
        <label class="btn-sm" style="display:inline-flex;align-items:center;cursor:pointer" for="entImportFile">上傳名單 CSV</label>
        <input type="file" id="entImportFile" accept=".csv,text/csv" style="display:none">
        <span class="muted small">${im.fileName?esc(im.fileName):"尚未選擇檔案"}</span>
      </div>
      <div id="entImportNote"></div>
    `);
    if(im.previewing){ html+=card("預檢結果","讀取中",emptyBox("正在比對名單…")); return html; }
    if(im.preview){
      const p=im.preview;
      const groups=[["newSeats","新增"],["alreadyRegistered","已註冊・匯入後直接生效"],["duplicates","重複・會跳過"],["ownedByOtherClient","屬於其他公司・已擋下"],["overQuota","超過席次上限"]];
      html+=`<div class="kpi-row">${groups.map(([key,label])=>`<div class="kpi"><div class="kpi-top"><span class="kpi-label">${esc(label)}</span></div><div class="kpi-value">${n((p[key]||[]).length)}</div></div>`).join("")}</div>`;
      html+=groups.map(([key,label])=>{
        const list=p[key]||[];
        if(!list.length) return "";
        const rows=list.map((r)=>[esc(r.email||r),esc(r.note||r.reason||"")]);
        return card(`${label}（${list.length} 筆）`,"",tableHTML(["Email","備註／原因"],rows));
      }).join("");
      const hasOverQuota=(p.overQuota||[]).length>0;
      html+=`<div class="card"><div class="card-head"><div><h3>確認匯入</h3><div class="card-note">${hasOverQuota?"含超過席次上限的筆數，匯入前會再確認一次":"確認後才會真的寫入名單"}</div></div></div>
        <button type="button" class="btn-sm" data-ent-import-commit ${im.committing?"disabled":""}>${im.committing?"匯入中…":"確認匯入"}</button>
        <div id="entImportCommitNote"></div>
      </div>`;
    }
    if(im.result){
      const r=im.result, created=r.created||[], activated=r.activated||[], skipped=r.skipped||[], fail=r.failed||[];
      const okCount=r.summary?(r.summary.createdCount||0)+(r.summary.activatedCount||0):created.length+activated.length;
      html+=card("匯入結果", `成功 ${okCount} 筆（新增 ${created.length}・已註冊直接生效 ${activated.length}）・跳過 ${skipped.length} 筆・失敗 ${fail.length} 筆`, `
        ${fail.length?tableHTML(["Email","失敗原因"],fail.map((x)=>[esc(x.email||x),esc(x.error||x.reason||"")])):""}
        ${skipped.length?tableHTML(["Email","跳過原因"],skipped.map((x)=>[esc(x.email||x),esc(entSkipReasonZh(x.skipReason))])):""}
        ${(!fail.length&&!skipped.length)?emptyBox("全部成功，沒有跳過或失敗的筆數。"):""}
        <button type="button" class="btn-ghost btn-sm" style="margin-top:10px" data-ent-import-download>下載結果清單</button>
      `);
    }
    return html;
  }
  function entDownloadTemplate(){
    const im=state.tabs.entImport||{};
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/seats/export", { clientId: im.clientId||"", template:true })
      .then((p)=>downloadTextFile(p.filename||"munea-enterprise-seat-template.csv", p.csv||"email,備註\n", "text/csv;charset=utf-8;"))
      .catch((e)=>entActionNote("entImportNote", entActionError((e&&e.message)||"fail")));
  }
  function entRunImportPreview(){
    const im=state.tabs.entImport||(state.tabs.entImport={});
    if(!im.clientId){ entActionNote("entImportNote", entActionError("no_client_selected")); return; }
    im.previewing=true; im.preview=null; im.result=null;
    renderPage(state.page);
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/seats/import-preview", { clientId: im.clientId, csv: im.fileText })
      .then((p)=>{ im.previewing=false; im.preview=p; renderPage(state.page); })
      .catch((e)=>{ im.previewing=false; renderPage(state.page); entActionNote("entImportNote", entActionError((e&&e.message)||"fail")); });
  }
  function entRunImportCommit(){
    const im=state.tabs.entImport||{};
    const doCommit=()=>{
      im.committing=true; renderPage(state.page);
      const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
      const overQuotaList=(im.preview&&im.preview.overQuota)||[];
      postAdmin(base, token, "/admin/enterprise/seats/import-commit", { clientId: im.clientId, csv: im.fileText, confirmOverQuota: overQuotaList.length>0 })
        .then((p)=>{ im.committing=false; im.result=p; im.preview=null; reloadEnterpriseClients(); renderPage(state.page); })
        .catch((e)=>{ im.committing=false; renderPage(state.page); entActionNote("entImportCommitNote", entActionError((e&&e.message)||"fail")); });
    };
    const overQuota=(im.preview&&im.preview.overQuota)||[];
    if(overQuota.length){
      openConfirmModal({
        title:"這批名單會超過合約席次上限",
        bodyHtml:`<p>其中 <b>${overQuota.length}</b> 筆會讓已啟用席次超過合約上限，確定要照樣匯入嗎？超過的部分需要額外跟客戶確認加購。</p>`,
        confirmLabel:"照樣匯入", danger:true, onConfirm:doCommit,
      });
    } else { doCommit(); }
  }
  const ENT_SKIP_REASON_ZH = { duplicate:"重複", over_quota:"超過席次上限（未確認匯入）", owned_by_other_client:"屬於其他公司" };
  function entSkipReasonZh(code){ return ENT_SKIP_REASON_ZH[code] || code || "跳過"; }
  function entDownloadImportResult(){
    const im=state.tabs.entImport||{}, r=im.result||{};
    const created=r.created||[], activated=r.activated||[], skipped=r.skipped||[], fail=r.failed||[];
    const lines=["email,結果,原因"];
    created.forEach((x)=>lines.push(`${x.email||x},新增,`));
    activated.forEach((x)=>lines.push(`${x.email||x},已註冊直接生效,`));
    skipped.forEach((x)=>lines.push(`${x.email||x},跳過,${entSkipReasonZh(x.skipReason)}`));
    fail.forEach((x)=>lines.push(`${x.email||x},失敗,${String(x.error||x.reason||"").replace(/,/g," ")}`));
    downloadTextFile("munea-enterprise-import-result.csv", lines.join("\n"), "text/csv;charset=utf-8;");
  }

  // ── 畫面 4・收款登記 ──
  function entClientNameOf(clientId){
    const list=entClients(); const hit=list.find((c)=>String(c.id)===String(clientId));
    return hit?hit.name:(clientId||"–");
  }
  function renderEnterprisePayments(){
    const iv0=ensureEnterpriseInvoicesLoaded();
    const guard=entLoadingOrErrorCard(iv0.status,iv0.error,"收款登記","data-ent-retry-invoices");
    if(guard) return guard;
    ensureEnterpriseClientsLoaded(); // 請款單只存 enterpriseClientId，借企業客戶清單對照公司名（非阻擋、背景載入完自動重繪）
    const invoices=entInvoices();
    const filt=state.tabs.entPayFilter||"all";
    const counts={ all:invoices.length, draft:0, issued:0, paid:0, overdue:0 };
    invoices.forEach((iv)=>{
      if(iv.status==="draft") counts.draft++;
      else if(["issued","sent"].includes(iv.status)) counts.issued++;
      else if(["paid","invoiced"].includes(iv.status)) counts.paid++;
      if(Number(iv.overdueDays||0)>0 && !["paid","invoiced","void"].includes(iv.status)) counts.overdue++;
    });
    const chip=(id,label,cnt)=>`<button type="button" class="chip-filter${filt===id?" on":""}" data-ent-pay-filter="${id}" aria-pressed="${filt===id?"true":"false"}">${esc(label)} <span class="c">${cnt}</span></button>`;
    const tools=`<div class="tbl-tools">${chip("all","全部",counts.all)}${chip("draft","草稿・待確認",counts.draft)}${chip("issued","已寄出・待收款",counts.issued)}${chip("paid","已收款",counts.paid)}<span class="chip-sep"></span>${chip("overdue","逾期",counts.overdue)}<span class="chip-spring"></span><button type="button" class="btn-sm" data-ent-monthly-close>跑月結（產生本月請款單）</button></div>`;
    let html=entBillingSettingsWarningHTML();
    if(!invoices.length){
      html+=card("請款單列表","登記收款、標記已入帳", `${tools}${emptyBox("還沒有請款單——跑過月結後會出現。")}`);
      html+=`<div id="entPayActionNote"></div>`;
      return html;
    }
    const filtered=invoices.filter((iv)=>{
      if(filt==="overdue") return Number(iv.overdueDays||0)>0 && !["paid","invoiced","void"].includes(iv.status);
      if(filt==="draft") return iv.status==="draft";
      if(filt==="issued") return ["issued","sent"].includes(iv.status);
      if(filt==="paid") return ["paid","invoiced"].includes(iv.status);
      return true;
    });
    const openId=state.tabs.entPayOpenId;
    const rowsHtml=filtered.map((iv)=>{
      const overdue=Number(iv.overdueDays||0)>0 && !["paid","invoiced","void"].includes(iv.status);
      const isOpen=String(openId)===String(iv.id);
      let actions="";
      if(iv.status==="draft") actions=`<button type="button" class="btn-ghost btn-sm" data-ent-mark-sent="${esc(iv.id)}">已寄出</button>`;
      else if(["issued","sent"].includes(iv.status)) actions=`<button type="button" class="btn-ghost btn-sm" data-ent-pay-toggle="${esc(iv.id)}">${isOpen?"收合":"登記收款"}</button>`;
      else actions=`<span class="pill ok">已入帳</span>`;
      const payForm=isOpen?`
        <tr class="ent-pay-form-row"><td colspan="7">
          <div class="ent-form-grid">
            <label class="field"><span>實際入帳日</span><input type="date" id="epPaidAt-${esc(iv.id)}"></label>
            <label class="field"><span>實收金額 (NT$)</span><input type="number" id="epPaidAmount-${esc(iv.id)}" value="${esc(iv.totalTwd||0)}"></label>
            <label class="field"><span>匯款備註（末五碼等）</span><input type="text" id="epPaidNote-${esc(iv.id)}" placeholder="對帳用"></label>
          </div>
          <button type="button" class="btn-danger btn-sm" data-ent-mark-paid="${esc(iv.id)}">已入帳</button>
          <div id="entPayNote-${esc(iv.id)}"></div>
        </td></tr>`:"";
      return `<tr class="${overdue?"tr-overdue":""}">
        <td><b>${esc(iv.invoiceNo||iv.id||"–")}</b></td>
        <td>${esc(iv.clientName||entClientNameOf(iv.enterpriseClientId))}</td>
        <td>${esc(fmtDate(iv.periodStart))} － ${esc(fmtDate(iv.periodEnd))}</td>
        <td>${fmtMoney(iv.totalTwd)}</td>
        <td>${entInvoiceStatusPill(iv.status)}</td>
        <td>${overdue?`<b style="color:var(--danger)">逾期 ${n(iv.overdueDays)} 天</b><div class="small" style="color:var(--danger)">欠 ${fmtMoney(iv.totalTwd)}</div>`:`<span class="muted">—</span>`}</td>
        <td>${actions}</td>
      </tr>${payForm}`;
    }).join("");
    html+=`<div class="card tbl-card"><div class="card-head"><div><h3>請款單列表</h3><div class="card-note">按「已寄出」記寄出日、按「登記收款」填入帳資料後「已入帳」＝開通開關</div></div></div>${tools}<div class="table-wrap"><table><thead><tr><th>單號</th><th>公司</th><th>期間</th><th>金額</th><th>狀態</th><th>逾期</th><th></th></tr></thead><tbody>${rowsHtml}</tbody></table></div></div>`;
    html+=`<div id="entPayActionNote"></div>`;
    return html;
  }
  function entMarkSent(invoiceId){
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/invoice/mark-sent", { invoiceId })
      .then(()=>{ reloadEnterpriseInvoices(); })
      .catch((e)=>entActionNote("entPayActionNote", entActionError((e&&e.message)||"fail")));
  }
  function entMarkPaid(invoiceId){
    const invoices=entInvoices();
    const iv=invoices.find((x)=>String(x.id)===String(invoiceId));
    const paidAtEl=$("epPaidAt-"+invoiceId), paidAmountEl=$("epPaidAmount-"+invoiceId), paidNoteEl=$("epPaidNote-"+invoiceId);
    const paidAt=paidAtEl?paidAtEl.value:"";
    const paidAmount=Number(paidAmountEl?paidAmountEl.value:0)||0;
    const paymentNote=paidNoteEl?paidNoteEl.value:"";
    if(!paidAt){ entActionNote("entPayNote-"+invoiceId, `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>請填入帳日</strong>刷本子看到入帳的那一天。</div>`); return; }
    const seats=iv&&(iv.billableSeats!=null?iv.billableSeats:iv.activeSeats);
    openConfirmModal({
      title:"確定要標記已入帳嗎？",
      bodyHtml:`<p><b>即將開通 ${seats!=null?n(seats):"這批"} 個席次</b>，這個動作沒有辦法復原，請先確認款項真的已經入帳再按。</p><p class="muted small">公司：${esc(iv?(iv.clientName||entClientNameOf(iv.enterpriseClientId)):"–")}・單號：${esc((iv&&iv.invoiceNo)||invoiceId)}・入帳日：${esc(paidAt)}・實收：${fmtMoney(paidAmount)}</p>`,
      confirmLabel:"確定已入帳，開通", danger:true,
      onConfirm:()=>{
        const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
        postAdmin(base, token, "/admin/enterprise/invoice/mark-paid", { invoiceId, paidAt, paidAmountTwd:paidAmount, paymentNote })
          .then(()=>{ state.tabs.entPayOpenId=null; reloadEnterpriseInvoices(); reloadEnterpriseClients(); })
          .catch((e)=>entActionNote("entPayNote-"+invoiceId, entActionError((e&&e.message)||"fail")));
      },
    });
  }
  function entRunMonthlyClose(){
    openConfirmModal({
      title:"要跑這個月的月結嗎？",
      bodyHtml:`<p>會依目前每家公司「月底仍為使用中」的席次數，自動產出<b>請款單（草稿）</b>與 <b>ESG 成效月報</b>。請款單產出後還是草稿，需要人工確認才會轉成正式寄出。</p>`,
      confirmLabel:"開始跑月結",
      onConfirm:()=>{
        const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
        postAdmin(base, token, "/admin/enterprise/monthly-close", {})
          .then(()=>reloadEnterpriseInvoices())
          .catch((e)=>entActionNote("entPayActionNote", entActionError((e&&e.message)||"fail")));
      },
    });
  }

  function ENT_BS_COMPANY_FORM_HTML(bs){
    return `
      <div class="ent-form-grid">
        <label class="field"><span>開票公司抬頭</span><input type="text" id="bsIssuerCompanyName" value="${esc(bs.issuerCompanyName||"")}" placeholder="例：沐寧股份有限公司"></label>
        <label class="field"><span>統一編號</span><input type="text" id="bsIssuerTaxId" value="${esc(bs.issuerTaxId||"")}"></label>
        <label class="field field-wide"><span>公司地址</span><input type="text" id="bsIssuerAddress" value="${esc(bs.issuerAddress||"")}"></label>
        <label class="field"><span>聯絡電話</span><input type="text" id="bsIssuerPhone" value="${esc(bs.issuerPhone||"")}"></label>
        <label class="field"><span>聯絡人</span><input type="text" id="bsIssuerContactName" value="${esc(bs.issuerContactName||"")}"></label>
      </div>
    `;
  }
  function ENT_BS_BANK_FORM_HTML(bs){
    return `
      <div class="ops-notice warn" role="alert" style="margin-bottom:14px"><strong>帳號是敏感資料</strong>畫面上預設遮蔽，按「顯示」才會露出完整號碼，避免截圖外流。</div>
      <div class="ent-form-grid">
        <label class="field"><span>收款銀行</span><input type="text" id="bsBankName" value="${esc(bs.bankName||"")}"></label>
        <label class="field"><span>分行</span><input type="text" id="bsBankBranch" value="${esc(bs.bankBranch||"")}"></label>
        <label class="field"><span>戶名</span><input type="text" id="bsBankAccountName" value="${esc(bs.bankAccountName||"")}"></label>
        <label class="field"><span>帳號</span>
          <div class="token-wrap">
            <input type="password" id="bsBankAccountNo" value="${esc(bs.bankAccountNo||"")}" autocomplete="off">
            <button type="button" class="eye-btn" data-ent-toggle-mask="bsBankAccountNo">顯示</button>
          </div>
        </label>
      </div>
    `;
  }
  function ENT_BS_OTHER_FORM_HTML(bs){
    return `
      <div class="ent-form-grid">
        <label class="field"><span>付款期限天數</span><input type="number" id="bsPaymentTermsDays" value="${esc(bs.paymentTermsDays!=null?bs.paymentTermsDays:15)}"><small class="muted">對應需求單「次月 15 日前」——從帳單期間結束日起算天數，預設 15 天，可調</small></label>
        <label class="field field-wide"><span>請款單備註</span><input type="text" id="bsInvoiceFooterNote" value="${esc(bs.invoiceFooterNote||"")}" placeholder="例：請於匯款後回傳水單"></label>
      </div>
      <button type="button" class="btn-sm" data-ent-save-billing-settings>儲存變更</button>${bs.updatedAt?`<span class="muted small" style="margin-left:10px">上次更新：${esc(fmtTime(bs.updatedAt))}${bs.updatedBy?("（"+esc(bs.updatedBy)+"）"):""}</span>`:""}
      <div id="entBillingSaveNote"></div>
    `;
  }
  function renderEnterpriseBillingSettings(){
    const c=ensureEnterpriseBillingSettingsLoaded();
    const guard=entLoadingOrErrorCard(c.status,c.error,"開票與收款設定","data-ent-retry-billing-settings");
    if(guard) return guard;
    const bs=(c.data&&c.data.settings)||{};
    const missing=entBillingSettingsMissing(bs);
    let html=missing.length?("<div class=\"ops-notice warn\" role=\"alert\"><strong>還沒填完</strong>還缺「"+missing.map((x)=>esc(x)).join("、")+"」——沒填的欄位，月結產出的請款單會印不出正確資訊。</div>"):"";
    html+=card("開票資訊","印在請款單抬頭的公司資料", ENT_BS_COMPANY_FORM_HTML(bs));
    html+=card("收款資訊","印在請款單上的匯款帳戶", ENT_BS_BANK_FORM_HTML(bs));
    html+=card("其他","付款期限與請款單上的備註", ENT_BS_OTHER_FORM_HTML(bs));
    return html;
  }
  function entCollectBillingSettingsForm(){
    const g=(id)=>{ const el=$(id); return el?el.value:""; };
    return {
      issuerCompanyName:g("bsIssuerCompanyName").trim(), issuerTaxId:g("bsIssuerTaxId").trim(), issuerAddress:g("bsIssuerAddress").trim(),
      issuerPhone:g("bsIssuerPhone").trim(), issuerContactName:g("bsIssuerContactName").trim(),
      bankName:g("bsBankName").trim(), bankBranch:g("bsBankBranch").trim(),
      bankAccountName:g("bsBankAccountName").trim(), bankAccountNo:g("bsBankAccountNo").trim(),
      paymentTermsDays:Number(g("bsPaymentTermsDays"))||15, invoiceFooterNote:g("bsInvoiceFooterNote").trim(),
    };
  }
  function entSaveBillingSettings(){
    const body=entCollectBillingSettingsForm();
    if(!body.issuerCompanyName){ entActionNote("entBillingSaveNote", `<div class="ops-notice warn" role="alert" style="margin-top:10px"><strong>請填開票公司抬頭</strong></div>`); return; }
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY), base=state.base||initialBaseUrl();
    postAdmin(base, token, "/admin/enterprise/billing-settings/save", body)
      .then(()=>{
        entActionNote("entBillingSaveNote", `<div class="ops-notice info" role="status" style="margin-top:10px"><strong>已儲存</strong>之後產出的請款單會套用這份資料。</div>`);
        setTimeout(reloadEnterpriseBillingSettings, 1600);
      })
      .catch((e)=>entActionNote("entBillingSaveNote", entActionError((e&&e.message)||"fail")));
  }

  // ══════════ 設定頁 ══════════
  // 訂閱試算（規劃計算機）——原本埋在「連線設定」頁，2026-07-20 併入「訂閱與點數」頁
  function assumeCardHTML(){
    const a=loadAssume();
    return `
    ${card("訂閱試算（規劃工具·不是真數字）", "填你的預期值，即時算 LTV／CAC／回本。這是規劃用的計算機，不是後台的真實數據。", `
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
    `)}`;
  }

  // ══════════ 連線 ══════════
  function initialBaseUrl(){ const s=storageGet(localStorage,ADMIN_BASE_KEY); if(s) return s; if(location.protocol.startsWith("http")) return location.origin; return DEFAULT_LOCAL_API; }
  function envLabelFor(u){ if(/munea-brain-staging/.test(u))return "雲端試營運"; if(/127\.0\.0\.1|localhost/.test(u))return "這台電腦（本機）"; if(/run\.app/.test(u))return "雲端伺服器"; return u.replace(/^https?:\/\//,"")||"–"; }
  function setStatus(t,k){
    const sp=$("statusPill"); if(sp){ sp.textContent=t; sp.className="status-pill"+(k?" "+k:""); }
    const r=$("envRole"); if(r) r.textContent=state.connected?envLabelFor(state.base||initialBaseUrl()):(t||"");
    const out=$("logoutBtn"); if(out) out.hidden=!state.connected;
  }
  function setBusy(on){
    state.loading=!!on;
    const root=$("pageRoot"); if(root) root.setAttribute("aria-busy",on?"true":"false");
    const refresh=$("refreshBtn"); if(refresh) refresh.disabled=!!on;
  }

  async function timedFetch(url,options){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
    try{ return await fetch(url,Object.assign({},options||{},{signal:controller.signal})); }
    catch(e){ if(e&&e.name==="AbortError") throw new Error("request_timeout"); throw e; }
    finally{ clearTimeout(timer); }
  }
  async function postAdmin(base, token, path, body){
    const safeBase=normalizeAdminBaseUrl(base);
    const res=await timedFetch(safeBase+path,{method:"POST",headers:requestHeaders({"Content-Type":"application/json; charset=utf-8","X-Munea-Admin-Token":token}),body:JSON.stringify(body||{})});
    const txt=await res.text(); let p={}; try{ p=txt?JSON.parse(txt):{}; }catch(e){ p={ok:false,error:{code:"invalid_json"}}; }
    if(!res.ok||p.ok===false){ const code=typeof p.error==="string"?p.error:(p.error&&p.error.code); throw new Error(code||("http_"+res.status)); }
    return p;
  }
  function explainErr(m){ m=String(m||""); if(/invalid_admin_token/.test(m))return "通行碼已失效或不正確"; if(/admin_token_not_configured/.test(m))return "伺服器還沒設通行碼"; if(/invalid_admin_url/.test(m))return "伺服器網址格式不正確"; if(/insecure_admin_url/.test(m))return "遠端伺服器必須使用 HTTPS"; if(/untrusted_admin_host/.test(m))return "這個伺服器不在後台允許清單內"; if(/request_timeout/.test(m))return "伺服器超過 15 秒沒有回應"; if(/invalid_json/.test(m))return "伺服器回應格式異常"; if(/http_40[13]/.test(m))return "被大門擋住（權限／通行碼）"; if(/Failed to fetch|NetworkError|load failed/i.test(m))return "連不到伺服器"; return "服務暫時異常（"+m.slice(0,80)+"）"; }

  // 抓所有真資料（登入成功、貼通行碼、開頁自動連線 三處共用）
  async function loadAll(base, token){
    const safeBase=normalizeAdminBaseUrl(base),keys=Object.keys(EP_LIST);
    state.base=safeBase; state.token=token; setBusy(true);
    try{
      const rs=await Promise.allSettled(keys.map((k)=>postAdmin(safeBase,token,EP_LIST[k][0],EP_LIST[k][1])));
      const data={},errors={};
      rs.forEach((r,i)=>{
        if(r.status==="fulfilled"){
          const payload=r.value||{};
          payload.meta=normalizeDataMeta(payload,keys[i]);
          data[keys[i]]=payload;
        }else errors[keys[i]]=(r.reason&&r.reason.message)||"fail";
      });
      state.data=data; state.errors=errors; state.connected=Object.keys(data).length>0;
      const errValues=Object.values(errors);
      if(!state.connected&&errValues.length&&errValues.every((m)=>/invalid_admin_token/.test(m))){ storageRemove(sessionStorage,ADMIN_TOKEN_KEY); state.token=""; }
      if($("rawOut")) $("rawOut").textContent=JSON.stringify({data,errors},null,2);
      if($("lastUpdated")){
        const q=dataQualitySummary();
        $("lastUpdated").textContent=state.connected?(q.dataAsOf?`資料更新到 ${fmtTime(q.dataAsOf)}`:`剛剛抓的（${fmtTime(new Date().toISOString())}）`):"";
      }
      renderSide(); renderPage(state.page);
      return { ok: state.connected, failed: errValues.length, total: keys.length, firstErr: errValues[0] };
    }finally{ setBusy(false); }
  }

  async function connect(){
    const rawBase=($("apiBaseUrl")?.value||initialBaseUrl()).trim();
    const token=($("adminToken")?.value||"").trim();
    if(!token){ setStatus("要先貼通行碼","error"); return; }
    try{
      const base=normalizeAdminBaseUrl(rawBase);
      try{ localStorage.setItem(ADMIN_BASE_KEY,base); }catch(e){}
      if($("rememberToken")?.checked) storageSet(sessionStorage,ADMIN_TOKEN_KEY,token); else storageRemove(sessionStorage,ADMIN_TOKEN_KEY);
      setStatus("讀取中…","");
      const r=await loadAll(base,token);
      if(r.failed===0) setStatus("已連線","ok");
      else if(r.failed===r.total){ setStatus("連線失敗","error"); if($("connectHint"))$("connectHint").textContent="連線失敗："+explainErr(r.firstErr); }
      else setStatus("有 "+r.failed+" 區讀不到","warn");
    }catch(e){ setStatus("連線失敗","error"); if($("connectHint"))$("connectHint").textContent=explainErr(e&&e.message); }
  }
  async function refreshData(){
    const token=state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY),base=state.base||initialBaseUrl();
    if(!token){ state.connected=false; setStatus("需要重新登入","error"); showLoginGate(); return; }
    setStatus("讀取中…","");
    try{
      const r=await loadAll(base,token);
      if(r.failed===0) setStatus("已連線","ok");
      else if(r.failed===r.total){ setStatus("連線失敗","error"); if(!state.token) showLoginGate(); }
      else setStatus("有 "+r.failed+" 區讀不到","warn");
    }catch(e){ setStatus("連線失敗","error"); state.errors={connection:(e&&e.message)||"fail"}; renderPage(state.page); }
  }

  // ══════════ 登入門（帳密 → 換後台通行碼） ══════════
  function loginGateHTML(){
    return `<form class="login-card" id="loginForm" aria-labelledby="loginTitle">
      <div class="login-brand">Mu<b>nea</b><span class="login-zh">沐寧</span></div>
      <div class="login-title" id="loginTitle">營運後台</div>
      <p class="login-sub">請輸入帳號與密碼登入</p>
      <label class="login-field"><span>帳號（Email）</span><input id="loginEmail" type="email" autocomplete="username" placeholder="you@example.com" spellcheck="false"></label>
      <label class="login-field"><span>密碼</span><input id="loginPassword" type="password" autocomplete="current-password" placeholder="密碼"></label>
      <button type="submit" class="login-btn" id="loginBtn">登入</button>
      <div class="login-hint" id="loginHint" role="status" aria-live="polite"></div>
    </form>`;
  }
  function removeLoginGate(){ const g=$("loginGate"); if(g) g.remove(); const layout=document.querySelector(".layout"); if(layout){ layout.inert=false; layout.removeAttribute("aria-hidden"); } }
  function showLoginGate(){
    if($("loginGate")) return;
    const layout=document.querySelector(".layout"); if(layout){ layout.inert=true; layout.setAttribute("aria-hidden","true"); }
    const g=document.createElement("div"); g.id="loginGate"; g.className="login-gate"; g.setAttribute("role","dialog"); g.setAttribute("aria-modal","true"); g.innerHTML=loginGateHTML();
    document.body.appendChild(g);
    $("loginForm")?.addEventListener("submit",(e)=>{ e.preventDefault(); doLogin(); });
    setTimeout(()=>$("loginEmail")?.focus(),50);
  }
  async function doLogin(){
    const email=($("loginEmail")?.value||"").trim();
    const password=($("loginPassword")?.value||"");
    const hint=$("loginHint");
    if(!email||!password){ if(hint){ hint.textContent="請輸入帳號和密碼"; hint.className="login-hint err"; } return; }
    if(hint){ hint.textContent="登入中…"; hint.className="login-hint"; }
    if($("loginBtn")) $("loginBtn").disabled=true;
    let base;
    try{
      base=normalizeAdminBaseUrl(initialBaseUrl());
      const res=await timedFetch(base+"/admin/login",{method:"POST",headers:requestHeaders({"Content-Type":"application/json; charset=utf-8"}),body:JSON.stringify({email,password})});
      const p=await res.json().catch(()=>({}));
      if(p&&p.ok&&p.token){
        storageSet(sessionStorage,ADMIN_TOKEN_KEY,p.token);
        try{ localStorage.setItem(ADMIN_BASE_KEY,base); }catch(e){}
        state.token=p.token; state.base=base;
        removeLoginGate();
        setStatus("讀取中…","");
        const r=await loadAll(base, p.token);
        setStatus(r.ok?(r.failed?"部分資料異常":"已連線"):"連線異常",r.ok?(r.failed?"warn":"ok"):"error");
        if(!r.ok) showLoginGate();
      } else {
        const map={too_many_attempts:"錯太多次了，先等 10 分鐘再試",invalid_credentials:"帳號或密碼不對",login_not_configured:"伺服器還沒設定登入（跟蘇菲說一聲）"};
        if(hint){ hint.textContent=map[p&&p.error]||"登入失敗，再試一次"; hint.className="login-hint err"; }
      }
    }catch(e){ if(hint){ hint.textContent=explainErr(e&&e.message); hint.className="login-hint err"; } }
    finally{ if($("loginBtn")) $("loginBtn").disabled=false; }
  }
  function logout(){
    storageRemove(sessionStorage,ADMIN_TOKEN_KEY);
    state.token=""; state.data=null; state.errors={}; state.connected=false;
    if($("lastUpdated")) $("lastUpdated").textContent="";
    setStatus("已登出",""); renderSide(); show(); showLoginGate();
  }

  // ══════════ 訂閱試算（計算機·設定頁） ══════════
  const ASSUME_DEF={plusPrice:599,proPrice:1199,plusCount:0,proCount:0,newPaid:0,marketing:0,lifeMonths:12};
  function loadAssume(){ try{ return {...ASSUME_DEF, ...JSON.parse(localStorage.getItem(ASSUME_KEY)||"{}")}; }catch(e){ return {...ASSUME_DEF}; } }
  function calcAssume(){
    const g=(id)=>Number($(id)?.value)||0;
    const a={plusPrice:g("aPlusPrice"),proPrice:g("aProPrice"),plusCount:g("aPlusCount"),proCount:g("aProCount"),newPaid:g("aNewPaid"),marketing:g("aMarketing"),lifeMonths:Math.max(1,g("aLifeMonths"))};
    localStorage.setItem(ASSUME_KEY,JSON.stringify(a));
    const paid=a.plusCount+a.proCount, mrr=a.plusCount*a.plusPrice+a.proCount*a.proPrice;
    const arpu=paid?mrr/paid:null, ltv=arpu!=null?arpu*a.lifeMonths:null, cac=a.newPaid?a.marketing/a.newPaid:null, ratio=(ltv!=null&&cac)?ltv/cac:null;
    if($("assumeOut")) $("assumeOut").innerHTML=`MRR <b>${fmtMoney(mrr)}</b> · ARPU ${arpu!=null?fmtMoney(arpu):"–"} · LTV ${ltv!=null?fmtMoney(ltv):"–"} · CAC ${cac!=null?fmtMoney(cac):"填新增付費+行銷花費"} · <b>LTV:CAC ${ratio!=null?ratio.toFixed(1)+":1"+(ratio>=3?" 🟢":ratio>=1?" 🟡":" 🔴"):"–"}</b>`;
  }

  // ══════════ 導覽 ══════════
  function renderSide(){
    const badges={ safety: state.connected?String((D().safety||{}).totals?.requiresHumanEscalation||0):"", feedback: state.connected?String(((D().feedback||{}).latest||[]).length||0):"", care: state.connected?String(carePriorityRows().rows.filter((r)=>r.score>=60).length||0):"", entOverdue: state.connected?String(entClients().filter((c)=>c.statusLight==="overdue").length||0):"", entBillingMissing: state.connected?String(entBillingSettingsMissingCount()):"" };
    $("sideNav").innerHTML=NAV.map((g)=>`<div class="nav-group"><div class="nav-group-label">${esc(g.group)}</div><div class="side-nav">${g.items.map((it)=>{
      const bv=badges[it.badge]; const b= it.badge&&bv&&bv!=="0"?`<span class="nav-badge">${esc(bv)}</span>`:"";
      return `<a href="#${it.id}" data-page="${it.id}">${icon(it.id)}<span class="nav-label">${esc(it.label)}</span>${b}</a>`;
    }).join("")}</div></div>`).join("")
      // 隱私權指向本服務自帶的 /privacy.html：munea.net 仍掛在舊 Vercel 部署、/privacy 為 404（2026-07-20 實測）
      + `<div class="side-links"><a href="/" target="_blank" rel="noopener">App 本體</a><a href="/selftest.html" target="_blank" rel="noopener">自動巡檢</a><a href="https://munea.net" target="_blank" rel="noopener">官網</a><a href="/privacy.html" target="_blank" rel="noopener">隱私權</a></div>`;
    document.querySelectorAll("#sideNav a[data-page]").forEach((a)=>{ const on=a.dataset.page===state.page; a.classList.toggle("on",on); if(on)a.setAttribute("aria-current","page"); else a.removeAttribute("aria-current"); });
  }
  function go(id,arg){ if(!TITLE[id]) id="overview"; state.page=id; location.hash="#"+id+(arg?":"+arg:""); }
  function show(){
    const raw=(location.hash||"#overview").slice(1), sep=raw.indexOf(":");
    const id=sep>-1?raw.slice(0,sep):raw, arg=sep>-1?raw.slice(sep+1):"";
    state.page=TITLE[id]?id:"overview";
    if(arg) state.tabs.entClientId=arg;
    if($("crumb")) $("crumb").textContent=CRUMB[state.page]||"";
    if($("pageTitle")) $("pageTitle").textContent=TITLE[state.page]||"";
    document.querySelectorAll("#sideNav a[data-page]").forEach((a)=>{ const on=a.dataset.page===state.page; a.classList.toggle("on",on); if(on)a.setAttribute("aria-current","page"); else a.removeAttribute("aria-current"); });
    if(state.connected){ renderPage(state.page); }
    else { $("pageRoot").innerHTML=""; showLoginGate(); }
  }
  function bindPageEvents(id){
    $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto)));
    $("pageRoot").querySelectorAll("[data-retry]").forEach((b)=>b.addEventListener("click",refreshData));
    $("pageRoot").querySelectorAll("[data-relogin]").forEach((b)=>b.addEventListener("click",logout));
    $("pageRoot").querySelectorAll("[data-acct]").forEach((b)=>b.addEventListener("click",()=>openAcctDetail(+b.dataset.acct)));
    const us=$("userSearch"); if(us){ us.value=state.tabs.userSearch||""; us.addEventListener("input",()=>{ state.tabs.userSearch=us.value.trim(); renderPage("users"); const el=$("userSearch"); if(el){ el.focus(); el.setSelectionRange(el.value.length,el.value.length);} }); }
    $("pageRoot").querySelectorAll("[data-ufilter]").forEach((b)=>b.addEventListener("click",()=>{ state.tabs.userFilter=b.dataset.ufilter; renderPage("users"); }));
    // ══ 企業客戶（B2B 席次）══
    $("pageRoot").querySelectorAll("[data-ent-view]").forEach((b)=>b.addEventListener("click",()=>{ const cid=b.dataset.entView; state.tabs.entDetail=null; go("enterpriseClientDetail",cid); loadEnterpriseClientDetail(cid); }));
    $("pageRoot").querySelectorAll("[data-ent-new-client]").forEach((b)=>b.addEventListener("click",openNewClientModal));
    $("pageRoot").querySelectorAll("[data-ent-retry-clients]").forEach((b)=>b.addEventListener("click",()=>{ reloadEnterpriseClients(); renderPage(state.page); }));
    $("pageRoot").querySelectorAll("[data-ent-retry-invoices]").forEach((b)=>b.addEventListener("click",()=>{ reloadEnterpriseInvoices(); renderPage(state.page); }));
    $("pageRoot").querySelectorAll("[data-ent-retry-detail]").forEach((b)=>b.addEventListener("click",()=>loadEnterpriseClientDetail(b.dataset.entRetryDetail)));
    $("pageRoot").querySelectorAll("[data-ent-save-client]").forEach((b)=>b.addEventListener("click",()=>entSaveClient(b.dataset.entSaveClient)));
    $("pageRoot").querySelectorAll("[data-ent-grant]").forEach((b)=>b.addEventListener("click",()=>entGrantSeats(b.dataset.entGrant)));
    $("pageRoot").querySelectorAll("[data-ent-download]").forEach((b)=>b.addEventListener("click",()=>entDownloadReport(b.dataset.entClient, +b.dataset.entDownload)));
    const eic=$("entImportClient"); if(eic){ eic.value=(state.tabs.entImport&&state.tabs.entImport.clientId)||""; eic.addEventListener("change",()=>{ (state.tabs.entImport||(state.tabs.entImport={})).clientId=eic.value; }); }
    $("pageRoot").querySelectorAll("[data-ent-template]").forEach((b)=>b.addEventListener("click",entDownloadTemplate));
    const eif=$("entImportFile"); if(eif){ eif.addEventListener("change",()=>{
      const f=eif.files&&eif.files[0]; if(!f) return;
      const im=state.tabs.entImport||(state.tabs.entImport={});
      im.fileName=f.name; im.result=null;
      const reader=new FileReader();
      reader.onload=()=>{ im.fileText=String(reader.result||""); entRunImportPreview(); };
      reader.readAsText(f);
    }); }
    $("pageRoot").querySelectorAll("[data-ent-import-commit]").forEach((b)=>b.addEventListener("click",entRunImportCommit));
    $("pageRoot").querySelectorAll("[data-ent-import-download]").forEach((b)=>b.addEventListener("click",entDownloadImportResult));
    $("pageRoot").querySelectorAll("[data-ent-pay-filter]").forEach((b)=>b.addEventListener("click",()=>{ state.tabs.entPayFilter=b.dataset.entPayFilter; renderPage("enterprisePayments"); }));
    $("pageRoot").querySelectorAll("[data-ent-mark-sent]").forEach((b)=>b.addEventListener("click",()=>entMarkSent(b.dataset.entMarkSent)));
    $("pageRoot").querySelectorAll("[data-ent-pay-toggle]").forEach((b)=>b.addEventListener("click",()=>{ const idv=b.dataset.entPayToggle; state.tabs.entPayOpenId=(String(state.tabs.entPayOpenId)===String(idv))?null:idv; renderPage("enterprisePayments"); }));
    $("pageRoot").querySelectorAll("[data-ent-mark-paid]").forEach((b)=>b.addEventListener("click",()=>entMarkPaid(b.dataset.entMarkPaid)));
    $("pageRoot").querySelectorAll("[data-ent-monthly-close]").forEach((b)=>b.addEventListener("click",entRunMonthlyClose));
    $("pageRoot").querySelectorAll("[data-ent-retry-billing-settings]").forEach((b)=>b.addEventListener("click",()=>{ reloadEnterpriseBillingSettings(); renderPage(state.page); }));
    $("pageRoot").querySelectorAll("[data-ent-save-billing-settings]").forEach((b)=>b.addEventListener("click",entSaveBillingSettings));
    $("pageRoot").querySelectorAll("[data-ent-toggle-mask]").forEach((b)=>b.addEventListener("click",()=>{
      const fid=b.dataset.entToggleMask, el=$(fid); if(!el) return;
      const showing=el.type==="text";
      el.type=showing?"password":"text";
      b.textContent=showing?"顯示":"隱藏";
    }));
    if(id==="subscription"){
      ["aPlusPrice","aProPrice","aPlusCount","aProCount","aNewPaid","aMarketing","aLifeMonths"].forEach((i)=>$(i)?.addEventListener("input",calcAssume));
      calcAssume();
    }
  }

  function init(){
    if(window.MuneaVersion && $("appVer")) $("appVer").textContent="v"+window.MuneaVersion.current;
    renderSide();
    $("refreshBtn")?.addEventListener("click",()=>{ if(state.connected||state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY)) refreshData(); else showLoginGate(); });
    $("logoutBtn")?.addEventListener("click",logout);
    window.addEventListener("hashchange",show);
    setStatus("尚未連線","");
    show();
    const st=storageGet(sessionStorage,ADMIN_TOKEN_KEY);
    if(st){ state.token=st; (async()=>{ try{ const base=initialBaseUrl(); const r=await loadAll(base,st); if(r.ok){ removeLoginGate(); setStatus(r.failed?"部分資料異常":"已連線",r.failed?"warn":"ok"); } else { setStatus("需要重新登入","error"); showLoginGate(); } }catch(e){ setStatus("連線失敗","error"); showLoginGate(); } })(); }
    else { showLoginGate(); }
  }
  document.addEventListener("DOMContentLoaded",init);
})();
