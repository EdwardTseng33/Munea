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
      thumbAsset: 'avatars/nening-v2-face.png',   // 2026-07-11 新長相大頭照
      homeAsset: 'avatars/nening-v2-face.png',
      fullAsset: 'avatars/nening-v2-full.png',   // 2026-07-11 新長相靜態底圖（配新打招呼/待機影片）
    }),
    'companion-real-male': template({
      backendChar: '阿宏',
      defaultNameKey: 'companion.ahong.name',
      defaultNameFallback: t('companion.ahong.name', '阿宏'),
      templateLabelKey: 'companion.ahong.label',
      templateLabelFallback: t('companion.ahong.label', '沉穩型，像大哥一樣可靠'),
      thumbAsset: 'avatars/ahong-v2-face.png',   // 2026-07-11 新長相大頭照
      homeAsset: 'avatars/ahong-v2-face.png',
      fullAsset: 'avatars/ahong-v4-full.png',   // 2026-07-11 新長相靜態底圖（配新打招呼/待機影片）
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
    'munea-2d-ayuan': template({
      backendChar: '阿原',
      defaultNameKey: 'companion.ayuan.name',
      defaultNameFallback: t('companion.ayuan.name', '阿原'),
      templateLabelKey: 'companion.ayuan.label',
      templateLabelFallback: t('companion.ayuan.label', '隨和型，像鄰居一樣好聊天'),
      thumbAsset: 'avatars/ayuan-2d-face.png',
      homeAsset: 'avatars/ayuan-2d.png',
      fullAsset: 'avatars/ayuan-2d-tall.jpg',
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
    'munea-2d-wangcai': template({
      backendChar: '旺財',
      defaultNameKey: 'companion.wangcai.name',
      defaultNameFallback: t('companion.wangcai.name', '旺財'),
      templateLabelKey: 'companion.wangcai.label',
      templateLabelFallback: t('companion.wangcai.label', '狗狗型，熱情又愛黏著你'),
      thumbAsset: 'avatars/munea-2d-wangcai-face.png',
      fullAsset: 'avatars/wangcai-tall.jpg',
    }),
  };
  const aliases = {
    'real-f': 'nening-real-female',
    'real-m': 'companion-real-male',
    'toon-f': 'munea-2d-xiaoyun',
    'toon-m': 'munea-2d-ayuan',
    cat: 'munea-2d-mimi',
    dog: 'munea-2d-wangcai',
  };
  function normalizeTemplateId(templateId) {
    return aliases[templateId] || (templates[templateId] ? templateId : 'nening-real-female');
  }
  function templateFor(templateId) {
    return templates[normalizeTemplateId(templateId)] || templates['nening-real-female'];
  }
  function normalizeProfile(profile) {
    const templateId = normalizeTemplateId(profile && profile.templateId);
    const t = templateFor(templateId);
    const nameTouched = !!(profile && profile.nameTouched);
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
  window.MuneaCompanionProfile = {
    STORAGE_KEY,
    templates,
    aliases,
    loadProfile,
    saveProfile,
    templateFor,
    normalizeProfile,
    normalizeTemplateId,
  };
})();
