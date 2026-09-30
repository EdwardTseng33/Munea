(function () {
  const STORAGE_KEY = 'munea.companionProfile.v1';

  function t(key, fallback) {
    return window.MuneaI18n
      ? window.MuneaI18n.t(key, null, fallback)
      : fallback;
  }

  function template(config) {
    const value = { ...config };
    Object.defineProperties(value, {
      defaultName: {
        enumerable: true,
        get: () => t(config.defaultNameKey, config.defaultNameFallback),
      },
      templateLabel: {
        enumerable: true,
        get: () => t(config.templateLabelKey, config.templateLabelFallback),
      },
    });
    return Object.freeze(value);
  }

  const templates = {
    'nening-real-female': template({
      backendChar: '寧寧',
      defaultNameKey: 'companion.nening.name',
      defaultNameFallback: t('companion.nening.name', '寧寧'),
      templateLabelKey: 'companion.nening.label',
      templateLabelFallback: t('companion.nening.label', '溫柔型，像家人一樣照看你'),
      thumbAsset: 'avatars/ningning-flat-face.png',   // 2026-09-30 扁平插畫寧寧（取代照片）
      homeAsset: 'avatars/ningning-flat-face.png',
      fullAsset: 'avatars/ningning-flat-full.png',
    }),
    'munea-2d-xiaoyun': template({
      backendChar: '小昀',
      defaultNameKey: 'companion.xiaoyun.name',
      defaultNameFallback: t('companion.xiaoyun.name', '小昀'),
      templateLabelKey: 'companion.xiaoyun.label',
      templateLabelFallback: t('companion.xiaoyun.label', '開朗型，像朋友一樣有朝氣'),
      thumbAsset: 'avatars/xiaoyun-2d-face.png',
      homeAsset: 'avatars/xiaoyun-2d.png',
      fullAsset: 'avatars/xiaoyun-2d-tall.jpg',
    }),
    'munea-2d-mimi': template({
      backendChar: '咪咪',
      defaultNameKey: 'companion.mimi.name',
      defaultNameFallback: t('companion.mimi.name', '咪咪'),
      templateLabelKey: 'companion.mimi.label',
      templateLabelFallback: t('companion.mimi.label', '貓咪型，有個性又會陪著你'),
      thumbAsset: 'avatars/munea-2d-mimi-face.png',
      fullAsset: 'avatars/mimi-tall.jpg',
    }),
  };
  const aliases = {
    'real-f': 'nening-real-female',
    'toon-f': 'munea-2d-xiaoyun',
    cat: 'munea-2d-mimi',
  };
  // 男生角色全數下線（Edward 2026-09-30）：阿宏、阿原、旺財。存過這些角色的人一律改由寧寧陪伴。
  // 預設名要一起換回：輸入框失焦就會把名字標成「自己取的」，所以很多人存的其實是預設名，
  // 不處理就會變成寧寧的臉掛著「Sam」、她講話還自稱 Sam。四種語言的預設名都要認得。
  const RETIRED_TEMPLATE_IDS = ['companion-real-male', 'munea-2d-ayuan', 'munea-2d-wangcai', 'real-m', 'toon-m', 'dog'];
  const RETIRED_DEFAULT_NAMES = ['阿宏', 'Sam', 'ひろし', 'Mateo', '阿原', 'Leo', 'けんた', 'Álvaro', '旺財', 'Buddy', 'ポチ', 'Toby'];
  function isRetiredTemplate(templateId) {
    return RETIRED_TEMPLATE_IDS.indexOf(templateId) >= 0;
  }
  function normalizeTemplateId(templateId) {
    return aliases[templateId] || (templates[templateId] ? templateId : 'nening-real-female');
  }
  function templateFor(templateId) {
    return templates[normalizeTemplateId(templateId)] || templates['nening-real-female'];
  }
  function normalizeProfile(profile) {
    const templateId = normalizeTemplateId(profile && profile.templateId);
    const t = templateFor(templateId);
    const retired = !!(profile && isRetiredTemplate(profile.templateId));
    const storedName = ((profile && profile.displayName) || '').trim();
    const nameTouched = !!(profile && profile.nameTouched)
      && !(retired && RETIRED_DEFAULT_NAMES.indexOf(storedName) >= 0);
    let rawName = (
      nameTouched
        ? ((profile && profile.displayName) || t.defaultName)
        : t.defaultName
    ).trim();
    if (/^munea$/i.test(rawName) || rawName === '沐寧') rawName = t.defaultName; // 品牌名不當人名（舊示範資料清理）
    const displayName = rawName.slice(0, 12) || t.defaultName;
    return {
      templateId,
      displayName,
      nameTouched,
      updatedAt: (profile && profile.updatedAt) || new Date().toISOString(),
    };
  }
  function loadProfile() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return normalizeProfile(raw ? JSON.parse(raw) : null);
    } catch (e) {
      return normalizeProfile(null);
    }
  }
  function saveProfile(profile) {
    const normalized = normalizeProfile(Object.assign({}, profile, { updatedAt: new Date().toISOString() }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    return normalized;
  }
  // 開機時看一眼原始存檔：是不是從已下線的男生角色搬過來的（App 要據此說一句、並同步回雲端）
  function storedTemplateRetired() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      return !!(raw && isRetiredTemplate(raw.templateId));
    } catch (e) {
      return false;
    }
  }
  window.MuneaCompanionProfile = {
    STORAGE_KEY,
    templates,
    aliases,
    RETIRED_TEMPLATE_IDS,
    RETIRED_DEFAULT_NAMES,
    isRetiredTemplate,
    storedTemplateRetired,
    loadProfile,
    saveProfile,
    templateFor,
    normalizeProfile,
    normalizeTemplateId,
  };
})();
