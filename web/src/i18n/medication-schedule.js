(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaMedicationScheduleI18n = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SLOT_IDS = Object.freeze([
    'after-breakfast',
    'after-lunch',
    'after-dinner',
    'bedtime',
  ]);
  const SLOT_KEYS = Object.freeze({
    'after-breakfast': 'medication.slot.afterBreakfast',
    'after-lunch': 'medication.slot.afterLunch',
    'after-dinner': 'medication.slot.afterDinner',
    bedtime: 'medication.slot.bedtime',
  });
  const LEGACY_ZH_LABELS = Object.freeze({
    'after-breakfast': '早餐後',
    'after-lunch': '午餐後',
    'after-dinner': '晚餐後',
    bedtime: '睡前',
  });
  const ALIASES = Object.freeze({
    'after-breakfast': [
      'after-breakfast', '早餐後', '早餐', 'after breakfast', '朝食後',
      'después del desayuno', 'despues del desayuno',
    ],
    'after-lunch': [
      'after-lunch', '午餐後', '午餐', 'after lunch', '昼食後',
      'después del almuerzo', 'despues del almuerzo',
    ],
    'after-dinner': [
      'after-dinner', '晚餐後', '晚餐', 'after dinner', '夕食後',
      'después de la cena', 'despues de la cena',
    ],
    bedtime: [
      'bedtime', '睡前', 'before bed', '就寝前', 'antes de dormir',
    ],
  });

  function comparable(value) {
    return String(value || '')
      .trim()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/\s+/g, ' ');
  }

  const ALIAS_TO_ID = new Map();
  for (const [slotId, aliases] of Object.entries(ALIASES)) {
    for (const alias of aliases) ALIAS_TO_ID.set(comparable(alias), slotId);
  }

  function normalizeSlot(value) {
    return ALIAS_TO_ID.get(comparable(value)) || null;
  }

  function rawSlotValues(medication) {
    const med = medication || {};
    const structured = med.slotIds || med.slot_ids || med.slots;
    if (Array.isArray(structured) && structured.length) return structured;
    return String(med.time || med.scheduleTime || med.schedule_time || '')
      .split(/[、,，;；/／]+/)
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function scheduleSlots(medication) {
    const result = [];
    const seen = new Set();
    for (const raw of rawSlotValues(medication)) {
      const slotId = normalizeSlot(raw);
      const identity = slotId || `custom:${comparable(raw)}`;
      if (!identity || seen.has(identity)) continue;
      seen.add(identity);
      result.push(Object.freeze({
        id: slotId,
        storageValue: slotId || String(raw).trim(),
        custom: slotId === null,
        raw: String(raw).trim(),
      }));
    }
    return result.sort((left, right) => {
      const leftIndex = left.id ? SLOT_IDS.indexOf(left.id) : SLOT_IDS.length;
      const rightIndex = right.id ? SLOT_IDS.indexOf(right.id) : SLOT_IDS.length;
      if (leftIndex !== rightIndex) return leftIndex - rightIndex;
      return left.raw.localeCompare(right.raw);
    });
  }

  function displaySlot(value, translate) {
    const slotId = normalizeSlot(value);
    if (!slotId) return String(value || '').trim();
    const fallback = LEGACY_ZH_LABELS[slotId];
    return typeof translate === 'function'
      ? translate(SLOT_KEYS[slotId], fallback)
      : fallback;
  }

  function storagePatch(values) {
    const slots = scheduleSlots({ slots: values });
    const known = slots.filter((slot) => slot.id).map((slot) => slot.id);
    const legacy = slots.map((slot) => (
      slot.id ? LEGACY_ZH_LABELS[slot.id] : slot.raw
    ));
    return Object.freeze({
      slotIds: Object.freeze(known),
      time: legacy.join('、'),
    });
  }

  return Object.freeze({
    ALIASES,
    LEGACY_ZH_LABELS,
    SLOT_IDS,
    SLOT_KEYS,
    displaySlot,
    normalizeSlot,
    scheduleSlots,
    storagePatch,
  });
}));
