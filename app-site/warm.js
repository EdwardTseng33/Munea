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
    {labels:{'zh-TW':'早上・她先開口',en:'Morning · She says hi first',ja:'朝 · 先に声をかけます',es:'Mañana · Saluda primero'},img:'assets/app-home.jpg',time:'08:00'},
    {labels:{'zh-TW':'中午・親口提醒',en:'Noon · A spoken reminder',ja:'昼 · 声でリマインド',es:'Mediodía · Recordatorio por voz'},img:'assets/app-reminder.jpg',time:'12:00'},
    {labels:{'zh-TW':'下午・家人放心',en:'Afternoon · Family at ease',ja:'午後 · 家族も安心',es:'Tarde · La familia tranquila'},img:'assets/app-family.jpg',time:'15:00'},
    {labels:{'zh-TW':'晚上・睡前記得',en:'Night · Remembered',ja:'夜 · 今日のことを記憶',es:'Noche · Lo vivido queda en la memoria'},img:'assets/app-status.jpg',time:'21:00'}
  ];
  let curStep = 0;
  const activeLocale = () => document.documentElement.dataset.muneaLocale || 'zh-TW';
  function setStep(i){
    curStep = i;
    steps.forEach((s,k)=>s.classList.toggle('on', k===i));
    if(sceneLabel) sceneLabel.textContent = scenes[i].labels[activeLocale()] || scenes[i].labels.en;
    if(sceneImg && scenes[i].img && !sceneImg.src.endsWith(scenes[i].img)) sceneImg.src = scenes[i].img;
    if(timechip) timechip.textContent = scenes[i].time;
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

/* ===== Four-locale public-site language switch ===== */
(function(){
  const KEY = 'careon-lang';
  const SUPPORTED = ['zh-TW', 'en', 'ja', 'es'];
  const HTML_LANG = {'zh-TW':'zh-Hant',en:'en',ja:'ja',es:'es'};
  const SHORT_LABEL = {'zh-TW':'中文',en:'EN',ja:'日本語',es:'ES'};
  const EN_MESSAGES = {soundOn:'Sound on',mute:'Mute'};
  const sw = document.querySelector('.lang-switch');
  const trigger = sw && sw.querySelector('.lang-trigger');
  const current = sw && sw.querySelector('.lang-current');
  const opts = sw ? [...sw.querySelectorAll('.lang-opt')] : [];
  const nodes = [...document.querySelectorAll('[data-en]')];
  const localizedAttributes = ['aria-label', 'alt', 'content'];
  const attributeBindings = localizedAttributes.flatMap((attribute) => (
    [...document.querySelectorAll(`[data-en-${attribute}]`)].map((element) => ({
      attribute,
      element,
      source: element.getAttribute(`data-en-${attribute}`),
      zh: element.getAttribute(attribute),
    }))
  ));
  const catalogs = new Map();
  nodes.forEach(n => { n._zh = n.innerHTML; });
  let lang = 'zh-TW';
  let requestId = 0;
  function normalizeLocale(value){
    const raw = String(value || '').trim().toLowerCase();
    if(raw === 'zh' || raw.startsWith('zh-')) return 'zh-TW';
    if(raw === 'ja' || raw.startsWith('ja-')) return 'ja';
    if(raw === 'es' || raw.startsWith('es-')) return 'es';
    if(raw === 'en' || raw.startsWith('en-')) return 'en';
    return null;
  }
  function initialLocale(){
    try {
      const saved = normalizeLocale(localStorage.getItem(KEY));
      if(saved) return saved;
    } catch(e){}
    const preferred = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language];
    for(const candidate of preferred){
      const resolved = normalizeLocale(candidate);
      if(resolved) return resolved;
    }
    return 'zh-TW';
  }
  async function loadCatalog(locale){
    if(locale === 'zh-TW' || locale === 'en') return null;
    if(catalogs.has(locale)) return catalogs.get(locale);
    const response = await fetch(`i18n/${locale}.json`);
    if(!response.ok) throw new Error(`locale catalog ${locale} returned ${response.status}`);
    const catalog = await response.json();
    if(
      catalog.schemaVersion !== 1
      || catalog.locale !== locale
      || !catalog.translations
      || !catalog.attributes
      || !catalog.messages
    ){
      throw new Error(`locale catalog ${locale} has an invalid contract`);
    }
    catalogs.set(locale, catalog);
    return catalog;
  }
  function translate(source, locale = lang){
    if(locale === 'zh-TW') return null;
    if(locale === 'en') return source;
    const catalog = catalogs.get(locale);
    return catalog && catalog.translations[source] || null;
  }
  function message(key, zhFallback){
    if(lang === 'zh-TW') return zhFallback;
    if(lang === 'en') return EN_MESSAGES[key] || null;
    const catalog = catalogs.get(lang);
    return catalog && catalog.messages[key] || null;
  }
  function setOpen(o){ if(!sw) return; sw.setAttribute('data-open', o ? 'true' : 'false'); if(trigger) trigger.setAttribute('aria-expanded', o ? 'true' : 'false'); }
  async function apply(value){
    const locale = normalizeLocale(value) || 'zh-TW';
    const ownRequest = ++requestId;
    if(trigger) trigger.setAttribute('aria-busy', 'true');
    try {
      await loadCatalog(locale);
      if(ownRequest !== requestId) return;
      const missing = [];
      const textUpdates = nodes.map(n => {
        const source = n.getAttribute('data-en');
        const localized = locale === 'zh-TW' ? n._zh : translate(source, locale);
        if(localized == null){
          missing.push(source);
        }
        return {element:n,localized};
      });
      const attributeUpdates = attributeBindings.map((binding) => {
        let localized = binding.zh;
        if(locale === 'en') localized = binding.source;
        if(locale === 'ja' || locale === 'es'){
          localized = catalogs.get(locale).attributes[binding.source];
        }
        if(localized == null){
          missing.push(`${binding.attribute}:${binding.source}`);
        }
        return {...binding,localized};
      });
      if(missing.length) throw new Error(`${locale} is missing ${missing.length} translation(s)`);
      textUpdates.forEach(({element,localized}) => { element.innerHTML = localized; });
      attributeUpdates.forEach(({element,attribute,localized}) => {
        element.setAttribute(attribute, localized);
      });
      lang = locale;
      document.documentElement.lang = HTML_LANG[locale];
      document.documentElement.dataset.muneaLocale = locale;
      document.documentElement.removeAttribute('data-i18n-error');
      if(current) current.textContent = SHORT_LABEL[locale];
      opts.forEach(o => o.setAttribute('aria-selected', o.dataset.lang === locale ? 'true' : 'false'));
      try { localStorage.setItem(KEY, locale); } catch(e){}
      window.dispatchEvent(new CustomEvent('careon-lang', {detail:{locale}}));
    } catch(error) {
      document.documentElement.setAttribute('data-i18n-error', locale);
      console.error('[Munea marketing i18n]', error);
    } finally {
      if(ownRequest === requestId && trigger) trigger.removeAttribute('aria-busy');
    }
  }
  window.MuneaMarketingI18n = {
    apply,
    getLocale: () => lang,
    message,
    normalizeLocale,
    supportedLocales: [...SUPPORTED],
    translate,
  };
  apply(initialLocale());
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
