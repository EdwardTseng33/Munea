/* ============ CAREON · Warm Humane · motion ============ */
(function(){
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* scroll progress bar */
  const bar = document.querySelector('.progress');
  function onScroll(){
    const h = document.documentElement;
    const sc = h.scrollTop / (h.scrollHeight - h.clientHeight);
    if(bar) bar.style.width = (sc*100) + '%';
  }
  window.addEventListener('scroll', onScroll, {passive:true});
  onScroll();

  /* hero headline word stagger */
  document.querySelectorAll('.word').forEach((w,i)=>{
    w.style.animationDelay = (0.15 + i*0.12) + 's';
  });

  /* reveal on scroll */
  const io = new IntersectionObserver((es)=>{
    es.forEach(e=>{ if(e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
  }, {threshold:.12});
  document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

  /* parallax blobs — very gentle, scroll-tied only */
  if(!reduce){
    const blobs = [...document.querySelectorAll('.hero .blob')];
    let ticking = false;
    window.addEventListener('scroll', ()=>{
      if(ticking) return;
      ticking = true;
      requestAnimationFrame(()=>{
        const y = window.scrollY;
        blobs.forEach((b,i)=>{ b.style.transform = `translateY(${y * (0.03 + i*0.02)}px)`; });
        ticking = false;
      });
    }, {passive:true});
  }

  /* ===== scrollytelling story ===== */
  const steps = [...document.querySelectorAll('.story-step')];
  const sceneLabel = document.querySelector('.scene .scene-label .txt');
  const scenePh = document.querySelector('.scene .ph .scene-ph-txt');
  const timechip = document.querySelector('.scene .timechip');
  const sceneImg = document.querySelector('.scene .ph img');
  const scenes = [
    {label:'早上・她先開口', en:'Morning · She says hi first', img:'assets/app-home.jpg',     time:'08:00', timeEn:'08:00'},
    {label:'中午・親口提醒',  en:'Noon · A spoken reminder',    img:'assets/app-reminder.jpg', time:'12:00', timeEn:'12:00'},
    {label:'下午・家人放心',  en:'Afternoon · Family at ease',  img:'assets/app-family.jpg',   time:'15:00', timeEn:'15:00'},
    {label:'晚上・睡前記得',  en:'Night · Remembered',          img:'assets/app-status.jpg',   time:'21:00', timeEn:'21:00'}
  ];
  let curStep = 0;
  const isEn = () => document.documentElement.lang === 'en';
  function setStep(i){
    curStep = i;
    steps.forEach((s,k)=>s.classList.toggle('on', k===i));
    if(sceneLabel) sceneLabel.textContent = isEn() ? scenes[i].en : scenes[i].label;
    if(sceneImg && scenes[i].img && !sceneImg.src.endsWith(scenes[i].img)) sceneImg.src = scenes[i].img;
    if(timechip) timechip.textContent = isEn() ? scenes[i].timeEn : scenes[i].time;
  }
  if(steps.length){
    setStep(0);
    const so = new IntersectionObserver((es)=>{
      es.forEach(e=>{ if(e.isIntersecting){ setStep(steps.indexOf(e.target)); } });
    }, {rootMargin:'-45% 0px -45% 0px', threshold:0});
    steps.forEach(s=>so.observe(s));
    window.addEventListener('careon-lang', () => setStep(curStep));
  }

  /* ===== animated closed loop ===== */
  const nodes = [...document.querySelectorAll('.ring .node')];
  if(nodes.length && !reduce){
    let idx = 0, timer = null, ring = document.querySelector('.ring');
    function tick(){
      nodes.forEach((n,k)=>n.classList.toggle('active', k===idx));
      idx = (idx+1) % nodes.length;
    }
    function start(){ if(!timer){ tick(); timer = setInterval(tick, 1600); } }
    function stop(){ clearInterval(timer); timer=null; }
    const ro = new IntersectionObserver((es)=>{
      es.forEach(e=> e.isIntersecting ? start() : stop());
    }, {threshold:.25});
    if(ring) ro.observe(ring);
    nodes.forEach((n,k)=>n.addEventListener('mouseenter', ()=>{ idx=k; nodes.forEach((m,j)=>m.classList.toggle('active', j===k)); idx=(k+1)%nodes.length; }));
  } else if(nodes.length){
    nodes[0].classList.add('active');
  }

  /* ===== card tilt ===== */
  if(!reduce && window.matchMedia('(hover:hover)').matches){
    document.querySelectorAll('[data-tilt]').forEach(card=>{
      card.addEventListener('mousemove', e=>{
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left)/r.width - .5;
        const py = (e.clientY - r.top)/r.height - .5;
        card.style.transform = `translateY(-10px) perspective(800px) rotateX(${ -py*5 }deg) rotateY(${ px*6 }deg)`;
      });
      card.addEventListener('mouseleave', ()=>{ card.style.transform = ''; });
    });
  }
})();

/* ===== 中文 / English language switch (dropdown) ===== */
(function(){
  const KEY = 'careon-lang';
  const sw = document.querySelector('.lang-switch');
  const trigger = sw && sw.querySelector('.lang-trigger');
  const current = sw && sw.querySelector('.lang-current');
  const opts = sw ? [...sw.querySelectorAll('.lang-opt')] : [];
  const nodes = [...document.querySelectorAll('[data-en]')];
  nodes.forEach(n => { n._zh = n.innerHTML; });   // capture original Chinese
  let lang = 'zh';
  try { if (localStorage.getItem(KEY) === 'en') lang = 'en'; } catch(e){}
  function setOpen(o){ if(!sw) return; sw.setAttribute('data-open', o ? 'true' : 'false'); if(trigger) trigger.setAttribute('aria-expanded', o ? 'true' : 'false'); }
  function apply(l){
    lang = l;
    document.documentElement.lang = (l === 'en') ? 'en' : 'zh-Hant';
    nodes.forEach(n => { n.innerHTML = (l === 'en') ? n.getAttribute('data-en') : n._zh; });
    if (current) current.textContent = (l === 'en') ? 'EN' : '中文';
    opts.forEach(o => o.setAttribute('aria-selected', o.dataset.lang === l ? 'true' : 'false'));
    try { localStorage.setItem(KEY, l); } catch(e){}
    window.dispatchEvent(new Event('careon-lang'));
  }
  apply(lang);
  if (trigger) trigger.addEventListener('click', (e) => { e.stopPropagation(); setOpen(sw.getAttribute('data-open') !== 'true'); });
  opts.forEach(o => o.addEventListener('click', () => { apply(o.dataset.lang); setOpen(false); }));
  document.addEventListener('click', (e) => { if (sw && !sw.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });
})();

/* ===== mobile hamburger menu ===== */
(function(){
  const header = document.querySelector('header');
  const btn = header && header.querySelector('.menu-btn');
  if (!header || !btn) return;
  function setMenu(o){ header.setAttribute('data-menu', o ? 'open' : 'closed'); btn.setAttribute('aria-expanded', o ? 'true' : 'false'); }
  setMenu(false);
  btn.addEventListener('click', (e) => { e.stopPropagation(); setMenu(header.getAttribute('data-menu') !== 'open'); });
  header.querySelectorAll('.navlinks a').forEach(a => a.addEventListener('click', () => setMenu(false)));
  document.addEventListener('click', (e) => { if (!header.contains(e.target)) setMenu(false); });
  window.addEventListener('resize', () => { if (window.innerWidth > 900) setMenu(false); });
})();
