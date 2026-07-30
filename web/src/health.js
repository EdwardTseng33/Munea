/* 沐寧 · Apple 健康（HealthKit）網頁橋接
   跟原生外掛 Capacitor.Plugins.Health 對接（原生程式：ios/App/App/HealthPlugin.swift）。
   - 只在 iPhone 真機（有原生外掛）才會動；網頁/模擬器自動變空轉，不影響其他功能。
   - 讀到的值：丟給狀態頁的 window.__muneaSetHealth（Windows 端負責呈現）＋步數餵給首頁走路任務。
   對接文件：docs/Apple健康串接-給Mac的實作說明-2026-07-08.md */
window.MuneaHealth = (function () {
  const GOAL = 500; // 走路任務目標步數（跟首頁「今天走 500 步」一致）
  const REFRESH_COOLDOWN_MS = 60000;
  let disconnectArmTimer = null;
  let refreshPromise = null;
  let lastRefreshAt = 0;
  let lastSummary = null;
  // 讀到資料了沒：true=至少一項有值、false=一項都沒有、null=還沒讀過（不亂猜）
  let hasData = null;
  // 這次開 App 之後真的讀過了沒。沒讀過之前不准說「讀不到」——
  // 只憑上次存下來的舊結果就先下結論，會在剛打開項目回來時冤枉使用者。
  let readDone = false;
  let lastReadFields = [];   // 這次讀到哪幾項
  let lastReadError = '';    // 讀取失敗的原因（空字串＝沒失敗）
  let lastReadAt = 0;

  function t(key, fallback, values) {
    return window.MuneaI18n
      ? window.MuneaI18n.t(key, values || null, fallback)
      : fallback;
  }

  function plugin() {
    return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Health) || null;
  }
  function isNative() {
    try { return !!(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()); }
    catch (e) { return false; }
  }
  // 這台裝置能不能用（有原生外掛 = 在 App 裡）
  function available() { return !!plugin(); }
  function connected() { try { return localStorage.getItem('munea.devicesOn') === '1'; } catch (e) { return false; } }

  // 蘋果不會告訴 App「使用者拒絕了讀取」——授權視窗跳過就一律算成功。
  // 所以「有沒有真的連上」只能看讀不讀得到值，不能看 requestAuthorization 的回覆。
  function hasAnyValue(s) {
    if (!s) return false;
    return ['steps', 'hr', 'spo2', 'bpSys', 'bpDia', 'sleepHours']
      .some(k => typeof s[k] === 'number' && isFinite(s[k]) && s[k] > 0);
  }
  function setHasData(v) {
    hasData = v;
    try {
      if (v === null) localStorage.removeItem('munea.health.hasData');
      else localStorage.setItem('munea.health.hasData', v ? '1' : '0');
    } catch (e) {}
  }
  // 上次真的讀到的摘要（重開 App 後、第一次刷新回來前也要有依據，不能空窗期亂猜）
  function cachedSummary() {
    if (lastSummary) return lastSummary;
    try {
      const raw = JSON.parse(localStorage.getItem('munea.health.last') || 'null');
      return raw && raw.s ? raw.s : null;
    } catch (e) { return null; }
  }

  // 每一項指標現在是什麼狀態：
  //   'off'   還沒連 Apple 健康
  //   'ok'    真的讀到值了
  //   'empty' 連了，但這一項讀不到（沒授權這項、或這支手機還沒有這種紀錄）
  // 畫面一律照這個渲染。不可以用「使用者按過連接鍵」當作有資料——
  // 蘋果不會告訴 App 讀取被拒絕，按過鍵不代表讀得到任何東西。
  function metricStates() {
    const all = v => ({ bp: v, hr: v, spo2: v, sleep: v, steps: v });
    if (!connected()) return all('off');
    const s = cachedSummary();
    if (!s) return all('empty');
    const has = k => typeof s[k] === 'number' && isFinite(s[k]) && s[k] > 0;
    return {
      bp: (has('bpSys') && has('bpDia')) ? 'ok' : 'empty',
      hr: has('hr') ? 'ok' : 'empty',
      spo2: has('spo2') ? 'ok' : 'empty',
      sleep: has('sleepHours') ? 'ok' : 'empty',
      steps: has('steps') ? 'ok' : 'empty'
    };
  }

  function loadHasData() {
    try {
      const v = localStorage.getItem('munea.health.hasData');
      hasData = v === '1' ? true : v === '0' ? false : null;
    } catch (e) { hasData = null; }
  }

  // 蘋果的授權視窗「同一批項目只跳一次」——問過之後再呼叫，系統什麼都不會做、
  // 也不會回報任何錯誤。所以要自己記住問過沒有，否則第二次點「連接」在使用者眼中就是壞掉。
  function askedBefore() {
    try { return !!localStorage.getItem('munea.health.askedAt'); } catch (e) { return false; }
  }
  function markAsked() {
    try { localStorage.setItem('munea.health.askedAt', String(Date.now())); } catch (e) {}
  }

  // 使用者只需要理解兩種狀態，加上一個動作（Edward 2026-07-30 拍板）：
  //   'off' 未連接 → 按鍵「連接」
  //   'on'  已連接 → 按鍵「解除連接」
  //
  // 「已連接」的定義＝**真的讀得到資料**。讀不到就是沒連上，不另外發明狀態——
  // 讀不到的原因（沒開項目／這支手機沒紀錄／讀取失敗）是我們內部的事，
  // 不該變成使用者要理解的第三、第四種狀態。原因寫在下面的說明文字裡就好。
  //
  // 'checking' 只是還沒讀完的過場，不是狀態：畫面沿用上一次的結論，
  // 不會先跳一個「讀不到」再自己改口。
  function uiState() {
    if (!connected()) return 'off';
    if (!readDone) return hasData === true ? 'on' : 'checking';
    return hasData === true ? 'on' : 'off';
  }

  // 把使用者送到「健康」App 自己開項目（App 不能代替他開，蘋果不給）
  async function openHealthApp() {
    const p = plugin();
    if (!p || typeof p.openHealthApp !== 'function') return { opened: false };
    try { return await p.openHealthApp(); } catch (e) { return { opened: false }; }
  }

  const FIELD_LABEL = {
    steps: () => t('health.steps', '步數'),
    hr: () => t('health.heartRate', '心率'),
    spo2: () => t('health.bloodOxygen', '血氧'),
    bpSys: () => t('health.bloodPressure', '血壓'),
    bpDia: () => t('health.bloodPressure', '血壓'),
    sleepHours: () => t('health.sleep', '睡眠'),
  };

  // 把 {time} 這種佔位符換成真的值。翻譯載入時是翻譯層在換，
  // 但沒載到翻譯（走預設字）時沒人換，會把「{time} 讀到：{items}」原封不動給使用者看。
  function fill(text, values) {
    return String(text == null ? '' : text)
      .replace(/\{(\w+)\}/g, (whole, key) => (values && values[key] != null ? String(values[key]) : whole));
  }

  // 讀取實況：讓人能確定「到底讀到了沒」，而不是只看到一片空白自己猜。
  function readEvidence() {
    if (!connected() || !lastReadAt) return '';
    const at = new Date(lastReadAt);
    const clock = String(at.getHours()).padStart(2, '0') + ':' + String(at.getMinutes()).padStart(2, '0');
    if (lastReadError) return fill(t('health.readFailedAt', '{time} 讀取失敗：{reason}', { time: clock, reason: lastReadError }), { time: clock, reason: lastReadError });
    const names = [];
    lastReadFields.forEach(k => {
      const label = FIELD_LABEL[k] && FIELD_LABEL[k]();
      if (label && names.indexOf(label) < 0) names.push(label);
    });
    return names.length
      ? fill(t('health.readOkAt', '{time} 讀到：{items}', { time: clock, items: names.join('、') }), { time: clock, items: names.join('、') })
      : fill(t('health.readNothingAt', '{time} 讀過了，一項都沒有', { time: clock }), { time: clock });
  }

  function renderConnectionState() {
    const view = uiState();
    const on = view !== 'off';
    // 第一次還沒問過授權 → 按「連接」跳系統視窗；
    // 問過了（蘋果一輩子只跳一次）→ 按「連接」直接帶去健康 App。
    // 兩種對使用者來說都只是「連接」這一個動作，不必知道差別。
    const firstTime = !askedBefore();
    const btn = document.getElementById('cnHealthBtn');
    if (btn) {
      btn.classList.toggle('done', on);
      btn.classList.toggle('disconnect', on);
      btn.classList.remove('arm');
      delete btn.dataset.disconnectArmed;
      btn.dataset.action = on ? 'disconnect' : (firstTime ? 'connect' : 'openHealth');
      btn.textContent = on
        ? t('health.disconnect', '解除連接')
        : t('health.connect', btn.dataset.label || '連接');
      btn.disabled = false;
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    const state = document.getElementById('healthSettingsState');
    if (state) state.classList.toggle('off', !on);
    const stateLabel = document.getElementById('healthSettingsStateLabel');
    if (stateLabel) stateLabel.textContent = on
      ? t('health.connected', '已連接')
      : t('health.notConnected', '未連接');
    const detail = document.getElementById('cnHealthDetail');
    if (detail) detail.textContent = on
      ? t('health.syncingDetail', '正在同步步數、心率、睡眠、血壓與血氧')
      : t('health.availableDetail', '自動含手錶與其他裝置 · 步數/心率/睡眠/血壓/血氧');
    // 說明文字負責講「為什麼現在是未連接」——原因放這裡，不變成另一種狀態。
    const help = document.getElementById('cnHealthHelp');
    if (help) help.textContent = on
      ? t(
        'health.disconnectHelp',
        '「解除連接」是叫沐寧不要再讀，iPhone 給的授權還是開著的——要完全收回，請到「健康」App →個人照片→「App 與服務」→沐寧 關掉項目。',
      )
      : view === 'checking'
        ? t('health.checkingHelp', '正在跟「健康」App 要今天的資料，稍等一下。')
        : firstTime
          // 授權視窗裡的項目預設是關的——很多人直接按允許，等於一項都沒開，
          // 這是「按了連接卻沒資料」最大的來源，所以先講在前面。
          ? t(
            'health.notConnectedHelp',
            '按下「連接」後手機會跳出一個畫面，請把要給沐寧看的項目一項一項打開再按允許——那些項目預設是關著的。',
          )
          : t(
            'health.reconnectHelp',
            '沐寧目前讀不到資料。授權畫面只會跳一次，所以按「連接」我會帶你到「健康」App，在那裡把沐寧的項目打開就好。',
          );
    const evidence = document.getElementById('cnHealthReadState');
    if (evidence) {
      const line = readEvidence();
      evidence.textContent = line;
      evidence.hidden = !line;
    }
  }

  function emitConnectionState() {
    setTimeout(renderConnectionState, 0);
    try { window.dispatchEvent(new CustomEvent('munea:health-connection', { detail: { connected: connected() } })); } catch (e) {}
  }

  // 使用者點「連接 Apple 健康」→ 跳系統授權 → 讀一次資料
  async function connect() {
    const p = plugin();
    if (!p) return { ok: false, reason: 'unsupported' }; // 不在 App 裡（網頁預覽）
    try {
      const asked = askedBefore();
      const r = await p.requestAuthorization();
      if (r && r.available === false) return { ok: false, reason: 'unavailable' }; // 這台沒有健康資料
      markAsked();
      try { localStorage.setItem('munea.devicesOn', '1'); } catch (e) {}
      const s = await refresh({ force: true });
      emitConnectionState();
      // 一項都沒讀到就照實說：多半是授權視窗裡沒打開項目，也可能這支手機本來就沒紀錄。
      // 蘋果不讓 App 分辨這兩者，所以不猜原因、只講現況跟怎麼開。
      if (!hasAnyValue(s)) {
        // 之前已經問過 → 系統剛剛那一下什麼都沒跳（蘋果只跳一次），
        // 再叫他「重按一次連接」永遠不會有結果，要直接送他去「健康」App 開項目。
        return { ok: true, empty: true, needsHealthApp: asked, summary: s };
      }
      return { ok: true, summary: s };
    } catch (e) {
      return { ok: false, reason: 'error', message: String(e) };
    }
  }

  // 讀最新健康摘要，餵回網頁
  async function refresh(options) {
    if (!connected()) return null;
    const p = plugin();
    if (!p) return null;
    if (refreshPromise) return refreshPromise;
    const force = !!(options && options.force);
    if (!force && lastRefreshAt && Date.now() - lastRefreshAt < REFRESH_COOLDOWN_MS) {
      // 冷卻期內不重讀，但這代表剛剛才讀過——別讓畫面卡在「檢查中」出不來
      readDone = true;
      setTimeout(renderConnectionState, 0);
      return lastSummary;
    }

    lastRefreshAt = Date.now();
    refreshPromise = (async function () {
      let s = null;
      // 讀失敗要留下原因。原本這裡是 catch 完就安靜回 null，
      // 使用者看到的跟「真的沒有資料」一模一樣，誰都查不出是哪一種。
      try { s = await p.getSummary(); }
      catch (e) {
        lastReadError = String((e && (e.message || e.errorMessage)) || e || 'unknown');
        lastReadAt = Date.now();
        readDone = true;
        setTimeout(renderConnectionState, 0);
        return null;
      }
      if (!connected()) return null;
      if (!s || s.available === false) return null;
      // 原生端回報這次讀到哪幾項、哪幾項出錯（新版才有；舊版沒有就用值反推）
      lastReadFields = Array.isArray(s.fields)
        ? s.fields
        : ['steps', 'hr', 'spo2', 'bpSys', 'bpDia', 'sleepHours'].filter(k => typeof s[k] === 'number' && s[k] > 0);
      lastReadError = Array.isArray(s.errors) && s.errors.length ? s.errors.join('；') : '';
      lastReadAt = Date.now();
      readDone = true;
      // 記住這次到底有沒有值——沒有的話畫面要照實講，不能繼續寫「正在同步」
      setHasData(hasAnyValue(s));
      setTimeout(renderConnectionState, 0);
      lastSummary = s;
      // 狀態頁血壓/心率/睡眠等欄位：交給 Windows 端留的接口
      try { if (typeof window.__muneaSetHealth === 'function') window.__muneaSetHealth(s); } catch (e) {}
      // 數字寫完後再跑一次誠實層：這次沒讀到的項目要收回「—」並把標籤藏起來，
      // 否則上一輪讀到、這一輪讀不到時，畫面會留著舊值跟舊標籤繼續宣稱。
      try { if (typeof window.MMDEV === 'function') window.MMDEV(); } catch (e) {}
      // 步數 → 首頁走路任務（app.js 的接口）
      if (typeof s.steps === 'number' && typeof window.__muneaSetSteps === 'function') {
        try { window.__muneaSetSteps(s.steps); } catch (e) {}
      }
      try {
        if (typeof p.getHistory === 'function' && typeof window.__muneaSetHealthHistory === 'function') {
          const history = await p.getHistory({ days: 35 });
          if (connected() && history && history.available !== false && Array.isArray(history.days)) {
            window.__muneaSetHealthHistory(history.days);
          }
        }
      } catch (e) {}
      try { localStorage.setItem('munea.health.last', JSON.stringify({ t: Date.now(), s: s })); } catch (e) {}
      return s;
    })();
    try { return await refreshPromise; }
    finally { refreshPromise = null; }
  }

  function disconnect() {
    try {
      localStorage.removeItem('munea.devicesOn');
      localStorage.setItem('munea.health.disconnectedAt', String(Date.now()));
    } catch (e) {}
    setHasData(null);
    readDone = false; lastReadFields = []; lastReadError = ''; lastReadAt = 0;
    emitConnectionState();
    return { ok: true, authorizationRetained: true };
  }

  // 去「健康」App，回來自動重讀一次，剛打開的項目直接長出來、不用再按一次
  async function goHealthAppAndReread() {
    const onBack = () => {
      if (document.visibilityState === 'visible') {
        document.removeEventListener('visibilitychange', onBack);
        refresh({ force: true });
      }
    };
    document.addEventListener('visibilitychange', onBack);
    await openHealthApp();
  }

  // 整頁只有一顆按鍵。它做什麼由狀態決定（uiState），不再有第二顆做類似事情的鍵。
  function bindConnectionUi() {
    const btn = document.getElementById('cnHealthBtn');
    if (!btn) return;
    btn.addEventListener('click', function (event) {
      const action = btn.dataset.action || (connected() ? 'disconnect' : 'connect');
      if (action === 'connect') {
        setTimeout(renderConnectionState, 0);   // 真正的授權由 app.js 那邊呼叫 connect()
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      // 「連接」但系統視窗不會再跳（問過了）→ 帶去健康 App，回來自動重讀
      if (action === 'openHealth') { lastReadError = ''; goHealthAppAndReread(); return; }
      // 解除連接：兩段式確認，避免長輩誤觸
      if (btn.dataset.disconnectArmed !== '1') {
        btn.dataset.disconnectArmed = '1';
        btn.classList.add('arm');
        btn.textContent = t('health.confirmDisconnect', '再按一次解除');
        clearTimeout(disconnectArmTimer);
        disconnectArmTimer = setTimeout(renderConnectionState, 4000);
        return;
      }
      clearTimeout(disconnectArmTimer);
      disconnect();
    }, true);
    renderConnectionState();
  }

  // App 啟動：之前連過就靜默刷新一次（含把步數帶回走路任務）
  function boot() {
    loadHasData();
    // 每次開 App 都要重新確認一次。上次存的「讀不到」只是上次的事——
    // 使用者可能剛剛才去健康 App 把項目打開，這時候先說讀不到就是冤枉他。
    readDone = false; lastReadError = ''; lastReadFields = []; lastReadAt = 0;
    renderConnectionState();
    // 不加 force：重開 App 本來就沒有冷卻期，正常讀一次即可（冷卻期是為了省電，別破壞）
    if (available() && connected()) { refresh(); }
  }

  loadHasData();
  bindConnectionUi();
  window.addEventListener('munea:locale-ready', renderConnectionState);

  return { GOAL: GOAL, REFRESH_COOLDOWN_MS: REFRESH_COOLDOWN_MS, available: available, connected: connected, connect: connect, disconnect: disconnect, refresh: refresh, renderConnectionState: renderConnectionState, boot: boot, isNative: isNative, metricStates: metricStates, hasAnyValue: hasAnyValue, openHealthApp: openHealthApp, askedBefore: askedBefore, uiState: uiState, readEvidence: readEvidence };
})();
