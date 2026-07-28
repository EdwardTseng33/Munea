/* ============ Munea 官網 · 共用動作 ============
 * 注意：語言切換已改成「四個真網址」（/、/en/、/ja/、/es/），
 * 舊的「把英文藏在標籤屬性、用 JS 當場換字」那套已整包移除
 * —— 那條路 Google 只看得到中文版，四語系等於白做。
 * 每個動作都尊重系統的「減少動態」設定。
 * ============================================== */
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* 捲動進度條 */
  const bar = document.querySelector('.progress');
  function onScroll() {
    const h = document.documentElement;
    const sc = h.scrollTop / (h.scrollHeight - h.clientHeight);
    if (bar) bar.style.width = sc * 100 + '%';
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* 主標一個字一個字進場 */
  document.querySelectorAll('.word').forEach((w, i) => {
    w.style.animationDelay = 0.15 + i * 0.12 + 's';
  });

  /* 捲到才浮現 */
  const io = new IntersectionObserver(
    (es) => {
      es.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el));

  /* ===== 一天之中：捲動說故事 =====
   * 場景資料全部寫在 HTML 的 data-* 上，所以四個語系各自帶各自的文字，
   * 這支程式不必知道現在是哪一國話。 */
  const steps = [...document.querySelectorAll('.story-step')];
  const sceneWrap = document.querySelector('.scene .ph');
  const sceneLabel = document.querySelector('.scene .scene-label .txt');
  const sceneImg = document.querySelector('.scene .ph img');
  const timechip = document.querySelector('.scene .timechip');

  if (steps.length && sceneImg) {
    let cur = -1;
    const setStep = (i) => {
      if (i === cur || !steps[i]) return;
      cur = i;
      const d = steps[i].dataset;
      steps.forEach((s, k) => s.classList.toggle('on', k === i));
      if (sceneLabel && d.scene) sceneLabel.textContent = d.scene;
      if (timechip && d.time) timechip.textContent = d.time;
      if (d.img && !sceneImg.src.endsWith(d.img)) {
        if (reduce) {
          sceneImg.src = d.img;
        } else {
          // 先淡出、換圖、再淡入，避免換圖時硬跳
          if (sceneWrap) sceneWrap.classList.add('swapping');
          const swap = () => {
            sceneImg.src = d.img;
            if (sceneWrap) requestAnimationFrame(() => sceneWrap.classList.remove('swapping'));
          };
          setTimeout(swap, 180);
        }
      }
    };

    setStep(0);

    const so = new IntersectionObserver(
      (es) => {
        es.forEach((e) => {
          if (e.isIntersecting) setStep(steps.indexOf(e.target));
        });
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: 0 }
    );
    steps.forEach((s) => so.observe(s));

    // 手機上捲動觸發區很窄，補上「點一下也能換」
    steps.forEach((s, k) => s.addEventListener('click', () => setStep(k)));
  }

  /* ===== 卡片微傾（有滑鼠才啟用）===== */
  if (!reduce && window.matchMedia('(hover:hover)').matches) {
    document.querySelectorAll('[data-tilt]').forEach((card) => {
      card.addEventListener('mousemove', (e) => {
        const r = card.getBoundingClientRect();
        const px = (e.clientX - r.left) / r.width - 0.5;
        const py = (e.clientY - r.top) / r.height - 0.5;
        card.style.transform = `translateY(-10px) perspective(800px) rotateX(${-py * 5}deg) rotateY(${px * 6}deg)`;
      });
      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  }
})();

/* ===== 語言選單（只管開合，選項本身是連到別的網址的真連結）===== */
(function () {
  const sw = document.querySelector('.lang-switch');
  if (!sw) return;
  const trigger = sw.querySelector('.lang-trigger');
  const setOpen = (o) => {
    sw.setAttribute('data-open', o ? 'true' : 'false');
    if (trigger) trigger.setAttribute('aria-expanded', o ? 'true' : 'false');
  };
  setOpen(false);
  if (trigger)
    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      setOpen(sw.getAttribute('data-open') !== 'true');
    });
  document.addEventListener('click', (e) => {
    if (!sw.contains(e.target)) setOpen(false);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setOpen(false);
  });
})();

/* ===== 手機漢堡選單 ===== */
(function () {
  const header = document.querySelector('header');
  const btn = header && header.querySelector('.menu-btn');
  if (!header || !btn) return;
  const setMenu = (o) => {
    header.setAttribute('data-menu', o ? 'open' : 'closed');
    btn.setAttribute('aria-expanded', o ? 'true' : 'false');
  };
  setMenu(false);
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setMenu(header.getAttribute('data-menu') !== 'open');
  });
  header.querySelectorAll('.navlinks a').forEach((a) => a.addEventListener('click', () => setMenu(false)));
  document.addEventListener('click', (e) => {
    if (!header.contains(e.target)) setMenu(false);
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth > 900) setMenu(false);
  });
})();
