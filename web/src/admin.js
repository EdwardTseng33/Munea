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
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  };
  function icon(id, cls){ return `<svg class="${cls||"nav-ico"}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON_PATHS[id]||""}</svg>`; }

  // ══════════ 狀態 ══════════
  const ADMIN_BASE_KEY = "munea.admin.apiBaseUrl";
  const ADMIN_TOKEN_KEY = "munea.admin.token";
  const ASSUME_KEY = "munea.admin.assumptions";
  const DEFAULT_LOCAL_API = "http://127.0.0.1:8200";
  const state = { data: null, errors: {}, connected: false, page: "overview", tabs: {} };

  const EP_LIST = {
    northStar: ["/admin/north-star", { days: 30 }],
    usage: ["/admin/usage", { days: 30 }],
    accounts: ["/admin/accounts", { limit: 50 }],
    subscriptionMetrics: ["/admin/subscription-metrics", { days: 30 }],
    feedback: ["/admin/feedback", { limit: 20 }],
    safety: ["/admin/safety-events", { days: 30, limit: 30 }],
    privacy: ["/admin/privacy-requests", { limit: 20 }],
    summaries: ["/admin/conversation-summaries", { limit: 20 }],
    audit: ["/admin/audit-events", { limit: 20 }],
  };

  const CHART = { teal: "#1AA093", coral: "#D98841", gold: "#E0B354", prev: "#C9C0B0", grid: "#ECE6DA", ink: "#33403D", muted: "#6B7772" };
  const cc = { teal: CHART.teal, coral: CHART.coral, gold: CHART.gold, prev: CHART.prev };
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
  const n = (v) => (v==null||v===""||isNaN(v))?"–":Number(v).toLocaleString("en-US");

  // 真資料取用（沒連線/沒資料一律空，不編）
  const D = () => state.data || {};
  const northStar = () => D().northStar || {};
  const usage = () => D().usage || {};
  const subM = () => D().subscriptionMetrics || {};
  const daily = () => usage().daily || [];
  const ecount = () => usage().eventCounts || {};

  function fmtMoney(v){ return (v==null||isNaN(v))?"–":"NT$"+Math.round(Number(v)).toLocaleString("en-US"); }
  function pct(v){ return (v==null||isNaN(v))?"–":Math.round(Number(v)*100)+"%"; }
  function shortDate(iso){ const p=String(iso).split("-"); return p.length===3?`${+p[1]}/${+p[2]}`:iso; }
  function fmtTime(v){ if(!v)return "–"; const d=new Date(v); if(isNaN(d))return String(v); try{ return new Intl.DateTimeFormat("zh-TW",{timeZone:"Asia/Taipei",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);}catch(e){return String(v);} }
  function zh(map,v,f){ if(v==null||v==="")return f||"–"; return map[String(v).toLowerCase()]||String(v); }
  const RISK_ZH = { crisis:"🔴 危機", critical:"🔴 危機", high:"🔴 高風險", medium:"🟡 中風險", moderate:"🟡 中風險", low:"🟢 低風險", none:"低" };
  const FB_ZH = { bug:"問題回報", idea:"功能許願", praise:"稱讚", nps:"打分數" };
  const PV_ZH = { account_deletion:"刪除帳號", deletion:"刪除帳號", export:"資料副本", data_export:"資料副本", correction:"資料更正" };
  const ST_ZH = { pending:"待處理", open:"待處理", received:"已收到", processing:"處理中", done:"已完成", completed:"已完成", closed:"已結案" };

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
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img"});
    for(let t=0;t<=4;t++){ const val=max/4*t,gy=y(val); s.appendChild(svg("line",{x1:L,x2:W-R,y1:gy,y2:gy,stroke:CHART.grid,"stroke-width":1})); const tx=svg("text",{x:L-8,y:gy+4,"text-anchor":"end","font-size":11,fill:CHART.muted}); tx.textContent=n(Math.round(val)); s.appendChild(tx); }
    const band=pw/labels.length, groupW=Math.min(band*0.62,series.length*20+(series.length-1)*4), barW=Math.min(22,(groupW-(series.length-1)*4)/series.length);
    labels.forEach((lb,i)=>{ const cx=L+band*i+band/2,startX=cx-groupW/2;
      series.forEach((se,si)=>{ const v=se.values[i],top=y(v),x=startX+si*(barW+4),h=Math.max(0,T+ph-top);
        const path=svg("path",{d:h<=0.5?`M ${x} ${T+ph} h ${barW}`:`M ${x} ${T+ph} V ${top+4} Q ${x} ${top} ${x+4} ${top} H ${x+barW-4} Q ${x+barW} ${top} ${x+barW} ${top+4} V ${T+ph} Z`,fill:se.color});
        path.addEventListener("mousemove",(e)=>tip(`<div>${esc(lb)}${series.length>1?" · "+esc(se.name):""}</div><b>${n(v)}</b>${opts.unit?" "+opts.unit:""}`,e.clientX,e.clientY));
        path.addEventListener("mouseleave",hideTip); s.appendChild(path); });
      const tl=svg("text",{x:cx,y:H-8,"text-anchor":"middle","font-size":11,fill:CHART.ink}); tl.textContent=lb; s.appendChild(tl); });
    box.innerHTML=""; box.appendChild(s);
    if(series.length>1){ const lg=document.createElement("div"); lg.className="legend"; lg.innerHTML=series.map((se)=>`<span class="key"><span class="swatch" style="background:${se.color}"></span>${esc(se.name)}</span>`).join(""); box.appendChild(lg); }
  }

  function lineChart(box, labels, series, opts){
    opts=opts||{};
    if(!labels.length || allZero(series)){ box.innerHTML=emptyBox(opts.empty||"還沒有資料。"); return; }
    const W=760,H=180,L=44,R=16,T=14,B=26, pw=W-L-R, ph=H-T-B;
    const maxV=opts.maxY||niceMax(Math.max(1,...series.flatMap((s)=>s.values))), minV=opts.minY||0;
    const nP=labels.length, x=(i)=>L+(nP<=1?pw/2:(i/(nP-1))*pw), y=(v)=>T+ph-((v-minV)/(maxV-minV))*ph;
    const s=svg("svg",{viewBox:`0 0 ${W} ${H}`,role:"img"});
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
  function renderPage(id){
    pending.length=0;
    let html="";
    if (id==="overview") html=renderOverview();
    else if (id==="users") html=renderUsers();
    else if (id==="safety") html=renderSafety();
    else if (id==="subscription") html=renderSubscription();
    else if (id==="feedback") html=renderFeedback();
    else if (id==="records") html=renderRecords();
    else if (id==="settings") html=settingsHTML();
    $("pageRoot").innerHTML=html;
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

  function renderUsers(){
    const accts=(D().accounts||{}).accounts||[];
    const ns=northStar();
    let html=kpiRow([
      { label:"帳號數", value:n(accts.length), sub:"目前建立的帳號／家庭" },
      { label:"活躍人數", value:n(ns.activePeople), sub:"近 30 天有真互動" },
      { label:"語音接通率", value:ns.voiceSessionSuccessRate==null?"–":pct(ns.voiceSessionSuccessRate), sub:"撥了有講到話" },
      { label:"家人互動", value:n(ns.familyInteractions), sub:"家庭圈往來次數" },
    ]);
    if(!accts.length){
      html+=card("用戶與家庭圈名冊", "現在有哪些人／家庭在用沐寧", emptyBox("還沒有帳號——正式開放註冊後，這裡會列出每一家。"));
      return html;
    }
    const q=state.tabs.userSearch||"";
    const rows=accts.filter((a)=>{ if(!q)return true; const p=a.primaryPerson||{},f=a.familyGroup||{}; return (p.displayName||a.accountName||"").indexOf(q)>-1||(f.name||"").indexOf(q)>-1; });
    html+=card("用戶與家庭圈名冊", `共 ${accts.length} 筆`,
      `<div class="rowflex"><span class="muted small">點「查看」看單一用戶</span><input class="tbl-search" id="userSearch" type="search" placeholder="搜尋名字或家庭"></div>`+
      tableHTML(["帳號","家庭圈","主要使用者","陪伴角色","家人數","最近更新",""],
        rows.map((a,i)=>{ const p=a.primaryPerson||{},f=a.familyGroup||{},c=a.companion||{},m=a.familyMembers||{};
          return [esc(a.accountName||a.accountId||"–"),esc(f.name||"–"),esc(p.displayName||"–"),esc(c.displayName||c.templateId||"–"),`<span class="num">${n(m.count||0)}</span>`,esc(fmtTime(a.updatedAt||a.createdAt)),`<button class="btn-ghost btn-sm" data-acct="${i}">查看</button>`]; })));
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

  function renderSubscription(){
    const sm=subM(), win=sm.windowDays||30;
    let html=kpiRow([
      { label:"新增訂閱", value:n(sm.newSubscriptions), sub:`近 ${win} 天付費訂閱新增`, star:true },
      { label:"點數加購", value:n(sm.pointsPurchases), unit:sm.pointsPurchases?" 筆":"", sub:`共 ${n(sm.pointsTotal)} 點` },
      { label:"新註冊", value:n(sm.registrations), sub:`近 ${win} 天開通帳號` },
      { label:"免費→付費轉換率", value:sm.freeToPaidConversion==null?"–":(sm.freeToPaidConversion*100).toFixed(1)+"%", sub:"付費數 ÷ 註冊數 · 目標 ≥8%" },
    ]);
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
      ["<b>Plus 家庭</b>","每月贈 200 點 · 家庭圈最多 4 人","<span class='num'>NT$499/月</span>"],
      ["<b>Pro 大家庭</b>","每月贈 500 點 · 家庭圈最多 12 人","<span class='num'>NT$999/月</span>"],
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
    return `<div class="table-wrap"><table><thead><tr>${cols.map((c)=>`<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${rows.map((r)=>`<tr>${r.map((c)=>`<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  function openAcctDetail(idx){
    const a=((D().accounts||{}).accounts||[])[idx]; if(!a) return;
    const p=a.primaryPerson||{},f=a.familyGroup||{},c=a.companion||{},m=a.familyMembers||{};
    const fields=[["家庭圈",f.name||"–"],["主要使用者",p.displayName||"–"],["陪伴角色",c.displayName||c.templateId||"–"],["家人數",(m.count||0)+" 人"],["建立",fmtTime(a.createdAt)],["最近更新",fmtTime(a.updatedAt)]];
    const body=`<div class="modal-head"><div><div class="modal-title">${esc(a.accountName||a.accountId||"帳號")}</div><div class="muted small">${esc(f.name||"–")}</div></div><button class="modal-x" data-close type="button">✕</button></div>
      <div class="detail-grid">${fields.map((x)=>`<div class="dcell"><div class="dlabel">${esc(x[0])}</div><div class="dval">${esc(x[1])}</div></div>`).join("")}</div>
      <div class="kpi-sub" style="margin-top:14px">為保護隱私，健康與聊天內容需經該用戶授權才在此顯示。</div>`;
    let mo=$("acctModal"); if(!mo){ mo=document.createElement("div"); mo.id="acctModal"; mo.className="modal-overlay"; document.body.appendChild(mo); }
    mo.innerHTML=`<div class="modal-card">${body}</div>`; mo.hidden=false;
    mo.querySelectorAll("[data-close]").forEach((b)=>b.addEventListener("click",()=>{ mo.hidden=true; }));
    mo.addEventListener("click",(e)=>{ if(e.target===mo) mo.hidden=true; });
  }

  // ══════════ 設定頁 ══════════
  function settingsHTML(){
    const a=loadAssume();
    return `
    ${card("連線", "貼上通行碼、按「連線看真資料」——後台只顯示真資料，還沒有的會顯示空的（上線有用戶就會長出來）", `
      <div class="field"><span>目前看的是：<b id="envLabel">–</b> <button type="button" class="btn-ghost" id="toggleAdv" style="min-height:28px;padding:0 10px">換一台伺服器</button></span></div>
      <div class="field" id="advRow" hidden><span>伺服器網址（進階，平常不用動）</span><input id="apiBaseUrl" type="url" spellcheck="false"></div>
      <div class="field"><span>管理通行碼<small>（由蘇菲保管，跟她要一聲就好）</small></span><div class="token-wrap"><input id="adminToken" type="password" autocomplete="off" placeholder="貼上通行碼"><button type="button" class="eye-btn" id="eyeBtn">顯示</button></div></div>
      <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer"><input type="checkbox" id="rememberToken"><span>記住通行碼（只到關掉這個分頁，較安全）</span></label>
      <button type="button" class="primary" id="connectBtn">連線看真資料</button>
      <div class="kpi-sub" id="connectHint" style="margin-top:10px"></div>
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
  function initialBaseUrl(){ const s=localStorage.getItem(ADMIN_BASE_KEY); if(s) return s; if(location.protocol.startsWith("http")) return location.origin; return DEFAULT_LOCAL_API; }
  function envLabelFor(u){ if(/munea-brain-staging/.test(u))return "雲端試營運"; if(/127\.0\.0\.1|localhost/.test(u))return "這台電腦（本機）"; if(/run\.app/.test(u))return "雲端伺服器"; return u.replace(/^https?:\/\//,"")||"–"; }
  function setStatus(t,k){ const sp=$("statusPill"); if(sp){ sp.textContent=t; sp.className="status-pill"+(k?" "+k:""); } const r=$("envRole"); if(r) r.textContent=state.connected?("已連線 · "+envLabelFor(localStorage.getItem(ADMIN_BASE_KEY)||"")):(t||"尚未連線"); }
  function connectPromptHTML(){ return `<div class="connect-prompt"><h2>貼上通行碼，看真資料</h2><p class="muted">後台只顯示真實數據，還沒有的會顯示空的。到「連線設定」貼上通行碼（跟蘇菲要一聲就好）。</p><button type="button" class="primary" data-goto="settings">前往連線設定</button></div>`; }

  async function postAdmin(base, token, path, body){
    const res=await fetch(base+path,{method:"POST",headers:{"Content-Type":"application/json; charset=utf-8","X-Munea-Admin-Token":token},body:JSON.stringify(body||{})});
    const txt=await res.text(); let p={}; try{ p=txt?JSON.parse(txt):{}; }catch(e){ p={ok:false,error:{code:"invalid_json"}}; }
    if(!res.ok||p.ok===false){ throw new Error((p.error&&p.error.code)||("http_"+res.status)); }
    return p;
  }
  function explainErr(m){ m=String(m||""); if(/invalid_admin_token/.test(m))return "通行碼不對"; if(/admin_token_not_configured/.test(m))return "伺服器還沒設通行碼"; if(/http_40[13]/.test(m))return "被大門擋住（權限/通行碼）"; if(/Failed to fetch|NetworkError|load failed/i.test(m))return "連不到伺服器"; return m; }

  async function connect(){
    const base=($("apiBaseUrl")?.value||initialBaseUrl()).trim().replace(/\/+$/,"");
    const token=($("adminToken")?.value||"").trim();
    if(!token){ setStatus("要先貼通行碼","error"); return; }
    localStorage.setItem(ADMIN_BASE_KEY, base);
    if($("rememberToken")?.checked) sessionStorage.setItem(ADMIN_TOKEN_KEY, token); else sessionStorage.removeItem(ADMIN_TOKEN_KEY);
    setStatus("讀取中…","");
    const keys=Object.keys(EP_LIST);
    const rs=await Promise.allSettled(keys.map((k)=>postAdmin(base,token,EP_LIST[k][0],EP_LIST[k][1])));
    const data={},errors={};
    rs.forEach((r,i)=>{ if(r.status==="fulfilled")data[keys[i]]=r.value; else errors[keys[i]]=(r.reason&&r.reason.message)||"fail"; });
    state.data=data; state.errors=errors; state.connected=Object.keys(data).length>0;
    if($("rawOut")) $("rawOut").textContent=JSON.stringify({data,errors},null,2);
    if($("lastUpdated")) $("lastUpdated").textContent=state.connected?"資料時間 "+fmtTime(new Date().toISOString()):"";
    const failed=Object.keys(errors).length;
    if(failed===0) setStatus("✅ 已連線","ok");
    else if(failed===keys.length){ setStatus("❌ 連不上","error"); state.connected=false; if($("connectHint"))$("connectHint").textContent="連線失敗："+explainErr(errors[keys[0]]); }
    else setStatus("⚠ 有 "+failed+" 區讀不到","warn");
    updateBanner(); renderSide(); renderPage(state.page);
  }

  // ══════════ 訂閱試算（計算機·設定頁） ══════════
  const ASSUME_DEF={plusPrice:499,proPrice:999,plusCount:0,proCount:0,newPaid:0,marketing:0,lifeMonths:12};
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
    document.querySelectorAll("#sideNav a").forEach((a)=>a.classList.toggle("on",a.dataset.page===state.page));
  }
  function updateBanner(){ const b=$("connectBanner"); if(b) b.hidden = state.connected || state.page==="settings"; }
  function go(id){ if(!TITLE[id]) id="overview"; state.page=id; location.hash="#"+id; }
  function show(){
    const id=(location.hash||"#overview").slice(1);
    state.page=TITLE[id]?id:"overview";
    if($("crumb")) $("crumb").textContent=CRUMB[state.page]||"";
    if($("pageTitle")) $("pageTitle").textContent=TITLE[state.page]||"";
    document.querySelectorAll("#sideNav a").forEach((a)=>a.classList.toggle("on",a.dataset.page===state.page));
    updateBanner();
    if(state.connected||state.page==="settings"){ renderPage(state.page); }
    else { $("pageRoot").innerHTML=connectPromptHTML(); $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto))); }
  }
  function bindPageEvents(id){
    $("pageRoot").querySelectorAll("[data-goto]").forEach((b)=>b.addEventListener("click",()=>go(b.dataset.goto)));
    $("pageRoot").querySelectorAll("[data-acct]").forEach((b)=>b.addEventListener("click",()=>openAcctDetail(+b.dataset.acct)));
    const us=$("userSearch"); if(us){ us.value=state.tabs.userSearch||""; us.addEventListener("input",()=>{ state.tabs.userSearch=us.value.trim(); renderPage("users"); const el=$("userSearch"); if(el){ el.focus(); el.setSelectionRange(el.value.length,el.value.length);} }); }
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

  function init(){
    if(window.MuneaVersion && $("appVer")) $("appVer").textContent="v"+window.MuneaVersion.current;
    renderSide();
    $("refreshBtn")?.addEventListener("click",()=>{ if(state.connected) connect(); else go("settings"); });
    $("gotoSettings")?.addEventListener("click",()=>go("settings"));
    window.addEventListener("hashchange",show);
    setStatus("尚未連線","");
    show();
    const st=sessionStorage.getItem(ADMIN_TOKEN_KEY);
    if(st){ (async()=>{ try{ const base=initialBaseUrl(); const keys=Object.keys(EP_LIST); const rs=await Promise.allSettled(keys.map((k)=>postAdmin(base,st,EP_LIST[k][0],EP_LIST[k][1]))); const data={},errors={}; rs.forEach((r,i)=>{ if(r.status==="fulfilled")data[keys[i]]=r.value; else errors[keys[i]]="fail"; }); if(Object.keys(data).length){ state.data=data; state.errors=errors; state.connected=true; setStatus("✅ 已連線","ok"); if($("lastUpdated"))$("lastUpdated").textContent="資料時間 "+fmtTime(new Date().toISOString()); updateBanner(); renderSide(); renderPage(state.page); } }catch(e){} })(); }
  }
  document.addEventListener("DOMContentLoaded",init);
})();
