(function(){
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const BIZ=['診斷','配對','付費','上課','學會','續約'];
const ROLES={student:['學','學生 · 小睿的手機'],parent:['家','家長 · 媽媽的 LINE'],class:['學','學生 · 小睿的 iPad'],teacher:['師','老師 · 林老師的 iPad'],ops:['師','老師 · 林老師的 iPad']};
const STEPS=[
 {g:'開始',id:'welcome',dev:'Phone',role:'student',biz:0,t:'第一眼：不是又一個題庫',
  why:'國中生打開學習 App 的前 10 秒就決定要不要留下。第一頁只說一件事：我們先找你卡在哪，不考你、不打分數。',
  ev:['多數 AI 家教 App 第 30 天留存不到 12%，輸在「打開就是寫題目」','兩個圓點就是品牌，也是 AI 教練「小陪」的臉：一個是你，一個是陪你的人'],dr:['低門檻開始','不評分']},
 {g:'開始',id:'diag',dev:'Phone',role:'student',biz:0,t:'診斷：問答案，也問「你怎麼想的」',
  why:'只看對錯分不出「不會」和「粗心」。每題多問一句想法，AI 才知道他卡在概念、計算還是讀題，後面配對才準。試著選一個答案看看。',
  ev:['卡點分成三型：概念型、計算型、讀題型，配到的老師和小組不一樣','可以用說的：國中生打字意願低，語音優先'],dr:['被理解','自主：隨時可停']},
 {g:'開始',id:'result',dev:'Phone',role:'student',biz:0,t:'結果：你只卡在一步',
  why:'把「數學不好」縮小成「一個點」。孩子第一次看到自己的問題是有邊界的、走得完的，這是整個產品最重要的情緒轉折。',
  ev:['路徑圖取代分數：會了（綠）、卡住（珊瑚，會跳動）、已掌握（金）','「有 5 個人跟你卡在同一步」：把丟臉變成有伴'],dr:['勝任感','歸屬感']},
 {g:'加入小隊',id:'invite',dev:'Phone',role:'student',biz:1,t:'小隊邀請：AI 配對的真人小組課',
  why:'同一隊、同一位老師、同一個時段走 8 週。配對理由用一道式子講清楚，點一下式子看不等號翻過去。',
  ev:['市場調研結論：固定 8 週小隊的留存與成班率，明顯好過每堂重配','加入前只看得到頭像顏色，保護未成年人隱私','第一堂試上，不滿意不收費：把家長的風險降到零'],dr:['歸屬感','可預期的節奏']},
 {g:'加入小隊',id:'teacher',dev:'Phone',role:'student',biz:1,t:'認識老師：不看星星，看學生過幾天還會不會',
  why:'老師頁最大的數字是「學生隔三天還講得出來的比例」。這是平台選老師、排老師、發季獎金的同一把尺。按播放聽 30 秒。',
  ev:['AI 先知道要開什麼課，再依卡點類型找擅長的老師','老師每隊約 NT$1,000，季獎金跟著這個數字走'],dr:['信任','透明']},
 {g:'加入小隊',id:'sent',dev:'Phone',role:'student',biz:1,t:'孩子先說要，家長才付錢',
  why:'報名由孩子按下去。家長收到的是「他自己想加入」，不是又一個被安排的補習。這一步決定了三週後他還在不在。',
  ev:['三週流失的第一大原因：被逼著來的','AI 湊名單，老師按「接這一隊」才成班：機器建議、人負責'],dr:['自主','承諾']},
 {g:'加入小隊',id:'parentpay',dev:'Line',role:'parent',biz:2,t:'家長：在 LINE 裡看懂、同意、付款',
  why:'家長不用下載 App。診斷摘要、方案、同意書、付款都在 LINE 完成。勾兩個同意、按付款試試。',
  ev:['走 LINE／網頁付款，不經 App 內購，省下 15–30% 通路費','不用電銷：診斷摘要本身就是銷售，獲客成本目標 NT$2,500 以下','同意書明講家長看得到什麼、看不到什麼，避免變成監控工具'],dr:['家人迴路','透明']},
 {g:'每天',id:'home',dev:'Phone',role:'student',biz:3,t:'首頁：今天照你的步調',
  why:'每天最多兩件事，22:30 關燈。小陪看過睡眠後自動減量。小隊目標是六個人合計，沒有誰拖累誰。',
  ev:['國中生的黃金時段是 20:30–22:00，提醒只落在這段','合作型目標取代個人連勝：不用「斷了就歸零」的損失恐懼','小陪是陪練工具，不扮演情緒伴侶：話少、具體、只談學習節奏'],dr:['小隊合作目標','不羞辱','狀態感知']},
 {g:'每天',id:'practice',dev:'Phone',role:'student',biz:3,t:'練習：三級提示，沒有第四級',
  why:'AI 永遠不直接給答案。輕推、問一句、示範一步，用到哪一級都會記下來，老師上課前看得到。按提示再作答。',
  ev:['AI 家教最大的失敗：學生拿來抄答案，研究顯示多數人用一次就不再用','提示用量是比分數更好的卡點訊號'],dr:['勝任感','剛好的難度']},
 {g:'每天',id:'say',dev:'Phone',role:'student',biz:4,t:'說給我聽：產品的心臟',
  why:'講得出來才算會。三道關：當下講得出、換一題做得出、隔三天不提示還在。按麥克風試試，完成後家人會在 LINE 收到好消息。',
  ev:['教別人的學習效果顯著高於自己複習，有真人在聽時效果接近兩倍','錄音不保留，只留三個勾：未成年人資料最小化','好消息預設分享給家人，其他由孩子決定'],dr:['勝任感','家人迴路','教隊友']},
 {g:'上課',id:'lock',dev:'Phone',role:'student',biz:3,t:'上課提醒：有人在等你',
  why:'通知的主詞是隊友和老師，不是系統。一天最多四次，每次都能說不；段考那週自動安靜。',
  ev:['「小安已經上線了」比「你有一堂課」有效得多','沒卡點可以請假，不扣堂數'],dr:['歸屬感','自主']},
 {g:'上課',id:'class',dev:'Pad',role:'class',biz:3,t:'小隊教室：50 分鐘，老師講話不到四成',
  why:'三段式：一起理解 → 自己試試（AI 依本週卡點把 6 人分成 2–3 組）→ 說給隊友聽。點上方 1、2、3 切換，試試拍照交答案和舉手。',
  ev:['同一隊走 8 週，但每週課內重新分組：兼顧歸屬感與精準度','自己的練習只有老師看得到，國中生最怕在同學面前錯','手機也能上課，iPad 體驗最好'],dr:['互相講','安全感','真人老師']},
 {g:'上課',id:'finish',dev:'Phone',role:'student',biz:4,t:'完賽：六個人都講出來了',
  why:'下課不是結束。六個人都說給小陪聽，這一堂才算完賽。老師只要按住說 50 秒。',
  ev:['沒過的人隔天補一格就亮，沒有排名、沒有人被公開點名','老師的一句具體稱讚，是國中生最在意的回饋'],dr:['小隊合作目標','被看見']},
 {g:'上課',id:'family',dev:'Line',role:'parent',biz:4,t:'家人：今晚可以問他什麼',
  why:'不給家長分數，給他們一句今晚能問的話。孩子講給家人聽，就是再練一次。按一個回應試試。',
  ev:['家長最常說的困擾：不知道怎麼關心才不會吵架','家長的回應會出現在孩子的路線上，形成迴路','週報只含孩子選擇分享的項目'],dr:['家人迴路','自主']},
 {g:'學會',id:'retest',dev:'Phone',role:'student',biz:4,t:'隔三天：不提示再測，才算真的學會',
  why:'這是對家長和萬通最硬的成果指標：再測通過率。過了，這個點變金色，永遠不會掉。選正確答案看看。',
  ev:['試點關卡：再測通過率 ≥ 70%','金色不會因為沒來而消失：成就是存下來的，不是租來的'],dr:['勝任感','看得見的累積']},
 {g:'學會',id:'route',dev:'Phone',role:'student',biz:4,t:'路線：計畫和歷程放在一起',
  why:'往前看是這週安排（含睡眠、補習、考前減量），往後看是走過的路和家人的回應。切換上方兩個分頁。',
  ev:['每週有一格由孩子自己選要練什麼','考前三天自動減量，段考週低頻','只跟自己比'],dr:['自主','狀態感知','看得見的累積']},
 {g:'續走',id:'review',dev:'Phone',role:'student',biz:5,t:'8 週回顧：孩子自己決定要不要續',
  why:'續約的理由不是折扣，是「這段路我走完了，下一段我想跟同一群人走」。',
  ev:['試點關卡：續購率 ≥ 50%','可以換隊：阿哲去了幾何隊，不是失敗，是配對在運作'],dr:['歸屬感','自主']},
 {g:'續走',id:'renew',dev:'Line',role:'parent',biz:5,t:'家長續約：一頁成果，一個按鈕',
  why:'家長看到的是已掌握的點、完賽數、老師的一句話。成績只有孩子願意才出現。',
  ev:['8 堂 NT$2,990；平台抽 20–25%，其餘歸開課的教育機構與老師','這一頁同時是給客戶機構看的成效資料'],dr:['家人迴路','成果透明']},
 {g:'後台',id:'brief',dev:'Pad',role:'teacher',biz:3,t:'老師：課前一頁，兩分鐘讀完',
  why:'老師不備課、不出講義、不打字。AI 把六個人各卡在哪、建議怎麼分組寫成一頁；分組理由看得懂、可以不採用。',
  ev:['老師願不願意留下來，決定於行政負擔','可解釋的分組：老師看得到原因，才會信任 AI'],dr:['老師留任','人機分工']},
 {g:'後台',id:'ops',dev:'Pad',role:'teacher',biz:1,t:'老師：AI 建議開課，老師決定接不接',
  why:'沒有中間的行政人員。AI 看見哪裡有需求、湊好名單、寫好理由，直接送到適合的老師面前；老師決定開不開、接不接。學生情緒的事排第一，先到帶他的老師手上。按按看右邊的按鈕。',
  ev:['人力結構決定淨利：不設電銷、不設排課行政，老師直接面對 AI 整理好的需求','試點關卡：成班率 ≥ 60%'],dr:['人機分工','安全網']}
];

/* ---------- shell ---------- */
const rail=$('#rail'),ctx=$('#ctx'),stage=$('#stage');
let cur=0,timers=[];
const later=(f,ms)=>{const t=setTimeout(f,ms);timers.push(t);return t};
const every=(f,ms)=>{const t=setInterval(f,ms);timers.push(t);return t};
function clearTimers(){timers.forEach(t=>{clearTimeout(t);clearInterval(t)});timers=[]}

(function buildRail(){
  let g=null,box=null;
  STEPS.forEach((s,i)=>{
    if(s.g!==g){g=s.g;box=document.createElement('div');box.className='grp';box.innerHTML='<h5>'+g+'</h5>';rail.appendChild(box)}
    const b=document.createElement('button');b.innerHTML='<span class="n">'+(i+1)+'</span><span>'+s.t.split('：')[0]+'</span>';
    b.onclick=()=>go(i);box.appendChild(b);s.btn=b;
  });
})();

function renderCtx(s,i){
  ctx.innerHTML='<div><div class="k">第 '+(i+1)+' 步 / '+STEPS.length+' · '+s.g+'</div><h2>'+s.t+'</h2></div><p>'+s.why+'</p>'+
   '<div class="sec"><h6>商業流程走到哪</h6><div class="biz">'+BIZ.map((_,k)=>'<i class="'+(k<s.biz?'on':k===s.biz?'now':'')+'"></i>').join('')+'</div><div class="bizl">'+BIZ.map(b=>'<span>'+b+'</span>').join('')+'</div></div>'+
   '<div class="sec"><h6>為什麼這樣設計</h6><ul>'+s.ev.map(e=>'<li>'+e+'</li>').join('')+'</ul></div>'+
   '<div class="sec"><h6>這一頁推動的動機</h6><div class="chips">'+s.dr.map((d,k)=>'<span class="chip'+(k%3===1?' c':k%3===2?' h':'')+'">'+d+'</span>').join('')+'</div></div>';
}

function fit(){
  const s=STEPS[cur],dev=$('#dev'+s.dev),W=dev.offsetWidth,H=dev.offsetHeight;
  const aw=stage.clientWidth,ah=Math.max(420,window.innerHeight-150);
  const k=Math.min(1,aw/W,ah/H);
  dev.style.transform='scale('+k+')';
  dev.style.margin='0 '+(-(W*(1-k))/2)+'px '+(-(H*(1-k)))+'px';
  stage.style.minHeight=(H*k)+'px';
}

function go(i){
  if(typeof i==='string'){i=STEPS.findIndex(s=>s.id===i)}
  if(i<0||i>=STEPS.length)return;
  clearTimers();cur=i;const s=STEPS[i];
  ['Phone','Line','Pad'].forEach(d=>{$('#dev'+d).style.display=d===s.dev?'':'none'});
  $$('.scr').forEach(x=>x.classList.toggle('on',x.dataset.id===s.id));
  STEPS.forEach((x,k)=>{x.btn.classList.toggle('on',k===i);x.btn.classList.toggle('done',k<i)});
  rail.scrollTop=s.btn.offsetTop-rail.clientHeight/2;rail.scrollLeft=s.btn.offsetLeft-rail.clientWidth/2;
  const r=ROLES[s.role];$('#role').dataset.r=s.role==='class'?'student':s.role;$('#role i').textContent=r[0];$('#roleT').textContent=r[1];
  $('#prev').disabled=i===0;$('#next').disabled=i===STEPS.length-1;
  document.querySelector('.main').classList.toggle('wide',s.dev==='Pad');renderCtx(s,i);fit();
  $('#toast').classList.remove('show');$('#burst').classList.remove('go');
  const sc=$('.scr.on .sc,.scr.on .chat');if(sc)sc.scrollTop=0;
  (ENTER[s.id]||(()=>{}))();
  try{history.replaceState(null,'','#'+s.id)}catch(e){}
}
$('#prev').onclick=()=>go(cur-1);$('#next').onclick=()=>go(cur+1);
document.addEventListener('click',e=>{
  const n=e.target.closest('[data-next]');if(n&&!n.disabled)return go(cur+1);
  const p=e.target.closest('[data-prev]');if(p)return go(cur-1);
  const g=e.target.closest('[data-go]');if(g&&!g.disabled)return go(g.dataset.go);
});
document.addEventListener('keydown',e=>{if(e.target.matches('input,textarea'))return;if(e.key==='ArrowRight')go(cur+1);if(e.key==='ArrowLeft')go(cur-1)});
window.addEventListener('resize',fit);

/* ---------- helpers ---------- */
function burst(){
  const b=$('#burst'),cols=['#F26B54','#0E5F52','#F4C24D','#DCEFE8','#F9D3C9'];b.classList.remove('go');b.innerHTML='';
  for(let k=0;k<26;k++){const d=document.createElement('i'),a=Math.random()*6.28,r=90+Math.random()*170;
    d.style.cssText='background:'+cols[k%5]+';--x:'+Math.cos(a)*r+'px;--y:'+(Math.sin(a)*r-60)+'px;animation-delay:'+(Math.random()*.15)+'s';b.appendChild(d)}
  void b.offsetWidth;b.classList.add('go');
}
function toast(who,msg,app){const t=$('#toast');t.classList.toggle('app',!!app);$('.lg',t).textContent=app?'T':'LINE';$('#toastT').textContent=who;$('#toastM').textContent=msg;t.classList.add('show');later(()=>t.classList.remove('show'),3600)}
function enable(b,on){b.disabled=!on;b.style.opacity=on?1:.4}
function mkWave(el,n){el.innerHTML='';for(let k=0;k<n;k++)el.appendChild(document.createElement('i'))}
function runWave(el){el.classList.add('on');return every(()=>$$('i',el).forEach(i=>i.style.height=(6+Math.random()*30)+'px'),120)}
function stopWave(el,t){clearInterval(t);el.classList.remove('on');$$('i',el).forEach(i=>i.style.height='6px')}
function type(el,text,ms,done){el.textContent='';el.style.color='';let k=0;const t=every(()=>{el.textContent=text.slice(0,++k);if(k>=text.length){clearInterval(t);done&&done()}},ms)}
function single(list,cb){list.forEach(b=>b.addEventListener('click',()=>{list.forEach(x=>x.classList.remove('sel'));b.classList.add('sel');cb&&cb(b)}))}

/* ---------- interactions ---------- */
// diagnosis
const dOpts=$$('#diagOpts .opt'),dWhy=$$('#diagWhy .why button');
single(dOpts,()=>{$('#diagWhy').style.display='flex';$('#diagProg').style.width='58%';const sc=$('.scr[data-id=diag] .sc');later(()=>sc.scrollTo({top:sc.scrollHeight,behavior:'smooth'}),60)});
single(dWhy,()=>enable($('#diagGo'),true));
// invite
$('#eqInvite').onclick=function(){this.classList.toggle('play')};
// teacher
const T_TX='「我上課話不多。我會先問你怎麼想的，錯的地方通常很有道理，我們就從那裡開始。」';
mkWave($('#tWave'),22);
$('#tPlay').onclick=()=>{const w=$('#tWave'),t=runWave(w);type($('#tTx'),T_TX,70,()=>stopWave(w,t))};
// parent pay
single($$('#plans .plan'));
const agr=$$('#agree input');agr.forEach(c=>c.onchange=()=>{$('#payBtn').disabled=!agr.every(x=>x.checked)});
$('#payBtn').onclick=()=>{$('#payBtn').textContent='付款處理中⋯';later(()=>$('#paySheet').classList.add('show'),900)};
// practice
const HINT={1:'輕推：看第二行。你兩邊除以的是正數，還是負數？',2:'問一句：3 比 2 大。兩邊都乘以 −1，變成 −3 和 −2，現在誰比較大？',3:'示範一步：−3x ≤ 12，兩邊同除以 −3，左邊變成 x，右邊變成 −4。不等號的方向交給你。'};
const hBtns=$$('#hints button');
hBtns.forEach(b=>b.onclick=()=>{const l=+b.dataset.l;hBtns.forEach(x=>x.classList.toggle('on',x===b));$('#hintN').textContent=Math.max(l,+$('#hintN').textContent);
  const hb=$('#hintBox');hb.textContent=HINT[l];hb.classList.remove('show');void hb.offsetWidth;hb.classList.add('show');if(hBtns[l])hBtns[l].disabled=false});
$$('#pracOpts .opt').forEach(o=>o.onclick=()=>{$$('#pracOpts .opt').forEach(x=>x.classList.remove('right','wrong'));
  const hb=$('#hintBox');
  if(o.hasAttribute('data-right')){o.classList.add('right');hb.textContent='對了。你用了 '+$('#hintN').textContent+' 級提示，我記下來了。現在換你講給我聽，為什麼會反過來。';enable($('#pracGo'),true)}
  else{o.classList.add('wrong');hb.textContent='這是你上週的答案。不急，按一下「輕推」，我只指給你看是哪一步。'}
  hb.classList.remove('show');void hb.offsetWidth;hb.classList.add('show')});
// say
const SAY='因為⋯兩邊乘負的，數字在數線上會整個翻到另一邊。本來 3 比 2 大，翻過去變成 −3 比 −2 小，所以大小關係反了，不等號也要跟著反。';
mkWave($('#sayWave'),26);let recT=null,recOn=false;
function endRec(){if(!recOn)return;recOn=false;const w=$('#sayWave');stopWave(w,recT);$('#recBtn').classList.remove('on');$('#sayDuo').classList.add('talk');
  $('#recTip').textContent='小陪在聽你剛剛講的⋯';const ck=$$('#checks .ck');
  later(()=>ck[0].classList.add('ok'),700);
  later(()=>{$('#sayQ').textContent='你有講到「數線翻過去」，這就是原因，不是背的。換一題：−x > 5，x 是多少？⋯你答 x < −5，對。';ck[1].classList.add('ok')},1700);
  later(()=>{ck[2].classList.add('later');$('#sayDuo').classList.remove('talk');$('#recTip').textContent='兩個勾了。第三個勾，三天後見。';burst()},2700);
  later(()=>toast('媽媽 · 剛剛','收到好消息：小睿今天講得出「為什麼要變號」'),3500);
  later(()=>{$('#sayShare').style.display='flex';const sc=$('.scr[data-id=say] .sc');sc.scrollTo({top:sc.scrollHeight,behavior:'smooth'})},4200);
}
$('#recBtn').onclick=()=>{if(recOn)return endRec();recOn=true;$('#recBtn').classList.add('on');recT=runWave($('#sayWave'));$('#recTip').textContent='正在聽⋯再按一下結束';type($('#sayTx'),SAY,55,()=>later(endRec,500))};
$('#shareSquad').onclick=function(){this.textContent='已傳給小安';this.disabled=true;later(()=>toast('小安','我聽懂了！數線翻過去那個好記',true),900)};
// classroom
const boards=$$('.board'),stepB=$$('#stepper button');
function clsStage(n){stepB.forEach(b=>{const s=+b.dataset.s;b.classList.toggle('on',s===n);b.classList.toggle('ok',s<n)});boards.forEach(b=>b.classList.toggle('on',+b.dataset.b===n));
  const g=$$('#squadG .av'),A=[0,3,5];g.forEach((a,k)=>{a.classList.remove('grpA','grpB');if(n===2)a.classList.add(A.includes(k)?'grpA':'grpB')});
  $('#clsCoach').textContent=n===1?'小陪：我在旁邊記，不插嘴。':n===2?'小陪：分組看的是這週卡在哪。你在 A 組，林老師先過來。':'小陪：講給小安聽，他只會按「聽懂了」或「再講一次」。';
  if(n===1)playB1()}
function playB1(){const b=$('#b1'),nl=$('#nl');b.classList.remove('played');nl.classList.remove('play');later(()=>{b.classList.add('played');nl.classList.add('play')},700)}
stepB.forEach(b=>b.onclick=()=>clsStage(+b.dataset.s));
$$('[data-stage]').forEach(b=>b.onclick=()=>clsStage(+b.dataset.stage));
$('#b1Play').onclick=playB1;
$('#snap').onclick=()=>{const d=$('#drop');d.classList.add('got');d.innerHTML='<svg class="i"><use href="#i-check"/></svg><span><b>已交給林老師</b><br>只有老師看得到。小陪：你這次有變號。</span>'};
['cMic','cCam'].forEach(id=>$('#'+id).onclick=function(){this.classList.toggle('off')});
$('#cHand').onclick=function(){const on=this.classList.toggle('on');$('#clsCoach').textContent=on?'林老師看到你舉手了，下一個就是你。':'小陪：手放下了。'};
$('#cHelp').onclick=function(){const on=this.classList.toggle('on');$('#clsCoach').textContent=on?'只有林老師知道你需要幫忙，同學看不到。她會私下過來。':'小陪：好，需要再按。'};
$('#pairBtn').onclick=function(){let n=3;this.disabled=true;this.textContent='正在講⋯ '+n;const t=every(()=>{n--;if(n>0){this.textContent='正在講⋯ '+n}else{clearInterval(t);this.textContent='講完了';$('#pairRes').style.display='block'}},800)};
// family
single($$('#rx button'),b=>{const e=$('#rxEcho');e.style.display='grid';e.textContent=b.textContent;later(()=>{e.insertAdjacentHTML('afterend','<span class="day" style="animation:scrIn .4s">小睿的路線上會出現你的回應</span>')},600)});
// retest
$$('#reOpts .opt').forEach(o=>o.onclick=()=>{$$('#reOpts .opt').forEach(x=>x.classList.remove('right','wrong'));
  if(o.hasAttribute('data-right')){o.classList.add('right');$('#reDone').style.display='grid';enable($('#reGo'),true);burst();const sc=$('.scr[data-id=retest] .sc');later(()=>sc.scrollTo({top:sc.scrollHeight,behavior:'smooth'}),80)}
  else o.classList.add('wrong')});
// route
$$('#seg button').forEach(b=>b.onclick=()=>{$$('#seg button').forEach(x=>x.classList.toggle('on',x===b));$('#vFwd').style.display=b.dataset.v==='fwd'?'grid':'none';$('#vBack').style.display=b.dataset.v==='back'?'grid':'none'});
// ops
$$('#opsQ [data-ok]').forEach(b=>b.onclick=()=>{if(b.disabled)return;b.disabled=true;b.textContent='已處理';b.closest('.q').classList.add('ok');const n=$('#opsN');n.textContent=Math.max(0,+n.textContent-1)});

/* ---------- on-enter resets ---------- */
const ENTER={
 diag(){dOpts.concat(dWhy).forEach(x=>x.classList.remove('sel'));$('#diagWhy').style.display='none';$('#diagProg').style.width='50%';enable($('#diagGo'),false)},
 invite(){const e=$('#eqInvite');e.classList.remove('play');later(()=>e.classList.add('play'),1100)},
 teacher(){$('#tTx').textContent='按播放，聽林老師怎麼帶課。'},
 parentpay(){$('#paySheet').classList.remove('show');$('#payBtn').textContent='用 LINE Pay 付款'},
 home(){later(()=>{$('#squadProg').style.width='50%';$('#squadTxt').textContent='目前 3 / 6 · 小晴剛剛點亮一個'},1400)},
 practice(){$('#hintBox').classList.remove('show');$('#hintN').textContent='0';hBtns.forEach((b,k)=>{b.classList.remove('on');b.disabled=k>0});$$('#pracOpts .opt').forEach(x=>x.classList.remove('right','wrong'));enable($('#pracGo'),false)},
 say(){recOn=false;$('#recBtn').classList.remove('on');$('#sayDuo').classList.remove('talk');$$('#checks .ck').forEach(c=>c.classList.remove('ok','later'));$('#sayTx').textContent='⋯';$('#sayTx').style.color='var(--faint)';$('#sayShare').style.display='none';$('#recTip').textContent='按一下開始，再按一下結束';
   $('#sayQ').textContent='為什麼兩邊除以負數，不等號要反過來？用你自己的話講，30 秒就好。';const s=$('#shareSquad');s.disabled=false;s.textContent='講給小安聽'},
 class(){clsStage(1);let sec=41*60+12;every(()=>{sec--;$('#clsTimer').textContent='剩 '+String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0')},1000)},
 finish(){const r=$('#ring');r.classList.remove('go');$('#ringN').textContent='0';const av=$$('#finAvs .av');av.forEach(a=>a.classList.remove('done'));
   later(()=>r.classList.add('go'),300);av.forEach((a,k)=>later(()=>{a.classList.add('done');$('#ringN').textContent=k+1;if(k===5)burst()},450+k*260))},
 retest(){$$('#reOpts .opt').forEach(x=>x.classList.remove('right','wrong'));$('#reDone').style.display='none';enable($('#reGo'),false)}
};

const h=location.hash.slice(1);go(Math.max(0,STEPS.findIndex(s=>s.id===h)));
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);
})();
