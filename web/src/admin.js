(function () {
  "use strict";

  // ══════════ 選單：只保留「有真資料源」的頁（上線就緒·無假數據） ══════════
  const NAV = [
    { group: "營運總覽", items: [
      { id: "overview", label: "總覽儀表板" },
    ]},
    { group: "用戶與守護", items: [
      { id: "users", label: "用戶管理" },
      { id: "safety", label: "安全守護警示", badge: "safety" },
      { id: "medication", label: "用藥與回診" },
    ]},
    { group: "營收", items: [
      { id: "subscription", label: "訂閱與點數" },
    ]},
    { group: "服務與紀錄", items: [
      { id: "feedback", label: "用戶意見", badge: "feedback" },
      { id: "records", label: "系統紀錄" },
    ]},
    { group: "設定", items: [
      { id: "settings", label: "連線設定" },
    ]},
  ];
  const CRUMB = {}, TITLE = {};
  NAV.forEach((g) => g.items.forEach((it) => { CRUMB[it.id] = g.group; TITLE[it.id] = it.label; }));

  const ICON_PATHS = {
    overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M17 3.13a4 4 0 0 1 0 7.75"/>',
    safety: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    subscription: '<rect x="2" y="5" width="20" height="14" rx="2.5"/><path d="M2 10h20"/>',
    feedback: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
    records: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    medication: '<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
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
  function zh(map,v,f){ if(v==null||v==="")return f||"–"; return map[String(v).toLowerCase()]||String(v); }
  const RISK_ZH = { crisis:"🔴 危機", critical:"🔴 危機", high:"🔴 高風險", medium:"🟡 中風險", moderate:"🟡 中風險", low:"🟢 低風險", none:"低" };
  const FB_ZH = { bug:"問題回報", idea:"功能許願", praise:"稱讚", nps:"打分數" };
  const PV_ZH = { account_deletion:"刪除帳號", deletion:"刪除帳號", export:"資料副本", data_export:"資料副本", correction:"資料更正" };
  const ST_ZH = { pending:"待處理", open:"待處理", received:"已收到", processing:"處理中", done:"已完成", completed:"已完成", closed:"已結案" };
  const CREDIT_ZH = { subscription_monthly_allowance:"每月贈點", credit_grant:"發放點數", credit_consume:"使用點數", free_signup_voice_avatar_trial:"新用戶體驗贈點", apple_purchase:"加購點數", apple_purchase_refunded:"加購退款", apple_refund_reversed:"退款回沖", call_consume:"通話扣點" };

  // ══════════ 元件 ══════════
  function kpiRow(items){
    return `<div class="kpi-row">${items.map((k,i)=>`
      <div class="kpi ${i===0&&k.star?"kpi-accent":""}">
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
      if(i%lstep===0||i===labels.length-1){ const tl=svg("text",{x:cx,y:H-8,"text-anchor":"middle","font-size":11,fill:CHART.muted}); tl.textContent=lb; s.appendChild(tl); } });
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
    return `<div class="ops-notice error" role="alert"><strong>營運資料載入失敗</strong>${esc(explainErr(first))}。請確認連線與權限後重試。 <button type="button" class="btn-ghost" data-retry>重新整理</button> <button type="button" class="btn-ghost" data-goto="settings">連線設定</button></div>`;
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
    return `<div class="ops-notice info" role="status"><strong>${asof}</strong>之後有新的會再抓進來。</div>`;
  }
  function renderPage(id){
    pending.length=0;
    let html="";
    if (id==="overview") html=renderOverview();
    else if (id==="users") html=renderUsers();
    else if (id==="safety") html=renderSafety();
    else if (id==="medication") html=renderMedication();
    else if (id==="subscription") html=renderSubscription();
    else if (id==="feedback") html=renderFeedback();
    else if (id==="records") html=renderRecords();
    else if (id==="settings") html=settingsHTML();
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
      { label:"需人工跟進", value:n(t.requiresHumanEscalation||0), sub:"建議 30 分內確認", star:true },
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
    html+=principle("危機處理 SOP：① 專員 30 分鐘內確認 → ② 聯繫家庭圈指定聯絡人 → ③ 必要時引導撥打 119／1925 並記錄 → ④ 結案回填。所有紀錄僅授權營運與安全團隊檢視。");
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
    html+=card("每月經常性收入 MRR ／ 流失率", "要接 Apple 開發者後台才有真數字", `
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div><div class="kpi-sub">MRR（月訂閱收入）</div><div class="kpi-value" style="color:var(--muted)">待接</div></div>
        <div><div class="kpi-sub">流失率（取消訂閱）</div><div class="kpi-value" style="color:var(--muted)">待接</div></div>
      </div>
      <div class="kpi-sub" style="margin-top:12px">${esc(p.mrr||"需要「目前有效訂閱」聚合——規劃走 App Store Connect API 拉真訂閱與營收。")}${p.churnRate?"　"+esc(p.churnRate):""}</div>`);
    html+=card("方案表現", "月費 · 贈點 · 家庭圈上限（固定資訊）", tableHTML(["方案","內容","月費"],[
      ["<b>免費體驗</b>","綁定送 5 分鐘 · 提醒與心情先用起來","<span class='num'>NT$0</span>"],
      ["<b>Plus 家庭</b>","每月贈 100 點 · 家庭圈最多 4 人","<span class='num'>NT$599/月</span>"],
      ["<b>Pro 大家庭</b>","每月贈 200 點 · 家庭圈最多 12 人","<span class='num'>NT$1,199/月</span>"],
    ]));
    html+=`<div class="kpi-sub" style="padding:0 4px">想試算 LTV／CAC／回本？到「設定 → 訂閱試算」填你的方案月費與行銷花費。</div>`;
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
        return `<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(zh(FB_ZH,it.type,"意見"))}${it.score!=null?`　${esc(it.score)} 分`:""}${img?"　📎有圖":""}</div><div class="ri-meta">${esc(it.category||"–")} · ${esc(fmtTime(it.createdAt))} · App ${esc(it.appVersion||"?")}</div><div style="margin-top:4px">${esc(it.text||"")}</div>${img}</div></div>`;
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
    html+=card("系統操作紀錄", "系統跟管理端動過什麼，給工程師追查用", au.length?`<div class="rows">${au.slice(0,15).map((e)=>`<div class="row-item"><div class="ri-body"><div class="ri-title">${esc(e.eventType||"事件")}</div><div class="ri-meta">${esc(e.targetTable||"–")} · ${esc(fmtTime(e.createdAt))}</div><div>${esc(e.targetId||e.accountId||"")}</div></div></div>`).join("")}</div>`:emptyBox("還沒有操作紀錄。"));
    return html;
  }

  function tableHTML(cols, rows){
    return `<div class="table-wrap"><table><thead><tr>${cols.map((c)=>`<th scope="col">${c?esc(c):'<span class="sr-only">操作</span>'}</th>`).join("")}</tr></thead><tbody>${rows.map((r)=>`<tr>${r.map((c)=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
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

  // ══════════ 設定頁 ══════════
  function settingsHTML(){
    const a=loadAssume();
    return `
    ${card("連線", "貼上通行碼、按「連線看真資料」——後台只顯示真資料，還沒有的會顯示空的（上線有用戶就會長出來）", `
      <div class="field"><span>目前看的是：<b id="envLabel">–</b> <button type="button" class="btn-ghost" id="toggleAdv" aria-controls="advRow" aria-expanded="false" style="min-height:28px;padding:0 10px">換一台伺服器</button></span></div>
      <div class="field" id="advRow" hidden><span>伺服器網址（進階，平常不用動）</span><input id="apiBaseUrl" type="url" spellcheck="false"></div>
      <div class="field"><span>管理通行碼<small>（由蘇菲保管，跟她要一聲就好）</small></span><div class="token-wrap"><input id="adminToken" type="password" autocomplete="off" placeholder="貼上通行碼"><button type="button" class="eye-btn" id="eyeBtn" aria-controls="adminToken" aria-pressed="false">顯示</button></div></div>
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer"><input type="checkbox" id="rememberToken"><span>記住通行碼（只到關掉這個分頁，較安全）</span></label>
      <button type="button" class="primary" id="connectBtn">連線看真資料</button>
      <div class="kpi-sub" id="connectHint" role="status" aria-live="polite" style="margin-top:10px"></div>
    `)}
    ${card("訂閱試算（規劃工具·不是真數字）", "填你的預期值，即時算 LTV／CAC／回本。這是planning用的計算機，不是後台的真實數據。", `
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

  // ══════════ 連線 ══════════
  function initialBaseUrl(){ const s=storageGet(localStorage,ADMIN_BASE_KEY); if(s) return s; if(location.protocol.startsWith("http")) return location.origin; return DEFAULT_LOCAL_API; }
  function envLabelFor(u){ if(/munea-brain-staging/.test(u))return "雲端試營運"; if(/127\.0\.0\.1|localhost/.test(u))return "這台電腦（本機）"; if(/run\.app/.test(u))return "雲端伺服器"; return u.replace(/^https?:\/\//,"")||"–"; }
  function setStatus(t,k){
    const sp=$("statusPill"); if(sp){ sp.textContent=t; sp.className="status-pill"+(k?" "+k:""); }
    const r=$("envRole"); if(r) r.textContent=state.connected?("已連線 · "+envLabelFor(state.base||initialBaseUrl())):(t||"尚未連線");
    const out=$("logoutBtn"); if(out) out.hidden=!state.connected;
  }
  function setBusy(on){
    state.loading=!!on;
    const root=$("pageRoot"); if(root) root.setAttribute("aria-busy",on?"true":"false");
    const refresh=$("refreshBtn"); if(refresh) refresh.disabled=!!on;
  }
  function connectPromptHTML(){ return `<div class="connect-prompt"><h2>貼上通行碼，看真資料</h2><p class="muted">後台只顯示真實數據，還沒有的會顯示空的。到「連線設定」貼上通行碼（跟蘇菲要一聲就好）。</p><button type="button" class="primary" data-goto="settings">前往連線設定</button></div>`; }

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
        const q=dataQualitySummary(),queryTime=new Date().toISOString();
        $("lastUpdated").textContent=state.connected?(`查詢 ${fmtTime(queryTime)} · 紀錄最新時間 ${q.dataAsOf?fmtTime(q.dataAsOf):"未提供"}`):"";
      }
      updateBanner(); renderSide(); renderPage(state.page);
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
    if(!token){ state.connected=false; setStatus("需要重新登入","error"); updateBanner(); showLoginGate(); return; }
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
      <button type="button" class="login-alt" id="loginAlt">改用通行碼進入（進階）</button>
    </form>`;
  }
  function removeLoginGate(){ const g=$("loginGate"); if(g) g.remove(); const layout=document.querySelector(".layout"); if(layout){ layout.inert=false; layout.removeAttribute("aria-hidden"); } }
  function showLoginGate(){
    if($("loginGate")) return;
    const layout=document.querySelector(".layout"); if(layout){ layout.inert=true; layout.setAttribute("aria-hidden","true"); }
    const g=document.createElement("div"); g.id="loginGate"; g.className="login-gate"; g.setAttribute("role","dialog"); g.setAttribute("aria-modal","true"); g.innerHTML=loginGateHTML();
    document.body.appendChild(g);
    $("loginForm")?.addEventListener("submit",(e)=>{ e.preventDefault(); doLogin(); });
    $("loginAlt")?.addEventListener("click",()=>{ removeLoginGate(); go("settings"); });
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
    setStatus("已登出",""); updateBanner(); renderSide(); show(); showLoginGate();
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
    const badges={ safety: state.connected?String((D().safety||{}).totals?.requiresHumanEscalation||0):"", feedback: state.connected?String(((D().feedback||{}).latest||[]).length||0):"" };
    $("sideNav").innerHTML=NAV.map((g)=>`<div class="nav-group"><div class="nav-group-label">${esc(g.group)}</div><div class="side-nav">${g.items.map((it)=>{
      const bv=badges[it.badge]; const b= it.badge&&bv&&bv!=="0"?`<span class="nav-badge">${esc(bv)}</span>`:"";
      return `<a href="#${it.id}" data-page="${it.id}">${icon(it.id)}<span class="nav-label">${esc(it.label)}</span>${b}</a>`;
    }).join("")}</div></div>`).join("");
    document.querySelectorAll("#sideNav a").forEach((a)=>{ const on=a.dataset.page===state.page; a.classList.toggle("on",on); if(on)a.setAttribute("aria-current","page"); else a.removeAttribute("aria-current"); });
  }
  function updateBanner(){ const b=$("connectBanner"); if(b) b.hidden = state.connected || state.page==="settings"; }
  function go(id){ if(!TITLE[id]) id="overview"; state.page=id; location.hash="#"+id; }
  function show(){
    const id=(location.hash||"#overview").slice(1);
    state.page=TITLE[id]?id:"overview";
    if($("crumb")) $("crumb").textContent=CRUMB[state.page]||"";
    if($("pageTitle")) $("pageTitle").textContent=TITLE[state.page]||"";
    document.querySelectorAll("#sideNav a").forEach((a)=>{ const on=a.dataset.page===state.page; a.classList.toggle("on",on); if(on)a.setAttribute("aria-current","page"); else a.removeAttribute("aria-current"); });
    updateBanner();
    if(state.connected||state.page==="settings"){ renderPage(state.page); }
    else { $("pageRoot").innerHTML=connectPromptHTML(); $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto))); }
  }
  function bindPageEvents(id){
    $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto)));
    $("pageRoot").querySelectorAll("[data-retry]").forEach((b)=>b.addEventListener("click",refreshData));
    $("pageRoot").querySelectorAll("[data-acct]").forEach((b)=>b.addEventListener("click",()=>openAcctDetail(+b.dataset.acct)));
    const us=$("userSearch"); if(us){ us.value=state.tabs.userSearch||""; us.addEventListener("input",()=>{ state.tabs.userSearch=us.value.trim(); renderPage("users"); const el=$("userSearch"); if(el){ el.focus(); el.setSelectionRange(el.value.length,el.value.length);} }); }
    $("pageRoot").querySelectorAll("[data-ufilter]").forEach((b)=>b.addEventListener("click",()=>{ state.tabs.userFilter=b.dataset.ufilter; renderPage("users"); }));
    if(id==="settings"){
      const base=initialBaseUrl();
      if($("apiBaseUrl")) $("apiBaseUrl").value=base;
      if($("envLabel")) $("envLabel").textContent=envLabelFor(base);
      const st=storageGet(sessionStorage,ADMIN_TOKEN_KEY);
      if(st&&$("adminToken")){ $("adminToken").value=st; $("rememberToken").checked=true; }
      $("connectBtn")?.addEventListener("click",connect);
      $("toggleAdv")?.addEventListener("click",()=>{ const row=$("advRow"),open=row.hidden; row.hidden=!open; $("toggleAdv").setAttribute("aria-expanded",open?"true":"false"); if(open)$("apiBaseUrl")?.focus(); });
      $("eyeBtn")?.addEventListener("click",()=>{ const f=$("adminToken"); const sh=f.type==="text"; f.type=sh?"password":"text"; $("eyeBtn").textContent=sh?"顯示":"隱藏"; $("eyeBtn").setAttribute("aria-pressed",sh?"false":"true"); });
      $("apiBaseUrl")?.addEventListener("input",()=>{ if($("envLabel"))$("envLabel").textContent=envLabelFor($("apiBaseUrl").value); });
      ["aPlusPrice","aProPrice","aPlusCount","aProCount","aNewPaid","aMarketing","aLifeMonths"].forEach((i)=>$(i)?.addEventListener("input",calcAssume));
      calcAssume();
      if(state.data&&$("rawOut")) $("rawOut").textContent=JSON.stringify({data:state.data,errors:state.errors},null,2);
    }
  }

  function init(){
    if(window.MuneaVersion && $("appVer")) $("appVer").textContent="v"+window.MuneaVersion.current;
    const period=$("currentPeriod")?.querySelector("span"); if(period) period.textContent=new Intl.DateTimeFormat("zh-TW",{year:"numeric",month:"long",timeZone:"Asia/Taipei"}).format(new Date());
    renderSide();
    $("refreshBtn")?.addEventListener("click",()=>{ if(state.connected||state.token||storageGet(sessionStorage,ADMIN_TOKEN_KEY)) refreshData(); else go("settings"); });
    $("logoutBtn")?.addEventListener("click",logout);
    $("gotoSettings")?.addEventListener("click",()=>go("settings"));
    window.addEventListener("hashchange",show);
    setStatus("尚未連線","");
    show();
    const st=storageGet(sessionStorage,ADMIN_TOKEN_KEY);
    if(st){ state.token=st; (async()=>{ try{ const base=initialBaseUrl(); const r=await loadAll(base,st); if(r.ok){ setStatus(r.failed?"部分資料異常":"已連線",r.failed?"warn":"ok"); } else { setStatus("需要重新登入","error"); showLoginGate(); } }catch(e){ setStatus("連線失敗","error"); showLoginGate(); } })(); }
    else { showLoginGate(); }
  }
  document.addEventListener("DOMContentLoaded",init);
})();
