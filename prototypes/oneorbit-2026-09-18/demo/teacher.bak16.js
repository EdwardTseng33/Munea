(function(){
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const BIZ=['接班','備課','上課','紀錄','成長','收入'];
const ROLE={Line:'林老師的手機 · LINE',Phone:'林老師的手機 · LINE 內開啟的網頁',Web:'林老師的電腦／平板 · 網頁'};
const STEPS=[
 {g:'接班',id:'notify',dev:'Line',biz:0,t:'LINE 通知：有一隊很適合你',why:'老師不用裝新東西。小陪湊好一隊，只問最適合的那一位，保留 3 小時。不做搶單：手快不等於適合。',ev:['台灣老師幾乎都看 LINE，回應比 App 推播快','專用官方帳號加勿擾時段，不跟私人訊息混在一起','沒回應自動轉下一位，不記缺點'],dr:['穩定課源','被尊重的時間']},
 {g:'接班',id:'offer',dev:'Phone',biz:0,t:'接班卡：在 LINE 裡直接打開',why:'點 LINE 訊息的「看這一隊」，會在 LINE 裡面直接打開 Tandelo 的網頁（上方是 LINE 的瀏覽列），用 LINE 帳號自動登入，不用另外裝 App、不用輸入密碼。一張卡講完：教什麼、幾個人、什麼時段、賺多少、為什麼是你。按「接這一隊」試試。',ev:['收入寫在最上面，不讓老師自己算','適合度與理由透明，老師才信任 AI 分課','人數掉到 4 人鐘點費不變：風險由平台扛'],dr:['收入確定','決定權在老師']},
 {g:'接班',id:'taken',dev:'Phone',biz:0,t:'成班：剩下的不用你做',why:'不用建群、排時間、收錢、出講義。這是老師願意留在平台、不把學生帶走的主要理由。',ev:['傳統家教老師三成時間花在找學生、喬時間、催款'],dr:['省掉行政']},
 {g:'每天',id:'today',dev:'Web',biz:1,t:'今天：先看下一堂，再處理三件事',why:'最上面是下一堂的倒數與一顆進教室，底下一條今天的時間軸；接著三張「等你決定」的卡，每張一句話、兩個按鈕；最後一條小陪的建議。按按看卡片上的按鈕。',ev:['老師打開第一眼要知道：下一堂什麼時候、要先處理什麼','每件事只給兩個選項，按完卡片就淡掉','收入、等級、通過率縮成右上三個小數字，點了才進去看'],dr:['掌控感','省時間']},
 {g:'每天',id:'opps',dev:'Web',biz:0,t:'開課機會：學生先湊隊，再找老師',why:'每一筆機會背後就是一支「草擬的隊」：學生診斷後進等候池 → 小陪依卡點、年級、程度、共同空檔湊出 3–6 人 → 問最適合的老師 → 老師接了才送邀請給學生 → 家長付款滿 4 人成班（不足改小組）。點任一列看這隊怎麼湊出來的。',ev:['老師接的是一支已經湊好的隊，不是空的時段','接班前只看得到卡點，名字成班後才顯示','每列下方的小進度條：綠＝已完成、紅＝現在卡在這一步','學生端需要先填「我什麼時候可以上」，才進得了等候池'],dr:['收入確定','省掉招生']},
 {g:'每天',id:'students',dev:'Web',biz:1,t:'我的學生：依團切換，一個孩子一份紀錄',why:'老師同時帶好幾個團。上方切換「需要注意」（跨所有團）、「全部」或單一個團；右上可以看每個團的概況。同一個孩子在兩個團（例如小晴也在一對一）只會有一份紀錄。點點看。',ev:['預設打開「需要注意」：老師最常問的是今天該先顧誰，不是誰在哪一團','代課的團只看得到當週資料，下課後自動收回','學生的目標與身心狀態旗標一起呈現，老師才知道今天該推還是該放','只給旗標不給原始健康數據'],dr:['教得更準']},
 {g:'每天',id:'calendar',dev:'Web',biz:1,t:'班表與代課：請假三步完成',why:'「我能上課的時間」一整週一眼看完、用滑的塗。「我的課」點週三 19:00 的不等式 B 隊試試請假：1 原因與處理方式（代課或全隊改期）→ 2 小陪排好三位代課人選（擅長卡點、教過這些學生、時段有空）→ 3 自動交接、通知家長、說明對你的影響。',ev:['48 小時以上請假不扣可靠度；48 小時內算臨時請假；生病附就醫證明也不扣','代課老師只看得到這堂需要的資料，下課後權限自動收回','家長可以選改期補上，不扣堂數','同一隊 8 週內代課超過 2 次，小陪會建議換正式老師，保住隊的連續性','開課前 2 小時內或上課中斷線：小陪先帶「自己試試」，同時一次問三位待命老師'],dr:['彈性','不被懲罰的安心']},
 {g:'上課',id:'brief',dev:'Web',biz:1,t:'上課前：一個大大的進教室',why:'最上面是下一堂課的倒數、誰已經在等候室、設備檢查，和最顯眼的「進教室」。下面才是六個人各卡在哪、建議怎麼分組、開場怎麼問。不備課、不出講義。',ev:['建議可以不採用；老師永遠有最後決定權'],dr:['專業被放大']},
 {g:'上課',id:'room',dev:'Web',biz:2,t:'教室：50 分鐘跟著教案軌走',why:'上方的教案軌把 50 分鐘分成六段：暖身 5、你們的錯 10、自己試試 10、補最後一哩 10、互相講 10、我搞懂的 5。每一段自動換上對應的教材與畫面（投票、白板、作答牆、分組、互講、出場卡），紅線是現在時間；超時會提醒怎麼補回來。點任一段或按「下一段」走一次，也可以在白板上直接畫。',ev:['教材不是一疊投影片，是綁在時間軸上的六種活動：老師只要按「下一段」','每一段的時間可以拖拉調整；AI 只建議不硬切，下課時間由老師掌握','數學課的主角是題目與推導，不是人臉：白板佔七成畫面','學生的作答只有老師看得到；要全班討論時匿名投到白板','小陪提醒「她不會舉手但需要你」：AI 當老師的第二雙眼睛','下方工具列放老師上課最常用的五個動作，下課按鈕最醒目'],dr:['教得更準','真人的價值']},
 {g:'小陪整理',id:'recap',dev:'Web',biz:3,t:'課後整理：AI 寫好筆記、逐字稿、下一堂',why:'按下課後，小陪依逐字稿、白板和作答整理四樣東西：教學筆記（含關鍵時刻與白板快照）、逐字稿（可搜尋、標出好問題與沉默）、每個學生的狀態、下一堂的建議進度。四個分頁點點看，逐字稿可以搜尋「負號」。',ev:['老師下課後不用寫任何東西；AI 漏掉的，在筆記最下面打一行或按麥克風講一句就好','逐字稿只存文字 30 天、錄音不保留、只有老師看得到全文；上課錄音需家長事先同意','「小晴沉默 17 分鐘」這類訊號，老師上課當下看不到，課後才看得到','下一堂的建議直接放進課前一頁，形成迴圈'],dr:['省掉行政','教得更準','專業被放大']},
 {g:'小陪整理',id:'records',dev:'Web',biz:3,t:'學生週報：一週一份，看目標與狀態',why:'不再每堂課送一次。每週日小陪替每個學生整理一份：目標進度、這週學會了什麼、觀察、狀態、下週建議，和一句給家人「這週可以問他」的話。老師一次看完、改一句或直接確認，約 3 分鐘。上方三個分頁把 AI 替老師準備的東西收在同一處：學生週報、給我的建議、每堂課後整理。',ev:['每堂課後的整理自動存檔、更新學生路線，老師不用按任何東西','家長版只含孩子同意分享的；「狀態」那格只有老師看得到','想改語氣就點「請小陪改」，用說的或打字交代'],dr:['省掉行政','家長信任','教得更準']},
 {g:'小陪整理',id:'assist',dev:'Web',biz:4,t:'教學助理：AI 的教學與教材建議',why:'建議來自老師自己的數據，不是通用的教學法文章。教材可以一鍵加進下一堂；AI 出的題目要老師看過才會到學生面前。按幾個按鈕試試。',ev:['建議分三種語氣：有效、試試、留意，不打分數、不排名','教材不綁出版社版本；老師上傳的教材被採用有分潤','旁聽其他老師，是老師在平台上成長的路'],dr:['專業成長','專業被放大']},
 {g:'備課',id:'materials',dev:'Web',biz:1,t:'教材：掛在卡點上，依六段取用',why:'框架是三層：卡點地圖（科目 › 單元 › 卡點）是骨架；教材掛在卡點上，並標好適合六段裡的哪一段；教案＝8 週路徑 × 每堂六段，上課時教案軌自動取用。三個分頁：教材庫（篩選、編輯、複製、刪除、審核 AI 產生的）、8 週教案（空格請小陪補）、上傳（小陪拆題、標卡點、分段、檢查）。都點點看。',ev:['教材不綁出版社版本：同一個卡點，不管學生用哪一版課本都能用','AI 產生的一律標示、老師審過才進教案','上傳時自動檢查答案、學生個資與翻拍市售書的版權問題','老師分享教材被採用有分潤，也算進等級的專業貢獻分'],dr:['省掉備課','專業被放大']},
 {g:'評鑑',id:'tier',dev:'Web',biz:4,t:'等級與評價：一套看得懂的演算法',why:'等級不看總堂數，而是每月 1 日依最近 180 天的六類指標重算：學生學會了嗎 35、留得住嗎 25（續走、換師率、試上轉付費）、評價 15、可靠度 15（臨時請假、遲到缺課、當天確認、家長回覆）、投入度 10（每月安排堂數、接班回應）、貢獻最多加 5。連續兩個月達標才升降。切到「規則」看完整算法與公平校正。',ev:['換師率只算學生主動要求換掉老師；AI 因卡點不同建議轉隊不算','通過率跟同卡點同程度比：帶程度較弱的學生不吃虧','樣本少時分數往平台平均拉近，避免新老師被一兩個評價決定','每月超過 40 堂不再加分：不鼓勵老師過勞'],dr:['公平','成長','收入確定']},
 {g:'評鑑',id:'impact',dev:'Web',biz:4,t:'我的成效：學生學會了嗎',why:'評鑑看三件事：學生隔三天還會不會（主要，綁獎金）、學生與家長每 8 週兩題的匿名回饋、同儕觀課。只有老師自己看得到回饋，不公開星等、不排名。',ev:['公開星星評分會讓老師討好學生、不敢要求','學生回饋只問兩題、滿 5 人才顯示，保護學生','成效決定 AI 推什麼課給你，規則寫明；回饋只用來幫老師看自己','連兩季明顯低於平台、或出現安全疑慮，才會有真人約談'],dr:['公平','專業認同','成長']},
 {g:'收入',id:'income',dev:'Web',biz:5,t:'收入與獎金：規則全部寫明',why:'每堂課上完隔天就進「可出帳」。獎金五種，全部綁「學生有沒有學會、願不願意續走」與對平台的貢獻，不綁招生。',ev:['老師最大的不安是「不知道下個月有多少」','獎金規則公開，老師知道怎麼做會賺更多','不綁家長評分：避免老師討好而不敢要求'],dr:['收入確定','透明','公平']},
 {g:'收入',id:'payout',dev:'Web',biz:5,t:'出帳：預設每月自動，隨時可手動',why:'選速度、按確認就好。扣繳與補充保費自動算好，入帳 LINE 通知，報稅資料自動彙整。預設每月 1 日自動出帳，老師完全不用管；想改成每半個月或每週也可以。按「確認出帳」走一次。',ev:['標準 7 天免手續費；快速 3 天收少量手續費，高等級老師免費，當成一種福利','第一次綁帳戶線上驗證約 3 分鐘；換帳戶要重新驗證，防盜領','稅務身分（承攬或僱傭）與扣繳比例要請會計師確認後定案'],dr:['收入確定','省掉行政']},
 {g:'設定',id:'profile',dev:'Web',biz:0,t:'個人資料：直接在名片上改',why:'上方大卡就是家長看到的樣子，點名字、介紹或標籤直接改；點頭像換照片、點紅色語音鈕重錄。下方三格是能教什麼、擅長什麼、資格與公開設定。',ev:['所見即所得：不再左邊表單、右邊預覽','開新科目要試教一堂才解鎖','全名、聯絡方式、任教學校一律不公開'],dr:['專業認同','掌控感']}
];
const rail=$('#rail'),ctx=$('#ctx'),stage=$('#stage');let cur=0,timers=[];
const later=(f,ms)=>{const t=setTimeout(f,ms);timers.push(t);return t},every=(f,ms)=>{const t=setInterval(f,ms);timers.push(t);return t};
function clearTimers(){timers.forEach(t=>{clearTimeout(t);clearInterval(t)});timers=[]}
(function(){let g=null,box;STEPS.forEach((s,i)=>{if(s.g!==g){g=s.g;box=document.createElement('div');box.className='grp';box.innerHTML='<h5>'+g+'</h5>';rail.appendChild(box)}
  const b=document.createElement('button');b.innerHTML='<span class="n">'+(i+1)+'</span><span>'+s.t.split('：')[0]+'</span>';b.onclick=()=>go(i);box.appendChild(b);s.btn=b})})();
function renderCtx(s,i){ctx.innerHTML='<div><div class="k">第 '+(i+1)+' 步 / '+STEPS.length+' · '+s.g+'</div><h2>'+s.t+'</h2></div><p>'+s.why+'</p>'+
 '<div class="sec"><h6>老師的工作流程走到哪</h6><div class="biz">'+BIZ.map((_,k)=>'<i class="'+(k<s.biz?'on':k===s.biz?'now':'')+'"></i>').join('')+'</div><div class="bizl">'+BIZ.map(b=>'<span>'+b+'</span>').join('')+'</div></div>'+
 '<div class="sec"><h6>為什麼這樣設計</h6><ul>'+s.ev.map(e=>'<li>'+e+'</li>').join('')+'</ul></div>'+
 '<div class="sec"><h6>老師為什麼想留下來</h6><div class="chips">'+s.dr.map((d,k)=>'<span class="chip'+(k%3===1?' c':k%3===2?' h':'')+'">'+d+'</span>').join('')+'</div></div>'}
function fit(){const s=STEPS[cur],dev=$('#dev'+s.dev),W=dev.offsetWidth,H=dev.offsetHeight,aw=stage.clientWidth,ah=Math.max(420,innerHeight-150),k=Math.min(1,aw/W,ah/H);
 dev.style.transform='scale('+k+')';dev.style.margin='0 '+(-(W*(1-k))/2)+'px '+(-(H*(1-k)))+'px';stage.style.minHeight=(H*k)+'px'}
function go(i){if(typeof i==='string')i=STEPS.findIndex(s=>s.id===i);if(i<0||i>=STEPS.length)return;clearTimers();cur=i;const s=STEPS[i];
 ['Line','Phone','Web'].forEach(d=>$('#dev'+d).style.display=d===s.dev?'':'none');
 $$('.scr').forEach(x=>x.classList.toggle('on',x.dataset.id===s.id));
 STEPS.forEach((x,k)=>{x.btn.classList.toggle('on',k===i);x.btn.classList.toggle('done',k<i)});
 rail.scrollTop=s.btn.offsetTop-rail.clientHeight/2;rail.scrollLeft=s.btn.offsetLeft-rail.clientWidth/2;
 $('#roleT').textContent=ROLE[s.dev];$('#prev').disabled=i===0;$('#next').disabled=i===STEPS.length-1;
 $('.main').classList.toggle('wide',s.dev==='Web');
 const map={brief:'brief',room:'brief',recap:'records',records:'records',assist:'records',impact:'tier',payout:'income'};$$('#side button').forEach(b=>b.classList.toggle('on',b.dataset.go===(map[s.id]||s.id)));
 renderCtx(s,i);fit();(ENTER[s.id]||(()=>{}))();if($('#aiChat').classList.contains('on')){$('#acCtx').textContent='我看得到你現在在「'+(PAGE[s.id]||'這一頁')+'」';$('#acS').innerHTML=(SUG[s.id]||SUG._).map(x=>'<button>'+x+'</button>').join('')}$('#aiFab').style.display=s.id==='room'?'none':''}
$('#prev').onclick=()=>go(cur-1);$('#next').onclick=()=>go(cur+1);
document.addEventListener('click',e=>{const n=e.target.closest('[data-next]');if(n&&!n.disabled)return go(cur+1);const g=e.target.closest('[data-go]');if(g&&!g.disabled)return go(g.dataset.go)});
document.addEventListener('keydown',e=>{if(e.key==='ArrowRight')go(cur+1);if(e.key==='ArrowLeft')go(cur-1)});
addEventListener('resize',fit);
function burst(){const b=$('#burst'),cols=['#F26B54','#0E5F52','#F4C24D','#DCEFE8','#F9D3C9'];b.classList.remove('go');b.innerHTML='';for(let k=0;k<26;k++){const d=document.createElement('i'),a=Math.random()*6.28,r=90+Math.random()*170;d.style.cssText='background:'+cols[k%5]+';--x:'+Math.cos(a)*r+'px;--y:'+(Math.sin(a)*r-60)+'px';b.appendChild(d)}void b.offsetWidth;b.classList.add('go')}
function type(el,text,ms,done){el.textContent='';el.style.color='';el.classList.add('typing');let k=0;const t=every(()=>{el.textContent=text.slice(0,++k);if(k>=text.length){clearInterval(t);el.classList.remove('typing');done&&done()}},ms)}

// offer
$('#takeBtn').onclick=()=>{go('taken');burst()};
// today
$$('[data-done]').forEach(b=>b.onclick=()=>{const d=b.closest('.dec');if(d){d.classList.add('done');d.querySelectorAll('button').forEach(x=>x.disabled=true);b.textContent='✓ '+b.textContent;const n=$('#opsN');n.textContent=Math.max(0,+n.textContent-1);return}b.disabled=true;b.textContent='已處理';b.closest('.li').style.opacity=.5});
// opps list
const OP=[
 {s:'數學',ty:'小隊',t:'乘除負數 · 國二',z:6,g:6,w:'週三 19:00',n:11,days:4,pay:8800,fit:92,why:'概念型卡點是你的強項；時段在你的可上課時間內'},
 {s:'數學',ty:'補強',t:'分數係數 · 國二',z:5,g:5,w:'週四 19:00',n:7,days:2,pay:600,fit:88,why:'其中 5 位是你現在的學生'},
 {s:'數學',ty:'小隊',t:'一次函數圖形 · 國二',z:6,g:5,w:'週二 20:00',n:9,days:6,pay:8800,fit:81,why:'你帶過 3 隊函數，通過率 76%'},
 {s:'理化',ty:'小隊',t:'浮力 · 國二',z:6,g:6,w:'週四 18:00',n:6,days:5,pay:8800,fit:74,why:'你有理化授課資格；這一科你還沒有成效紀錄'},
 {s:'數學',ty:'小隊',t:'應用題：文字變式子 · 國二',z:6,g:6,w:'週六 10:00',n:12,days:7,pay:8800,fit:61,why:'讀題型不是你最強的，接了會附帶法建議'},
 {s:'理化',ty:'一對一',t:'莫耳數計算 · 國三',z:1,g:1,w:'時間可談',n:1,days:3,pay:3200,fit:70,why:'家長指定要一對一 4 堂'},
 {s:'數學',ty:'小隊',t:'二元一次聯立 · 國二',z:3,g:3,w:'週一 20:00',n:3,days:3,pay:5600,fit:79,why:'三個好朋友一起報，指定要小組'},
 {s:'數學',ty:'一對一',t:'因式分解 · 國三',z:2,g:2,w:'週五 18:00',n:2,days:1,pay:4800,fit:77,why:'兄弟一起上；哥哥帶過函數隊'},
 {s:'英文',ty:'小隊',t:'關係代名詞 · 國三',z:6,g:6,w:'週一 19:00',n:8,days:3,pay:8800,fit:0,lock:'你沒有開英文科'},
 {s:'國文',ty:'小隊',t:'文言文閱讀 · 國三',z:6,g:6,w:'週五 19:00',n:10,days:8,pay:8800,fit:0,lock:'你沒有開國文科'},
 {s:'技能',ty:'小隊',t:'讀書計畫與時間管理 · 國中',z:6,g:6,w:'週日 20:00',n:14,days:9,pay:6400,fit:0,lock:'技能課需要另外的帶領資格'}];
let oF='all',oT='all';
function oRender(){const so=$('#oSort').value;const arr=OP.filter(o=>(oF==='all'||o.s===oF)&&(oT==='all'||(oT==='1'&&o.z===1)||(oT==='2'&&o.z>1&&o.z<=3)||(oT==='3'&&o.z>=4))).sort((a,b)=>so==='pay'?b.pay-a.pay:so==='wait'?b.days-a.days:b.fit-a.fit);
 $('#oList').innerHTML=arr.map(o=>'<div class="orow'+(o.lock?' lock':'')+(o.took?' took':'')+'"><div class="sub '+o.s+'">'+o.s+'</div><div class="ratio r'+(o.z===1?1:o.z<=3?2:3)+'"><b>1<i>對</i>'+o.z+'</b><span>'+Array.from({length:o.z},(_,k)=>'<u class="'+(k<o.g?'on':'')+'"></u>').join('')+'</span><small>'+(o.g>=o.z?'已湊滿':'已有 '+o.g+' 人')+'</small></div><div><b>'+o.t+'<span class="fitb">適合 '+o.fit+'</span></b><small>'+(o.lock||o.why)+'</small></div><div class="wait"><span>'+o.w+' · '+(o.ty==='補強'?'25 分補強':o.z===1?'一對一 4 堂':o.z<=3?'8 週小組':'8 週小隊')+'</span><div class="prog"><i style="width:'+Math.min(100,o.n*8)+'%;background:'+(o.days>6?'var(--coral)':'var(--pine)')+'"></i></div><small>'+o.n+' 人在等 · 最久 '+o.days+' 天</small><div class="ostage"><i class="on"></i><i class="on"></i><i class="'+(o.took?'on':'now')+'"></i><i></i><i></i>'+(o.took?'等學生確認':'等老師')+'</div></div><div class="n">'+o.pay.toLocaleString()+'<small> 元</small><em>每堂 '+Math.round(o.pay/(o.ty==='補強'?1:o.z===1?4:8)).toLocaleString()+'</em></div><div class="fit">'+(o.lock?'—':o.fit)+'<small><br>適合度</small></div>'+(o.lock?'<button class="mini o" data-apply>申請開這科</button>':'<button class="mini'+(o.fit<70?' o':'')+'" data-tk="'+OP.indexOf(o)+'"'+(o.took?' disabled':'')+'>'+(o.took?'已送出':o.fit<70?'我想試試':'我要開')+'</button>')+'</div>').join('')||'<p class="body">這個分類目前沒有機會。</p>'}
$('#oList').onclick=e=>{const row=e.target.closest('.orow');if(row&&!e.target.closest('button')&&!row.classList.contains('lock')){$('#odT').textContent=row.querySelector('b').textContent+' · '+row.querySelector('.wait span').textContent;$('#oDraw').classList.add('on');return}const b=e.target.closest('[data-tk]');if(b){OP[+b.dataset.tk].took=true;oRender()}const a=e.target.closest('[data-apply]');if(a){a.textContent='已申請 · 3 天內回覆';a.disabled=true}};
$$('#oTabs [data-f]').forEach(b=>b.onclick=()=>{oF=b.dataset.f;$$('#oTabs [data-f]').forEach(x=>x.classList.toggle('on',x===b));oRender()});
$$('#oTabs [data-t]').forEach(b=>b.onclick=()=>{oT=b.dataset.t;$$('#oTabs [data-t]').forEach(x=>x.classList.toggle('on',x===b));oRender()});
$('#oSort').onchange=oRender;oRender();
$('#odX').onclick=()=>$('#oDraw').classList.remove('on');
$('#odTake').onclick=function(){const f=$$('#odFlow .f5');f[2].className='f5 done';f[3].className='f5 now';f[3].querySelector('small').textContent='邀請已送出 · 3 / 6 人已付款';this.textContent='已接 · 等學生確認';this.disabled=true};
// availability
const HRS=[];for(let h=8;h<23;h++)HRS.push((h<10?'0':'')+h+':00');const DAYS=['一','二','三','四','五','六','日'],R=h=>h-8,BUSY=['0-'+R(19),'1-'+R(19),'2-'+R(19),'4-'+R(19),'5-'+R(10),'0-'+R(20),'2-'+R(20),'3-'+R(21)];
(function(){const g=$('#avgrid');let h='<span></span><span class="band" style="grid-column:span 4">早上</span><span class="band" style="grid-column:span 6">下午</span><span class="band" style="grid-column:span 4">晚上</span><span class="band late" style="grid-column:span 1">夜間</span><span></span>'+HRS.map((t,r)=>'<span class="hh'+(r>=R(22)?' late':'')+'">'+t.slice(0,2)+'</span>').join('');DAYS.forEach((dn,d)=>{h+='<span class="dd">'+dn+'</span>';HRS.forEach((_,r)=>{const lt=r>=R(22)?' late':'';const k=d+'-'+r;h+='<div class="c'+lt+(BUSY.includes(k)?' busy on':'')+'" data-k="'+k+'"></div>'})});g.innerHTML=h})();
let cap=8,paint=null;
function avEst(){const n=$$('#avgrid .c.on').length,per=Math.min(n,cap);$('#avEst').innerHTML=n?'約 NT$'+(per*4.3*1000/1000|0)+',000<small> / 月</small>':'—';const lt=$$('#avgrid .c.on.late').length;$('#avEstTx').textContent=n?'你開了 '+n+' 個時段、每週最多 '+cap+' 堂。依現在的需求，預估每週排得滿 '+per+' 堂。'+(lt?' 其中 '+lt+' 格在 22:00 後，只會推高中以上與技能課。':''):'先塗幾格你能上課的時間。'}
function setCell(c,v){if(c.classList.contains('busy'))return;c.classList.toggle('on',v)}
$('#avgrid').addEventListener('pointerdown',e=>{const c=e.target.closest('.c');if(!c||c.classList.contains('busy'))return;paint=!c.classList.contains('on');setCell(c,paint);avEst()});
$('#avgrid').addEventListener('pointerover',e=>{if(paint===null)return;const c=e.target.closest('.c');if(c){setCell(c,paint);avEst()}});
addEventListener('pointerup',()=>paint=null);
$$('[data-pre]').forEach(b=>b.onclick=()=>{$$('#avgrid .c').forEach(c=>{const [d,r]=c.dataset.k.split('-').map(Number);if(b.dataset.pre==='clear')setCell(c,false);if(b.dataset.pre==='eve'&&d<5&&(r===R(19)||r===R(20)))setCell(c,true);if(b.dataset.pre==='sat'&&d===5&&r>=R(9)&&r<=R(11))setCell(c,true);if(b.dataset.pre==='late'&&d<5&&r>=R(21))setCell(c,true)});avEst()});
$('#capM').onclick=()=>{cap=Math.max(1,cap-1);$('#capN').textContent=cap;avEst()};$('#capP').onclick=()=>{cap=Math.min(20,cap+1);$('#capN').textContent=cap;avEst()};
$$('#calSeg button').forEach(b=>b.onclick=()=>{$$('#calSeg button').forEach(x=>x.classList.toggle('on',x===b));const av=b.dataset.v==='avail';$('#calMine').style.display=av?'none':'grid';$('#calAvail').style.display=av?'grid':'none';$('#calSub').textContent=av?'塗一次就好。小陪只會在這些時間裡推課給你。':'本週 8 堂 · 點一堂課可以請假，小陪會幫你找代課';avEst()});
// students — grouped by squad
const SQ=[
 {id:'ineq',n:'不等式隊',k:'數學',wk:1,next:'週三 19:00',pass:'—',note:'第 1 週，還沒有再測資料'},
 {id:'ineqB',n:'不等式 B 隊',k:'數學',wk:2,next:'週三 19:00',pass:'80%',note:'進度正常'},
 {id:'fn',n:'函數隊',k:'數學',wk:6,next:'週二 19:00',pass:'83%',note:'第 8 週後 5 人想續走'},
 {id:'fnB',n:'函數 B 隊',k:'數學',wk:3,next:'週五 19:00',pass:'67%',note:'2 人卡在斜率，建議本週分組'},
 {id:'geo',n:'幾何隊',k:'數學',wk:4,next:'週六 10:00',pass:'75%',note:'阿哲下週轉入'},
 {id:'phy',n:'浮力隊（代課）',k:'理化',wk:5,next:'週四 18:00',pass:'—',note:'代王老師一堂，只看得到當週資料'},
 {id:'one',n:'一對一',k:'數學',wk:0,next:'週一、三 20:00',pass:'—',note:'小恩、小晴各 25 分鐘'}];
const ST=[
 {n:'小睿',img:'s1',sq:['ineq'],flag:'睡少',fc:'h',why:'說不出為什麼',att:2,goal:'他的目標：段考數學 70 → 85 · 還有 18 天',ai:'<b>現在卡哪：</b>知道除以負數要變號，但說不出為什麼，題目一變形就錯。<br><b>上次什麼有效：</b>用數線看「整個翻過去」，他自己講出來了。<br><b>下次建議：</b>直接給分數係數，別再重複整數題。',say:11,hint:1.4,gold:3,tl:[['9/24','隔三天再測通過：兩邊乘除負數'],['9/23','上課講給小安聽，小安按「我聽懂了」'],['9/18','診斷：錯的題都是同一個原因']]},
 {n:'小晴',img:'s4',sq:['ineq','one'],flag:'心情偏低',fc:'',why:'方向還不穩 · 另有一對一',att:3,goal:'她的目標：會考數學 B++ · 每天最多 30 分鐘',ai:'<b>現在卡哪：</b>方向會反過來的觀念還沒穩，再測沒過一次。<br><b>上次什麼有效：</b>一對一、不在同學面前。<br><b>下次建議：</b>小隊課裡別點她；週一的一對一再補。',say:6,hint:2.3,gold:1,tl:[['9/22','一對一：數線練習，第二題自己做出來'],['9/21','再測沒過：方向反了'],['9/17','加入不等式隊與一對一']]},
 {n:'阿哲',img:'s5',sq:['ineq','geo'],flag:'轉隊中',fc:'g',why:'下週轉入你的幾何隊',att:1,goal:'他的目標：不要再怕分數',ai:'<b>現在卡哪：</b>不等式其實已經會了，真正卡的是幾何證明。<br><b>上次什麼有效：</b>先稱讚他的提問，他才敢繼續問。<br><b>下次建議：</b>他會留在你手上（幾何隊），這次換隊不用交接。',say:9,hint:1.1,gold:4,tl:[['9/23','提了全隊最好的問題'],['9/20','家長同意轉到幾何隊']]},
 {n:'小凱',img:'s3',sq:['fnB'],flag:'卡斜率',fc:'',why:'兩週都卡在斜率',att:2,goal:'他的目標：段考數學 60 → 75',ai:'<b>現在卡哪：</b>會畫圖，但算不出斜率的正負。<br><b>上次什麼有效：</b>用爬坡比喻。<br><b>下次建議：</b>和小妤一組，你帶 8 分鐘。',say:4,hint:2.6,gold:2,tl:[['9/19','再測沒過：斜率正負'],['9/12','再測沒過：斜率正負']]},
 {n:'小安',img:'s2',sq:['ineq'],flag:'',fc:'',why:'粗心型，會變號但算錯',att:0,goal:'她的目標：只想跟上就好',ai:'<b>現在卡哪：</b>觀念對，除法常算錯。<br><b>下次建議：</b>請她放慢、寫出每一步。',say:8,hint:0.9,gold:2,tl:[['9/23','聽小睿講，按「我聽懂了」']]},
 {n:'小宇',img:'s3',sq:['ineq','fn'],flag:'',fc:'',why:'已經會了，可以當小老師',att:0,goal:'他的目標：會考 A',ai:'<b>現在：</b>兩個團都領先。<br><b>下次建議：</b>請他當講的人；可問他要不要挑戰進階隊。',say:15,hint:0.3,gold:6,tl:[['9/23','當 B 組小老師']]},
 {n:'小恩',img:'s6',sq:['ineq','one'],flag:'',fc:'',why:'會背不會講 · 另有一對一',att:1,goal:'她的目標：段考數學 75 → 85',ai:'<b>現在卡哪：</b>背得出規則，換題就錯。<br><b>下次建議：</b>先讓她解釋一個錯的答案。',say:7,hint:1.8,gold:2,tl:[['9/21','一對一：分數係數示範到第二步']]},
 {n:'小妤',img:'s4',sq:['fnB'],flag:'',fc:'',why:'斜率快通了',att:0,goal:'她的目標：不要再怕數學',ai:'<b>下次建議：</b>跟小凱一組，讓她講給他聽。',say:5,hint:1.5,gold:2,tl:[['9/19','再測通過：斜率']]}];
let sqF='att',sv='list',curS=0;
function sqTabs(){const cnt=id=>id==='att'?ST.filter(s=>s.att>0).length:id==='all'?34:ST.filter(s=>s.sq.includes(id)).length;
 const tabs=[{id:'att',n:'需要注意'},{id:'all',n:'全部'}].concat(SQ);
 $('#sqTabs').innerHTML=tabs.map(t=>'<button data-q="'+t.id+'" class="'+(sqF===t.id?'on':'')+'">'+t.n+' <em>'+(t.id==='all'?34:t.id==='one'?2:t.id==='att'?cnt('att'):(t.id==='ineq'?6:t.id==='ineqB'?5:t.id==='fn'?6:t.id==='fnB'?6:t.id==='geo'?5:4))+'</em></button>').join('')}
function sqName(id){return (SQ.find(q=>q.id===id)||{}).n}
function sList(){let arr=sqF==='att'?ST.filter(s=>s.att>0).sort((a,b)=>b.att-a.att):sqF==='all'?ST:ST.filter(s=>s.sq.includes(sqF));
 const q=SQ.find(x=>x.id===sqF);
 $('#sqSum').innerHTML=q?'<b>'+q.n+'</b><span>'+(q.wk?'第 '+q.wk+' 週 · ':'')+'下堂 '+q.next+' · 隔三天通過 '+q.pass+'</span><small>'+q.note+'</small>':sqF==='att'?'<b>需要你注意的，跨所有團</b><span>依急迫度排序；每個人標出他在哪個團</span>':'<b>全部 34 位</b><span>這裡只列出 8 位示意</span>';
 $('#slist').innerHTML=arr.map(s=>{const k=ST.indexOf(s);return '<button class="srow'+(k===curS?' on':'')+'" data-s="'+k+'"><img class="ph" src="img/'+s.img+'.jpg" width="40" height="40" alt=""><div><b>'+s.n+'</b><small>'+(sqF===s.sq[0]&&s.sq.length===1?'':s.sq.map(sqName).join('・')+' · ')+s.why+'</small></div>'+(s.flag?'<span class="flag '+s.fc+'">'+s.flag+'</span>':'<span></span>')+'</button>'}).join('')||'<p class="body" style="font-size:13px;padding:8px">這個團目前沒有需要特別注意的人。</p>'}
function sDetail(k){curS=k;const d=ST[k];$('#sdName').textContent=d.n;$('#sdImg').src='img/'+d.img+'.jpg';$('#sdGoal').textContent=d.goal;$('#sdFlag').textContent=d.flag||'狀態正常';$('#sdFlag').className='flag '+(d.flag?d.fc:'g');$('#sdAi').innerHTML=d.ai;
 $('#sdSq').innerHTML=d.sq.map(id=>'<span class="chip">'+sqName(id)+'</span>').join('')+(d.sq.length>1?'<span class="chip h">同一個孩子在你 '+d.sq.length+' 個團，紀錄只有一份</span>':'');
 $('#sdSay').innerHTML=d.say+'<small> 次</small>';$('#sdHint').innerHTML=d.hint+'<small> 級</small>';$('#sdGold').innerHTML=d.gold+'<small> 點</small>';$('#sdTl').innerHTML=d.tl.map(t=>'<div><span>'+t[0]+'</span><div>'+t[1]+'</div></div>').join('');
 $$('#slist .srow').forEach(r=>r.classList.toggle('on',+r.dataset.s===k))}
function sqDetail(){const rows=SQ.map(q=>'<div class="sqrow" data-q="'+q.id+'"><div><b>'+q.n+'</b><small>'+q.k+(q.wk?' · 第 '+q.wk+' / 8 週':'')+' · 下堂 '+q.next+'</small></div><div class="prog"><i style="width:'+(q.wk/8*100)+'%"></i></div><span class="lat">'+q.pass+'</span><small>'+q.note+'</small></div>').join('');
 $('#sqDetail').innerHTML='<h6>我的 7 個團 · 點一個看名單</h6><div class="sqhead"><span>團</span><span>進度</span><span>隔三天通過</span><span>小陪的提醒</span></div>'+rows}
$('#sqTabs').onclick=e=>{const b=e.target.closest('[data-q]');if(!b)return;sqF=b.dataset.q;sqTabs();sList();if(sv==='squad')setView('list')};
$('#slist').onclick=e=>{const r=e.target.closest('.srow');if(r)sDetail(+r.dataset.s)};
function setView(v){sv=v;$$('#sView button').forEach(x=>x.classList.toggle('on',x.dataset.v===v));$('#sdetail').style.display=v==='list'?'grid':'none';$('#sqDetail').style.display=v==='squad'?'grid':'none';if(v==='squad')sqDetail()}
$$('#sView button').forEach(b=>b.onclick=()=>setView(b.dataset.v));
$('#sqDetail').onclick=e=>{const r=e.target.closest('[data-q]');if(!r)return;sqF=r.dataset.q;sqTabs();sList();setView('list')};
sqTabs();sList();sDetail(0);
// substitute
let lvC=0,lvO='sub';
function lvStep(n){$$('.lvsteps span').forEach((x,k)=>x.classList.toggle('on',k<n));$$('.lvs').forEach(x=>x.classList.toggle('on',+x.dataset.s===n))}
$('#lvEv').onclick=()=>{$('#lvBox').classList.add('on');lvStep(1)};
$('#lvX').onclick=()=>$('#lvBox').classList.remove('on');
$('#lvWhy').onclick=e=>{const b=e.target.closest('button');if(!b)return;$$('#lvWhy button').forEach(x=>x.classList.toggle('on',x===b))};
$$('.opt2 button').forEach(b=>b.onclick=()=>{lvO=b.dataset.o;$$('.opt2 button').forEach(x=>x.classList.toggle('on',x===b))});
$('#lvNext1').onclick=()=>{if(lvO==='move'){lvStep(3);$('#lvDoneT').textContent='已問 5 位家長，改期到週五 19:00（4 票）';return}lvStep(2)};
$('#cands').onclick=e=>{const b=e.target.closest('.cand');if(!b)return;lvC=+b.dataset.c;$$('.cand').forEach(x=>x.classList.toggle('on',x===b));$('#lvNext2').textContent='請'+b.querySelector('b').textContent+'代課'};
$('#lvNext2').onclick=function(){this.textContent='詢問中⋯';this.disabled=true;later(()=>{this.disabled=false;const n=$$('.cand b')[lvC].textContent;$('#lvDoneT').textContent=n+'已接下這堂課';lvStep(3);const e=$('#lvEv');e.className='wev off';e.innerHTML='<span class="lat">19:00</span><b>'+n+'代課</b><small>你請假</small>'},1200)};
$('#lvClose').onclick=()=>$('#lvBox').classList.remove('on');
// calendar hourly
function calJump(){}
// calendar
// room — whiteboard + video
const SLIDES=['<div class="big1">−2<span style="font-style:italic">x</span> <span style="font-style:normal">&gt;</span> 6</div><div class="note1">↓ 兩邊同除以 −2</div><div class="big1">x <span class="flip" style="font-style:normal">&lt;</span> −3</div>',
 '<div class="note1">乘以 −1 之後，整條數線翻過去</div><svg class="nlw" viewBox="0 0 520 90"><line x1="10" y1="45" x2="510" y2="45" stroke="#0D2B26" stroke-width="3"/>'+[-3,-2,-1,0,1,2,3].map((v,k)=>'<line x1="'+(40+k*73)+'" y1="37" x2="'+(40+k*73)+'" y2="53" stroke="#0D2B26" stroke-width="2"/><text x="'+(40+k*73)+'" y="78" text-anchor="middle" font-family="Outfit" font-size="16" fill="#5E6B67">'+v+'</text>').join('')+'<circle cx="332" cy="45" r="9" fill="#0E5F52"/><circle cx="186" cy="45" r="9" fill="#F26B54"/><path d="M332 30 Q259 -6 186 30" fill="none" stroke="#F26B54" stroke-width="2.5" stroke-dasharray="6 5"/></svg><div class="note1">2 在 1 的右邊；翻過去之後，−2 跑到 −1 的左邊</div>',
 '<div class="note1">換你試試 · 先寫答案再說為什麼</div><div class="big1">−3x ≤ 12</div>',
 ''];
let tool='pen',col='#F26B54',strokes=[],cur2=null,cv,ctx2;
function cvInit(){cv=$('#board');const r=cv.getBoundingClientRect(),dpr=2;cv.width=cv.offsetWidth*dpr;cv.height=cv.offsetHeight*dpr;ctx2=cv.getContext('2d');ctx2.scale(dpr,dpr);redraw()}
function redraw(){if(!ctx2)return;ctx2.clearRect(0,0,cv.width,cv.height);strokes.forEach(drawS)}
function drawS(s){ctx2.save();ctx2.lineCap=ctx2.lineJoin='round';ctx2.globalCompositeOperation=s.t==='eraser'?'destination-out':'source-over';ctx2.globalAlpha=s.t==='hl'?.35:1;ctx2.strokeStyle=s.c;ctx2.lineWidth=s.t==='hl'?18:s.t==='eraser'?26:3.5;ctx2.beginPath();s.p.forEach((q,k)=>k?ctx2.lineTo(q[0],q[1]):ctx2.moveTo(q[0],q[1]));ctx2.stroke();ctx2.restore()}
function pos(e){const r=cv.getBoundingClientRect(),k=cv.offsetWidth/r.width;return [(e.clientX-r.left)*k,(e.clientY-r.top)*k]}
$('#board').addEventListener('pointerdown',e=>{if(tool==='text'||tool==='shape'){rToast(tool==='text'?'文字工具：點一下就能打字（示意）':'形狀工具：畫直線、箭頭、圓（示意）');return}cur2={t:tool,c:col,p:[pos(e)]};strokes.push(cur2);$('#bHint').style.opacity=0;$('#board').setPointerCapture(e.pointerId)});
$('#board').addEventListener('pointermove',e=>{if(!cur2)return;cur2.p.push(pos(e));redraw()});
addEventListener('pointerup',()=>cur2=null);
$$('#tools [data-t]').forEach(b=>b.onclick=()=>{tool=b.dataset.t;$$('#tools [data-t]').forEach(x=>x.classList.toggle('on',x===b))});
$$('#tools [data-c]').forEach(b=>b.onclick=()=>{col=b.dataset.c;$$('#tools [data-c]').forEach(x=>x.classList.toggle('on',x===b));if(tool==='eraser'){tool='pen';$$('#tools [data-t]').forEach(x=>x.classList.toggle('on',x.dataset.t==='pen'))}});
$('#undo').onclick=()=>{strokes.pop();redraw()};
function setPage(k){$('#slide').innerHTML=SLIDES[k]||'';$$('#pages [data-p]').forEach(x=>x.classList.toggle('on',+x.dataset.p===k));strokes=[];redraw()}
$('#pages').onclick=e=>{const b=e.target.closest('[data-p]');if(b)setPage(+b.dataset.p)};
$('#addPage').onclick=()=>{setPage(3);rToast('已新增空白頁，學生畫面同步')};
$('#addMat').onclick=()=>setPage(1);
function rToast(t){const x=$('#rToast');x.textContent=t;x.classList.add('show');clearTimeout(x._t);x._t=setTimeout(()=>x.classList.remove('show'),1800)}
const WALL=[['小睿','s1','x ≥ −4',1],['小安','s2','x ≥ 4',0],['小宇','s3','x ≥ −4',1],['小晴','s4','x ≤ −4',0],['阿哲','s5','x ≥ −4',1],['小恩','s6','x ≥ −4',1]];
function setStage(n){$('#wall').classList.toggle('on',n===2);$('#pairs2').classList.toggle('on',n===3);$('#tools').style.visibility=n===1?'visible':'hidden';$('#pages').style.visibility=n===1?'visible':'hidden';
 const vt=$$('#vg2 .vt2');vt.forEach(v=>v.classList.remove('gA','gB'));
 if(n===2){$('#wall').innerHTML=WALL.map(w=>'<div class="ans2"><div class="who"><img class="ph" src="img/'+w[1]+'.jpg" width="26" height="26" alt="">'+w[0]+'<span class="flag" style="margin-left:auto;display:none">錯</span></div><div class="hw">'+w[2]+'</div><div class="act2"><button data-show>投到白板（匿名）</button></div></div>').join('');
  $$('#wall .ans2').forEach((a,k)=>later(()=>{a.classList.add('in',WALL[k][3]?'ok':'bad');if(!WALL[k][3])a.querySelector('.flag').style.display='inline-block'},500+k*450));
  later(()=>$('#roomAi').textContent='4 人對、2 人錯。小安是除法算錯，小晴是方向沒反。兩種錯分開處理：按「分組」。',3400)}
 if(n===3){$('#pairs2').innerHTML=[['s1','s2','小睿 → 小安','正在講'],['s3','s4','小宇 → 小晴','正在講'],['s5','s6','阿哲 → 小恩','安靜 40 秒']].map((p,k)=>'<div class="pr"><div class="two"><img src="img/'+p[0]+'.jpg" alt=""><img src="img/'+p[1]+'.jpg" alt=""></div><b>'+p[2]+'</b>'+(k<2?'<div class="eqlz"><i></i><i></i><i></i></div>':'<span class="flag">'+p[3]+'</span>')+'<button class="mini o" data-listen>進去聽</button></div>').join('');
  $('#roomAi').textContent='阿哲那組安靜 40 秒了，可能卡住。點「進去聽」只有他們聽得到你。'}
 if(n===1)$('#roomAi').textContent='大家都在。小晴還沒開口過，她不會主動舉手。'}
// lesson track
const BLK=[{m:5,ai:'暖身：6 個人都答了。只有 4 人答對，等一下「你們的錯」就從這題講。'},{m:10,ai:'講這週全隊共同的錯：除以負數忘了變號。先用小陪準備的錯誤示例，再放數線動畫。'},{m:10,ai:'A、B 組拿到不同難度的題目，只有你看得到誰拿哪一份。'},{m:10,ai:'已依作答分組。你帶 A 組（小睿、小晴、小恩）走數線；B 組由小宇當小老師。'},{m:10,ai:'阿哲那組安靜 40 秒了，可能卡住。點「進去聽」只有他們聽得到你。'},{m:5,ai:'每人 30 秒說一句「我今天搞懂的」，同時交一題出場卡。這是課後整理最重要的資料。'}];
const START=[0,5,15,25,35,45];let blk=0,elapsed=0;
function setBlock(k){blk=Math.max(0,Math.min(5,k));$$('#track button').forEach((b,i)=>{b.classList.toggle('on',i===blk);b.classList.toggle('done',i<blk);b.classList.remove('over');b.querySelectorAll('.fill').forEach(x=>x.remove())});
 ['poll','exitc'].forEach(id=>$('#'+id).classList.remove('on'));
 if(blk===0){setStage(1);showPoll()}
 else if(blk===1){setStage(1);setPage(0)}
 else if(blk===2){setStage(2)}
 else if(blk===3){setStage(1);setPage(1);$('#bGroup').click()}
 else if(blk===4){setStage(3)}
 else {setStage(1);showExit()}
 $('#roomAi').textContent=BLK[blk].ai;elapsed=START[blk]*60+20;drawHead();$('#nextBlk').textContent=blk<5?'下一段：'+$$('#track button')[blk+1].querySelector('i').textContent+' ›':'下課 ›'}
function drawHead(){const tr=$('#track'),w=tr.clientWidth;$('#head').style.left=(elapsed/3000*w)+'px';const b=$$('#track button')[blk];let f=b.querySelector('.fill');if(!f){f=document.createElement('span');f.className='fill';b.appendChild(f)}const used=elapsed-START[blk]*60;f.style.width=Math.min(100,used/(BLK[blk].m*60)*100)+'%';if(used>BLK[blk].m*60){b.classList.add('over');$('#roomAi').textContent='這一段超時 '+Math.ceil((used-BLK[blk].m*60)/60)+' 分鐘。小陪建議把「互相講」縮到 8 分鐘，下課時間不變。'}
 const mm=elapsed/60|0,ss=elapsed%60;$('#rClock').textContent=String(mm).padStart(2,'0')+':'+String(ss).padStart(2,'0')}
function showPoll(){const p=$('#poll');p.classList.add('on');p.innerHTML='<h4>暖身快問 · 全員作答 · 30 秒</h4><div class="qq">−2 × 1 和 −2 × 2，哪個比較大？</div>'+[['−2 × 1 比較大',4,0],['−2 × 2 比較大',2,1],['一樣大',0,1]].map(r=>'<div class="pbar'+(r[2]?' bad':'')+'"><span>'+r[0]+'</span><div class="t"><i data-w="'+(r[1]/6*100)+'"></i></div><b>'+r[1]+' 人</b></div>').join('')+'<p class="body" style="font-size:13px">答錯的 2 人不會被公開。你看得到是誰：小安、小晴。</p>';later(()=>$$('#poll .t i').forEach(i=>i.style.width=i.dataset.w+'%'),200)}
function showExit(){const p=$('#exitc');p.classList.add('on');const E=[['s1','小睿','乘負數整條數線會翻過去，所以大小反過來。'],['s2','小安','要變號，而且除法要寫出來才不會錯。'],['s3','小宇','可以用代數字的方法檢查方向對不對。'],['s4','小晴','我知道要變號了，但為什麼還要再想一下。'],['s5','阿哲','負號不能直接丟掉，丟掉答案會錯。'],['s6','小恩','把錯的答案代回去就知道哪裡錯。']];
 p.innerHTML='<h4>我今天搞懂的 · 每人一句＋出場卡一題</h4><div class="exl">'+E.map(e=>'<div class="exr"><img src="img/'+e[0]+'.jpg" alt=""><div><b>'+e[1]+'</b>　'+e[2]+'</div><span class="flag '+(e[1]==='小晴'?'h':'g')+'">'+(e[1]==='小晴'?'出場卡錯':'出場卡對')+'</span></div>').join('')+'</div>';$$('#exitc .exr').forEach((r,k)=>later(()=>r.classList.add('in'),300+k*500))}
$('#track').onclick=e=>{const b=e.target.closest('[data-b]');if(b)setBlock(+b.dataset.b)};
$('#nextBlk').onclick=()=>{if(blk<5)setBlock(blk+1);else go('recap')};
$('#wall').addEventListener('click',e=>{const b=e.target.closest('[data-show]');if(!b)return;const w=b.closest('.ans2').querySelector('.hw').textContent;setStage(1);$('#slide').innerHTML='<div class="note1">有同學這樣寫（匿名）· 大家覺得呢？</div><div class="big1">'+w+'</div>';strokes=[];redraw();rToast('已投到全班白板，不顯示名字')});
$('#pairs2').addEventListener('click',e=>{const b=e.target.closest('[data-listen]');if(b){b.textContent='聆聽中 · 只有這組聽得到你';b.disabled=true}});
[['bMic','麥克風'],['bCam','鏡頭']].forEach(([id,n])=>$('#'+id).onclick=function(){const on=this.classList.toggle('on');this.classList.toggle('off',!on);rToast(n+(on?'已開啟':'已關閉'))});
$('#bShare').onclick=function(){this.classList.toggle('act');rToast(this.classList.contains('act')?'正在分享你的螢幕（示意）':'已停止分享')};
$('#bMuteAll').onclick=()=>{$$('#vg2 .vt2').forEach(v=>v.classList.remove('talk'));rToast('全體已靜音，學生可以舉手請求發言')};
$('#bQuiz').onclick=()=>{setStage(2);rToast('已出題：−3x ≤ 12，學生各自作答中')};
$('#bGroup').onclick=()=>{const vt=$$('#vg2 .vt2');vt.forEach(v=>v.classList.add(v.dataset.g==='A'?'gA':'gB'));rToast('A 組（珊瑚框）跟你；B 組（藍框）自己練，8 分鐘後回來');$('#roomAi').textContent='已依作答分組。A 組：小睿、小晴、小恩；B 組由小宇當小老師。'};
// voice
const VT='今天大家比我想的快。阿哲問了為什麼不能直接把負號丟掉，這是全隊最好的問題。小睿講給小安聽的那段很清楚。小晴方向還不穩，我想幫她補一格。下週進分數係數。';
const hold=$('#holdBtn');let held=false;
function startHold(e){e.preventDefault();if(held)return;held=true;hold.classList.add('on');$('#holdTip').textContent='正在聽⋯';type($('#vTx'),VT,45,()=>{hold.classList.remove('on');$('#holdTip').textContent='小陪整理中⋯';const ck=$$('#vOut .ck');ck.forEach((c,k)=>later(()=>c.classList.add('ok'),500+k*600));later(()=>{$('#holdTip').textContent='好了，三樣都在電腦上等你確認。';const b=$('#vGo');b.disabled=false;b.style.opacity=1},2400)})}
hold.addEventListener('pointerdown',startHold);hold.addEventListener('click',startHold);
// profile (inline edit)
function pv(){const n=[$('#pName').value,$('#pLine').value,$$('#stylePick button.on').length===3,$('#pubEdu').checked].filter(Boolean).length;const pc=60+n*10;$('#complN').textContent=pc+'%';$('#complRing').style.strokeDashoffset=97.4*(1-pc/100)}
['pName','pLine'].forEach(id=>$('#'+id).oninput=pv);['pubStyle','pubRate','pubEdu'].forEach(id=>$('#'+id).onchange=pv);
$$('.tagpick').forEach(g=>g.onclick=e=>{const b=e.target.closest('button');if(!b)return;const max=+g.dataset.max||99;if(!b.classList.contains('on')&&g.querySelectorAll('.on').length>=max){g.classList.remove('shake');void g.offsetWidth;g.classList.add('shake');return}b.classList.toggle('on');pv()});
$('#pRec').onclick=function(){this.classList.add('on');$('#pRecTx').textContent='錄音中⋯';later(()=>{this.classList.remove('on');$('#pRecTx').textContent='0:29 · 剛錄好'},2200)};
$$('[data-apply2]').forEach(b=>b.onclick=()=>{b.innerHTML='<b>已排試教</b><span>9/27（六）10:00</span>'});
pv();
// tier
function tierView(v){$$('#tierSeg button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));$$('.tv').forEach(t=>t.classList.toggle('on',t.dataset.v===v));if(v==='me')later(()=>$$('#dims .prog i').forEach(i=>i.style.width=i.dataset.w+'%'),120)}
$$('#tierSeg button').forEach(b=>b.onclick=()=>tierView(b.dataset.v));
$$('#ladder .tier').forEach((t,k)=>{if(k<2)t.classList.add('done');t.onclick=()=>tierView('rule')});
$$('[data-thx]').forEach(b=>b.onclick=()=>{b.textContent='已送出謝謝';b.disabled=true});
// materials
function matView(v){$$('#matSeg button').forEach(b=>b.classList.toggle('on',b.dataset.v===v));$$('.mv').forEach(m=>m.classList.toggle('on',m.dataset.v===v));$('#matF').style.visibility=v==='lib'?'visible':'hidden'}
$$('#matSeg button').forEach(b=>b.onclick=()=>matView(b.dataset.v));
$$('#matF [data-f]').forEach(b=>b.onclick=()=>{$$('#matF [data-f]').forEach(x=>x.classList.toggle('on',x===b));$$('#mgrid .mc').forEach(m=>m.classList.toggle('hide',b.dataset.f!=='all'&&m.dataset.src!==b.dataset.f))});
$('#mgrid').onclick=e=>{const d=e.target.closest('[data-del]');if(d){const m=d.closest('.mc');m.classList.add('gone');setTimeout(()=>m.remove(),250);return}
 const a=e.target.closest('[data-addp]');if(a){a.textContent='已加進第 2 週';a.disabled=true;return}
 const r=e.target.closest('[data-rev]');if(r){const m=r.closest('.mc');m.classList.remove('ai');m.dataset.src='mine';m.querySelector('small').textContent='AI 產生 · 你已審核 · 可用';r.outerHTML='<button class="mini o" data-addp>加進教案</button>'}};
$('#fillPlan').onclick=function(){$$('.plang .pc.empty').forEach((c,k)=>later(()=>{c.className='pc fill';c.textContent=['分層練習','讀題分組'][k]||'出場卡'},300+k*400));this.textContent='已補上 · 標成黃色，等你看過';this.disabled=true};
$('#upDemo').onclick=function(){const d=$('#drop2');d.classList.add('got');d.querySelector('b').textContent='不等式講義.pdf · 6 頁';this.remove();
 const R=['找到 14 題、答案與解法','12 題對應到 3 個卡點：乘除負數 7、分數係數 3、應用題 2','暖身 2、分層練習 8、出場卡 2、錯誤示例 2','第 9 題答案有誤（應為 x ≥ −4）· 沒有個資 · 非翻拍市售書','可以替你現在的 6 位學生出 A/B 兩組'];
 $$('.aistep').forEach((st,k)=>{later(()=>st.className='aistep run',k*700);later(()=>{st.className='aistep done';st.querySelector('div').insertAdjacentHTML('beforeend','<span class="res">'+R[k]+'</span>')},k*700+650)})};
// ===== 小陪 assistant =====
const SUG={today:['今天有什麼要先處理？','這個月賺多少？','週三那堂我要請假'],opps:['哪一隊最適合我？','只看 1 對 1','幫我開分數係數補強'],students:['小晴最近怎麼樣？','誰需要我注意？'],calendar:['段考前兩週我週日下午也可以','週三那堂我要請假','每週最多改成 10 堂'],materials:['幫我出分數係數的練習','第 3 週還缺什麼教材？'],income:['這個月賺多少？','什麼時候入帳？'],tier:['我離白金還差什麼？'],_:['這個月賺多少？','週三那堂我要請假','小晴最近怎麼樣？']};
const PAGE={today:'今天',opps:'開課機會',students:'我的學生',calendar:'班表',brief:'上課前',room:'教室',recap:'課後整理',records:'紀錄',materials:'教材',assist:'教學助理',tier:'評鑑',impact:'評鑑',income:'收入',payout:'出帳',profile:'個人資料'};
function acSay(h,cls){const d=document.createElement('div');d.className='msg '+cls;d.innerHTML=h;$('#acM').appendChild(d);$('#acM').scrollTop=9e9;return d}
function acReply(q){const t=acSay('<i></i><i></i><i></i>','t');setTimeout(()=>{t.remove();let h;
 if(/週日|可以上|有空/.test(q))h='好。我理解成：<b>段考前兩週（10/25、11/1）的週日 14:00–17:00</b> 也開放排課。<div class="act"><button class="mini" data-ac="avail">套用到班表</button><button class="mini o" data-ac="no">不是這個意思</button></div>';
 else if(/請假/.test(q))h='是<b>週三 9/23 19:00 不等式 B 隊</b>嗎？離上課還有 2 天，不影響可靠度。<div class="act"><button class="mini" data-ac="leave">對，幫我找代課</button><button class="mini o" data-ac="no">不是</button></div>';
 else if(/賺|收入|入帳/.test(q))h='9 月到今天：<div class="kv2"><span>可出帳</span><b>NT$18,200</b><span>結算中</span><b>NT$3,000</b><span>本月預估</span><b>NT$33,000</b><span>下次自動入帳</span><b>10/8 前</b></div><div class="act"><button class="mini o" data-ac="income">看明細</button></div>';
 else if(/小晴|注意/.test(q))h='<b>小晴</b>：方向的觀念還沒穩、再測沒過一次；心情連兩天偏低；她不會舉手。週四有排 25 分鐘補強。<div class="act"><button class="mini o" data-ac="stu">看她的紀錄</button></div>';
 else if(/最多|堂/.test(q))h='每週上限改成 <b>10 堂</b>嗎？依現在的需求，每月大約會多 NT$8,000。<div class="act"><button class="mini" data-ac="cap">改成 10 堂</button></div>';
 else if(/適合|開|補強/.test(q))h='最適合你的是<b>乘除負數 · 1 對 6 · 週三 19:00</b>（適合 92），6 人已湊滿、等你接。<div class="act"><button class="mini" data-ac="opp">帶我去看</button></div>';
 else if(/教材|練習|出/.test(q))h='我依這六個人的錯法出了<b>分數係數 3＋3＋2 題</b>，放在教材庫「AI 產生待審」，你看過才會給學生。<div class="act"><button class="mini o" data-ac="mat">去審核</button></div>';
 else if(/白金|等級/.test(q))h='還差 <b>1 分</b>。最快的兩條路：課後整理當天確認（+1），或接班 3 小時內回覆（+1）。';
 else h='我可以幫你：調班表、請假找代課、查學生、查收入、出教材。直接說或打字都行。';
 acSay(h,'a')},700)}
function acAsk(q){if(!q)return;acSay(q,'u');acReply(q)}
function acOpen(q){$('#aiChat').classList.add('on');$('#aiFab').classList.add('hide');const id=STEPS[cur].id;$('#acCtx').textContent='我看得到你現在在「'+(PAGE[id]||'這一頁')+'」';$('#acS').innerHTML=(SUG[id]||SUG._).map(x=>'<button>'+x+'</button>').join('');if(!$('#acM').children.length)acSay('嗨，林老師。要調班表、請假、查學生或收入，跟我說一聲就好。','a');if(q)acAsk(q);else $('#acIn').focus()}
$('#aiFab').onclick=()=>acOpen();$('#acX').onclick=()=>{$('#aiChat').classList.remove('on');$('#aiFab').classList.remove('hide')};
$('#acS').onclick=e=>{const b=e.target.closest('button');if(b)acAsk(b.textContent)};
$('#acF').onsubmit=e=>{e.preventDefault();const v=$('#acIn').value.trim();$('#acIn').value='';acAsk(v)};
$('#acMic').onclick=function(){this.classList.add('rec');$('#acIn').placeholder='正在聽⋯';setTimeout(()=>{this.classList.remove('rec');$('#acIn').placeholder='打字，或按左邊用說的';acAsk((SUG[STEPS[cur].id]||SUG._)[0])},1300)};
document.addEventListener('click',e=>{const k=e.target.closest('[data-ask]');if(k)return acOpen(k.dataset.ask);const b=e.target.closest('[data-ac]');if(!b)return;const a=b.dataset.ac;b.closest('.act').querySelectorAll('button').forEach(x=>x.disabled=true);
 if(a==='avail'){go('calendar');$$('#calSeg button')[1].click();$$('#avgrid .c').forEach(c=>{const [d,r]=c.dataset.k.split('-').map(Number);if(d===6&&r>=R(14)&&r<=R(16))setCell(c,true)});avEst();acSay('已套用，班表上亮起來的三格就是。預估每月收入同步更新了。','a')}
 else if(a==='leave'){go('calendar');setTimeout(()=>$('#lvEv').click(),200);acSay('已幫你打開請假，我先排了三位代課人選。','a')}
 else if(a==='income')go('income');else if(a==='stu'){go('students')}else if(a==='opp')go('opps');else if(a==='mat')go('materials');
 else if(a==='cap'){cap=10;$('#capN').textContent=10;avEst();acSay('改好了，每週最多 10 堂。','a')}
 else acSay('好，那你再說一次，我重新理解。','a')});
// assist + payout
$$('[data-adopt]').forEach(b=>b.onclick=()=>{b.disabled=true;b.textContent='已採用'});
$$('[data-add]').forEach(b=>b.onclick=()=>{b.disabled=true;b.textContent='已放進課前一頁'});
let poD=7;$$('#poSpeed button').forEach(b=>b.onclick=()=>{$$('#poSpeed button').forEach(x=>x.classList.toggle('on',x===b));poD=+b.dataset.d;$('#poFee').textContent=poD===3?'0（第 2 級免手續費）':'0';$('#poGo').textContent='確認出帳到 玉山銀行 ••••3821 · '+(poD===3?'9/24 前':'9/28 前')+'入帳'});
$('#poGo').onclick=()=>{$('#poForm').style.display='none';$('#poDone').style.display='grid';$('#poEta').textContent=poD===3?'預計 9/24（四）':'預計 9/28（一）';$('#poBank').textContent=poD===3?'1–2 個工作天':'3–5 個工作天';const st=$$('#poSteps div');st.forEach((d,k)=>d.classList.toggle('on',k===0));later(()=>st[1].classList.add('on'),1200);later(()=>st[2].classList.add('on'),2400)};
const FREQ={m:['每月 1 日自動出帳','上個月已結算的全部出帳，走標準 7 天，約 8 日前入帳'],h:['每月 1 日、16 日自動出帳','每半個月結一次，走標準 7 天'],w:['每週一自動出帳','可出帳滿 NT$1,000 才出，走標準 7 天']};let freq='m';
function autoTxt(){const on=$('#autoTog').classList.contains('on');$('#autoTx').textContent=on?FREQ[freq][0]:'自動出帳已關閉';$('#autoSub').textContent=on?FREQ[freq][1]:'需要時在左邊手動出帳';$('#autoFreq').style.display=on?'grid':'none'}
$('#autoTog').onclick=function(){this.classList.toggle('on');autoTxt()};
$$('#autoFreq button').forEach(b=>b.onclick=()=>{freq=b.dataset.f;$$('#autoFreq button').forEach(x=>x.classList.toggle('on',x===b));autoTxt()});
// recap
$('#obsSave').onclick=function(){const v=$('#obsIn').value.trim()||'小晴今天好像心情不好，週四補強先聊聊。';$('#obsIn').value=v;this.textContent='已加進小晴的紀錄';this.disabled=true};
$('#obsMic').onclick=()=>{const t='小晴今天好像心情不好，週四補強先聊聊。',el=$('#obsIn');let k=0;el.value='';const iv=every(()=>{el.value=t.slice(0,++k);if(k>=t.length)clearInterval(iv)},40)};
function rcTab(r){$$('#rcTabs [data-r]').forEach(b=>b.classList.toggle('on',b.dataset.r===r));$$('.rcp').forEach(p=>p.classList.toggle('on',p.dataset.r===r))}
$('#rcTabs').onclick=e=>{const b=e.target.closest('[data-r]');if(b)rcTab(b.dataset.r)};
const STS=[['小睿','s1',90,80,'會講了，還能教別人。狀態：睡少但專注。','g','可以挑戰分數係數'],['小安','s2',70,60,'觀念懂，除法仍算錯。','','放慢寫出每一步'],['小宇','s3',95,70,'領先，當小老師表現好。','g','給進階題'],['小晴','s4',35,20,'17 分鐘沒開口，方向反了；31:05 第一次問問題。','c','週四一對一；別在全班前點她'],['阿哲','s5',80,90,'提出全隊最好的問題；互講時卡 40 秒後自己通。','g','稱讚他的問題，下堂當開場'],['小恩','s6',65,50,'會背不會講，互講時講得比較完整了。','h','先讓她解釋一個錯答案']];
$('#stg').innerHTML=STS.map(x=>'<div class="sc3"><div class="who"><img class="ph" src="img/'+x[1]+'.jpg" width="34" height="34" alt=""><b>'+x[0]+'</b>'+(x[5]?'<span class="flag '+x[5]+'" style="margin-left:auto">'+(x[5]==='c'?'需關心':x[5]==='g'?'進步':'留意')+'</span>':'')+'</div><div class="bars3"><span>理解</span><div class="prog"><i style="width:'+x[2]+'%"></i></div><span>參與</span><div class="prog"><i style="width:'+x[3]+'%;background:var(--coral)"></i></div></div><p>'+x[4]+'</p><small style="color:var(--mute)">下次：'+x[6]+'</small></div>').join('');
$('#txQ').oninput=e=>{const q=e.target.value.trim();$$('#txl .tr').forEach(r=>{r.classList.toggle('hide',q&&!r.textContent.includes(q))})};
$('[data-jumpk]').onclick=function(){const on=this.classList.toggle('on');$$('#txl .tr').forEach(r=>r.classList.toggle('hide',on&&!r.classList.contains('key')));this.textContent=on?'顯示全部':'只看關鍵時刻'};
// weekly reports
const WR=[{n:'小睿',im:'s1',g:'段考數學 70 → 85',gp:46,gt:'走完 3 / 7 個點 · 照這個步調到得了',l:['兩邊乘除負數（已掌握）','分數係數（會了，等再測）'],o:'這週練了 5 天、說給我聽 4 次。上課第一次主動講給隊友聽。',s:'睡眠偏少兩天；小陪已自動減量。',nx:'下週進應用題；建議維持每天 30 分鐘就好。',ask:'「負二乘以一和負二乘以二，哪個比較大？」'},
 {n:'小晴',im:'s4',g:'會考數學 B++',gp:22,gt:'走完 1 / 6 個點 · 有點慢，但方向對',l:['不等式的意思（已掌握）'],o:'方向的觀念還沒穩，再測沒過一次；週四一對一之後第二題自己做出來。',s:'這週比較安靜。她選擇不分享心情，老師只看得到旗標。',nx:'先不加新內容；下週一對一再補一次數線。',ask:'「這週哪一題你自己做出來了？」（請先別問分數）'},
 {n:'阿哲',im:'s5',g:'不要再怕分數',gp:60,gt:'不等式已走完 · 下週轉幾何隊',l:['乘除負數（已掌握）','移項（已掌握）'],o:'提了全隊最好的問題。看到分數仍會緊張，但願意開口了。',s:'狀態穩定。',nx:'轉到週六幾何隊，老師同一位。',ask:'「你那天問老師的問題是什麼？」'}];
function wDraw(k){const d=WR[k]||WR[0];$('#wrep').innerHTML='<div class="wr-h"><img src="img/'+d.im+'.jpg" alt=""><div><b>'+d.n+' 的這一週</b><small>小陪整理的草稿</small></div><span style="display:flex;gap:6px"><button class="mini o" data-ask="幫我把'+d.n+'的週報語氣改得更鼓勵一點">請小陪改</button><button class="mini" data-wok="'+k+'">確認</button></span></div>'+
 '<div class="wr-goal"><div class="r"><b>目標：'+d.g+'</b><span>'+d.gt+'</span></div><div class="prog"><i style="width:'+d.gp+'%"></i></div></div>'+
 '<div class="wr-g"><div class="wr-c"><h6>這週學會了</h6>'+d.l.map(x=>'<div>· '+x+'</div>').join('')+'</div><div class="wr-c"><h6>觀察</h6>'+d.o+'</div><div class="wr-c"><h6>狀態 · 只有你看得到</h6>'+d.s+'</div></div>'+
 '<div class="wr-c" style="background:var(--honey-soft)"><h6>下週</h6>'+d.nx+'</div>'+
 '<div class="wr-ask"><small>給家人 · 這週可以問他</small>'+d.ask+'</div>'}
$('#wlist').onclick=e=>{const r=e.target.closest('[data-w]');if(!r)return;$$('#wlist .srow').forEach(x=>x.classList.toggle('on',x===r));wDraw(+r.dataset.w)};
function wOk(k){const r=$$('#wlist .srow')[k];if(!r)return;const t=r.querySelector('.wst');t.textContent='已確認 · 週日 20:00 送出';t.classList.add('ok')}
$('#wrep').onclick=e=>{const b=e.target.closest('[data-wok]');if(b){wOk(+b.dataset.wok);b.textContent='已確認';b.disabled=true}};
$('#sendAll').onclick=function(){$$('#wlist .srow').forEach((_,k)=>later(()=>wOk(k),k*180));this.disabled=true;this.textContent='6 份已確認 · 週日 20:00 送出'};
wDraw(0);
const ENTER={
 _ai(){},
 opps(){$('#oDraw').classList.remove('on');if(location.search.includes('od'))later(()=>$('#oList .orow').click(),60)},
 materials(){matView((location.search.match(/mv=(\w+)/)||[])[1]||'lib')},
 tier(){const v=(location.search.match(/tv=(\w+)/)||[])[1]||'me';tierView(v)},
 recap(){rcTab('note');$('#rcBody').style.opacity=0;$('#rcFoot').classList.remove('show');$('#rcSub').textContent='小陪正在整理這堂課⋯';const d=$$('#rcProg div');d.forEach(x=>x.className='');
  d.forEach((x,k)=>{later(()=>x.className='run',k*650);later(()=>x.className='done',k*650+600)});
  later(()=>{$('#rcBody').style.opacity=1;$('#rcSub').textContent='整理好了 · 50 分鐘 · 6 人出席 · 你講話 34%';$('#rcFoot').classList.add('show')},2800)},
 today(){},
 room(){setStage(1);setPage(0);later(()=>{cvInit();setBlock(1);elapsed=12*60+48;drawHead()},80);every(()=>{elapsed+=1;drawHead()},1000);
  const vt=$$('#vg2 .vt2');vt.forEach(v=>v.querySelectorAll('.badge').forEach(x=>x.remove()));let t=0;every(()=>{vt.forEach(v=>v.classList.remove('talk'));vt[[0,2,4,0,2][t++%5]].classList.add('talk')},1600);
  later(()=>{vt[4].insertAdjacentHTML('beforeend','<span class="badge"><svg class="i"><use href="#i-hand"/></svg></span>');rToast('阿哲舉手了')},4000);
  later(()=>{vt[3].insertAdjacentHTML('beforeend','<span class="badge help"><svg class="i"><use href="#i-help"/></svg></span>');rToast('小晴私下按了「需要幫忙」，只有你看得到')},7500)},
 voice(){held=false;hold.classList.remove('on');$('#vTx').textContent='⋯';$$('#vOut .ck').forEach(c=>c.classList.remove('ok'));const b=$('#vGo');b.disabled=true;b.style.opacity=.4;$('#holdTip').textContent='按住開始（示範只需 4 秒）'},
 payout(){$('#poForm').style.display='grid';$('#poDone').style.display='none'},
 income(){let n=0;const el=$('#incBig');const t=every(()=>{n+=700;if(n>=18200){n=18200;clearInterval(t)}el.innerHTML='NT$'+n.toLocaleString()},30);later(()=>{$('#mInc').style.width='72%';$$('#bars2 i').forEach(i=>i.style.height=(i.dataset.h*0.85)+'px')},200)},
 calendar(){if(location.search.includes('chat'))later(()=>acOpen('段考前兩週我週日下午也可以'),200);$('#lvBox').classList.remove('on');if(location.search.includes('lv'))later(()=>$('#lvEv').click(),50);if(location.search.includes('avail'))$$('#calSeg button')[1].click()}
};
{const h=location.hash.slice(1);go(Math.max(0,STEPS.findIndex(s=>s.id===h)))};if(document.fonts&&document.fonts.ready)document.fonts.ready.then(fit);
})();
