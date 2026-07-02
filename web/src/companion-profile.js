(function () {
  const STORAGE_KEY = 'munea.companionProfile.v1';
  const templates = {
    'nening-real-female': {
      backendChar: '寧寧',
      defaultName: '寧寧',
      templateLabel: '溫柔型 · 像家人，會照看',
      thumbAsset: 'avatars/nening-real-female.png',
      homeAsset: 'avatars/nening-hero.png',
      fullAsset: 'avatars/nening-real-female-full.png',
    },
    'companion-real-male': {
      backendChar: '阿宏',
      defaultName: '阿宏',
      templateLabel: '沉穩型 · 像大哥，很可靠',
      thumbAsset: 'avatars/companion-real-male.png',
    },
    'munea-2d-xiaoyun': {
      backendChar: '小昀',
      defaultName: '小昀',
      fullAsset: 'avatars/nening-real-female-full.png',
      templateLabel: '開朗型 · 像朋友，很有朝氣',
      thumbAsset: 'avatars/munea-2d-xiaoyun.png',
    },
    'munea-2d-ayuan': {
      backendChar: '阿原',
      defaultName: '阿原',
      templateLabel: '隨和型 · 鄰家感，好聊天',
      thumbAsset: 'avatars/munea-2d-ayuan.png',
    },
    'munea-2d-mimi': {
      backendChar: '咪咪',
      defaultName: '咪咪',
      templateLabel: '貓咪型 · 陪伴感，有個性',
      thumbAsset: 'avatars/munea-2d-mimi.png',
    },
    'munea-2d-wangcai': {
      backendChar: '旺財',
      defaultName: '旺財',
      templateLabel: '狗狗型 · 熱情，很黏人',
      thumbAsset: 'avatars/munea-2d-wangcai.png',
    },
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
    let rawName = ((profile && profile.displayName) || t.defaultName).trim();
    if (/^munea$/i.test(rawName) || rawName === '沐寧') rawName = t.defaultName; // 品牌名不當人名（舊示範資料清理）
    const displayName = rawName.slice(0, 12) || t.defaultName;
    return {
      templateId,
      displayName,
      nameTouched: !!(profile && profile.nameTouched),
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
