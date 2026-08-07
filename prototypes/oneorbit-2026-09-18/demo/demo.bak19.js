(function(){
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const BIZ=['診斷','配對','付費','上課','學會','續約'];
const ROLES={student:['學','學生 · 小睿的手機'],parent:['家','家長 · 媽媽的 LINE'],class:['學','學生 · 小睿的 iPad'],teacher:['師','老師 · 林老師的 iPad'],ops:['師','老師 · 林老師的 iPad']};
const STEPS=[
 {g:'開始',id:'welcome',dev:'Phone',role:'student',biz:0,t:'第一眼：兩分鐘，或先逛逛',
  why:'下載、登入、每天的練習都免費。第一頁只要兩分鐘，也可以直接跳過先看看。門檻越低，進來的孩子越多；付費的時刻放在他真的需要的時候。',
  ev:['原本的 20 分鐘診斷太長：國中生在第一個 60 秒沒拿到東西就會離開','「先逛逛」不是流失，是把診斷延後到他有動機的那一刻','兩個圓點就是品牌，也是 AI 教練「小陪」'],dr:['低門檻開始','自主']},
 {g:'開始',id:'goal',dev:'Phone',role:'student',biz:0,t:'目標：先問你要去哪',
  why:'陪跑教練的第一句話不是「來考試」，是「你想要什麼」。點一個目標後，會看到小陪已經依學校行事曆帶入年級、學校正在教什麼、段考日期：小隊課會對準孩子自己的段考。',
  ev:['家長最在意的是段考：先知道學校教到哪、哪天考，8 週才對得準','目標可以不是分數：「不要再怕數學」也算','連結健康資料是選項不是條件；只看趨勢，不給老師和家人看數字','全部可跳過，之後在「我」裡面補'],dr:['自主','被理解','目標感']},
 {g:'開始',id:'diag',dev:'Phone',role:'student',biz:0,t:'初診：三種 90 秒內的方式',
  why:'拍一張考卷（10 秒）、看 3 題憑感覺選（90 秒）、或直接用說的。不用算、不用考完。三個都點點看。完整的診斷分散到之後每天的練習裡，越用越準。',
  ev:['「挑出別人哪一步怪怪的」比自己解題快十倍，而且一樣測得出概念','拍考卷是家長和孩子最直覺的動作，也是最好的分享素材','初診只要準到能給出第一個卡點就夠了'],dr:['低門檻開始','被理解']},
 {g:'開始',id:'result',dev:'Phone',role:'student',biz:0,t:'初步結果：你只卡在一步',
  why:'把「數學不好」縮小成「一個點」。孩子第一次看到自己的問題是有邊界的、走得完的，這是整個產品最重要的情緒轉折。',
  ev:['路徑圖取代分數：會了（綠）、卡住（珊瑚，會跳動）、已掌握（金）','把舊的洞和學校正在教的連起來：家長一看就懂為什麼要先補','「有 5 個人跟你卡在同一步」：把丟臉變成有伴'],dr:['勝任感','歸屬感']},
 {g:'加入小隊',id:'when',dev:'Phone',role:'student',biz:1,t:'你什麼時候可以：點幾格就好',
  why:'要湊得成隊，先要知道誰什麼時候有空。孩子點幾格有空的時段、標一下補習和社團，小陪就能在等候池裡找到卡點相同、時間也對得上的人。點幾格試試。',
  ev:['這一步接到老師版的「開課機會」：先有湊好的隊，才去問老師','一整週、從早到晚都能選，不預設孩子只有晚上有空（寒暑假、自學、週末都不同）','點星期可以整欄選；也可以直接用說的','時間可以之後在「我」裡面改'],dr:['自主','低門檻開始']},
 {g:'加入小隊',id:'invite',dev:'Phone',role:'student',biz:1,t:'小隊邀請：對準段考的 8 週',
  why:'卡點只是起點，不是整門課。這 8 週的課表事先排好：先補全隊一起卡住的洞（2 週）→ 第一次段考後一起訂正 → 跟上學校正在教的 → 最後兩週衝第二次段考。每週的題目，再用全隊這週真的錯的題和問的問題來排。',
  ev:['課表由教研團隊依年級、程度、考試事先設計；小陪只負責每週依全隊調題目，老師確認','為什麼是這六個人：同一個洞、同樣的學校進度、程度相近、同一個晚上有空','老師先答應，邀請才會送到孩子手上；48 小時內一定有答案','第一堂試上，不滿意不收費'],dr:['目標感','歸屬感','可預期的節奏']},
 {g:'加入小隊',id:'teacher',dev:'Phone',role:'student',biz:1,t:'認識老師：不看星星，看學生過幾天還會不會',
  why:'老師頁最大的數字是「學生過幾天還講得出來的比例」。這是平台選老師、排老師、發季獎金的同一把尺。按播放聽 30 秒。',
  ev:['AI 先知道要開什麼課，再依卡點類型找擅長的老師','老師每隊約 NT$1,000，季獎金跟著這個數字走'],dr:['信任','透明']},
 {g:'加入小隊',id:'sent',dev:'Phone',role:'student',biz:1,t:'孩子先說要，家長才付錢',
  why:'報名由孩子按下去。家長收到的是「他自己想加入」，不是又一個被安排的補習。這一步決定了三週後他還在不在。',
  ev:['三週流失的第一大原因：被逼著來的','AI 湊名單、老師先答應，家長付款滿 4 人才成班：機器建議、人負責'],dr:['自主','承諾']},
 {g:'加入小隊',id:'parentpay',dev:'Line',role:'parent',biz:2,t:'家長：在 LINE 裡看懂、同意、付款',
  why:'家長不用下載 App。先看懂孩子卡在哪、這一期 8 週怎麼走、對準哪一次段考，再選方案、同意、付款，全部在 LINE 完成。勾兩個同意、按付款試試。',
  ev:['家長買的不是「配對」，是「8 週後的段考」：所以第一則訊息就講這一期對準哪一次考試','第一堂家長可以在旁邊看：對線上課不放心的家長，眼見為憑','走 LINE／網頁付款，不經 App 內購，省下 15–30% 通路費','同意書明講家長看得到什麼、看不到什麼，避免變成監控工具'],dr:['家人迴路','透明']},
 {g:'每天',id:'checkin',dev:'Phone',role:'student',biz:3,t:'狀態：今天、這週、學會的',
  why:'原本的「狀態」和「路線」合成一個分頁，因為講的是同一件事：我現在怎麼樣、這週怎麼排、我走到哪。上方三段切換：今天（小陪的觀察、心情紀錄、今天的數字、目標）→ 這週（每天排什麼、心情與睡眠）→ 學會的（真的會了的點與家人的回應）。底部分頁改成 首頁／小隊／說給我聽／狀態／我。',
  ev:['少一個分頁，孩子不用想「進度要去哪裡看」','小隊獨立成一個分頁：下一堂、隊友、老師的話、請假都在那裡','心情是紀錄不是問卷；每個數字都標來源；原始數據只留給孩子自己'],dr:['狀態感知','自主','目標感']},
 {g:'每天',id:'home',dev:'Phone',role:'student',biz:3,t:'首頁：今天照你的步調',
  why:'每天最多兩件事，22:30 關燈。小陪看過睡眠後自動減量。小隊目標是六個人合計，沒有誰拖累誰。',
  ev:['國中生的黃金時段是 20:30–22:00，提醒只落在這段','合作型目標取代個人連勝：不用「斷了就歸零」的損失恐懼','小陪是陪練工具，不扮演情緒伴侶：話少、具體、只談學習節奏'],dr:['小隊合作目標','不羞辱','狀態感知']},
 {g:'每天',id:'practice',dev:'Phone',role:'student',biz:3,t:'練習：先示範，再慢慢撤掉幫助',
  why:'完全不會的孩子，一直被反問只會更挫折。所以先給「看一個例子」（用不同的題目示範完整解法），有想法了再用三級提示，最後自己做。看過示範的題不算獨立完成，之後會再給一題新的。按按看。',
  ev:['研究顯示：對初學者先示範再撤除幫助，比永遠只問不教有效；對已有基礎的才用追問','無限制的 AI 協助會讓拿掉 AI 後的表現下降，所以示範用不同的題、並標記協助程度','用到哪一種幫助都會記下來，老師上課前看得到'],dr:['勝任感','剛好的難度']},
 {g:'每天',id:'say',dev:'Phone',role:'student',biz:4,t:'說給我聽：產品的心臟',
  why:'講得出來才算會。能力分五級：還不確定 → 有幫助下完成 → 自己完成 → 過幾天還會 → 換情境也會用。這一頁走前三級，按麥克風試試。下面還有一個入口：不會的題目可以拍照上來，小陪用問的帶孩子解。',
  ev:['教別人的學習效果顯著高於自己複習，有真人在聽時效果接近兩倍','錄音不保留，只留三個勾：未成年人資料最小化','好消息預設分享給家人，其他由孩子決定'],dr:['勝任感','家人迴路','教隊友']},
 {g:'每天',id:'ask',dev:'Phone',role:'student',biz:3,t:'拍一題問小陪：不給答案，給問題',
  why:'孩子最常做的事就是拍題目找答案。我們不擋這個動作，但把它變成學習：拍上來之後，小陪一步一步問——這題在問什麼、第一步想做什麼、除以負數要注意什麼——孩子自己走到答案。按按看選項，故意選錯也可以。',
  ev:['解題 App 給答案，孩子照抄；我們給問題，孩子自己解，隔幾天還會','連續說不確定兩次，小陪會用「另一題」示範一次，再換孩子做自己拍的這題','拍上來的題目自動進錯題本，過幾天不給提示再問一次','孩子用了哪一級幫助都會記下來，老師上課前看得到'],dr:['勝任感','剛好的難度','自主']},
 {g:'每天',id:'plus',dev:'Phone',role:'student',biz:2,t:'付費時刻：免費用完，不是被擋住',
  why:'免費版每天都能用，付費只出現在他想要更多的時候。孩子不能付錢，只能決定要不要傳給家人。上小隊課的那 8 週，Plus 免費附。',
  ev:['三種收入：Plus 月訂閱（AI 教練）、小隊課 8 週一包（真人）、一對一加購','訂閱給的是穩定收入與留存，上課給的是毛利與成效','「明天再來就好」永遠是一個正常選項，不做罪惡感設計'],dr:['自主','家人迴路']},
 {g:'上課',id:'lock',dev:'Phone',role:'student',biz:3,t:'上課提醒與請假：有人在等你，也可以不來',
  why:'通知的主詞是隊友和老師，不是系統。點「今天請假」試試。原則是「團體不等人，個人不掉隊」：課表照走，補的動作在課堂外完成，下一堂老師用暖身第一題確認他補起來了。三種補法：改上同主題的別隊（最好）、補課包 15 分鐘、或這堂不補退回堂數。',
  ev:['補課包＝白板快照＋小陪重述重點＋2–3 題＋說給我聽一次；不是整堂錄影，課堂不留錄影','24 小時前請假：換別隊或補課包都免費，學費不退（老師已備課）；臨時請假每月 1 次可退堂數','隊友只看到「今天請假」，看不到原因，也不用等他','8 週內缺超過 3 堂，小陪建議轉下一期或改一對一，保護另外五個人的節奏','老師端同步：課前一頁標出誰請假、怎麼補、回來時怎麼確認'],dr:['自主','不羞辱','歸屬感']},
 {g:'上課',id:'class',dev:'Pad',role:'class',biz:3,t:'小隊教室：跟老師看同一塊白板',
  why:'中間是老師的白板，她畫什麼你同步看到；上方是同一條 50 分鐘教案軌，老師按下一段，你的畫面跟著換：暖身投票 → 講解 → 自己寫（直接寫在板子上，只有老師看得到）→ 分組 → 講給隊友聽 → 一句我搞懂的。點上方六段走一次。',
  ev:['老師版和學生版是同一塊板、同一條時間軸','自己的作答只有老師看得到；答錯不公開','分組時其他組的視訊會淡掉，只聽得到自己這組'],dr:['互相講','安全感','真人老師']},
 {g:'上課',id:'finish',dev:'Phone',role:'student',biz:4,t:'小隊：下一堂、隊友、老師的話',
  why:'「小隊」是底部固定的分頁。最上面是下一堂課和請假，接著是這一期 8 週走到哪；中間是這一堂六個人都講出來了沒；最下面可以丟一個問題給下週，林老師上課前會看到。試著丟一個問題。',
  ev:['孩子丟的問題，週日由小陪和全隊的錯題一起排出「這週要解的 3 題」，老師確認後上課','沒過的人隔天補一格就亮，沒有排名、沒有人被公開點名','請假入口放在下一堂課旁邊，不用去別的地方找'],dr:['小隊合作目標','被看見','歸屬感']},
 {g:'上課',id:'family',dev:'Line',role:'parent',biz:4,t:'家人：今晚可以問他什麼',
  why:'不給家長分數，給他們一句今晚能問的話。孩子講給家人聽，就是再練一次。按一個回應試試。',
  ev:['家長最常說的困擾：不知道怎麼關心才不會吵架','家長的回應會出現在孩子的路線上，形成迴路','週報只含孩子選擇分享的項目'],dr:['家人迴路','自主']},
 {g:'學會',id:'retest',dev:'Phone',role:'student',biz:4,t:'過幾天：不提示再測，才算真的學會',
  why:'這是對家長最硬的成果指標：再測通過率。過了，這個點變金色，永遠不會掉。選正確答案看看。',
  ev:['試點關卡：再測通過率 ≥ 70%','金色不會因為沒來而消失：成就是存下來的，不是租來的'],dr:['勝任感','看得見的累積']},
 {g:'續走',id:'review',dev:'Phone',role:'student',biz:5,t:'8 週回顧：孩子自己決定要不要續',
  why:'這一期結束在段考。孩子上傳考卷，小陪對照兩次段考：分數變了多少、哪一類錯不見了。續約的理由不是折扣，是「我真的進步了，下一期想跟同一群人一起準備期末考」。',
  ev:['試點關卡：續購率 ≥ 50%','段考對照是家長續報最有力的理由，但成績只有孩子同意才分享','可以換程度：阿哲去了進階的隊，不是失敗，是分程度在運作'],dr:['歸屬感','自主']},
 {g:'續走',id:'renew',dev:'Line',role:'parent',biz:5,t:'家長續約：一頁成果，一個按鈕',
  why:'家長看到的是兩次段考的對照、已掌握的點、老師的一句話，以及下一期對準哪一次考試。成績只有孩子願意才出現。',
  ev:['續約由孩子先按「我想繼續」，家長看完一頁成果才付款，不打推銷電話','這一頁的格式，之後也是給機構與政府看的成效報告'],dr:['家人迴路','成果透明']}
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
  document.querySelector('.main').classList.toggle('wide',s.dev==='Pad');renderCtx(s,i);fit();$('#sChat').classList.remove('on');$('#lvSheet').classList.remove('show');$('#lvScrim').classList.remove('on');
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
// goal
single($$('#goalChips button'),()=>{$('#goalMore').style.display='flex';enable($('#goalGo'),true)});
$('#goalRange').oninput=e=>$('#goalTo').textContent=e.target.value;
$$('#goalTime button').forEach(b=>b.onclick=()=>$$('#goalTime button').forEach(x=>x.classList.toggle('on',x===b)));
$('#goalHealth').onclick=function(){this.textContent='已連結 · 只看趨勢';this.disabled=true};
// quick check
const QC=[['−2x &gt; 6','x &gt; −3','兩邊同除以 −2'],['−x ≤ 4','x ≤ −4','兩邊同乘以 −1'],['3x &lt; 12','x &lt; 4','兩邊同除以 3']];let qi=0;
function qShow(){const c=QC[qi];$('#qEq').innerHTML='<span class="math">'+c[0]+'</span><span style="font-family:Noto Sans TC;font-style:normal;font-size:13px;color:var(--mute)">↓ '+c[2]+'</span><span class="math res">'+c[1]+'</span>';$('#diagProg').style.width=(qi/3*100)+'%';$('#qNote').style.visibility='hidden';$$('#qBtns .opt').forEach(x=>x.classList.remove('sel'))}
function qMode(m){['qPick','qScan','qCards'].forEach(id=>$('#'+id).style.display=id===m?'flex':'none')}
$('#qSwipe').onclick=()=>{qi=0;qMode('qCards');qShow()};
$('#qSay').onclick=()=>{qi=0;qMode('qCards');qShow()};
$$('#qBtns .opt').forEach(b=>b.onclick=()=>{$$('#qBtns .opt').forEach(x=>x.classList.remove('sel'));b.classList.add('sel');$('#qNote').style.visibility='visible';$('#qNoteTx').textContent=['收到，不說對錯，下一題。','好，再一題就好。','夠了，我大概知道了。'][qi];
  later(()=>{qi++;if(qi<3)qShow();else{$('#diagProg').style.width='100%';later(()=>go('result'),500)}},800)});
$('#qPhoto').onclick=()=>{qMode('qScan');const sc=$('.scan');sc.classList.remove('done');$('#qScanTx').textContent='我在看⋯';later(()=>{sc.classList.add('done');$('#qScanTx').textContent='四題裡錯的兩題是同一個原因。我知道了。'},3000);later(()=>go('result'),4600)};
// ===== 小陪 chat (student) =====
const SSUG={when:['平日晚上和週六下午我都可以','週二我有補習'],home:['今天可以少一點嗎？','這題我不會','我想換一個目標'],checkin:['我昨天其實有睡 7 小時','把目標改成 80 分'],route:['下一步要練什麼？'],_:['今天可以少一點嗎？','這週三我要請假','我想換一個目標']};
function scSay(h,c){const d=document.createElement('div');d.className='msg '+c;d.innerHTML=h;$('#scM').appendChild(d);$('#scM').scrollTop=9e9}
function scAsk(q){if(!q)return;scSay(q,'u');setTimeout(()=>{let h;
 if(/晚上|下午|可以|有空/.test(q)&&/平日|週/.test(q))h='好，我幫你填：<b>平日 19–21、週六 12–17</b>。<div class="act"><button data-sc="when">套用</button><button class="o" data-sc="no">不是</button></div>';
 else if(/補習|社團/.test(q))h='好，<b>週二晚上</b>我標成有事，不會排你。<div class="act"><button data-sc="busy">好</button></div>';
 else if(/少一點|累/.test(q))h='可以。今天只留「說給我聽 5 分鐘」，其他挪到週末，目標不受影響。<div class="act"><button data-sc="less">就這樣</button></div>';
 else if(/不會|這題|不懂/.test(q))h='拍給我看。我不會直接給答案，我會一步一步問你，你自己解出來。<div class="act"><button data-sc="ask">拍一題給小陪</button></div>';
 else if(/請假/.test(q))h='好，我幫你打開請假，選哪一堂、怎麼補就好。<div class="act"><button data-sc="leave">打開請假</button></div>';
 else if(/目標|分/.test(q))h='好，我帶你去改目標。改完我會告訴你到不到得了。<div class="act"><button data-sc="goal">去改目標</button></div>';
 else if(/睡/.test(q))h='收到，我把昨晚改成你說的 7 小時。以後數字不對都可以跟我說。';
 else h='我可以幫你：調今天的量、改目標、改有空的時間、請假。功課的問題請到練習裡問我，我會一步一步帶。';
 scSay(h,'a')},600)}
function scOpen(q){const id=STEPS[cur].id;$('#sChat').classList.add('on');$('#scS').innerHTML=(SSUG[id]||SSUG._).map(x=>'<button type="button">'+x+'</button>').join('');if(!$('#scM').children.length)scSay('嗨小睿。要調時間、改目標、請假，跟我說就好。','a');if(q)scAsk(q)}
$('#scX').onclick=()=>$('#sChat').classList.remove('on');
$('#scS').onclick=e=>{const b=e.target.closest('button');if(b)scAsk(b.textContent)};
$('#scF').onsubmit=e=>{e.preventDefault();const v=$('#scIn').value.trim();$('#scIn').value='';scAsk(v)};
$('#scMic').onclick=function(){this.classList.add('rec');$('#scIn').placeholder='正在聽⋯';setTimeout(()=>{this.classList.remove('rec');$('#scIn').placeholder='打字，或按左邊用說的';scAsk((SSUG[STEPS[cur].id]||SSUG._)[0])},1300)};
document.addEventListener('click',e=>{const k=e.target.closest('[data-ask]');if(k)return scOpen(k.dataset.ask);const b=e.target.closest('[data-sc]');if(!b)return;const a=b.dataset.sc;b.parentElement.querySelectorAll('button').forEach(x=>x.disabled=true);
 if(a==='when'){$$('#whgrid .c').forEach(c=>{const [d,r]=c.dataset.k.split('-').map(Number);if((d<5&&r===3)||(d===5&&r===1))c.classList.add('on')});whUpd();$('#sChat').classList.remove('on')}
 else if(a==='busy'){const c=$('#whgrid [data-k="1-3"]');if(c){c.classList.remove('on');c.classList.add('busy')}scSay('標好了。','a')}
 else if(a==='leave'){$('#sChat').classList.remove('on');const id=STEPS[cur].id;lvOpen(id==='finish'?'930':'923',id)}
 else if(a==='ask'){$('#sChat').classList.remove('on');go('ask')}
 else if(a==='goal'){$('#sChat').classList.remove('on');go('checkin');setTimeout(()=>{$('#gForm').classList.add('on');$('#gForm').scrollIntoView({block:'center'})},250)}
 else if(a==='less'){scSay('改好了，首頁只剩一件事。','a')}
 else scSay('好，你再說一次。','a')});
// student leave (one sheet, many entries)
const LVC={'923':['9/23（三）',new Date(2026,8,23,19)],'930':['9/30（三）',new Date(2026,8,30,19)],'107':['10/7（三）',new Date(2026,9,7,19)]};
const LVNOW={home:new Date(2026,8,21,20,35),lock:new Date(2026,8,23,18,50),finish:new Date(2026,8,23,19,58)};
let lvk='923',lvx='home',lvo='swap';
function lvInfo(){const now=LVNOW[lvx]||LVNOW.home,m=(LVC[lvk][1]-now)/60000,t=m<60?'還有 '+Math.round(m)+' 分鐘':m<1440?'還有 '+Math.round(m/60)+' 小時':'還有 '+Math.floor(m/1440)+' 天';
 $('#lvInfo').innerHTML=m<1440?'<span class="chip c">'+t+'</span><span>臨時請假 · 這個月免費還有 <b>1</b> 次</span>':'<span class="chip">'+t+'</span><span>24 小時前請假，不扣次數</span>';
 $$('#lvPk button').forEach(b=>{b.disabled=LVC[b.dataset.k][1]<now;b.classList.toggle('on',b.dataset.k===lvk)})}
function lvOpen(k,x){lvk=k;lvx=x;$('#lvPack').classList.remove('on');$('#lv1').style.display='grid';$('#lv2').style.display='none';lvInfo();$('#lvSheet').classList.add('show');$('#lvScrim').classList.add('on')}
function lvClose(){$('#lvSheet').classList.remove('show');$('#lvScrim').classList.remove('on')}
$('#lvPk').onclick=e=>{const b=e.target.closest('button');if(b&&!b.disabled){lvk=b.dataset.k;lvInfo()}};
$('#lvX').onclick=lvClose;$('#lvScrim').onclick=lvClose;$('#lvOk').onclick=lvClose;
$('#lvChip').addEventListener('click',e=>{e.stopPropagation();lvOpen('923','lock')});
document.addEventListener('click',e=>{const b=e.target.closest('[data-lv]');if(b)lvOpen(b.dataset.lv,STEPS[cur].id)});
single($$('#lvR button'));$$('#lvO button').forEach(b=>b.onclick=()=>{lvo=b.dataset.o;$$('#lvO button').forEach(x=>x.classList.toggle('on',x===b))});
$('#lvGo').onclick=()=>{const T={swap:['改上週六 10:00 那一隊','王老師會拿到你的卡點和上週紀錄。進度不會落後。'],self:['小陪幫你補一格','隔天 15 分鐘，補完就跟上。'],none:['這堂不補，堂數退回','這一堂不扣，下個月可以用。']}[lvo];
 const P={swap:['<b>你這一堂會去：週六 10:00 王老師那一隊</b>','<div><i>1</i>同一個主題，同一週的進度</div><div><i>2</i>還有 1 個位子，小陪已經幫你卡好</div><div><i>3</i>回來上課時，林老師會用暖身第一題確認你跟上了</div>','<small>去別隊上完就不用補課包。</small>'],
  self:['<b>補課包 · 15 分鐘</b>','<div><i>1</i>白板快照：老師那天寫的重點</div><div><i>2</i>小陪把老師講的重述一次（不是整堂錄影）</div><div><i>3</i>2–3 題＋說給我聽一次</div>','<small>明天做完就跟上。下一堂老師會用暖身第一題確認你。</small>'],
  none:['<b>這一堂不補</b>','<div><i>1</i>堂數退回，下個月可以用</div><div><i>2</i>課後整理還是會送到你的「狀態」</div><div><i>3</i>下一堂老師會先確認你有沒有跟上</div>','<small>這個月的免費不補還有 0 次。</small>']}[lvo];
 $('#lvT').textContent=LVC[lvk][0]+' 已請假';$('#lvD').innerHTML='<b style="color:var(--pine-ink)">'+T[0]+'</b><br>'+T[1]+'<br>媽媽和林老師都收到了。';
 $('#lvPack').innerHTML=P.join('');$('#lvPack').classList.add('on');$('#lv1').style.display='none';$('#lv2').style.display='grid'};
// 拍一題問小陪
const GQ=[
 {q:'先不要算。你覺得這一題在問什麼？',o:[['x 的範圍',1],['x 等於多少',0],['我不確定',-1]],ok:'對，它問的是範圍，所以答案長得像「x ≤ 幾」或「x ≥ 幾」。',no:'再看一次那個符號：≤ 是「小於等於」，所以它問的是一個範圍，不是一個數字。'},
 {q:'那第一步你想做什麼？',o:[['兩邊同除以 −3',1],['兩邊同減 12',0],['我不確定',-1]],ok:'好，那就除。',no:'減 12 也不算錯，但 x 前面還掛著 −3，先把它處理掉比較快。'},
 {q:'除以負數的時候，有一件事要注意。你記得是什麼嗎？',o:[['不等號要換方向',1],['不用換',0],['想不起來',-1]],ok:'就是這件事。',no:'先別急著背。想一下：−2 × 1 和 −2 × 2，哪個比較大？'},
 {q:'換你算。答案是哪一個？',o:[['x ≥ −4',1],['x ≤ −4',0],['我想再看一次示範',-1]],ok:'你自己走完了。',no:'再看一次：兩邊除以 −3，而且方向要換過來。'}
];
const DEMO='<div class="gqd"><b>我用「別的題目」示範一次，你拍的那題留給你自己做</b><div>−2<i>x</i> &gt; 6 → 兩邊同除以 −2 → <i>x</i> &lt; −3</div><div>看到了嗎：除以負數，&gt; 變成了 &lt;。現在換你回去做 −3<i>x</i> ≤ 12。</div></div>';
let gqi=0;
function gqSay(cls,html){const d=document.createElement('div');d.className=cls;d.innerHTML=html;$('#gqList').appendChild(d);const sc=$('.scr.on .sc');if(sc)sc.scrollTop=9e9;return d}
function gqAsk(){const g=GQ[gqi];if(!g){$('#askDone').style.display='grid';const sc=$('.scr.on .sc');later(()=>{if(sc)sc.scrollTop=9e9},60);return}
 gqSay('gqq',g.q);const box=gqSay('gqo',g.o.map((x,k)=>'<button data-o="'+k+'">'+x[0]+'</button>').join(''));
 box.onclick=e=>{const b=e.target.closest('[data-o]');if(!b)return;const [txt,val]=g.o[+b.dataset.o];
  box.querySelectorAll('button').forEach(x=>x.disabled=true);gqSay('gqa',txt);
  later(()=>{if(val===1){gqSay('gqq',g.ok);gqi++;later(gqAsk,500)}
   else if(val===0){gqSay('gqq',g.no);later(()=>{box.querySelectorAll('button').forEach(x=>{x.disabled=false});gqSay('gqq','再選一次，選錯沒關係。')},500)}
   else{gqSay('gqd',DEMO.replace('<div class="gqd">','').replace(/<\/div>$/,''));later(()=>{box.querySelectorAll('button').forEach(x=>{x.disabled=false});gqSay('gqq','看完了，換你。')},600)}},520)}}
function askReset(){gqi=0;$('#gqList').innerHTML='';$('#askDone').style.display='none';$('#askUp').style.display='grid';$('#askGo').style.display='none';$('#shotBox').classList.remove('scanning')}
function askShot(){$('#shotBox').classList.add('scanning');later(()=>{$('#askUp').style.display='none';$('#askGo').style.display='grid';later(gqAsk,400)},1300)}
$('#askCam').onclick=askShot;$('#askLib').onclick=askShot;
// state page v3
const TASK={rev:['i-pencil','回顧不等式錯題','20 分'],say:['i-mic','說給我聽','5 分'],plus:['i-spark','加分題：分數係數','10 分'],walk:['i-walk','先走 10 分鐘','10 分']};
const MOOD=[['開心','#F4B740','今天狀態很好。要不要趁現在挑戰一題難的？','ok'],['愉悅','#3FB5A3','不錯的一天。照平常的節奏走。','ok'],['平靜','#5B8DB8','平平的也很好。今天兩件小事就好。','soso'],['低落','#6F7F95','收到。今天只留一件最小的事，其他我挪到週末。','tired'],['焦慮','#E0913A','離段考還有 15 天，進度是夠的。先走 10 分鐘，回來只做一件。','upset'],['生氣','#E5604E','不問為什麼。今天可以什麼都不做，想動再說。','upset']];
const PLANS={ok:['rev','say'],soso:['say','rev'],tired:['say'],upset:['walk']};
let pl=['say','rev'];
function apDraw(){$('#apList').innerHTML=pl.map(k=>'<div class="ap-i"><svg class="i"><use href="#'+TASK[k][0]+'"/></svg>'+TASK[k][1]+'<span>'+TASK[k][2]+'</span></div>').join('')||'<div class="ap-i">今天休息。目標不受影響，我把進度挪到週末。</div>'}
single($$('#moodChips button'),b=>{const m=MOOD[+b.dataset.i];$('#mOrb').style.background=m[1];$('#mName').textContent=m[0];$('#mName').style.color=m[1];$('#mLine').textContent='20:34 記下了。'+(+b.dataset.i>2?'想說原因可以點下面，不說也沒關係。':'');$('#moodWhy').style.display='flex';pl=PLANS[m[3]].slice();apDraw();type($('#obsTx'),'昨晚睡 5.9 小時。'+m[2],22);window.__mood=b;window.__moodName=m[0];$('#apOk').textContent='照這樣'});
$('#moodWhy').onclick=e=>{const b=e.target.closest('button');if(b)b.classList.toggle('sel')};
$$('#stSeg button').forEach(b=>b.onclick=()=>{$$('#stSeg button').forEach(x=>x.classList.toggle('on',x===b));const v=b.dataset.v;$('#stToday').style.display=v==='d'?'grid':'none';$('#stWeek').style.display=v==='w'?'grid':'none';$('#stJourney').style.display=v==='j'?'grid':'none';
 if(v==='w'){$('#hSub').textContent='過去 7 天';const seq=[2,2,1,2,3,2,2];$('#hMood').innerHTML=['二','三','四','五','六','日','今'].map((d,i)=>'<i style="--c:'+MOOD[seq[i]][1]+'">'+d+'</i>').join('');$('#hSleep').innerHTML=[7.2,6.8,7.0,5.5,7.5,8.1,5.9].map(h=>'<i class="'+(h<6.5?'low':'')+'" style="height:'+(h*10)+'%"></i>').join('')}
 if(v==='j')jGo()});
$('#apOk').onclick=function(){this.textContent='好，回首頁';later(()=>go('home'),500)};
$('#apMore').onclick=()=>{if(!pl.includes('plus')){pl.push('plus');apDraw()}};
$('#apRest').onclick=()=>{pl=[];apDraw()};
const SRC={sleep:'<div class="r"><b>睡眠來自 Apple 健康</b><span class="fine">只讀時數，不讀其他</span></div><div class="why"><button>數字不對，我自己填</button><button>先暫停讀取</button></div><span class="fine" style="text-align:left">原始數字只留在你的手機。老師只看得到「本週睡眠偏少」，家人看不到。</span>',
 steps:'<div class="r"><b>步數來自 Apple 健康</b><span class="fine">走得少，我會插一格走 5 分鐘</span></div><div class="why"><button>先暫停讀取</button></div>',
 exam:'<div class="r"><b>從學校行事曆帶入：第一次 10/6、第二次 11/18</b></div><div class="why"><button>改日期</button><button>加一個考試</button></div>'};
$('#srcCards').onclick=e=>{const b=e.target.closest('[data-src]');if(!b)return;const on=b.classList.contains('sel');$$('#srcCards button').forEach(x=>x.classList.remove('sel'));const p=$('#srcPanel');if(on){p.classList.remove('on');return}b.classList.add('sel');p.innerHTML=SRC[b.dataset.src];p.classList.remove('on');void p.offsetWidth;p.classList.add('on')};
$('#srcPanel').onclick=e=>{const b=e.target.closest('button');if(b){b.classList.toggle('sel')}};
$('#gEdit').onclick=()=>$('#gForm').classList.toggle('on');
function gAi(){const v=+$('#gRange').value,t=[15,30,45][$$('#gTime button').findIndex(x=>x.classList.contains('on'))];$('#gVal').textContent=v;const need=(v-70)*1.1,have=t*18/30*1.0*1.2;$('#gAi').textContent=have>=need+3?v+' 分、每天 '+t+' 分：到得了，還有餘裕。':have>=need?v+' 分、每天 '+t+' 分：剛好到得了，不能常休息。':v+' 分、每天 '+t+' 分：有點趕。建議先設 '+Math.max(72,Math.round(70+have/1.1))+' 分，或加一堂小隊課。'}
$('#gRange').oninput=gAi;$$('#gTime button').forEach(b=>b.onclick=()=>{$$('#gTime button').forEach(x=>x.classList.toggle('on',x===b));gAi()});
single($$('#gKind button'));
$('#gSave').onclick=()=>{$('#gTitle').textContent='我的目標：段考數學 '+$('#gRange').value;$('#gPace').textContent=$('#gAi').textContent.includes('趕')?'有點趕':'照這個步調到得了';$('#gForm').classList.remove('on')};
$('#askPlus').onclick=function(){this.textContent='已傳到媽媽的 LINE';this.disabled=true;later(()=>toast('媽媽','我看看喔，晚點回你'),1200)};
// invite
$('#qBox').onsubmit=e=>{e.preventDefault();const v=$('#qIn').value.trim()||'分數前面有負號怎麼辦';$('#qIn').value='';$('#qTx').textContent='已放進下週的問題箱：「'+v+'」· 不會顯示你的名字';$('#qTx').classList.add('ok')};
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
$('#showEx').onclick=()=>{const hb=$('#hintBox');hb.innerHTML='<b>例子（換一題）</b><br><span class="math">−5x ≤ 10</span><br>兩邊同除以 −5，除以負數方向要反過來<br><span class="math">x ≥ −2</span><br><small style="color:var(--mute)">看過例子，這題不算獨立完成；等一下我會再給你一題新的。</small>';hb.classList.remove('show');void hb.offsetWidth;hb.classList.add('show');$('#hintN').textContent='例'};
$('#makeRow').onclick=function(){this.querySelector('small').textContent='已加進這週的可選任務，會取代 3 題重複練習';this.querySelector('.chip').textContent='已加'};
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
// classroom v2
const SB=[['poll','暖身'],['board','一起看常錯的'],['try','自己試試'],['group','再帶一次'],['pair','講給隊友聽'],['exit','我搞懂的']],SLEFT=['5','7','9','9','6','3'];
const SCO=['小陪：憑直覺選就好，答錯的不會被公開。','小陪：老師畫的你這邊同步看得到。我在旁邊記，不插嘴。','小陪：直接寫在板子上，或拍紙本。只有林老師看得到。','小陪：你在 A 組。分組看的是這週卡在哪，不是程度。','小陪：他只會按「聽懂了」或「再講一次」。','小陪：一句就好。這句話會留在你的路線上。'];
let sctx=null,sdraw=false;
function sBlock(k){$$('#strack button').forEach((b,i)=>{b.classList.toggle('on',i===k);b.classList.toggle('done',i<k)});$$('.sb-in').forEach(v=>v.classList.toggle('on',v.dataset.v===SB[k][0]));$('#snow').innerHTML='現在：<b>'+SB[k][1]+'</b> · 這段還有 '+SLEFT[k]+' 分鐘';$('#clsCoach').textContent=SCO[k];
 const pv=$$('#svg5 .sv');pv.forEach(v=>v.classList.remove('dim'));if(k===3)[0,1,3].forEach(i=>pv[i].classList.add('dim'));if(k===4)[1,2,3,4].forEach(i=>pv[i].classList.add('dim'));
 if(k===1){const n=$('#nl');n.classList.remove('play');later(()=>n.classList.add('play'),1400)}
 if(k===2)later(padInit,80)}
function padInit(){const c=$('#spad');c.width=c.offsetWidth*2;c.height=c.offsetHeight*2;sctx=c.getContext('2d');sctx.scale(2,2);sctx.lineWidth=3;sctx.lineCap='round';sctx.strokeStyle='#1B2530'}
function ppos(e){const c=$('#spad'),r=c.getBoundingClientRect(),k=c.offsetWidth/r.width;return [(e.clientX-r.left)*k,(e.clientY-r.top)*k]}
$('#spad').addEventListener('pointerdown',e=>{if(!sctx)padInit();sdraw=true;const q=ppos(e);sctx.beginPath();sctx.moveTo(q[0],q[1])});
$('#spad').addEventListener('pointermove',e=>{if(!sdraw)return;const q=ppos(e);sctx.lineTo(q[0],q[1]);sctx.stroke()});
addEventListener('pointerup',()=>sdraw=false);
$('#sClear').onclick=()=>{if(sctx)sctx.clearRect(0,0,9999,9999)};
$('#snap').onclick=function(){this.textContent='已拍照';};
$('#sSend').onclick=function(){this.textContent='已交給林老師';this.disabled=true;$('#clsCoach').textContent='小陪：收到。你這次有把方向反過來。'};
$('#strack').onclick=e=>{const b=e.target.closest('[data-b]');if(b)sBlock(+b.dataset.b)};
single($$('#spoll button'),()=>{const w=[67,33,0];$$('#spoll button').forEach((b,i)=>{if(!b.querySelector('u'))b.insertAdjacentHTML('beforeend','<u></u>');later(()=>b.querySelector('u').style.width=w[i]+'%',100)});$('#sres').textContent='6 人裡 4 人選 −2 × 1。等一下就從這題開始。'});
['cMic','cCam'].forEach(id=>$('#'+id).onclick=function(){this.classList.toggle('off')});
$('#cHand').onclick=function(){const on=this.classList.toggle('on');$('#clsCoach').textContent=on?'林老師看到你舉手了，下一個就是你。':'小陪：手放下了。'};
$('#cHelp').onclick=function(){const on=this.classList.toggle('on');$('#clsCoach').textContent=on?'只有林老師知道，同學看不到。她會私下過來。':'小陪：好，需要再按。'};
$('#pairBtn').onclick=function(){let n=3;this.disabled=true;this.textContent='正在講⋯ '+n;const t=every(()=>{n--;if(n>0)this.textContent='正在講⋯ '+n;else{clearInterval(t);this.textContent='講完了';$('#pairRes').textContent='小安按了「我聽懂了」'}},800)};
$('#exitRec').onclick=function(){this.classList.add('on');type($('#exitTx'),'乘負數整條數線會翻過去，所以大小反過來。',55,()=>{this.classList.remove('on');$('#exitTx').style.color='var(--pine-ink)'})};
// availability
let whBusy=false;function whUpd(){const n=$$('#whgrid .c.on').length;enable($('#whGo'),n>=2);$('#whCoach').style.display=n?'grid':'none';$('#whTx').textContent=n<2?'再點一格，我比較好找人。':'你選的時段裡，週三 19:00 有 5 個人跟你卡在同一步。時間之後隨時能改。'}
$('#whgrid').onclick=e=>{const d=e.target.closest('.d');if(d){const cs=$$('#whgrid .c').filter(c=>c.dataset.k.startsWith(d.dataset.d+'-')&&!c.classList.contains('busy'));const all=cs.every(c=>c.classList.contains('on'));cs.forEach(c=>c.classList.toggle('on',!all));return whUpd()}
 const c=e.target.closest('.c');if(!c)return;if(whBusy){c.classList.remove('on');c.classList.toggle('busy')}else if(!c.classList.contains('busy'))c.classList.toggle('on');whUpd()};
$('#whBusy [data-busy]').onclick=function(){whBusy=!whBusy;this.classList.toggle('sel',whBusy);this.textContent=whBusy?'點格子標成「有事」· 再按一次結束':'標記固定有事的時間'};
// family
single($$('#rx button'),b=>{const e=$('#rxEcho');e.style.display='grid';e.textContent=b.textContent;later(()=>{e.insertAdjacentHTML('afterend','<span class="day" style="animation:scrIn .4s">小睿的路線上會出現你的回應</span>')},600)});
// retest
$$('#reOpts .opt').forEach(o=>o.onclick=()=>{$$('#reOpts .opt').forEach(x=>x.classList.remove('right','wrong'));
  if(o.hasAttribute('data-right')){o.classList.add('right');$('#reDone').style.display='grid';enable($('#reGo'),true);burst();const sc=$('.scr[data-id=retest] .sc');later(()=>sc.scrollTo({top:sc.scrollHeight,behavior:'smooth'}),80)}
  else o.classList.add('wrong')});
function countUp(root){$$('[data-count]',root).forEach(el=>{const n=+el.dataset.count;let k=0;const t=every(()=>{k++;el.textContent=Math.min(n,Math.round(n*k/14));if(k>=14)clearInterval(t)},40)})}
function jGo(){const r=$('.jring');r.classList.remove('go');$$('.jn').forEach(n=>n.classList.remove('in'));later(()=>r.classList.add('go'),100);countUp($('#stJourney'));$$('.jn').forEach((n,k)=>later(()=>n.classList.add('in'),200+k*160))}
document.addEventListener('click',e=>{const b=e.target.closest('[data-jp]');if(!b)return;b.classList.add('on');b.lastChild.textContent='播放中⋯「整條數線翻過去」';setTimeout(()=>{b.classList.remove('on');b.lastChild.textContent='聽我當時怎麼講'},2200)});
// route
// ops

/* ---------- on-enter resets ---------- */
const ENTER={
 goal(){if(location.search.includes('gm'))later(()=>{$$('#goalChips button')[0].click();const sc=$('.scr.on .sc');if(sc)sc.scrollTop=150},60)},
 diag(){qMode('qPick')},
 checkin(){$$('#moodChips button').forEach(x=>x.classList.remove('sel'));$('#moodWhy').style.display='none';$('#mOrb').style.background='';$('#mName').textContent='還沒記';$('#mName').style.color='';$('#mLine').textContent='點下面一個，記下現在的心情。只有你看得到。';pl=['say','rev'];apDraw();$('#srcPanel').classList.remove('on');$$('#srcCards button').forEach(x=>x.classList.remove('sel'));$('#gForm').classList.remove('on');$$('#stSeg button')[location.search.includes('sw')?1:location.search.includes('sj')?2:0].click();$('#apOk').textContent='照這樣'},
 plus(){const b=$('#askPlus');b.disabled=false;b.textContent='傳給媽媽看看'},
 invite(){const r=$('#r8');r.classList.remove('show');$$('#r8>div').forEach((x,k)=>x.style.transitionDelay=(k*70)+'ms');later(()=>r.classList.add('show'),150)},
 teacher(){$('#tTx').textContent='按播放，聽林老師怎麼帶課。'},
 ask(){askReset();if(location.search.includes('aq')){later(askShot,60);later(()=>{const b=document.querySelector('.gqo [data-o="0"]');if(b)b.click()},2600);later(()=>{const b=document.querySelector('.gq .gqo:last-of-type [data-o="2"]');if(b)b.click()},4200)}},
 parentpay(){$('#paySheet').classList.remove('show');$('#payBtn').textContent='用 LINE Pay 付款'},
 lock(){if(location.search.includes('lv'))later(()=>{$('#lvChip').click();if(location.search.includes('lvd'))later(()=>$('#lvGo').click(),500)},80)},
 home(){if(location.search.includes('lvh'))later(()=>lvOpen('923','home'),80);if(window.__mood){const m=window.__mood.dataset.m;$('#homeMood').textContent=window.__moodName||'平靜';$('#homeCoach').textContent=m==='tired'||m==='upset'?'今天只留一件事：說給我聽 5 分鐘。其他我挪到週末了。':'你的小隊成班了。昨晚睡得少，今天我只排兩件事。';const r=$$('.scr[data-id=home] .row')[0];if(r)r.style.display=(m==='tired'||m==='upset')?'none':''}later(()=>{$('#squadProg').style.width='50%';$('#squadTxt').textContent='目前 3 / 6 · 小晴剛剛點亮一個'},1400)},
 practice(){$('#hintBox').classList.remove('show');$('#hintN').textContent='0';hBtns.forEach((b,k)=>{b.classList.remove('on');b.disabled=k>0});$$('#pracOpts .opt').forEach(x=>x.classList.remove('right','wrong'));enable($('#pracGo'),false)},
 say(){recOn=false;$('#recBtn').classList.remove('on');$('#sayDuo').classList.remove('talk');$$('#checks .ck').forEach(c=>c.classList.remove('ok','later'));$('#sayTx').textContent='⋯';$('#sayTx').style.color='var(--faint)';$('#sayShare').style.display='none';$('#recTip').textContent='按一下開始，再按一下結束';
   $('#sayQ').textContent='為什麼兩邊除以負數，不等號要反過來？用你自己的話講，30 秒就好。';const s=$('#shareSquad');s.disabled=false;s.textContent='講給小安聽'},
 class(){sctx=null;sBlock(+((location.search.match(/sb=(d)/)||[])[1]||1));$('#pairBtn').disabled=false;$('#pairBtn').textContent='開始講';$('#pairRes').textContent='';const pv=$$('#svg5 .sv');let t=0;every(()=>{pv.forEach(v=>v.classList.remove('talk'));pv[[1,3,0][t++%3]].classList.add('talk')},1800)},
 when(){whBusy=false;$$('#whgrid .c').forEach(c=>c.classList.remove('on','busy'));$$('#whBusy button').forEach(b=>b.classList.remove('sel'));enable($('#whGo'),false);$('#whCoach').style.display='none'},
 finish(){$('#qTx').textContent='林老師上課前會看到，不會顯示你的名字';$('#qTx').classList.remove('ok');const r=$('#ring');r.classList.remove('go');$('#ringN').textContent='0';const av=$$('#finAvs .av');av.forEach(a=>a.classList.remove('done'));
   later(()=>r.classList.add('go'),300);av.forEach((a,k)=>later(()=>{a.classList.add('done');$('#ringN').textContent=k+1;if(k===5)burst()},450+k*260))},
 retest(){$$('#reOpts .opt').forEach(x=>x.classList.remove('right','wrong'));$('#reDone').style.display='none';enable($('#reGo'),false)}
};

const h=location.hash.slice(1);go(Math.max(0,STEPS.findIndex(s=>s.id===h)));
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);
})();
