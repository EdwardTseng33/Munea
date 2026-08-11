import './i18n/legal-routing.js';
import './i18n/medication-schedule.js';

/* Munea 沐寧 — 原型互動
 * 落實 Claude Design「沐寧 沐寧 配色」+ Elfie 融入（安心存摺 / 今天一起完成 / 家人互動）
 * 標 [ENGINE] 處正式版接 castle-voice-engine（中文〔台灣〕優先、英文第二 + 三顆腦 + 擬真 avatar；台語先不承諾）。 */

const $  = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const muneaLocale = () => (window.MuneaI18n ? window.MuneaI18n.current() : 'zh-TW');
const muneaPreferredLanguages = () => (window.MuneaI18n ? window.MuneaI18n.preferredLanguages() : ['zh-TW']);
const muneaT = (key, fallback, values = null) => (
  window.MuneaI18n ? window.MuneaI18n.t(key, values, fallback) : fallback
);
const legacyStaticTextSources = new WeakMap();
const legacyStaticAttributeSources = new WeakMap();
function localizeLegacyStaticCopy() {
  if (
    !window.MuneaI18n
    || typeof window.MuneaI18n.translateLegacySourceText !== 'function'
    || muneaLocale() === 'zh-TW'
  ) return;
  const excludedParents = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'OPTION']);
  for (const root of document.querySelectorAll('.screen, .modal-mask, .reader-page')) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const parent = node.parentElement;
      if (
        parent
        && !excludedParents.has(parent.tagName)
        && !parent.isContentEditable
      ) {
        if (!legacyStaticTextSources.has(node)) {
          legacyStaticTextSources.set(node, node.nodeValue);
        }
        const source = legacyStaticTextSources.get(node);
        const translated = window.MuneaI18n.translateLegacySourceText(source);
        if (translated !== node.nodeValue) node.nodeValue = translated;
      }
      node = walker.nextNode();
    }
    for (const element of root.querySelectorAll('[placeholder], [aria-label], [title]')) {
      let sources = legacyStaticAttributeSources.get(element);
      if (!sources) {
        sources = {};
        legacyStaticAttributeSources.set(element, sources);
      }
      for (const attribute of ['placeholder', 'aria-label', 'title']) {
        if (!element.hasAttribute(attribute)) continue;
        if (!Object.hasOwn(sources, attribute)) sources[attribute] = element.getAttribute(attribute);
        const translated = window.MuneaI18n.translateLegacySourceText(sources[attribute]);
        if (translated !== element.getAttribute(attribute)) {
          element.setAttribute(attribute, translated);
        }
      }
    }
  }
}
function localizeCanonicalLegacyPanels() {
  if (muneaLocale() === 'zh-TW') return;
  const setText = (selector, key, fallback, values = null) => {
    const element = document.querySelector(selector);
    if (element) element.textContent = muneaT(key, fallback, values);
  };
  const setDirectText = (selector, key, fallback, values = null) => {
    const element = document.querySelector(selector);
    if (!element) return;
    // 同上：底下已經有翻譯標記就別再補，否則外語版會印兩次。
    if (element.querySelector('[data-i18n]')) return;
    [...element.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .forEach((node) => node.remove());
    element.append(document.createTextNode(muneaT(key, fallback, values)));
  };
  const setAttribute = (selector, attribute, key, fallback, values = null) => {
    const element = document.querySelector(selector);
    if (element) element.setAttribute(attribute, muneaT(key, fallback, values));
  };

  // 就診摘要面板（M1 起改為真資料）。原本這裡在幫「寫死假數字的舊面板」做多語，
  // 其中 rptSendBtn 與 rpt-card 已隨改版移除（這裡刻意不寫井字號前綴：smoke.ps1 的
  // 「Frontend id references」會掃全檔的井字號選擇器、連註解也算，
  // 寫了就等於宣告一個不存在的元素，CI 會紅）。面板本文走 data-i18n，
  // 這裡只補 data-i18n 到不了的地方：aria-label、期間膠囊、要帶角色名的頁尾。
  // aria-label 改走 markup 的 data-i18n-aria-label（dom-localizer.js 支援）。
  // 原本在這裡用 JS setAttribute，問題是這整個函式**只在非 zh-TW 才跑**——
  // 等於 aria 只有外語使用者才是對的，中文讀屏使用者拿到的是 markup 裡的字。
  // 宣告式綁定四個語系一視同仁，而且改文案時不會忘記同步。
  $$('#rptPeriodTabs .seg-btn').forEach(button => {
    const days = parseInt(button.dataset.days, 10);
    if (days) button.textContent = muneaT('visit.days', '{n} days', { n: days });
  });
  // 頁尾要帶角色名，而角色是使用者選的（不是字串常數），所以不能單靠 data-i18n
  setText('#rptFoot', 'visit.footer',
    'Compiled by {companion} · Records provided by the family, not a medical diagnosis',
    { companion: (typeof cname === 'function' ? cname() : 'Munea') });

  setText('#historyModal h2', 'history.title', 'Past records');
  setText('#historyModal > .modal > .modal-sub', 'history.subtitle', 'View monthly summaries or choose a date range.');
  const historyMonths = $('#histMonths');
  if (historyMonths && historyMonths.dataset.localizedEmpty !== '1') {
    historyMonths.dataset.localizedEmpty = '1';
    historyMonths.replaceChildren();
    const empty = document.createElement('p');
    empty.className = 'modal-sub';
    empty.textContent = muneaT('history.empty', 'There are no records for this period.');
    historyMonths.appendChild(empty);
  }

  const consentPairs = [
    ['consent.cloudProcessingTitle', 'Voice and text are encrypted and sent to the cloud for processing', 'consent.cloudProcessingBody', 'They are used only to understand you and provide the service.'],
    ['consent.summaryOnlyTitle', 'Only necessary conversation highlights are retained', 'consent.summaryOnlyBody', 'Original recordings are not stored.'],
    ['consent.voicePurposeTitle', 'Your voice is used only to understand what you say', 'consent.voicePurposeBody', 'It is not used for identity recognition or unrelated purposes.'],
    ['consent.profileCloudTitle', 'Profile information you provide is securely synced', 'consent.profileCloudBody', 'Your photo stays on this phone.'],
  ];
  $$('#consentSheet .consent-points li').forEach((item, index) => {
    const pair = consentPairs[index];
    if (!pair) return;
    const title = item.querySelector('b');
    const body = item.querySelector('small');
    if (title) title.textContent = muneaT(pair[0], pair[1]);
    if (body) body.textContent = muneaT(pair[2], pair[3]);
  });
  setText('#consentSheet .consent-note', 'consent.dataController', 'Munea manages this data. You can request access, correction, or deletion.');
  setText('#consentAgree', 'consent.agree', 'I understand. Start talking');
  setText('#consentDetail', 'consent.detail', 'Read the full privacy notice first');

  setText(
    '#connect .cn-intro p',
    'health.connectDisclosure',
    'Apple Health syncs steps, heart rate, sleep, and other data when Munea opens. Munea can notify you when something needs attention. This is not real-time or medical-grade monitoring.',
  );
  setText('#connect .cn-note p', 'health.optionalBody', 'Health data is optional. Your companion can still support you through daily conversations and reminders.', {
    companion: cname(),
  });
  setDirectText(
    '#connect .cn-privacy',
    'health.familyVisibility',
    'Only family members you authorize can view health information.',
  );

  setText('#feedbackModal h2', 'feedback.title', 'Feedback');
  setText('#feedbackModal > .modal > .modal-sub', 'legacyUi.feedbackSubtitle', 'We read every message. Choose a topic and tell us what you think.');
  // 意見分類那四顆按鈕不必在這裡補翻譯——它們的 index.html 裡已經有
  // <span data-i18n="feedback.categoryXxx">，翻譯層會處理。
  // 這段是改版殘骸：按鈕本來是純文字，後來改成包在 span 裡，這個迴圈忘了拿掉，
  // 於是 setDirectText 又在 span 後面補一段文字節點，外語版每顆按鈕的字都印兩次
  // （「Informar de un problemaInformar de un problema」，Edward 2026-08-01 抓到）。
  // 中文版不受影響——localizeCanonicalLegacyPanels 開頭就對 zh-TW 直接 return，
  // 所以這個 bug 只有外語看得到，中文走查永遠測不出來。
  const feedbackPhotoLabel = $('#fbPhotoLabel');
  if (feedbackPhotoLabel) {
    [...feedbackPhotoLabel.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .forEach((node) => node.remove());
    feedbackPhotoLabel.insertBefore(
      document.createTextNode(muneaT('feedback.photoLabel', 'Add an image (optional)')),
      feedbackPhotoLabel.firstChild,
    );
  }
  setText('#fbPhotoLabel span', 'feedback.photoHint', 'Add a screenshot when words are not enough.');
  setDirectText('#fbPhotoAdd', 'feedback.choosePhoto', 'Choose an image');
  const feedbackText = $('#fbText');
  if (feedbackText) feedbackText.placeholder = muneaT(
    'feedback.placeholder',
    'Tell us what happened or what you would like Munea to add',
  );
  setText('#fbSend', 'feedback.submit', 'Send feedback');

  setText('#interestsModal h2', 'interests.title', 'Topics to talk about');
  setText('#interestsModal > .modal > .modal-sub', 'interests.subtitle', 'Choose topics that interest you. You can change them at any time.');
  setText('#interestsSave', 'interests.save', 'Save topics');

  setText('#safetyModal h2', 'safety.title', 'Safety notifications');
  setText('#safetyModal > .modal > .modal-sub', 'legacyUi.safetyDescription', 'Choose when selected family members should be notified. This is not real-time or medical-grade monitoring.');
  const safetyTriggers = [
    ['safety.triggerBloodPressure', 'Blood pressure is very high or low (above 180 or below 90)'],
    ['safety.triggerHeartRate', 'Heart rate is unusually fast or slow'],
    ['safety.triggerBloodOxygen', 'Blood oxygen is low (below 90%)'],
  ];
  $$('#safetyModal .safety-triggers li').forEach((item, index) => {
    const copy = safetyTriggers[index];
    if (copy) setDirectText(`#safetyModal .safety-triggers li:nth-child(${index + 1})`, copy[0], copy[1]);
  });
  const safetyFlow = $$('#safetyModal .sf-step > span');
  if (safetyFlow[0]) safetyFlow[0].textContent = muneaT(
    'safety.checkInFlow',
    '{companion} checks in with you first.',
    { companion: cname() },
  );
  if (safetyFlow[1]) safetyFlow[1].textContent = muneaT('legacyUi.safetyLog', 'Save the event and notify selected family members.');
  if (safetyFlow[2]) safetyFlow[2].textContent = muneaT('legacyUi.safetyEmergency', 'A contact can call or check on you. Contact local emergency services in an emergency.');
  setText('#safetySave', 'safety.save', 'Save safety settings');

  setText('#companionSheet h2', 'companion.settingsTitle', 'Companion');
  setText(
    '#companionSheet > .modal > .modal-sub',
    'companion.settingsIntro',
    'Choose a companion, then give them a name. Their appearance, voice, and personality follow the companion; your memories stay with you.',
  );
  setText('#companionSheet .companion-name-label', 'legacyUi.companionName', 'Name your companion');
  setText('#companionSheet .field-label', 'legacyUi.companionRole', 'Choose an AI companion');
  setAttribute('#companionNameInput', 'placeholder', 'companion.namePlaceholder', 'For example: Ningning, Mia, or Alex');

  setAttribute('#famManageBtn', 'aria-label', 'accessibility.manageFamily', 'Manage family members');
  setAttribute('#chatExit', 'aria-label', 'accessibility.closeChat', 'Close conversation and return home');
  setAttribute('#walkGoal', 'aria-label', 'activity.adjustGoal', 'Adjust step goal');
  setAttribute('#walkDue', 'aria-label', 'activity.deadlineDate', 'Challenge deadline date');
  setAttribute('#walkDueTime', 'aria-label', 'activity.deadlineTime', 'Challenge deadline time');
  setAttribute('#eventName', 'placeholder', 'activity.eventNamePlaceholder', 'For example: Family birthday dinner');
  setAttribute('#eventPlace', 'placeholder', 'activity.eventPlacePlaceholder', 'For example: A nearby restaurant or home');
  setAttribute('#voteQ', 'placeholder', 'activity.voteQuestionPlaceholder', 'For example: Where should we eat this weekend?');
  ['#vo1', '#vo2'].forEach((selector) => setAttribute(
    selector,
    'placeholder',
    'activity.voteOptionPlaceholder',
    'For example: A restaurant or home',
  ));
  setAttribute('#drawPrize', 'placeholder', 'activity.drawPrizePlaceholder', 'For example: Ice cream or a small treat');
  ['#rw1', '#rw2', '#rw3'].forEach((selector) => setAttribute(
    selector,
    'placeholder',
    'activity.rewardPlaceholder',
    'For example: A family meal or a small gift',
  ));
  [
    ['#reportClose', 'accessibility.back', 'Back'],
    ['#profileClose', 'profile.close', 'Close profile'],
    ['#famCircleClose', 'familyCircle.close', 'Close care circle'],
    ['#topUpClose', 'purchase.close', 'Close credit top-up'],
    ['#historyClose', 'history.close', 'Close records'],
  ].forEach(([selector, key, fallback]) => setAttribute(
    selector,
    'aria-label',
    key,
    fallback,
  ));
  setAttribute('#pfNick', 'placeholder', 'profile.familyNicknamePlaceholder', 'For example: Grandma');
  setAttribute('#joinCodeInput', 'placeholder', 'join.codePlaceholder', 'Enter invitation code');
  setAttribute('#visitTitle', 'placeholder', 'appointment.titlePlaceholder', 'For example: Cardiology follow-up');
  setAttribute('#npsSlider', 'aria-label', 'feedback.npsAria', 'Recommendation score from 0 to 10');
  const npsHints = $$('#fbNpsWrap .nps-hint span');
  if (npsHints[0]) npsHints[0].textContent = muneaT('feedback.npsZero', '0 · Not at all likely');
  if (npsHints[1]) npsHints[1].textContent = muneaT('feedback.npsTen', '10 · Very likely');

  setText('#subPlans > .sub-intro', 'subscription.benefitsIntro', 'Every paid plan includes');
  setDirectText('#pointsUnlockNotice', 'subscription.unlockCredits', 'Subscribe to Plus or Pro to buy credit packs.');
  const benefitKeys = [
    ['subscription.benefitVoiceTitle', 'Natural voice companionship', 'subscription.benefitVoiceBody', 'Talk naturally in a familiar language.'],
    ['subscription.benefitCareTitle', 'Everyday care', 'subscription.benefitCareBody', 'Companion reminders and daily records.'],
    ['subscription.benefitFamilyTitle', 'Family care circle', 'subscription.benefitFamilyBody', 'Helps family members stay informed and connected.'],
    ['subscription.benefitMemoryTitle', 'Continuing companion memory', 'subscription.benefitMemoryBody', 'Keeps important people and routines in context.'],
  ];
  $$('#subPlans .sub-value .sv-row').forEach((row, index) => {
    const keys = benefitKeys[index];
    if (!keys) return;
    const title = row.querySelector('.sv-txt b');
    const body = row.querySelector('.sv-txt small');
    if (title) title.textContent = muneaT(keys[0], keys[1]);
    if (body) body.textContent = muneaT(keys[2], keys[3]);
  });
  setText('#subPlans .sub-sec-label', 'subscription.choosePlan', 'Choose a plan');
  const cycleButtons = $$('#subCycle .scyc-btn');
  if (cycleButtons[0]) cycleButtons[0].textContent = muneaT('subscription.billingMonthly', 'Monthly');
  if (cycleButtons[1]) {
    const labelNode = [...cycleButtons[1].childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
    if (labelNode) labelNode.textContent = `${muneaT('subscription.billingYearly', 'Yearly')} `;
    const badge = cycleButtons[1].querySelector('.scyc-badge');
    if (badge) badge.textContent = muneaT('subscription.savePercent', 'Save {percent}%', { percent: 20 });
  }
  const creditRuleKeys = [
    ['subscription.monthlyCreditsTitle', 'Monthly plan credits', 'subscription.monthlyCreditsBody', 'Issued again each billing period.'],
    ['subscription.purchasedCreditsTitle', 'Purchased credits', 'subscription.purchasedCreditsBody', 'They do not expire.'],
    ['subscription.deductionOrderTitle', 'Credit order', 'subscription.deductionOrderBody', 'Monthly credits are used before purchased credits.'],
  ];
  $$('#subPlans .credit-rules .cr-row').forEach((row, index) => {
    const keys = creditRuleKeys[index];
    if (!keys) return;
    const title = row.querySelector('b');
    const body = row.querySelector('.cr-note');
    if (title) title.textContent = muneaT(keys[0], keys[1]);
    if (body) body.textContent = muneaT(keys[2], keys[3]);
  });
  localizePurchasePlanContent();
  $$('.tu-card').forEach((card) => {
    const credits = Number(card.dataset.p || 0);
    const formatted = new Intl.NumberFormat(muneaLocale()).format(credits);
    const amount = card.querySelector('b');
    const minutes = card.querySelector('.tu-min');
    if (amount) amount.textContent = muneaT('purchase.creditsAmount', '{credits} credits', { credits: formatted });
    if (minutes) minutes.textContent = muneaT('purchase.approxMinutes', 'About {minutes} minutes', { minutes: formatted });
  });

  const changelog = $('#changelogList');
  if (changelog) {
    changelog.replaceChildren();
    const summary = document.createElement('p');
    summary.className = 'modal-sub';
    summary.textContent = muneaT(
      'version.localizedSummary',
      'This update improves call status explanations, text fallback, and readability.',
    );
    changelog.appendChild(summary);
  }
  setText('#versionSheet h2', 'version.title', "What's new");
  const versionSubtitle = $('#versionSheet > .modal > .modal-sub');
  if (versionSubtitle && versionSubtitle.firstChild) {
    versionSubtitle.firstChild.textContent = `${muneaT('app.title', 'Munea')} `;
  }
  setText('#verClose', 'version.close', 'Got it');
}
let muneaRendererCopyCache = null;
function muneaRendererCopy() {
  if (muneaRendererCopyCache) return muneaRendererCopyCache;
  const api = window.MuneaAppRendererCopy;
  if (!api || typeof api.createAppRendererCopy !== 'function') return null;
  muneaRendererCopyCache = api.createAppRendererCopy({
    t: (key, values) => muneaT(key, key, values),
  });
  return muneaRendererCopyCache;
}
let muneaPurchaseFlowCache = null;
function muneaPurchaseFlow() {
  if (muneaPurchaseFlowCache) return muneaPurchaseFlowCache;
  const api = window.MuneaPurchaseFlow;
  if (!api || typeof api.createPurchaseFlow !== 'function') return null;
  muneaPurchaseFlowCache = api.createPurchaseFlow({
    t: (key, values) => muneaT(key, key, values),
  });
  return muneaPurchaseFlowCache;
}
function localizePurchasePlanContent() {
  const benefitsIntro = document.querySelector('#subPlans > .sub-intro');
  if (benefitsIntro) benefitsIntro.textContent = muneaT(
    'subscription.benefitsIntro',
    'Every paid plan includes',
  );
  const unlockNotice = $('#pointsUnlockNotice');
  if (unlockNotice) unlockNotice.textContent = muneaT(
    'subscription.unlockCredits',
    'Subscribe to Plus or Pro to buy credit packs.',
  );
  const benefitKeys = [
    ['subscription.benefitVoiceTitle', 'Natural voice companionship', 'subscription.benefitVoiceBody', 'Talk naturally in a familiar language.'],
    ['subscription.benefitCareTitle', 'Everyday care', 'subscription.benefitCareBody', 'Companion reminders and daily records.'],
    ['subscription.benefitFamilyTitle', 'Family care circle', 'subscription.benefitFamilyBody', 'Helps family members stay informed and connected.'],
    ['subscription.benefitMemoryTitle', 'Continuing companion memory', 'subscription.benefitMemoryBody', 'Keeps important people and routines in context.'],
  ];
  $$('#subPlans .sub-value .sv-row').forEach((row, index) => {
    const keys = benefitKeys[index];
    if (!keys) return;
    const title = row.querySelector('.sv-txt b');
    const body = row.querySelector('.sv-txt small');
    if (title) title.textContent = muneaT(keys[0], keys[1]);
    if (body) body.textContent = muneaT(keys[2], keys[3]);
  });
  const planLabel = $('#subPlans .sub-sec-label');
  if (planLabel) planLabel.textContent = muneaT('subscription.choosePlan', 'Choose a plan');
  const cycleButtons = $$('#subCycle .scyc-btn');
  if (cycleButtons[0]) cycleButtons[0].textContent = muneaT('subscription.billingMonthly', 'Monthly');
  if (cycleButtons[1]) {
    const labelNode = [...cycleButtons[1].childNodes].find((node) => node.nodeType === Node.TEXT_NODE);
    if (labelNode) labelNode.textContent = `${muneaT('subscription.billingYearly', 'Yearly')} `;
    const badge = cycleButtons[1].querySelector('.scyc-badge');
    if (badge) badge.textContent = muneaT('subscription.savePercent', 'Save {percent}%', { percent: 20 });
  }
  const creditRuleKeys = [
    ['subscription.monthlyCreditsTitle', 'Monthly plan credits', 'subscription.monthlyCreditsBody', 'Issued again each billing period.'],
    ['subscription.purchasedCreditsTitle', 'Purchased credits', 'subscription.purchasedCreditsBody', 'They do not expire.'],
    ['subscription.deductionOrderTitle', 'Credit order', 'subscription.deductionOrderBody', 'Monthly credits are used before purchased credits.'],
  ];
  $$('#subPlans .credit-rules .cr-row, #subPoints .credit-rules .cr-row').forEach((row, index) => {
    const keys = creditRuleKeys[index % creditRuleKeys.length];
    const title = row.querySelector('b');
    const body = row.querySelector('.cr-note');
    if (title) title.textContent = muneaT(keys[0], keys[1]);
    if (body) body.textContent = muneaT(keys[2], keys[3]);
  });
  const planCardFacts = {
    plus: {
      audienceKey: 'subscription.plusAudience',
      audienceFallback: 'For everyday voice companionship and essential family care',
      credits: 100,
      members: 4,
    },
    pro: {
      audienceKey: 'subscription.proAudience',
      audienceFallback: 'For more frequent companionship and advanced video interaction',
      credits: 200,
      members: 12,
    },
  };
  $$('#planPick .ppk').forEach((card) => {
    const facts = planCardFacts[card.dataset.t];
    if (!facts) return;
    const tag = card.querySelector('.ppk-tag');
    if (tag) tag.textContent = muneaT('subscription.mostPopular', 'Most popular');
    const audience = card.querySelector('.ppk-who');
    if (audience) audience.textContent = muneaT(facts.audienceKey, facts.audienceFallback);
    const features = card.querySelectorAll('.ppk-feats li');
    if (features[0]) features[0].textContent = muneaT(
      'subscription.monthlyVoiceCredits',
      '{credits} voice-companion credits each month. Unused monthly credits do not roll over.',
      { credits: facts.credits },
    );
    if (features[1]) features[1].textContent = muneaT(
      'subscription.healthTrendAccess',
      'Full 7-day and 30-day health trends',
    );
    if (features[2]) features[2].textContent = muneaT(
      'subscription.familyMemberLimit',
      'Up to {members} people in the family care circle',
      { members: facts.members },
    );
  });
  const creditIntro = document.querySelector('#subPoints > .sub-fine');
  if (creditIntro) creditIntro.textContent = muneaT(
    'subscription.creditsUsageIntro',
    'Conversations use credits. Add more credits to keep talking when they run out.',
  );
  const legalTerms = $('#legalTermsLink');
  const legalPrivacy = $('#legalPrivacyLink');
  const legalLine = $('#subPlans .sub-legal');
  if (legalLine && legalTerms && legalPrivacy) {
    [...legalLine.childNodes]
      .filter((node) => node.nodeType === Node.TEXT_NODE)
      .forEach((node) => node.remove());
    legalTerms.textContent = muneaT('reader.termsTitle', 'Terms of Service');
    legalPrivacy.textContent = muneaT('reader.privacyTitle', 'Privacy Policy');
    legalLine.insertBefore(
      document.createTextNode(`${muneaT(
        'subscription.renewalDisclosure',
        'Subscriptions renew automatically through your Apple Account. Manage or cancel in iPhone Settings; access continues through the current billing period. Purchased credits do not expire. See',
      )} `),
      legalTerms,
    );
    legalLine.insertBefore(
      document.createTextNode(` ${muneaT('subscription.legalAnd', 'and')} `),
      legalPrivacy,
    );
    legalLine.appendChild(document.createTextNode(muneaT('subscription.legalPeriod', '.')));
  }
  $$('.tu-card').forEach((card) => {
    const credits = Number(card.dataset.p || 0);
    const formatted = new Intl.NumberFormat(muneaLocale()).format(credits);
    const amount = card.querySelector('b');
    const minutes = card.querySelector('.tu-min');
    if (amount) amount.textContent = muneaT('purchase.creditsAmount', '{credits} credits', { credits: formatted });
    if (minutes) minutes.textContent = muneaT('purchase.approxMinutes', 'About {minutes} minutes', { minutes: formatted });
  });
  const manage = $('#planCancelBtn');
  if (manage) manage.textContent = muneaT('purchase.manageSubscription', 'Manage subscription');
  const restore = $('#restoreBtn');
  if (restore) restore.textContent = muneaT('purchase.restore', 'Restore purchases');
}

// 這句話「像不像使用者真的說出口的話」——判準跟著他當下的語系走（Edward 2026-07-31 拍板）
//
// 為什麼不能一套標準管四國：台灣的長輩不會突然冒出韓文，出現韓文＝語音聽錯了、必須擋
// （7/14 事故就是「アラ」混在中文裡、被比例式守門放行）；但日文版看到假名是天經地義的，
// 同一套標準會把日本用戶的正常句子整批擋在門外——那不是防雜訊，那是讓功能對外國人全滅。
//
// 夾雜英文一律放行：長輩會說「我去看 doctor」「血壓 OK」，那是正常說法不是雜訊；
// 舊版「連續 3 個英文字母就擋」連這種話都擋，是只有中文時期的權宜寫法。
const MUNEA_SPEECH_RULES = {
  // local＝這個語系的本命字；alien＝一出現就代表聽錯了的字；minUnique＝字元重複到什麼程度算雜訊
  // 拉丁語系的 minUnique 必須放低：字母只有 26 個，長句本來就一直重複，用中文的 0.5 會誤殺整句英文
  'zh-TW': { local: /[一-龥]/, alien: /[぀-ヿ가-힣Ѐ-ӿ]/, minUnique: 0.5 },
  ja: { local: /[぀-ヿ一-龥]/, alien: /[가-힣Ѐ-ӿㄅ-ㄪ]/, minUnique: 0.45 },
  en: { local: /[A-Za-z]/, alien: /[぀-ヿ가-힣Ѐ-ӿ一-龥ㄅ-ㄪ]/, minUnique: 0.22 },
  es: { local: /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/, alien: /[぀-ヿ가-힣Ѐ-ӿ一-龥ㄅ-ㄪ]/, minUnique: 0.22 },
};
function muneaSpeechRule(locale) {
  return MUNEA_SPEECH_RULES[locale || muneaLocale()] || MUNEA_SPEECH_RULES['zh-TW'];
}
function muneaIsCleanSpeechText(raw, locale) {
  const s = String(raw == null ? '' : raw).replace(/\s+/g, '');
  if (!s) return false;
  const rule = muneaSpeechRule(locale);
  if (rule.alien.test(s)) return false;         // 別的語系的字冒出來＝聽錯了（7/14 事故那道防線，逐語系保留）
  if (/(.)\1{4,}/.test(s)) return false;        // 同一個字連著出現 5 次以上＝雜訊，跟語言無關
  // 算比例前先扣掉標點與符號，否則「血壓 OK！」的驚嘆號會稀釋掉本命字
  const meaningful = s.replace(/[\p{P}\p{S}\p{Z}\p{M}]/gu, '');
  if (!meaningful) return false;
  const chars = [...meaningful];
  let localCount = 0, latinCount = 0, digitCount = 0;
  chars.forEach(c => {
    if (rule.local.test(c)) localCount += 1;
    if (/[A-Za-z]/.test(c)) latinCount += 1;
    if (/\d/.test(c)) digitCount += 1;
  });
  if (!localCount) return false;                                       // 一個本命字都沒有＝這不是他在講的語言
  if ((localCount + latinCount + digitCount) / chars.length < 0.9) return false;  // 其餘都是不明字元＝雜訊
  if (localCount / chars.length < 0.3) return false;                   // 夾字可以，但不能反客為主
  if (new Set(s).size / s.length < rule.minUnique) return false;
  return true;
}
function muneaIsCleanDisplayText(raw) {
  const s = String(raw == null ? '' : raw).trim();
  if (!s || s.length > 160) return false;
  if (/[\u0000-\u001f\u007f\ufffd<>]/u.test(s)) return false;
  if (/[\u202a-\u202e\u2066-\u2069]/u.test(s)) return false;
  if (/(?:javascript|data)\s*:|https?:\/\//iu.test(s)) return false;
  const meaningful = s.replace(/[\p{P}\p{S}\p{Z}\p{M}]/gu, '');
  if (!meaningful || !/[\p{L}\p{N}]/u.test(meaningful)) return false;
  const characters = [...meaningful.toLocaleLowerCase(muneaLocale())];
  if (characters.length >= 6 && new Set(characters).size / characters.length < 0.35) return false;
  return true;
}
// 顯示前再守一次門（Edward 2026-07-15 事故：首頁招呼卡以外，用藥/看診/留意卡都還在印未過濾的存檔文字）
// 存檔時就算漏接、或手機裡已經存著舊的髒資料，畫面上都不該印出來——不乾淨就退回 fallback，不留原文
function muneaSafeDisplayText(raw, fallback) {
  const s = String(raw == null ? '' : raw).trim();
  if (!s) return fallback;
  return muneaIsCleanDisplayText(s) ? s : fallback;
}
// 頭像底色的唯一清單——這八個色號在 styles.css 裡真的存在。
// 以前分配顏色的地方寫了 p-ma / p-ba / p-jie 這種 CSS 沒有的名字，
// 套上去等於沒有顏色；集中成一份之後，色號寫錯就會在同一個地方被抓到。
// p-me 不在裡面：那是「本人」專用，借給家人會讓兩個人看起來是同一個。
const MUNEA_AVA_TINTS = ['p-ama', 'p-zhi', 'p-bao', 'p-lin', 'p-hai', 'p-ye', 'p-mo', 'p-mei'];
function muneaSafeTint(tint, seedName) {
  if (MUNEA_AVA_TINTS.indexOf(tint) >= 0) return tint;
  const key = String(seedName || '');
  let sum = 0;
  for (let i = 0; i < key.length; i += 1) sum = (sum * 31 + key.charCodeAt(i)) % 9973;
  return MUNEA_AVA_TINTS[sum % MUNEA_AVA_TINTS.length];
}
// 一份名單一起配色，保證同一家人不會兩個人同色。
// 各自去算的話會撞（用名字算出來的顏色本來就可能相同），而家人是一起出現在同一排的——
// 兩個一樣的圓圈看起來就是同一個人。本人（self）永遠留著自己的顏色不參與輪替。
function muneaAssignTints(list) {
  const used = new Set();
  (list || []).forEach(m => { if (m && m.self && m.tint) used.add(m.tint); });
  return (list || []).map((m, i) => {
    if (!m || m.self) return m;
    let t = MUNEA_AVA_TINTS.indexOf(m.tint) >= 0 ? m.tint : '';
    if (!t || used.has(t)) t = MUNEA_AVA_TINTS.find(x => !used.has(x)) || MUNEA_AVA_TINTS[i % MUNEA_AVA_TINTS.length];
    used.add(t);
    return Object.assign({}, m, { tint: t });
  });
}
function muneaEscapeHtml(raw) {
  return String(raw == null ? '' : raw).replace(/[&<>"']/g, character => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

const OVERLAYS = ['med', 'connect', 'chat'];
const AVATAR_ENGINE_MODES = Object.freeze({
  STATIC_CSS: 'static-css',
  TWO_D_VISEME: '2d-viseme',
  DITTO: 'ditto',
  LIVE_AVATAR: 'liveavatar',
});
const VOICE_PROVIDER_MODES = Object.freeze({
  STATIC_FALLBACK: 'static-fallback',
  STT_CHAT_TTS: 'stt-chat-tts',
  GEMINI_LIVE: 'gemini-live',
  INTERACTIONS: 'interactions',
});
const TWO_D_AVATARS = new Set(['munea-2d-xiaoyun', 'munea-2d-ayuan', 'munea-2d-mimi', 'munea-2d-wangcai']);

/* ===== [ENGINE] 角色模板 vs 使用者命名：模板決定外觀/聲音/人格，名字由使用者取 ===== */
const CompanionProfile = window.MuneaCompanionProfile;
const CHARACTER_TEMPLATES = CompanionProfile.templates;
let savedCompanionProfile = CompanionProfile.loadProfile();
let currentAvatarId = savedCompanionProfile.templateId;
let companionDisplayName = savedCompanionProfile.displayName;
let companionNameTouched = savedCompanionProfile.nameTouched;
// 動物角色（咪咪/旺財）先下架（Edward 2026-07-09：擬真臉引擎做不了卡通動物）——選過的自動回「溫柔型」寧寧、不留半殘狀態
const REMOVED_AVATARS = new Set(['munea-2d-mimi', 'munea-2d-wangcai', 'munea-2d-xiaoyun', 'munea-2d-ayuan']);   // V1 只留兩位擬真真人（Edward 2026-07-10）
if (REMOVED_AVATARS.has(currentAvatarId)) {
  currentAvatarId = 'nening-real-female';
  savedCompanionProfile.templateId = currentAvatarId;
  if (['咪咪', '旺財', '小昀', '阿原'].indexOf((companionDisplayName || '').trim()) >= 0) { companionDisplayName = '寧寧'; companionNameTouched = false; }
}
let currentChar = CompanionProfile.templateFor(currentAvatarId).backendChar; // 後端角色模板，決定腦＋聲音
let chatHistory = [];            // 多輪對話脈絡
let chatOpened = false;          // 這次進聊聊她有沒有先開過口
let chatAudio = null;
let companionBackendSyncing = false;
let accountBootstrapPromise = null;
let latestTrustedLocaleContext = null;
let activeChatSessionId = null;
let activeChatStartedAt = 0;
let activeChatTurnCount = 0;
let latestAiContext = null;
let latestAiContextSource = 'not loaded';
let latestRelationshipState = null;
const ACCOUNT_BOOTSTRAP_KEY = 'munea.accountBootstrapped.v1';
const ACCOUNT_BOOTSTRAP_USER_KEY = 'munea.accountBootstrappedUser.v1';
const ONBOARDING_COMPLETED_KEY = 'munea.onboardingCompleted.v1';
const AI_PROVIDER_CONSENT_KEY = 'munea.aiProviderConsent.v1';
const AI_PROVIDER_CONSENT_VERSION = '2026-07-02-ai-provider-v1';
const DEV_FIXTURE_MARKER_KEY = 'munea.developmentFixtures.v1';
// 開帳與個人資料重整（2026-07-24）：首登一次性彈個人資料卡的旗標——填了或跳過都算「問過」，
// 之後永不再自動彈；跳過者靠首頁「幫你留意」裡的一則提醒（見 syncProfileNudge）自己回來補。
// 2026-07-28 Edward 拍板：原本的獨立小卡＋關閉 X 整組退役，改收進留意卡輪播——
// 輪播 5.2 秒自己轉走＝天生不強迫，不需要 X（舊 X 被樣式蓋住等於沒用，是這次的起因）。
const PERSON_PROFILE_PROMPT_KEY = 'munea.personProfilePrompted.v1';

/* ===== AvatarRuntime：先把即時 avatar 的共用合約立起來 =====
 * mode=static-css 先用靜態圖 + CSS 呼吸/眨眼/聲波；之後 Ditto / LiveAvatar 只要接這層。 */
let speakTimer = null;
let visemeTimer = null;
let avatarSession = null;
const avatarRuntime = {
  modes: AVATAR_ENGINE_MODES,
  mode: AVATAR_ENGINE_MODES.STATIC_CSS,
  decision: null,
  state: 'idle',
  viseme: 'rest',
  character: currentChar,
  resolveMode(avatarId = currentAvatarId) {
    const forced = new URLSearchParams(location.search).get('avatar');
    if (forced === '2d') return AVATAR_ENGINE_MODES.TWO_D_VISEME;
    if (forced === 'static') return AVATAR_ENGINE_MODES.STATIC_CSS;
    if (Object.values(AVATAR_ENGINE_MODES).includes(forced)) return forced;
    return TWO_D_AVATARS.has(avatarId) ? AVATAR_ENGINE_MODES.TWO_D_VISEME : AVATAR_ENGINE_MODES.STATIC_CSS;
  },
  setMode(mode) {
    const valid = Object.values(AVATAR_ENGINE_MODES).includes(mode);
    this.mode = valid ? mode : AVATAR_ENGINE_MODES.STATIC_CSS;
    const sc = $('#chat');
    if (sc) sc.dataset.avatarMode = this.mode;
  },
  setDecision(decision) {
    this.decision = decision || null;
    if (this.decision && this.decision.selectedMode) this.setMode(this.decision.selectedMode);
  },
  setViseme(shape) {
    this.viseme = shape || 'rest';
    const sc = $('#chat');
    if (sc) sc.dataset.avatarViseme = this.viseme;
  },
  setState(st) {
    this.state = st;
    const sc = $('#chat');
    if (sc) {
      sc.dataset.state = st;
      sc.dataset.avatarMode = this.mode;
      sc.dataset.avatarViseme = this.viseme;
    }
    if (st !== 'speaking') this.stopMockViseme();
  },
  setCharacter(name, avatarId) {
    this.character = name;
    if (avatarId) currentAvatarId = avatarId;
    this.setMode(this.resolveMode(avatarId));
    this.setViseme('rest');
    const nm = $('#chatName'); if (nm) nm.textContent = name;
    const fimg = $('#faceImg');
    if (fimg && avatarId) {
      const template = templateFor(avatarId);
      fimg.src = template.fullAsset || template.homeAsset || template.thumbAsset || ('avatars/' + avatarId + '.png');
      fimg.classList.toggle('sq', !template.fullAsset);
    }
  },
  startMockViseme(ms) {
    this.stopMockViseme();
    if (this.mode !== AVATAR_ENGINE_MODES.TWO_D_VISEME) return;
    const shapes = ['open', 'wide', 'round', 'smile', 'open', 'rest'];
    let i = 0;
    this.setViseme(shapes[i]);
    visemeTimer = setInterval(() => {
      i = (i + 1) % shapes.length;
      this.setViseme(shapes[i]);
    }, 120);
    setTimeout(() => this.stopMockViseme(), ms);
  },
  // 真語音通話的嘴型：跟著她「實際的聲音大小」動（有聲音才動嘴、停頓就合嘴）— Edward 7/9 六角色全 avatar
  startLiveViseme(getLevel) {
    this.stopMockViseme();
    if (this.mode !== AVATAR_ENGINE_MODES.TWO_D_VISEME) return;
    const shapes = ['open', 'wide', 'round', 'smile'];
    let i = 0;
    visemeTimer = setInterval(() => {
      const lv = Math.max(0, Math.min(1, getLevel ? (getLevel() || 0) : 0));
      if (lv > 0.05) { i = (i + 1) % shapes.length; this.setViseme(shapes[i]); }
      else this.setViseme('rest');
    }, 110);
  },
  stopMockViseme() {
    clearInterval(visemeTimer);
    visemeTimer = null;
    this.setViseme('rest');
  },
  speak(text, audioMs = 0) {
    this.setState('speaking');
    clearTimeout(speakTimer);
    const ms = audioMs || Math.min(8000, Math.max(2200, (text ? text.length : 8) * 165));
    this.startMockViseme(ms);
    speakTimer = setTimeout(() => {
      if (this.state === 'speaking') {
        this.setState('idle');
        setLocalizedCallHint('ready');
      }
    }, ms);
    return ms;
  },
  onAudioEnd() {
    if (this.state === 'speaking') {
      this.setState('idle');
      setLocalizedCallHint('ready');
    }
  },
};
window.MuneaAvatarRuntime = avatarRuntime;

function setFaceState(st) { avatarRuntime.setState(st); }
function faceSpeak(text, audioMs = 0) {
  const ms = avatarRuntime.speak(text, audioMs);
  recordAvatarUsage(text, ms);
  return ms;
}
function setCallHint(text, busy) {
  const cap = $('#chatCaption');
  if (cap) { cap.textContent = text; cap.classList.toggle('cap-busy', !!busy); }
}
function setLocalizedCallHint(state, busy = false) {
  const rendererCopy = muneaRendererCopy();
  const fallbackKeys = {
    connecting: 'voice.connecting',
    developerConnecting: 'voice.call.developerConnecting',
    developerReady: 'voice.call.developerReady',
    firstWarmup: 'voice.call.firstWarmup',
    idleEnded: 'voice.call.idleEnded',
    idleWarning: 'voice.call.idleWarning',
    openingWarmup: 'voice.call.openingWarmup',
    ready: 'voice.ready',
    speaking: 'voice.call.speaking',
    unavailable: 'voice.call.unavailable',
  };
  const text = rendererCopy
    ? rendererCopy.callHint(state)
    : muneaT(fallbackKeys[state] || fallbackKeys.unavailable, '');
  setCallHint(text, busy);
}
const VOICE_RUNTIME_KEYS = Object.freeze({
  audioOnlyFallback: 'voice.runtime.audioOnlyFallback',
  degradedBody: 'voice.runtime.degradedBody',
  degradedTitle: 'voice.runtime.degradedTitle',
  didNotHear: 'voice.runtime.didNotHear',
  heard: 'voice.runtime.heard',
  listening: 'voice.runtime.listening',
  microphoneMuted: 'voice.runtime.microphoneMuted',
  microphoneMutedHint: 'voice.runtime.microphoneMutedHint',
  microphonePermission: 'voice.runtime.microphonePermission',
  microphoneTapToResume: 'voice.runtime.microphoneTapToResume',
  playbackBlocked: 'voice.runtime.playbackBlocked',
  recordingTapWhenDone: 'voice.runtime.recordingTapWhenDone',
  reconnecting: 'voice.runtime.reconnecting',
  recoveredBody: 'voice.runtime.recoveredBody',
  recoveredTitle: 'voice.runtime.recoveredTitle',
  thinking: 'voice.runtime.thinking',
});
function voiceRuntimeCopy(state) {
  const rendererCopy = muneaRendererCopy();
  if (rendererCopy && typeof rendererCopy.voiceRuntimeText === 'function') {
    return rendererCopy.voiceRuntimeText(state);
  }
  return muneaT(VOICE_RUNTIME_KEYS[state] || VOICE_RUNTIME_KEYS.reconnecting, '');
}
function setLocalizedRuntimeHint(state, busy = false) {
  setCallHint(voiceRuntimeCopy(state), busy);
}
function setLocalizedRuntimeCaption(state) {
  const rendererCopy = muneaRendererCopy();
  if (rendererCopy && typeof rendererCopy.voiceRuntimeCaption === 'function') {
    const caption = rendererCopy.voiceRuntimeCaption(state);
    setCaption(caption.title, caption.body);
    return;
  }
  if (state === 'recovered') {
    setCaption(voiceRuntimeCopy('recoveredTitle'), voiceRuntimeCopy('recoveredBody'));
    return;
  }
  setCaption(voiceRuntimeCopy('degradedTitle'), voiceRuntimeCopy('degradedBody'));
}
// 通話狀態卡（2026-07-23 排隊／全滿 → 2026-07-24 Edward 拍板 P0 擴成通用失敗卡）：
// 單行字幕（#chatCaption）已退役被 CSS 藏起來，setCallHint 在聊聊頁實際上看不到——
// 忙線／失敗都必須有自己看得懂的卡，不能只靠一句藏起來的字幕當「有講過」。
// mode: 'queued'（payload=queue 物件 {position, eta_s}）｜ 'full'（連排隊位子都滿，附「先用文字聊」出口）
function showBusyCard(mode, payload) {
  const card = $('#busyCard'); if (!card) return;
  card.dataset.mode = mode;
  const title = $('#busyCardTitle'), pos = $('#busyCardPos'), note = $('#busyCardNote'), btn = $('#busyCardBtn'), alt = $('#busyCardAlt');
  const rendererCopy = muneaRendererCopy();
  if (rendererCopy) {
    const q = payload || {};
    const localized = rendererCopy.queueCard({
      companion: cname(),
      etaSeconds: q.eta_s,
      mode,
      position: q.position,
    });
    card.dataset.action = localized.action;
    if (title) title.textContent = localized.title;
    if (pos) pos.textContent = localized.position;
    if (note) note.textContent = localized.note;
    if (btn) btn.textContent = localized.button;
    if (alt) alt.hidden = !localized.showTextFallback;
    card.hidden = false;
    return;
  }
  if (mode === 'queued') {
    card.dataset.action = 'cancel';
    if (alt) alt.hidden = true;
    const q = payload || {};
    const position = Math.max(1, parseInt(q.position, 10) || 1);
    const preparing = position <= 1;   // 排第 1 位＝其實是在幫你準備、不是真的一堆人在排（Edward 2026-07-24 拍板）
    const eta = formatQueueEta(q.eta_s);
    if (title) title.textContent = preparing
      ? muneaT('voice.queue.preparingWithCompanion', '{companion}正在為你準備聊天室', { companion: cname() })
      : muneaT('voice.queue.busyWithCompanion', '現在比較多人在跟{companion}聊天', { companion: cname() });
    if (pos) pos.textContent = preparing
      ? ''
      : muneaT('voice.queue.position', '你排第 {count} 位', { count: position });
    let etaLine;
    if (eta === 'soon') {
      etaLine = preparing
        ? muneaT('voice.queue.etaPreparingSoon', '快好了，通常幾分鐘內就會自動接通。')
        : muneaT('voice.queue.etaWaitingSoon', '快好了，很快就輪到你。');
    } else if (typeof eta === 'number') {
      etaLine = preparing
        ? muneaT('voice.queue.etaPreparingMinutes', '大約再 {minutes} 分鐘會自動接通。', { minutes: eta })
        : muneaT('voice.queue.etaWaitingMinutes', '大約再 {minutes} 分鐘會輪到你。', { minutes: eta });
    } else {
      etaLine = preparing
        ? muneaT('voice.queue.etaPreparingUnknown', '通常幾分鐘內就好，準備好會自動接通。')
        : muneaT('voice.queue.etaWaitingUnknown', '輪到你會自動接通。');
    }
    if (note) note.textContent = muneaT(
      'voice.queue.note',
      '{eta}排隊不扣點數，暫時先別關掉這個畫面；準備好就會自動接通。',
      { eta: etaLine },
    );
    if (btn) btn.textContent = muneaT('voice.queue.cancel', '取消排隊');
  } else {
    // 'full'：連排隊的位子都滿了——除了「知道了」，多給一個不用等 GPU 席位的出口
    card.dataset.action = 'dismiss';
    if (title) title.textContent = muneaT('voice.queue.fullTitle', '現在忙線中');
    if (pos) pos.textContent = '';
    if (note) note.textContent = muneaT(
      'voice.queue.fullBody',
      '想跟{companion}聊天的人比較多，請稍後再試試看。',
      { companion: cname() },
    );
    if (btn) btn.textContent = muneaT('common.okay', '知道了');
    if (alt) alt.hidden = false;
  }
  card.hidden = false;
}
// 排隊等待時間人話化（2026-07-24 P0）：後端 queue.eta_s 一直都有算、前端過去只讀 position 把它丟掉。
// 不給精確倒數（會顯得像在說謊）——只給粗略區間：快好了 / 大約幾分鐘 / 太久或缺值就不顯示數字。
function formatQueueEta(etaS) {
  const n = Number(etaS);
  if (!Number.isFinite(n) || n <= 0) return null;
  if (n < 90) return 'soon';
  if (n <= 600) return Math.ceil(n / 60);   // 10 分鐘內才給概數，且無條件進位（寧可講久一點、不要讓人覺得被騙）
  return null;   // 超過 10 分鐘或算不出來：只講準備／排隊敘事，不亂猜數字
}
function hideBusyCard() { const card = $('#busyCard'); if (card) card.hidden = true; }
// 通用失敗卡（2026-07-24 Edward 拍板 P0）：登入失效／帳號未就緒／服務設定異常／暖機超時／
// 斷線重連失敗／連線逾時／拿不到麥克風——這些過去全部只寫進被藏起來的 #chatCaption，使用者等於零回饋。
// 現在一律借 busyCard 的殼：標題講人話原因＋一句怎麼辦＋一顆按鈕。
function showCallStatusCard(stateOrOptions) {
  const rendererCopy = muneaRendererCopy();
  const opts = typeof stateOrOptions === 'string'
    ? (rendererCopy
      ? rendererCopy.callStatus(stateOrOptions)
      : {
        action: 'dismiss',
        btnText: muneaT('common.okay', ''),
        note: muneaT('voice.call.retryLater', ''),
        title: muneaT('voice.call.unavailable', ''),
      })
    : (stateOrOptions || {});
  const card = $('#busyCard'); if (!card) return;
  card.dataset.mode = 'error';
  card.dataset.action = opts.action || 'dismiss';
  const title = $('#busyCardTitle'), pos = $('#busyCardPos'), note = $('#busyCardNote'), btn = $('#busyCardBtn'), alt = $('#busyCardAlt');
  if (title) title.textContent = opts.title || muneaT('voice.call.unavailable', '');
  if (pos) pos.textContent = '';
  if (note) note.textContent = opts.note || muneaT('voice.call.retryLater', '');
  if (btn) btn.textContent = opts.button || opts.btnText || muneaT('common.okay', '');
  if (alt) alt.hidden = true;
  card.hidden = false;
}
// ===== 全滿出口：先用文字聊（2026-07-24 Edward 拍板 P0）=====
// Avatar／即時語音兩個 GPU 席位滿了時，不用讓長輩乾等排隊——直接借既有文字聊天管線（window.__chatSay，
// 內部就是 init() 裡的 chatHandle／voiceProvider.sendText）繼續聊，這條路本來就不吃 Avatar／Voice 席位，
// 也不用排隊。別新造頁面，只在通話畫面裡疊一塊簡單的文字面板，讀「打字」不讀「說話」。
// （這幾個函式放頂層 scope，是因為 connectCall() 本身也是頂層函式，需要在真的要撥號前呼叫
// exitTextFallbackChat() 收掉面板——放進 init() 裡面 connectCall 會拿不到。）
function appendTextChatBubble(role, text) {
  const log = $('#textChatLog'); if (!log || !text) return;
  const row = document.createElement('div');
  row.className = 'tc-row ' + (role === 'user' ? 'tc-user' : 'tc-ai');
  row.textContent = text;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}
function startTextFallbackChat() {
  const panel = $('#textChatPanel'); if (!panel) return;
  chatOpened = true;
  activeChatSessionId = makeSessionId('text');
  activeChatStartedAt = Date.now();
  activeChatTurnCount = 0;
  panel.hidden = false;
  const inp = $('#textChatInput'); if (inp) { inp.value = ''; inp.focus(); }
  try { trackProductEvent('call_full_text_fallback_started', {}); } catch (e) {}
}
function exitTextFallbackChat() {
  const panel = $('#textChatPanel');
  if (panel && !panel.hidden) {
    panel.hidden = true;
    if (chatOpened) { try { trackProductEvent('call_full_text_fallback_ended', { turnCount: activeChatTurnCount }); } catch (e) {} }
    chatOpened = false;
  }
}
async function sendTextFallbackMessage() {
  const input = $('#textChatInput'); const sendBtn = $('#textChatSend');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendTextChatBubble('user', text);
  setBtnBusy(sendBtn, muneaT('common.sending', ''));
  const beforeLen = chatHistory.length;
  try {
    await window.__chatSay(text);   // init() 裡掛出來的 chatHandle 橋（chatHandle 本身是 init() 內部函式，拿不到）
  } finally {
    clearBtnBusy(sendBtn, muneaT('textChat.send', ''));
    if (input) input.focus();
  }
  // chatHandle 內部會把新的一輪對話（含 AI 回覆）推進 chatHistory；掃新增的區段找出「她」的回覆貼上面板。
  for (let i = beforeLen; i < chatHistory.length; i++) {
    if (chatHistory[i] && chatHistory[i].role === 'model') appendTextChatBubble('ai', chatHistory[i].text);
  }
}
// 等待中按鈕：加轉圈、鎖點擊（Edward 7/8：Loading 要有動態，不然像當機）
function setBtnBusy(b, text) {
  if (!b) return;
  if (!b.dataset.idleText) b.dataset.idleText = b.textContent;
  b.disabled = true; b.classList.add('busy-spin');
  if (text) b.textContent = text;
}
function clearBtnBusy(b, text) {
  if (!b) return;
  b.disabled = false; b.classList.remove('busy-spin');
  b.textContent = text || b.dataset.idleText || b.textContent;
  delete b.dataset.idleText;
}
function templateFor(avatarId = currentAvatarId) {
  return CompanionProfile.templateFor(avatarId);
}
function persistCompanionProfile() {
  savedCompanionProfile = CompanionProfile.saveProfile({
    templateId: currentAvatarId,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    nameTouched: companionNameTouched,
  });
}
function isStaticPreview() {
  return location.port === '8135' || location.protocol === 'file:';
}
async function muneaAuthHeaders(base = {}) {
  const headers = { ...base };
  const auth = window.MuneaAuth;
  if (auth && typeof auth.getAccessToken === 'function') {
    const token = await auth.getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // 薄門通行碼：管家腦雲端開門後靠它擋陌生流量（App 自動帶、用戶無感；本機沒設門=帶了也無妨）
  try { if (typeof MUNEA_APP_KEY === 'string' && MUNEA_APP_KEY) headers['X-Munea-Key'] = MUNEA_APP_KEY; } catch (e) {}
  return headers;
}
async function companionProfileApi(action, profile) {
  if (isStaticPreview()) return null;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 2500);
  try {
    const r = await fetch(brainURL('/companion-profile'), {
      method: 'POST',
      headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ action, profile }),
      signal: ctrl.signal,
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) {
    return null;
  } finally {
    clearTimeout(to);
  }
}
function applyCompanionProfile(profile, options = {}) {
  const normalized = CompanionProfile.normalizeProfile(profile);
  currentAvatarId = normalized.templateId;
  companionDisplayName = normalized.displayName;
  companionNameTouched = normalized.nameTouched;
  currentChar = templateFor(currentAvatarId).backendChar;
  if (options.persist !== false) persistCompanionProfile();
  syncCompanionUI();
}
async function loadCompanionProfileFromBackend() {
  const r = await companionProfileApi('load');
  if (r && r.ok && r.profile) applyCompanionProfile(r.profile);
}
async function saveCompanionProfileToBackend() {
  if (companionBackendSyncing) return;
  companionBackendSyncing = true;
  try {
    await companionProfileApi('save', savedCompanionProfile);
  } finally {
    companionBackendSyncing = false;
  }
}
function storageGet(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch (e) {}
}
function readAiProviderConsent() {
  try {
    const raw = localStorage.getItem(AI_PROVIDER_CONSENT_KEY);
    if (!raw) return { agreed: false, version: AI_PROVIDER_CONSENT_VERSION };
    const parsed = JSON.parse(raw);
    return {
      agreed: parsed && parsed.agreed === true,
      version: parsed && parsed.version ? parsed.version : AI_PROVIDER_CONSENT_VERSION,
      agreedAt: parsed && parsed.agreedAt ? parsed.agreedAt : '',
      source: parsed && parsed.source ? parsed.source : 'unknown',
    };
  } catch (e) {
    return { agreed: false, version: AI_PROVIDER_CONSENT_VERSION };
  }
}
function saveAiProviderConsent(agreed, source = 'settings') {
  const payload = {
    agreed: agreed === true,
    version: AI_PROVIDER_CONSENT_VERSION,
    source,
    agreedAt: agreed === true ? new Date().toISOString() : '',
    updatedAt: new Date().toISOString(),
  };
  storageSet(AI_PROVIDER_CONSENT_KEY, JSON.stringify(payload));
  updateAiProviderConsentUI();
  trackProductEvent('ai_provider_consent_updated', {
    agreed: payload.agreed,
    source,
    consentVersion: AI_PROVIDER_CONSENT_VERSION,
  });
  return payload;
}
function updateAiProviderConsentUI() {
  const consent = readAiProviderConsent();
  window.MuneaAiProviderConsentState = consent;
}
function setupAiProviderConsentControls() {
  updateAiProviderConsentUI();
}
window.MuneaAiProviderConsent = {
  key: AI_PROVIDER_CONSENT_KEY,
  version: AI_PROVIDER_CONSENT_VERSION,
  read: readAiProviderConsent,
  save: saveAiProviderConsent,
};
function currentAuthUserId() {
  const auth = window.MuneaAuth || {};
  if (typeof auth.state === 'function') {
    const state = auth.state() || {};
    if (state.authUserId || state.userId) return state.authUserId || state.userId;
  }
  const user = auth.user || auth.currentUser || {};
  return auth.userId || auth.authUserId || user.id || user.userId || null;
}
function muneaDeviceTimeZone() {
  try {
    const tz = (Intl.DateTimeFormat().resolvedOptions().timeZone || '').trim();
    if (tz) return tz;
  } catch (e) {}
  return 'Asia/Taipei';
}
function accountBootstrapPayload(action = 'create', extra = {}) {
  const authUserId = currentAuthUserId();
  const payload = {
    action,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    companionProfile: savedCompanionProfile,
    locale: muneaLocale(),
    // 手機真正的時區——不再寫死台北。這是後端唯一能知道「這個人在哪一國」的訊號，
    // 急難號碼靠它決定（2026-08-01：寫死台北會讓西班牙／美國／日本使用者被叫去打
    // 台灣的 119 跟 1925）。App 內其他地方（吃藥提醒、推播）本來就是這樣讀的，
    // 只有帳號建立這裡漏了。讀不到就退回台北，跟那些地方一致。
    timezone: muneaDeviceTimeZone(),
    preferredLanguages: muneaPreferredLanguages(),
    source: 'web-prototype',
    ...extra,
  };
  if (authUserId) payload.authUserId = authUserId;
  return payload;
}
function captureTrustedLocaleContext(response) {
  const account = response && response.store && response.store.account;
  const context = account && account.localeContext;
  if (!context || typeof context !== 'object' || Array.isArray(context)) return;
  latestTrustedLocaleContext = Object.freeze({ ...context });
}
async function syncAccountBootstrap(action = 'create', extra = {}) {
  // Only the fixture/direct-call profile skips cloud account creation. The
  // Gateway QA profile is still a real Supabase user and must be bootstrapped.
  if (isStaticPreview() || usesDevelopmentDirectCall()) return null;
  const authUserId = currentAuthUserId();
  const cachedForCurrentUser = Boolean(
    authUserId &&
    storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'true' &&
    storageGet(ACCOUNT_BOOTSTRAP_USER_KEY) === authUserId
  );
  if (action !== 'preview' && cachedForCurrentUser && !extra.force) {
    return { ok: true, cached: true };
  }
  // Sign-in, app init and call preflight may arrive together. They must await
  // the same write instead of letting the call race ahead of account_members.
  if (accountBootstrapPromise) return accountBootstrapPromise;
  accountBootstrapPromise = (async () => {
    const response = await brainPost('/account-bootstrap', accountBootstrapPayload(action, extra));
    if (response && response.ok) {
      captureTrustedLocaleContext(response);
      storageSet(ACCOUNT_BOOTSTRAP_KEY, 'true');
      if (authUserId) storageSet(ACCOUNT_BOOTSTRAP_USER_KEY, authUserId);
      const store = response.store || {};
      if (store.primaryCareRecipientId) storageSet('munea.cloudPersonId', store.primaryCareRecipientId);
      if (store.familyGroup && store.familyGroup.id) storageSet('munea.familyGroupId', store.familyGroup.id);
      if (response.activeCompanionProfile) applyCompanionProfile(response.activeCompanionProfile);
      trackProductEvent('onboarding_completed', {
        bootstrapReason: extra.reason || action,
        bootstrapBackend: response.backend && response.backend.provider ? response.backend.provider : 'json',
      });
      try { syncPullAll(); } catch (e) {}
    } else if (response && response.error && response.error.code === 'auth_user_required') {
      storageSet(ACCOUNT_BOOTSTRAP_KEY, 'pending-auth');
    }
    return response;
  })();
  try {
    return await accountBootstrapPromise;
  } finally {
    accountBootstrapPromise = null;
  }
}
function syncCompanionUI() {
  const t = templateFor();
  if (!companionNameTouched) companionDisplayName = t.defaultName;
  const display = companionDisplayName.trim() || t.defaultName;
  const src = 'avatars/' + currentAvatarId + '.png';
  const thumbSrc = t.thumbAsset || src;
  const homeSrc = thumbSrc;   // 首頁頭像＝選角色同一張臉、同一種取景（Edward 7/9：不再用另一張 hero 照）
  const fullSrc = t.fullAsset || homeSrc;
  // 這些位置顯示的是「你選的那個角色」的名字，會跟著換角色變。
  // index.html 把它們釘在女生角色的翻譯標記上（companion.nening.name），
  // 翻譯層每次重掃就蓋回寧寧／Lucía——於是換成男生後照片換了、名字沒換，
  // 甚至出現「Lucía」配男生照片、旁邊卻寫「Soy Mateo」的錯亂畫面
  // （Edward 2026-08-01 兩次抓到；中文版也一樣壞，不是外語才有的問題）。
  // 跟同日心情記錄、蘋果健康那兩個是同一個病：
  // **程式算出來的字不能同時掛翻譯標籤。**
  // 集中在這裡一次拔掉，之後新增顯示角色名的地方也只要加進這個清單。
  // .cname 那顆（用藥提醒說明裡的角色名）原本沒有任何程式在更新它，
  // 永遠停在女生角色的名字——用 $$ 一起收，新增的也自動涵蓋。
  const NAME_SLOTS = ['#companionHomeName', '#chatName', '#settingsCompanionName', '.cname'];
  NAME_SLOTS.forEach((sel) => {
    $$(sel).forEach((el) => {
      el.removeAttribute('data-i18n');
      el.textContent = display;
    });
  });
  const careHeading = $('#careHeading'); if (careHeading) careHeading.textContent = muneaT('home.careHeading', '{companion}幫你留意', { companion: display });
  const chatTaskTitle = $('#chatTaskTitle'); if (chatTaskTitle) chatTaskTitle.textContent = muneaT('home.taskChatTitle', '和{companion}聊聊', { companion: display });
  const interestsSubtitle = $('#interestsSubtitle'); if (interestsSubtitle) interestsSubtitle.textContent = muneaT('settings.interestsSubtitle', '挑幾個興趣，{companion}會多留意', { companion: display });
  const settingLabel = $('#settingsTemplateLabel');
  if (settingLabel) { settingLabel.removeAttribute('data-i18n'); settingLabel.textContent = t.templateLabel; }
  const settingImg = $('#settingsCompanionImg'); if (settingImg) settingImg.src = thumbSrc;
  const nameInput = $('#companionNameInput');
  if (nameInput && document.activeElement !== nameInput && nameInput.value !== display) nameInput.value = display;
  const fimg = $('#faceImg'); if (fimg) { fimg.src = fullSrc; fimg.classList.toggle('sq', !t.fullAsset); }
  $$('.bc-avatar img').forEach(i => { i.src = homeSrc; });
  $$('.obs-ava img').forEach(i => { i.src = thumbSrc; });   // 狀態頁「○○的觀察」頭像＝跟著選的角色臉（Edward 2026-07-09）
  const obsHeading = $('#obsHeading'); if (obsHeading) obsHeading.textContent = muneaT('status.companionObservation', '{companion}的觀察', { companion: display });
  const medSub = $('#medSub'); if (medSub) medSub.textContent = muneaT('medication.emptyHint', '還沒設定用藥，跟{companion}說一聲就好', { companion: display });
  const retentionNotice = $('#retentionNotice'); if (retentionNotice) retentionNotice.textContent = muneaT('history.retentionNotice', '保存一年；滿一年前{companion}會先問你要不要留下來。', { companion: display });
  $$('#avatarPick .avo').forEach(o => o.classList.toggle('on', o.dataset.ava === currentAvatarId));
  avatarRuntime.setCharacter(display, currentAvatarId);
  renderCompanionGreeting();
  // 在聊聊頁換角色：待機動態跟著換人（通話中不動）
  try {
    const chatActive = document.getElementById('chat') && document.getElementById('chat').classList.contains('active');
    if (chatActive && typeof FaceIdle !== 'undefined' && (typeof callConnected === 'undefined' || !callConnected)) FaceIdle.start();
  } catch (e) {}
  renderAiDiagnostics();
}
function setCompanionName(name, opts) {
  companionDisplayName = (name || '').slice(0, 12);
  companionNameTouched = companionDisplayName.trim().length > 0;
  persistCompanionProfile();
  syncCompanionUI();
  if (!(opts && opts.skipBackend)) saveCompanionProfileToBackend();
}
function setCompanionTemplate(avatarId) {
  const templateId = CompanionProfile.normalizeTemplateId(avatarId);
  const t = templateFor(templateId);
  currentAvatarId = templateId;
  currentChar = t.backendChar;
  // 名字規則：只有「用戶自己取過的名字」才保留；名字若等於任一角色的預設名＝沒真的取過 → 跟著新角色走
  const defaults = Object.values(CompanionProfile.templates || {}).map(x => x.defaultName);
  const isCustom = companionNameTouched && defaults.indexOf((companionDisplayName || '').trim()) === -1;
  if (!isCustom) { companionDisplayName = t.defaultName; companionNameTouched = false; }
  persistCompanionProfile();
  chatHistory = [];
  chatOpened = false;
  voiceProvider.close();
  syncCompanionUI();
  saveCompanionProfileToBackend();
  syncAccountBootstrap('create', { reason: 'companion_template_updated' });
  const cap = $('#chatCaption');
  if (cap) cap.textContent = muneaT('chat.captionHint', '直接說，我在這裡');
}

function playB64(b64) {
  try {
    if (chatAudio) chatAudio.pause();
    chatAudio = new Audio('data:audio/wav;base64,' + b64);
    chatAudio.onended = () => avatarRuntime.onAudioEnd();
    chatAudio.play();
  } catch (e) {}
}
// 跟真腦講話；沒有伺服器（純靜態 demo）就回 null、讓畫面自己退回規則版
const BRAIN_PATIENCE = { '/chat': 30000, '/butler/post-turn': 45000, '/voice-session': 12000, '/visit-summary': 15000 };  // 摘要要撈記憶＋量測＋用藥三路，比一般請求慢（M1 PR-4c）
// 管家腦雲端正式住址（台灣機房）——打包後的手機沒有「同一棟樓」可打相對路徑，一定要絕對網址
// 否則家人同步/邀請/資料權利/回饋全打空氣（7/9 上線體檢 B2 抓到的重傷）
// 7/16 Edward 拍板 B 案：正式包指真正式 munea-brain（測試機 -staging 留給開發包與 canary）
const BRAIN_URL_DEFAULT = 'https://munea-brain-491603544409.asia-east1.run.app';
// 判斷「是不是打包後的原生 App」：不是 http/https 開頭（capacitor:// file://）或有 Capacitor 殼＝真機
function isPackagedApp() {
  try {
    if (window.Capacitor && (window.Capacitor.isNativePlatform ? window.Capacitor.isNativePlatform() : true)) return true;
    return !/^https?:$/.test(location.protocol);
  } catch (e) { return false; }
}
// 引擎住址：①設過 munea.brainUrl 優先 ②真機沒設→走雲端正式 ③一般網頁（本機/區網有引擎同源）→相對路徑照舊
function brainURL(path) {
  try {
    const b = localStorage.getItem('munea.brainUrl');
    if (b) return b.replace(/\/$/, '') + path;
    if (b === '' ) return path;                 // 明確設空字串＝強制走同源（開發用）
    const dev = window.MUNEA_DEV_CONFIG || {};  // 開發包釘測試機（同 voiceUrl 那條線、正式包沒這塊設定）
    if (dev.enabled === true && dev.brainUrl) return String(dev.brainUrl).replace(/\/$/, '') + path;
    if (isPackagedApp()) return BRAIN_URL_DEFAULT + path;
    return path;
  } catch (e) { return path; }
}
async function brainPost(url, body) {
  if (isStaticPreview()) return null;
  // 加超時護欄：語音腦連不上時，不卡死畫面（§6.5 降級鐵律：對話不斷、老實退回）
  // 等待分級：聊天回話給足 30 秒（畫面有「我想一下」思考態撐場）、記憶整理背景 45 秒、其餘 6 秒
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), BRAIN_PATIENCE[url] || 6000);
  try {
    const r = await fetch(brainURL(url), { method: 'POST', headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body), signal: ctrl.signal });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}

async function refreshServerPlanEntitlement() {
  // The server is authoritative: this also reflects an expiry detected while
  // the app was closed, rather than preserving a stale local paid-plan badge.
  if (!isLoggedIn()) return null;
  const result = await brainPost('/entitlements', { action: 'load' });
  renderSubscriptionEndDate(result && result.billing && result.billing.subscription);
  const plan = result && result.billing && result.billing.activePlan;
  if (!['free', 'plus', 'pro'].includes(plan)) return result;
  try { localStorage.setItem('munea.plan', plan); } catch (e) {}
  try { renderPlanState(); renderFcRoster(); } catch (e) {}
  return result;
}

function renderSubscriptionEndDate(subscription) {
  const el = $('#setPlanRenewalDate');
  if (!el) return;
  const expiresAt = subscription && subscription.expiresAt;
  const expires = expiresAt ? new Date(expiresAt) : null;
  const active = subscription && subscription.status === 'active';
  if (!active || !expires || Number.isNaN(expires.getTime())) {
    el.hidden = true;
    el.textContent = '';
    return;
  }
  const date = new Intl.DateTimeFormat(muneaLocale(), {
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(expires);
  el.textContent = muneaT('subscription.expiryDate', '訂閱到期日：{date}', { date });
  el.hidden = false;
}

function subscriptionSuccessMessage(plan, subscription) {
  const rendererCopy = muneaRendererCopy();
  const planLabel = rendererCopy ? rendererCopy.planLabel(plan) : (({ plus: 'Plus', pro: 'Pro' })[plan] || muneaT('purchase.planFallbackYours', '你的'));
  const expires = subscription && subscription.expiresAt ? new Date(subscription.expiresAt) : null;
  if (subscription && subscription.status === 'active' && expires && !Number.isNaN(expires.getTime())) {
    const date = new Intl.DateTimeFormat(muneaLocale(), {
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
      year: 'numeric', month: '2-digit', day: '2-digit'
    }).format(expires);
    return muneaT('subscription.thankYou', '謝謝你訂閱 {plan}！方案已啟用。', { plan: planLabel })
      + ' ' + muneaT('subscription.expiryDate', '訂閱到期日：{date}', { date });
  }
  return muneaT('subscription.thankYou', '謝謝你訂閱 {plan}！方案已啟用。', { plan: planLabel });
}

async function routineRemindersPost(body) {
  if (isStaticPreview()) return null;
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 6000);
  try {
    const r = await fetch(brainURL('/routine-reminders'), {
      method: 'POST',
      headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body || {}),
      signal: ctrl.signal
    });
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
  finally { clearTimeout(to); }
}
function stableReminderId(prefix, raw) {
  let h = 0;
  const s = String(raw || '');
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return prefix + Math.abs(h).toString(36);
}
function splitReminderSlots(value) {
  return String(value || '').split('\u3001').map(x => x.trim()).filter(Boolean);
}
function medScheduleTimes(med) {
  return splitReminderSlots(med && med.time).map(label => {
    const def = (typeof MED_SLOT_DEF !== 'undefined' ? MED_SLOT_DEF : []).find(x => x[0] === label);
    return { label, time: def ? medSlotTime(def[1], def[2]) : '' };
  });
}
function ensureMedReminderId(med) {
  if (!med.id) med.id = stableReminderId('med_', [med.name, med.time, med.days, med.by].join('|'));
  return med.id;
}
function ensureVisitReminderId(visit) {
  if (!visit.id) visit.id = stableReminderId('visit_', [visit.title, visit.dateISO, visit.time].join('|'));
  return visit.id;
}
function syncMedicationReminder(med) {
  if (!med || !med.name) return Promise.resolve(null);
  ensureMedReminderId(med);
  return routineRemindersPost({
    action: 'save',
    reminder: {
      id: med.id,
      title: med.name,
      type: 'medication',
      status: 'active',
      // \u7528\u85e5\u7167\u7247\u53ea\u7559\u672c\u6a5f\u3001\u4e0d\u4e0a\u96f2\uff08\u96b1\u79c1\u653f\u7b56\u5c0d\u5916\u627f\u8afe\uff09\uff1aschedule \u4e0d\u542b photo \u6b04\u4f4d\u3002
      // \u7167\u7247\u7559\u5728 localStorage['munea.meds']\uff0c\u7531 refreshRoutineRemindersFromBackend \u5728\u96f2\u7aef\u5408\u4f75\u6642\u8cbc\u56de\u3002
      schedule: {
        slotLabels: splitReminderSlots(med.time),
        times: medScheduleTimes(med),
        days: med.days || '\u9577\u671f',
        by: med.by || '',
        source: 'munea-web'
      }
    }
  });
}
function syncVisitReminder(visit) {
  if (!visit || !visit.dateISO) return Promise.resolve(null);
  ensureVisitReminderId(visit);
  return routineRemindersPost({
    action: 'save',
    reminder: {
      id: visit.id,
      title: visit.title || '\u56de\u8a3a',
      type: 'check_in',
      status: 'active',
      schedule: {
        date: visit.dateISO,
        time: visit.time || '',
        label: visit.label || '',
        remindBefore: Number.isFinite(Number(visit.remindBefore)) ? Number(visit.remindBefore) : 120,
        source: 'munea-web'
      }
    }
  });
}
function archiveRoutineReminder(id) {
  if (!id) return;
  routineRemindersPost({ action: 'archive', id });
}
function reminderToLocalMed(reminder) {
  const schedule = reminder.schedule || {};
  const labels = Array.isArray(schedule.slotLabels) ? schedule.slotLabels : splitReminderSlots(schedule.slotLabels || '');
  const fallbackLabels = Array.isArray(schedule.times) ? schedule.times.map(x => x && x.label).filter(Boolean) : [];
  // \u4e0d\u5f9e\u96f2\u7aef\u8b80 photo\uff1a\u7167\u7247\u662f\u672c\u6a5f\u8cc7\u6599\uff0c\u96f2\u7aef\u4e0d\u8a72\u6709\u3002\u820a\u5e33\u865f\u82e5\u9084\u6709\u6b98\u7559\u7684 schedule.photo \u4e5f\u4e00\u5f8b\u5ffd\u7565\u3002
  return {
    id: reminder.id,
    name: reminder.title || '\u85e5',
    time: (labels.length ? labels : fallbackLabels).join('\u3001'),
    days: schedule.days || schedule.repeat || '\u9577\u671f',
    by: schedule.by || '\u96f2\u7aef',
    photo: ''
  };
}
function reminderToLocalVisit(reminder) {
  const schedule = reminder.schedule || {};
  return {
    id: reminder.id,
    title: reminder.title || '\u56de\u8a3a',
    dateISO: schedule.date || '',
    time: schedule.time || '',
    label: schedule.label || ''
  };
}
function mergeByReminderKey(primary, secondary, keyFn) {
  const seen = new Set();
  const out = [];
  [...(primary || []), ...(secondary || [])].forEach(item => {
    const key = keyFn(item);
    if (!key || seen.has(key)) return;
    seen.add(key);
    out.push(item);
  });
  return out;
}
async function refreshRoutineRemindersFromBackend() {
  const data = await routineRemindersPost({ action: 'list', status: 'active', limit: 200 });
  const reminders = data && Array.isArray(data.reminders) ? data.reminders : [];
  if (!reminders.length) return;
  const remoteVisits = reminders.filter(r => r && r.type === 'check_in').map(reminderToLocalVisit).filter(v => v.dateISO);
  const localMeds = loadMeds();
  const medKey = m => m.id || (m.name + '|' + m.time);
  // 雲端沒有照片（照片只留本機），而 mergeByReminderKey 是遠端優先——
  // 若不在這裡把本機照片貼回同一筆藥，使用者的藥品照片會在每次雲端同步後消失。
  const localPhotoByKey = new Map();
  localMeds.forEach(m => { const k = medKey(m); if (k && m.photo) localPhotoByKey.set(k, m.photo); });
  const remoteMeds = reminders
    .filter(r => r && r.type === 'medication')
    .map(reminderToLocalMed)
    .filter(m => m.name && m.time)
    .map(m => {
      const photo = localPhotoByKey.get(medKey(m));
      return photo ? Object.assign({}, m, { photo }) : m;
    });
  if (remoteMeds.length) {
    const merged = mergeByReminderKey(remoteMeds, localMeds, medKey);
    try { localStorage.setItem('munea.meds', JSON.stringify(merged)); } catch (e) {}
    updateMedCount();
  }
  if (remoteVisits.length) {
    let existing = [];
    try { existing = JSON.parse(localStorage.getItem('munea.visits') || '[]') || []; } catch (e2) {}
    const merged = mergeByReminderKey(remoteVisits, existing, v => v.id || (v.title + '|' + v.dateISO + '|' + v.time));
    try { localStorage.setItem('munea.visits', JSON.stringify(merged)); } catch (e3) {}
    if (window.__muneaRefreshVisitRow) window.__muneaRefreshVisitRow();
    if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks();
  }
}
window.__muneaRoutineReminderSync = { refresh: refreshRoutineRemindersFromBackend, saveMed: syncMedicationReminder, saveVisit: syncVisitReminder };

function localFamilyRelayMembers() {
  try {
    const items = JSON.parse(localStorage.getItem('munea.circleMembers') || '[]');
    return Array.isArray(items) ? items : [];
  } catch (e) { return []; }
}
async function refreshFamilyRelayMembers() {
  if (!isLoggedIn()) return localFamilyRelayMembers();
  const data = await brainPost('/family-members', { action: 'list', familyGroupId: famGroupId(), limit: 100 });
  const remote = data && Array.isArray(data.members) ? data.members : [];
  if (!remote.length) return localFamilyRelayMembers();
  const old = localFamilyRelayMembers();
  const mine = muneaCloudPersonId();
  const members = remote.map((m, index) => {
    const name = String(m.displayName || m.name || '').trim() || muneaT('familyCircle.memberFallback', '家人');
    const previous = old.find(x => x.personId === m.personId || x.name === name) || {};
    return {
      name,
      relationship: m.relationship || previous.relationship || '家人',
      personId: m.personId || m.id,
      init: previous.init || name[0],
      // 這裡本來配的是 p-ma / p-ba / p-jie——這三個色號 CSS 裡從來沒有，
      // 所以四個家人裡有三個的頭像是沒有底色的（Edward 2026-08-01 從畫面上看出來）。
      // 改用真的存在的八色，同一份名單裡也就不會兩個人長得一樣。
      tint: (MUNEA_AVA_TINTS.indexOf(previous.tint) >= 0 ? previous.tint : MUNEA_AVA_TINTS[index % MUNEA_AVA_TINTS.length]),
      self: (m.personId || m.id) === mine,
    };
  });
  try { localStorage.setItem('munea.circleMembers', JSON.stringify(muneaAssignTints(members))); } catch (e) {}
  if (typeof window.__muneaAfterCircleSync === 'function') window.__muneaAfterCircleSync();
  return members;
}
function relayNameKey(value) {
  return String(value || '').replace(/[\s　]/g, '').replace(/^(我的|我們家)/, '').toLowerCase();
}
async function createFamilyRelay(recipientName, message) {
  const who = String(recipientName || '').trim().slice(0, 40);
  const content = String(message || '').trim().replace(/^[，,：:]*/, '').slice(0, 240);
  if (!isLoggedIn()) return { ok: false, error: 'login_required' };
  if (!who || content.length < 2) return { ok: false, error: 'recipient_or_message_required' };
  if (!muneaIsCleanSpeechText(content)) return { ok: false, error: 'message_not_clean_zh' };
  let members = await refreshFamilyRelayMembers();
  const key = relayNameKey(who);
  const matches = members.filter(m => !m.self && m.personId && [m.name, m.relationship].some(v => relayNameKey(v) === key));
  if (matches.length !== 1) {
    const error = matches.length > 1 ? 'recipient_ambiguous' : 'recipient_not_in_family_circle';
    if (typeof toast === 'function') toast(matches.length > 1 ? muneaT('familyCircle.recipientAmbiguous', '家庭圈裡有同名家人，請說完整名稱') : muneaT('familyCircle.recipientNotFound', '家庭圈裡找不到「{name}」，請先確認家人名稱', { name: who }));
    return { ok: false, error };
  }
  const target = matches[0];
  const data = await brainPost('/family-relays', {
    action: 'create',
    relay: {
      familyGroupId: famGroupId(),
      recipientPersonId: target.personId,
      recipientLabel: target.name,
      senderLabel: myFeedName(),
      content,
      source: 'voice-ai',
    },
  });
  if (!data || !data.ok || !data.relay) {
    if (typeof toast === 'function') toast(muneaT('chat.sendFailedToast', "這句話還沒送出去，請再試一次"));
    return { ok: false, error: (data && data.error) || 'relay_write_failed' };
  }
  if (typeof toast === 'function') toast(muneaT('familyCircle.relayQueuedToast', '傳出去了，{name}一打開就會看到', { companion: cname(), name: target.name }));
  return { ok: true, relayId: data.relay.id, recipientName: target.name, message: content };
}
async function claimNextFamilyRelay() {
  if (!isLoggedIn()) return null;
  const data = await brainPost('/family-relays', { action: 'claim' });
  const relay = data && data.ok && data.relay ? data.relay : null;
  if (!relay) return null;
  try {
    const receipts = JSON.parse(localStorage.getItem('munea.familyRelayReceipts') || '{}') || {};
    if (receipts[relay.id]) {
      const acknowledged = await finishFamilyRelayClaim(relay, 'ack');
      if (acknowledged) { delete receipts[relay.id]; localStorage.setItem('munea.familyRelayReceipts', JSON.stringify(receipts)); }
      return null;
    }
  } catch (e) {}
  return relay;
}
function rememberSpokenFamilyRelay(relay) {
  if (!relay || !relay.id) return;
  try {
    const receipts = JSON.parse(localStorage.getItem('munea.familyRelayReceipts') || '{}') || {};
    receipts[relay.id] = Date.now();
    const recent = Object.entries(receipts).sort((a, b) => b[1] - a[1]).slice(0, 30);
    localStorage.setItem('munea.familyRelayReceipts', JSON.stringify(Object.fromEntries(recent)));
  } catch (e) {}
}
async function finishFamilyRelayClaim(relay, action) {
  if (!relay || !relay.id || !relay.claimToken) return false;
  const data = await brainPost('/family-relays', { action, id: relay.id, claimToken: relay.claimToken });
  return !!(data && data.ok);
}
window.__muneaFamilyRelays = { create: createFamilyRelay, claim: claimNextFamilyRelay, finish: finishFamilyRelayClaim, refreshMembers: refreshFamilyRelayMembers };
// 首頁那張卡的重繪入口掛出來：驗收時要能在不打真電話的情況下看到「家人帶話」長什麼樣
window.__muneaHomeRelayView = { sync: () => syncHomeFamilyRelay(), load: () => loadHomeRelay(), preview: relay => { _muneaHomeRelay = relay || null; renderCompanionGreeting(); } };

// ===== 聊聊 AI 幫你把提醒設進 App（跟手動新增走同一份清單 + 同一套雲端/手機通知）· 2026-07-09 Edward =====
const INTEREST_TOPIC_KEYS = { '旅遊景點': 'legacyUi.topic.travel', '美食餐廳': 'legacyUi.topic.food', '影劇戲劇': 'legacyUi.topic.tv', '新聞時事': 'legacyUi.topic.news', '健康養生': 'legacyUi.topic.health', '運動': 'legacyUi.topic.sports', '懷舊老歌': 'legacyUi.topic.music', '園藝花草': 'legacyUi.topic.gardening', '歷史故事': 'legacyUi.topic.history', '寵物': 'legacyUi.topic.pets', '棋牌麻將': 'legacyUi.topic.games', '天氣節氣': 'legacyUi.topic.weather' };
function interestTopicLabel(t) { return INTEREST_TOPIC_KEYS[t] ? muneaT(INTEREST_TOPIC_KEYS[t], t) : t; }
function aiVisitLabel(dateISO, time) {
  try {
    const d = new Date(dateISO + 'T00:00');
    const hasTime = !!(time && /^\d{1,2}:\d{2}$/.test(time));
    if (!(muneaLocale() || 'zh-TW').startsWith('zh')) {
      let label = new Intl.DateTimeFormat(muneaLocale(), { month: 'numeric', day: 'numeric', weekday: 'short' }).format(d);
      if (hasTime) {
        const p = time.split(':').map(Number);
        label += ' ' + new Intl.DateTimeFormat(muneaLocale(), { hour: 'numeric', minute: '2-digit' }).format(new Date(2000, 0, 1, p[0], p[1]));
      }
      return label;
    }
    const md = (d.getMonth() + 1) + '/' + d.getDate();
    const wd = [muneaT('mood.weekdayShortSun', '日'), muneaT('mood.weekdayShortMon', '一'), muneaT('mood.weekdayShortTue', '二'), muneaT('mood.weekdayShortWed', '三'), muneaT('mood.weekdayShortThu', '四'), muneaT('mood.weekdayShortFri', '五'), muneaT('mood.weekdayShortSat', '六')][d.getDay()];
    let tstr = '';
    if (hasTime) {
      const p = time.split(':').map(Number), h = p[0], m = p[1];
      const ap = h < 12 ? muneaT('common.am', '上午') : muneaT('common.pm', '下午'), h12 = ((h + 11) % 12) + 1;
      tstr = ' ' + ap + ' ' + h12 + ':' + String(m).padStart(2, '0');
    }
    return md + '（' + wd + '）' + tstr;
  } catch (e) { return dateISO + (time ? ' ' + time : ''); }
}
// 提前多久提醒（分鐘）。舊資料沒有這個欄位 → 一律當成 120，維持既有行為。
// 放最外層是因為兩條路都要用：畫面上自己選、以及寧寧用講的幫他設（Edward 2026-08-01）。
var VISIT_LEAD_DEFAULT = 120;
var VISIT_LEAD_CHOICES = [0, 30, 60, 120, 1440];
// 講出來的說法。原本存檔提示寫死「前一天會提醒你」，
// 提前多久變成他自己選的之後，寫死就會說謊（正式機截圖抓到）。
function visitLeadSpoken(minutes) {
  switch (Number(minutes)) {
    case 0: return muneaT('visit.leadSpokenOnTime', '準時');
    case 30: return muneaT('visit.leadSpoken30m', '提前 30 分');
    case 60: return muneaT('visit.leadSpoken1h', '提前 1 小時');
    case 1440: return muneaT('visit.leadSpoken1d', '提前一天');
    default: return muneaT('visit.leadSpoken2h', '提前 2 小時');
  }
}
async function aiAddVisitReminder(a) {
  const rawTitle = String((a && a.title) || '').trim();
  // AI 語音辨識可能夾雜外文雜訊，存檔前先守門（Edward 2026-07-15 事故：aiAddVisitReminder / aiAddMedReminder 原本沒接共用守門）。
  // 退回去的預設名稱原本寫死中文「回診」——日文西文使用者被擋掉時，App 裡就會冒出一個中文詞（2026-08-01 實測看到）。
  const title = (rawTitle && muneaIsCleanSpeechText(rawTitle)) ? rawTitle : muneaT('visit.defaultTitle', '回診');
  const dateISO = String((a && a.dateISO) || '').trim();
  const time = String((a && a.time) || '').trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateISO) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return { ok: false, error: 'invalid_date_or_time' };
  const when = new Date(dateISO + 'T' + time + ':00');
  if (Number.isNaN(when.getTime()) || when.getTime() < Date.now() - 60000) return { ok: false, error: 'reminder_time_in_past' };
  let arr = [];
  try { arr = JSON.parse(localStorage.getItem('munea.visits') || '[]') || []; } catch (e) {}
  if (!Array.isArray(arr)) arr = [];
  const label = aiVisitLabel(dateISO, time);
  // 提前多久只收畫面上有的那五種。她若聽成別的數字（例如 47 分），
  // 收下來就會變成「畫面上選不到、但存著的是它」——一律退回預設兩小時。
  const leadRaw = Number(a && a.remindBefore);
  const remindBefore = VISIT_LEAD_CHOICES.includes(leadRaw) ? leadRaw : VISIT_LEAD_DEFAULT;
  const visit = { title, dateISO, time, label, remindBefore };
  ensureVisitReminderId(visit);
  arr = arr.filter(v => String(v && v.id) !== String(visit.id));
  arr.push(visit);
  try { localStorage.setItem('munea.visits', JSON.stringify(arr)); } catch (e) { return { ok: false, error: 'local_write_failed' }; }
  try { if (typeof syncPush === 'function') syncPush('visits', arr); } catch (e) {}
  let cloud = null;
  try { cloud = await syncVisitReminder(visit); } catch (e) {}
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  try { if (window.__muneaRefreshVisitRow) window.__muneaRefreshVisitRow(); } catch (e) {}
  try { if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks(); } catch (e) {}
  return { ok: true, title, label, remindBefore, reminderId: visit.id, persistence: cloud && cloud.ok ? 'cloud' : 'device' };
}
const CARE_Q_KEY = 'munea.careQuestions';
/* 上限 5 題（Edward 2026-07-29：「可以多點但不要超過 5 點」）。
   滿了**不可以默默丟掉最舊的**——寧寧答應要幫他記，偷偷刪掉等於毀約。
   滿了就講出來，讓他自己決定刪哪一題。 */
const CARE_Q_MAX = 10;
const CARE_Q_MAX_LEN = 60;      // 一題最長 60 字（跟工具描述一致）
function loadCareQuestions() {
  let arr = [];
  try { arr = JSON.parse(localStorage.getItem(CARE_Q_KEY) || '[]') || []; } catch (e) {}
  if (!Array.isArray(arr)) arr = [];
  return arr.filter(q => q && typeof q.text === 'string' && q.text);
}
function saveCareQuestions(arr) {
  // 這裡不再 slice——靜靜截掉等於把「答應記住的事」丟掉。滿了要在入口擋下並說明。
  try { localStorage.setItem(CARE_Q_KEY, JSON.stringify(arr)); return true; } catch (e) { return false; }
}
function openCareQuestions() {
  return loadCareQuestions().filter(q => !q.askedAt);
}
async function aiAddCareQuestion(a) {
  const raw = String((a && a.question) || '').trim().slice(0, CARE_Q_MAX_LEN);
  // 同一道共用守門：辨識雜訊／外文亂碼寧可拒收讓她再問一次，不存假問題（沿用 2026-07-15 事故的教訓）
  if (!raw || !muneaIsCleanSpeechText(raw)) return { ok: false, error: 'question_text_unclear' };
  const arr = loadCareQuestions();
  const norm = raw.replace(/\s+/g, '');
  if (arr.some(q => !q.askedAt && String(q.text || '').replace(/\s+/g, '') === norm)) {
    // 同一個問題重複記＝清單變垃圾場。回 ok（她已經跟長輩說要記了，不該讓她改口說失敗），但不重複塞。
    return { ok: true, question: raw, count: openCareQuestions().length, duplicate: true };
  }
  // 滿 5 題就明確回失敗，讓她當場講出來、問他要不要換掉哪一題。
  // **絕不默默擠掉最舊的那題**——她說了會記住，結果偷偷刪掉，比一開始就說「記不下了」糟得多。
  const openNow = openCareQuestions();
  if (openNow.length >= CARE_Q_MAX) {
    return { ok: false, error: 'question_list_full', count: openNow.length, max: CARE_Q_MAX };
  }
  const item = { id: 'q_' + Date.now().toString(36) + Math.random().toString(16).slice(2, 6), text: raw, createdAt: new Date().toISOString(), askedAt: '' };
  arr.push(item);
  if (!saveCareQuestions(arr)) return { ok: false, error: 'local_write_failed' };
  const count = openCareQuestions().length;
  // 閘門埋點（H1：就醫時刻是不是真痛點）——只記數量與長度，**不送問題內文**（健康疑問屬敏感內容，
  // trackProductEvent 本來就會剝 text/transcript/reply，這裡連欄位都不放）
  try { trackProductEvent('care_question_added', { questionCount: count, textLength: raw.length, via: 'voice' }); } catch (e) {}
  try { if (window.__muneaRefreshVisitRow) window.__muneaRefreshVisitRow(); } catch (e) {}
  try { if (typeof renderCareQuestions === 'function') renderCareQuestions(); } catch (e) {}
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  return { ok: true, question: raw, count, persistence: 'device' };
}
window.__muneaOpenCareQuestions = openCareQuestions;
window.__muneaLoadCareQuestions = loadCareQuestions;
window.__muneaSaveCareQuestions = saveCareQuestions;

/* ===== 就診摘要（M1 · PR-4c）=====
   帶去給醫生看的一頁。三條設計決定寫在這裡，改動前先讀：

   ① **快照優先，不是每次現算**。診間網路常常爛，而且記憶層會淘汰舊資料
      （不重要的一次性事件放兩週就清掉）。所以產生過的摘要一律存快照，
      打開時先畫快照、背景再更新——離線打得開，且早期症狀不會憑空消失。
   ② **口袋問題在前端合併**。那份清單是裝置本機的（H1 期間刻意不上雲），
      後端不知道它的存在。客觀資料由後端組、主觀問題由前端接上去。
   ③ **不出現任何判定字眼與警示色**。後端 visit_summary.py 守了一遍，
      這裡再守一遍——畫面上加一個紅色驚嘆號，就等於我們在說「這個不正常」。 */
const VISIT_SUMMARY_SNAP_KEY = 'munea.visitSummary.v1';
const VISIT_SUMMARY_PERIOD_KEY = 'munea.visitSummaryPeriod';
const VISIT_SUMMARY_PERIODS = [7, 14, 30, 60];
const VISIT_SUMMARY_MARK = { symptom: '●', vital: '▲', med: '✕' };
let _rptPeriod = 0;
let _rptEditing = false;   // 診間閱讀狀態（乾淨）↔ 在家整理狀態（有刪除鍵）

function visitSummaryPeriod() {
  let stored = 0;
  try { stored = parseInt(localStorage.getItem(VISIT_SUMMARY_PERIOD_KEY) || '', 10); } catch (e) {}
  return VISIT_SUMMARY_PERIODS.indexOf(stored) >= 0 ? stored : 14;
}
function setVisitSummaryPeriod(days) {
  if (VISIT_SUMMARY_PERIODS.indexOf(days) < 0) return;
  try { localStorage.setItem(VISIT_SUMMARY_PERIOD_KEY, String(days)); } catch (e) {}
}
function loadVisitSummarySnapshot(days) {
  try {
    const all = JSON.parse(localStorage.getItem(VISIT_SUMMARY_SNAP_KEY) || '{}') || {};
    const snap = all[String(days)];
    return (snap && snap.summary) ? snap : null;
  } catch (e) { return null; }
}
function saveVisitSummarySnapshot(days, summary) {
  try {
    const all = JSON.parse(localStorage.getItem(VISIT_SUMMARY_SNAP_KEY) || '{}') || {};
    all[String(days)] = { summary, savedAt: new Date().toISOString() };
    localStorage.setItem(VISIT_SUMMARY_SNAP_KEY, JSON.stringify(all));
  } catch (e) {}
}
async function fetchVisitSummary(days) {
  const r = await brainPost('/visit-summary', { periodDays: days });
  if (r && r.ok && r.summary) { saveVisitSummarySnapshot(days, r.summary); return r.summary; }
  return null;
}

function rptEsc(text) {
  return String(text == null ? '' : text)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function rptShortDate(iso) {
  const m = String(iso || '').match(/^\d{4}-(\d{2})-(\d{2})$/);
  return m ? (parseInt(m[1], 10) + '/' + parseInt(m[2], 10)) : '';
}
/* 紙面要印的姓名（Edward 2026-07-30 拍板「要有」）。
   一張要遞給醫生的紙沒有名字，在診間很可能被拿錯、或跟別人的資料混在一起。

   刻意只取 name（個人資料的「名稱」）：
   · **不退回 nick**——「阿嬤」在診間對比病歷毫無用處，印一個看似有身分卻
     不能比對的名字，比留空更誤導
   · **不退回角色名**——那是 AI 的名字，不是病人的
   · 沒填就整個不印（不留「姓名：」的空欄位，空欄位在文件上看起來像漏填）

   刻意**不印生日、身分證號、地址**。Edward 拍板的是「要有姓名」，不是一整組
   身分資料。這張紙會被影印、被放在診間桌上——多一個識別欄位就多一分外洩代價。
   （若之後要處理同名比對，生日是標準做法，但那是另一個隱私決定。） */
function visitSummaryPatientName() {
  try {
    const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}') || {};
    const name = String(p.name || '').trim();
    return muneaSafeDisplayText(name, '');
  } catch (e) { return ''; }
}

/* 沒讀到的來源翻成人話。畫面、純文字、PDF 三處共用同一份對照，
   免得同一份摘要在三個地方講出不一樣的缺料清單。 */
function visitPartialNames(partial) {
  const label = {
    vitals: muneaT('visit.partialVitals', '在家量測'),
    medication: muneaT('visit.partialMedication', '用藥紀錄'),
    symptoms: muneaT('visit.partialSymptoms', '聊天中提到的狀況'),
  };
  return (partial || []).map(k => label[k] || k).join(muneaListSeparator());
}

/* ── 本機先組一份（Edward 2026-07-29：「不要顯示整理中」）─────────────
   原本整頁一起等 /visit-summary，等到最慢的那一塊，所以開頁一片空白。
   查過資料在哪：在家量的（munea.healthLog）、吃藥（munea.meds＋munea.medDone）
   本來就在這支手機裡，連日期範圍都能當場算——這三塊根本不必等網路。

   **刻意不在這裡重做時間軸的挑選邏輯。** 哪一筆數值算「有變化」、哪一句
   閒聊算「症狀」，規則長在 engine/visit_summary.py。在前端照抄一份，兩邊
   遲早會走鐘，屆時手機上看到的和印給醫師的 PDF 會是兩份不同的東西——
   這種東西不能有兩個版本。所以時間軸只認伺服器那一份，等它回來；
   等不到就明講等不到，不自己編一份。 */
function vsLocalDateRange(days) {
  const to = new Date();
  const from = new Date(to.getTime() - (days - 1) * 86400000);
  const iso = d => d.getFullYear() + '-'
    + String(d.getMonth() + 1).padStart(2, '0') + '-'
    + String(d.getDate()).padStart(2, '0');
  return { from: iso(from), to: iso(to) };
}
const VS_VITAL_FIELDS = [
  { key: 'bp', label: () => muneaT('health.bloodPressure', '血壓') },
  { key: 'hr', label: () => muneaT('health.heartRate', '心跳') },
  { key: 'spo2', label: () => muneaT('health.bloodOxygen', '血氧') },
];
/* 在家量的：只做加總，不做判讀——最近一次的數字＋這段期間量了幾天。
   不比對任何標準值，不說高不說低（醫材紅線）。 */
function vsLocalVitals(range) {
  let log = {};
  try { log = JSON.parse(localStorage.getItem('munea.healthLog') || '{}') || {}; } catch (e) {}
  const days = Object.keys(log).filter(d => d >= range.from && d <= range.to).sort();
  if (!days.length) return [];
  const out = [];
  for (const field of VS_VITAL_FIELDS) {
    let latest = '';
    let count = 0;
    for (const d of days) {
      const row = log[d] || {};
      let value = '';
      if (field.key === 'bp') {
        if (Number.isFinite(row.bpSys) && Number.isFinite(row.bpDia)) value = row.bpSys + '/' + row.bpDia;
      } else if (Number.isFinite(row[field.key])) {
        value = String(row[field.key]);
      }
      if (value) { latest = value; count += 1; }
    }
    if (count) {
      out.push(field.label() + ' ' + latest + ' · '
        + muneaT('visit.measuredDays', '量了 {n} 天', { n: count }));
    }
  }
  return out;
}
/* 藥實際吃了沒：排了幾次、吃了幾次。只給次數不給服藥率——
   百分比讀起來就是評分，評分就是判斷。 */
function vsLocalMedication(range) {
  const meds = (typeof loadMeds === 'function') ? loadMeds() : [];
  if (!meds.length) return [];
  const dayKeys = [];
  for (let d = new Date(range.from + 'T00:00:00'); ; d = new Date(d.getTime() + 86400000)) {
    const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')
      + '-' + String(d.getDate()).padStart(2, '0');
    dayKeys.push(key);
    if (key >= range.to) break;
    if (dayKeys.length > 400) break;   // 保險絲：日期算錯也不要無限迴圈
  }
  const done = {};
  for (const key of dayKeys) {
    try { done[key] = JSON.parse(localStorage.getItem('munea.medDone.' + key) || '{}') || {}; }
    catch (e) { done[key] = {}; }
  }
  const out = [];
  for (const med of meds) {
    const slots = String(med.time || '').split('、').map(s => s.trim()).filter(Boolean);
    if (!slots.length) continue;
    let scheduled = 0;
    let taken = 0;
    for (const key of dayKeys) {
      for (const slot of slots) {
        scheduled += 1;
        if (done[key][slot + '|' + med.name]) taken += 1;
      }
    }
    if (scheduled) out.push({ name: med.name, scheduled, taken, missed: Math.max(0, scheduled - taken) });
  }
  return out;
}
function buildLocalVisitSummary(days) {
  const range = vsLocalDateRange(days);
  return {
    periodDays: days,
    from: range.from,
    to: range.to,
    timeline: [],
    timelineOmitted: 0,
    vitals: vsLocalVitals(range),
    medication: vsLocalMedication(range),
    baselineNote: '',
    partial: [],
    timelinePending: true,   // 時間軸還沒有：等伺服器，不是「沒事發生」
    fromDevice: true,
  };
}

function renderVisitSummary(summary) {
  const body = document.getElementById('rptBody');
  if (!body) return;
  const questions = (typeof openCareQuestions === 'function') ? openCareQuestions() : [];
  const parts = [];
  const sec = key => '<h2 class="set-section">' + rptEsc(key) + '</h2>';

  // ① 想問醫生擺最上面——醫師最先想知道的是「這個病人今天想幹嘛」
  //
  // 為什麼刪除鍵要藏在「編輯」後面：這一頁有兩個使用時刻，需求正好相反。
  //   · 看診前在家 → 要加、要刪
  //   · 在診間把手機遞給醫生 → 一整排「刪除」既雜亂又不專業，
  //     而且醫生捲頁時很可能誤觸，把他準備了兩個禮拜的問題刪掉
  // 預設是乾淨的閱讀狀態，要改再按「編輯」。
  parts.push('<h2 class="set-section vs-sec-act">'
    + rptEsc(muneaT('visit.questionsTitle', '這次想問醫生'))
    + (questions.length
      ? '<button type="button" id="rptEditToggle">' + rptEsc(_rptEditing
        ? muneaT('common.done', '完成') : muneaT('common.edit', '編輯')) + '</button>'
      : '')
    + '</h2>');
  if (questions.length) {
    // 問題列直接用 .set-row（17px＝規範定的「內文」字級）。
    // 這是整頁最需要看清楚的東西——長輩在診間拿著手機唸給醫生聽，
    // 縮成 14px 的小字等於白做。編號用 .sr-ico 那顆現成的圓角方塊，
    // 他可以直接說「第二題」。刪除用文字不用 ✕ 圖示：長輩讀得懂字，
    // 猜不出圖示，而且刪東西這種不可逆的動作更不該用猜的。
    parts.push('<div class="set-list">');
    questions.forEach((q, i) => {
      parts.push('<div class="set-row"><span class="sr-ico">' + (i + 1) + '</span>'
        + '<span class="sr-main">' + rptEsc(muneaSafeDisplayText(q.text, '')) + '</span>'
        + (_rptEditing
          ? '<button class="vs-del" type="button" data-qid="' + rptEsc(q.id) + '" aria-label="'
            + rptEsc(muneaT('visit.deleteQuestionAria', '刪掉這一題')) + '">'
            + rptEsc(muneaT('common.delete', '刪除')) + '</button>'
          : '')
        + '</div>');
    });
    parts.push('</div>');
  } else {
    parts.push('<p class="vs-empty">' + rptEsc(muneaT('visit.questionsEmpty',
      '還沒有記下要問的問題。跟{companion}聊到身體上的疑問時，她會幫你記下來。',
      { companion: (typeof cname === 'function' ? cname() : '寧寧') })) + '</p>');
  }
  // 滿了就不給加，並且講明為什麼——不能讓他按了沒反應
  if (questions.length >= CARE_Q_MAX) {
    parts.push('<p class="vs-note">' + rptEsc(muneaT('visit.questionsFullHint',
      '已經記滿 {n} 題了。想再加的話，先刪掉一題。', { n: CARE_Q_MAX })) + '</p>');
  } else if (!_rptEditing) {
    parts.push('<button class="vs-add" type="button" id="rptAddQ">'
      + rptEsc(muneaT('visit.addQuestion', '＋ 自己加一題')) + '</button>');
  }

  if (!summary) {
    parts.push(sec(muneaT('visit.timelineTitle', '這段期間發生的事')));
    parts.push('<p class="vs-empty">' + rptEsc(muneaT('visit.restUnavailable',
      '其他資料還沒讀到，等連上網路再看一次。')) + '</p>');
    body.innerHTML = parts.join('');
    bindVisitSummaryBody();
    return;
  }

  // ② 時間軸：三種來源用形狀分（醫師要分辨的是可信度，不是嚴重度，所以不用顏色）。
  //    這一塊只認伺服器那一份——前端不自己挑哪筆算「有變化」，兩份規則會走鐘。
  parts.push(sec(muneaT('visit.timelineTitle', '這段期間發生的事')));
  parts.push('<div class="reader-card">');
  if (summary.timeline && summary.timeline.length) {
    summary.timeline.forEach(e => {
      parts.push('<div class="vs-line"><span class="d">' + rptShortDate(e.date) + '</span>'
        + '<span class="m">' + (VISIT_SUMMARY_MARK[e.kind] || '·') + '</span>'
        + '<span class="q">' + rptEsc(e.text)
        + (e.detail ? '<em>' + rptEsc(e.detail) + '</em>' : '') + '</span></div>');
    });
    parts.push('<p class="vs-note">'
      + rptEsc(muneaT('visit.legend', '● 長輩自己說的　▲ 在家量的　✕ 用藥紀錄')) + '</p>');
    // 截斷一定要說出來——悄悄少幾筆會讓醫師以為這就是全部
    if (summary.timelineOmitted > 0) {
      parts.push('<p class="vs-note">'
        + rptEsc(muneaT('visit.timelineOmitted', '另有 {n} 筆較早的紀錄沒有列出來。', { n: summary.timelineOmitted }))
        + '</p>');
    }
  } else if (summary.timelinePending) {
    // 還在讀 ≠ 沒事發生。這兩件事講反了，醫師會以為這段期間他都好好的。
    parts.push('<div class="vs-pend" style="border-top:0;margin-top:0;padding-top:0">'
      + '<i class="vs-dot"></i>' + rptEsc(muneaT('visit.timelineLoading', '聊天中提到的還在讀…')) + '</div>');
  } else if (summary.timelineFailed) {
    parts.push('<div class="vs-pend" style="border-top:0;margin-top:0;padding-top:0">'
      + '⌛ ' + rptEsc(muneaT('visit.timelineOffline', '這次沒連上，聊天中提到的沒有列進來')) + '</div>');
  } else {
    parts.push('<p class="vs-empty" style="padding:0">'
      + rptEsc(muneaT('visit.timelineEmpty', '這段期間沒有記錄到特別的變化。')) + '</p>');
  }
  parts.push('</div>');

  if (summary.vitals && summary.vitals.length) {
    parts.push(sec(muneaT('visit.vitalsTitle', '在家量的')));
    parts.push('<div class="set-list">');
    summary.vitals.forEach(line => {
      parts.push('<div class="set-row"><span class="sr-main">' + rptEsc(line) + '</span></div>');
    });
    parts.push('</div>');
    if (summary.baselineNote) parts.push('<p class="vs-note">' + rptEsc(summary.baselineNote) + '</p>');
  }

  if (summary.medication && summary.medication.length) {
    parts.push(sec(muneaT('visit.medTitle', '藥實際吃了沒')));
    parts.push('<div class="set-list">');
    summary.medication.forEach(m => {
      parts.push('<div class="set-row"><span class="sr-main">' + rptEsc(m.name)
        + (m.missed ? '<small>' + rptEsc(muneaT('visit.medMissed', '其中 {n} 次沒吃', { n: m.missed })) + '</small>' : '')
        + '</span><span class="sr-on">'
        + rptEsc(muneaT('visit.medCounts', '排 {scheduled} 次 · 吃了 {taken} 次',
          { scheduled: m.scheduled, taken: m.taken })) + '</span></div>');
    });
    parts.push('</div>');
  }

  // 部分資料沒讀到要講——一份少了血壓的摘要看起來就像「他都沒量」
  if (summary.partial && summary.partial.length) {
    parts.push('<p class="vs-note">⌛ '
      + rptEsc(muneaT('visit.partialNote', '{names}這次沒有讀到，這一頁不是完整的。連上網路後再開一次。',
        { names: visitPartialNames(summary.partial) })) + '</p>');
  }

  body.innerHTML = parts.join('');
  bindVisitSummaryBody();
}

function bindVisitSummaryBody() {
  const add = document.getElementById('rptAddQ');
  if (add) add.addEventListener('click', addCareQuestionManually);
  const edit = document.getElementById('rptEditToggle');
  if (edit) edit.addEventListener('click', () => {
    _rptEditing = !_rptEditing;
    renderVisitSummary(_rptLastSummary);
  });
  document.querySelectorAll('#rptBody .vs-del').forEach(btn => {
    btn.addEventListener('click', () => removeCareQuestion(btn.dataset.qid));
  });
}

/* 長輩自己加一題。刻意**沒有**「子女代為新增」的入口——
   沐寧要降低子女的負擔，不是給子女一個做整理工的工具（Edward 2026-07-28）。 */
function addCareQuestionManually() {
  const open = openCareQuestions();
  if (open.length >= CARE_Q_MAX) {
    toast(muneaT('visit.questionsFull', '已經記滿 {n} 題了，先刪掉一題再加', { n: CARE_Q_MAX }));
    return;
  }
  const raw = window.prompt(muneaT('visit.promptQuestion', '想問醫生什麼？'));
  if (raw === null) return;
  const text = String(raw).trim().slice(0, CARE_Q_MAX_LEN);
  if (!text) return;
  if (!muneaIsCleanSpeechText(text)) { toast(muneaT('visit.questionUnclear', '這句我看不懂，換個說法再試一次')); return; }
  const arr = loadCareQuestions();
  const norm = text.replace(/\s+/g, '');
  if (arr.some(q => !q.askedAt && String(q.text || '').replace(/\s+/g, '') === norm)) {
    toast(muneaT('visit.questionDuplicate', '這題已經在清單裡了')); return;
  }
  arr.push({ id: 'q_' + Date.now().toString(36) + Math.random().toString(16).slice(2, 6), text, createdAt: new Date().toISOString(), askedAt: '' });
  if (!saveCareQuestions(arr)) { toast(muneaT('visit.questionSaveFailed', '沒存起來，請再試一次')); return; }
  try { trackProductEvent('care_question_added', { questionCount: openCareQuestions().length, textLength: text.length, via: 'manual' }); } catch (e) {}
  renderVisitSummary(_rptLastSummary);
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
}
function removeCareQuestion(id) {
  if (!id) return;
  const arr = loadCareQuestions().filter(q => String(q.id) !== String(id));
  saveCareQuestions(arr);
  try { trackProductEvent('care_question_removed', { questionCount: openCareQuestions().length }); } catch (e) {}
  renderVisitSummary(_rptLastSummary);
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
}

/* 看診日過了，問題自動歸檔（Edward 2026-07-29：拿掉「看完醫生了」那顆按鈕，
   因為這一頁是歷史資料、不是待辦事項，不該要求他按「完成」）。

   歸檔＝標記 askedAt，**不刪除**。理由跟原本那顆按鈕一樣：他問過什麼是病史
   的一部分，只是不要再拿舊問題提醒他。判定用「問題建立時間早於某一次已過的
   就診」——早於那次看診才算問過了；看完診之後才記的，是要問下一次的。 */
/* 只留 60 天（Edward 2026-07-29：「最多就是儲存60天」）。
   60 天正好是天數選項的上限——超過那個範圍的紀錄，這一頁再也顯示不到，
   留著只是佔手機空間。問過的問題也一樣：歸檔是為了下次不再提醒他，
   不是要永久保存一份健康疑問清單在裝置上。 */
const VISIT_DATA_RETENTION_DAYS = 60;
function pruneVisitSummaryData() {
  const cutoff = Date.now() - VISIT_DATA_RETENTION_DAYS * 86400000;
  // ① 問過的問題：超過 60 天就清掉。**還沒問的一律留著**——
  //    他可能兩個月前就想問了，還沒輪到看診，那不是過期資料。
  try {
    const arr = loadCareQuestions();
    const kept = arr.filter(q => {
      if (!q || !q.askedAt) return true;
      const asked = Date.parse(q.askedAt);
      return !Number.isFinite(asked) || asked > cutoff;
    });
    if (kept.length !== arr.length) saveCareQuestions(kept);
  } catch (e) {}
  // ② 摘要快照：存太久的那份跟現況早就對不上，留著反而可能拿舊的給醫生看
  try {
    const all = JSON.parse(localStorage.getItem(VISIT_SUMMARY_SNAP_KEY) || '{}') || {};
    let changed = false;
    for (const key of Object.keys(all)) {
      const savedAt = Date.parse((all[key] || {}).savedAt || '');
      if (!Number.isFinite(savedAt) || savedAt <= cutoff) { delete all[key]; changed = true; }
    }
    if (changed) localStorage.setItem(VISIT_SUMMARY_SNAP_KEY, JSON.stringify(all));
  } catch (e) {}
}

function autoArchiveCareQuestions() {
  let visits = [];
  try { visits = JSON.parse(localStorage.getItem('munea.visits') || '[]') || []; } catch (e) {}
  if (!Array.isArray(visits) || !visits.length) return 0;
  const now = Date.now();
  let lastPassed = 0;
  for (const v of visits) {
    if (!v || !v.dateISO) continue;
    const at = new Date(v.dateISO + 'T' + (v.time || '09:00')).getTime();
    if (Number.isFinite(at) && at <= now && at > lastPassed) lastPassed = at;
  }
  if (!lastPassed) return 0;
  const arr = loadCareQuestions();
  const stamp = new Date(lastPassed).toISOString();
  let n = 0;
  arr.forEach(q => {
    if (q.askedAt) return;
    const created = Date.parse(q.createdAt || '');
    if (Number.isFinite(created) && created <= lastPassed) { q.askedAt = stamp; n += 1; }
  });
  if (n) {
    saveCareQuestions(arr);
    try { trackProductEvent('care_questions_auto_archived', { archivedCount: n }); } catch (e) {}
    try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  }
  return n;
}

let _rptLastSummary = null;
async function openVisitSummary(source) {
  const page = document.getElementById('reportModal');
  if (!page) return;
  _rptEditing = false;   // 每次打開都回到閱讀狀態
  autoArchiveCareQuestions();
  pruneVisitSummaryData();
  _rptPeriod = visitSummaryPeriod();
  syncVisitSummaryTabs();
  page.classList.add('show');
  page.setAttribute('aria-hidden', 'false');
  try { trackProductEvent('visit_summary_opened', { periodDays: _rptPeriod, source: source || 'unknown' }); } catch (e) {}
  await loadVisitSummaryInto(_rptPeriod);
}
function closeVisitSummary() {
  const page = document.getElementById('reportModal');
  if (!page) return;
  page.classList.remove('show');
  page.setAttribute('aria-hidden', 'true');
}

/* 開頁順序（Edward 2026-07-29：「不要顯示整理中」）：
     1. 本機資料先畫——在家量的、吃藥、要問的問題都在這支手機裡，開頁就有東西
     2. 有上次的快照就用快照（診間離線時，時間軸也還在）
     3. 伺服器回來就換成完整那一份
   日期範圍當場算，不必等任何人。 */
async function loadVisitSummaryInto(days) {
  const line = document.getElementById('rptPeriodLine');
  const coverage = s => muneaT('visit.coverage', '涵蓋 {from} – {to}',
    { from: rptShortDate(s.from), to: rptShortDate(s.to) });

  const local = buildLocalVisitSummary(days);
  const snap = loadVisitSummarySnapshot(days);
  // 快照有完整時間軸，比本機這份多；但本機的數字是此刻最新的，所以疊上去。
  _rptLastSummary = snap && snap.summary
    ? Object.assign({}, snap.summary, {
        vitals: local.vitals.length ? local.vitals : snap.summary.vitals,
        medication: local.medication.length ? local.medication : snap.summary.medication,
        timelinePending: true,
      })
    : local;
  renderVisitSummary(_rptLastSummary);
  if (line) line.textContent = coverage(_rptLastSummary);

  const fresh = await fetchVisitSummary(days);
  if (fresh) {
    _rptLastSummary = fresh;
    renderVisitSummary(fresh);
    if (line) line.textContent = coverage(fresh);
    return;
  }
  // 連不上：本機那幾塊照樣留著給醫生看，但時間軸要明講是缺的，不能裝成「沒事發生」
  _rptLastSummary = Object.assign({}, _rptLastSummary, {
    timelinePending: false,
    timelineFailed: !(_rptLastSummary.timeline && _rptLastSummary.timeline.length),
  });
  renderVisitSummary(_rptLastSummary);
}
function syncVisitSummaryTabs() {
  document.querySelectorAll('#rptPeriodTabs .seg-btn').forEach(b => {
    b.classList.toggle('on', parseInt(b.dataset.days, 10) === _rptPeriod);
  });
}
window.__muneaOpenVisitSummary = openVisitSummary;

/* 摘要轉純文字——分享給家人、複製，也是 PDF 失敗時的退路。
   一樣只搬事實，不加任何一句解讀。 */
function visitSummaryAsText(summary) {
  const companion = (typeof cname === 'function' ? cname() : muneaT('app.shortName', '沐寧'));
  const footer = muneaT('visit.footer', '{companion}整理 · 家屬提供的紀錄，非醫療診斷', { companion });
  const patientName = visitSummaryPatientName();
  // 純文字版跟 PDF 是同一份摘要，姓名要一致——不然兩份給出去的東西身分不同
  const lines = [muneaT('visit.summaryTitle', '就診摘要') + (patientName ? ' · ' + patientName : '')];
  if (summary) lines.push(muneaT('visit.coverage', '涵蓋 {from} – {to}', { from: summary.from, to: summary.to }));
  const qs = (typeof openCareQuestions === 'function') ? openCareQuestions() : [];
  if (qs.length) {
    lines.push('', '【' + muneaT('visit.questionsTitle', '這次想問醫生') + '】');
    qs.forEach((q, i) => lines.push((i + 1) + '. ' + muneaSafeDisplayText(q.text, '')));
  }
  if (summary && summary.timeline && summary.timeline.length) {
    lines.push('', '【' + muneaT('visit.timelineTitle', '這段期間發生的事') + '】');
    summary.timeline.forEach(e => {
      lines.push(rptShortDate(e.date) + ' ' + (VISIT_SUMMARY_MARK[e.kind] || '·') + ' ' + e.text + (e.detail ? '（' + e.detail + '）' : ''));
    });
    lines.push(muneaT('visit.legend', '● 長輩自己說的　▲ 在家量的　✕ 用藥紀錄'));
    if (summary.timelineOmitted > 0) {
      lines.push(muneaT('visit.timelineOmitted', '另有 {n} 筆較早的紀錄沒有列出來。', { n: summary.timelineOmitted }));
    }
  }
  if (summary && summary.vitals && summary.vitals.length) {
    lines.push('', '【' + muneaT('visit.vitalsTitle', '在家量的') + '】');
    summary.vitals.forEach(v => lines.push(v));
    if (summary.baselineNote) lines.push(summary.baselineNote);
  }
  if (summary && summary.medication && summary.medication.length) {
    lines.push('', '【' + muneaT('visit.medTitle', '藥實際吃了沒') + '】');
    summary.medication.forEach(m => lines.push(m.name + '：'
      + muneaT('visit.medCounts', '排 {scheduled} 次 · 吃了 {taken} 次', { scheduled: m.scheduled, taken: m.taken })
      + (m.missed ? '　' + muneaT('visit.medMissed', '其中 {n} 次沒吃', { n: m.missed }) : '')));
  }
  if (summary && summary.partial && summary.partial.length) {
    lines.push('', muneaT('visit.partialNotePrint', '{names}這次沒有讀到，這一頁不是完整的。',
      { names: visitPartialNames(summary.partial) }));
  }
  lines.push('', footer);
  return lines.join('\n');
}

/* 摘要 → 一份自成一體的 A4 HTML，餵給原生外掛轉 PDF。
   為什麼要另外組一份、不直接印畫面：摘要面板是可滾動的子頁，直接印會拿到
   App 的殼＋被裁掉的捲動內容。這份只有摘要本身，版面完全可控、每一份長一樣。
   樣式全部行內寫死：離屏 webview 載入時 baseURL 是 nil，外部 CSS／字型根本不會被載到。

   ── 這一頁的設計前提（決定了下面每一個選擇）───────────────────
   ① 醫生大約 60 秒看完 → 可掃讀優先於好看。標題列、區塊標、數字對齊
      都是為了「眼睛一路往下不用回頭」。
   ② **診所印表機常常是黑白的** → 層級必須在灰階下就成立。顏色只作點綴，
      任何意義都同時由字重／級數／線條承載，不單靠顏色。
   ③ 不得有警示色（醫材紅線）——沒有紅、沒有橘、沒有底色分級。
      時間軸三種來源用「形狀」區分，因為醫師要分辨的是可信度不是嚴重度。
   ④ 字型吃系統：標題用襯線（沐寧頁面大標本來就是襯線，紙面也才有文件的重量），
      內文用系統無襯線。數字一律 tabular-nums 才對得齊。
   ⑤ 可能超過一頁（60 天資料多），所以每個區塊都不准被切開。 */
function visitSummaryAsHTML(summary) {
  const qs = (typeof openCareQuestions === 'function') ? openCareQuestions() : [];
  const companion = (typeof cname === 'function' ? cname() : muneaT('app.shortName', '沐寧'));
  const period = summary
    ? muneaT('visit.coverage', '涵蓋 {from} – {to}', { from: summary.from, to: summary.to })
    : '';
  const sec = label => '<h2>' + rptEsc(label) + '</h2>';
  const rows = [];

  // 抬頭走「信紙」結構：上面一行品牌，下面一行文件標題。
  //
  // Edward 2026-07-30 指正兩次：先是「報告沒有品牌 Logo 與名稱」，
  // 然後是「Logo 與 Logo 字不是有圖嗎？不要自己自創，要符合品牌設計規範」。
  // 我第一版整個省掉品牌（判斷錯了），第二版自己用向量重畫一個水滴（更錯——
  // 品牌標記不是可以自由發揮的東西）。這一版用**真的資產**與**官網的鎖定式**。
  //
  // 標記：web/src/visit-summary-logo.js（現行 App Icon 的透明圓角版 base64）。
  //   為什麼內嵌：ExportPlugin.swift 用 baseURL: nil 載這份 HTML，相對路徑會破圖。
  // 文字標：照官網 app-site/warm.css 的 .logo 鎖定式原樣搬過來——
  //   Poppins 700、字距 -.025em、「Mu」墨色 +「nea」主色、「沐寧」.78em 左距 .41em。
  //   這不是我挑的排版，是既有規範，所以照抄不改。
  //
  // 分兩行而不是塞進標題列，是因為醫生要先知道「這是什麼文件」——
  // 品牌是出處（安靜地放在信紙頭），標題才是主角。
  const brandLogo = (typeof window !== 'undefined' && window.MUNEA_VISIT_SUMMARY_LOGO) || '';
  // 文字標的字體：Poppins 700 只子集化 "Munea" 五個字母（0.8KB）。
  // 官網是從 Google CDN 載 Poppins，但這份 HTML 走 baseURL: nil 的離屏 webview，
  // 載不到任何外部資源——不內嵌的話字形會退回系統無襯線，文字標就不是品牌了
  // （Edward 2026-07-30：「Munea 的字粗字體也有問題」，根因就是這個）。
  const brandFont = (typeof window !== 'undefined' && window.MUNEA_VISIT_SUMMARY_WORDMARK_FONT) || '';
  const patientName = visitSummaryPatientName();
  rows.push('<header>'
    + '<div class="logo">'
    // 圖載不到時只是少一個標記，文字標照樣在——紙上不會出現破圖，也不會沒有出處
    +   (brandLogo ? '<img class="logo-mark" src="' + brandLogo + '" alt="" />' : '')
    +   '<span class="logo-word">Mu<b>nea</b><span class="logo-zh">沐寧</span></span>'
    + '</div>'
    + '<div class="title"><h1>' + rptEsc(muneaT('visit.summaryTitle', '就診摘要')) + '</h1>'
    // 姓名跟標題同一條基線：醫生拿起這張紙，先確認「這是誰的」再讀內容。
    // 沒填就整個不印——不留空欄位（文件上的空欄位看起來像漏填）。
    +   (patientName
      ? '<span class="patient">' + rptEsc(patientName) + '</span>'
      : '')
    +   '<span class="period">' + rptEsc(period) + '</span></div>'
    + '</header>');

  // ① 想問醫生＝這張紙存在的理由，所以是唯一有底色、字也最大的一塊
  if (qs.length) {
    rows.push('<section class="ask">' + sec(muneaT('visit.questionsTitle', '這次想問醫生')) + '<ul>');
    // 編號自己畫：::marker 的 color 在各家排版引擎支援不一致，
    // 用 span 才保證印出來是主色、而且對得齊
    qs.forEach((q, i) => rows.push('<li><span class="n">' + (i + 1) + '</span>'
      + rptEsc(muneaSafeDisplayText(q.text, '')) + '</li>'));
    rows.push('</ul></section>');
  }

  // ② 時間軸
  if (summary && summary.timeline && summary.timeline.length) {
    rows.push('<section>' + sec(muneaT('visit.timelineTitle', '這段期間發生的事')) + '<table class="tl">');
    summary.timeline.forEach(e => {
      rows.push('<tr><td class="d">' + rptEsc(rptShortDate(e.date)) + '</td>'
        + '<td class="m">' + (VISIT_SUMMARY_MARK[e.kind] || '·') + '</td>'
        + '<td>' + rptEsc(e.text)
        + (e.detail ? '<span class="det">' + rptEsc(e.detail) + '</span>' : '') + '</td></tr>');
    });
    rows.push('</table><p class="legend">'
      + rptEsc(muneaT('visit.legend', '● 長輩自己說的　▲ 在家量的　✕ 用藥紀錄')) + '</p>');
    // 截斷一定要說出來——悄悄少幾筆會讓醫師以為這就是全部
    if (summary.timelineOmitted > 0) {
      rows.push('<p class="note">'
        + rptEsc(muneaT('visit.timelineOmitted', '另有 {n} 筆較早的紀錄沒有列出來。', { n: summary.timelineOmitted }))
        + '</p>');
    }
    rows.push('</section>');
  }

  // ③④ 在家量的 ＋ 藥實際吃了沒：**併排兩欄**。
  //     兩邊都是短清單，各佔一整列的話 A4 的寬度整片浪費，而且醫生的視線要
  //     橫跨整頁才讀到一個數字。併排之後兩塊都在視線範圍內，一眼看完。
  //     只有一邊有資料時自動吃滿整列。
  const hasVitals = !!(summary && summary.vitals && summary.vitals.length);
  const hasMeds = !!(summary && summary.medication && summary.medication.length);
  if (hasVitals || hasMeds) {
    rows.push('<div class="cols">');
    if (hasVitals) {
      rows.push('<section>' + sec(muneaT('visit.vitalsTitle', '在家量的')) + '<table class="kv">');
      summary.vitals.forEach(v => {
        // 「血壓 128/82 · 量了 14 天」→ 拆成項目／數值兩欄
        const cut = String(v).indexOf(' ');
        rows.push('<tr><th>' + rptEsc(cut > 0 ? v.slice(0, cut) : v) + '</th>'
          + '<td>' + rptEsc(cut > 0 ? v.slice(cut + 1) : '') + '</td></tr>');
      });
      rows.push('</table>');
      if (summary.baselineNote) rows.push('<p class="note">' + rptEsc(summary.baselineNote) + '</p>');
      rows.push('</section>');
    }
    if (hasMeds) {
      // 只給次數不給服藥率——百分比讀起來就是評分，評分就是判斷
      rows.push('<section>' + sec(muneaT('visit.medTitle', '藥實際吃了沒')) + '<table class="kv">');
      summary.medication.forEach(m => {
        rows.push('<tr><th>' + rptEsc(m.name) + '</th><td>'
          + rptEsc(muneaT('visit.medCounts', '排 {scheduled} 次 · 吃了 {taken} 次',
            { scheduled: m.scheduled, taken: m.taken }))
          + (m.missed
            ? '<span class="det">' + rptEsc(muneaT('visit.medMissed', '其中 {n} 次沒吃', { n: m.missed })) + '</span>'
            : '')
          + '</td></tr>');
      });
      rows.push('</table></section>');
    }
    rows.push('</div>');
  }

  // 缺料要講——一份少了血壓的摘要看起來就像「他都沒量」
  if (summary && summary.partial && summary.partial.length) {
    rows.push('<p class="note incomplete">'
      + rptEsc(muneaT('visit.partialNotePrint', '{names}這次沒有讀到，這一頁不是完整的。',
        { names: visitPartialNames(summary.partial) })) + '</p>');
  }

  // 頁尾也帶品牌名——這張紙被影印、抬頭被裁掉的時候，出處還在。
  // 品牌名是專有名詞，不進 i18n 目錄（不該被翻譯），所以另外接在前面。
  rows.push('<footer><b>沐寧 Munea</b> · '
    + rptEsc(muneaT('visit.footer', '{companion}整理 · 家屬提供的紀錄，非醫療診斷', { companion }))
    + '</footer>');

  // lang 跟著 App 語系走：離屏 webview 的斷行與字型選擇吃這個屬性，
  // 寫死 zh-Hant 會讓日文那份用中文字形排版。
  const lang = muneaLocale() === 'zh-TW' ? 'zh-Hant' : muneaLocale();
  return '<!doctype html><html lang="' + rptEsc(lang) + '"><head><meta charset="utf-8">'
    + '<style>'
    // 取自 web/src/styles.css 的 :root（Edward 2026-07-03 定色），紙面只用其中最低限度的幾個
    // 取自 web/src/styles.css 的 :root（Edward 2026-07-03 定色），紙面只用其中最低限度的幾個
    // 定色照 docs/產品設計期待-對齊憲章.md，Edward 2026-07-30 拍板補充：
    // **主企業色是薄荷綠，不是深綠**；深綠依規範只准做文字強調。
    // 所以這裡不叫 --teal（那個名字會讓後人以為品牌主色是深綠），
    // 改用兩個講清楚用途的名字：
    //   --mint-deep   #2E8A83  薄荷綠的深階 → **線條與來源符號**，不當內文色
    //   --logo-orange #F4A261  Logo 上那顆橘（Edward 7/30 拍板）→ 只給品牌相關
    //
    // 為什麼區塊標回墨色、不用薄荷綠深階：實測 #2E8A83 對白紙是 4.13:1，
    // 而區塊標是 9.5pt 粗體——WCAG 的「大字」要 ≥11.5pt 粗體才算，所以這個
    // 組合沒過 AA（4.5:1）。憲章那條「不准淡色字配淡色底」就是在講這件事。
    // 憲章原文是「文字只用白／石墨黑」，所以文字回石墨黑（11.6:1），
    // 品牌與層級靠「線條＋字重＋級數」承載——這一頁本來就要求層級在灰階下
    // 也成立，那顏色對標題就只是裝飾，裝飾不該犧牲可讀性。
    //
    // 文字標的「nea」是例外，仍用薄荷綠深階：那是品牌鎖定式的一部分，
    // WCAG 對 logotype 明文豁免對比要求（1.4.3 例外條款），而且官網用的是
    // 更淡的 #3AA8A0——紙面已經加深一階了。
    + ':root{--ink:#3A352E;--muted:#5A6963;--mint-deep:#2E8A83;'
    +   '--logo-orange:#F4A261;--mint:#E8F2EE;--line:#D9D3C7}'
    // 內嵌字體要排在最前面，@font-face 必須先宣告才輪得到後面的 font-family
    + (brandFont
      ? '@font-face{font-family:"Munea Wordmark";src:url(' + brandFont + ') format("woff2");'
        + 'font-weight:700;font-style:normal;font-display:block}'
      : '')
    + '@page{size:A4;margin:15mm 14mm 12mm}'
    + '*{box-sizing:border-box}'
    // 底色要印得出來（WKWebView.createPDF 吃這個屬性），否則問題區塊會變全白
    + 'html{-webkit-print-color-adjust:exact;print-color-adjust:exact}'
    + 'body{margin:0;color:var(--ink);font-size:10.5pt;line-height:1.6;'
    +   'font-family:-apple-system,"PingFang TC","Hiragino Sans","Heiti TC",sans-serif;'
    +   'font-variant-numeric:tabular-nums}'

    // 抬頭：標題與期間同基線，下面一條 1.5pt 實線＝這一頁唯一的品牌動作
    + 'header{border-bottom:1.5pt solid var(--mint-deep);padding-bottom:5pt}'
    // 信紙頭：標記與品牌名，級數刻意壓小——出處不該跟文件標題爭
    // 品牌鎖定式：比例照官網 .logo（標記 30px 對字級 22px、間距 11px），
    // 換算成紙面級數後等比縮小。字型 Poppins 在離屏 webview 載不到，
    // 退回系統無襯線——字重與字距照規範，形不走樣。
    + '.logo{display:flex;align-items:center;gap:.5em;margin-bottom:3pt;'
    +   'font-family:"Munea Wordmark",Poppins,-apple-system,"PingFang TC",sans-serif;'
    +   'font-weight:700;font-size:10.5pt;letter-spacing:-.025em;color:var(--ink)}'
    + '.logo-mark{width:14.3pt;height:14.3pt;flex:none;object-fit:contain}'
    + '.logo-word{line-height:1;white-space:nowrap}'
    + '.logo-word b{color:var(--mint-deep);font-weight:700}'
    + '.logo-zh{font-family:"Noto Sans TC","PingFang TC",sans-serif;font-size:.78em;'
    +   'font-weight:700;letter-spacing:.04em;margin-left:.41em}'
    + '.title{display:flex;align-items:baseline;justify-content:space-between;gap:12pt}'
    + 'h1{font-family:"Songti TC","Noto Serif TC",Georgia,serif;font-size:18pt;font-weight:700;'
    +   'margin:0;line-height:1.2}'
    // 姓名比期間顯眼（它是身分不是註記），但比標題小——標題仍是文件主角。
    // margin-right:auto 把期間推到最右，姓名留在標題旁邊。
    + '.patient{font-size:11pt;font-weight:700;color:var(--ink);white-space:nowrap;'
    +   'margin-right:auto;padding-bottom:1pt}'
    + '.period{font-size:9pt;color:var(--muted);white-space:nowrap}'

    // 區塊標：不用 uppercase（對中文完全無效），字距只給極小值——
    // 中文被拉開字距看起來是排錯不是設計。層級靠「字重＋主色＋下方細線」建立，
    // 這三者在黑白印表機下也還在（線與字重不吃顏色）。
    + 'section{margin-top:12pt;page-break-inside:avoid;break-inside:avoid}'
    + 'h2{font-size:9.5pt;font-weight:700;letter-spacing:.02em;color:var(--ink);'
    +   'margin:0 0 4pt;padding-bottom:2pt;border-bottom:.5pt solid var(--line)}'

    // ① 想問醫生：唯一有底色、字最大的一塊（這張紙存在的理由）
    + '.ask{background:var(--mint);border-radius:2pt;padding:9pt 11pt 10pt;margin-top:10pt}'
    + '.ask h2{border-bottom-color:rgba(35,108,102,.28);margin-bottom:5pt}'
    + '.ask ul{margin:0;padding:0;list-style:none}'
    + '.ask li{position:relative;padding-left:18pt;font-size:11.5pt;line-height:1.5;margin:4pt 0}'
    + '.ask .n{position:absolute;left:0;top:0;width:13pt;text-align:right;'
    +   'font-weight:700;color:var(--ink)}'

    // 表格：只用細橫線，不用外框不用斑馬紋——紙上格線越少越好讀
    + 'table{width:100%;border-collapse:collapse}'
    + 'th,td{padding:3.5pt 0;vertical-align:baseline;border-bottom:.5pt solid var(--line);text-align:left}'
    + 'tr:last-child th,tr:last-child td{border-bottom:0}'
    + '.tl .d{width:34pt;color:var(--muted);font-size:9pt;white-space:nowrap}'
    + '.tl .m{width:14pt;text-align:center;color:var(--mint-deep)}'
    + '.det{display:block;font-size:8.5pt;font-weight:400;color:var(--muted);margin-top:1pt}'

    // 在家量的／藥：併排兩欄，數值緊跟在項目後面不貼頁緣
    + '.cols{display:flex;gap:22pt;align-items:flex-start;'
    +   'page-break-inside:avoid;break-inside:avoid}'
    + '.cols>section{flex:1;min-width:0;margin-top:12pt}'
    + '.kv th{font-weight:400;color:var(--muted);white-space:nowrap;padding-right:10pt}'
    + '.kv td{text-align:right;font-weight:600}'

    + '.legend{font-size:8.5pt;color:var(--muted);margin:5pt 0 0}'
    + '.note{font-size:8.5pt;color:var(--muted);margin:4pt 0 0;line-height:1.5}'
    // 缺料那句要看得見（但不用警示色——一條左側細線就夠）
    + '.incomplete{margin-top:11pt;padding-left:7pt;border-left:2pt solid var(--line)}'

    + 'footer{margin-top:18pt;padding-top:5pt;border-top:.5pt solid var(--line);'
    +   'font-size:8.5pt;color:var(--muted);text-align:center}'
    + 'footer b{color:var(--mint-deep);font-weight:700}'
    + '</style></head><body>' + rows.join('') + '</body></html>';
}

/* 原生匯出外掛（ios/App/App/ExportPlugin.swift）。沒有就回 null，呼叫端自己退回文字分享。 */
function muneaExportPlugin() {
  return (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.Export) || null;
}
async function exportVisitSummaryPdf(summary) {
  const plugin = muneaExportPlugin();
  if (!plugin || typeof plugin.sharePdf !== 'function') return { ok: false, error: 'plugin_unavailable' };
  try {
    const stamp = summary && summary.to ? String(summary.to) : '';
    const r = await plugin.sharePdf({
      html: visitSummaryAsHTML(summary),
      filename: muneaT('visit.exportFilename', '就診摘要') + (stamp ? '-' + stamp : ''),
    });
    return { ok: true, completed: !!(r && r.completed) };
  } catch (e) {
    return { ok: false, error: (e && (e.code || e.message)) || 'export_failed' };
  }
}


async function aiAddMedReminder(a) {
  const rawName = String((a && a.name) || '').trim();
  const name = (rawName && muneaIsCleanDisplayText(rawName)) ? rawName : '';
  let slots = (a && Array.isArray(a.slots))
    ? a.slots.map(canonicalMedicationSlot).filter(Boolean)
    : [];
  slots = [...new Set(slots)];
  if (!name || !slots.length) return { ok: false, error: 'medication_name_or_slots_required' };
  const meds = (typeof loadMeds === 'function') ? loadMeds() : [];
  const med = {
    name,
    time: slots.join('、'),
    days: canonicalMedicationDuration(a && a.days),
    by: '',
    photo: '',
  };
  ensureMedReminderId(med);
  const nextMeds = meds.filter(m => String(m && m.id) !== String(med.id));
  nextMeds.push(med);
  try { localStorage.setItem('munea.meds', JSON.stringify(nextMeds)); } catch (e) { return { ok: false, error: 'local_write_failed' }; }
  try { if (typeof syncPush === 'function') syncPush('meds', nextMeds); } catch (e) {}
  let cloud = null;
  try { cloud = await syncMedicationReminder(med); } catch (e) {}
  try { if (typeof updateMedCount === 'function') updateMedCount(); } catch (e) {}
  try { if (typeof renderMedList === 'function') renderMedList(); } catch (e) {}
  try { if (window.MuneaNotify) window.MuneaNotify.sync(); } catch (e) {}
  return { ok: true, name, slots, reminderId: med.id, persistence: cloud && cloud.ok ? 'cloud' : 'device' };
}
// 聊聊語音收到 AI 的「幫你做進 App」指令 → 執行 + 螢幕輕提示（寧寧的口頭確認由 AI 那頭講）
async function handleVoiceAction(action, args) {
  args = args || {};
  if (action === 'update_conversation_locale') {
    const locale = window.MuneaI18n
      ? window.MuneaI18n.normalize(args.locale)
      : String(args.locale || '');
    if (!['zh-TW', 'en', 'ja', 'es'].includes(locale)) {
      return { ok: false, error: 'unsupported_locale' };
    }
    const current = latestTrustedLocaleContext || {};
    const preferred = [
      locale,
      ...(Array.isArray(current.preferredLanguages)
        ? current.preferredLanguages
        : muneaPreferredLanguages()),
    ].filter((value, index, all) => value && all.indexOf(value) === index);
    const response = await brainPost('/account-bootstrap', accountBootstrapPayload('patch', {
      localeContext: {
        conversationLocale: locale,
        preferredLanguages: preferred,
      },
    }));
    if (!response || !response.ok) {
      return { ok: false, error: 'locale_preference_write_failed' };
    }
    captureTrustedLocaleContext(response);
    return { ok: true, locale, persistence: 'cloud' };
  }
  if (action === 'set_clinic_reminder') {
    const r = await aiAddVisitReminder({
      title: args.title, dateISO: args.date, time: args.time, remindBefore: args.remindBefore,
    });
    if (typeof toast === 'function') {
      // 提前多久也要寫在畫面上：她講的跟畫面寫的必須一致，
      // 不然長輩不知道到底哪個算數。
      toast(r.ok
        ? muneaT('visit.reminderSetToastWithLead', '看診提醒設好了：{title} · {label}（{lead}）',
          { title: r.title, label: r.label, lead: visitLeadSpoken(r.remindBefore) })
        : muneaT('visit.reminderDateUnclear', '看診日期我沒抓到，你再說一次日期好嗎'));
    }
    return r;
  }
  if (action === 'add_care_question') {
    const r = await aiAddCareQuestion({ question: args.question });
    if (typeof toast === 'function') {
      // 失敗有兩種，不能都說「我沒聽清楚」——清單滿了他再重講一百次也沒用，
      // 只會讓他覺得自己講話講不清楚。要講真正的原因。
      let msg;
      if (r.ok) {
        msg = muneaT('visit.questionSaved', '記下來了，看醫生前我會提醒你（{n} 個問題）', { n: r.count });
      } else if (r.error === 'question_list_full') {
        msg = muneaT('visit.questionsFull', '已經記滿 {n} 題了，先刪掉一題再加', { n: r.max || CARE_Q_MAX });
      } else {
        msg = muneaT('visit.questionUnheard', '這個問題我沒聽清楚，你再說一次好嗎');
      }
      toast(msg);
    }
    return r;
  }
  if (action === 'set_medication_reminder') {
    const r = await aiAddMedReminder({ name: args.name, slots: args.slots, days: args.days });
    if (typeof toast === 'function') toast(r.ok
      ? muneaT(
        'medication.action.added',
        '用藥提醒已設定：{slots}服用「{name}」',
        { slots: localizedMedicationSlotList(r.slots), name: r.name },
      )
      : muneaT(
        'medication.action.missingSchedule',
        '還沒確認服藥時間，請再說一次。',
      ));
    return r;
  }
  if (action === 'set_personal_event') {
    // 約會/聚餐/出遊 → 揪一攤活動帳本（7/16 Edward：這類事不准再進看診/用藥）
    const fn = window.__muneaAddPersonalEvent;
    const r = fn ? await fn({ title: args.title, dateISO: args.date, time: args.time, place: args.place }) : { ok: false, error: 'unsupported_action' };
    if (typeof toast === 'function') toast(r.ok ? muneaT('schedule.savedToast', '行程記好了：{title} · {label}', { title: r.title, label: r.label }) : muneaT('schedule.dateUnclear', '日期時間我沒抓到，你再說一次好嗎'));
    return r;
  }
  if (action === 'create_family_activity') {
    const fn = window.__muneaAddFamilyActivity;
    const r = fn ? await fn({
      kind: args.kind, dateISO: args.date, time: args.time, title: args.title,
      options: args.options, prizes: args.prizes, questionCount: args.questionCount,
      stepGoal: args.stepGoal,
    }) : { ok: false, error: 'unsupported_action' };
    if (typeof toast === 'function') {
      // 缺東西要講清楚缺什麼——說「我沒聽清楚」會讓他重講一百次都沒用
      let msg;
      if (r.ok) msg = muneaT('activity.voiceCreated', '{title}發出去了：{label}', { title: r.title, label: r.label });
      else if (r.error === 'vote_needs_two_options') msg = muneaT('activity.voteNeedsTwoOptions', '投票至少要兩個選項');
      else if (r.error === 'vote_question_required') msg = muneaT('activity.voiceVoteQuestionNeeded', '要投什麼？先告訴我題目');
      else if (r.error === 'draw_prize_required') msg = muneaT('activity.fillPrizeFirst', '先填獎品，抽起來才有趣');
      else if (r.error === 'activity_time_in_past') msg = muneaT('activity.voicePastDate', '那個日子已經過了，換一天好嗎');
      // 種類不對是她那邊聽岔了、不是他講錯話——不可以回「日期我沒抓到」害他一直重講日期
      else if (r.error === 'unsupported_activity_kind') msg = muneaT('activity.voiceKindUnsupported', '這種活動我還開不了，家人那頁可以自己開');
      else msg = muneaT('activity.voiceDateUnclear', '日期我沒抓到，你再說一次好嗎');
      toast(msg);
    }
    return r;
  }
  if (action === 'send_family_relay') {
    return await createFamilyRelay(args.recipientName, args.message);
  }
  return { ok: false, error: 'unsupported_action' };
}
window.__muneaHandleVoiceAction = handleVoiceAction;

/* ===== VoiceProvider：先立合約，之後可換 Gemini Live / Interactions，不綁死 App 核心 ===== */
function makeSessionId(prefix = 'session') {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}
function developerConfig() {
  return window.MUNEA_DEV_CONFIG || {};
}
function isLocalDevHost() {
  return ['localhost', '127.0.0.1', ''].includes(location.hostname) || location.protocol === 'file:';
}
function isDeveloperBypassAllowed() {
  const cfg = developerConfig();
  return cfg.enabled === true && (cfg.allowNonLocalhost === true || isLocalDevHost());
}
function usesDevelopmentDirectCall() {
  const cfg = developerConfig();
  return isDeveloperBypassAllowed() && cfg.bypassCallControl === true;
}
// --gateway 開發包（2026-07-18 專用真測試帳號施工）：開發者模式開著、但不走本機直連假資料，
// 走真總機領證——這時「開發者鈕」該叫真帳號登入，不是造假證 session。
function isGatewayDeveloperProfile() {
  return isDeveloperBypassAllowed() && !usesDevelopmentDirectCall();
}
function developerFixtureDate(daysAgo) {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - daysAgo);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function developerFixtureVitals(name, offset) {
  const log = {};
  for (let daysAgo = 27; daysAgo >= 0; daysAgo--) {
    const rhythm = 27 - daysAgo + offset;
    log[developerFixtureDate(daysAgo)] = {
      steps: 5200 + (rhythm % 7) * 510,
      sleepHours: +(6.3 + (rhythm % 5) * 0.3).toFixed(1),
      hr: 66 + (rhythm % 8),
      spo2: 96 + (rhythm % 3),
      bpSys: 116 + (rhythm % 7),
      bpDia: 72 + (rhythm % 5),
    };
  }
  const latest = log[developerFixtureDate(0)];
  // 開發示範也帶今日心情標籤（跟正式資料同格式），讓家人頁左「心情」右「平安燈」的分工看得出來
  // 六種心情各給一個人，家人頁一次看得完（Edward 2026-08-01 要檢查六種都顯示得出來）。
  // 原本只有開心／平穩／疲累三種輪流——焦慮與生氣根本沒機會出現在示範畫面上。
  const fixtureMoods = [
    ['開心', 'happy'], ['愉快', 'glad'], ['平靜', 'calm'],
    ['低落', 'down'], ['焦慮', 'anxious'], ['生氣', 'angry'],
  ];
  const mm = fixtureMoods[((offset / 2) | 0) % fixtureMoods.length];
  return { name, nick: name, day: '今天', updatedAt: Date.now(), mood: { label: mm[0], key: mm[1], date: developerFixtureDate(0) }, ...latest, log };
}
function seedDeveloperFixtures(cfg) {
  if (cfg.seedFixtures !== true) return;
  const fixtureVersion = cfg.fixtureVersion || 'v1';
  if (storageGet(DEV_FIXTURE_MARKER_KEY) === fixtureVersion && cfg.resetFixturesOnLaunch !== true) return;
  const profileName = cfg.profileName || 'Edward';
  const members = [
    { name: profileName, init: profileName[0] || '我', tint: 'p-me', self: true },
    { name: '媽媽', init: '媽', tint: 'p-ama', self: false },
    { name: '爸爸', init: '爸', tint: 'p-zhi', self: false },
    { name: '姊姊', init: '姊', tint: 'p-mei', self: false },
    { name: '哥哥', init: '哥', tint: 'p-zhi', self: false },
    { name: '阿姨', init: '姨', tint: 'p-ama', self: false },
    { name: '舅舅', init: '舅', tint: 'p-mei', self: false },
  ];
  storageSet('munea.personProfile', JSON.stringify({ name: profileName, nick: profileName, birth: '1990 年 3 月', city: '台北市中山區', avatar: '' }));
  storageSet('munea.plan', cfg.plan || 'pro');
  storageSet('munea.ptsBought', String(Number.isFinite(+cfg.purchasedPoints) ? +cfg.purchasedPoints : 700));
  storageSet('munea.familyGroupId', 'fam-edward-development');
  storageSet('munea.cloudPersonId', 'dev-edward-person');
  storageSet('munea.circleMembers', JSON.stringify(members));
  storageSet('munea.famVitals', JSON.stringify({
    'dev-family-mother': developerFixtureVitals('媽媽', 0),
    'dev-family-father': developerFixtureVitals('爸爸', 2),
    'dev-family-sister': developerFixtureVitals('姊姊', 4),
    'dev-family-brother': developerFixtureVitals('哥哥', 6),
    'dev-family-aunt': developerFixtureVitals('阿姨', 8),
    'dev-family-uncle': developerFixtureVitals('舅舅', 10),
  }));
  storageSet('munea.familyFeed2', JSON.stringify([
    '<b>媽媽</b>要我提醒你：週末回家一起吃飯',
    '<b>爸爸</b>今天走了 7,200 步，狀態很穩',
    '<b>姊姊</b>傳了一個愛心，晚點想和你聊聊',
  ]));
  const activityEnd = new Date();
  activityEnd.setDate(activityEnd.getDate() + 2);
  storageSet('munea.activities', JSON.stringify([{
    id: Date.now(),
    kind: 'walk',
    owner: profileName,
    names: ['媽媽', '爸爸', '姊姊'],
    title: '全家一起走路',
    goal: 30000,
    startISO: developerFixtureDate(0),
    days: 2,
    dateISO: developerFixtureDate(-2),
    dueTime: '20:00',
    dueLabel: `${activityEnd.getMonth() + 1}/${activityEnd.getDate()} 20:00 截止`,
  }]));
  storageSet(DEV_FIXTURE_MARKER_KEY, fixtureVersion);
}
function applyDeveloperBypass() {
  const cfg = developerConfig();
  if (!isDeveloperBypassAllowed()) return;
  if (cfg.skipOnboarding === true) storageSet(ONBOARDING_COMPLETED_KEY, 'true');
  seedDeveloperFixtures(cfg);
}
function authAnalyticsContext() {
  const auth = window.MuneaAuth;
  const state = auth && typeof auth.state === 'function' ? auth.state() : {};
  const cfg = developerConfig();
  const devBypass = isDeveloperBypassAllowed();
  const excluded = !!(state.developerMode || (devBypass && (cfg.analyticsExcluded === true || cfg.excludeAnalytics === true)));
  return {
    authProvider: state.provider || 'guest',
    developerMode: !!state.developerMode,
    analyticsExcluded: excluded,
    accountType: excluded ? 'developer' : 'user',
  };
}
function isAiDevDiagnosticsEnabled() {
  const debug = new URLSearchParams(location.search).get('debug');
  const auth = window.MuneaAuth;
  const state = auth && typeof auth.state === 'function' ? auth.state() : {};
  const cfg = developerConfig();
  return debug === 'ai' || debug === 'all' || state.developerMode || (isDeveloperBypassAllowed() && cfg.showAiDiagnostics !== false);
}
function compactList(value) {
  if (!value) return '-';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '-';
  return String(value || '-');
}
function renderAiDiagnostics() {
  const panel = $('#aiDevPanel');
  if (!panel) return;
  const enabled = isAiDevDiagnosticsEnabled();
  panel.hidden = !enabled;
  if (!enabled) return;
  const ctx = latestAiContext || {};
  const persona = ctx.personaLayer || {};
  const relationship = ctx.relationship || {};
  const guardian = ctx.guardian || {};
  const perception = ctx.perception || {};
  const memory = ctx.memory || {};
  const setText = (id, value) => { const el = $(id); if (el) el.textContent = value == null || value === '' ? '-' : String(value); };
  setText('#aiDevPersona', persona.templateId || currentAvatarId);
  setText('#aiDevRapport', relationship.rapportLevel || (latestRelationshipState && latestRelationshipState.rapportLevel) || 'new');
  setText('#aiDevGuardian', guardian.riskLevel || 'none');
  setText('#aiDevMemory', memory.count == null ? '-' : memory.count);
  setText('#aiDevSource', latestAiContextSource);
  setText('#aiDevPerception', compactList(perception.domains));
  setText('#aiDevTone', compactList(relationship.toneOverrideKeys || (latestRelationshipState && Object.keys(latestRelationshipState.toneOverrides || {}))));
  const json = $('#aiDevJson');
  if (json) {
    json.textContent = JSON.stringify({
      aiContext: latestAiContext,
      relationshipState: latestRelationshipState,
      voiceProvider: voiceProvider.mode,
      avatarMode: avatarRuntime.mode,
      analytics: authAnalyticsContext(),
    }, null, 2);
  }
}
function setLatestAiContext(context, source, relationshipState) {
  if (context) latestAiContext = context;
  if (relationshipState) latestRelationshipState = relationshipState;
  if (source) latestAiContextSource = source;
  renderAiDiagnostics();
}
async function refreshAiDiagnostics() {
  const panel = $('#aiDevPanel');
  if (!panel || panel.hidden) return null;
  const button = $('#aiDevRefresh');
  if (button) button.textContent = 'Loading';
  try {
    const response = await brainPost('/persona/context', {
      companionProfile: savedCompanionProfile,
      char: currentChar,
      text: 'developer diagnostics refresh',
      ...authAnalyticsContext(),
    });
    if (response) {
      latestRelationshipState = response.relationshipState || latestRelationshipState;
      setLatestAiContext({
        personaLayer: {
          templateId: response.templateId,
          displayName: response.displayName,
          personaArchetype: response.persona && response.persona.personaArchetype,
        },
        relationship: {
          rapportLevel: response.relationshipState && response.relationshipState.rapportLevel,
          hasRelationshipMemory: !!(response.relationshipState && response.relationshipState.relationshipMemory),
          toneOverrideKeys: Object.keys((response.relationshipState && response.relationshipState.toneOverrides) || {}),
        },
        guardian: {
          riskLevel: response.safety && response.safety.riskLevel,
          action: response.safety && response.safety.forceSafetyBoundary ? 'boundary' : 'allow',
        },
        perception: { domains: [], needsCurrentFacts: false },
        memory: { count: 0 },
      }, 'persona-context refresh', response.relationshipState);
    } else if (!latestAiContext) {
      setLatestAiContext(null, isStaticPreview() ? 'static preview' : 'refresh unavailable');
    }
    return response;
  } finally {
    if (button) button.textContent = 'Refresh';
  }
}
function analyticsContext(extra = {}) {
  return {
    templateId: currentAvatarId,
    avatarMode: avatarRuntime.mode,
    voiceProvider: voiceProvider.mode,
    voiceState: voiceProvider.state,
    companionTemplate: currentAvatarId,
    ...authAnalyticsContext(),
    ...extra,
  };
}
function trackProductEvent(eventName, properties = {}) {
  if (!eventName || isStaticPreview()) return Promise.resolve(null);
  const safeProperties = analyticsContext(properties);
  delete safeProperties.text;
  delete safeProperties.transcript;
  delete safeProperties.reply;
  return brainPost('/product-event', {
    eventName,
    sessionId: activeChatSessionId,
    source: 'web-prototype',
    properties: safeProperties,
  });
}
const VoiceCallDiagnostics = window.MuneaVoiceDiagnostics || null;
if (VoiceCallDiagnostics) {
  VoiceCallDiagnostics.setReporter((eventName, properties) => trackProductEvent(eventName, properties));
}
function voiceCallMark(stage, status, details) {
  try { return VoiceCallDiagnostics && VoiceCallDiagnostics.mark(stage, status, details); } catch (e) { return null; }
}
function voiceCallFail(stage, error, details) {
  try { return VoiceCallDiagnostics && VoiceCallDiagnostics.fail(stage, error, details); } catch (e) { return null; }
}
function voiceCallEnd(outcome, reason, details) {
  try { return VoiceCallDiagnostics && VoiceCallDiagnostics.end(outcome, { reason, ...(details || {}) }); } catch (e) { return null; }
}
function postTurnReview() {
  if (isStaticPreview() || !chatHistory.length) return Promise.resolve(null);
  return brainPost('/butler/post-turn', {
    history: chatHistory.slice(-12),
    char: currentChar,
    companionProfile: savedCompanionProfile,
    sessionId: activeChatSessionId,
    ...authAnalyticsContext(),
  }).then(response => {
    if (response) setLatestAiContext(response.aiContext, 'butler post-turn', response.relationshipState);
    if (!response && !postTurnReview._retried) {
      postTurnReview._retried = true;
      setTimeout(() => { postTurnReview().finally(() => { postTurnReview._retried = false; }); }, 10000);
    }
    return response;
  });
}

function isAvatarDebug() {
  return new URLSearchParams(location.search).get('debug') === 'avatar';
}
function requestedAvatarMode() {
  return avatarRuntime.resolveMode(currentAvatarId);
}
function premiumAvatarMode(mode = avatarRuntime.mode) {
  return mode === AVATAR_ENGINE_MODES.DITTO || mode === AVATAR_ENGINE_MODES.LIVE_AVATAR;
}
function avatarSessionPayload(action = 'start', extra = {}) {
  const mode = extra.mode || requestedAvatarMode();
  return {
    action,
    mode,
    requestedMode: mode,
    templateId: currentAvatarId,
    char: currentChar,
    displayName: companionDisplayName.trim() || templateFor().defaultName,
    ...extra,
  };
}
function updateAvatarDiagnostics(response) {
  const el = $('#avatarDiagnostics');
  if (!el) return;
  if (!isAvatarDebug()) {
    el.hidden = true;
    return;
  }
  const session = response && response.session ? response.session : avatarSession;
  if (!session) {
    el.hidden = false;
    el.textContent = 'avatar: local preview';
    return;
  }
  const fallback = session.fallbackReason ? ` / ${session.fallbackReason}` : '';
  el.hidden = false;
  el.textContent = `avatar: ${session.selectedMode} via ${session.provider || 'local-browser'}${fallback}`;
}
function applyAvatarSessionDecision(response) {
  if (!response || !response.ok || !response.session) {
    updateAvatarDiagnostics(response);
    return null;
  }
  avatarSession = response.session;
  avatarRuntime.setDecision(avatarSession);
  const sc = $('#chat');
  if (sc) {
    sc.dataset.avatarProvider = avatarSession.provider || 'local-browser';
    sc.dataset.avatarFallbackReason = avatarSession.fallbackReason || '';
  }
  updateAvatarDiagnostics(response);
  return avatarSession;
}
async function avatarSessionApi(action = 'start', extra = {}) {
  if (isStaticPreview()) {
    updateAvatarDiagnostics(null);
    return null;
  }
  return brainPost('/avatar-session', avatarSessionPayload(action, extra));
}
async function prepareAvatarSession(extra = {}) {
  avatarRuntime.setMode(requestedAvatarMode());
  const response = await avatarSessionApi('start', extra);
  const session = applyAvatarSessionDecision(response);
  trackProductEvent('avatar_session_started', {
    requestedMode: requestedAvatarMode(),
    selectedMode: session ? session.selectedMode : avatarRuntime.mode,
    provider: session ? session.provider : 'local-browser',
    fallbackReason: session ? session.fallbackReason : '',
  });
  return response;
}
async function recordAvatarUsage(text, audioMs = 0) {
  if (!premiumAvatarMode()) return;
  const durationMs = audioMs || Math.min(8000, Math.max(2200, (text ? text.length : 8) * 165));
  const response = await avatarSessionApi('complete', {
    mode: avatarRuntime.mode,
    selectedMode: avatarRuntime.mode,
    durationMs,
    estimatedDurationMs: durationMs,
  });
  const session = applyAvatarSessionDecision(response);
  trackProductEvent('avatar_session_completed', {
    durationMs,
    selectedMode: session ? session.selectedMode : avatarRuntime.mode,
    usageCommitted: !!(session && session.usageCommitted),
  });
}

const voiceProvider = {
  modes: VOICE_PROVIDER_MODES,
  mode: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
  state: 'idle',
  session: null,
  setState(st) {
    this.state = st;
    const sc = $('#chat');
    if (sc) sc.dataset.voiceState = st;
  },
  async connect(context = {}) {
    this.setState('connecting');
    const session = await brainPost('/voice-session', {
      char: currentChar,
      companionProfile: savedCompanionProfile,
      locale: muneaLocale(),
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      ...context,
    });
    this.session = session || {
      ok: false,
      provider: VOICE_PROVIDER_MODES.STATIC_FALLBACK,
      fallback: VOICE_PROVIDER_MODES.STT_CHAT_TTS,
      locale: muneaLocale(),
    };
    this.mode = this.session.provider || this.session.fallback || VOICE_PROVIDER_MODES.STT_CHAT_TTS;
    setLatestAiContext(this.session.aiContext, 'voice-session', this.session.relationshipState);
    this.setState('idle');
    return this.session;
  },
  async open(char) {
    if (!this.session) await this.connect({ char });
    return brainPost('/open', { char, locale: muneaLocale() });
  },
  async sendText({ history, char }) {
    this.setState('thinking');
    try {
      const response = await brainPost('/chat', { history, char, locale: muneaLocale(), companionProfile: savedCompanionProfile, userMood: (window.MM && window.MM.currentMood) ? window.MM.currentMood() : '', interests: loadInterests() });
      if (response) setLatestAiContext(response.aiContext, 'chat response', response.relationshipState);
      return response;
    } finally {
      this.setState('idle');
    }
  },
  async sendVoiceNote({ audio, mime, durationMs, char }) {
    this.setState('uploading');
    try {
      const response = await brainPost('/voice-note', { char, locale: muneaLocale(), audio, mime, durationMs, provider: this.mode });
      if (response) setLatestAiContext(response.aiContext, 'voice-note', response.relationshipState);
      return response;
    } finally {
      this.setState('idle');
    }
  },
  close() {
    this.session = null;
    this.setState('idle');
  },
};
window.MuneaVoiceProvider = voiceProvider;

// ===== 想聊的話題（興趣）：存本機、文字/語音聊天都帶給 AI 當開場方向＋接話素材 =====
const INTEREST_TOPICS = ['旅遊景點', '美食餐廳', '影劇戲劇', '新聞時事', '健康養生', '運動', '懷舊老歌', '園藝花草', '歷史故事', '寵物', '棋牌麻將', '天氣節氣'];
function loadInterests() {
  try { const a = JSON.parse(localStorage.getItem('munea.interests') || 'null'); return Array.isArray(a) ? a.filter(t => INTEREST_TOPICS.includes(t)).slice(0, 5) : []; }
  catch (e) { return []; }
}
function saveInterests(list) { try { localStorage.setItem('munea.interests', JSON.stringify((list || []).slice(0, 5))); } catch (e) {} }

// ===== 真即時語音（Gemini 3.1 Live）：MuneaVoiceProvider 的 live 模式 =====
// 架構：前端這支 → WebSocket 即時語音橋（engine/live_voice_server.py）。麥克風即時串流上去、聲音即時播回來、可打斷。
// 連哪裡：localStorage['munea.liveVoiceUrl']，沒設就走正式雲端（台灣機房 · 7/9 Edward 拍板正式上線推進）。
const LIVE_VOICE_URL_DEFAULT = 'wss://munea-voice-491603544409.asia-east1.run.app';
// 薄門通行碼：App 自動帶、用戶無感；擋「拿到網址直接來撥」的陌生流量（本機引擎沒開門檢查、帶了也無妨）
const MUNEA_APP_KEY = 'mnk_03d3a1545a3c5215b924c162c54e83f2ecd059e5';
const CALL_CONTROL_URL_DEFAULT = 'https://munea-call-control-fiu65jd4da-de.a.run.app';
let _clientReleaseInfoPromise = null;
async function clientReleaseInfo() {
  if (_clientReleaseInfoPromise) return _clientReleaseInfoPromise;
  _clientReleaseInfoPromise = (async () => {
    const fallback = {
      version: String((window.MuneaVersion && window.MuneaVersion.current) || ''),
      build: '',
      protocol: Number((window.MuneaVersion && window.MuneaVersion.callProtocol) || 0),
    };
    try {
      const plugin = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App;
      if (!plugin || typeof plugin.getInfo !== 'function') return fallback;
      const info = await plugin.getInfo();
      return {
        version: String((info && info.version) || fallback.version),
        build: String((info && info.build) || ''),
        protocol: fallback.protocol,
      };
    } catch (e) { return fallback; }
  })();
  return _clientReleaseInfoPromise;
}
const CallControl = {
  active: null,
  pending: null,
  heartbeatTimer: null,
  cancelled: false,
  generation: 0,
  url() {
    if (usesDevelopmentDirectCall()) return '';
    // Production must always use the release Gateway. A stale localStorage
    // override from an older test build must never route an installed App to
    // a retired controller or back to direct GPU access.
    const cfg = developerConfig();
    if (isDeveloperBypassAllowed() && cfg.callControlUrl) {
      return String(cfg.callControlUrl).replace(/\/$/, '');
    }
    return CALL_CONTROL_URL_DEFAULT;
  },
  async _headers(forceRefresh = false) {
    if (forceRefresh) {
      const auth = window.MuneaAuth;
      const token = auth && typeof auth.recoverRejectedSession === 'function'
        ? await auth.recoverRejectedSession()
        : null;
      if (!token) throw new Error('authentication_required');
      return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
    }
    const headers = await muneaAuthHeaders({ 'Content-Type': 'application/json' });
    delete headers['X-Munea-Key'];
    return headers;
  },
  async _fetch(endpoint, options = {}) {
    const send = async forceRefresh => fetch(endpoint, {
      ...options,
      headers: { ...(options.headers || {}), ...(await this._headers(forceRefresh)) },
    });
    const response = await send(false);
    if (response.status !== 401) return response;
    voiceCallMark('gateway_auth_recovery', 'pass', { endpoint: this.url() });
    return send(true);
  },
  async acquire(characterId) {
    const base = this.url();
    if (!base) throw new Error('call_control_not_configured');
    const generation = ++this.generation;
    this.cancelled = false;
    this._queueSeen = false;
    const idempotencyKey = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID() : ('call-' + Date.now() + '-' + Math.random());
    let accountRecoveryAttempted = false;
    const clientRelease = await clientReleaseInfo();
    while (!this.cancelled) {
      const personId = storageGet('munea.cloudPersonId') || '';
      const requestBody = {
        character_id: characterId || 'default',
        idempotency_key: idempotencyKey,
        app_version: clientRelease.version,
        app_build: clientRelease.build,
        client_protocol: clientRelease.protocol,
      };
      if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(personId)) {
        requestBody.person_id = personId;
      }
      const response = await this._fetch(base + '/v1/calls', {
        method: 'POST',
        body: JSON.stringify(requestBody),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error((result && result.detail) || ('call_control_http_' + response.status));
      if (this.cancelled || generation !== this.generation) {
        await this._disposeResult(result, 'cancelled_during_acquire');
        throw new Error('call_cancelled');
      }
      if (result.status === 'connect') {
        voiceCallMark('gateway_service_identity', 'pass', result.gateway_identity || {});
        if (clientRelease.protocol && Number(result.call_protocol || 0) !== clientRelease.protocol) {
          await this._disposeResult(result, 'incompatible_call_protocol');
          throw new Error('incompatible_call_protocol');
        }
        this.pending = null;
        this.active = result;
        this._startHeartbeat();
        return result;
      }
      if (result.status === 'queued') {
        this.pending = { call_id: result.call_id, idempotency_key: idempotencyKey };
        const queue = result.queue || {};
        // 忙線排隊（2026-07-23 Edward 拍板 B 案 → 2026-07-24 P0 補上 eta_s）：明著告訴用戶排第幾位／準備中、輪到自動接通
        showBusyCard('queued', queue);
        setCallPreflightPending(true, muneaT('voice.queue.pending', '排隊中…'));
        setCallHint(muneaT('voice.queue.wait', '輪到你時會自動接通。'), true);
        if (!this._queueSeen) {
          this._queueSeen = true;
          try { trackProductEvent('call_queue_shown', { position: queue.position || 1, depth: queue.depth || 0 }); } catch (e) {}
        }
        await new Promise(resolve => setTimeout(resolve, 3000));
        continue;
      }
      const reason = result.reason || 'capacity_unavailable';
      if (reason === 'account_not_ready' && !accountRecoveryAttempted) {
        accountRecoveryAttempted = true;
        voiceCallMark('gateway_account_recovery', 'pass', { endpoint: this.url() });
        const bootstrap = await syncAccountBootstrap('create', {
          reason: 'gateway_account_not_ready',
          force: true,
        });
        if (bootstrap && bootstrap.ok) continue;
      }
      throw new Error(reason);
    }
    throw new Error('call_cancelled');
  },
  async _disposeResult(result, reason) {
    if (!result || !result.call_id || !this.url()) return null;
    try {
      const isLease = result.status === 'connect' && result.lease_version;
      const suffix = isLease ? '/release' : '/cancel';
      const options = { method: 'POST', keepalive: true };
      if (isLease) {
        options.body = JSON.stringify({
          lease_version: result.lease_version,
          event_id: 'app-dispose-' + Date.now() + '-' + Math.random(),
          reason: reason || 'cancelled',
        });
      }
      const response = await this._fetch(this.url() + '/v1/calls/' + encodeURIComponent(result.call_id) + suffix, options);
      return await response.json().catch(() => null);
    } catch (e) { return null; }
  },
  async refreshToken() {
    if (!this.active) return null;
    const response = await this._fetch(this.url() + '/v1/calls/' + encodeURIComponent(this.active.call_id) + '/token', {
      method: 'POST',
      body: JSON.stringify({ lease_version: this.active.lease_version }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.status !== 'connect') throw new Error('call_token_refresh_failed');
    this.active = Object.assign({}, this.active, result);
    return this.active;
  },
  async _heartbeatOnce() {
    const lease = this.active;
    if (!lease) throw new Error('call_lease_missing');
    const response = await this._fetch(this.url() + '/v1/calls/' + encodeURIComponent(lease.call_id) + '/heartbeat', {
      method: 'POST',
      body: JSON.stringify({
        lease_version: lease.lease_version,
        event_id: 'app-heartbeat-' + Date.now() + '-' + Math.random(),
        component: 'app',
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error((result && result.detail) || ('heartbeat_http_' + response.status));
    if (this.active && this.active.call_id === lease.call_id && result.state) this.active.state = result.state;
    return result;
  },
  async waitUntilActive(timeoutMs = 15000) {
    const lease = this.active;
    if (!lease) throw new Error('call_lease_missing');
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.cancelled || !this.active || this.active.call_id !== lease.call_id) throw new Error('call_cancelled');
      let result = null;
      try {
        result = await this._heartbeatOnce();
      } catch (e) {
        const reason = String(e && e.message || e);
        if (reason === 'call_cancelled' || reason === 'stale_lease' || reason === 'call_not_owned') throw e;
      }
      if (result && result.should_end) throw new Error(result.reason || 'lease_ended');
      if (result && result.state === 'active') return result;
      await new Promise(resolve => setTimeout(resolve, 750));
    }
    throw new Error('call_ready_timeout');
  },
  _startHeartbeat() {
    clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = setInterval(async () => {
      if (!this.active) return;
      try {
        const result = await this._heartbeatOnce();
        if (result.should_end) {
          try { LiveVoice.stop(); } catch (e) {}
          try { completeChatSession(result.reason || 'lease_ended'); } catch (e) {}
        }
      } catch (e) { /* 45s lease reaper is the final guard; one missed heartbeat is recoverable. */ }
    }, 15000);
  },
  async release(reason) {
    this.cancelled = true;
    this.generation += 1;
    clearInterval(this.heartbeatTimer); this.heartbeatTimer = null;
    const lease = this.active; const pending = this.pending;
    this.active = null; this.pending = null;
    try {
      if (lease) {
        const response = await this._fetch(this.url() + '/v1/calls/' + encodeURIComponent(lease.call_id) + '/release', {
          method: 'POST', keepalive: true,
          body: JSON.stringify({ lease_version: lease.lease_version, event_id: 'app-release-' + Date.now() + '-' + Math.random(), reason: reason || 'ended' }),
        });
        return await response.json().catch(() => null);
      } else if (pending) {
        const response = await this._fetch(this.url() + '/v1/calls/' + encodeURIComponent(pending.call_id) + '/cancel', {
          method: 'POST', keepalive: true,
        });
        return await response.json().catch(() => null);
      }
    } catch (e) { /* Voice/Avatar callbacks and lease TTL provide idempotent cleanup. */ }
    return null;
  },
};
function getLiveVoiceUrl() {
  if (CallControl.active) return (CallControl.active.voice && CallControl.active.voice.url) || '';
  try {
    const cfg = developerConfig();
    if (isDeveloperBypassAllowed() && cfg.voiceUrl) return String(cfg.voiceUrl);
  } catch (e) {}
  try { const u = localStorage.getItem('munea.liveVoiceUrl'); if (u !== null) return u; } catch (e) {}
  return LIVE_VOICE_URL_DEFAULT;
}
// ===== 撥號前連線暖身 · 第一階段（2026-07-16 Edward「撥號前暖機 接續推進」）=====
// App 一開、回前景時，先把三條線（顯卡／語音／通話總機）的 DNS＋TLS 握手做完，
// 順便輕拍一下雲端讓沉睡的服務開始醒（雲端冷啟、顯卡快照喚醒都吃這第一下）——
// 使用者按「聊聊」時就省掉這些前置秒數。一次性、60 秒防抖、不輪詢：
// 尊重 7/9「只在聊聊頁探、不空燒顯卡」拍板，持續探測仍只在聊聊頁（Avatar.wake）。
let _connWarmLast = 0;
function preDialConnWarm(reason) {
  try {
    const now = Date.now();
    if (now - _connWarmLast < 60000) return;
    _connWarmLast = now;
    let n = 0;
    try {
      const a = getAvatarUrl();
      if (a) { n++; fetch(a.replace(/\/$/, '') + '/health?key=' + encodeURIComponent(MUNEA_APP_KEY), { mode: 'cors', cache: 'no-store' }).catch(() => {}); }
    } catch (e) {}
    try {
      const v = getLiveVoiceUrl();
      if (v) { n++; fetch(v.split('?')[0].replace(/^ws/, 'http').replace(/\/$/, '') + '/health', { mode: 'no-cors', cache: 'no-store' }).catch(() => {}); }
    } catch (e) {}
    try {
      const c = CallControl.url();
      if (c) { n++; fetch(c + '/health', { mode: 'no-cors', cache: 'no-store' }).catch(() => {}); }
    } catch (e) {}
    try { trackProductEvent('conn_prewarm', { reason, targets: n }); } catch (e) {}
  } catch (e) {}
}
// ===== 雲端寧寧擬真臉（快照秒醒 · 7/9 定案主力）=====
// 平常全睡不計費；進聊聊頁先「預醒」（8–10 秒）、按通話時臉多半已就緒。
// 連哪裡：localStorage['munea.avatarUrl']（設空字串=關閉臉）；預設＝正式雲端服務。
const AVATAR_URL_DEFAULT = 'https://edwardt0303--munea-nening-avatar-nening-web.modal.run';
// 新引擎 FlashHead（2026-07-11 Edward 拍板轉正主線；同日「直接接到app裡面」＝預設就走它）：
// localStorage['munea.faceEngine'] 只剩「手動退回舊引擎」用（設 'ditto'）；不設＝FlashHead。
// 門牌＝台灣 GLOWS RTX 6000 Ada 常駐主卡（640、3 席、2026-07-13 正式驗收）。
// ⚠ 這台機器 Release 重開後號碼會變；正式 App 下一版會改只認 Call Gateway。
// 備援1（美國 RunPod 4090 常駐）：https://a535qiaoru5bno-8188.proxy.runpod.net
// 備援2（Modal L4 試作版、產能貼預算會截斷）：https://edwardt0303--munea-flashhead-avatar-dev-flashhead-web.modal.run
const FLASHHEAD_URL_DEFAULT = 'https://tw-07.access.glows.ai:26969';
const RETIRED_FLASHHEAD_URLS = new Set([
  'https://tw-06.access.glows.ai:26718',
]);
function faceEngine() {
  try { return localStorage.getItem('munea.faceEngine') || 'flashhead'; } catch (e) { return 'flashhead'; }
}
// 擬真角色 → 雲端臉引擎代號（2026-07-11 Edward 拍板 launch 兩角色）：寧寧=擬真女=a05、阿宏=擬真男=a06。
// 其餘（2D 四角色）回空字串＝不接 flashhead 臉、走 2D 動畫。全身立繪底圖也照這個對應換。
const FLASHHEAD_CHAR_MAP = { '寧寧': 'a05', '阿宏': 'a06' };
function flashheadCharFor(backendChar) { try { return FLASHHEAD_CHAR_MAP[backendChar] || ''; } catch (e) { return ''; } }
function getAvatarUrl() {
  if (CallControl.active) return (CallControl.active.worker && CallControl.active.worker.url) || '';
  try {
    const raw = localStorage.getItem('munea.avatarUrl');
    if (raw !== null) {
      const u = raw.replace(/\/$/, '');
      // 舊版曾把臨時 GLOWS 門牌寫進 localStorage；升版後要自動回到新主卡。
      if (RETIRED_FLASHHEAD_URLS.has(u)) localStorage.removeItem('munea.avatarUrl');
      else return u;
    }
  } catch (e) {}
  return faceEngine() === 'flashhead' ? FLASHHEAD_URL_DEFAULT : AVATAR_URL_DEFAULT;
}
// FlashHead 全身合成開關（2026-07-11）：開＝把 512 活臉搬進 9:16 全身立繪的判斷框（羽化貼回、先鋒參數）；
// 關＝活臉搬回原位、恢復照片模式（Ditto/掛斷用）。搬家後補一次 play()——iOS 換位可能暫停。
function _fhFitStage(frame) {
  const host = frame && frame.parentElement;
  if (!host) return;
  const hostWidth = host.clientWidth;
  const hostHeight = host.clientHeight;
  if (!hostWidth || !hostHeight) return;
  const scale = Math.max(hostWidth / 1080, hostHeight / 1920);
  frame.style.width = Math.ceil(1080 * scale) + 'px';
  frame.style.height = Math.ceil(1920 * scale) + 'px';
}
// 臉框素材預熱（2026-07-16 治「第一通黑閃」）：進聊聊頁／按撥號就先把全身立繪換成對的角色並解碼，
// 不要等接通那刻才裝圖——第一通冷開機時圖還沒解碼、臉框深色底會先露出來閃一下。
function _fhWarmArt() {
  try {
    if (faceEngine() !== 'flashhead') return;
    const _fc = flashheadCharFor(currentChar) || 'a05';
    [['fhBg', 'flashhead/bg-'], ['fhPersonImg', 'flashhead/person-']].forEach(([id, prefix]) => {
      const img = document.getElementById(id);
      if (!img) return;
      const want = prefix + _fc + '.png';
      if (img.getAttribute('src') !== want) img.src = want;
      if (img.decode) { const p = img.decode(); if (p && p.catch) p.catch(() => {}); }
    });
  } catch (e) {}
}
// 撥號時就先把雲端臉播放器放進臉框（2026-07-16 治「第一通黑閃」）：接通那刻才搬 DOM 會讓影像圖層
// 整個重建、黑一格才回來；先搬好（臉框還藏著、看不見），接通時 _fhComposite 的搬移就變成不動作＝零重建。
function _fhPreParentVid() {
  try {
    if (faceEngine() !== 'flashhead') return;
    const ov = document.getElementById('fhOverlay');
    const vid = document.getElementById('faceVid');
    if (ov && vid && vid.parentElement !== ov) ov.appendChild(vid);
  } catch (e) {}
}
function _fhComposite(on, vid) {
  try {
    const frame = document.getElementById('fhFrame');
    const ov = document.getElementById('fhOverlay');
    if (!frame || !ov || !vid) return;
    if (on) {
      frame.hidden = false;
      _fhFitStage(frame);
      if (!window.__muneaFhStageObserver && typeof ResizeObserver !== 'undefined') {
        window.__muneaFhStageObserver = new ResizeObserver(() => {
          if (!frame.hidden) _fhFitStage(frame);
        });
        window.__muneaFhStageObserver.observe(frame.parentElement);
      }
      const _bg = document.getElementById('fhBg');   // 全身立繪底圖跟著角色換：擬真女 bg-a05、擬真男 bg-a06
      const _fc = flashheadCharFor(currentChar) || 'a05';
      if (_bg && _bg.getAttribute('src') !== 'flashhead/bg-' + _fc + '.png') _bg.src = 'flashhead/bg-' + _fc + '.png';
      const _pi = document.getElementById('fhPersonImg');   // 呼吸用人物去背層跟著換（與底圖同版位、由 scripts/build_flashhead_person_layer.py 產）
      if (_pi && _pi.getAttribute('src') !== 'flashhead/person-' + _fc + '.png') _pi.src = 'flashhead/person-' + _fc + '.png';
      // 模型與畫面都使用同一個原生正方形裁切，避免把人物長方形硬壓成 640x640。
      // a05 y=190、a06 y=209，來源均為 1080x1920；高度由 CSS aspect-ratio 固定為正方形。
      const _box = (_fc === 'a06') ? { top: '10.885417%' } : { top: '9.895833%' };
      ov.style.top = _box.top;
      ov.style.height = '';
      if (vid.parentElement !== ov) { ov.appendChild(vid); try { const p = vid.play(); if (p && p.catch) p.catch(() => {}); } catch (e) {} }
      vid.style.objectFit = ''; vid.style.background = '';
    } else {
      frame.hidden = true;
      const bg = document.querySelector('#chat .face-bg');
      if (bg && vid.parentElement !== bg) { bg.insertBefore(vid, document.getElementById('faceAud')); }
    }
  } catch (e) {}
}
// （2026-07-11 施工圖①：方案B「伺服器直送雲端臉」整套已拔除——7/10 退役死碼、聲音上行只走客戶端自己送這一條。）
// 同線收聲（2026-07-11 · 治「聲音先出、臉慢 3-5 秒」根因＝聲音和影像走兩條線）：
// 開＝App 從臉的那條線多收一軌聲音、從那裡播（跟影像天生同步、免手動猜 faceSyncMs）。
// 預設關＝現役零影響；上行照舊走「手機轉送」（Avatar.feed 一寸不動、不碰 7/10 那顆方案B 雷）。
// 保底：同線 3 秒沒出聲 → 自動退回本地播放（防「有臉沒聲」，比慢半拍更糟）。
function faceSameLineOn() {
  try {
    const v = localStorage.getItem('munea.faceSameLine');
    if (v !== null) return v === '1';                 // 手動設定最優先（=0 可在 FlashHead 模式下關同線）
    return faceEngine() === 'flashhead';              // FlashHead 模式預設開同線（它天生兩軌同線）
  } catch (e) { return false; }
}
// 單一真相：「她現在正在出聲嗎」——Voice PCM 算出的播放水位是主時鐘；同線實際
// 解碼音量只准在預估句尾後的 bounded grace 內補正。Avatar 要先算嘴型才真正起播，
// 單靠 PCM 到達時間會提早約 0.4-0.9 秒開麥，喇叭尾音就會被當成使用者插話。
// grace 嚴格封頂 1.5 秒，避免遠端 idle 音軌的底噪再次把麥克風永久鎖死。
function speechActive() {
  try {
    const now = performance.now();
    const queued = (typeof LiveVoice !== 'undefined' && LiveVoice._playoutUntil && now < LiveVoice._playoutUntil);
    const sameLine = typeof LiveVoice !== 'undefined' && LiveVoice._sameLine && LiveVoice._sameLineFellBack !== true;
    const predictedEnd = Number((typeof LiveVoice !== 'undefined' && LiveVoice._playoutUntil) || 0);
    const decodedTail = !!(sameLine && predictedEnd && now <= predictedEnd + 1500
      && Number(Avatar && Avatar._faceAudLevel || 0) >= 0.06);
    if (queued || decodedTail) window.__muneaSpeechTs = now;
    const tailMs = sameLine ? 120 : 400;
    return !!(queued || decodedTail || (window.__muneaSpeechTs && (now - window.__muneaSpeechTs) < tailMs));
  } catch (e) { return false; }
}
const Avatar = {
  pc: null, ws: null, on: false, _waking: false, warm: false, _wakeGen: 0,
  _session: '', _lastError: '', _renderStream: null,
  _videoReady: false, _feedReady: false, _readyNotified: false,
  _notifyReady() {
    if (this._readyNotified || !this._videoReady || !this._feedReady) return;
    this._readyNotified = true;
    this._diagNote('影像+聲音上行都就緒');
    voiceCallMark('avatar_ready', 'pass');
    if (typeof window.__muneaOnFaceReady === 'function') window.__muneaOnFaceReady();
    try {
      if (typeof LiveVoice !== 'undefined' && LiveVoice.on) LiveVoice._requestFaceDirect();
    } catch (e) {}
  },
  _handlePcmAck(msg, basis = 'avatar_audio_ws_ack') {
    if (!msg || msg.type !== 'avatar_pcm_received' || Number(msg.turn) <= 0) return;
    const turn = Number(msg.turn);
    if (Number.isFinite(Number(msg.prebufferMs))) {
      this._lastPrebufferMs = Math.max(200, Math.min(350, Number(msg.prebufferMs)));
    }
    if (window.MuneaVoiceDiagnostics) window.MuneaVoiceDiagnostics.markTurn(
      turn, 'avatar_pcm_received', { basis, bytes: Number(msg.bytes) || 0,
        prebufferMs: this._lastPrebufferMs || 0 }
    );
    this._playoutArmedTurn = turn;
    this._directAckTurn = turn;
    this._playoutStatsBaseline = null;
    voiceCallMark('voice_turn_avatar_pcm', 'pass', { turn, bytes: Number(msg.bytes) || 0, basis });
  },
  showLiveFrame() {
    if (!this._videoReady) return false;
    const vid = document.getElementById('faceVid');
    const bg = document.querySelector('#chat .face-bg');
    if (!vid || !bg) return false;
    if (faceEngine() === 'flashhead') _fhComposite(true, vid);
    else _fhComposite(false, vid);
    bg.classList.add('livevid');
    return true;
  },
  _diag(msg) {  // 診斷小窗（設定 munea.debug=1 才顯示）：手機上排查「臉沒動」用
    try {
      if (localStorage.getItem('munea.debug') !== '1') return;
      const el = document.getElementById('avatarDiagnostics');
      if (el) { el.hidden = false; el.textContent = '臉: ' + msg; }
    } catch (e) {}
  },
  // 黑盒子：記整串同線聲音事件（帶時間），失敗時自動跳出來讓 Edward 截圖抓真兇（2026-07-12）
  _diagNote(msg, force) {
    try {
      if (!Avatar._diagTrail) Avatar._diagTrail = [];
      const t0 = Avatar._callT0 || Date.now();
      const el = ((Date.now() - t0) / 1000).toFixed(1);
      Avatar._diagTrail.push(el + 's ' + msg);
      if (Avatar._diagTrail.length > 10) Avatar._diagTrail.shift();
      const on = force || (function () { try { return localStorage.getItem('munea.debug') === '1'; } catch (e) { return false; } })();
      if (on) {
        const d = document.getElementById('avatarDiagnostics');
        if (d) { d.hidden = false; d.style.whiteSpace = 'pre-line'; d.style.maxHeight = '40vh'; d.style.overflow = 'auto'; d.textContent = muneaT('avatar.forceDiagHeader', '聲音診斷:') + '\n' + Avatar._diagTrail.join('\n'); }
      }
    } catch (e) {}
  },
  // 進聊聊頁就把顯卡叫醒（Edward 2026-07-09 方案二）：連續探健康到「醒了」為止（涵蓋 8-10 秒冷啟），
  // warm=true 後按通話臉就近乎即到。只在聊聊頁探、離頁就停（不空燒顯卡）。
  wake() {
    const u = getAvatarUrl(); if (!u) { this.warm = false; return; }
    if (this._waking) return;
    this._waking = true; this.warm = false;
    const gen = ++this._wakeGen;
    const onChat = () => { const c = document.getElementById('chat'); return c && c.classList.contains('active'); };
    const ping = () => fetch(u + '/health?key=' + encodeURIComponent(MUNEA_APP_KEY), { mode: 'cors' })
      .then(r => (r && r.ok) ? r.json() : null).catch(() => null);
    const poll = tries => {
      if (gen !== this._wakeGen) return;                 // 換角色/重進頁 → 舊輪作廢
      ping().then(j => {
        if (gen !== this._wakeGen) return;
        if (j && j.ok) { this.warm = true; this._waking = false; this._diag('顯卡就緒'); return; }  // 醒了、就緒
        if (tries > 0 && onChat()) { this._diag('喚醒顯卡中…'); setTimeout(() => poll(tries - 1), 1500); }
        else { this._waking = false; }                   // 離頁或等太久 → 停（按通話時 start 會再喚醒）
      });
    };
    poll(14);   // 最多約 21 秒（冷啟 8-10s 綽綽有餘）
  },
  async start() {
    const u = getAvatarUrl(); if (!u) return false;
    const vid = document.getElementById('faceVid'); if (!vid) return false;
    voiceCallMark('avatar_start', 'pass', { endpoint: u, engine: faceEngine() });
    this._lastError = ''; this._session = '';
    this._videoReady = false; this._feedReady = false; this._readyNotified = false;
    this._faceAudReceiver = null;
    this._renderStream = new MediaStream();
    vid.srcObject = this._renderStream;
    vid.muted = true;
    try {
      // 連線路線（7/9 手機實測補強）：家用網路直連即可；手機行動網路（5G/4G）常要走「中繼站」轉一手
      // 中繼＝公開測試中繼（正式上線換自家帳號的中繼、一行換）；munea.avatarRelay=1 可強制全走中繼（診斷用）
      const legacyIceServers = [
        { urls: 'stun:stun.l.google.com:19302' },
        // 自架可靠中繼站（GCP coturn · 34.81.102.52 · 2026-07-10 Edward 選 B、已實測能轉接）——手機行動網路優先走這台、穩
        { urls: ['turn:34.81.102.52:3478?transport=udp', 'turn:34.81.102.52:3478?transport=tcp'],
          username: 'muneaturn', credential: 'munea-turn-a7k2q' },
        // 443 偽裝門（2026-07-11 治「第一通線路 failed」）：走大家都不擋的 443 端口——雲端側開門後生效、開之前這兩條只是白試一下無害
        { urls: ['turn:34.81.102.52:443?transport=tcp', 'turn:34.81.102.52:443?transport=udp'],
          username: 'muneaturn', credential: 'munea-turn-a7k2q' },
        // 免費公用中繼＝備援（自架的萬一掛了還有得用）
        { urls: ['turn:openrelay.metered.ca:80', 'turn:openrelay.metered.ca:443', 'turn:openrelay.metered.ca:443?transport=tcp'],
          username: 'openrelayproject', credential: 'openrelayproject' },
      ];
      const leaseIceServers = CallControl.active && CallControl.active.ice_servers;
      const iceServers = Array.isArray(leaseIceServers) && leaseIceServers.length ? leaseIceServers : legacyIceServers;
      let forceRelay = false;
      try { forceRelay = localStorage.getItem('munea.avatarRelay') === '1'; } catch (e) {}
      this.pc = new RTCPeerConnection(forceRelay ? { iceServers, iceTransportPolicy: 'relay' } : { iceServers });
      this._diag('連線中（中繼' + (forceRelay ? '·強制' : '·備援') + '）');
      this.pc.addTransceiver('video', { direction: 'recvonly' });
      const _sameLine = faceSameLineOn();
      if (_sameLine) this.pc.addTransceiver('audio', { direction: 'recvonly' });   // 同線：臉那條線多收一軌聲音（跟影像同步）
      this.pc.ontrack = e => {
        // WebRTC 不保證 audio/video 的 ontrack 事件帶同一個 MediaStream 物件。
        // 明確把兩軌合進同一個 render stream，交給唯一播放器 faceVid，避免有影無聲或兩路時鐘漂移。
        if (!this._renderStream) this._renderStream = new MediaStream();
        if (e.track && !this._renderStream.getTracks().some(track => track.id === e.track.id)) this._renderStream.addTrack(e.track);
        if (vid.srcObject !== this._renderStream) vid.srcObject = this._renderStream;
        if (_sameLine && e.track && e.track.kind === 'audio') {
          voiceCallMark('avatar_audio_track', 'pass', { enabled: e.track.enabled, muted: e.track.muted });
          this._attachFaceAudio(e.track);
          try { this._faceAudReceiver = e.receiver; } catch (er) {}
          try {
            const _sid = (e.streams && e.streams[0] && e.streams[0].id || '').slice(-4);
            Avatar._diagNote('聲音軌到 str=' + _sid + ' en=' + e.track.enabled + ' mu=' + e.track.muted);
          } catch (er) {}
          const _fa2 = document.getElementById('faceAud'); if (_fa2) _fa2.muted = true;
          const _pa = vid.play(); if (_pa && _pa.catch) _pa.catch(() => {});
          return;
        }
        if (e.track && e.track.kind === 'video') voiceCallMark('avatar_video_track', 'pass');
        if (_sameLine) {
          vid.muted = true;   // 招呼前的 1 秒路徑暖機通過後才解除；第一句不再拿來試播。
          try { Avatar._diagNote('影像軌到 合成流含音軌=' + this._renderStream.getAudioTracks().length); } catch (er) {}
          const _pv = vid.play();
          if (_pv && _pv.then) _pv.then(() => Avatar._diagNote('影音播放:成功')).catch((err) => {   // 被 iOS 擋（手勢斷鏈）→ 點畫面一下＝新手勢救回（先鋒 tap-to-play 的 App 版）
            Avatar._diagNote(muneaT('avatar.forcePlaybackBlocked', '影音播放:被擋({reason})', { reason: (err && err.name) || '' }), true);
            try { setLocalizedRuntimeHint('playbackBlocked', true); } catch (e2) {}
            try {
              document.getElementById('chat').addEventListener('click', () => {
                vid.muted = false; const _p3 = vid.play(); if (_p3 && _p3.catch) _p3.catch(() => {});
                try { setCallHint(''); } catch (e3) {}
              }, { once: true });
            } catch (e4) {}
          });
        }
        // 不在 ontrack 當下切畫面；第一個有效影格確認後，開場閘才會呼叫 showLiveFrame()。
        this._diag('影像軌到了，等待第一格');
      };
      this.pc.addEventListener('iceconnectionstatechange', () => {
        this._diag('線路 ' + this.pc.iceConnectionState);
        const iceState = this.pc.iceConnectionState;
        if (iceState === 'failed') voiceCallFail('avatar_ice', iceState);
        else voiceCallMark('avatar_ice_' + iceState, 'pass');
        // 第一通線路 failed 自救（Edward 2026-07-11）：臉連線失敗＝自動重連一次（等於幫用戶掛掉重撥）——他實測第二通總是成功
        if (this.pc.iceConnectionState === 'failed' && this.on && Date.now() - (Avatar._lastRetry || 0) > 20000) {
          Avatar._lastRetry = Date.now();
          this._diag('線路失敗 → 自動重連一次');
          try { this.stop(); } catch (e2) {}
          setTimeout(() => {
            if (typeof callConnected !== 'undefined' && !callConnected && !callDialing) return;   // 已掛斷就不重連
            const resume = CallControl.active ? CallControl.refreshToken() : Promise.resolve();
            resume.then(() => Avatar.start()).then(ok => {
              if (!ok) return;
              try {   // 通話已開場的情況下臉遲到加入：補亮會動的臉那層（開場那步早跑過、這裡要自己補）
                Avatar.showLiveFrame();
                FaceIdle.stop();
              } catch (e3) {}
            }).catch(() => {});
          }, 800);
        }
      });
      const o = await this.pc.createOffer(); await this.pc.setLocalDescription(o);
      // 2026-07-29 接通提速第 2 刀：舊版「等收集完全部連線候選再送（demo-live 同款）、
      // 上限 3 秒」——名單裡掛著多台中繼站（含公用備援），行動網路上幾乎每次都等好等滿，
      // 是真機 trail「5.9 秒影像軌才到」的最大單一成分。改成夠用就先送：
      // 湊到第一條「走得出去」的路線（經 STUN 或中繼）＋0.8 秒緩衝就出發；
      // 3 秒上限與收集完成照舊。量測記號 avatar_ice_gather 上真機直接看省多少。
      await new Promise(res => {
        if (this.pc.iceGatheringState === 'complete') return res();
        const gatherT0 = performance.now();
        let usable = 0, settled = false;
        const done = () => {
          if (settled) return; settled = true;
          try { this.pc.removeEventListener('icegatheringstatechange', chk); } catch (e2) {}
          try { this.pc.removeEventListener('icecandidate', onCand); } catch (e2) {}
          clearInterval(tick); clearTimeout(cap);
          try { voiceCallMark('avatar_ice_gather', 'pass', { ms: Math.round(performance.now() - gatherT0), usable }); } catch (e2) {}
          res();
        };
        const maybe = () => {
          if (this.pc.iceGatheringState === 'complete') return done();
          if (usable > 0 && (performance.now() - gatherT0) >= 800) return done();
        };
        const chk = () => maybe();
        const onCand = (e) => {
          // host 候選只在同網段有用；能出門的是經 STUN（srflx）或中繼（relay）那幾條
          if (e && e.candidate && /typ (srflx|relay)/.test(String(e.candidate.candidate || ''))) usable += 1;
          maybe();
        };
        this.pc.addEventListener('icegatheringstatechange', chk);
        this.pc.addEventListener('icecandidate', onCand);
        const tick = setInterval(maybe, 200);
        const cap = setTimeout(done, 3000);
      });
      // 帶上目前選的角色（六角色 · 7/9）；角色不吃擬真引擎時服務會說不行 → 自動退回 2D 動畫
      // FlashHead 測試模式不帶角色（它目前只有測試臉、帶中文名會被拒連）——擬真女底圖入庫後再帶
      let _cq = '';
      try {
        if (faceEngine() === 'flashhead') {
          const _fc = flashheadCharFor(currentChar);   // 寧寧→a05、阿宏→a06；2D 角色回空＝不帶（服務用預設 a05）
          if (_fc) _cq = '&char=' + encodeURIComponent(_fc);
        } else if (typeof currentChar === 'string' && currentChar) {
          _cq = '&char=' + encodeURIComponent(currentChar);
        }
      } catch (e) {}
      const _leaseToken = CallControl.active && CallControl.active.call_token;
      const _avatarAuth = _leaseToken ? ('token=' + encodeURIComponent(_leaseToken)) : ('key=' + encodeURIComponent(MUNEA_APP_KEY));
      voiceCallMark('avatar_offer_requested', 'pass', { endpoint: u, authMode: _leaseToken ? 'call_token' : 'app_key' });
      const r = await fetch(u + '/offer?' + _avatarAuth + _cq, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: this.pc.localDescription.sdp, type: this.pc.localDescription.type }) });
      const a = await r.json();
      if (!r.ok || a.error) {
        this._lastError = a.code || ('http_' + r.status);
        throw new Error(a.error || 'avatar offer failed');
      }
      this._session = a.session || '';
      if (!this._session) { this._lastError = 'missing_session'; throw new Error('avatar session missing'); }
      voiceCallMark('avatar_offer_accepted', 'pass', { httpStatus: r.status });
      await this.pc.setRemoteDescription(a);
      // 聲音上行：App 自己開一條 WS 把語音送去雲端臉（下面 feed()/reset() 會用到）
      this.ws = new WebSocket(u.replace(/^http/, 'ws') + '/audio?' + _avatarAuth + '&session=' + encodeURIComponent(this._session));
      this.ws.binaryType = 'arraybuffer';
      this.ws.onmessage = event => {
        try {
          const msg = JSON.parse(String(event.data || ''));
          this._handlePcmAck(msg);
        } catch (e) {}
      };
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('avatar audio feed timeout')), 6000);
        this.ws.onopen = () => {
          clearTimeout(timer);
          this.on = true; this._feedReady = true;
          this._diagNote('聲音上行就緒');
          voiceCallMark('avatar_audio_feed_open', 'pass');
          this._notifyReady();
          resolve();
        };
        this.ws.onerror = () => { clearTimeout(timer); reject(new Error('avatar audio feed failed')); };
      });
      return true;
    } catch (e) {
      voiceCallFail('avatar_start', this._lastError || e, { endpoint: u });
      this.stop();
      return false;
    }
  },
  beginTurn(turn) {
    try {
      if (!this.on || !this.ws || this.ws.readyState !== 1) return;
      this.ws.send('reset');
      const id = Math.max(0, Number(turn) || 0);
      this._pendingPlayoutTurn = id;
      this._audioTurn = id;
      this._playoutArmedTurn = 0;
      this._directAckTurn = 0;
      this._playoutStatsBaseline = null;
      if (id) this.ws.send('turn:' + id);
    } catch (e) {}
  },
  beginDirectTurn(turn) {
    const id = Math.max(0, Number(turn) || 0);
    this._pendingPlayoutTurn = id;
    this._audioTurn = id;
    // Avatar ACK travels back on a different websocket and can beat the Voice
    // PCM event by a few milliseconds. Preserve that ACK for the same turn;
    // otherwise diagnostics would miss the real first WebRTC playout.
    if (this._directAckTurn !== id) this._playoutArmedTurn = 0;
    this._playoutStatsBaseline = null;
  },
  feed(buf) { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send(buf); } catch (e) {} },
  reset() { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send('reset'); } catch (e) {} },
  finish() { try { if (this.on && this.ws && this.ws.readyState === 1) this.ws.send('finish'); } catch (e) {} },
  _markFaceWebrtcPlayout(turn, basis) {
    if (!turn || this._pendingPlayoutTurn !== turn || this._playoutArmedTurn !== turn) return;
    this._pendingPlayoutTurn = 0;
    this._playoutArmedTurn = 0;
    if (window.MuneaVoiceDiagnostics) window.MuneaVoiceDiagnostics.markTurn(
      turn, 'webrtc_playout', { basis }
    );
    voiceCallMark('voice_turn_webrtc_playout', 'pass', { turn, basis });
  },
  async _probeFaceWebrtcPlayout(player) {
    const turn = this._pendingPlayoutTurn;
    if (!turn || this._playoutArmedTurn !== turn || this._playoutStatsBusy ||
        !player || player.muted || player.paused) return;
    const now = performance.now();
    if (now - (this._playoutStatsAt || 0) < 80) return;
    const receiver = this._faceAudReceiver;
    if (!receiver || !receiver.getStats) return;
    this._playoutStatsAt = now;
    this._playoutStatsBusy = true;
    try {
      let emitted = null;
      const stats = await receiver.getStats();
      stats.forEach(report => {
        if (report.type !== 'inbound-rtp' || (report.kind !== 'audio' && report.mediaType !== 'audio')) return;
        if (Number.isFinite(Number(report.jitterBufferEmittedCount))) {
          emitted = Math.max(Number(emitted) || 0, Number(report.jitterBufferEmittedCount));
        }
      });
      if (this._pendingPlayoutTurn !== turn || this._playoutArmedTurn !== turn || emitted === null) return;
      if (this._playoutStatsBaseline === null) {
        this._playoutStatsBaseline = emitted;
      } else if (emitted > this._playoutStatsBaseline) {
        this._markFaceWebrtcPlayout(turn, 'webrtc_jitter_buffer_emitted_player_active');
      }
    } catch (e) {
      // Safari versions without the counter still use the decoded-RMS path below.
    } finally {
      this._playoutStatsBusy = false;
    }
  },
  // 同線：把臉那條線多帶的聲音軌接到 faceAud 播出，並持續量音量（給 LiveVoice 3 秒保底判斷用）
  _attachFaceAudio(track) {
    try {
      const aud = document.getElementById('faceAud'); if (!aud) return;
      const ms = new MediaStream([track]);
      // faceAud 只做音量儀表；真正聲音固定由 faceVid 播放。
      // 如果這裡也解除靜音，同一遠端音軌會被兩個 media element 同時播放而重疊。
      aud.srcObject = ms; aud.muted = true;
      const p = aud.play(); if (p && p.catch) p.catch(() => {});
      this._diag('聲音到了（同線）');
      try {
        this._faceAudCtx = new AudioContext();
        const src = this._faceAudCtx.createMediaStreamSource(ms);
        const an = this._faceAudCtx.createAnalyser(); an.fftSize = 512;
        src.connect(an); this._faceAudAnalyser = an;   // 只接分析器、不接喇叭（聲音由 <audio> 播、這裡純量）
        const data = new Uint8Array(an.fftSize);
        this._faceAudMaxLevel = 0;
        const loop = () => {
          if (!this._faceAudAnalyser) return;
          an.getByteTimeDomainData(data);
          let s = 0; for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; s += v * v; }
          const rms = Math.sqrt(s / data.length);
          this._faceAudLevel = rms;
          if (rms > (this._faceAudMaxLevel || 0)) this._faceAudMaxLevel = rms;
          const player = document.getElementById('faceVid');
          if (rms > 0.015 && this._pendingPlayoutTurn &&
              this._playoutArmedTurn === this._pendingPlayoutTurn &&
              player && !player.muted && !player.paused) {
            const turn = this._pendingPlayoutTurn;
            this._markFaceWebrtcPlayout(turn, 'decoded_remote_audio_player_active');
          }
          this._probeFaceWebrtcPlayout(player);
          this._faceAudRaf = requestAnimationFrame(loop);
        };
        loop();
      } catch (e) {}
    } catch (e) {}
  },
  // ── 臉部影像流看門（2026-07-16 Edward 真機：嘴巴卡頓→整個畫面凍住不再動；伺服器 faceaudio_send_err=0
  //    ＝凍在 App 端影像流。既有恢復只有「ICE 變 failed 才重連」，幀流停掉但 ICE 還 connected 時沒人管）──
  // 判停邏輯：只在「有聲音輸出（speechActive＝LiveVoice 自己收到的音訊帳，不依賴臉）但連續 4 秒沒有新幀」
  // 時判 stall——靜默期引擎 idle feed 幀本來就疏、不累計、不誤判。
  _frameProgress() {
    const vid = document.getElementById('faceVid');
    if (!vid) return -1;
    try {
      if (vid.getVideoPlaybackQuality) {
        const q = vid.getVideoPlaybackQuality();
        if (q && typeof q.totalVideoFrames === 'number' && q.totalVideoFrames > 0) return q.totalVideoFrames;
      }
    } catch (e) {}
    if (typeof vid.webkitDecodedFrameCount === 'number' && vid.webkitDecodedFrameCount > 0) return vid.webkitDecodedFrameCount;
    return vid.currentTime || 0;   // 最後備援：MediaStream 的 currentTime（幀停走時多數瀏覽器跟著停）
  },
  _armFaceWatch() {
    clearInterval(this._faceWatchT);
    try {
      const sessionKey = String((typeof activeChatSessionId !== 'undefined' && activeChatSessionId) || 'unknown');
      if (this._faceWatchSession !== sessionKey) { this._faceWatchSession = sessionKey; this._faceRebuilds = 0; this._faceFellBack = false; }
    } catch (e) {}
    this._faceStallMs = 0;
    this._faceProgressLast = -1;
    this._faceWatchT = setInterval(() => this._faceWatchTick(1000), 1000);
  },
  _faceWatchTick(stepMs) {
    if (!this.on) { clearInterval(this._faceWatchT); return; }
    const progress = this._frameProgress();
    if (progress !== this._faceProgressLast) { this._faceProgressLast = progress; this._faceStallMs = 0; return; }   // 有新幀＝健康
    if (!speechActive()) return;   // 只在「有聲音輸出但無新幀」時累計（靜默期 idle feed 幀疏、不算 stall）
    this._faceStallMs += stepMs;
    if (this._faceStallMs < 4000) return;
    this._faceStallMs = 0;
    voiceCallFail('face_stream_stalled', 'no_new_frames_4s_while_audio', { rebuilds: this._faceRebuilds || 0 });
    try { trackProductEvent('face_stream_stalled', { rebuilds: this._faceRebuilds || 0 }); } catch (e) {}
    try { this._diagNote(muneaT('avatar.forceFaceFrozen', '臉凍住(有聲4秒無新幀)'), true); } catch (e) {}
    // 正式 Gateway 把 Voice+Avatar 綁在同一張 lease。通話中關閉一條仍然 connected
    // 的 Avatar WebRTC，Avatar 會正確回報 component release，但舊總機會把整通標成
    // stale_lease，接著 App 就失去麥克風。正式通話只能做保留 transport 的視覺降級。
    if (CallControl.active) { this._fallbackVoiceOnly('stall_preserve_paired_lease'); return; }
    if ((this._faceRebuilds || 0) >= 2) { this._fallbackVoiceOnly('stall_after_rebuilds'); return; }   // 重建額度用完 → 降級純語音
    this._faceRebuilds = (this._faceRebuilds || 0) + 1;
    this._rebuildFace();
  },
  // 重建臉部連線：沿用「第一通線路 failed 自救」同一條路（refreshToken → 重新 /offer → 補亮）。
  _rebuildFace() {
    try { this.stop(); } catch (e) {}
    setTimeout(() => {
      if (typeof callConnected !== 'undefined' && !callConnected && !callDialing) return;   // 已掛斷就不重連
      const resume = CallControl.active ? CallControl.refreshToken() : Promise.resolve();
      resume.then(() => Avatar.start()).then(ok => {
        if (!ok) { Avatar._fallbackVoiceOnly('rebuild_failed'); return; }
        try {   // 通話已開場、臉重新加入：補亮會動的臉那層（開場那步早跑過、這裡自己補）
          Avatar.showLiveFrame();
          FaceIdle.stop();
        } catch (e) {}
      }).catch(() => { try { Avatar._fallbackVoiceOnly('rebuild_failed'); } catch (e) {} });
    }, 800);
  },
  // 降級成純語音繼續通話：同線聲音改走本地播放、隱藏活臉、立繪待機頂上。
  // 注意：正式 paired lease 中不可 close Avatar transport；close 會被總機視為整通釋放。
  _fallbackVoiceOnly(reason) {
    if (this._faceFellBack) return;
    this._faceFellBack = true;
    voiceCallMark('face_fallback_voice_only', 'pass', { reason: String(reason || 'face_stream_stalled'), rebuilds: this._faceRebuilds || 0 });
    try { trackProductEvent('face_fallback_voice_only', { reason: String(reason || ''), rebuilds: this._faceRebuilds || 0 }); } catch (e) {}
    try { this._diagNote(muneaT('avatar.forceFaceGiveUp', '臉救不回→降級純語音繼續'), true); } catch (e) {}
    // 關鍵：同線模式的聲音出口在臉那條線上——不切回本地播放，臉一收聲音會跟著死。
    try {
      if (typeof LiveVoice !== 'undefined' && LiveVoice._sameLine) {
        LiveVoice._sameLineFellBack = true;
        try { localStorage.setItem('munea.sameLineFellBack', String(Date.now())); } catch (e) {}
      }
    } catch (e) {}
    try { const _fa = document.getElementById('faceAud'); if (_fa) _fa.muted = true; } catch (e) {}
    try {
      const _fv = document.getElementById('faceVid');
      if (_fv) {
        _fv.muted = true;
        _fhComposite(false, _fv);
      }
      const _bg = document.querySelector('#chat .face-bg');
      if (_bg) _bg.classList.remove('livevid');
    } catch (e) {}
    try { clearInterval(this._faceWatchT); } catch (e) {} this._faceStallMs = 0;
    // 故意不呼叫 this.stop()：保留 pc/ws/session，直到使用者真的掛斷才釋放 paired lease。
    voiceCallMark('avatar_transport_preserved', 'pass', { reason: String(reason || '') });
    try { FaceIdle.start(); } catch (e) {}   // 立繪待機動畫頂上，不留凍格
    try { setLocalizedRuntimeHint('audioOnlyFallback'); } catch (e) {}
  },
  stop() {
    this.on = false;
    this._pendingPlayoutTurn = 0; this._audioTurn = 0; this._playoutArmedTurn = 0; this._directAckTurn = 0;
    this._playoutStatsBaseline = null; this._playoutStatsBusy = false; this._playoutStatsAt = 0;
    this._videoReady = false; this._feedReady = false; this._readyNotified = false;
    try { clearInterval(this._faceWatchT); } catch (e) {} this._faceStallMs = 0;   // 臉部看門一起收
    try { if (this.ws) this.ws.close(); } catch (e) {}
    try { if (this.pc) this.pc.close(); } catch (e) {}
    this.ws = this.pc = null; this._session = '';
    const vid = document.getElementById('faceVid');
    if (vid) { try { vid.srcObject = null; } catch (e) {} }
    this._renderStream = null;
    this._faceAudReceiver = null;
    // 同線收聲一起收
    try { if (this._faceAudRaf) cancelAnimationFrame(this._faceAudRaf); } catch (e) {}
    this._faceAudAnalyser = null; this._faceAudRaf = 0; this._faceAudLevel = 0; this._faceAudMaxLevel = 0;
    try { if (this._faceAudCtx) this._faceAudCtx.close(); } catch (e) {}
    this._faceAudCtx = null;
    const aud = document.getElementById('faceAud'); if (aud) { try { aud.srcObject = null; } catch (e) {} }
    const bg = document.querySelector('#chat .face-bg'); if (bg) bg.classList.remove('livevid');
    _fhComposite(false, document.getElementById('faceVid'));   // 掛斷＝收全身合成、活臉歸位、照片回來
  },
};
window.MuneaAvatar = Avatar;
// 有真影格在播才蓋上照片（無縫接手；斷了自動退回照片）
document.addEventListener('DOMContentLoaded', () => {
  const vid = document.getElementById('faceVid');
  if (vid) vid.addEventListener('playing', () => {
    // 會動的臉線路通了＝「臉就緒」候選。⚠ 第一通冷開機時 'playing' 會在「真畫面到之前」就響，
    // 這時亮出來＝整屏粉紅（空畫面被手機渲染成粉色、Edward 2026-07-11 真機抓到）。
    // 修法：等到「真的解出第一格畫」（畫面有寬度＋播放時間有在走）才發就緒信號。
    const _confirmRealFrame = (tries) => {
      if (vid.videoWidth > 0 && vid.currentTime > 0.05) {
        Avatar._facePlaying = true;
        Avatar._videoReady = true;
        voiceCallMark('avatar_first_frame', 'pass', { width: vid.videoWidth, height: vid.videoHeight });
        Avatar._notifyReady();
        Avatar._armFaceWatch();   // 首幀確認就開臉部看門（重建成功回來也會重新武裝）：有聲 4 秒無新幀＝凍住
        return;
      }
      if (tries > 0) setTimeout(() => _confirmRealFrame(tries - 1), 250);   // 最多再等 25 秒（冷開機窗）——沒真畫面就不亮、待機動畫繼續頂著
    };
    _confirmRealFrame(100);
  });
});

const LiveVoice = {
  ws: null, ac: null, mic: null, proc: null, playCtx: null, playHead: 0, on: false,
  micLevel: 0, playLevel: 0, onCaption: null, onReady: null, micOpen: false, _openMicAfterGreet: false, _capBuf: '',
  _faceDirect: false, _faceDirectRequested: false, _faceDirectSession: '', _faceDirectTurn: 0,
  _requestFaceDirect() {
    const callToken = CallControl.active && CallControl.active.call_token;
    const session = Avatar._session || '';
    const url = getAvatarUrl();
    if (!this._sameLine || !callToken || !Avatar.on || !session || !url ||
        !this.ws || this.ws.readyState !== 1) return false;
    if (this._faceDirectRequested && this._faceDirectSession === session) return true;
    try {
      this._faceDirect = false;
      this._faceDirectRequested = true;
      this._faceDirectSession = session;
      this.ws.send(JSON.stringify({ type: 'faceaudio', on: true, url, session }));
      voiceCallMark('voice_face_direct_requested', 'pass', { endpoint: url });
      return true;
    } catch (e) {
      this._faceDirectRequested = false;
      this._faceDirectSession = '';
      voiceCallFail('voice_face_direct_requested', e);
      return false;
    }
  },
  prime() {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        this._micUnavailableReason = (!window.isSecureContext && !['localhost', '127.0.0.1'].includes(location.hostname))
          ? 'https_required'
          : 'media_unavailable';
        return false;
      }
      if (!this.playCtx || this.playCtx.state === 'closed') this.playCtx = new AudioContext({ sampleRate: 24000 });
      this.playHead = this.playCtx.currentTime;
      if (!this.ac || this.ac.state === 'closed') this.ac = new AudioContext();
      this._resumeAudio();
      if (!this._primeMicPromise) {
        this._primeMicPromise = navigator.mediaDevices.getUserMedia({ audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: false,
          channelCount: { ideal: 1 },
          sampleRate: { ideal: 48000 },
        } })
          .then(stream => ({ stream })).catch(error => ({ error }));
      }
      return true;
    } catch (e) { return false; }
  },
  _resumeAudio() {
    [this.ac, this.playCtx].forEach(ctx => {
      try { if (ctx && ctx.state === 'suspended') { const p = ctx.resume(); if (p && p.catch) p.catch(() => {}); } } catch (e) {}
    });
  },
  _setMicOpen(open) {
    this.micOpen = !!open;
    clearTimeout(this._micWatchT);
    if (!this.micOpen) return;
    this._resumeAudio();
    const sentAtOpen = this._micPackets || 0;
    this._micWatchT = setTimeout(() => {
      if (!this.micOpen || (this._micPackets || 0) > sentAtOpen) return;
      this._resumeAudio();
      try { trackProductEvent('voice_mic_stalled', { audioState: this.ac && this.ac.state, trackState: this.mic && this.mic.getAudioTracks()[0] && this.mic.getAudioTracks()[0].readyState }); } catch (e) {}
      setLocalizedRuntimeHint('microphoneTapToResume');
      if (!this._micGestureBound) {
        this._micGestureBound = true;
        const recover = () => {
          this._micGestureBound = false;
          this._resumeAudio();
          setLocalizedRuntimeHint('listening');
        };
        try { document.getElementById('chat').addEventListener('click', recover, { once: true }); } catch (e) {}
      }
    }, 1800);
  },
  _sendMicBuffer(buf) {
    if (!this.ws || this.ws.readyState !== 1 || !buf) return;
    this.ws.send(buf);
    this._micPackets = (this._micPackets || 0) + 1;
    if (!this._firstMicPacketRecorded) {
      this._firstMicPacketRecorded = true;
      voiceCallMark('microphone_first_packet', 'pass', { bytes: buf.byteLength || 0, silent: buf === this._silentBuf });
    }
  },
  _noteUserMicActivity(rms, frameMs, speakerActive) {
    if (speakerActive || !this.micOpen) { this._userSpeechMs = 0; return; }
    const floor = Math.max(0, Number(this._bargeState && this._bargeState.noiseFloor) || 0.006);
    const threshold = Math.min(0.04, Math.max(0.018, floor * 3));
    if (rms >= threshold) {
      this._lastHumanVoiceAt = Date.now();
      this._userSpeechQuietMs = 0;
      this._userSpeechMs = (this._userSpeechMs || 0) + frameMs;
      this._userSpeechPeak = Math.max(this._userSpeechPeak || 0, rms);
      if (!this._userSpeechLatched && this._userSpeechMs >= 150) {
        this._userSpeechLatched = true;
        this._pendingUserSpeech = { startedAt: performance.now(), peakRms: this._userSpeechPeak, threshold };
        try { trackProductEvent('voice_user_speech_detected', { peakRms: +this._userSpeechPeak.toFixed(4), threshold: +threshold.toFixed(4) }); } catch (e) {}
        clearTimeout(this._userSpeechWatchT);
        this._userSpeechWatchT = setTimeout(() => {
          const pending = this._pendingUserSpeech;
          if (!pending) return;
          this._pendingUserSpeech = null;
          try { trackProductEvent('voice_user_speech_unrecognized', { waitMs: Math.round(performance.now() - pending.startedAt), peakRms: +pending.peakRms.toFixed(4) }); } catch (e) {}
        }, 4000);
      }
      return;
    }
    this._userSpeechMs = Math.max(0, (this._userSpeechMs || 0) - frameMs * 1.5);
    if (!this._userSpeechLatched) return;
    this._userSpeechQuietMs = (this._userSpeechQuietMs || 0) + frameMs;
    if (this._userSpeechQuietMs >= 600) {
      this._userSpeechLatched = false;
      this._userSpeechQuietMs = 0;
      this._userSpeechPeak = 0;
    }
  },
  _ackUserSpeech() {
    const pending = this._pendingUserSpeech;
    if (!pending) return;
    this._pendingUserSpeech = null;
    clearTimeout(this._userSpeechWatchT);
    try { trackProductEvent('voice_user_speech_recognized', { waitMs: Math.round(performance.now() - pending.startedAt), peakRms: +pending.peakRms.toFixed(4) }); } catch (e) {}
  },
  _takeAssistantAudio(data) {
    if (!(data instanceof ArrayBuffer) || data.byteLength < 2 || data.byteLength % 2 !== 0) return null;
    if (this._assistantAudioStarted) return data;
    if (!this._assistantAudioPending) this._assistantAudioPending = [];
    this._assistantAudioPending.push(new Uint8Array(data));
    this._assistantAudioPendingBytes = (this._assistantAudioPendingBytes || 0) + data.byteLength;
    if (this._assistantAudioPendingBytes < 960) {
      if (!this._tinyAudioRecorded) {
        this._tinyAudioRecorded = true;
        try { trackProductEvent('voice_tiny_audio_buffered', { bytes: this._assistantAudioPendingBytes, minimumBytes: 960 }); } catch (e) {}
      }
      return null;
    }
    const combined = new Uint8Array(this._assistantAudioPendingBytes);
    let offset = 0;
    this._assistantAudioPending.forEach(chunk => { combined.set(chunk, offset); offset += chunk.byteLength; });
    this._assistantAudioPending = [];
    this._assistantAudioPendingBytes = 0;
    this._assistantAudioStarted = true;
    return combined.buffer;
  },
  _resetAssistantAudioGate() {
    this._assistantAudioPending = [];
    this._assistantAudioPendingBytes = 0;
    this._assistantAudioStarted = false;
    this._tinyAudioRecorded = false;
  },
  _resetBargeInDetector() {
    const policy = window.MuneaVoiceTurnPolicy;
    const floor = this._bargeState && this._bargeState.noiseFloor;
    this._bargeState = policy ? policy.createState(floor) : null;
    this._bargePreRoll = [];
    this._bargeInActive = false;
    this._bargeProposalPending = false;
    this._bargeSpeechOnsetAt = 0;
    this._duckPreRoll = [];
    this._duckPostRoll = [];
  },
  _stopAssistantPlayback() {
    clearTimeout(this._speakTimer);
    (this._srcs || []).forEach(source => { try { source.stop(); } catch (e) {} });
    this._srcs = [];
    if (this.playCtx) this.playHead = this.playCtx.currentTime;
    this.playLevel = 0;
    this.speaking = false;
    this._playoutUntil = performance.now();
    this._newAvatarTurn = true;
    this._turnHasScheduledAudio = false;
    this._capBuf = '';
    this._resetAssistantAudioGate();
    this._setFaceAudioMuted(true);
    Avatar.reset();
  },
  _ensureLocalPlaybackGain() {
    if (!this.playCtx || this.playCtx.state === 'closed') return null;
    if (this._playGain && this._playGain.context === this.playCtx) return this._playGain;
    try {
      const gain = this.playCtx.createGain();
      gain.gain.value = 1;
      gain.connect(this._avAnalyser || this.playCtx.destination);
      this._playGain = gain;
      return gain;
    } catch (e) { return null; }
  },
  // 收集一小段持續人聲，再交給 Voice 判斷是不是插話（2026-08-11）。
  //
  // 為什麼要多這一關：Edward 8/8 真機「整句話頻繁出現斷字、卡住一個字跳針」。
  // 舊行為＝一判定你插話就硬停播放＋清空臉那邊的緩衝，代價是**要重新囤半秒才出得了聲**。
  // 判對了沒事（你本來就要講話），**判錯了就是斷字**——而在手機開擴音的情況下，
  // 她自己的聲音繞回麥克風本來就容易被誤判。
  //
  // 1.0.62 證明「先壓低 24dB」仍是可聽的斷字：手機擴音的回音會反覆觸發候選，
  // 即使 Voice 最後拒絕，使用者已經先聽到每句被壓扁。候選期不准碰播放；只有
  // Voice 回 barge_in_ack accepted 後才停止聲音，讓伺服器成為唯一裁決者。
  _maybeBargeIn(rms, threshold, sustainMs, preRoll, detectedSpeechMs) {
    if (this._bargeInActive || this._duckPendingAt) return;
    const policy = window.MuneaVoiceTurnPolicy;
    // 第一步只收證據，不壓音量、不砍話、不清緩衝。
    this._duckPendingAt = performance.now();
    this._duckPreRoll = Array.isArray(preRoll) ? preRoll.slice() : [];
    this._duckPostRoll = [];
    voiceCallMark('barge_in_candidate_observing', 'pass', { rms: Math.round(rms*1000)/1000, sustainMs, playbackChanged: false });
    var self=this;
    // 第二步：再看短暫確認窗。真人插話會持續講；回音殘響撐不了那麼久。
    const confirmMs = policy ? policy.DEFAULTS.duckConfirmMs : 110;
    this._duckConfirmT = setTimeout(function(){
      self._duckPendingAt = 0;
      // This is only a proposal trigger. The App never decides who spoke and
      // never cuts playback here; the Voice speaker arbiter owns the verdict.
      if (self._duckPostRoll.length >= 3) {
        const confirmedSpeechMs = self._bargeSpeechOnsetAt
          ? Math.max(0, performance.now() - self._bargeSpeechOnsetAt)
          : Math.max(0, Number(detectedSpeechMs) || 0) + confirmMs;
        const evidence = self._duckPreRoll.concat(self._duckPostRoll);
        self._beginBargeIn(
          rms, threshold, sustainMs, evidence, confirmedSpeechMs,
          self._duckPostRoll.length,
        );   // 送候選；是否為真人插話只由 Voice 裁決
      } else {
        voiceCallMark('barge_in_candidate_abandoned', 'pass', { recoveredMs: confirmMs });
      }
    }, confirmMs);
  },
  _beginBargeIn(rms, threshold, sustainMs, preRoll, detectedSpeechMs, postDuckFrames = 0) {
    if (this._bargeInActive || this._bargeProposalPending) return;
    this._bargeProposalPending = true;
    try { clearTimeout(this._duckConfirmT); } catch (e) {}
    this._duckPendingAt = 0;
    const policy = window.MuneaVoiceTurnPolicy;
    // Two-phase barge-in: ask the server to buffer the following evidence,
    // deliver the retained microphone onset, then commit the interruption.
    // WebSocket ordering guarantees the server judges after hearing evidence.
    const evidence = Array.isArray(preRoll) ? preRoll : [];
    const payload = {
      rms: +rms.toFixed(4),
      candidate_threshold: +threshold.toFixed(4),
      sustain_ms: Math.max(0, Number(sustainMs) || 0),
      evidence_frames: evidence.length,
      // Candidate observation no longer ducks playback. Declaring these as
      // post-duck evidence would make Voice use the lower quiet-room threshold
      // on loudspeaker echo and recreate the self-interruption server-side.
      post_duck_frames: 0,
      candidate_tail_frames: Math.max(0, Number(postDuckFrames) || 0),
      post_duck_sustain_ms: policy ? policy.DEFAULTS.duckEvidenceMs : 80,
      detected_speech_ms: Math.round(Math.max(0, Number(detectedSpeechMs) || 0)),
      timing_basis: 'audio_callback_estimate',
      playback_unchanged: true,
    };
    try { this.ws.send(JSON.stringify({ type: 'barge_in_start', ...payload })); } catch (e) {}
    evidence.forEach(frame => this._sendMicBuffer(frame));
    try { this.ws.send(JSON.stringify({ type: 'barge_in', ...payload })); } catch (e) {}
    try { trackProductEvent('voice_barge_in_candidate', payload); } catch (e) {}
    voiceCallMark('barge_in_candidate_sent', 'pass', {
      detectedSpeechMs: payload.detected_speech_ms,
      openingGuard: payload.sustain_ms > ((policy && policy.DEFAULTS.sustainMs) || 150),
      timingBasis: payload.timing_basis,
    });
  },
  // 2026-08-08 Edward 拍板：「讓她放棄主動打招呼，改由用戶先說第一句話她才開始回話」。
  //
  // 為什麼這樣比較好：她主動開口那一句，得先繞去顯示卡算嘴型再回來，
  // 使用者只能盯著畫面等——而那正是「接通後感覺當機」的來源。
  // 改成使用者先說：接通即可出聲，她收到才回，沒有任何人在等一句罐頭招呼。
  //
  // 唯一的例外是**家人傳話**：那是有人託她轉達的具體內容，
  // 讓使用者先開口反而會錯過，所以這種情況仍由她先說。
  greet() {
    try {
      if (!(this.ws && this.ws.readyState === 1)) return;
      const relay = this._pendingRelay || null;
      if (!relay) { voiceCallMark('greeting_skipped', 'pass', { reason: 'user_speaks_first' }); return; }
      this.ws.send(JSON.stringify({ type: 'greet', relay }));
      voiceCallMark('greeting_requested', 'pass', { reason: 'family_relay' });
    } catch (e) { voiceCallFail('greeting_requested', e); }
  },   // 只有「家人託她轉達」才主動開口；其餘一律等使用者先說
  async prepareRelay() {
    if (this._pendingRelay) return this._pendingRelay;
    this._relaySpokenId = null;
    try { this._pendingRelay = await claimNextFamilyRelay(); } catch (e) { this._pendingRelay = null; }
    return this._pendingRelay;
  },
  async _finishRelay(action) {
    const relay = this._pendingRelay;
    if (!relay || this._relayFinishing) return false;
    this._relayFinishing = true;
    let ok = false;
    try { ok = await finishFamilyRelayClaim(relay, action); } catch (e) {}
    this._relayFinishing = false;
    if (ok || action === 'release') this._pendingRelay = null;
    if (action === 'ack' && ok) {
      this._relaySpokenId = null;
      try {
        const receipts = JSON.parse(localStorage.getItem('munea.familyRelayReceipts') || '{}') || {};
        delete receipts[relay.id]; localStorage.setItem('munea.familyRelayReceipts', JSON.stringify(receipts));
      } catch (e) {}
    } else if (action === 'ack' && this._pendingRelay) {
      clearTimeout(this._relayAckRetry);
      this._relayAckRetry = setTimeout(() => this._finishRelay('ack'), 5000);
    }
    return ok;
  },
  nudge(level) { try { if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({ type: 'nudge', level: level || 1 })); } catch (e) {} },   // 使用者一直沒講話 → 請 AI 溫柔提醒（省點 · Edward 2026-07-10）
  // 掛斷時把整通對話送去萃取長期記憶（讓「聊聊」講的也記得住 · Edward 2026-07-10）——跟文字聊天同一條記憶入口
  saveMemory() {
    try {
      const t = (this._transcript || []).filter(x => x && (x.text || '').trim());
      if (t.length < 2) return;   // 至少一來一往才值得記
      brainPost('/butler/post-turn', {
        history: t.slice(-24),
        char: currentChar,
        companionProfile: savedCompanionProfile,
        sessionId: activeChatSessionId,
        ...authAnalyticsContext(),
      });
    } catch (e) {}
  },
  _f2i(f) { const b = new Int16Array(f.length); for (let i = 0; i < f.length; i++) { let s = Math.max(-1, Math.min(1, f[i])); b[i] = s < 0 ? s * 0x8000 : s * 0x7fff; } return b; },
  _down(buf, inR, outR) { if (outR >= inR) return buf; const r = inR / outR, len = Math.round(buf.length / r), o = new Float32Array(len); let i = 0, j = 0; while (j < len) { const n = Math.round((j + 1) * r); let s = 0, c = 0; for (; i < n && i < buf.length; i++) { s += buf[i]; c++; } o[j++] = c ? s / c : 0; } return o; },
  _toSpeaking() { if (this.speaking) return; this.speaking = true; if (this.onSpeak) this.onSpeak(); },
  _playbackLeadSeconds() {
    // The first answer arrives while the iPhone audio route and Avatar WebRTC
    // jitter buffer are still settling. A 480 ms queue is intentionally used
    // for that first turn; later turns keep the existing low-latency behavior.
    const base = (this._playbackTurn || 0) <= 1 ? 0.48 : 0.22;
    return Math.min(0.72, base + Math.min(3, this._playbackUnderruns || 0) * 0.08);
  },
  _scheduleLocalPlayback(f) {
    const b = this.playCtx.createBuffer(1, f.length, 24000); b.getChannelData(0).set(f);
    const s = this.playCtx.createBufferSource(); s.buffer = b; s.connect(this._ensureLocalPlaybackGain() || this._avAnalyser || this.playCtx.destination);
    const now = this.playCtx.currentTime;
    let offset = 0.18;
    try {
      if (typeof Avatar !== 'undefined' && Avatar.on) {
        const flashhead = (typeof faceEngine === 'function' && faceEngine() === 'flashhead');
        let ms = flashhead ? 200 : parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
        if (isNaN(ms) || ms < 0 || ms > 3000) ms = flashhead ? 200 : 900;
        offset = ms / 1000;
      }
    } catch (e) {}
    offset = Math.max(offset, this._playbackLeadSeconds());
    if (!this._turnHasScheduledAudio) {
      this.playHead = now + offset;
      this._turnHasScheduledAudio = true;
    } else if (this.playHead < now + 0.06) {
      this._playbackUnderruns = (this._playbackUnderruns || 0) + 1;
      this.playHead = now + this._playbackLeadSeconds();
      try { trackProductEvent('voice_playback_underrun', { turn: this._playbackTurn, count: this._playbackUnderruns }); } catch (e) {}
    }
    s.start(this.playHead); this.playHead += b.duration;
    if (!this._srcs) this._srcs = [];
    this._srcs.push(s); s.onended = () => { const k2 = this._srcs.indexOf(s); if (k2 >= 0) this._srcs.splice(k2, 1); this._toListening(); };
    this._toListening();
  },
  _setFaceAudioMuted(muted) {
    // faceAud 永久靜音，只當 analyser 的 MediaStream 來源；faceVid 是唯一同線播放器。
    try { const meter = document.getElementById('faceAud'); if (meter) meter.muted = true; } catch (e) {}
    try { const player = document.getElementById('faceVid'); if (player) player.muted = !!muted; } catch (e) {}
  },
  async _faceAudioSnapshot() {
    let bytes = 0, audioLevel = -1, hasStats = false;
    try {
      const receiver = Avatar._faceAudReceiver;
      if (receiver && receiver.getStats) {
        const stats = await receiver.getStats();
        stats.forEach(r => {
          if (r.type !== 'inbound-rtp' || (r.kind !== 'audio' && r.mediaType !== 'audio')) return;
          hasStats = true;
          if (typeof r.bytesReceived === 'number') bytes = r.bytesReceived;
          if (typeof r.audioLevel === 'number') audioLevel = r.audioLevel;
        });
      }
    } catch (e) {}
    return { bytes, audioLevel, hasStats };
  },
  async prepareOpeningAudioPath(waitMs = 600) {
    if (!this._sameLine) {
      this._sameLineWarmup = false;
      return { mode: 'local_audio', verified: true, receiverAttached: false };
    }
    this._sameLineWarmup = true;
    this._setFaceAudioMuted(true);
    const receiverDeadline = Date.now() + Math.max(0, Math.min(600, waitMs || 0));
    while (this.on && !Avatar._faceAudReceiver && Date.now() < receiverDeadline) {
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    const after = await this._faceAudioSnapshot();
    const receiverAttached = !!Avatar._faceAudReceiver;
    // WebRTC 的音訊軌本來就持續送靜音；只確認接收器已掛上即可。
    // 舊版另外送 1 秒零 PCM 給 Avatar，會建立一個假的模型回合，可能與
    // 第一個真回答競爭 feeder／GPU 佇列，造成開頭反覆起音又被切掉。
    const stable = receiverAttached;
    this._sameLineWarmup = false;
    if (stable) {
      this._sameLineFellBack = false;
      this._setFaceAudioMuted(false);
    } else {
      this._sameLineFellBack = true;
      this._setFaceAudioMuted(true);
    }
    const mode = stable ? 'receiver_ready' : 'local_fallback';
    try { trackProductEvent('voice_sameline_warmup', { result: stable ? 'ready' : mode, bytes: after.bytes, audioLevel: after.audioLevel, hasStats: after.hasStats, receiverAttached, stage: 'before_first_user_turn', syntheticPcm: false }); } catch (e) {}
    return { mode, verified: stable, receiverAttached };
  },
  // ── 同線聲音「中途斷續」監測＋自動退回（2026-07-29 · 穩定度）──
  // 背景：同線模式下聲音繞三趟（伺服器→手機→臉機→WebRTC回手機），只要上行或臉機
  // 慢一下，使用者聽到的就是「卡一下／吃掉一個字」。而既有保底只在「開頭 3 秒完全沒聲」
  // 才退回本地播放——只擋「死掉」、沒擋「斷續」，跟伺服器端 7/29 修掉的是同一類設計漏洞。
  // 真機數據佐證（正式庫 sameline_check）：Edward 7/28 的通話全部走同線（result: kept），
  // 但通話中段沒有任何量測——他回報的卡卡正好發生在沒人看的地方。
  // 判法：每 200ms 問一次連線「聲音位元組有沒有在增加」（getStats，iPhone 讀得到；
  // 不用音量量表——iPhone Web Audio 讀遠端串流恆為 0，7/12 已踩過）。
  // 「她此刻應該在講話」（_playoutUntil 未到）而位元組不動連續兩拍＝一次斷續；
  // 一通累積 2 次＝這條線不可靠，退回本地播放（聲音穩定優先，臉可能慢半拍——
  // 跟伺服器端同一個取捨：長輩主要用聽的）。每次斷續都回報後台，之後不用截圖就有數據。
  _sameLineFallBackNow(reason) {
    // 2026-07-29 深夜 Edward 真機（1.0.46 · 22:15 通）抓到第一版的錯：這裡原本只把
    // 同線那軌靜音、聲音改走手機播——但**臉還在雲端自己的時鐘上繼續演**，聲音跟嘴
    // 從此兩個時鐘、越走越歪（「查詢後嘴巴慢慢對不上」）；切換瞬間兩條出聲路的音量
    // 也不同（「忽大忽小」）。教訓：**切聲音就要一起收臉**——不留一張說謊的嘴。
    // 改為整套走 Avatar._fallbackVoiceOnly（收掉活臉、換待機立繪、掛提示、標記同線退回），
    // 跟「影像凍住救不回」同一條已驗證的降級路。
    this._sameLineFellBack = true;
    this._slFallbackAfterTurn = '';
    try { clearTimeout(this._slBoundaryFallbackT); } catch (e) {}
    this._slBoundaryFallbackT = null;
    try { trackProductEvent('sameline_fellback', { reason: String(reason || '') }); } catch (e) {}
    try { Avatar._diagNote(muneaT('avatar.forceSameLineFallback', '同線退回本地({reason})→臉一起收、換待機', { reason }), true); } catch (e) {}
    try { Avatar._fallbackVoiceOnly('sameline_' + String(reason || 'stutter')); } catch (e) {
      // 後備（降級路本身出錯時至少把聲音顧好）：靜音同線那軌、防兩邊一起出聲（7/11 教訓）
      try { const _fa = document.getElementById('faceAud'); if (_fa) _fa.muted = true; } catch (e2) {}
      try { const _fv = document.getElementById('faceVid'); if (_fv) _fv.muted = true; } catch (e2) {}
      try { localStorage.setItem('munea.sameLineFellBack', String(Date.now())); } catch (e2) {}
    }
  },
  _queueSameLineBoundaryFallback(reason, detail) {
    // 位元組統計的短停頓只能觀測，不能拆掉本通 Avatar。1.0.62 的查詢「有聲無嘴」
    // 就是這個 heuristic 在第二次 microstall 後排程 voice-only fallback。真正 4 秒
    // 無影格的硬故障仍由 Avatar._faceWatchTick 處理，兩者不得混為一談。
    if (!this._sameLine || this._sameLineFellBack === true) return;
    try { trackProductEvent('sameline_fallback_suppressed', { reason: String(reason || 'quality'), ...(detail || {}) }); } catch (e) {}
  },
  _scheduleSameLineBoundaryFallback() {
    const reason = this._slFallbackAfterTurn;
    if (!reason || !this.on || this._sameLineFellBack === true) return;
    try { clearTimeout(this._slBoundaryFallbackT); } catch (e) {}
    const waitMs = Math.max(0, Math.min(30000, (this._playoutUntil || 0) - performance.now() + 160));
    this._slBoundaryFallbackT = setTimeout(() => {
      this._slBoundaryFallbackT = null;
      if (!this.on || this._sameLineFellBack === true) return;
      this._sameLineFallBackNow(reason);
    }, waitMs);
  },
  _armSameLineStutterWatch() {
    if (this._slStutterT) return;
    this._slPrevBytes = -1; this._slStallStreak = 0; this._slStalls = 0; this._slSlowLeads = 0;
    // 2026-08-01 量測修正（Edward 7/31 深夜回報「斷斷續續」，翻紀錄卻查無實據）：
    // 這支表把「她這輪還沒開口」跟「講到一半斷掉」混成同一個數字。每輪伺服器一送
    // 聲音，_playoutUntil 就往前推＝「她應該在講了」，但臉機要 1-2 秒才開始把聲音
    // 送回來，於是每一輪固定誤記一次斷續（7/31 那通 6 輪剛好 6 次）。
    // 拆成兩個各自誠實的數字：①臉機這輪隔多久才開口（sameline_face_lead_ms）
    // ②真的開口以後中途斷了幾次（sameline_audio_stall，開口後才起算）。
    this._slFaceStarted = false; this._slTurnStartAt = 0;
    this._slStutterT = setInterval(async () => {
      if (!this.on || !this._sameLine || this._sameLineFellBack === true) {
        clearInterval(this._slStutterT); this._slStutterT = null; return;
      }
      const now = performance.now();
      // 只在「她此刻應該正在講話」的時間窗內量；剩不到 400ms 的句尾不算（自然收尾）
      if (!this._playoutUntil || now > this._playoutUntil - 400) {
        this._slStallStreak = 0; this._slPrevBytes = -1;
        this._slFaceStarted = false; this._slTurnStartAt = 0;
        return;
      }
      if (!this._slTurnStartAt) this._slTurnStartAt = now;   // 這一輪開始該有聲音了（±0.2 秒）
      let bytes = -1;
      try {
        const rcv = Avatar._faceAudReceiver;
        if (rcv && rcv.getStats) {
          const st = await rcv.getStats();
          st.forEach(r => { if (r.type === 'inbound-rtp' && (r.kind === 'audio' || r.mediaType === 'audio') && typeof r.bytesReceived === 'number') bytes = r.bytesReceived; });
        }
      } catch (e) {}
      if (bytes < 0) return;   // 讀不到就不判（寧可漏一拍、不誤退）
      if (!this._slFaceStarted) {
        // 這一輪臉機還沒開始送聲音回來：這段不算斷續，只量它讓人等了多久。
        if (this._slPrevBytes >= 0 && (bytes - this._slPrevBytes) >= 80) {
          this._slFaceStarted = true;
          const leadMs = Math.round(now - this._slTurnStartAt);
          const leadLimitMs = (this._playbackTurn || 0) <= 1 ? 1800 : 1200;
          try { trackProductEvent('sameline_face_lead_ms', { ms: leadMs, turn: this._playbackTurn || 0 }); } catch (e) {}
          if (leadMs > leadLimitMs) {
            this._slSlowLeads = (this._slSlowLeads || 0) + 1;
            try { trackProductEvent('sameline_face_slow', { ms: leadMs, limitMs: leadLimitMs, count: this._slSlowLeads, turn: this._playbackTurn || 0 }); } catch (e) {}
            if (leadMs >= 2500 || this._slSlowLeads >= 2) this._queueSameLineBoundaryFallback('slow_face_lead', { ms: leadMs, count: this._slSlowLeads });
          } else {
            this._slSlowLeads = 0;
          }
        }
        this._slPrevBytes = bytes;
        return;
      }
      const byteDelta = this._slPrevBytes >= 0 ? (bytes - this._slPrevBytes) : -1;
      if (byteDelta >= 0 && byteDelta < 80) {
        this._slStallStreak += 1;
        if (this._slStallStreak === 2) {   // 連續兩拍（約 400ms）幾乎沒聲進來＝約 1-2 個字
          this._slStalls += 1;
          try { trackProductEvent('sameline_audio_stall', { count: this._slStalls, durationMs: 400, byteDelta, turn: this._playbackTurn || 0 }); } catch (e) {}
          try { trackProductEvent('sameline_audio_microstall', { count: this._slStalls, durationMs: 400, byteDelta, turn: this._playbackTurn || 0 }); } catch (e) {}
          // 只記錄、不動手：這偵測器在真機上每通可能誤觸發——
          // 她每輪開口前臉機要 1-2 秒處理，那段「該講卻沒聲」被誤算成斷流（turn 2/3/7
          // 的 telemetry 全是這型）。自動切換帶來的雪崩（忽大忽小/臉不同步/回音自斷）
          // 比它要治的斷續傷害大得多（Edward 7/30 親測退步）。保留計數與事件、
          // 拿真數據把「輪首處理延遲」跟「真斷流」分開之後，才考慮放回自動切換。
          if (this._slStalls >= 2 && !this._slWouldFallbackSent) {
            this._slWouldFallbackSent = true;
            try { trackProductEvent('sameline_would_fallback', { turn: this._playbackTurn || 0 }); } catch (e) {}
            this._queueSameLineBoundaryFallback('repeated_microstall', { count: this._slStalls });
          }
        }
      } else {
        this._slStallStreak = 0;
      }
      this._slPrevBytes = bytes;
    }, 200);
  },
  _notePlayout(byteLength) {
    const now = performance.now();
    const useSameLine = this._sameLine && !this._sameLineWarmup && this._sameLineFellBack !== true;
    const sameLineDelay = Math.max(200, Math.min(350,
      Number(Avatar._lastPrebufferMs) || ((this._playbackTurn || 0) <= 1 ? 350 : 200)));
    const delay = useSameLine ? sameLineDelay : Math.round(this._playbackLeadSeconds() * 1000);
    if (!this._playoutUntil || this._playoutUntil < now) this._playoutUntil = now + delay;
    this._playoutUntil += (byteLength / (24000 * 2)) * 1000;
  },
  _toListening() {
    clearTimeout(this._speakTimer);
    const remain = Math.max(0, (this._playoutUntil || 0) - performance.now());
    if (remain > 80) {
      this._speakTimer = setTimeout(() => this._toListening(), remain + 120);
      return;
    }
    this.speaking = false; this.playLevel = 0;
    if (this._relaySpokenId && this._pendingRelay && this._relaySpokenId === this._pendingRelay.id) this._finishRelay('ack');
    if (this._openMicAfterGreet) { this._setMicOpen(true); this._openMicAfterGreet = false; }
    if (this.onListen) this.onListen();
  },
  // 全零靜音包（正式開麥前餵給上行）：長度跟真收音包一致。內容永遠是 0，你的聲音絕不會提早上傳。
  _silentUplinkFrame(inputLen) {
    const rate = (this.ac && this.ac.sampleRate) || 48000;
    const len = Math.max(1, Math.round(inputLen * 16000 / rate));
    if (!this._silentBuf || this._silentBufLen !== len) { this._silentBufLen = len; this._silentBuf = new Int16Array(len).buffer; }
    return this._silentBuf;
  },
  // 把「麥克風 → 降採樣 → 上行」的送音迴圈接上目前的 mic stream（start 建管、看門狗重建都走這裡）。
  _attachMicProcessor() {
    const src = this.ac.createMediaStreamSource(this.mic);
    this._micSrc = src;
    this.proc = this.ac.createScriptProcessor(2048, 1, 1);
    src.connect(this.proc); this.proc.connect(this.ac.destination);
    // Echo cancellation handles normal speaker leakage. While the assistant
    // speaks, a sustained near-field voice opens a short pre-roll path so
    // the user can barge in without streaming every speaker echo frame.
    this.proc.onaudioprocess = e => {
      const inp = e.inputBuffer.getChannelData(0);
      if (!this.micOpen) {
        // 收音管不等人（2026-07-16 蟲 b 根治）：還沒「正式開麥」也讓上行從 WebSocket open 那一刻
        // 就是活的——伺服器不再看到 in_bytes=0、看門狗能分辨「管線死了」跟「還沒開麥」。
        // 降頻保活（PR #136 review 帳單題）：守門期間不全速灌靜音，每 500ms 才送一小包全零
        // （42.7ms 音訊 ≈ 1 token；只為保活＋uplink 偵測）；開麥後才全速送真音訊——
        // 開場與按靜音期間的 Gemini 輸入 token 從每分鐘 ~1500 降到 ~128、幾乎不增帳。
        // 內容守門照舊：開麥前送的是全零、不是真收音，你的聲音絕不會在她招呼前灌進去（Edward 2026-07-09 規則不變）。
        this.micLevel = 0;
        const nowMs = performance.now();
        if (!this._silentKeepaliveAt || nowMs - this._silentKeepaliveAt >= 500) {
          this._silentKeepaliveAt = nowMs;
          this._sendMicBuffer(this._silentUplinkFrame(inp.length));
        }
        return;
      }
      let s = 0; for (let i = 0; i < inp.length; i++) s += inp[i] * inp[i];
      const rms = Math.sqrt(s / inp.length);
      this.micLevel = Math.min(1, rms * 8);   // 即時音量→收音波頻高度
      const buf = this._f2i(this._down(inp, this.ac.sampleRate, 16000)).buffer;
      const speakerActive = speechActive();
      const policy = window.MuneaVoiceTurnPolicy;
      const frameMs = (inp.length / this.ac.sampleRate) * 1000;
      this._noteUserMicActivity(rms, frameMs, speakerActive);
      // 開場前兩輪 iPhone 回音消除還沒收斂、回音殘留最強 → 插話判定拉嚴一級（openingSustainMs）
      const _opening = (this._playbackTurn || 0) <= 1;
      const sustainOpts = policy && _opening
        ? { sustainMs: policy.DEFAULTS.openingSustainMs } : undefined;
      // 預捲格數跟著門檻走：門檻拉長（開場 300ms）預捲也要跟著蓋過去，不然判定成功時開頭已被丟掉
      // ＝「回長話第一句沒反應」根因之一（2026-07-16 Edward 真機三訴②）
      const _preFrames = policy ? (_opening ? policy.DEFAULTS.openingPreRollFrames : policy.DEFAULTS.preRollFrames) : 6;

      if (speakerActive && this._bargeInActive) {
        this._sendMicBuffer(buf);
        return;
      }
      if (speakerActive && this._bargeProposalPending) return;
      if (speakerActive && policy) {
        this._postGuardUntil = performance.now() + policy.DEFAULTS.postSpeechGuardMs;   // 她一停口即進守門期
        if (this._duckPendingAt) {
          // Only fresh frames captured after the speaker was ducked can prove
          // that a nearby user is still speaking.  The old path spliced these
          // frames away and later judged the original speaker-echo pre-roll.
          // These are evidence only. Voice owns the sole speaker verdict.
          this._duckPostRoll.push(buf);
          while (this._duckPostRoll.length > 6) this._duckPostRoll.shift();
          return;
        }
        this._bargePreRoll.push(buf);
        while (this._bargePreRoll.length > _preFrames) this._bargePreRoll.shift();
        const observedAt = performance.now();
        const previousSpeechMs = Math.max(0, Number(this._bargeState && this._bargeState.speechMs) || 0);
        const observed = policy.observe(this._bargeState, rms, frameMs, true, sustainOpts);
        this._bargeState = observed.state;
        if (observed.state.speechMs > 0 && previousSpeechMs <= 0) {
          // Web Audio hands us a completed buffer. Approximate physical onset
          // at that buffer's start, then keep a monotonic wall-clock through
          // brief dips instead of reporting only the configured sustain value.
          this._bargeSpeechOnsetAt = observedAt - frameMs;
        } else if (observed.state.speechMs <= 0) {
          this._bargeSpeechOnsetAt = 0;
        }
        if (!observed.shouldInterrupt) return;
        const preRoll = this._bargePreRoll.splice(0);
        const sustainMs = sustainOpts ? sustainOpts.sustainMs : policy.DEFAULTS.sustainMs;
        const detectedSpeechMs = this._bargeSpeechOnsetAt
          ? Math.max(0, performance.now() - this._bargeSpeechOnsetAt)
          : observed.state.speechMs;
        // 先壓音量短暫確認，確定真的是他在講才砍話（誤判就只是音量抖一下，不再斷字）
        this._maybeBargeIn(rms, observed.threshold, sustainMs, preRoll, detectedSpeechMs);
        return;
      }
      if (speakerActive) { this.micLevel = 0; return; }
      // 講完後守門期（治「前 10 秒斷續/怪收音」）：她句中停頓（GLOWS 偶發 1.8~2s 供聲卡點）
      // 或剛講完的空檔，收音不裸放行——不然回音/環境噪音會被上游當成有人講話、把她打斷。
      // 真人講話走跟插話同一套「持續人聲＋預捲」判定，開頭字由預捲補回、不掉字。
      if (policy && performance.now() < (this._postGuardUntil || 0)) {
        this._bargePreRoll.push(buf);
        while (this._bargePreRoll.length > _preFrames) this._bargePreRoll.shift();
        const guarded = policy.observe(this._bargeState, rms, frameMs, true, sustainOpts);
        this._bargeState = guarded.state;
        if (!guarded.shouldInterrupt) return;
        this._postGuardUntil = 0;
        const preRoll = this._bargePreRoll.splice(0);
        preRoll.forEach(frame => this._sendMicBuffer(frame));
        return;
      }
      if (policy) {
        this._bargeState = policy.observe(this._bargeState, rms, frameMs, false).state;
        this._bargeSpeechOnsetAt = 0;
      }
      this._sendMicBuffer(buf);
    };
  },
  // 收音管「先建後招呼」（2026-07-16 蟲 b 根治）：getUserMedia 一回來就把送音迴圈建好待命，
  // 不等 WebSocket onopen、更不等她招呼講完——管線本身不等任何人，守門只管內容。
  async _setupMicPipeline(micPromise) {
    try {
      const micResult = await micPromise;
      if (this._primeMicPromise === micPromise) this._primeMicPromise = null;
      if (!micResult || !micResult.stream) return { ok: false, error: (micResult && micResult.error) || 'microphone_unavailable' };
      if (!this.on) { try { micResult.stream.getTracks().forEach(t => t.stop()); } catch (e) {} return { ok: false, error: 'call_cancelled' }; }
      this.mic = micResult.stream;
      voiceCallMark('microphone_ready', 'pass', { trackState: this.mic.getAudioTracks()[0] && this.mic.getAudioTracks()[0].readyState });
      this._resumeAudio();
      this._attachMicProcessor();
      return { ok: true };
    } catch (e) { return { ok: false, error: e }; }
  },
  // 收音管重建（看門狗用）：3 秒一包都沒送出＝音訊圖真的死了（iOS AudioContext 卡住／軌道悶掉），
  // 整組拆掉重來：新 getUserMedia＋新送音迴圈；AudioContext 卡死就換一顆新的。
  async _rebuildMicPipeline() {
    this._micRebuilds = (this._micRebuilds || 0) + 1;
    const attempt = this._micRebuilds;
    try { if (this.proc) this.proc.disconnect(); } catch (e) {}
    try { if (this._micSrc) this._micSrc.disconnect(); } catch (e) {}
    try { if (this.mic) this.mic.getTracks().forEach(t => t.stop()); } catch (e) {}
    this.proc = null; this._micSrc = null; this.mic = null;
    try {
      if (this.ac && this.ac.state !== 'running') {
        const wedged = this.ac;
        this.ac = new AudioContext();
        try { wedged.close(); } catch (e) {}
      }
    } catch (e) {}
    this._resumeAudio();
    let stream = null, error = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: false,
        channelCount: { ideal: 1 },
        sampleRate: { ideal: 48000 },
      } });
    } catch (err) { error = err; }
    if (!this.on) { try { if (stream) stream.getTracks().forEach(t => t.stop()); } catch (e) {} return false; }
    if (!stream) { voiceCallFail('microphone_uplink_rebuilt', error || 'rebuild_getusermedia_failed', { attempt }); return false; }
    this.mic = stream;
    try { this._attachMicProcessor(); } catch (e) { voiceCallFail('microphone_uplink_rebuilt', e, { attempt }); return false; }
    voiceCallMark('microphone_uplink_rebuilt', 'pass', { attempt });
    try { trackProductEvent('voice_mic_uplink_rebuilt', { attempt }); } catch (e) {}
    if (this.micOpen) setLocalizedRuntimeHint('listening');   // 重建成功、正在收音 → 蓋掉稍早的「請點一下畫面」提示
    return true;
  },
  // 收音管看門（蟲 b「整通零上行」根治）：WebSocket open 後 3 秒還沒送出第一包（開麥前也該有靜音包）
  // ＝管線根本沒活 → 記診斷並自動重建，最多 2 次；之後留給既有「點一下畫面」手勢兜底。
  _armUplinkWatch() {
    clearTimeout(this._uplinkWatchT);
    this._uplinkWatchT = setTimeout(async () => {
      if (!this.on || !this.ws || this.ws.readyState !== 1) return;
      if ((this._micPackets || 0) > 0) return;                      // 有包＝管線活著，看門收工
      voiceCallFail('microphone_uplink_slow', 'no_uplink_3000ms', { rebuilds: this._micRebuilds || 0, audioState: this.ac && this.ac.state });
      try { trackProductEvent('voice_mic_uplink_stalled', { rebuilds: this._micRebuilds || 0, audioState: this.ac && this.ac.state }); } catch (e) {}
      if ((this._micRebuilds || 0) >= 2) return;                    // 重建額度用完 → 不再重試
      await this._rebuildMicPipeline();
      if (this.on) this._armUplinkWatch();                          // 重建後再看 3 秒，確認真的有包流出
    }, 3000);
  },
  // 死線看門（蟲 c 根治 · 2026-07-16 鐵證：connected→ready 後 30 秒 closed、in/out 都 0、連開場白都沒觸發）：
  // phase='ready_timeout'：open 後 10 秒連 ready 都沒等到（半死 socket / 腦開機卡死）；
  // phase='no_audio_both_ways'：ready 後 5 秒她的開場音訊沒來、上行也一包沒送出（雙向死線）。
  // 兩者都不讓用戶乾等 30 秒 readiness gate——關掉 socket 走既有 onDrop 自動重連路，一通最多重接一次。
  // 健康通話不會誤殺：收音管先建後招呼，open 後零點幾秒就有上行（至少是靜音包）。
  _armDeadLineWatch(phase, waitMs) {
    clearTimeout(this._deadLineWatchT);
    this._deadLineWatchT = setTimeout(() => {
      if (!this.on || !this.ws || this.ws.readyState !== 1) return;
      // 2026-08-08 Edward 拍板改「使用者先說」之後，判斷要跟著改：
      // 她不再主動開口，所以「她沒出聲」變成**正常現象**，不能再當成線死掉的證據。
      // 現在唯一能證明線活著的是上行——麥克風在 ready 就開，健康的通話零點幾秒內
      // 就有封包（安靜時是靜音包）。上行一包都沒有，才是真的死線。
      const lineAlive = phase === 'ready_timeout'
        ? !!this.ready
        : ((this._micPackets || 0) > 0 || this._firstAudioRecorded);
      if (lineAlive) return;
      // ready 已經證明 Voice socket 與模型都活著；此時只有麥克風上行尚未產生封包。
      // 關 socket 會觸發 Voice 收線，再讓 Call Control 把整個 lease 結束，原本設計的
      // 自動重連反而拿到 stale_lease、畫面閃一下後誤顯示忙線。收音管看門會繼續重建，
      // 這裡保留已就緒的 Voice／Avatar 與席位，不再用「零上行」硬砍整通。
      if (phase === 'no_audio_both_ways') {
        voiceCallFail('dead_line_kept_open', 'microphone_uplink_pending', {
          micPackets: this._micPackets || 0,
          rebuilds: this._micRebuilds || 0,
          audioState: this.ac && this.ac.state,
        });
        try { this._resumeAudio(); } catch (e) {}
        setLocalizedRuntimeHint('microphonePermission');
        return;
      }
      const sessionKey = String((typeof activeChatSessionId !== 'undefined' && activeChatSessionId) || 'unknown');
      if (this._deadLineSessionId === sessionKey) {
        voiceCallFail('dead_line_reconnect', 'dead_line_persisted', { phase });
        return;   // 這通已重接過仍是死線 → 交給 30 秒 readiness gate 收整通、不無限重接
      }
      this._deadLineSessionId = sessionKey;
      voiceCallFail('dead_line_reconnect', phase + '_' + waitMs + 'ms');
      try { trackProductEvent('voice_dead_line_reconnect', { phase }); } catch (e) {}
      setLocalizedRuntimeHint('reconnecting', true);
      try { this.ws.close(); } catch (e) { try { this.stop(); } catch (e2) {} }   // close → onclose → onDrop 自動重連
    }, waitMs);
  },
  async start(onListen, onSpeak, onDrop) {
    let url = getLiveVoiceUrl();
    if (!url) { voiceCallFail('voice_endpoint', 'missing_voice_url'); return false; }
    // 帶上目前選的角色（決定聲音＋個性；漏帶會永遠是寧寧——7/8 Edward 抓的蟲）
    try { if (typeof currentChar === 'string' && currentChar) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'char=' + encodeURIComponent(currentChar); } catch (e) {}
    // 把使用者改過的名字帶給語音伺服器，讓 AI 知道自己現在叫什麼
    try { const nm = (typeof cname === 'function' ? cname() : ''); if (nm) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'name=' + encodeURIComponent(nm); } catch (e) {}
    try { const _md = (window.MM && window.MM.currentMood) ? window.MM.currentMood() : ''; if (_md) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'mood=' + encodeURIComponent(_md); } catch (e) {}
    // 帶上他挑的興趣話題，讓 AI 開場就聊得對味
    try { const _ts = loadInterests(); if (_ts.length) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'topics=' + encodeURIComponent(_ts.join(',')); } catch (e) {}
    // AI 怎麼稱呼「你」＝個人資料的家人稱呼優先、沒填用名稱（7/9 Edward 拍板：不吃帳號）
    try {
      const _pp = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
      const _uad = ((_pp.nick || '').trim() || (_pp.name || '').trim());
      if (_uad) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'user=' + encodeURIComponent(_uad);
      // 所在地（可到區）→ 讓寧寧推薦附近真的吃得到的餐廳、聊在地話題（不再亂猜位置 · 7/9 Edward）
      const _loc = (_pp.city || '').trim();
      if (_loc) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'loc=' + encodeURIComponent(_loc);
      // 年齡→語音節奏資料通道（開帳與個人資料重整 2026-07-24 拍板）：這裡只把資料備好、
      // 不接消費端——「年齡→講話節奏預設」的三層 fallback 邏輯在 PR #243（engine/live_voice_server.py
      // _voice_rhythm_param，該 PR 尚未合併，伺服器目前也不解析這個參數）。未知 query 參數會被安全忽略，
      // 不影響現行通話；#243 合併後如需接線，於 live_voice_server.py 解析 `age` 餵進第①層 fallback。
      const _bym = String(_pp.birth || '').match(/(19|20)(\d{2})/);
      if (_bym) {
        const _age = new Date().getFullYear() - parseInt(_bym[0], 10);
        if (_age > 0 && _age < 130) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'age=' + encodeURIComponent(_age);
      }
    } catch (e) {}
    // 能力握手：告訴伺服器「這版 App 接得住 AI 幫你設提醒」→ 只有新版才拿到設提醒工具，舊版不會被假成功（2026-07-09 Edward）
    url += (url.indexOf('?') >= 0 ? '&' : '?') + 'cap_rem=1';
    // 能力握手：「接得住 AI 幫你記行程」（揪一攤）→ 約會/聚餐不再被硬塞成看診提醒（2026-07-16 Edward）
    url += '&cap_evt=1';
    // 能力握手：「接得住 AI 幫你記要問醫生的問題」（口袋問題）→ 舊版不會拿到工具（M1 PR-3）
    url += '&cap_ask=1';
    const _clientRelease = await clientReleaseInfo();
    url += '&app_version=' + encodeURIComponent(_clientRelease.version || '');
    url += '&app_build=' + encodeURIComponent(_clientRelease.build || '');
    url += '&client_protocol=' + encodeURIComponent(_clientRelease.protocol || 0);
    // 熟識度：帶上「聊過幾通」→ 越熟開場越簡短、像老朋友（Edward 2026-07-10「隨熟識度思考語句量」）
    try { url += '&fam=' + (parseInt(localStorage.getItem('munea.callCount') || '0', 10) || 0); } catch (e) {}
    // 當日開場路線：關係熟識度不能代替「今天已問過幾次」。同一通斷線重連沿用原路線，不誤算新通話。
    try {
      if (this._openingSessionId !== activeChatSessionId) {
        const now = new Date();
        const day = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
        let daily = {}; try { daily = JSON.parse(localStorage.getItem('munea.dailyCallOpening') || '{}') || {}; } catch (e2) {}
        this._openingSessionId = activeChatSessionId;
        this._openingDayKey = day;
        this._openingDayCall = daily.day === day ? Math.max(0, parseInt(daily.count || '0', 10) || 0) : 0;
        this._openingRecorded = false;
      }
      url += '&day_call=' + Math.max(0, this._openingDayCall || 0);
    } catch (e) {}
    // Production uses a short-lived token bound to this call's Voice+Avatar lease.
    const _callToken = CallControl.active && CallControl.active.call_token;
    url += (url.indexOf('?') >= 0 ? '&' : '?') + (_callToken
      ? ('token=' + encodeURIComponent(_callToken))
      : ('key=' + encodeURIComponent(MUNEA_APP_KEY)));
    voiceCallMark('voice_socket_connecting', 'pass', { endpoint: url, authMode: _callToken ? 'call_token' : 'app_key' });
    this.on = true;
    this.ready = false;   // 伺服器真的接上腦（Gemini session 開好）才會回 ready
    // 這裡是「連線剛建立、還沒接通」的初始值——此時本來就還不該送聲音。
    // 真正接通（markConnected）之後會立刻開麥，不再等她把招呼講完（2026-08-08）。
    this.micOpen = false; this._openMicAfterGreet = false;
    this._topicSaved = false; this._userBuf = '';   // 每通電話重新抓「你聊了什麼」
    this._transcript = []; this._userTurn = '';   // 每通電話重新累積聊天記錄（掛斷送去萃取長期記憶）
    this._playoutUntil = 0; this._newAvatarTurn = true; this._micPackets = 0; this._micRebuilds = 0; this._silentKeepaliveAt = 0;
    this._playbackTurn = 0; this._playbackUnderruns = 0; this._turnHasScheduledAudio = false;
    this._voiceTurnId = 0; this._localVoiceTurnId = 0; this._lastHumanVoiceAt = 0;
    this._slFallbackAfterTurn = ''; this._slSlowLeads = 0; this._slWouldFallbackSent = false;
    try { clearTimeout(this._slBoundaryFallbackT); } catch (e) {} this._slBoundaryFallbackT = null;
    this._firstAudioRecorded = false; this._firstMicPacketRecorded = false;
    this._serviceIdentity = null;
    this._firstUserCaptionRecorded = false; this._firstAssistantCaptionRecorded = false;
    this._userSpeechMs = 0; this._userSpeechQuietMs = 0; this._userSpeechPeak = 0; this._userSpeechLatched = false; this._pendingUserSpeech = null;
    clearTimeout(this._userSpeechWatchT); this._resetAssistantAudioGate();
    this._dropAssistantAudio = false; this._resetBargeInDetector();
    this.onListen = onListen; this.onSpeak = onSpeak; this.onDrop = onDrop; this.speaking = false; this._speakTimer = null;
    // iOS 只保證在使用者點下通話按鈕的同步呼叫鏈內允許啟動音訊。
    // 先建立並喚醒 AudioContext，也立刻要求麥克風；不要等 WebSocket onopen 才做。
    if (!this.prime()) { this.on = false; voiceCallFail('microphone_requested', this._micUnavailableReason || 'microphone_prime_failed'); return false; }
    const micPromise = this._primeMicPromise;
    // 收音管先建後招呼（蟲 b 根治）：管線跟 WebSocket 握手「並行」建，不再等 onopen 才動工。
    // 送音迴圈建好就開始跑（ws 還沒 open 時 _sendMicBuffer 自然丟包），open 那一刻立即有上行。
    const micPipelineReady = this._setupMicPipeline(micPromise);
    try { this.ws = new WebSocket(url); this.ws.binaryType = 'arraybuffer'; }
    catch (e) { this.on = false; voiceCallFail('voice_socket_construct', e, { endpoint: url }); return false; }
    return await new Promise(resolve => {
      let settled = false;
      const done = ok => { if (!settled) { settled = true; resolve(ok); } };
      this.ws.onopen = async () => {
        voiceCallMark('voice_socket_open', 'pass', { endpoint: url });
        this._sameLine = faceSameLineOn(); this._sameLineFellBack = false; this._sameLineWatchStarted = false;   // 同線收聲狀態每通重置
        this._faceDirect = false; this._faceDirectRequested = false; this._faceDirectSession = ''; this._faceDirectTurn = 0;
        this._sameLineWarmup = this._sameLine;
        if (this._sameLineWarmup) this._setFaceAudioMuted(true);
        this._requestFaceDirect();
        try { clearTimeout(this._sameLineWatch); } catch (e) {}
        const micSetup = await micPipelineReady;   // 管線多半早就建好了，這裡只是收結果
        if (!micSetup.ok) {
          voiceCallFail('microphone_ready', micSetup.error || 'microphone_unavailable');
          setLocalizedRuntimeHint('microphonePermission'); try { this.ws.close(); } catch (e) {} done(false); return;
        }
        this._resumeAudio();
        this._armUplinkWatch();                        // open 後 3 秒沒有第一包 → 自動重建收音管（最多 2 次）
        this._armDeadLineWatch('ready_timeout', 10000);   // open 後 10 秒連 ready 都沒到 → 死線重接
        if (this.onConnecting) this.onConnecting();   // 線接上了、腦還在開機 → 顯示「撥通中」載入動態
        done(true);
      };
      this.ws.onmessage = async ev => {
        if (typeof ev.data === 'string') {
          try {
            const o = JSON.parse(ev.data);
            if (o.type === 'service_identity') {
              this._serviceIdentity = o;
              voiceCallMark('voice_service_identity', 'pass', {
                version: o.version || '', commit: o.commit || '',
                callProtocol: Number(o.callProtocol) || 0,
                voiceProtocol: o.voiceProtocol || '',
              });
            }
            if (o.type === 'faceaudio_status') {
              const wasDirect = this._faceDirect === true;
              this._faceDirect = o.on === true;
              if (wasDirect && !this._faceDirect) this._newAvatarTurn = true;
              voiceCallMark('voice_face_direct_status', this._faceDirect ? 'pass' : 'fallback', {
                reason: o.reason || '', turn: Number(o.turn) || 0,
              });
              try { trackProductEvent('voice_face_direct_status', {
                result: this._faceDirect ? 'direct' : 'app_relay', reason: o.reason || '',
              }); } catch (e) {}
            }
            if (o.type === 'avatar_pcm_received') {
              Avatar._handlePcmAck(o, 'voice_direct_avatar_ack');
            }
            if (o.type === 'faceaudio_turn' && Number(o.turn) > 0) {
              this._faceDirectTurn = Number(o.turn);
              if (this._sameLine && this._faceDirect) Avatar.beginDirectTurn(this._faceDirectTurn);
            }
            if (o.type === 'interrupted' && this.playCtx) {
              this._dropAssistantAudio = true;
              this._stopAssistantPlayback();
            }
            if (o.type === 'barge_in_ack') {
              // Voice is the sole speaker arbiter. The App only ducks and sends
              // evidence; playback may stop only after this accepted verdict.
              const accepted = o.accepted !== false;
              this._bargeProposalPending = false;
              if (accepted) {
                this._bargeInActive = true;
                this._dropAssistantAudio = true;
                this._stopAssistantPlayback();
                if (this.onListen) this.onListen();
              } else {
                this._dropAssistantAudio = false;
                this._resetBargeInDetector();
              }
              try {
                trackProductEvent(o.accepted === false ? 'voice_barge_in_rejected' : 'voice_barge_in_accepted', {
                  reason: o.reason || null,
                  evidenceMs: Number(o.evidence_ms) || 0,
                  evidenceBasis: o.evidence_basis || '',
                });
              } catch (e) {}
              voiceCallMark('barge_in_server_ack', 'pass', {
                accepted: o.accepted !== false,
                reason: o.reason || '',
                evidenceMs: Number(o.evidence_ms) || 0,
                evidenceBasis: o.evidence_basis || '',
              });
              this._capBuf = '';
            }
            if (o.type === 'voice_turn_timing' && Number(o.turn) > 0) {
              const turn = Number(o.turn);
              this._voiceTurnId = turn;
              if (window.MuneaVoiceDiagnostics) {
                if (o.stage === 'vad_stop' && this._lastHumanVoiceAt) {
                  window.MuneaVoiceDiagnostics.markTurn(turn, 'last_human_voice', {
                    observedAt: this._lastHumanVoiceAt,
                    basis: 'client_mic_rms',
                  });
                }
                window.MuneaVoiceDiagnostics.markTurn(turn, o.stage, {
                  afterLastVoiceMs: o.afterLastVoiceMs !== null && o.afterLastVoiceMs !== undefined && Number.isFinite(Number(o.afterLastVoiceMs)) ? Number(o.afterLastVoiceMs) : null,
                  afterVadMs: o.afterVadMs !== null && o.afterVadMs !== undefined && Number.isFinite(Number(o.afterVadMs)) ? Number(o.afterVadMs) : null,
                  targetMs: o.targetMs !== null && o.targetMs !== undefined && Number.isFinite(Number(o.targetMs)) ? Number(o.targetMs) : null,
                  turnClass: o.class || '',
                  slowCaller: !!o.slowCaller,
                  basis: o.basis || 'voice_server_monotonic',
                });
              }
              voiceCallMark('voice_turn_' + o.stage, 'pass', { turn, targetMs: Number(o.targetMs) || 0 });
            }
            if (o.type === 'caption' && o.who === 'nening' && o.text && !this._dropAssistantAudio) {   // 寧寧說的話→字幕逐字（累積成一句）
              if (!this._firstAssistantCaptionRecorded) { this._firstAssistantCaptionRecorded = true; voiceCallMark('assistant_first_caption', 'pass'); }
              this._capBuf = (this._capBuf || '') + o.text;
              if (this.onCaption) this.onCaption(this._capBuf);
            }
            if (o.type === 'ready') {
              const expectedCall = Number((window.MuneaVersion && window.MuneaVersion.callProtocol) || 0);
              const expectedVoice = String((window.MuneaVersion && window.MuneaVersion.voiceProtocol) || '');
              const identity = this._serviceIdentity || {};
              if ((expectedCall && Number(identity.callProtocol || 0) !== expectedCall)
                  || (expectedVoice && String(identity.voiceProtocol || '') !== expectedVoice)) {
                voiceCallFail('voice_protocol_mismatch', 'incompatible_voice_service', {
                  expectedCall, actualCall: Number(identity.callProtocol || 0),
                  expectedVoice, actualVoice: String(identity.voiceProtocol || ''),
                });
                setLocalizedRuntimeHint('reconnecting', true);
                try { this.ws.close(4412, 'incompatible voice protocol'); } catch (e) {}
                return;
              }
              this.ready = true; voiceCallMark('voice_ready', 'pass');
              this._armDeadLineWatch('no_audio_both_ways', 5000);
              // 2026-08-08 Edward：「有一通可以講，但撥通後就又都不能講了」。
              // 開麥本來掛在接通那條路的尾巴（markConnected 之後），但那條路上有兩道
              // 「狀態變了就直接離開」的檢查——一旦命中就整段跳過，麥克風永遠關著。
              // 間歇性正是這樣來的：同一份程式，有時走到、有時沒走到。
              // 改成掛在這裡：腦一接上就開麥。這是「能收音」的最早時機，
              // 而且它在 ready 事件本身，沒有任何提早離開的分支繞得過去。
              this._setMicOpen(true); this._openMicAfterGreet = false;
              if (this.onReady) this.onReady(); this._toListening();
              try { localStorage.setItem('munea.lastChatAt', String(Date.now())); } catch (e2) {}
            }   // 腦開機完成 → 語音就緒＋立刻開麥；記下「聊過了」；ready 後 5 秒雙向無聲＝死線重接
            if (o.type === 'caption' && o.who === 'user' && o.text) {
              this._ackUserSpeech();
              if (!this._firstUserCaptionRecorded) { this._firstUserCaptionRecorded = true; voiceCallMark('asr_first_caption', 'pass'); }
              this._userTurn = (this._userTurn || '') + o.text;   // 累積「這輪你說的話」→ 掛斷時送去萃取長期記憶（讓聊聊講的也記得住 · Edward 2026-07-10）
              if (!this._topicSaved) {
                // 首頁「記得你說…」的在地記憶：抓這通電話你說的第一句話
                this._userBuf = (this._userBuf || '') + o.text;
                // 只存「乾淨、像一句話」的內容當首頁話題，擋語音辨識亂碼／英數雜訊（Edward 2026-07-12）
                const clean = this._userBuf.replace(/\s+/g, '');
                const cjk = (clean.match(/[一-龥]/g) || []).length;
                const looksClean = clean.length >= 5 && clean.length <= 16 && muneaIsCleanSpeechText(clean);   // 改用共用嚴格守門：出現任一日文/韓文/俄文字元就擋（Edward 2026-07-14 事故：「アラ」混在中文裡、比例式守門放行）
                if (looksClean) { try { localStorage.setItem('munea.lastTopic', clean.slice(0, 16)); } catch (e3) {} this._topicSaved = true; }
                else if (clean.length >= 24) { this._topicSaved = true; }   // 累積夠長仍不乾淨＝這通沒有適合話題、別硬塞亂碼
              }
            }
            if (o.type === 'turn_complete') {
              const interruptedTurn = !!this._dropAssistantAudio;
              this._dropAssistantAudio = false;
              this._resetBargeInDetector();
              // 把這一輪（你說的＋她回的）存進聊天記錄 → 掛斷時送去萃取長期記憶
              try { if (!interruptedTurn) {
                if (!this._transcript) this._transcript = [];
                const ut = (this._userTurn || '').trim(), nt = (this._capBuf || '').trim();
                if (ut) this._transcript.push({ role: 'user', text: ut });
                if (nt) this._transcript.push({ role: 'assistant', text: nt });
                this._userTurn = '';
              } } catch (eT) {}
              if (interruptedTurn) Avatar.reset();
              else if (!this._faceDirect) Avatar.finish(); // direct route 由 Voice 在最後 PCM 後送 finish，避免跨 WS 亂序
              if (!interruptedTurn && this._slFallbackAfterTurn) this._scheduleSameLineBoundaryFallback();
              this._newAvatarTurn = true;
              this._resetAssistantAudioGate();
              this._toListening(); this._capBuf = '';
            }   // 她講完 → 換你講、麥克風重開、字幕緩衝清空
            if (o.type === 'relay_spoken' && o.id) { this._relaySpokenId = o.id; rememberSpokenFamilyRelay(this._pendingRelay); }
            if (o.type === 'relay_interrupted' && o.id && this._pendingRelay && o.id === this._pendingRelay.id) this._finishRelay('release');
            if (o.type === 'relay_rejected' && o.id && this._pendingRelay && o.id === this._pendingRelay.id) this._finishRelay('release');
            if (o.type === 'action' && o.action) {   // AI 要「幫你做進 App」（設看診/用藥提醒）→ 執行
              let result = { ok: false, error: 'app_action_unavailable' };
              try {
                if (window.__muneaHandleVoiceAction) result = await window.__muneaHandleVoiceAction(o.action, o.args || {});
              } catch (eAct) { result = { ok: false, error: String(eAct && eAct.message || 'app_action_failed') }; }
              try {
                if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify({
                  type: 'action_result', id: o.id, action: o.action, ok: !!(result && result.ok),
                  result: result && result.ok ? result : undefined,
                  error: result && !result.ok ? (result.error || 'app_action_failed') : undefined,
                }));
              } catch (eAck) {}
            }
          } catch (e) {}
          return;
        }
        if (!this.playCtx) return;
        if (this._dropAssistantAudio) return;
        const audioData = this._takeAssistantAudio(ev.data);
        if (!audioData) return;
        if (!this._firstAudioRecorded) {
          this._firstAudioRecorded = true;
          voiceCallMark('voice_first_audio', 'pass', { bytes: audioData.byteLength });
        }
        if (this._newAvatarTurn) {
          if (this._slFallbackAfterTurn && this._sameLineFellBack !== true) {
            this._sameLineFallBackNow(this._slFallbackAfterTurn);
          }
          const timingTurn = (this._sameLine && this._faceDirect && this._faceDirectTurn) ||
            this._voiceTurnId || ((this._localVoiceTurnId || 0) + 1);
          this._localVoiceTurnId = timingTurn;
          if (this._sameLine && this._faceDirect) Avatar.beginDirectTurn(timingTurn);
          else Avatar.beginTurn(timingTurn);       // App relay 才由手機清上一輪；direct route 由 Voice 排序 reset→PCM
          this._slFaceStarted = false; this._slTurnStartAt = 0; this._slPrevBytes = -1; this._slStallStreak = 0;
          if (this._sameLine && !this._sameLineWarmup && this._sameLineFellBack !== true) this._setFaceAudioMuted(false);
          if (this._openMicAfterGreet) { this._setMicOpen(true); this._openMicAfterGreet = false; }
          this._newAvatarTurn = false;
          this._playoutUntil = 0;
          this._playbackTurn = (this._playbackTurn || 0) + 1;
          this._playbackUnderruns = 0;
          this._turnHasScheduledAudio = false;
        }
        this._notePlayout(audioData.byteLength);     // Gemini 會快轉送完資料；用「音訊實際長度」算何時真的播完
        if (this._sameLineWarmup) this._setFaceAudioMuted(true);
        if (!(this._sameLine && this._faceDirect)) Avatar.feed(audioData); // direct route 不再繞手機二次上行
        this._toSpeaking();                                        // 收到她的聲音 → 進入「她在說」
        const i16 = new Int16Array(audioData), f = new Float32Array(i16.length);
        for (let k = 0; k < i16.length; k++) f[k] = i16[k] / 0x8000;
        let ps = 0; for (let k = 0; k < f.length; k++) ps += f[k] * f[k];
        this.playLevel = Math.min(1, Math.sqrt(ps / f.length) * 3.4);   // 即時音量→講話波頻高度
        // 同線模式：聲音只從 faceVid（臉那條線）出，faceAud 只量測、永久靜音。
        // 保底：頭一段講話若 3 秒內完全沒收到同線音軌 → 之後這通改回本地播放。
        if (this._sameLine && !this._sameLineWarmup && this._sameLineFellBack !== true) {
          if (!this._sameLineWatchStarted) {
            this._sameLineWatchStarted = true;
            try { Avatar._faceAudMaxLevel = 0; } catch (e) {}
            this._sameLineWatch = setTimeout(async () => {
              let mx = 0; try { mx = Avatar._faceAudMaxLevel || 0; } catch (e) {}
              // iPhone 上 Web Audio 讀遠端串流會恆為 0（Safari 已知坑）→ 不能只信量表 mx。
              // 第二證人：連線「真的有沒有收到聲音位元組」（getStats，iPhone 讀得到）——有流量＝同線活著、別退回。
              let bytes = 0, alevel = -1, hasStats = false;
              try {
                const rcv = Avatar._faceAudReceiver;
                if (rcv && rcv.getStats) {
                  const st = await rcv.getStats();
                  st.forEach(r => { if (r.type === 'inbound-rtp' && (r.kind === 'audio' || r.mediaType === 'audio')) { hasStats = true; if (typeof r.bytesReceived === 'number') bytes = r.bytesReceived; if (typeof r.audioLevel === 'number') alevel = r.audioLevel; } });
                }
              } catch (e) {}
              const streamAlive = (bytes > 3000) || (alevel > 0.001);   // 連線收到夠多聲音位元組＝真的有聲在傳
              try { Avatar._diagNote('3秒查:量表=' + mx.toFixed(3) + ' 流量=' + bytes + 'B 音量=' + (alevel < 0 ? '無' : alevel.toFixed(3)) + (hasStats ? '' : '(無stats)')); } catch (e) {}
              try { trackProductEvent('sameline_check', { result: (mx < 0.015 && !streamAlive) ? 'fellback' : 'kept', mx: +(mx || 0).toFixed(3), bytes: bytes, audioLevel: alevel, hasStats: hasStats, trail: (Avatar._diagTrail || []).join(' | ') }); } catch (e) {}   // 回報後台=不用靠截圖也拿得到真機診斷（Codex 2026-07-12 建議）
              if (mx < 0.015 && !streamAlive) {
                this._sameLineFellBack = true;
                // 關鍵：退回本地播放的同時「把同線那軌靜音」——不然引擎晚點醒過來、兩邊一起出聲＝回答重疊（Edward 2026-07-11 真機抓到）
                try { const _fa = document.getElementById('faceAud'); if (_fa) _fa.muted = true; } catch (e) {}
                try { const _fv = document.getElementById('faceVid'); if (_fv) _fv.muted = true; } catch (e) {}   // 聲音改走影像播放器後（1.24.4）：退回時它也要閉嘴、同理防重疊
                try { Avatar._diagNote(muneaT('avatar.forceNoSoundFallback', '判定真沒聲→退回本地(會慢)'), true); } catch (e) {}
                try { localStorage.setItem('munea.sameLineFellBack', String(Date.now())); } catch (e) {}
              } else {
                try { Avatar._diagNote(muneaT('avatar.forceSameLineAlive', '同線活著→維持不退回') + (mx < 0.015 ? muneaT('avatar.forceIphoneWorkaround', '(繞過iPhone坑)') : ''), mx < 0.015); } catch (e) {}
              }
            }, 3000);
          }
          this._armSameLineStutterWatch();   // 中途斷續監測（2026-07-29）：開頭 3 秒查只擋「死掉」，這支擋「斷續」
          this._toListening();                                    // 依實際應播完時間換手，不再用「資料停止到貨」誤判句尾
          return;                                                  // 不本地排程（聲音由 faceAud 出）
        }
        this._scheduleLocalPlayback(f);                            // 本地備援同樣等排程音訊真的播完才開麥
      };
      this.ws.onclose = event => {
        const wasOpen = this.on;
        if (wasOpen) voiceCallFail('voice_socket_closed', 'ws_' + (event.code || 0), { closeCode: event.code || 0, closeReason: event.reason || '', wasClean: !!event.wasClean });
        done(false); this.stop(); if (wasOpen && onDrop) onDrop();
      };
      this.ws.onerror = () => { voiceCallFail('voice_socket_error', 'websocket_error', { endpoint: url }); done(false); };
    });
  },
  stop() {
    if (this._pendingRelay) this._finishRelay(this._relaySpokenId ? 'ack' : 'release');
    this.on = false;
    this.ready = false;
    clearTimeout(this._speakTimer); clearTimeout(this._micWatchT); clearTimeout(this._userSpeechWatchT); this._playoutUntil = 0; this._newAvatarTurn = true;
    clearTimeout(this._uplinkWatchT); clearTimeout(this._deadLineWatchT);   // 收音管看門＋死線看門一起收
    this.micOpen = false; this._openMicAfterGreet = false;
    try { clearTimeout(this._duckConfirmT); } catch (e) {}
    this._duckPendingAt = 0;
    this._sameLineWarmup = false;
    this._faceDirect = false; this._faceDirectRequested = false; this._faceDirectSession = ''; this._faceDirectTurn = 0;
    this._pendingUserSpeech = null; this._resetAssistantAudioGate();
    this._dropAssistantAudio = false; this._resetBargeInDetector();
    try { clearTimeout(this._sameLineWatch); } catch (e) {} this._sameLineWatchStarted = false;   // 同線保底計時器一起收
    try { clearInterval(this._slStutterT); } catch (e) {} this._slStutterT = null;   // 中途斷續監測一起收（2026-07-29）
    try { clearTimeout(this._slBoundaryFallbackT); } catch (e) {} this._slBoundaryFallbackT = null; this._slFallbackAfterTurn = '';
    try { Avatar.stop(); } catch (e) {}   // 掛斷＝臉一起收（所有掛斷路徑都走這裡）
    try { const c = document.getElementById('chat'); if (c && c.dataset.state === 'connecting') c.dataset.state = 'idle'; } catch (e) {}
    try { if (this.proc) this.proc.disconnect(); } catch (e) {}
    try { if (this._micSrc) this._micSrc.disconnect(); } catch (e) {}
    try { if (this.mic) this.mic.getTracks().forEach(t => t.stop()); } catch (e) {}
    const pendingMic = this._primeMicPromise; this._primeMicPromise = null;
    if (pendingMic) pendingMic.then(r => { try { if (r && r.stream) r.stream.getTracks().forEach(t => t.stop()); } catch (e) {} });
    try { if (this.ws) this.ws.close(); } catch (e) {}
    try { if (this.ac) this.ac.close(); } catch (e) {}
    try { if (this.playCtx) this.playCtx.close(); } catch (e) {}
    try { if (window.MuneaAvSyncMeter) MuneaAvSyncMeter.stop(); } catch (e) {}   // 延遲量測器一起收
    this._avAnalyser = null;                                                      // playCtx 關了→分析器作廢，下通重建
    this._playGain = null;
    this.ws = this.ac = this.mic = this.proc = this._micSrc = this.playCtx = null;
  },
};
window.MuneaLiveVoice = LiveVoice;

// ── 聲↔臉 延遲量測器（Edward 2026-07-10：肉眼抓延遲太累、改用機器量）─────────────────
// 原理：同一個時鐘下，同時盯「播出去的聲音何時起」＋「臉的嘴巴那塊畫面何時開始動」，
// 兩個「開始」時間相減＝這句話的延遲秒數。左下角小字直接顯示（近幾句平均＋建議補償值）。
// 進階：munea.avSyncAuto=1 時，量到多少就自動把「聲音等臉」的時間補到剛好對齊（代價：她回話會慢一點）。
// 2026-07-11 施工圖②降級為隱藏除錯工具：munea.debug=1 才啟動，預設完全不跑（不建 canvas、不取像素、不顯示浮層）——
// 預設開著時它每幀取像素白燒長輩舊 iPhone CPU、螢光浮層又像 bug（Edward 抱怨的閃爍元凶）。
const AvSyncMeter = {
  on: false, _raf: 0, _video: null, _canvas: null, _ctx: null, _prev: null, _overlay: null,
  _audioHot: false, _videoHot: false, _pendA: false, _tA: 0, _samples: [], _lastTune: 0,
  start(videoEl) {
    if (this.on) return;
    try {
      if (localStorage.getItem('munea.debug') !== '1') return;   // debug-only：munea.debug=1 才啟動；預設不建 canvas、不取像素、不顯示浮層（2026-07-11 ②）
      this._video = videoEl || document.getElementById('faceVid');
      this._canvas = document.createElement('canvas'); this._canvas.width = 48; this._canvas.height = 48;
      this._ctx = this._canvas.getContext('2d', { willReadFrequently: true });
      this._overlay = document.createElement('div');
      this._overlay.style.cssText = 'position:fixed;left:10px;bottom:12px;z-index:99999;background:rgba(12,14,20,.78);color:#fff;font:600 12px/1.5 -apple-system,system-ui,sans-serif;padding:7px 10px;border-radius:10px;pointer-events:none;white-space:pre;letter-spacing:.2px;';
      this._overlay.textContent = '延遲量測：聽聲音、看嘴巴中…';
      document.body.appendChild(this._overlay);
      this._samples = []; this._prev = null; this._audioHot = this._videoHot = this._pendA = false;
      this.on = true; this._loop();
    } catch (e) {}
  },
  _ensureAnalyser() {
    if (LiveVoice._avAnalyser || !LiveVoice.playCtx) return LiveVoice._avAnalyser || null;
    try {
      const a = LiveVoice.playCtx.createAnalyser(); a.fftSize = 512; a.smoothingTimeConstant = 0.2;
      a.connect(LiveVoice.playCtx.destination); LiveVoice._avAnalyser = a;   // 之後的每段聲音都會串過它（透明、不改音）
    } catch (e) {}
    return LiveVoice._avAnalyser || null;
  },
  _audioRms() {
    const a = this._ensureAnalyser(); if (!a) return 0;
    const buf = new Uint8Array(a.fftSize); a.getByteTimeDomainData(buf);
    let s = 0; for (let i = 0; i < buf.length; i += 2) { const v = (buf[i] - 128) / 128; s += v * v; }
    return Math.sqrt(s / (buf.length / 2));   // 0~1 播出去的聲音能量
  },
  _mouthMotion() {
    const v = this._video; if (!v || !v.videoWidth) return 0;
    try {
      const sw = v.videoWidth, sh = v.videoHeight;
      this._ctx.drawImage(v, sw * 0.30, sh * 0.33, sw * 0.40, sh * 0.17, 0, 0, 48, 48);   // 嘴巴區＝高度33-50%（7/10 錄影逐格驗證：55%以下是胸口、之前盯錯位置才一直不出數字）
      const cur = this._ctx.getImageData(0, 0, 48, 48).data; let m = 0, n = 0;
      if (this._prev) { for (let i = 0; i < cur.length; i += 8) { m += Math.abs(cur[i] - this._prev[i]); n++; } }
      this._prev = cur;
      return n ? (m / n / 255) : 0;   // 0~1 嘴巴那塊畫面的變化量
    } catch (e) { return 0; }
  },
  _loop() {
    if (!this.on) return;
    const now = performance.now();
    const ar = this._audioRms(), mm = this._mouthMotion();
    if (ar > 0.045 && !this._audioHot) { this._audioHot = true; this._tA = now; this._pendA = true; }   // 聲音：靜→起
    else if (ar < 0.02) this._audioHot = false;
    if (mm > 0.028 && !this._videoHot) {                                                                  // 嘴巴：靜→動
      this._videoHot = true;
      if (this._pendA) {
        const d = (now - this._tA) / 1000;
        if (d > 0.05 && d < 5.5) { this._samples.push(d); if (this._samples.length > 6) this._samples.shift(); this._pendA = false; this._render(); this._maybeTune(); }
      }
    } else if (mm < 0.014) this._videoHot = false;
    this._raf = requestAnimationFrame(() => this._loop());
  },
  _avg() { const n = this._samples.length; return n ? this._samples.reduce((a, b) => a + b, 0) / n : 0; },
  _render() {
    if (!this._overlay) return;
    const n = this._samples.length, last = n ? this._samples[n - 1] : 0, avg = this._avg();
    const curW = parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
    const suggest = Math.max(0, Math.min(2800, Math.round(curW + avg * 1000)));   // 想對齊該把「聲音等臉」設多少
    const auto = ((localStorage.getItem('munea.avSyncAuto') || '1') === '1') ? '（自動補償中）' : '';   // 7/11 起預設開：量到差多少就自動補多少
    this._overlay.textContent = `臉比聲音慢 ${last.toFixed(1)}s（這句）\n近 ${n} 句平均 ${avg.toFixed(1)}s${auto}\n對齊建議：聲音等臉 ${suggest}ms`;
  },
  _maybeTune() {
    // 舊水管拆除（1.24.6）：新引擎＝臉聲同線原生對齊、退回也用寫死小等待——校時器只准看、不准動手
    //（它是舊雙管世界的拐杖，在新世界會把聲音越推越後＝嘴先動的機制源；量測顯示照舊、供機器人成績單用）
    try { if (typeof faceEngine === 'function' && faceEngine() === 'flashhead') return; } catch (e) {}
    if ((localStorage.getItem('munea.avSyncAuto') || '1') !== '1') return;   // 7/11 起預設開（Edward 拍板對齊為正解）；munea.avSyncAuto=0 可關
    if (this._samples.length < 3) return;
    const now = performance.now(); if (now - this._lastTune < 4000) return;   // 每 4 秒最多調一次、給它時間穩
    const sorted = this._samples.slice().sort((a, b) => a - b), med = sorted[Math.floor(sorted.length / 2)];
    const curW = parseInt(localStorage.getItem('munea.faceSyncMs') || '900', 10);
    const newW = Math.max(0, Math.min(2800, Math.round(curW + med * 1000)));   // D=臉lag−等待 → 等待+=D 一步對齊
    if (Math.abs(newW - curW) > 120) {
      try { localStorage.setItem('munea.faceSyncMs', String(newW)); } catch (e) {}
      this._lastTune = now; this._samples = [];   // 換了等待時間 → 清掉重量、看新的對齊結果
    }
  },
  stop() {
    this.on = false; if (this._raf) cancelAnimationFrame(this._raf);
    if (this._overlay) { try { this._overlay.remove(); } catch (e) {} this._overlay = null; }
    this._prev = null; this._samples = [];
  },
};
window.MuneaAvSyncMeter = AvSyncMeter;

/* 收音波紋（2026-08-10 改版「點線」· Edward 從三款提案挑的 C）
   一次改三件他點名的事：
   ① 一接通就看得見——撥通中就開始畫，沒收到聲音時是一排安靜的小點（「線通了、在等你說」），
      不再是接通後畫面空一塊、直到有人開口才憑空冒出東西。
   ② 只有長輩講話才會動——寧寧出聲時波紋一律歸零。她講話已經有嘴形＋聲音，
      波紋再跳一次是重複；而且擴音的回音本來就會漏進麥克風，不擋就會變成「她在收自己的音」。
   ③ 畫法改成細長條配一排小點（顆粒感），比舊的九根細棍看得清楚。
   顏色只用品牌薄荷綠：橘色畫在暖膚色的立繪上會糊掉（8/10 三款提案實測截圖）。 */
const FaceWave = {
  canvas: null, ctx: null, raf: 0, cur: 0, w: 0, h: 0, dpr: 0, _tick: 0,
  // 靜音門檻（2026-08-01）：安靜房間的底噪經過 micLevel 放大約落在 0.05-0.1，
  // 低於這條線一律當作沒聲音＝波紋躺平不抖。調高＝更安靜但小聲說話會慢半拍才起波。
  QUIET_FLOOR: 0.12,
  // 波紋該跳多高：她在出聲就一律 0；否則看麥克風、扣掉底噪門檻。
  // 拆成純函式方便驗（吃兩個數字、吐一個數字，不碰畫面）。
  gate(micLevel, herVoiceOn) {
    if (herVoiceOn) return 0;
    const v = Math.max(0, Math.min(1, Number(micLevel) || 0));
    return v < FaceWave.QUIET_FLOOR ? 0 : (v - FaceWave.QUIET_FLOOR) / (1 - FaceWave.QUIET_FLOOR);
  },
  level() {
    let her = false;
    try { her = typeof speechActive === 'function' && speechActive(); } catch (e) {}
    const mic = (typeof LiveVoice !== 'undefined' && LiveVoice.micLevel) || 0;
    return this.gate(mic, her);
  },
  _measure() {
    const c = this.canvas; if (!c) return false;
    const w = c.clientWidth, h = c.clientHeight;
    if (!w || !h) return false;                              // 還被藏著（display:none）→ 這格先不畫
    const d = Math.min(window.devicePixelRatio || 1, 2.5);
    if (w !== this.w || h !== this.h || d !== this.dpr) {
      this.w = w; this.h = h; this.dpr = d;
      c.width = Math.round(w * d); c.height = Math.round(h * d);
      this.ctx.setTransform(d, 0, 0, d, 0, 0);
    }
    return true;
  },
  // 中間厚、兩側收到 0：波紋不會在畫面邊緣硬切一刀
  _env(u) { return Math.pow(Math.sin(Math.PI * u), 1.4); },
  _paint(t) {
    const x = this.ctx, w = this.w, h = this.h, mid = h / 2, cur = this.cur;
    x.clearRect(0, 0, w, h);
    const g = x.createLinearGradient(0, 0, w, 0);
    const a = 0.82 + 0.18 * cur;
    g.addColorStop(0, 'rgba(62,212,194,0)');
    g.addColorStop(0.16, 'rgba(62,212,194,' + a + ')');
    g.addColorStop(0.5, 'rgba(22,196,174,1)');
    g.addColorStop(0.84, 'rgba(62,212,194,' + a + ')');
    g.addColorStop(1, 'rgba(62,212,194,0)');
    // 全部形狀畫成同一條路徑、只填一次：陰影只算一遍（一格算 78 次陰影在舊手機上會掉格）
    x.beginPath();
    const n = Math.max(8, Math.floor(w / 6));
    for (let i = 0; i < n; i++) {
      const u = (i + 0.5) / n, px = u * w, env = this._env(u);
      const wob = Math.sin(u * 14 + t * 2.2) * 0.5 + 0.5;
      const barH = 3 + env * (h * 0.46) * cur * (0.45 + wob * 0.55);
      this._cap(x, px - 1.4, mid - barH / 2, 2.8, barH);
      // 點狀疊層：安靜時它跟細條疊在一起＝一排小點；有聲音就跑到柱子外面，變成一條游動的散點
      // （0.40 是實測挑的：再小點會被柱子蓋住、看不出「點線」的個性）
      const dotY = mid + Math.sin(u * 9 - t * 1.6) * env * (h * 0.40) * cur;
      x.moveTo(px + 1.5, dotY);
      x.arc(px, dotY, 1.5, 0, Math.PI * 2);
    }
    // 貼著形狀的一圈暗影：壓在暖膚色立繪上也讀得出來，又不會在臉上留一塊灰霧
    x.shadowColor = 'rgba(4,14,12,.55)'; x.shadowBlur = 5; x.shadowOffsetY = 1;
    x.fillStyle = g; x.fill();
    x.shadowColor = 'transparent'; x.shadowBlur = 0; x.shadowOffsetY = 0;
  },
  // roundRect 在舊 iOS Safari 沒有 → 沒有就退成方角，不讓整條波紋消失
  _cap(x, left, top, w, h) {
    const r = Math.min(1.4, h / 2);
    if (typeof x.roundRect === 'function') { x.roundRect(left, top, w, h, r); return; }
    x.rect(left, top, w, h);
  },
  // 撥通中就叫：先畫靜止狀態，音量自己會來
  start() {
    if (!this.canvas) {
      this.canvas = document.getElementById('faceWaveCanvas');
      if (!this.canvas) return;
      this.ctx = this.canvas.getContext('2d');
    }
    if (this.raf) return;
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      // 尺寸每 30 格才量一次：量尺寸會逼瀏覽器重算版面，通話中每格都量太貴
      if ((this._tick++ % 30) === 0 || !this.w) { if (!this._measure()) return; }
      this.cur += (this.level() - this.cur) * 0.35;          // 平滑起落，不抖
      if (this.cur < 0.004) this.cur = 0;                    // 收乾淨＝真的靜止，不留看不出來的殘抖
      this._paint(performance.now() / 1000);
    };
    this.raf = requestAnimationFrame(loop);
  },
  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0; this.cur = 0;
    if (this.ctx && this.w) { try { this._paint(0); } catch (e) {} }   // 留一排靜止小點，不留半截波形
  },
};
window.MuneaFaceWave = FaceWave;

// 進聊聊頁：她像朋友一樣「主動先開口」（帶記憶＋今日狀態）
let callConnected = false;
let callDialing = false;
let callPreflightPending = false;
function setCallPreflightPending(on, pendingLabel = muneaT('voice.connecting', '')) {
  callPreflightPending = on;
  if (!on) hideBusyCard();   // 排隊卡跟著撥號前置狀態走：接通／取消／失敗任何一條路離開排隊就收卡
  // 2026-08-01：撥號前置一結束、又沒真的撥起來（失敗／取消／被擋），把提早切過去的
  // 「撥通中」畫面收回待機——配合 connectCall 開頭「先切畫面再跑網路」那一刀。
  if (!on && !callDialing && !callConnected) {
    try {
      const _c = document.getElementById('chat');
      if (_c && _c.dataset.state === 'connecting') _c.dataset.state = 'idle';
    } catch (e) {}
  }
  const b = $('#callToggle'); if (!b) return;
  b.setAttribute('aria-busy', on ? 'true' : 'false');
  const lbl = $('#callToggleLabel');
  if (lbl && on) lbl.textContent = pendingLabel;
  else if (lbl && !callDialing) lbl.textContent = callConnected
    ? muneaT('voice.call.end', '')
    : muneaT('voice.call.start', '');
}
// 撥通中狀態：按鈕顯示「撥通中···」循環；真的接通（她開始聽/說）才變「結束通話」＋開始計時（Edward 7/9）
function setCallDialing(on) {
  if (on) setCallPreflightPending(false);
  callDialing = on;
  const b = $('#callToggle'); if (!b) return;
  b.classList.toggle('dialing', on);
  const lbl = $('#callToggleLabel');
  if (lbl) {
    if (on) {
      lbl.textContent = muneaT('voice.call.dialing', '');
      const dots = document.createElement('span');
      dots.className = 'dial-dots';
      dots.innerHTML = '<i>·</i><i>·</i><i>·</i>';
      lbl.appendChild(dots);
    } else {
      lbl.textContent = callConnected
        ? muneaT('voice.call.end', '')
        : muneaT('voice.call.start', '');
    }
  }
}
function setCallToggle(connected) {
  callConnected = connected;
  callDialing = false;
  setCallPreflightPending(false);
  const _b0 = $('#callToggle'); if (_b0) _b0.classList.remove('dialing');
  // 在線狀態：撥通前「未在線」（灰點）、撥通後「在線」（綠點呼吸）
  const fn = document.querySelector('.face-name');
  if (fn) {
    fn.classList.toggle('off', !connected);
    const st = fn.querySelector('.fn-status');
    if (st) st.textContent = connected
      ? muneaT('voice.call.online', '')
      : muneaT('voice.call.offline', '');
  }
  const b = $('#callToggle');
  if (!b) return;
  b.classList.toggle('start', !connected);
  b.classList.toggle('end', connected);
  const pts = document.querySelector('.hud-pill.pts');
  if (pts) pts.style.display = (connected || ptsPillHidden()) ? 'none' : '';   // 通話中讓畫面乾淨；免費 0 點不掛牌
  const lbl = $('#callToggleLabel');
  if (lbl) lbl.textContent = connected
    ? muneaT('voice.call.end', '')
    : muneaT('voice.call.start', '');
}

// ===== 待機動態（Edward 7/9 供片）：進聊聊頁播「打招呼」一次 → 「待機」循環；按通話即停回靜態，交給語音＋雲端臉 =====
const FACE_MOTION = {
  'nening-real-female': { hello: 'avatars/motion/nening-hello.mp4', idles: ['avatars/motion/nening-idle.mp4'] },
  // 擬真男重新掛回（2026-07-11 Edward 給新影片、新長相）：撥號前用「打招呼→待機」影片、引擎已做交叉淡入不黑閃
  'companion-real-male': { hello: 'avatars/motion/ahong-hello.mp4', idles: ['avatars/motion/ahong-idle.mp4'] },
  'munea-2d-xiaoyun': { hello: 'avatars/motion/xiaoyun-hello.mp4', idles: ['avatars/motion/xiaoyun-idle.mp4'] },
  'munea-2d-ayuan': { hello: 'avatars/motion/ayuan-hello.mp4', idles: ['avatars/motion/ayuan-idle.mp4'] },
  'munea-2d-mimi': { hello: 'avatars/motion/mimi-hello.mp4', idles: ['avatars/motion/mimi-idle.mp4', 'avatars/motion/mimi-idle2.mp4'] },   // 咪咪有兩段待機（含舔鼻子）輪著播
  'munea-2d-wangcai': { hello: 'avatars/motion/wangcai-hello.mp4', idles: ['avatars/motion/wangcai-idle.mp4'] },
};
function currentFaceTemplate() {
  try {
    const P = window.MuneaCompanionProfile;
    const raw = (typeof currentAvatarId !== 'undefined' && currentAvatarId)
      ? currentAvatarId
      : (((P && P.loadProfile ? P.loadProfile() : null) || {}).templateId || '');
    return P && P.normalizeTemplateId ? P.normalizeTemplateId(raw) : (raw || 'nening-real-female');
  } catch (e) { return 'nening-real-female'; }
}
const FaceIdle = {
  // 輪播引擎：打招呼一次 → 多段待機輪流（咪咪有兩段）。兩支播放器輪班：下一段永遠先在底下備好、
  // 真的出畫面才交叉淡入，上一段停在最後一格墊著——任何換片點都沒有黑格、不閃頻（Edward 7/9）
  vA: null, vB: null, active: false, _gen: 0, _front: null, _back: null, _idles: null, _nextIdx: 0,
  _mk(suffix) {
    const img = document.getElementById('faceImg');
    if (!img || !img.parentElement) return null;
    const v = document.createElement('video');
    v.id = 'faceIdle' + suffix; v.muted = true; v.playsInline = true; v.setAttribute('playsinline', ''); v.preload = 'auto';
    v.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .28s ease;pointer-events:none';
    img.insertAdjacentElement('afterend', v);   // 蓋在靜態照上、壓在雲端臉(faceVid)下
    v.onended = () => { if (FaceIdle.active && v === FaceIdle._front) FaceIdle._swap(); };
    return v;
  },
  ensure() {
    if (!this.vA) this.vA = this._mk('A');
    if (!this.vB) this.vB = this._mk('B');
    return this.vA && this.vB;
  },
  _preloadNext() {
    if (!this._idles || !this._idles.length) return;   // 只有打招呼片：播完停在最後一格
    // 把下一段待機片裝進待命的那支播放器（單段角色＝同一支片重複裝、換片點一樣淡接）
    const src = this._idles[this._nextIdx % this._idles.length];
    this._back.loop = false; this._back.style.opacity = '0'; this._back.src = src;
    try { this._back.load(); } catch (e) {}
  },
  _swap() {
    const gen = this._gen;
    const front = this._front, back = this._back;
    const cross = () => {
      if (gen !== this._gen) return;
      back.style.opacity = '1';                                                          // 新片淡入（舊片停最後一格墊著）
      setTimeout(() => { if (gen === this._gen) front.style.opacity = '0'; }, 200);      // 疊 0.2 秒再讓舊片淡出
      this._front = back; this._back = front;
      this._nextIdx++;
      setTimeout(() => { if (gen === this._gen) this._preloadNext(); }, 650);            // 等淡出完全結束才裝下一段（裝片會重置畫面、不能在交疊中做）
    };
    back.play().then(() => requestAnimationFrame(() => requestAnimationFrame(cross))).catch(cross);
  },
  start(tplId) {
    const m = FACE_MOTION[tplId || currentFaceTemplate()];
    if (!this.ensure()) return;
    if (!m) { this.stop(); return; }             // 沒動態素材的角色維持靜態圖
    const gen = ++this._gen;                     // 換角色/重進頁時作廢舊流程
    this.active = true;
    this._idles = m.idles || []; this._nextIdx = 0;
    this._front = this.vA; this._back = this.vB;
    const A = this._front;
    A.loop = false; A.src = m.hello;
    this._preloadNext();                         // 第一段待機先備好
    const showA = () => { if (gen === this._gen) A.style.opacity = '1'; A.removeEventListener('playing', showA); };
    A.addEventListener('playing', showA);
    A.play().catch(() => {
      // 被省電規則暫時擋下（例如分頁在背景）：半秒後再試一次，仍不行就維持靜態圖
      setTimeout(() => { if (this.active && gen === this._gen) A.play().catch(() => { if (gen === this._gen) this.stop(); }); }, 600);
    });
  },
  stop() {
    this.active = false; this._gen++; this._idles = null;
    [this.vA, this.vB].forEach(v => {
      if (!v) return;
      try { v.pause(); } catch (e) {}
      v.style.opacity = '0'; v.removeAttribute('src'); try { v.load(); } catch (e) {}
    });
  },
};

async function enterChat() {
  setCallToggle(false);
  // 2026-07-28（Edward 回報「二度撥通會看到上一段對話」）：這裡原本只把字幕框藏起來、
  // 沒有清掉裡面的字——上一通最後一句就一直留在框裡，下次撥通又把框顯示出來，
  // 一接通就看到上一通的對話。直接整個拿掉，要用時 setCaption 會重建一個乾淨的。
  const box = document.querySelector('.face-caption-box');
  if (box) box.remove();
  setFaceState('idle');
  _fhWarmArt();   // 全身立繪先換對角色並解碼（第一通接通時不再有解碼空窗＝不黑閃）
  if (typeof callConnected === 'undefined' || !callConnected) FaceIdle.start();   // 待機動態輪播（通話中不搶）
}

async function openVoiceSession() {
  if (chatOpened) return;
  chatOpened = true;
  activeChatSessionId = makeSessionId('voice');
  activeChatStartedAt = Date.now();
  activeChatTurnCount = 0;
  setFaceState('idle');
  setCallHint(muneaT('voice.connecting', '正在連線...'));
  await prepareAvatarSession();
  trackProductEvent('voice_session_started', {
    locale: muneaLocale(),
    requestedAvatarMode: requestedAvatarMode(),
  });
  const r = await voiceProvider.open(currentChar);
  if (r && r.reply) {
    setLocalizedCallHint('speaking');
    chatHistory.push({ role: 'model', text: r.reply });
    if (r.audio) playB64(r.audio); else speakChat(r.reply);
    faceSpeak(r.reply);
  } else {
    const fallback = muneaT('voice.fallback', '我在這裡，今天過得好嗎？想聊什麼都可以。');
    setLocalizedCallHint('ready');
    faceSpeak(fallback);
  }
}

function completeChatSession(reason = 'ended') {
  const trackedSession = Boolean(activeChatSessionId && activeChatStartedAt);
  const serverAuthoritative = Boolean(CallControl.url());
  const completedReasons = new Set(['ended', 'user_ended', 'idle_timeout', 'out_of_points', 'free_signup_trial_exhausted']);
  const diagnosticOutcome = reason === 'user_cancelled'
    ? 'cancelled'
    : (callConnected && completedReasons.has(reason) ? 'completed' : 'failed');
  voiceCallEnd(diagnosticOutcome, reason, {
    connected: callConnected,
    durationMs: activeChatStartedAt ? Math.max(0, Date.now() - activeChatStartedAt) : 0,
  });
  try {
    const releaseResult = CallControl.release(reason);
    if (serverAuthoritative && releaseResult && releaseResult.then) {
      releaseResult.then(result => {
        try { trackProductEvent('call_control_released', {
          reason,
          billedCredits: result && result.billed_credits,
          billableSeconds: result && result.billable_seconds,
        }); } catch (e) {}
        try { refreshServerCredits(); } catch (e) {}
      });
    }
  } catch (e) {}
  if (_callSec > 3 && trackedSession && !serverAuthoritative) {
    const mins = Math.max(1, Math.round(_callSec / 60));
    POINTS.used = Math.min(POINTS.total, POINTS.used + mins * 1);
    pushWallet();
    renderPoints();
  updateMedCount();
    toast(muneaT('voice.call.goodbye', ''));
  }
  stopCallTimer();
  if (!activeChatSessionId || !activeChatStartedAt) return;
  const durationMs = Math.max(0, Date.now() - activeChatStartedAt);
  trackProductEvent('voice_session_completed', {
    reason,
    durationMs,
    turnCount: activeChatTurnCount,
    meaningful: durationMs >= 60000 || activeChatTurnCount >= 3,
  });
  // 掛斷 → 把這通聊聊的對話送去萃取長期記憶（讓聊聊講的也記得住 · Edward 2026-07-10）
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice.saveMemory) LiveVoice.saveMemory(); } catch (e) {}
  activeChatSessionId = null;
  activeChatStartedAt = 0;
  activeChatTurnCount = 0;
}

function showView(id) {
  // 2026-07-30 Edward 拍板：訪客可以進聊聊頁看看（看得到誰要陪他講話、畫面長什麼樣），
  // 關卡從「門口」移到「開始通話」那一刻（見 connectCall 開頭與 #callToggle）。
  // 7/9 拍板 A 的原意沒有被放寬——免費 5 分鐘一樣要綁帳號才給，只是不再攔在門口。
  const t = $('#toast'); if (t) t.classList.remove('show');
  $$('.modal-mask.show').forEach(m => m.classList.remove('show'));
  // 回到首頁就去看有沒有家人帶話——長輩不會為了看訊息特地去按什麼，話要自己送到他眼前
  if (id === 'home') { try { syncHomeFamilyRelay(); } catch (e) {} }
  if (id === 'status') {
    renderStatusCharts();
    if (typeof window.__muneaRefreshMedicationUi === 'function') window.__muneaRefreshMedicationUi();
    const strip = $('#srcStrip');
    if (strip) strip.style.display = localStorage.getItem('munea.devicesOn') ? 'none' : '';
    // 底部「接上 Apple 健康」卡：還沒接才顯示；接上了就收起來（Edward 7/9）
    const cc = $('#stConnectCard');
    if (cc) cc.style.display = localStorage.getItem('munea.devicesOn') ? 'none' : '';
    const segBtns = document.querySelectorAll('#statusSeg .seg-btn');
    if (segBtns.length) {
      segBtns.forEach(x => x.classList.toggle('on', x.dataset.v === 'today'));
      const m = { today: $('#statusToday'), week: $('#statusWeek'), month: $('#statusMonth') };
      Object.entries(m).forEach(([k, el]) => { if (el) el.style.display = k === 'today' ? '' : 'none'; });
      if ($('#statusTitle')) $('#statusTitle').textContent = muneaT('status.todayTitle', '今天的狀態');
    }
  }
  if (id === 'family') {
    try { syncPullAll(); } catch (e) {}   // 進家人頁先拉最新動態
    if (window.__muneaSweepActs) { try { window.__muneaSweepActs(); } catch (e) {} }   // 順手收掉到期的活動卡（不用重開 App）
    const va = $('#viewAll');
    if (va && !va.classList.contains('active')) {
      $$('#family .fam-view').forEach(v => v.classList.remove('active'));
      va.classList.add('active');
    }
  }
  $$('.screen').forEach(s => s.classList.toggle('active', s.id === id));
  if (window.__muneaApplyUserAvatar) window.__muneaApplyUserAvatar();
  setTimeout(refreshHscrollHints, 60); // 分頁切換後重算「右邊還有」提示
  const overlay = OVERLAYS.includes(id);
  $('#tabBar').classList.toggle('hidden', overlay);
  $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.view === id));
  const el = $('#' + id); if (el) el.scrollTop = 0;
  if (id === 'chat') { Avatar.wake(); enterChat(); }   // 進聊聊頁＝先預醒雲端臉（按通話時多半已就緒）
  else if (typeof FaceIdle !== 'undefined') FaceIdle.stop();   // 離開聊聊頁＝待機動態停、省電
}

// 登入把關（7/9 Edward 拍板）：聊聊＋家人連線類要登入·用到才問；solo（今日健康/心情/提醒）免登入
// 回 true=已登入可繼續；回 false=擋下並跳「先登入」提示（不是一開 App 就擋登入牆）
function isLoggedIn() { try { const st = authState(); return !!(st && st.status === 'signed-in'); } catch (e) { return false; } }
function requireLogin(reasonText, feature) {
  try {
    if (isLoggedIn()) return true;
    if (typeof openAuthSheet === 'function') openAuthSheet();
    if (typeof setAuthMessage === 'function') {
      setAuthMessage(reasonText || muneaT('auth.signInRequired', '請使用 Google 或 Apple 登入'), 'ok');
    }
    try { trackProductEvent('login_gate_shown', { feature: feature || 'family' }); } catch (e) {}
    return false;
  } catch (e) { return true; }   // 判斷出錯就不擋（不因把關 bug 卡死使用者）
}
function requireLoginForFamily(reasonText) { return requireLogin(reasonText, 'family'); }
// 登入後帳號卡標題顯示什麼（Edward 2026-07-14 問）：優先真名（Google／Apple 登入都會給），
// 沒名字就用 email 的 @ 前面那段，再沒有才退回「已登入」。
function authDisplayName(state) {
  if (!state) return '';
  if (state.name) return String(state.name).trim();
  if (state.email) return String(state.email).split('@')[0];
  return '';
}
// 帳號卡右上角「唯一」的身份標籤（Edward 2026-07-14：只留一顆、統一右上，不要兩顆）
// 開發測試帳號 → TEST · FREE/PLUS/PRO；否則 FREE / PLUS / PRO
let _memBadgePlan = 'free';
function renderMemBadge(plan) {
  if (plan) _memBadgePlan = String(plan).toLowerCase();
  const mb = $('#memBadge');
  if (!mb) return;
  let dev = false;
  try { dev = !!authState().developerMode; } catch (e) {}
  const key = dev ? 'test' : _memBadgePlan;
  mb.textContent = dev ? ('TEST · ' + (_memBadgePlan || 'free').toUpperCase()) : key.toUpperCase();
  mb.className = 'mem-badge ' + key;
}
function authState() {
  const auth = window.MuneaAuth;
  return auth && typeof auth.state === 'function' ? auth.state() : { status: 'guest' };
}
function localPersonAvatar() {
  try { return (JSON.parse(localStorage.getItem('munea.personProfile') || '{}')).avatar || ''; } catch (e) { return ''; }
}
// 個人資料卡是否已經有「真資料」（不是全空白）——首登彈卡與「讓寧寧更認識你」小卡都靠這個判斷，
// 只看使用者會填的三格重點（家人稱呼／生日／所在地），不含名稱與照片（那兩格不影響「問過沒」判斷）。
function personProfileHasData(p) {
  const src = p || (function () { try { return JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); } catch (e) { return {}; } })();
  return !!(src && (String(src.nick || '').trim() || String(src.city || '').trim() || String(src.birth || '').trim()));
}
// 首頁「免費會員」標示（Edward 2026-07-24 拍板）：只在真的登入且是免費方案時顯示，不動方案邏輯本身。
function renderFreeMemberBadge() {
  const el = $('#homeMemberBadge');
  if (!el) return;
  let dev = false;
  try { dev = !!authState().developerMode; } catch (e) {}
  const free = !window.MMPLAN || typeof window.MMPLAN.isFree !== 'function' || window.MMPLAN.isFree();
  const show = isLoggedIn() && !dev && free;
  el.hidden = !show;
}
// 首頁「幫你留意」裡的個人資料提醒該不該出現：問過（首登彈過）但當時跳過、後續也還沒補填才出現。
// 一填完（稱呼／生日／所在地任一格有值）就自動不再出現——雲端資料合併回來也走同一條判斷。
function shouldShowProfileNudge() {
  return isLoggedIn() && storageGet(PERSON_PROFILE_PROMPT_KEY) === 'true' && !personProfileHasData();
}
// 只有「該不該出現」的答案真的翻面才重繪輪播：登入狀態每刷新一次就重繪的話，
// 輪播會被打回第一則，正在看家人帶話的人會被硬生生切走。
let _profileNudgeOn = null;
function syncProfileNudge() {
  const on = shouldShowProfileNudge();
  if (on === _profileNudgeOn) return;
  _profileNudgeOn = on;
  renderCareCarousel();
}
function renderAuthAvatar(state = authState(), signedIn = state.status === 'signed-in') {
  const box = $('#authAvatar');
  const img = $('#authAvatarImg');
  if (!box || !img) return;
  const meta = state && state.user && state.user.user_metadata ? state.user.user_metadata : {};
  const accountPhoto = signedIn ? (state.avatarUrl || meta.avatar_url || meta.picture || meta.photo_url || '') : '';
  const uploadedPhoto = signedIn ? localPersonAvatar() : '';
  const source = accountPhoto || uploadedPhoto;
  box.classList.toggle('guest', !signedIn);
  box.classList.toggle('has-photo', !!source);
  if (!source) {
    img.hidden = true;
    img.removeAttribute('src');
    img.dataset.source = '';
    img.onerror = null;
    return;
  }
  img.hidden = false;
  img.dataset.source = accountPhoto ? 'account' : 'local';
  img.onerror = () => {
    if (img.dataset.source === 'account' && uploadedPhoto && uploadedPhoto !== img.src) {
      img.dataset.source = 'local';
      img.src = uploadedPhoto;
      return;
    }
    img.hidden = true;
    img.removeAttribute('src');
    box.classList.remove('has-photo');
  };
  img.src = source;
}
function setAuthMessage(text = '', type = '') {
  const el = $('#authMessage');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('is-error', type === 'error');
  el.classList.toggle('is-ok', type === 'ok');
}
function setAuthMessageState(state, type = '') {
  const rendererCopy = muneaRendererCopy();
  const localized = {
    cancelled: () => muneaT('auth.cancelled', '已取消登入'),
    inProgress: () => muneaT('auth.inProgress', '正在前往登入…'),
    unavailable: () => muneaT('auth.unavailable', '目前無法登入，請稍後再試。'),
  };
  const resolvedState = localized[state] ? state : 'unavailable';
  setAuthMessage(
    rendererCopy
      ? rendererCopy.authMessage(resolvedState)
      : localized[resolvedState](),
    type,
  );
}
function localizeAuthTerms() {
  const terms = $('#authSheet .auth-terms');
  const link = terms && terms.querySelector('a');
  if (terms && link) {
    // 使用條款與隱私權政策各自成連結：同意畫面上兩份文件都要點得到（上線後合規要求）
    const combinedText = muneaT('auth.termsLink', '使用條款與隱私權政策');
    const termsText = muneaT('auth.termsLinkTerms', '使用條款');
    const privacyText = muneaT('auth.termsLinkPrivacy', '隱私權政策');
    // 連接詞從完整句切出來：en/es 需要前後空格，而字典值不允許留白邊
    const joiner = combinedText.startsWith(termsText) && combinedText.endsWith(privacyText)
      ? combinedText.slice(termsText.length, combinedText.length - privacyText.length)
      : muneaT('auth.termsJoiner', '與');
    link.textContent = termsText;
    link.setAttribute('href', '#');
    link.removeAttribute('target');
    link.removeAttribute('rel');
    const privacyLink = document.createElement('a');
    privacyLink.textContent = privacyText;
    privacyLink.setAttribute('href', '#');
    terms.replaceChildren(
      document.createTextNode(`${muneaT('auth.termsPrefix', '繼續即代表同意')} `),
      link,
      document.createTextNode(joiner),
      privacyLink,
      document.createTextNode(` — ${muneaT(
        'auth.aiProcessingDisclosure',
        '語音與文字會由 Munea 的 AI 系統處理，部分服務位於境外。',
      )}`),
    );
    if (link.dataset.readerBound !== '1') {
      link.dataset.readerBound = '1';
      link.addEventListener('click', event => {
        event.preventDefault();
        closeAuthSheet();
        openInAppReader('terms');
      });
    }
    privacyLink.addEventListener('click', event => {
      event.preventDefault();
      closeAuthSheet();
      openInAppReader('privacy');
    });
  }
  const close = $('#authCloseBtn');
  if (close) close.setAttribute('aria-label', muneaT('accessibility.close', '關閉'));
}
function openAuthSheet() {
  const sheet = $('#authSheet');
  if (!sheet) return;
  localizeAuthTerms();
  sheet.classList.add('show');
  sheet.setAttribute('aria-hidden', 'false');
  setAuthMessage('');
  const devBtn = $('#authDeveloperBtn');
  if (devBtn) {
    devBtn.hidden = !isDeveloperBypassAllowed();
    if (!devBtn.hidden) {
      devBtn.textContent = isGatewayDeveloperProfile()
        ? muneaT('auth.testAccount', devBtn.dataset.labelGateway || '使用測試帳號登入')
        : muneaT('auth.developerMode', devBtn.dataset.labelDefault || '使用開發者模式');
    }
  }
}
function closeAuthSheet() {
  const sheet = $('#authSheet');
  if (!sheet) return;
  sheet.classList.remove('show');
  sheet.setAttribute('aria-hidden', 'true');
}
// 通用「下拉關閉」手勢：抓每個彈窗頂部的把手往下拖，過門檻就關、沒過就彈回（Edward 7/7：所有類似彈窗都要有）
function enableSheetDrag() {
  let active = null, startY = 0, dy = 0;
  const modalOf = m => m && m.querySelector('.modal');
  const move = clientY => {
    if (!active) return;
    dy = Math.max(0, clientY - startY);
    const m = modalOf(active); if (m) m.style.transform = 'translateY(' + dy + 'px)';
  };
  const end = () => {
    if (!active) return;
    const mask = active, m = modalOf(mask); active = null;
    if (m) {
      m.style.transition = 'transform .28s cubic-bezier(.22,.9,.32,1)';
      if (dy > 88) { m.style.transform = 'translateY(100%)'; setTimeout(() => { mask.classList.remove('show'); m.style.transform = ''; m.style.transition = ''; }, 250); }
      else { m.style.transform = ''; setTimeout(() => { if (m) m.style.transition = ''; }, 300); }
    }
    dy = 0;
  };
  document.querySelectorAll('.modal-mask').forEach(mask => {
    const grab = mask.querySelector('.modal-grab');
    if (!grab || grab.dataset.drag) return;
    grab.dataset.drag = '1';
    grab.style.touchAction = 'none';                 // 把手上不觸發捲動
    const down = clientY => { active = mask; startY = clientY; dy = 0; const m = modalOf(mask); if (m) m.style.transition = 'none'; };
    grab.addEventListener('touchstart', e => down(e.touches[0].clientY), { passive: true });
    grab.addEventListener('mousedown', e => { e.preventDefault(); down(e.clientY); });
  });
  window.addEventListener('touchmove', e => { if (active) { move(e.touches[0].clientY); if (e.cancelable) e.preventDefault(); } }, { passive: false });
  window.addEventListener('touchend', end);
  window.addEventListener('mousemove', e => { if (active) move(e.clientY); });
  window.addEventListener('mouseup', end);
}
function syncAccountScopedCaches(state) {
  // 換帳號（含登出）就清掉「跟上一個帳號綁定」的本機殘留：
  // 方案等級與邀請碼都是伺服器按帳號算的，殘留會讓人走進註定失敗的畫面
  // （例：測試帳號的 Pro 殘留讓真帳號穿過免費門、到雲端才被擋）。
  try {
    const uid = String((state && (state.authUserId || state.userId)) || '');
    const last = localStorage.getItem('munea.lastAuthUser') || '';
    if (uid === last) return;
    localStorage.setItem('munea.lastAuthUser', uid);
    localStorage.removeItem('munea.inviteCode');
    localStorage.removeItem('munea.inviteCodeAt');
    localStorage.removeItem('munea.plan');
    if (uid && typeof refreshServerPlanEntitlement === 'function') refreshServerPlanEntitlement();
  } catch (e) {}
}
function updateAuthUI() {
  // 7/9 正式化：示範假登入（陳秀英）拆除——畫面只反映真實登入狀態
  const state = authState();
  syncAccountScopedCaches(state);
  let signedIn = state.status === 'signed-in';
  renderAuthAvatar(state, signedIn);
  const card = $('#authCard');
  if (card) card.dataset.authState = signedIn ? 'signed-in' : 'guest';
  const status = $('#authStatusText');
  if (status) status.textContent = signedIn
    ? (authDisplayName(state) || muneaT('auth.signedIn', '已登入'))
    : muneaT('auth.guestMode', '訪客模式');
  const email = $('#authEmailText');
  if (email) email.textContent = signedIn && state.email ? state.email : '';
  const signIn = $('#authSignInBtn');
  if (signIn) signIn.hidden = signedIn;
  const signOut = $('#authSignOutBtn');
  if (signOut) signOut.hidden = !signedIn;
  renderMemBadge();
  renderFreeMemberBadge();
  syncProfileNudge();
  // 剛登入完就去看有沒有人留話給他——不必等他自己切分頁（登出時這支會把卡片收乾淨）
  try { syncHomeFamilyRelay(); } catch (e) {}
  renderAiDiagnostics();
}
async function signInWithAuthProvider(provider) {
  // 7/9 正式化：沒設定好就老實說、不再假裝登入成功
  if (authState().configured === false) {
    setAuthMessageState('unavailable', 'error');
    return;
  }
  const auth = window.MuneaAuth;
  if (!auth) return setAuthMessageState('unavailable', 'error');
  setAuthMessageState('inProgress', 'ok');
  trackProductEvent('auth_sign_in_started', { provider });
  const method = provider === 'apple' ? auth.signInWithApple : auth.signInWithGoogle;
  const result = method ? await method() : { ok: false, error: { code: 'unsupported_provider' } };
  const code = String(result && result.error && result.error.code || 'unknown').replace(/[^a-z0-9_.-]/gi, '').slice(0, 64) || 'unknown';
  const fallbackFrom = String(result && result.fallbackFrom || '').replace(/[^a-z0-9_.-]/gi, '').slice(0, 64);
  if (result && result.ok) {
    if (fallbackFrom) {
      trackProductEvent('auth_sign_in_fallback_started', { provider, from: fallbackFrom, path: result.authPath || '' });
      return setAuthMessageState('inProgress', 'ok');
    }
    return setAuthMessageState('inProgress', 'ok');
  }
  trackProductEvent('auth_sign_in_failed', { provider, code, fallbackFrom });
  // 比對結尾而非整串：Apple 與 Google 各自回 <provider>_sign_in_cancelled／_in_progress，
  // 寫死 google_ 開頭會讓 Apple 使用者按到一半退出時看到紅字「登入失敗」——取消不是失敗。
  if (code.endsWith('_sign_in_cancelled')) return setAuthMessageState('cancelled', 'info');
  if (code.endsWith('_sign_in_in_progress')) return setAuthMessageState('inProgress', 'ok');
  setAuthMessageState('unavailable', 'error');
}
async function signInDeveloperMode() {
  const auth = window.MuneaAuth;
  if (!auth) return setAuthMessage(muneaT('auth.devNotEnabled', '開發者模式尚未啟用'), 'error');
  // --gateway profile：真帳號真登入拿真 JWT、過總機驗證——不是造假證（Build 43 安全洞已補死，永不重開）。
  if (isGatewayDeveloperProfile()) {
    if (typeof auth.signInWithTestAccount !== 'function') return setAuthMessage(muneaT('auth.devNotEnabled', '開發者模式尚未啟用'), 'error');
    const result = await auth.signInWithTestAccount({ reason: 'settings_auth_sheet_gateway' });
    if (result && result.ok) {
      trackProductEvent('auth_developer_signed_in', { provider: 'test-account' });
      updateAuthUI();
      closeAuthSheet();
      return;
    }
    const code = String((result && result.error && result.error.code) || 'unknown');
    setAuthMessage(
      code === 'test_account_credentials_missing' ? muneaT('auth.devTestMissing', '測試帳號憑證未設定') : muneaT('auth.devTestFailed', '測試帳號登入失敗（{code}）', { code }),
      'error',
    );
    return;
  }
  if (typeof auth.signInAsDeveloper !== 'function') return setAuthMessage(muneaT('auth.devNotEnabled', '開發者模式尚未啟用'), 'error');
  const result = await auth.signInAsDeveloper({ reason: 'settings_auth_sheet' });
  if (result && result.ok) {
    trackProductEvent('auth_developer_signed_in', { provider: 'dev-bypass' });
    updateAuthUI();
    closeAuthSheet();
    return;
  }
  setAuthMessage(muneaT('auth.devNotAllowed', '此環境不可使用開發者模式'), 'error');
}
async function signOutAuth() {
  const auth = window.MuneaAuth;
  if (!auth || typeof auth.signOut !== 'function') return;
  await auth.signOut();
  trackProductEvent('auth_signed_out', {});
  updateAuthUI();
}
function setupAuthControls() {
  if ($('#authSignInBtn')) $('#authSignInBtn').addEventListener('click', openAuthSheet);
  if ($('#authSignOutBtn')) $('#authSignOutBtn').addEventListener('click', async () => {
    const state = authState();
    if (state.status === 'signed-in') { await signOutAuth(); return; }
    updateAuthUI();
  });
  if ($('#authCloseBtn')) $('#authCloseBtn').addEventListener('click', closeAuthSheet);
  if ($('#authAppleBtn')) $('#authAppleBtn').addEventListener('click', () => signInWithAuthProvider('apple'));
  if ($('#authGoogleBtn')) $('#authGoogleBtn').addEventListener('click', () => signInWithAuthProvider('google'));
  if ($('#authDeveloperBtn')) $('#authDeveloperBtn').addEventListener('click', signInDeveloperMode);
  const sheet = $('#authSheet');
  if (sheet) sheet.addEventListener('click', e => { if (e.target === sheet) closeAuthSheet(); });
  updateAuthUI();
}

// 首頁天氣：真的查（open-meteo 免費氣象站、不用鑰匙）——查得到才顯示、查不到整塊不出現，不擺假太陽
(function homeWeather() {
  const wrap = document.getElementById('homeWxWrap'), wx = document.getElementById('homeWx');
  if (!wrap || !wx) return;
  const CK = 'munea.wxCache';
  try { const c = JSON.parse(localStorage.getItem(CK) || 'null'); if (c && Date.now() - c.t < 1800000) { wx.textContent = c.text; wrap.style.display = ''; return; } } catch (e) {}
  function wtxt(code) {
    const M = [[0, '☀ ' + muneaT('weather.clear', '晴')], [1, '🌤 ' + muneaT('weather.mostlyClear', '晴時多雲')], [2, '⛅ ' + muneaT('weather.cloudy', '多雲')], [3, '☁ ' + muneaT('weather.overcast', '陰')], [45, '🌫 ' + muneaT('weather.fog', '有霧')], [51, '🌦 ' + muneaT('weather.drizzle', '毛毛雨')], [61, '🌧 ' + muneaT('weather.rain', '有雨')], [71, '❄ ' + muneaT('weather.snow', '下雪')], [80, '🌧 ' + muneaT('weather.showers', '陣雨')], [95, '⛈ ' + muneaT('weather.thunder', '雷雨')]];
    let t = '⛅ ' + muneaT('weather.cloudy', '多雲'); for (const [c, s] of M) if (code >= c) t = s; return t;
  }
  function ok(text) { wx.textContent = text; wrap.style.display = ''; try { localStorage.setItem(CK, JSON.stringify({ t: Date.now(), text })); } catch (e) {} }
  function byCoords(lat, lon) {
    return fetch('https://api.open-meteo.com/v1/forecast?latitude=' + lat + '&longitude=' + lon + '&current=temperature_2m,weather_code&timezone=auto')
      .then(r => r.json()).then(j => {
        const c = j && j.current;
        if (!c || typeof c.temperature_2m !== 'number') throw new Error('no-data');
        ok(wtxt(c.weather_code || 0) + ' ' + Math.round(c.temperature_2m) + '°');
      });
  }
  function byCity(city) {
    return fetch('https://geocoding-api.open-meteo.com/v1/search?count=' + 1 + '&language=' + encodeURIComponent(window.MuneaI18n ? window.MuneaI18n.weatherLanguage() : 'zh') + '&name=' + encodeURIComponent(city))
      .then(r => r.json()).then(j => {
        const g = j && j.results && j.results[0];
        if (!g) throw new Error('no-city');
        return byCoords(g.latitude, g.longitude);
      });
  }
  let city = '';
  try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || 'null'); city = ((p && p.city) || '').trim(); } catch (e) {}
  // 7/9 隱私修正（送審前）：拿掉精確定位（GPS）備援，只用「個人資料」設定的縣市查天氣——沒設城市就整塊不顯示，不再問使用者要精確位置
  (city ? byCity(city) : Promise.reject(new Error('no-profile-city')))
    .catch(() => { /* 沒設所在地＝不顯示天氣，只留日期 */ });
})();

function _muneaSameCalendarDate(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}
function _muneaDaysBetween(a, b) {
  const A = new Date(a.getFullYear(), a.getMonth(), a.getDate()).getTime();
  const B = new Date(b.getFullYear(), b.getMonth(), b.getDate()).getTime();
  return Math.round((A - B) / 86400000);
}
function _muneaDayOfYear(d) {
  const start = new Date(d.getFullYear(), 0, 0);
  return Math.floor((d - start) / 86400000);
}
function _muneaAskByHour(h) {
  if (h >= 18 || h < 5) return muneaT('greet.askNight', '睡前跟我聊聊今天？');
  if (h >= 5 && h < 11) return muneaT('greet.askMorning', '走走回來，說給我聽？');
  if (h >= 11 && h < 14) return muneaT('greet.askNoon', '來跟我聊聊今天？');
  return muneaT('greet.askAfternoon', '傍晚散個步，回來跟我聊？');
}
// 順位 0：只取家人動態最上面一則，格式要真的是「XX要我提醒你：YYY」，內容再過一次乾淨中文守門
// ——這裡是全家人都看得到的位置，比首頁話題本身更危險（Edward 2026-07-14）
// 首頁那張卡上的家人帶話（Edward 2026-07-31）
//
// 舊寫法是撈「家人動態牆」的第一則、再用比對句子的方式猜哪句是傳話（`^(.+?)要我提醒你`）——
// 那等於拿畫面上的文字反推資料：中文文案改一個字就失靈，換成英日西更是整條認不出來。
// 而且動態牆是 App 自己產的句子，真正的傳話根本不在裡面——長輩只有在「開始聊聊」時
// 才聽得到寧寧唸，首頁完全看不到。現在直接跟雲端拿真的那一則。
//
// 沒有「我知道了」這種確認鍵（Edward 2026-07-31）：長輩不必為了讓話消失而學按什麼。
// 話送到眼前就算送到了，接著自然被日子蓋過去——
//   ① 去聊過天：那件事已經在對話裡談過了，卡片回到平常的問候
//   ② 有新的一則帶話：新的蓋掉舊的，一次只講一件事
//   ③ 放到隔天：昨天的叮嚀今天再貼一次只會變成噪音
// 顯示當下就回報送達，所以要自己在手機裡留一份——雲端不會再給同一則。
const HOME_RELAY_KEY = 'munea.homeRelay';
const HOME_RELAY_TTL_MS = 24 * 60 * 60 * 1000;
let _muneaHomeRelay = null;
function homeRelayText(relay) {
  if (!relay) return '';
  const body = muneaSafeDisplayText(relay.content, '');
  if (!body) return '';
  const who = muneaSafeDisplayText(relay.senderLabel, '') || muneaT('familyCircle.someoneInFamily', '家人');
  return muneaT('familyCircle.relayLine', '{name}要我提醒你：{body}', { name: who, body });
}
function loadHomeRelay() {
  try {
    const saved = JSON.parse(localStorage.getItem(HOME_RELAY_KEY) || 'null');
    if (!saved || !saved.at || !homeRelayText(saved)) return null;
    if (Date.now() - saved.at > HOME_RELAY_TTL_MS) return null;          // ③ 隔天就不再貼
    if (+(localStorage.getItem('munea.lastChatAt') || 0) > saved.at) return null;  // ① 聊過了
    return saved;
  } catch (e) { return null; }
}
function saveHomeRelay(relay) {
  try {
    if (!relay) localStorage.removeItem(HOME_RELAY_KEY);
    else localStorage.setItem(HOME_RELAY_KEY, JSON.stringify({
      id: relay.id, senderLabel: relay.senderLabel, content: relay.content, at: Date.now(),
    }));
  } catch (e) {}
}
async function syncHomeFamilyRelay() {
  const had = !!_muneaHomeRelay;
  if (typeof isLoggedIn === 'function' && !isLoggedIn()) {
    _muneaHomeRelay = null;
    saveHomeRelay(null);
    if (had) renderCompanionGreeting();
    return;
  }
  _muneaHomeRelay = loadHomeRelay();          // 先貼上手機裡留著的那則，畫面不會空一拍
  if (had !== !!_muneaHomeRelay) renderCompanionGreeting();
  let relay = null;
  try { relay = await claimNextFamilyRelay(); } catch (e) { relay = null; }
  if (!homeRelayText(relay)) return;
  _muneaHomeRelay = relay;                    // ② 新的蓋掉舊的
  saveHomeRelay(relay);
  renderCompanionGreeting();
  // 話已經在他眼前了＝送到了。回報放在畫面之後，網路慢也不會讓卡片晚一步出現。
  try {
    await finishFamilyRelayClaim(relay, 'ack');
    rememberSpokenFamilyRelay(relay);         // 記下這則已經到了，通話時不必再唸一次
  } catch (e) {}
}
// 用藥有沒打勾（順位 2-b）：跟 renderPillTask() 同一套算法（今天還沒吃的下一項 / 完成數 / 總數）
function _muneaPillStatusToday() {
  try {
    const meds = (typeof loadMeds === 'function') ? loadMeds() : [];
    if (!meds.length) return null;
    let done = {};
    try { done = JSON.parse(localStorage.getItem('munea.medDone.' + pillDateKey())) || {}; } catch (e2) {}
    const slots = [];
    meds.forEach(med => String(med.time).split('、').forEach(raw => {
      const slot = raw.trim();
      if (slot) slots.push({ slot, name: med.name, key: slot + '|' + med.name });
    }));
    if (!slots.length) return null;
    const total = slots.length;
    const doneN = slots.filter(s => done[s.key]).length;
    const next = slots.find(s => !done[s.key]);
    return next ? { next, doneN, total } : null;
  } catch (e) { return null; }
}
// 3 天內（含今天）最近一筆回診（順位 2-a）
function _muneaVisitWithinDays(days) {
  try {
    const arr = JSON.parse(localStorage.getItem('munea.visits') || 'null');
    if (!Array.isArray(arr)) return null;
    const today = new Date(); today.setHours(0, 0, 0, 0);
    let best = null, bestDiff = Infinity;
    arr.forEach(v => {
      if (!v || !v.dateISO) return;
      const d = new Date(v.dateISO + 'T00:00');
      if (isNaN(d)) return;
      const diff = Math.round((d - today) / 86400000);
      if (diff >= 0 && diff <= days && diff < bestDiff) { bestDiff = diff; best = v; }
    });
    return best;
  } catch (e) { return null; }
}
// 順位 2「今天還沒聊」的內容子選：好幾天沒聊 > 回診 > 用藥 > 天氣 > 家常問候輪替（用當年第幾天 mod 輪替，不連兩天一樣）
function _muneaNotChattedTodayLine(now, ask) {
  try {
    const lastAt = +(localStorage.getItem('munea.lastChatAt') || 0);
    const gapDays = lastAt ? _muneaDaysBetween(now, new Date(lastAt)) : null;
    if (gapDays !== null && gapDays >= 3) {
      const v = { days: gapDays, ask };
      const leads = [
        muneaT('greet.gap1', '{days}天沒聊了，{ask}', v), muneaT('greet.gap2', '有{days}天沒聽你說話了，{ask}', v), muneaT('greet.gap3', '隔了{days}天沒聊，{ask}', v),
        muneaT('greet.gap4', '{days}天沒你的消息了，{ask}', v), muneaT('greet.gap5', '{days}天沒說到話了，{ask}', v), muneaT('greet.gap6', '好些天沒聊了，都{days}天了，{ask}', v)
      ];
      return leads[_muneaDayOfYear(now) % leads.length];
    }
    const visit = _muneaVisitWithinDays(3);
    if (visit) {
      const vt = muneaSafeDisplayText(visit.title, '') || muneaSafeDisplayText(visit.label, '') || muneaT('visit.defaultTitle', '回診');   // 招呼卡引用看診標題前守門（Edward 2026-07-15 事故）
      const v = { visit: vt, ask };
      const leads = [muneaT('greet.visit1', '{visit}快到了，{ask}', v), muneaT('greet.visit2', '別忘了{visit}，{ask}', v), muneaT('greet.visit3', '{visit}的事，記得，{ask}', v), muneaT('greet.visit4', '要回診了，{ask}', v), muneaT('greet.visit5', '{visit}要記得，{ask}', v)];
      return leads[_muneaDayOfYear(now) % leads.length];
    }
    const pill = _muneaPillStatusToday();
    if (pill) {
      const v = { slot: medSlotLabel(pill.next.slot), ask };
      const leads = [
        muneaT('greet.pill1', '{slot}的藥吃了嗎，{ask}', v), muneaT('greet.pill2', '記得吃{slot}的藥，{ask}', v), muneaT('greet.pill3', '別忘了{slot}的藥，{ask}', v),
        muneaT('greet.pill4', '{slot}該吃藥囉，{ask}', v), muneaT('greet.pill5', '藥還沒吃完，{ask}', v)
      ];
      return leads[_muneaDayOfYear(now) % leads.length];
    }
    let wxText = '';
    try { const c = JSON.parse(localStorage.getItem('munea.wxCache') || 'null'); if (c && c.text) wxText = c.text; } catch (e3) {}
    if (wxText) {
      const v = { wx: wxText, ask };
      const leads = [muneaT('greet.wx1', '今天{wx}，{ask}', v), muneaT('greet.wx2', '{wx}，出門記得看天氣，{ask}', v)];
      return leads[_muneaDayOfYear(now) % leads.length];
    }
    const v = { ask };
    const chat = [
      muneaT('greet.chat1', '上次聊得很開心，我都記得你——{ask}', v), muneaT('greet.chat2', '今天有什麼新鮮事嗎，{ask}', v), muneaT('greet.chat3', '想到什麼都可以跟我說，{ask}', v),
      muneaT('greet.chat4', '我在這裡，{ask}', v), muneaT('greet.chat5', '今天過得還好嗎，{ask}', v), muneaT('greet.chat6', '有空的話，{ask}', v), muneaT('greet.chat7', '我一直都在，{ask}', v)
    ];
    return chat[_muneaDayOfYear(now) % chat.length];
  } catch (e) { return ask; }
}
// 順位 3「今天已經聊過」的收尾句：不帶逼問、不再重複問「要不要聊」
function _muneaChattedTodayLine(now) {
  const lines = [
    muneaT('greet.done1', '今天聊得很開心，我都記得。'), muneaT('greet.done2', '有你陪我聊聊，今天很好。'), muneaT('greet.done3', '想到什麼都可以再找我。'),
    muneaT('greet.done4', '今天說的話我都記著了。'), muneaT('greet.done5', '先歇著吧，我一直都在。'), muneaT('greet.done6', '謝謝你今天陪我聊天。'),
    muneaT('greet.done7', '今天先到這裡，想聊隨時找我。'), muneaT('greet.done8', '有你在，今天特別好。')
  ];
  return lines[_muneaDayOfYear(now) % lines.length];
}
function renderCompanionGreeting(now = new Date()) {
  const msg = $('#bcMsg');
  if (!msg) return;
  const nm = (typeof cname === 'function' ? cname() : muneaT('companion.nening.name', '寧寧'));
  const ask = _muneaAskByHour(now.getHours());
  let line = '';
  let relayLine = '';
  try {
    relayLine = homeRelayText(_muneaHomeRelay);
    const lastAt = +(localStorage.getItem('munea.lastChatAt') || 0);
    if (relayLine) {
      line = relayLine;
    } else if (!lastAt) {
      line = muneaT('home.introFirst', '我是{companion}，來陪你說說話的——點下面，跟我認識一下？', { companion: nm });
    } else if (!_muneaSameCalendarDate(new Date(lastAt), now)) {
      line = _muneaNotChattedTodayLine(now, ask);
    } else {
      line = _muneaChattedTodayLine(now);
    }
  } catch (e) {
    line = nm + '，' + ask;   // 順位 4：任何讀取失敗，只靠 cname() 與時段拼出最保守泛用句
  }
  if (!line) line = nm + '，' + ask;
  msg.textContent = line;
  // 有家人帶話時整張卡換一個樣子：標上「家人帶話」、字放大到 4 行、給一顆「我知道了」。
  // 沒有帶話就回到平常的問候，一顆多餘的按鍵都不留。
  const card = $('#butlerCard'), more = $('#bcRelayMore');
  if (card) { card.classList.toggle('has-relay', !!relayLine); if (!relayLine) card.classList.remove('relay-open'); }
  // 話太長被切掉時才給「看全部」——切掉的後半可能正是重點（幾點回診、東西放哪）
  if (more) {
    const clipped = !!relayLine && card && !card.classList.contains('relay-open') && msg.scrollHeight > msg.clientHeight + 1;
    more.hidden = !clipped;
  }
  // 聊聊頁人物畫面上的那顆字泡（faceIdleHi）已整個拿掉（Edward 2026-07-16）——首頁卡片這行照舊
}

function renderHomeGreeting() {
  const now = new Date();
  const h = now.getHours();
  renderCompanionGreeting(now);

  const meta = $('#metaDate');
  if (meta) {
    meta.textContent = new Intl.DateTimeFormat(muneaLocale(), {
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    }).format(now);
  }
  const kick = $('#greetKicker'), big = $('#greetBig');
  let k = muneaT('home.greetingHello', '你好');
  if (h >= 5 && h < 11) k = muneaT('home.greetingMorning', '早安');
  else if (h >= 11 && h < 18) k = muneaT('home.greetingAfternoon', '午安');
  else if (h >= 18 && h < 22) k = muneaT('home.greetingEvening', '晚上好');
  else k = muneaT('home.greetingLate', '夜深了');
  if (kick) kick.textContent = k;
  if (big) big.textContent = k;
}
renderHomeGreeting();
// 話太長時的「看全部」；綁一次就好，卡片本身不重建、只切換樣子
document.addEventListener('click', e => {
  if (!(e.target && e.target.closest)) return;
  if (e.target.closest('#bcRelayMore')) {
    const card = $('#butlerCard');
    if (card) card.classList.add('relay-open');
    const more = $('#bcRelayMore'); if (more) more.hidden = true;
  }
});

function loadMeds() {
  // 沒設用藥就是空的——首頁不該有吃藥任務、用藥管理顯示空狀態（Edward 2026-07-07）
  try { return JSON.parse(localStorage.getItem('munea.meds')) || []; } catch (e) { return []; }
}
function updateMedCount() {
  const count = loadMeds().length;
  const n = muneaT('settings.medicationCount', '{count} 種藥', { count });
  const el = $('#medCountLabel');
  if (el) el.textContent = n;
  const el2 = $('#medCountSettings');
  if (el2) el2.textContent = n;
  renderPillTask();
  if (window.MuneaNotify) window.MuneaNotify.sync(); // 用藥變動 → 重排 App 關著也會響的提醒
}
const PILL_SLOT_ORDER = ['早餐後', '午餐後', '晚餐後', '睡前'];
const PILL_SLOT_KEYS = Object.freeze({
  '早餐後': 'medication.slot.afterBreakfast',
  '午餐後': 'medication.slot.afterLunch',
  '晚餐後': 'medication.slot.afterDinner',
  '睡前': 'medication.slot.bedtime',
});
function localizedMedicationSlot(slot) {
  const label = String(slot || '').trim();
  const key = PILL_SLOT_KEYS[label];
  return key ? muneaT(key, label) : label;
}
function canonicalMedicationSlot(slot) {
  const label = String(slot || '').trim();
  if (PILL_SLOT_KEYS[label]) return label;
  const stableIds = {
    afterBreakfast: '早餐後',
    afterLunch: '午餐後',
    afterDinner: '晚餐後',
    'after-breakfast': '早餐後',
    'after-lunch': '午餐後',
    'after-dinner': '晚餐後',
    bedtime: '睡前',
  };
  if (stableIds[label]) return stableIds[label];
  const normalized = window.MuneaMedicationScheduleI18n?.normalizeSlot(label);
  if (normalized && stableIds[normalized]) return stableIds[normalized];
  return Object.keys(PILL_SLOT_KEYS).find(
    canonical => localizedMedicationSlot(canonical).toLocaleLowerCase(muneaLocale())
      === label.toLocaleLowerCase(muneaLocale()),
  ) || '';
}
function localizedMedicationSlotList(slots) {
  const values = (Array.isArray(slots) ? slots : String(slots || '').split('、'))
    .map(canonicalMedicationSlot)
    .filter(Boolean)
    .map(localizedMedicationSlot);
  try {
    return new Intl.ListFormat(muneaLocale(), { style: 'long', type: 'conjunction' }).format(values);
  } catch (e) {
    return values.join('、');
  }
}
function localizedMedicationDuration(duration) {
  const raw = canonicalMedicationDuration(duration);
  const dayMatch = raw.match(/^(\d+)\s*天$/);
  if (dayMatch) {
    const count = new Intl.NumberFormat(muneaLocale()).format(Number(dayMatch[1]));
    return muneaT('medication.duration.days', '{count} 天', { count });
  }
  if (raw === '長期') return muneaT('medication.duration.longTerm', '長期');
  if (raw === '每天') return muneaT('medication.duration.daily', '每天');
  return raw;
}
function canonicalMedicationDuration(duration) {
  const raw = String(duration || '').trim();
  if (!raw) return muneaT('medication.duration.longTerm', '長期');
  return window.MuneaMedicationScheduleI18n?.normalizeDuration(raw) || raw;
}
function pillDateKey() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
const WEEK_STEPS = [4200, 5100, 3600, 6200, 5500, 0, 0]; // 一~日；今天=第5天
function renderStatusCharts(force = false) {
  const wb = document.getElementById('weekBars');
  if (force && wb) delete wb.dataset.done;
  if (wb && !wb.dataset.done) {
    const mx = Math.max(...WEEK_STEPS, 1);
    const names = Array.from({ length: 7 }, (_, index) => (
      new Intl.DateTimeFormat(muneaLocale(), { weekday: 'narrow' })
        .format(new Date(2024, 0, 7 + index))
    ));
    wb.innerHTML = WEEK_STEPS.map((v, i) => {
      const kind = i === 4 ? 'today' : (i > 4 ? 'future' : (v >= 5000 ? 'hi' : ''));
      const hpx = v ? Math.max(10, Math.round(v / mx * 74)) : 8;
      return '<div class="cbar ' + kind + '"><i style="height:' + hpx + 'px"></i><b>' + names[i] + '</b></div>';
    }).join('');
    wb.dataset.done = '1';
  }
  const mb = document.getElementById('monthBars');
  if (force && mb) delete mb.dataset.done;
  if (mb && !mb.dataset.done) {
    let html = '';
    for (let d = 1; d <= 30; d++) {
      const v = d <= 23 ? (30 + ((d * 37) % 60)) : 0; // 過去23天示範值、未來留白
      const kind = d === 23 ? 'today' : (d > 23 ? 'future' : (v >= 70 ? 'hi' : ''));
      html += '<div class="cbar ' + kind + '"><i style="height:' + Math.max(6, Math.round(v / 90 * 44)) + 'px"></i></div>';
    }
    mb.innerHTML = html;
    mb.dataset.done = '1';
  }
}
function renderPillTask() {
  const card = document.querySelector('.task-item[data-task="pill"]');
  const title = $('#pillTitle'), sub = $('#pillSub');
  if (!card || !title || !sub) return;
  const meds = loadMeds();
  if (!meds.length) {
    // 沒設定用藥就不該有這個任務——整條收起來，不留佔位（Edward 2026-07-07）
    card.style.display = 'none';
    card.classList.remove('done');
    if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
    return;
  }
  card.style.display = '';
  let slots = [];
  if (window.MuneaMedication) {
    slots = window.MuneaMedication.dayEvents(meds, pillDateKey()).map(event => ({
      ...event,
      name: event.medicationName,
      key: event.slot + '|' + event.medicationName,
    }));
  } else {
    let done = {};
    try { done = JSON.parse(localStorage.getItem('munea.medDone.' + pillDateKey())) || {}; } catch (e) {}
    for (const med of meds) {
      for (const raw of String(med.time).split('、')) {
        const slot = raw.trim();
        if (slot) slots.push({ slot, name: med.name, key: slot + '|' + med.name, photo: med.photo || '', status: done[slot + '|' + med.name] ? 'taken' : 'scheduled' });
      }
    }
    slots.sort((a, b) => PILL_SLOT_ORDER.indexOf(a.slot) - PILL_SLOT_ORDER.indexOf(b.slot));
  }
  const total = slots.length;
  const doneN = slots.filter(s => s.status === 'taken').length;
  const next = slots.find(s => s.status !== 'taken' && s.status !== 'skipped');
  if (next) {
    const genericName = muneaT('medication.genericName', '藥');
    const rawName = String(next.name || '').trim();
    const shortSource = muneaLocale() === 'zh-TW'
      ? rawName.split(/\s+/)[0]
      : rawName;
    const shortName = muneaSafeDisplayText(shortSource, genericName);
    title.textContent = muneaT('medication.takeName', '吃{name}', { name: shortName });
    sub.textContent = muneaT('medication.taskProgress', '{slot} · 今天 {done}/{total} 次', {
      slot: localizedMedicationSlot(next.slot),
      done: doneN,
      total,
    });
    card.classList.remove('done');
  } else {
    title.textContent = muneaT('medication.allDone', '都完成了');
    sub.textContent = muneaT('medication.completedToday', '今天 {total} 次都記到了', { total });
    card.classList.add('done');
  }
  const _pico = card.querySelector('.task-ico');
  if (_pico) { const _pph = next && next.photo; if (_pph) { _pico.style.backgroundImage = 'url(' + _pph + ')'; _pico.style.backgroundSize = 'cover'; _pico.style.backgroundPosition = 'center'; _pico.classList.add('med-photo-ico'); _pico.onclick = ev => { ev.stopPropagation(); showMedPhoto(_pph, next.name); }; } else { _pico.style.backgroundImage = ''; _pico.classList.remove('med-photo-ico'); _pico.onclick = null; } }
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
}
// 回診只在「當天」變成今日任務；其餘日子不顯示（Edward 2026-07-07）
function _todayISO() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function visitToday() {
  let arr = null;
  try { arr = JSON.parse(localStorage.getItem('munea.visits') || 'null'); } catch (e) {}
  if (!Array.isArray(arr)) return null;
  const today = _todayISO();
  return arr.filter(v => v && v.dateISO === today).sort((a, b) => String(a.time || '').localeCompare(String(b.time || '')))[0] || null;
}
// 串清單的寫法各國不一樣：中文日文用「、」不留空格，英文西班牙文要「逗號＋一個空格」。
// 文案表不准存前後有空白的值（守門擋著、避免文案末尾藏看不見的空格），
// 所以空格在這裡補——英文西文原本被串成「Riverside;Park;Market」（2026-08-01 截圖看見）。
function muneaListSeparator() {
  const locale = muneaLocale();
  const sep = muneaT('common.listSeparator', '、');
  return (locale === 'en' || locale === 'es') ? sep + ' ' : sep;
}
function _clock12(tv) {
  const p = String(tv || '').split(':'); const hh = +p[0], mm = +p[1] || 0;
  if (isNaN(hh)) return '';
  const date = new Date(2024, 0, 1, hh, mm);
  // 整點原本會省略分鐘，四個語系印出來差很多：
  //   中文「下午8時」／英文「8 PM」／日文「20時」／西班牙文只剩一個「20」。
  // 西班牙文那個看起來像壞掉（2026-08-01 Edward 指出）。一律帶分鐘就四語一致。
  return new Intl.DateTimeFormat(muneaLocale(), {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}
// 24 小時制，跟用藥任務的「14:00」一致（Edward 2026-07-14）
function _clock24(tv) {
  const p = String(tv || '').split(':'); const hh = +p[0], mm = +p[1] || 0;
  if (isNaN(hh)) return '';
  return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0');
}
// 只要「7/14（週二）」——不帶標題、不帶時間（Edward 2026-07-14）
function _visitDayShort(v) {
  if (!v) return '';
  if (v.dateISO) {
    const d = new Date(v.dateISO + 'T00:00');
    if (!isNaN(d.getTime())) {
      return new Intl.DateTimeFormat(muneaLocale(), {
        month: 'numeric',
        day: 'numeric',
        weekday: 'short',
      }).format(d);
    }
  }
  return String(v.label || '').split(/\s*[上下]午/)[0].trim();  // 舊資料兜底
}
function renderVisitTask() {
  const card = document.getElementById('visitTask');
  if (!card) return;
  const v = visitToday();
  if (!v) { card.style.display = 'none'; card.classList.remove('done'); if (typeof refreshTaskProgress === 'function') refreshTaskProgress(); return; }
  card.style.display = '';
  const t = $('#visitTaskTitle'), s = $('#visitTaskSub'), tm = $('#visitTaskTime');
  if (t) t.textContent = muneaSafeDisplayText(v.title, '') || muneaSafeDisplayText(v.label, '') || muneaT('visit.defaultTitle', '回診');   // 今天一起完成的回診卡標題守門（Edward 2026-07-15 事故）
  // 副標給一個點開的理由——有記問題就講幾題，沒有就回到原本的提醒（M1 PR-4c）
  let sub = _visitDayShort(v) || muneaT('visit.defaultNote', '記得帶健保卡與用藥資料');
  try {
    const qn = (typeof openCareQuestions === 'function') ? openCareQuestions().length : 0;
    if (qn > 0) sub = muneaT('visit.openForQuestions', '點開看這次要問的 {n} 個問題', { n: qn });
  } catch (e) {}
  if (s) s.textContent = sub;
  if (tm) tm.textContent = _clock24(v.time) || muneaT('common.today', '今天');
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
}
// 行程（揪一攤約會/聚餐）跟回診同一條規矩：只在「當天」進今日任務（Edward 7/16「今天的行程才顯示今天」）
function eventToday() {
  let arr = null;
  try { arr = JSON.parse(localStorage.getItem('munea.activities') || 'null'); } catch (e) {}
  if (!Array.isArray(arr)) return null;
  const today = _todayISO();
  return arr.filter(a => a && a.kind === 'event' && a.dateISO === today)
    .sort((x, y) => String(x.time || '').localeCompare(String(y.time || '')))[0] || null;
}
function renderEventTask() {
  const card = document.getElementById('eventTask');
  if (!card) return;
  const ev = eventToday();
  if (!ev) { card.style.display = 'none'; card.classList.remove('done'); if (typeof refreshTaskProgress === 'function') refreshTaskProgress(); return; }
  card.style.display = '';
  const t = $('#eventTaskTitle'), s = $('#eventTaskSub'), tm = $('#eventTaskTime');
  if (t) t.textContent = muneaSafeDisplayText(ev.title, '') || muneaT('event.familyTitle', '和家人的約');
  if (s) s.textContent = muneaSafeDisplayText(ev.place, '') || muneaT('event.arriveOnTime', '記得準時赴約');
  if (tm) tm.textContent = _clock24(ev.time) || muneaT('common.today', '今天');
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
}
// 首頁「今天一起完成」整組重算：用藥（有設才有）＋回診（當天才有）＋行程（當天才有）＋走走＋心情筆記＋聊聊
function renderDailyTasks() { renderPillTask(); renderVisitTask(); renderEventTask(); refreshMoodTask(); }
window.__muneaRenderDailyTasks = renderDailyTasks;
// Apple 健康的步數 → 首頁走路任務（原生端 health.js 讀到步數後呼叫）
function renderWalkProgress(n) {
  n = Math.max(0, Math.round(+n || 0));
  const card = document.querySelector('.task-item[data-task="walk"]');
  if (!card) return;
  const goal = (window.MuneaHealth && window.MuneaHealth.GOAL) || 500;
  const sub = document.getElementById('walkSub');
  const chip = document.getElementById('walkChip');
  if (sub) sub.removeAttribute('data-i18n');
  if (chip) chip.removeAttribute('data-i18n');
  const count = new Intl.NumberFormat(muneaLocale()).format(n);
  const formattedGoal = new Intl.NumberFormat(muneaLocale()).format(goal);
  if (sub) {
    sub.textContent = n >= goal
      ? muneaT('home.walkProgressMet', '今天走了 {count} 步，達標了', { count })
      : muneaT('home.walkProgress', '今天走了 {count} / {goal} 步', {
        count,
        goal: formattedGoal,
      });
  }
  if (chip) {
    chip.textContent = n >= goal
      ? muneaT('home.walkGoalMet', '達標')
      : muneaT('home.walkSteps', '{count} 步', { count });
  }
  card.dataset.steps = String(n);
  if (n >= goal) card.classList.add('done'); // 走到目標就自動完成
  if (typeof refreshTaskProgress === 'function') refreshTaskProgress();
  // 步數也記進數據日記帳（供 7/30 天真趨勢）
  try {
    if (!isLoggedIn()) throw 'guest';
    const day = _todayISO();
    mergeHealthHistory([{ date: day, steps: n }]);
  } catch (e) {}
}
window.__muneaSetSteps = renderWalkProgress;

const HEALTH_LOG_RETENTION_DAYS = 365;
function mergeHealthHistory(days, syncCloud = true) {
  if (!isLoggedIn() || !Array.isArray(days)) return {};
  let log = {};
  try { log = JSON.parse(localStorage.getItem('munea.healthLog') || '{}') || {}; } catch (e) {}
  const fields = ['bpSys', 'bpDia', 'hr', 'spo2', 'sleepHours', 'steps'];
  for (const item of days) {
    if (!item || !/^\d{4}-\d{2}-\d{2}$/.test(String(item.date || ''))) continue;
    const current = Object.assign({}, log[item.date] || {});
    for (const field of fields) {
      const value = Number(item[field]);
      if (Number.isFinite(value) && value >= 0) current[field] = value;
    }
    if (Object.keys(current).length) log[item.date] = current;
  }
  const keys = Object.keys(log).sort();
  while (keys.length > HEALTH_LOG_RETENTION_DAYS) delete log[keys.shift()];
  try { localStorage.setItem('munea.healthLog', JSON.stringify(log)); } catch (e) {}
  if (syncCloud) pushOwnHealthLog(log);
  return log;
}
window.__muneaSetHealthHistory = function (days) { return mergeHealthHistory(days, true); };

function muneaCloudPersonId() {
  try { return localStorage.getItem('munea.cloudPersonId') || muneaDeviceId(); }
  catch (e) { return muneaDeviceId(); }
}
function pushOwnHealthLog(log) {
  try {
    const pf = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
    const personId = muneaCloudPersonId();
    const keys = Object.keys(log || {}).sort();
    const day = keys[keys.length - 1] || _todayISO();
    const current = (log || {})[day] || {};
    const mine = {};
    // 7/16 心情真串接：今日粗心情標籤（只有詞＋色，不含聊天內容）跟健康數據走同一條家庭帳本水管
    const mood = myMoodToday();
    mine[personId] = Object.assign({ name: (pf.name || '').trim(), nick: (pf.nick || '').trim(), day, updatedAt: Date.now(), log }, current, mood ? { mood } : {});
    syncPush('vitals', mine);
  } catch (e) {}
}
// 自己的今日心情摘要（loadMoodWeekReal 寫入）：只留 {label, key, date} 粗標籤、觀察細節不出這支手機
function myMoodToday() {
  try {
    const m = JSON.parse(localStorage.getItem('munea.myMoodToday') || 'null');
    return (m && m.key && m.date === _todayISO()) ? m : null;
  } catch (e) { return null; }
}
// Apple 健康的完整摘要 → 狀態頁「今天」的真數值（原生端 health.js 讀到後呼叫）
// s = { available, steps, hr, spo2, bpSys, bpDia, sleepHours }；缺哪項就不動哪項（示範值留著、不清空）
window.__muneaSetHealth = function (s) {
  if (!s || s.available === false) return;
  const num = v => (typeof v === 'number' && isFinite(v) && v > 0) ? v : null;
  const put = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  const chip = (id, txt, warn) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = txt;
    el.style.display = '';   // 真數據到了就把標籤點亮（沒接裝置時是藏起來的）
    el.style.background = warn ? 'var(--coral-soft)' : 'var(--mint)';
    el.style.color = warn ? 'var(--ink)' : 'var(--teal-dd)';
  };
  const sys = num(s.bpSys), dia = num(s.bpDia), hr = num(s.hr), spo2 = num(s.spo2),
        sleep = num(s.sleepHours), steps = num(s.steps);
  const worry = []; // 給「寧寧的觀察」的注意事項（白話）
  if (sys && dia) {
    const hi = sys >= 140 || dia >= 90, lo = sys < 90;
    put('bpNum', String(Math.round(sys)));
    put('bpUnit', '/' + Math.round(dia) + ' mmHg');
    chip('bpChip', hi ? muneaT('health.high', '偏高') : lo ? muneaT('health.low', '偏低') : muneaT('health.stable', '穩定'), hi || lo);
    put('bpSub', hi ? muneaT('health.bpHighRetryHint', '比平常高一點，晚點再量一次') : lo ? muneaT('health.bpLowHint', '偏低一些，起身動作放慢') : muneaT('health.bpNormalHint', '正常範圍內'));
    if (hi) worry.push(muneaT('health.worryBpHigh', '血壓比平常高一點')); if (lo) worry.push(muneaT('health.worryBpLow', '血壓偏低'));
  }
  if (hr) {
    const odd = hr < 50 || hr > 100;
    put('hrNum', String(Math.round(hr)));
    chip('hrChip', odd ? muneaT('health.attention', '注意') : muneaT('health.normal', '正常'), odd);
    if (odd) worry.push(hr > 100 ? muneaT('health.worryHrFast', '心跳偏快') : muneaT('health.worryHrSlow', '心跳偏慢'));
  }
  if (spo2) {
    put('spo2Num', String(Math.round(spo2)));
    if (spo2 < 95) worry.push(muneaT('health.worrySpo2', '血氧有點低'));
  }
  if (sleep) {
    put('sleepNum', String(Math.round(sleep * 10) / 10));
    if (sleep < 6) worry.push(muneaT('health.worrySleepShort', '昨晚睡得少'));
  }
  if (steps) {
    put('stepsNum', Math.round(steps).toLocaleString());
    // 運動量不足（7/9 Edward 點題）：傍晚後還走不到 3000 步才提、白天不亂催
    if (new Date().getHours() >= 18 && steps < 3000) worry.push(muneaT('health.worryFewSteps', '今天走得比較少'));
  }
  // 寧寧的觀察：有真資料才改寫，一句話講重點
  const obs = document.getElementById('obsText');
  if (obs && (sys || hr || sleep)) {
    const B = t => '<b style="color:#8FD4CC">' + t + '</b>';
    const bits = [];
    if (sys && dia) bits.push(muneaT('health.obsMetricBp', '血壓 {value}', { value: B(Math.round(sys) + '/' + Math.round(dia)) }));
    if (hr) bits.push(muneaT('health.obsMetricHr', '心率 {value}', { value: B(Math.round(hr)) }));
    if (sleep) bits.push(muneaT('health.obsMetricSleep', '睡眠 {value}', { value: B((Math.round(sleep * 10) / 10) + ' ' + muneaT('health.unit.hoursShort', '小時')) }));
    const metricsLine = bits.join(muneaListSeparator());
    obs.innerHTML = worry.length
      ? muneaT('health.obsSteadyWithWorry', '今天{metrics}，大致都穩，不過{worries}，我幫你多留意，先別擔心。', { metrics: metricsLine, worries: B(worry.join(muneaListSeparator())) })
      : muneaT('health.obsAllGood', '今天{metrics}，整體狀態不錯。{cheer}，想出門走走我陪你。', { metrics: metricsLine, cheer: '<span style="color:#8FD4CC;font-weight:700">' + muneaT('health.obsKeepItUp', '保持這個節奏就很好') + '</span>' });
    window.__muneaObsReal = obs.innerHTML;   // 真觀察已寫：分頁切換不得用預設蓋掉
  }
  // 安全通知（真的動）：數據掉出危險範圍 → 寫進家人動態（雲端同步、家人打開沐寧就看到）；同類 6 小時最多一次
  try {
    const danger = [];
    if (sys && (sys >= 180 || sys < 90)) danger.push('血壓 ' + Math.round(sys) + (dia ? '/' + Math.round(dia) : ''));
    if (hr && (hr > 120 || hr < 45)) danger.push('心率 ' + Math.round(hr));
    if (spo2 && spo2 < 90) danger.push('血氧 ' + Math.round(spo2) + '%');
    if (danger.length) {
      const last = +(localStorage.getItem('munea.safetyAlertAt') || 0);
      if (Date.now() - last > 21600000) {
        localStorage.setItem('munea.safetyAlertAt', String(Date.now()));
        let who = '家人';
        try { const pf = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); who = pf.nick || pf.name || '家人'; } catch (e2) {}
        pushFamilyFeed('⚠️ <b>' + who + '</b>的' + danger.join('、') + '超出安全範圍，打通電話關心一下');
        try { trackProductEvent('safety_alert_recorded', { kinds: danger.length }); } catch (e2) {}
      }
    }
  } catch (e) {}
  // 數據日記帳：今天的數據記成歷史（日期為鍵、留 365 天），狀態頁 7/30 天分頁就從這裡長出真趨勢
  // 7/9 Edward 拍板：只有登入的會員才記每天的數據 → 之後才有 7/30 天趨勢（訪客看得到今天、但不累積歷史）
  try {
    if (!isLoggedIn()) throw 'guest';   // 訪客不記歷史（今日即時數字上面已顯示）
    const day = _todayISO();
    const cur = {};
    if (sys) cur.bpSys = Math.round(sys);
    if (dia) cur.bpDia = Math.round(dia);
    if (hr) cur.hr = Math.round(hr);
    if (spo2) cur.spo2 = Math.round(spo2);
    if (sleep) cur.sleepHours = Math.round(sleep * 10) / 10;
    if (steps) cur.steps = Math.round(steps);
    mergeHealthHistory([Object.assign({ date: day }, cur)]);
  } catch (e) {}
};
function renderMedList() { renderMedSlots(); }
const MED_SLOT_DEF = [
  ['早餐後', 'b', 30], ['午餐後', 'l', 30], ['晚餐後', 'd', 30], ['睡前', 's', -30]
];
// 用藥時段的「畫面顯示名」（Edward 2026-07-29：直接寫餐別，不要寫飯前飯後——
// 藥該飯前還飯後吃是醫生決定的，App 不該替使用者預設）。
// 內部值維持「早餐後」等舊字串不動：那是用藥資料、推播、語音腦共用的代號，
// 改掉會對不上使用者既有的藥單。所有給人看的地方一律走 medSlotLabel()。
const MED_SLOT_LABEL = {
  '早餐後': () => muneaT('medication.slot.afterBreakfast', '早餐'),
  '午餐後': () => muneaT('medication.slot.afterLunch', '中餐'),
  '晚餐後': () => muneaT('medication.slot.afterDinner', '晚餐'),
  '睡前': () => muneaT('medication.slot.bedtime', '睡前'),
};
function medSlotLabel(slot) { return MED_SLOT_LABEL[slot] ? MED_SLOT_LABEL[slot]() : slot; }
function medSlotTime(rtKey, offset) {
  let rt = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
  try { rt = Object.assign(rt, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) {}
  let parts = (rt[rtKey] || '08:00').split(':').map(Number);
  const total = (parts[0] * 60 + parts[1] + offset + 1440) % 1440;
  return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
function showMedPhoto(url, name) {
  if (!url) return;
  let lb = document.getElementById('medLightbox');
  if (!lb) { lb = document.createElement('div'); lb.id = 'medLightbox'; lb.className = 'med-lightbox'; document.body.appendChild(lb); lb.addEventListener('click', ev => { if (ev.target === lb || ev.target.classList.contains('mlb-close')) lb.classList.remove('show'); }); }
  lb.innerHTML = '<div class="mlb-card"><img src="' + url + '" alt=""><div class="mlb-name">' + muneaEscapeHtml(muneaSafeDisplayText(name, '')) + '</div><button type="button" class="mlb-close">' + muneaEscapeHtml(muneaT('common.close', '關閉')) + '</button></div>';   // 藥物照片燈箱名稱守門（Edward 2026-07-15 事故）
  lb.classList.add('show');
}
function canvasToJpeg(cv) { let q = 0.82; let url = cv.toDataURL('image/jpeg', q); while (url.length > 180000 && q > 0.4) { q -= 0.16; url = cv.toDataURL('image/jpeg', q); } return url; }
function looksLikeImage(file) { return !!file && (/^image\//.test(file.type || '') || /\.(jpe?g|png|heic|heif|webp|gif|bmp)$/i.test(file.name || '')); }
function resizeSquare(file, cb, onErr) {
  if (!looksLikeImage(file)) { if (onErr) onErr(); return; }
  const r = new FileReader();
  r.onerror = () => { if (onErr) onErr(); };
  r.onload = () => { const img = new Image(); img.onload = () => { try { const S = 512; const side = Math.min(img.width, img.height); const sx = (img.width - side) / 2, sy = (img.height - side) / 2; const cv = document.createElement('canvas'); cv.width = S; cv.height = S; cv.getContext('2d').drawImage(img, sx, sy, side, side, 0, 0, S, S); cb(canvasToJpeg(cv)); } catch (e) { if (onErr) onErr(); } }; img.onerror = () => { if (onErr) onErr(); }; img.src = r.result; };
  r.readAsDataURL(file);
}
function renderMedSlots() {
  const box = $('#medSlots');
  if (!box) return;
  const meds = loadMeds();
  box.innerHTML = MED_SLOT_DEF.map(def => {
    const slot = def[0], k = def[1], off = def[2];
    const inSlot = meds.filter(m => String(m.time).split('、').map(x => x.trim()).includes(slot));
    const rows = inSlot.length
      ? inSlot.map(m => {
        const safeName = muneaSafeDisplayText(
          m.name,
          muneaT('medication.genericName', '藥物'),
        );
        const removeLabel = muneaT(
          'medicationManager.removeSlot',
          '從{slot}移除{name}',
          { slot: localizedMedicationSlot(slot), name: safeName },
        );
        return '<div class="ms-med">'
          + (m.photo ? '<span class="ms-thumb" data-name="' + muneaEscapeHtml(m.name) + '" style="background-image:url(' + m.photo + ')"></span>' : '')
          + '<b>' + muneaEscapeHtml(safeName) + '</b>'
          + '<span>' + muneaEscapeHtml(localizedMedicationDuration(m.days)) + '</span>'
          + '<button type="button" class="ms-del" data-slot="' + muneaEscapeHtml(slot) + '" data-name="' + muneaEscapeHtml(m.name) + '" aria-label="' + muneaEscapeHtml(removeLabel) + '">✕</button></div>';
      }).join('')   // 用藥管理清單顯示名守門（data-name 保留原文供刪除比對，Edward 2026-07-15 事故）
      : '';
    const count = new Intl.NumberFormat(muneaLocale()).format(inSlot.length);
    // 有藥就在第二行寫「幾種」；沒藥就把「這個時段沒有藥」寫在同一個位置——
    // 原本那是另外一整行，四個空時段等於白白多佔四行（Edward 2026-08-01：板位太大）
    const countCopy = inSlot.length
      ? (inSlot.length === 1
        ? muneaT('medicationManager.medicineCountOne', '{count} 種', { count })
        : muneaT('medicationManager.medicineCountOther', '{count} 種', { count }))
      : muneaT('medicationManager.emptySlot', '這個時段沒有藥');
    const reminderTimeLabel = muneaT(
      'medicationManager.reminderTime',
      '提醒時間',
    );
    const reminderTime = medSlotTime(k, off);
    return '<div class="ms-group"><div class="ms-head"><b>' + muneaEscapeHtml(localizedMedicationSlot(slot)) + '</b>' +
      '<span class="ms-time-wrap"><button type="button" class="ms-tbtn" data-k="' + k + '" data-m="-15">−</button>' +
      '<label class="ms-time-control"><span class="ms-time-display" aria-hidden="true">' + reminderTime + '</span>' +
      '<input type="time" class="ms-time" data-k="' + k + '" data-off="' + off + '" value="' + reminderTime + '" aria-label="' + muneaEscapeHtml(reminderTimeLabel) + '" /></label>' +
      '<button type="button" class="ms-tbtn" data-k="' + k + '" data-m="15">＋</button></span>' +
      '<span class="ms-count">' + muneaEscapeHtml(countCopy) + '</span></div>' + rows + '</div>';
  }).join('');
}

function setElementOwnText(element, text) {
  if (!element) return;
  // 這個元素裡若已經有掛翻譯標記的子節點，那段字翻譯層會自己處理——
  // 這裡再補一次就會變成同一句印兩次（外語版才看得到，中文版永遠測不出來）。
  // 2026-08-01 Edward 在西班牙文版看到「Informar de un problemaInformar de un problema」，
  // 追下去是四處都犯：意見分類四顆鈕、選圖片、三條健康警訊、我吃過了。
  // 與其一處一處刪，在這裡擋住整類——之後誰再呼叫都不會重複。
  if (element.querySelector && element.querySelector('[data-i18n]')) return;
  const textNodes = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE);
  if (textNodes.length) {
    textNodes[0].textContent = text;
    textNodes.slice(1).forEach(node => node.remove());
    return;
  }
  element.appendChild(document.createTextNode(text));
}

function renderMedicationReminderCopy(medication) {
  const modal = document.getElementById('medRemindModal');
  if (!modal) return;
  const med = medication || {};
  const canonicalSlot = canonicalMedicationSlot(med.time) || '早餐後';
  const slot = localizedMedicationSlot(canonicalSlot);
  const name = muneaSafeDisplayText(
    med.name,
    muneaT('medication.genericName', '藥物'),
  );
  modal.dataset.medicationName = name;
  modal.dataset.medicationSlot = canonicalSlot;
  if ($('#medDueSay')) $('#medDueSay').textContent = muneaT(
    'medicationReminder.dueSay',
    '{slot}的藥，時間到了',
    { slot },
  );
  if ($('#medDueName')) $('#medDueName').textContent = name;
  if ($('#medDueDesc')) $('#medDueDesc').textContent = muneaT(
    'medicationReminder.description',
    '{slot}提醒 · 請依藥袋或醫囑服用',
    { slot },
  );
}

function medicationReminderSpeech(medication) {
  const med = medication || {};
  const canonicalSlot = canonicalMedicationSlot(med.time) || '早餐後';
  return muneaT(
    'medicationReminder.speech',
    '{name}是{slot}的藥，時間到了。服用後跟我說一聲。',
    {
      name: muneaSafeDisplayText(
        med.name,
        muneaT('medication.genericName', '藥物'),
      ),
      slot: localizedMedicationSlot(canonicalSlot),
    },
  );
}

function localizeMedicationSurfaces() {
  const manager = document.getElementById('medMgrModal');
  if (manager) {
    const title = manager.querySelector('.modal > h2');
    if (title) title.textContent = muneaT('medication.title', '用藥');
    const subtitle = manager.querySelector('.modal-sub');
    if (subtitle) subtitle.textContent = [
      muneaT('medicationManager.subtitle', '設定後會在時間到時通知；開啟 App 可確認是否已服用。'),
      muneaT('medicationManager.disclaimer', 'Munea 只協助提醒，不提供用藥判斷；請依醫師或藥師指示服用。'),
    ].join(' ');
    const addLabel = manager.querySelector('.field-label.sect-new');
    if (addLabel) addLabel.textContent = muneaT('medicationManager.addMedicine', '新增一種藥');
    const nameInput = document.getElementById('medName');
    if (nameInput) nameInput.placeholder = muneaT('medication.namePlaceholder', '藥名照藥袋抄');
    const photoButton = document.getElementById('medPhotoBtn');
    if (photoButton) photoButton.textContent = muneaT('medicationManager.photo', '加入藥物照片');
    const photoHint = manager.querySelector('.med-photo-hint');
    if (photoHint) photoHint.textContent = muneaT('medicationManager.photoHint', '選填，幫助你辨認藥物');
    const scheduleLabel = document.getElementById('medTimeChips')?.previousElementSibling;
    if (scheduleLabel) scheduleLabel.textContent = muneaT(
      'medicationManager.scheduleMultiple',
      '什麼時候吃（可多選）',
    );
    const durationLabel = document.getElementById('medDayChips')?.previousElementSibling;
    if (durationLabel) durationLabel.textContent = muneaT('medicationManager.duration', '吃多久');
    document.querySelectorAll('#medTimeChips .mchip').forEach(chip => {
      chip.textContent = localizedMedicationSlot(chip.dataset.t);
    });
    document.querySelectorAll('#medDayChips .mchip').forEach(chip => {
      chip.textContent = localizedMedicationDuration(chip.dataset.d);
    });
    const addButton = document.getElementById('medAddBtn');
    if (addButton) addButton.textContent = muneaT('medicationManager.add', '加入提醒');
    const closeButton = document.getElementById('medMgrClose');
    if (closeButton) closeButton.setAttribute(
      'aria-label',
      muneaT('medicationManager.close', '關閉用藥提醒'),
    );
    renderMedSlots();
  }

  const reminder = document.getElementById('medRemindModal');
  if (reminder) {
    const closeButton = reminder.querySelector('.mx-close');
    if (closeButton) closeButton.setAttribute(
      'aria-label',
      muneaT('common.close', '關閉'),
    );
    const streak = reminder.querySelector('.mpc-streak');
    setElementOwnText(
      streak,
      muneaT('medicationReminder.streak', '已連續完成 {days} 天', {
        days: new Intl.NumberFormat(muneaLocale()).format(6),
      }),
    );
    const taken = document.getElementById('medTaken');
    setElementOwnText(taken, muneaT('medicationReminder.taken', '我吃過了'));
    const snooze = document.getElementById('medSnooze');
    if (snooze) snooze.textContent = muneaT(
      'medicationReminder.snooze',
      '{minutes} 分鐘後再提醒',
      { minutes: new Intl.NumberFormat(muneaLocale()).format(10) },
    );
    renderMedicationReminderCopy({
      name: reminder.dataset.medicationName,
      time: reminder.dataset.medicationSlot,
    });
  }
}

window.__medicationI18nTest = {
  showManager: medication => {
    const med = medication || {
      name: muneaT('medication.genericName', '藥物'),
      time: '早餐後',
      days: '長期',
    };
    localStorage.setItem('munea.meds', JSON.stringify([med]));
    localizeMedicationSurfaces();
    document.getElementById('medMgrModal')?.classList.add('show');
  },
  showReminder: medication => {
    renderMedicationReminderCopy(medication);
    localizeMedicationSurfaces();
    document.getElementById('medRemindModal')?.classList.add('show');
  },
  reminderSpeech: medication => medicationReminderSpeech(medication),
  canonicalSlot: slot => canonicalMedicationSlot(slot),
  canonicalDuration: duration => canonicalMedicationDuration(duration),
};

const POINTS = { total: 0, used: 0, serverRemaining: null,    // 方案與雲端錢包載入後再填入，不預設舊方案額度
  get bought() { try { return +localStorage.getItem('munea.ptsBought') || 0; } catch (e) { return 0; } } };
const LOW_PTS = 30;
window.__ptsTest = {
  setUsed: v => { POINTS.used = v; renderPoints(); },
  setRemaining: v => { POINTS.serverRemaining = Math.max(0, Number(v) || 0); renderPoints(); },
  showExhausted: () => __muneaShowPointsPopup(),
  showIdleChat: () => {
    document.querySelectorAll('.screen').forEach(screen => screen.classList.remove('active'));
    const chat = document.getElementById('chat');
    if (chat) {
      chat.classList.add('active');
      chat.dataset.state = 'idle';
    }
    setCallToggle(false);
    localizeChatControls();
  },
  showQueued: () => {
    showBusyCard('queued', { position: 3, eta_s: 121 });
    setCallPreflightPending(true, muneaT('voice.queue.pending', '排隊中…'));
  },
  showFreeMinute: () => {
    setCallPreflightPending(false);
    toast(muneaT(
      'credits.freeTrialOneMinute',
      '免費體驗剩約 1 分鐘，慢慢說完沒關係。',
    ));
  },
  showVoiceRuntimeCaption: state => {
    captionsOn = true;
    applyCaptionState();
    setLocalizedRuntimeCaption(state);
  },
  showVoiceRuntimeHint: state => {
    setLocalizedRuntimeHint(state);
    return document.getElementById('chatCaption')?.textContent || '';
  },
  ff: s => { _callSec = s; },
};
window.__medRefresh = () => updateMedCount();
function ptsLeft() {
  return Number.isFinite(POINTS.serverRemaining)
    ? POINTS.serverRemaining
    : POINTS.total - POINTS.used + POINTS.bought;
}
function refreshLowState() {
  // 「點數快用完了、到這裡加值」只對付費會員成立：免費不吃點數、也沒有加值鈕可按，
  // 對他們喊這句＝叫他去按一個不存在的鈕（免費 0 點時 0 < 30 會誤觸發、原本就在發生）。
  const low = !(window.MMPLAN && window.MMPLAN.isFree()) && ptsLeft() < LOW_PTS;
  const pts = document.querySelector('.hud-pill.pts');
  if (pts) pts.classList.toggle('low', low);
  const strip = document.getElementById('lowPtsStrip');
  if (strip) strip.style.display = low ? '' : 'none';
}
function pushWallet() { syncPush('wallet', { grant: POINTS.total, used: POINTS.used, bought: POINTS.bought }); }
// 點數牌：只要手上有點就一定看得到餘額（Edward 7/17 拍板）。
// 只有「免費 + 真的 0 點」才收起來——免費走一次性 5 分鐘體驗、不吃點數，
// 這時掛「剩 0 點」會被誤會成「沒點數不能聊」。
function ptsPillHidden() { return !!(window.MMPLAN && window.MMPLAN.isFree()) && ptsLeft() <= 0; }
function rebuildSettingsPointsLabel(formattedLeft) {
  const label = document.querySelector('.plan-card .pts-label');
  const balance = $('#ptsLeft');
  const usage = label ? label.querySelector('.pts-used') : null;
  const grant = $('#setPlanGrant');
  const used = $('#ptsUsed');
  if (!label || !balance || !usage || !grant || !used) return;

  const balanceMarker = '__MUNEA_CREDITS__';
  const balanceCopy = muneaT(
    'settings.creditsBalance',
    '點數 {credits} 點',
    { credits: balanceMarker },
  );
  const balanceParts = balanceCopy.split(balanceMarker);
  balance.textContent = formattedLeft;
  label.replaceChildren(
    document.createTextNode(balanceParts[0] || ''),
    balance,
    document.createTextNode(balanceParts.slice(1).join(balanceMarker) || ''),
    document.createTextNode(' '),
    usage,
  );

  const grantMarker = '__MUNEA_GRANT__';
  const usedMarker = '__MUNEA_USED__';
  const usageCopy = muneaT(
    'settings.monthlyGrantUsed',
    '每月送 {grant} · 已用 {used}',
    { grant: grantMarker, used: usedMarker },
  );
  const usageParts = usageCopy.split(grantMarker);
  const afterGrant = (usageParts[1] || '').split(usedMarker);
  grant.textContent = new Intl.NumberFormat(muneaLocale()).format(Number(grant.textContent) || 0);
  used.textContent = new Intl.NumberFormat(muneaLocale()).format(POINTS.used);
  usage.replaceChildren(
    document.createTextNode(usageParts[0] || ''),
    grant,
    document.createTextNode(afterGrant[0] || ''),
    used,
    document.createTextNode(afterGrant.slice(1).join(usedMarker) || ''),
  );
}
function renderPoints() {
  const left = ptsLeft();
  const formattedLeft = new Intl.NumberFormat(muneaLocale()).format(left);
  const hud = document.querySelector('.hud-pill.pts');
  if (hud) {
    hud.textContent = muneaT('settings.creditsBalance', '點數 {credits} 點', { credits: formattedLeft });
    hud.style.display = ptsPillHidden() ? 'none' : '';
  }
  rebuildSettingsPointsLabel(formattedLeft);
  // 餘額變了 → 設定頁那列點數（要不要露出來、說明句寫什麼）跟著重算。
  // 伺服器餘額（/credits/balance）回來時只會走到這裡，不會經過 renderPlanState。
  try { if (window.__muneaRenderCreditRow) window.__muneaRenderCreditRow(); } catch (e) {}
  if ($('#ptsBar')) $('#ptsBar').style.width = (POINTS.total > 0 ? Math.round(POINTS.used / POINTS.total * 100) : 0) + '%';
  refreshLowState();
}

async function refreshServerCredits() {
  if (!isLoggedIn()) return null;
  const result = await brainPost('/credits/balance', {});
  const rawTotal = result && result.walletSummary && result.walletSummary.total;
  const total = Number(rawTotal);
  if (rawTotal !== null && rawTotal !== undefined && rawTotal !== '' && Number.isFinite(total)) {
    POINTS.serverRemaining = Math.max(0, total);
    renderPoints();
  }
  return result;
}

let _callTimerInt = null, _callSec = 0;
let _lowWarned = false, _zeroSaid = false, _freeWarned = false;
let _brainDegraded = false;
function callBudgetTick() {
  if (window.MMPLAN && window.MMPLAN.isFree()) return;   // 免費用「單次時間試用」、不吃點數
  const left = ptsLeft() - Math.floor(_callSec / 60);
  if (!_lowWarned && left <= 15 && left > 0) {
    _lowWarned = true;
    const minutes = new Intl.NumberFormat(muneaLocale()).format(left);
    setCaption(
      muneaT('credits.lowTitle', '點數快用完了，大概還能聊 {minutes} 分鐘', { minutes }),
      muneaT('credits.lowBody', '用完聊天會先停，補點數就能繼續'),
    );
  }
  if (!_zeroSaid && left <= 0) {
    _zeroSaid = true;
    __muneaPointsOut();                                  // 點數用完 → 停止聊天 + 跳補點數
  }
}
function renderPointsPopupCopy(root) {
  const popup = root || document.getElementById('mm-pts');
  if (!popup) return;
  const title = popup.querySelector('[data-points-copy="title"]');
  const body = popup.querySelector('[data-points-copy="body"]');
  const go = popup.querySelector('[data-points-action="top-up"]');
  const no = popup.querySelector('[data-points-action="dismiss"]');
  if (title) title.textContent = muneaT('credits.exhaustedTitle', '點數用完了');
  if (body) body.textContent = muneaT(
    'credits.exhaustedBody',
    '聊天會用到點數，這批剛好用完囉。補一些點數，就能繼續跟沐寧聊。',
  );
  if (go) go.textContent = muneaT('settings.topUpCredits', '補充點數');
  if (no) no.textContent = muneaT('common.notNow', '先不用');
}
function __muneaShowPointsPopup(){
  var old=document.getElementById('mm-pts'); if(old) old.remove();
  var m=document.createElement('div'); m.id='mm-pts';
  m.style.cssText='position:fixed;inset:0;z-index:10060;display:flex;align-items:center;justify-content:center;background:rgba(30,26,22,.5);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px)';
  m.innerHTML='<div style="width:min(320px,84vw);background:#F4F0E8;border-radius:24px;padding:26px 22px 18px;text-align:center;box-shadow:0 24px 60px -14px rgba(0,0,0,.5)">'
    +'<div style="width:54px;height:54px;border-radius:16px;margin:0 auto 16px;background:linear-gradient(135deg,#E0B354,#C79A3B);display:grid;place-items:center"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v9M9 10h4.5a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3H15"/></svg></div>'
    +'<div data-points-copy="title" style="font-family:\'Noto Serif TC\',Georgia,serif;font-weight:900;font-size:19px;color:#3A352E;margin-bottom:10px"></div>'
    +'<div data-points-copy="body" style="font-size:14px;line-height:1.75;color:#5A6963;margin-bottom:20px"></div>'
    +'<button data-points-action="top-up" style="width:100%;border:none;background:#3AA8A0;color:#fff;font-weight:700;font-size:15.5px;padding:14px;border-radius:14px;cursor:pointer;margin-bottom:6px"></button>'
    +'<button data-points-action="dismiss" style="width:100%;border:none;background:none;color:#8A9691;font-weight:600;font-size:14px;padding:9px;cursor:pointer"></button>'
    +'</div>';
  document.body.appendChild(m);
  renderPointsPopupCopy(m);
  m.addEventListener('click',function(e){ if(e.target===m||e.target.closest('[data-points-action="dismiss"]')) m.remove(); });
  var go=m.querySelector('[data-points-action="top-up"]');
  if(go) go.addEventListener('click',function(){ m.remove(); var tm=document.getElementById('topUpModal'); if(tm) tm.classList.add('show'); });
}
function __muneaShowCallCreditBlocked(){
  if (window.MMPLAN && window.MMPLAN.isFree()) {
    window.MMPLAN.upsell('chat-daily');
    return;
  }
  __muneaShowPointsPopup();
}
function __muneaPointsOut(){
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice && LiveVoice.stop) LiveVoice.stop(); } catch (e) {}
  try { completeChatSession('out_of_points'); } catch (e) {}
  try { chatOpened = false; } catch (e) {}
  try { setCallToggle(false); } catch (e) {}
  stopCallTimer();
  __muneaShowPointsPopup();
}
function __muneaFreeChatOut__setCool() { try { localStorage.setItem('munea.reviewCoolOff', '1'); setTimeout(() => localStorage.removeItem('munea.reviewCoolOff'), 3600000); } catch (e) {} }
function __muneaFreeChatOut(){ __muneaFreeChatOut__setCool();
  try { if (typeof LiveVoice !== 'undefined' && LiveVoice && LiveVoice.stop) LiveVoice.stop(); } catch (e) {}
  try { completeChatSession('free_signup_trial_exhausted'); } catch (e) {}
  try { chatOpened = false; } catch (e) {}
  try { setCallToggle(false); } catch (e) {}
  stopCallTimer();
  toast(muneaT('credits.freeTrialEnded', '免費帳號的一次性 5 分鐘體驗已用完'));
  try { FaceIdle.start(); } catch (e) {}   // 收線後回到待機輪播
  if (window.MMPLAN) window.MMPLAN.upsell('chat-daily');
}
function startCallTimer() {
  stopCallTimer(); _callSec = 0;
  const el = $('#callTimer');
  _callTimerInt = setInterval(() => {
    callBudgetTick();
    if (window.MMPLAN && window.MMPLAN.isFree()) {
      window.MMPLAN.chatTick();
      const _rem = window.MMPLAN.chatRemainSec();
      // 快到了先溫柔預告（剩 1 分鐘）：畫面提示＋悄悄請角色自然收尾，不再無預警斷線
      if (_rem > 0 && _rem <= 60 && !_freeWarned) {
        _freeWarned = true;
        toast(muneaT(
          'credits.freeTrialOneMinute',
          '免費體驗剩約 1 分鐘，慢慢說完沒關係。',
        ));
        try {
          if (LiveVoice && LiveVoice.on && LiveVoice.ws && LiveVoice.ws.readyState === 1) {
            LiveVoice.ws.send(JSON.stringify({ type: 'text', text: '（系統悄悄話，請不要唸出這段、也不要提到系統或倒數：免費體驗只剩大約一分鐘，請自然地把話題暖心收尾，溫柔說今天先聊到這。）' }));
          }
        } catch (e) {}
      }
      if (_rem <= 0) { __muneaFreeChatOut(); return; }
    }
    _callSec++;
    const m = String(Math.floor(_callSec / 60)).padStart(2, '0');
    const s = String(_callSec % 60).padStart(2, '0');
    if (el) el.textContent = m + ':' + s;
  }, 1000);
}
function stopCallTimer() {
  _lowWarned = false; _zeroSaid = false; _freeWarned = false; _brainDegraded = false; if (_callTimerInt) { clearInterval(_callTimerInt); _callTimerInt = null; } const el = $('#callTimer'); if (el) el.textContent = '00:00'; }
// 字幕（逐字稿）預設「關」——依產品規劃，聊聊像視訊通話、只留必要狀態；字幕是給重聽長輩的可選輔助。
let captionsOn = false;
try { captionsOn = localStorage.getItem('munea.captions') === '1'; } catch (e) {}
function applyCaptionState() {
  const b = document.getElementById('captionToggle');
  const chat = document.getElementById('chat');
  if (b) { b.classList.toggle('off', !captionsOn); b.setAttribute('aria-pressed', captionsOn ? 'true' : 'false'); }
  if (chat) chat.classList.toggle('captions-on', captionsOn);
  if (!captionsOn) { const box = document.querySelector('.face-caption-box'); if (box) box.remove(); }
}
function localizeChatControls() {
  const captions = document.getElementById('captionToggle');
  const captionsLabel = captions && captions.querySelector('span');
  if (captionsLabel) captionsLabel.textContent = muneaT('voice.caption.label', '字幕');
  if (captions) captions.setAttribute('aria-label', muneaT('accessibility.toggleCaptions', '字幕開關'));

  const microphone = document.getElementById('chatMic');
  const microphoneLabel = microphone && microphone.querySelector('span');
  if (microphoneLabel) microphoneLabel.textContent = muneaT('voice.microphone.label', '麥克風');
  if (microphone) microphone.setAttribute('aria-label', muneaT('accessibility.toggleMicrophone', '麥克風開關'));

  // 通話鍵的字（2026-08-01）：它原本掛 data-i18n="voice.call.start"，於是通話中程式改成
  // 「掛斷」之後，巡邏的翻譯層會把它打回「開始通話」——正在通話的人看到一顆寫著
  // 「開始通話」的鍵。標籤拿掉了，換語言就由這裡重畫，並且要照當下是不是在通話講對的字。
  const callLabel = document.getElementById('callToggleLabel');
  if (callLabel && typeof callDialing !== 'undefined' && !callDialing) {
    callLabel.textContent = (typeof callConnected !== 'undefined' && callConnected)
      ? muneaT('voice.call.end', '掛斷')
      : muneaT('voice.call.start', '開始通話');
  }
}
function setCaption(text, hint) {
  if (!captionsOn) return;                 // 字幕關閉時不顯示逐字稿
  let box = document.querySelector('.face-caption-box');
  if (!box) {
    box = document.createElement('div');
    box.className = 'face-caption-box';
    document.getElementById('chat')?.appendChild(box);
  }
  box.innerHTML = text + (hint ? '<small>' + hint + '</small>' : '');
}

let _toastTimer = null;
// 每台裝置一個身份、每個家庭一個編號：同步時帶上，別人家的動態不會混進來（真帳號上線後改綁帳號）
function muneaDeviceId() {
  try {
    let d = localStorage.getItem('munea.deviceId');
    if (!d) { d = 'dev-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36); localStorage.setItem('munea.deviceId', d); }
    return d;
  } catch (e) { return 'dev-anon'; }
}
function famGroupId() {
  try {
    let g = localStorage.getItem('munea.familyGroupId');
    if (!g) { g = 'fam-' + muneaDeviceId(); localStorage.setItem('munea.familyGroupId', g); }
    return g;
  } catch (e) { return 'fam-anon'; }
}
function myFeedName() { try { const p2 = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); return (p2.nick || p2.name || '').trim() || '家人'; } catch (e) { return '家人'; } }
function myProfileName() {
  try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); return (p.name || p.nick || '').trim(); } catch (e) { return ''; }
}
const _syncPushTimers = new Map();
const _syncPushBodies = new Map();
const _syncPushLastSent = new Map();
let _syncPullPromise = null;
let _syncPullCompletedAt = 0;
let _familySyncTimer = null;
let _familyVisibilityBound = false;
let _lastPlanRecheckAt = 0;   // 回前景重新確認會員身分的節流時間戳
function syncPush(key, value) {
  if (isDeveloperBypassAllowed()) return;
  try {
    // 用藥照片只留本機、不上雲（隱私修正 7/9）：meds 同步前把 base64 照片欄位剝掉，其餘欄位照送
    const payload = (key === 'meds' && Array.isArray(value))
      ? value.map(m => { const rest = Object.assign({}, m); delete rest.photo; return rest; })
      : value;
    const body = JSON.stringify({ action: 'save', key, value: payload, familyGroupId: famGroupId(), personId: muneaCloudPersonId() });
    const previous = _syncPushLastSent.get(key);
    if (previous && previous.body === body && Date.now() - previous.at < 30000) return;
    _syncPushBodies.set(key, body);
    if (_syncPushTimers.has(key)) clearTimeout(_syncPushTimers.get(key));
    _syncPushTimers.set(key, setTimeout(() => {
      _syncPushTimers.delete(key);
      const pendingBody = _syncPushBodies.get(key);
      _syncPushBodies.delete(key);
      if (!pendingBody) return;
      muneaAuthHeaders({ 'Content-Type': 'application/json' }).then(headers => {
        fetch(brainURL('/family/state'), { method: 'POST', headers, body: pendingBody })
          .then(response => { if (response.ok) _syncPushLastSent.set(key, { body: pendingBody, at: Date.now() }); })
          .catch(() => {});
      }).catch(() => {});
    }, 350));
  } catch (e) {}
}
function syncPullAll(options) {
  if (isDeveloperBypassAllowed()) return;
  const opts = options || {};
  const minIntervalMs = Number.isFinite(opts.minIntervalMs) ? opts.minIntervalMs : 30000;
  if (!opts.force && typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
  if (_syncPullPromise) return _syncPullPromise;
  if (!opts.force && Date.now() - _syncPullCompletedAt < minIntervalMs) return Promise.resolve();
  _syncPullPromise = (async () => {
   try {
    const r = await fetch(brainURL('/family/state'), { method: 'POST', headers: await muneaAuthHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ action: 'load', familyGroupId: famGroupId() }) });
    if (!r.ok) return;
    const st = (await r.json()).state || {};
    const map = { activities: 'munea.activities', familyFeed: 'munea.familyFeed2', meds: 'munea.meds', visit: 'munea.visit', visits: 'munea.visits', routine: 'munea.routine', vitals: 'munea.famVitals' };
    for (const k in map) {
      if (st[k] !== undefined && st[k] !== null) {
        try { localStorage.setItem(map[k], JSON.stringify(st[k])); } catch (e) {}
      }
    }
    const ownVitals = st.vitals && st.vitals[muneaCloudPersonId()];
    if (ownVitals && ownVitals.log && typeof ownVitals.log === 'object') {
      const days = Object.keys(ownVitals.log).map(date => Object.assign({ date }, ownVitals.log[date] || {}));
      mergeHealthHistory(days, false);
    }
    // 圈名單同步（雲端不存「本人」標記，各裝置用自己的名字對回去）
    if (Array.isArray(st.circle) && st.circle.length) {
      try {
        const mine = myProfileName();
        const arr = st.circle.map(m => ({ name: m.name, personId: m.personId || m.id, relationship: m.relationship, init: m.init, tint: m.tint, self: !!mine && m.name === mine }));
        if (!arr.some(m => m.self)) {
          const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
          arr.unshift({ name: mine || p.nick || muneaT('common.meInitial', '我'), init: (p.nick || mine || muneaT('common.meInitial', '我'))[0], tint: 'p-ama', self: true });
        }
        localStorage.setItem('munea.circleMembers', JSON.stringify(muneaAssignTints(arr)));
        if (typeof window.__muneaAfterCircleSync === 'function') window.__muneaAfterCircleSync();
      } catch (e) {}
    }
    try { await refreshFamilyRelayMembers(); } catch (e) {}
    if (st.wallet && typeof st.wallet.used === 'number') {
      POINTS.used = st.wallet.used;
      try { localStorage.setItem('munea.ptsBought', String(st.wallet.bought || 0)); } catch (e) {}
    }
    if (typeof updateMedCount === 'function') updateMedCount();
    if (typeof renderPoints === 'function') renderPoints();
    if (typeof renderVisitRow === 'function') try { renderVisitRow(); } catch (e) {}
    renderCareCarousel();
   } catch (e) {
   } finally {
     _syncPullCompletedAt = Date.now();
     _syncPullPromise = null;
   }
  })();
  return _syncPullPromise;
}
function configureMedicationService() {
  if (!window.MuneaMedication) return Promise.resolve([]);
  const scope = isLoggedIn() ? muneaCloudPersonId() : 'guest';
  return window.MuneaMedication.configure({
    scope,
    meds: loadMeds,
    post: body => brainPost('/medication-doses', body),
  }).catch(() => []);
}
function handleMedicationChange(event) {
  const dose = event && event.detail ? event.detail : {};
  renderPillTask();
  if (typeof window.__muneaRefreshMedicationUi === 'function') window.__muneaRefreshMedicationUi();
  if (dose.status !== 'taken' || ['cloud-refresh', 'configured', 'schedule', 'legacy-import'].includes(dose.source)) return;
  trackProductEvent('routine_reminder_completed', {
    reminderType: 'medication',
    doseKey: dose.doseKey || '',
    source: dose.source || 'app',
  });
  // 家庭圈只分享服藥時段，不分享藥名，兼顧照護與用藥隱私。
  pushFamilyFeed('<b>' + myFeedName() + '</b>已記錄' + (dose.slot ? medSlotLabel(dose.slot) : '這次') + '服藥，' + cname() + '有看著');
}
// 真的連續按下「吃了」幾天（Edward 2026-08-02 送審前抓到）。
//
// 這格本來是無條件顯示、天數用「今天幾號減一」湊出來的——8/3 就說你連續 2 天準時吃藥。
// 剛下載的人連一顆藥都還沒設，第一次打開就被稱讚吃藥很規律，那是憑空捏造。
// 現在從今天往回數真的打勾紀錄；今天還沒吃不算中斷（早上打開 App 很正常）。
function realMedStreak() {
  try {
    const meds = JSON.parse(localStorage.getItem('munea.meds') || '[]');
    if (!Array.isArray(meds) || !meds.length) return 0;   // 藥都還沒設，沒有規律可言
    const dayHasDose = (d) => {
      try {
        const done = JSON.parse(localStorage.getItem('munea.medDone.' + isoOf(d)) || '{}');
        return !!done && Object.keys(done).some(k => done[k]);
      } catch (e) { return false; }
    };
    const cursor = new Date();
    if (!dayHasDose(cursor)) cursor.setDate(cursor.getDate() - 1);   // 今天還沒吃≠斷了
    let streak = 0;
    for (let i = 0; i < 60 && dayHasDose(cursor); i += 1) { streak += 1; cursor.setDate(cursor.getDate() - 1); }
    return streak;
  } catch (e) { return 0; }
}
function streakLine(n) {
  if (n >= 10) {
    return muneaT(
      'home.care.medicationStreakLong',
      'You took your medication on time {days} days this month. Great consistency—keep it up.',
      { days: n },
    );
  }
  if (n >= 3) {
    return muneaT(
      'home.care.medicationStreakMedium',
      'You took your medication on time {days} days this month. Your routine is taking shape.',
      { days: n },
    );
  }
  return muneaT(
    'home.care.medicationStreakStart',
    'You started tracking your medication. That is a good start.',
  );
}
const CARE_ICONS = {
  msg: '<svg class="ic" viewBox="0 0 24 24"><path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8z"/></svg>',
  walk: '<svg class="ic" viewBox="0 0 24 24"><path d="M13 4a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM8 21l3-6M14 21v-5l-2.5-3 1-5.5M8.5 9 11 6.5l2.5 1 2 3H18"/></svg>',
  cal: '<svg class="ic" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
  medal: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="6"/><path d="M15.5 12.9 17 22l-5-3-5 3 1.5-9.1"/></svg>',
  person: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4.5 21a7.5 7.5 0 0 1 15 0"/></svg>'
};
let _careIdx = 0, _careTimer = null;
// 留意卡文案規則（Edward 7/6）：標題 ≤12 字（一行放得下）、副標最多兩行（約 26 字內）完整顯示
function plain(s) { return String(s == null ? '' : s).replace(/<[^>]+>/g, ''); }
function localizedCareLabels(rendererCopy) {
  return rendererCopy
    ? rendererCopy.careLabels()
    : {
      acknowledge: muneaT('home.care.acknowledge', 'Got it'),
      open: muneaT('home.care.open', 'View'),
      remove: muneaT('home.care.remove', 'Remove this item'),
      report: muneaT('home.care.report', 'Report'),
    };
}
function buildCareItems() {
  const items = [];
  const rendererCopy = muneaRendererCopy();
  const careLabels = localizedCareLabels(rendererCopy);
  let feed = [];
  try { feed = JSON.parse(localStorage.getItem('munea.familyFeed2')) || []; } catch (e) {}
  // 這格顯示家人動態最新的一則，不再去猜「哪一則是傳話」（Edward 2026-07-31）。
  //
  // 舊寫法先用 /要我提醒你|帶話/ 撈出疑似傳話的那則，再拆成「誰」跟「說了什麼」——
  // 那是拿畫面上的中文句子反推資料：文案改一個字就撈不到，換成英日西整條認不出來。
  // 真的傳話現在由上面那張卡直接跟雲端拿、也不走這裡了，這格回歸它本來的工作：
  // 就是把動態牆最新的一則好好唸出來。少一套猜法，就少一個會在四語上線後爆掉的地方。
  const feedTop = feed.length ? feed[0] : null;
  // 標題用中性的「家人的動態」，不再寫「家人帶話給你」——這格唸的可能是按讚、走路活動、
  // 家庭記錄簿結算，寫「帶話」會讓人以為有留言沒看到。真的帶話在上面那張卡。
  let _rTitle = muneaT('home.care.familyFeedTitle', 'From your family');
  let _rSub = '', _relayClean = false;
  if (feedTop) {
    // 留意卡是首頁會轉動輪播的位置、比招呼卡更容易被看到——原文一律要過守門才能顯示
    // （Edward 2026-07-15 事故：這裡漏接、招呼卡另一條路徑已守）
    const _safe = muneaSafeDisplayText(plain(feedTop), '');
    if (_safe) { _rSub = _safe; _relayClean = true; }
  }
  // 蘋果 UGC 審核要求（7/9）：這則若真的來自家人 feed（傳話/愛心/塗鴉…），記下它在陣列裡的位置，卡片才能掛「移除／檢舉」；示範文案（feed 是空的）不算數
  const _feedIdx = feed.length ? 0 : -1;
  const _feed0Safe = feed[0] ? muneaSafeDisplayText(plain(feed[0]), '') : '';
  const defaultRelay = rendererCopy
    ? rendererCopy.familyRelay({ body: _feed0Safe, companion: cname() })
    : null;
  // 上面那張卡正在轉達真的家人帶話時，這裡就不要再講一次同一件事（Edward 2026-07-31）——
  // 一件事在同一個畫面出現兩遍，看的人會以為有兩則留言。
  const _relayOnButlerCard = !!(typeof _muneaHomeRelay !== 'undefined' && _muneaHomeRelay);
  const familyItem = _relayClean
    ? { k: 'family', tone: '', icon: 'msg', title: _rTitle, sub: _rSub, btn: careLabels.acknowledge, feedIdx: _feedIdx }
    : {
      k: 'family',
      tone: '',
      icon: 'msg',
      title: _rTitle,
      sub: defaultRelay
        ? defaultRelay.body
        : (_feed0Safe || muneaT(
          'home.care.demoRelay',
          'Your family says they will visit this weekend. {companion} saved the message for you.',
          { companion: cname() },
        )),
      btn: careLabels.open,
      feedIdx: _feedIdx,
    };
  let acts = [];
  try { acts = JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) {}
  const act = acts.find(a => a && !a.done && !a.archived);
  if (act && (act.type === 'walk' || /走|步/.test(act.title || ''))) {
    const goal = +(act.steps || act.goal || 8000);
    const gap = Math.max(0, goal - (+(act.mySteps || act.progress || 3000)));
    const owner = muneaSafeDisplayText(act.owner, '')
      || muneaT('home.care.familyFallback', 'Family');
    const localized = rendererCopy
      ? rendererCopy.walkActivity({ gap, owner })
      : null;
    items.push({
      k: 'family',
      tone: 'coral',
      icon: 'walk',
      title: localized
        ? localized.title
        : muneaT('home.care.walkTitle', '{name} started a walking activity', { name: owner }),
      sub: localized
        ? localized.body
        : gap > 0
          ? muneaT('home.care.walkGap', '{count} steps to go. Shall we take a walk tonight?', { count: Math.ceil(gap) })
          : muneaT('home.care.walkComplete', 'Goal reached. See how everyone did.'),
      btn: careLabels.open,
    });   // 活動發起人／標題守門（Edward 2026-07-15 事故）
  } else if (act) {
    const owner = muneaSafeDisplayText(act.owner, '')
      || muneaT('home.care.familyFallback', 'Family');
    const title = muneaSafeDisplayText(act.title, '')
      || muneaT('home.care.activityFallback', 'Family activity');
    const localized = rendererCopy
      ? rendererCopy.familyActivity({
        owner,
        title,
      })
      : null;
    items.push({
      k: 'family',
      tone: 'coral',
      icon: 'walk',
      title: localized
        ? localized.title
        : muneaT('home.care.activityTitle', '{name} started an activity', { name: owner }),
      sub: localized
        ? localized.body
        : muneaT('home.care.activityProgress', '“{title}” is in progress. See how everyone is doing.', { title }),
      btn: careLabels.open,
    });
  } else if (false) {
    // 這裡本來在「一個活動都沒有」的時候，硬塞一張寫死的示範卡：
    // 「家人發起的走路活動，還差 5000 步就達標」——但新使用者根本還沒有家人、
    // 也沒有任何活動。第一次打開 App 就看到一件沒發生的事，那是在騙人
    //（Edward 2026-08-02 送審前抓到：「確認剛下載登入的用戶沒有任何假資料」）。
    // 保留這段只是留個痕跡，永遠不會執行；真的沒活動就什麼都不推。
    const owner = muneaT('home.care.familyFallback', 'Family');
    const localized = rendererCopy
      ? rendererCopy.walkActivity({ gap: 5000, owner })
      : null;
    items.push({
      k: 'family',
      tone: 'coral',
      icon: 'walk',
      title: localized
        ? localized.title
        : muneaT('home.care.walkTitle', '{name} started a walking activity', { name: owner }),
      sub: localized
        ? localized.body
        : muneaT('home.care.walkGap', '{count} steps to go. Shall we take a walk tonight?', { count: 5000 }),
      btn: careLabels.open,
    });
  }
  // 動態牆是空的（新使用者、或家人還沒做任何事）就不要推這格——
  // 它的備援文案是「家人說週末回去看你」，那是示範句子，不是真的有人這樣說
  //（Edward 2026-08-02 送審前抓到）。沒有內容就安靜，不要編一則家人的消息給他看。
  if (!_relayOnButlerCard && _relayClean) items.push(familyItem);
  let v = null;
  try {
    let arr = JSON.parse(localStorage.getItem('munea.visits') || 'null');
    if (!Array.isArray(arr)) { const old = JSON.parse(localStorage.getItem('munea.visit') || 'null'); arr = (old && old.dateISO) ? [old] : []; }
    const today = isoOf(new Date());
    v = arr.filter(x => x && x.dateISO && x.dateISO >= today).sort((a, b) => a.dateISO.localeCompare(b.dateISO))[0] || null;
  } catch (e) {}
  if (v && v.dateISO) {
    const _vTitle = muneaSafeDisplayText(v.title, '')
      || muneaSafeDisplayText(v.label, '')
      || muneaT('home.care.visitFallback', 'Appointment');
    const visitDate = v.label || String(v.dateISO).slice(5).replace('-', '/');
    const localized = rendererCopy
      ? rendererCopy.upcomingVisit({
        companion: cname(),
        date: visitDate,
        title: _vTitle,
      })
      : null;
    items.push({
      k: 'status',
      tone: '',
      icon: 'cal',
      title: localized
        ? localized.title
        : muneaT('home.care.visitSoon', '{title} is coming up', { title: _vTitle }),
      sub: localized
        ? localized.body
        : muneaT(
          'home.care.visitNote',
          '{date} · {companion} saved what you want to ask the doctor.',
          { companion: cname(), date: visitDate },
        ),
      btn: careLabels.open,
    });
  }   // 留意卡看診快到了標題守門（Edward 2026-07-15 事故）
  // 真的有連續打勾才講——沒設藥、沒吃過就不要稱讚一個沒發生的習慣（Edward 2026-08-02）
  const _medStreak = realMedStreak();
  if (_medStreak >= 1) items.push({ k: 'status', tone: 'gold', icon: 'medal', title: muneaT('home.care.medicationRhythm', 'Your medication routine is on track'), sub: plain(streakLine(_medStreak)) });
  // 個人資料提醒（2026-07-28 Edward 拍板：從首頁那張趕不走的獨立小卡搬進來）：還沒填才插在第一則，
  // 一填完自動不再出現；輪播 5.2 秒會自己轉走＝天生不強迫，所以這則不配關閉鈕。
  // 標題刻意不放 AI 名字（Edward 2026-07-28 拍板：原本的「◯◯想更認識你」太煽情，改中性敘述）；
  // 7/29 再收成「個人資料」——「用戶」是產品人的詞、長輩不會這樣自稱，且這四個字跟設定頁入口、
  // 點下去開的那張卡標題完全一致，使用者一路看到的是同一個名字。
  // 附帶好處：固定 4 字＝完全不受名字長度影響，繞開了原本兩道會咬字的關卡——
  // 渲染時的 slice(0,12) 硬切（沒補刪節號）、以及 .care-txt p 的單行 ellipsis（375px 下約 10 字到底）。
  if (shouldShowProfileNudge()) {
    const localized = rendererCopy ? rendererCopy.profilePrompt() : null;
    items.unshift({
      k: 'profile',
      tone: '',
      icon: 'person',
      title: localized
        ? localized.title
        : muneaT('home.profilePromptTitle', 'Personal profile'),
      sub: localized
        ? localized.body
        : muneaT(
          'home.profilePromptBody',
          'Add your preferred name, birthday, and location for more natural greetings and accurate weather.',
        ),
      btn: localized
        ? localized.action
        : muneaT('home.profilePromptAction', 'Update'),
    });
  }
  return items;
}
function renderCareCarousel() {
  const body = document.getElementById('careBody');
  const dots = document.getElementById('careDots');
  if (!body || !dots) return;
  const rendererCopy = muneaRendererCopy();
  const careLabels = localizedCareLabels(rendererCopy);
  const items = buildCareItems();
  // 什麼都沒有的時候（剛下載、還沒設藥、還沒加家人）就誠實說沒有，
  // 不要編一則假消息填滿版面（Edward 2026-08-02）。這句同時告訴他這格之後會裝什麼。
  if (!items.length) {
    body.innerHTML = '<div class="care-item on" data-k="empty">' +
      '<span class="care-ico">' + CARE_ICONS.msg + '</span>' +
      '<div class="care-txt"><p>' + muneaT('home.care.emptyTitle', '目前沒有要提醒你的事') + '</p>' +
      '<small>' + muneaT('home.care.emptyBody', '設好用藥、看診，或把家人加進來，這裡就會幫你留意') + '</small></div>' +
      '</div>';
    dots.innerHTML = '';
    if (_careTimer) { clearInterval(_careTimer); _careTimer = null; }
    return;
  }
  body.innerHTML = items.map((it, i) =>
    '<div class="care-item' + (i === 0 ? ' on' : '') + '" data-k="' + it.k + '">' +
    '<span class="care-ico ' + it.tone + '">' + CARE_ICONS[it.icon] + '</span>' +
    '<div class="care-txt"><p>' + it.title + '</p>' + (it.sub ? '<small>' + it.sub + '</small>' : '') +
    (typeof it.feedIdx === 'number' && it.feedIdx > -1 ? '<div class="care-mod"><button type="button" class="care-mod-btn" data-remove="' + it.feedIdx + '">' + careLabels.remove + '</button><button type="button" class="care-mod-btn" data-report="' + it.feedIdx + '">' + careLabels.report + '</button></div>' : '') +
    '</div>' +
    (it.btn ? '<button type="button" class="care-btn" data-go="' + it.k + '">' + it.btn + '</button>' : '') +
    '</div>').join('');
  dots.innerHTML = items.map((_, i) => '<i class="' + (i === 0 ? 'on' : '') + '"></i>').join('');
  _careIdx = 0;
  if (_careTimer) clearInterval(_careTimer);
  _careTimer = setInterval(() => careAdvance(1), 5200);
  // 首輪起轉延後 1.4 秒：讓進場動畫先走完、不疊影
  clearInterval(_careTimer);
  _careTimer = null;
  setTimeout(() => { if (!_careTimer) _careTimer = setInterval(() => careAdvance(1), 5200); }, 1400);
}
function careAdvance(step) {
  const its = document.querySelectorAll('#careBody .care-item');
  const dots = document.querySelectorAll('#careDots i');
  if (!its.length) return;
  its[_careIdx].classList.remove('on');
  if (dots[_careIdx]) dots[_careIdx].classList.remove('on');
  _careIdx = (_careIdx + step + its.length) % its.length;
  its[_careIdx].classList.add('on');
  if (dots[_careIdx]) dots[_careIdx].classList.add('on');
}
function loadFeed() {
  try { const a = JSON.parse(localStorage.getItem('munea.familyFeed2')) || []; return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function pushFamilyFeed(text) {
  const a = loadFeed();
  a.unshift(text);
  while (a.length > 3) a.pop();
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  renderCareCarousel();
}
function restoreFamilyFeed() { renderCareCarousel(); }
// 蘋果 UGC 審核要求（7/9）：家人動態/傳話/塗鴉要能「移除」「檢舉」——都是真動作，不是假成功
function removeFamilyFeedItem(idx) {
  const a = loadFeed();
  if (idx < 0 || idx >= a.length) return;
  a.splice(idx, 1);
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  renderCareCarousel();
  toast(muneaT('notification.removedToast', "已經移除這則了"));
}
function reportFamilyFeedItem(idx) {
  const a = loadFeed();
  if (idx < 0 || idx >= a.length) return;
  const content = plain(a[idx]);
  try {
    const log = JSON.parse(localStorage.getItem('munea.feedReported') || '[]');
    log.unshift({ text: content, at: Date.now() });
    localStorage.setItem('munea.feedReported', JSON.stringify(log.slice(0, 50)));
  } catch (e) {}
  // 真的送進引擎既有的意見收件箱（會叮 #munea-營運、進 /admin/feedback 清單），不是假送出
  brainPost('/feedback', { type: 'bug', category: '檢舉動態', text: '【檢舉家人動態】' + content, appVersion: (window.MuneaVersion && window.MuneaVersion.current) || '', plan: (window.MMPLAN && window.MMPLAN.get()) || '' });
  a.splice(idx, 1);
  try { localStorage.setItem('munea.familyFeed2', JSON.stringify(a)); } catch (e) {}
  syncPush('familyFeed', a);
  renderCareCarousel();
  toast(muneaT('notification.reportedToast', "已收到，我們會處理；這則也先收起來了"));
}

function toast(text, duration = 2600) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = text;
  t.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), duration);
}

// 版本顯示 + 「版本更新」彈窗（讀 window.MuneaVersion 這個單一真相）
function applyAppVersion() {
  const V = window.MuneaVersion; if (!V) return;
  const n = document.getElementById('verRowNum'); if (n) n.textContent = V.current;
  const subtitle = document.getElementById('versionSubtitle');
  if (subtitle) subtitle.textContent = muneaT(
    'settings.versionReleaseNotes',
    '版本 {version} · 看更新內容',
    { version: V.current },
  );
}
function openVersionSheet() {
  const V = window.MuneaVersion || { current: '—', channel: '', changelog: [] };
  const cur = document.getElementById('verCurrent'); if (cur) cur.textContent = V.current;
  const ch = document.getElementById('verChannel'); if (ch) ch.textContent = V.channel || '';
  const list = document.getElementById('changelogList');
  if (list) {
    list.innerHTML = (V.changelog || []).map(rel =>
      '<div class="cl-rel"><div class="cl-head"><b>v' + rel.version + '</b>' +
      (rel.title ? '<span class="cl-title">' + rel.title + '</span>' : '') +
      '<span class="cl-date">' + (rel.date || '') + '</span></div><ul>' +
      (rel.items || []).map(i => '<li>' + i + '</li>').join('') + '</ul></div>'
    ).join('');
  }
  const m = document.getElementById('versionSheet'); if (m) m.classList.add('show');
  localizeCanonicalLegacyPanels();
}

// ===== 健康頁：分層排版（今日總結＋想提醒你＋都很穩）· 對應「健康照護-數據告警AI提醒-設計」=====
// [ENGINE] 正式版：值/燈號由守護腦判定＋真 Apple 健康帶入；read 由管家腦生成。
const METRIC_ICON = {
  bp:     '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/><path d="M3.2 12H9l.5-1 2 4.5 2-7 1.5 3.5h5.3"/>',
  hr:     '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  spo2:   '<path d="M12 3s6 6 6 11a6 6 0 0 1-12 0c0-5 6-11 6-11z"/>',
  steady: '<path d="M13 4a2 2 0 1 0 0 0M8 21l2-6 3 2 1 4M14 11l-3-2-3 2-2 4M15 13l3 1"/>',
  sleep:  '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>',
  act:    '<path d="M4 16v-2.4c0-2.1-1-3.1-1-5.6 0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0Z"/>',
  med:    '<path d="M10.5 20.5 3.5 13.5a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7z"/><path d="M8.5 8.5l7 7"/>',
};
const HEALTH_METRICS = {
  bp:     { name: () => muneaT('health.bloodPressure', '血壓'), val: () => '128', unit: () => '/82', status: 'ok',   read: () => muneaT('demo.status.readBp', '這週血壓都很穩，維持得很好。'), trend: [126,130,128,124,128,127,128] },
  hr:     { name: () => muneaT('health.heartRate', '心率'), val: () => '72',  unit: () => ' ' + muneaT('health.unit.times', '次'), status: 'ok',   read: () => muneaT('demo.status.readHr', '心跳平穩，沒有不規則的狀況。'), trend: [70,72,71,73,72,70,72] },
  spo2:   { name: () => muneaT('health.bloodOxygen', '血氧'), val: () => '97',  unit: () => '%',   status: 'ok',   read: () => muneaT('demo.status.readSpo2', '血氧很足，呼吸順順的。'), trend: [97,98,97,96,97,97,97] },
  steady: { name: () => muneaT('health.walkSteadiness', '走路穩定度'), val: () => muneaT('health.low', '偏低'), unit: () => '', status: 'warn', read: () => muneaT('demo.status.readSteady', '這週走路穩定度有點降，走慢些、扶著點。要不要我提醒家人多留意？'), trend: [3,3,2,2,2,2,2] },
  sleep:  { name: () => muneaT('health.sleep', '睡眠'), val: () => '7.5', unit: () => ' ' + muneaT('health.unit.hours', '時'), status: 'ok',   read: () => muneaT('demo.status.readSleep', '睡得不錯，這週平均 7.4 小時。'), trend: [7.2,7.5,6.8,7.6,7.4,7.5,7.5] },
  act:    { name: () => muneaT('health.activity', '活動'), val: () => '20',  unit: () => ' ' + muneaT('health.unit.minutes', '分'), status: 'ok',   read: () => muneaT('demo.status.readAct', '今天有出門走走，很好；回來記得喝口水。'), trend: [12,18,9,20,15,22,20] },
  med:    { name: () => muneaT('medication.title', '用藥'), val: () => '2',   unit: () => '/3',  status: 'warn', read: () => muneaT('demo.status.readMed', '今天還剩 1 次沒吃，到時間我會叫你。'), trend: [1,1,1,0,1,1,1] },
};
const METRIC_ORDER = ['bp', 'hr', 'spo2', 'steady', 'sleep', 'act', 'med'];
const STATUS_WORD = { ok: () => muneaT('health.statusSteady', '穩'), warn: () => muneaT('health.attention', '注意'), alert: () => muneaT('health.statusCareful', '要小心') };
function metricSvg(key) { return '<svg class="ic" viewBox="0 0 24 24">' + (METRIC_ICON[key] || '') + '</svg>'; }
function renderHealthDashboard() {
  const dots = document.getElementById('heroDots'), focus = document.getElementById('focusList'), calm = document.getElementById('calmStrip');
  if (!dots || !focus || !calm) return;
  const warns = METRIC_ORDER.filter(k => HEALTH_METRICS[k].status !== 'ok');
  const oks = METRIC_ORDER.filter(k => HEALTH_METRICS[k].status === 'ok');
  // 寧寧的話隨時段變（招牌記憶點：像記得你的時間）
  const head = document.getElementById('thHead'), sub = document.getElementById('thSub');
  if (head && sub) {
    const h = new Date().getHours();
    const part = h < 11 ? muneaT('health.dashMorning', '早安，昨晚睡得不錯。') : h < 17 ? muneaT('health.dashAfternoon', '午後了，記得起來走走。') : muneaT('health.dashEvening', '今天辛苦了，早點歇著。');
    if (!warns.length) { head.textContent = muneaT('health.dashAllGoodTitle', '今天一切都好'); sub.textContent = muneaT('health.dashAllGoodSub', '{part}每一項我都看著，放心。', { part }); }
    else { head.textContent = muneaT('health.dashSteadyTitle', '今天大致都穩'); sub.textContent = muneaT('health.dashWatchSub', '{part}有 {count} 件事我幫你盯著。', { part, count: warns.length }); }
  }
  // HERO 燈號：短橫條（綠=穩會呼吸、珊瑚=注意恆亮）
  dots.innerHTML = METRIC_ORDER.map(k => '<i class="' + HEALTH_METRICS[k].status + '"></i>').join('');
  // 想請你留意：大卡
  focus.innerHTML = warns.map(k => {
    const m = HEALTH_METRICS[k];
    return '<button class="focus-card ' + m.status + '" type="button" data-metric="' + k + '">' +
      '<span class="fc-ico">' + metricSvg(k) + '</span>' +
      '<div class="fc-body"><div class="fc-top"><b>' + m.name() + '</b><span class="fc-val">' + m.val() + '<small>' + m.unit() + '</small></span></div>' +
      '<div class="fc-read">' + m.read() + '</div></div>' +
      '<span class="fc-chev"><svg class="ic" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></span></button>';
  }).join('');
  // 其他都很穩：安靜清單列
  calm.innerHTML = oks.map(k => {
    const m = HEALTH_METRICS[k];
    return '<button class="calm-row" type="button" data-metric="' + k + '">' +
      '<span class="cr-ico">' + metricSvg(k) + '</span>' +
      '<span class="cr-name">' + m.name() + '</span>' +
      '<span class="cr-val">' + m.val() + '<small>' + m.unit() + '</small></span>' +
      '<span class="cr-dot"></span></button>';
  }).join('');
}
function renderMetricDetail(key) {
  const box = document.getElementById('metricDetail');
  if (!box) return;
  document.querySelectorAll('#status [data-metric]').forEach(t => t.classList.toggle('open', t.dataset.metric === key));
  if (box.dataset.open === key) { box.hidden = true; box.dataset.open = ''; document.querySelectorAll('#status [data-metric]').forEach(t => t.classList.remove('open')); return; }
  const m = HEALTH_METRICS[key];
  if (!m) { box.hidden = true; return; }
  const max = Math.max(...m.trend), min = Math.min(...m.trend);
  const bars = m.trend.map((v, i) => {
    const h = max === min ? 60 : 22 + Math.round((v - min) / (max - min) * 58);
    return `<i style="height:${h}%" class="${i === m.trend.length - 1 ? 'now' : ''}"></i>`;
  }).join('');
  const days = [muneaT('mood.weekdayShortMon', '一'), muneaT('mood.weekdayShortTue', '二'), muneaT('mood.weekdayShortWed', '三'), muneaT('mood.weekdayShortThu', '四'), muneaT('mood.weekdayShortFri', '五'), muneaT('mood.weekdayShortSat', '六'), muneaT('mood.weekdayShortSun', '日')];
  box.innerHTML =
    `<div class="md-head"><b>${muneaT('health.metricWeekTitle', '{name} · 這週', { name: m.name() })}</b><span class="md-status ${m.status}">${STATUS_WORD[m.status]()}</span></div>` +
    `<div class="md-chart">${bars}</div>` +
    `<div class="md-days">${days.map(d => '<span>' + d + '</span>').join('')}</div>` +
    `<div class="md-read"><span class="md-face"><img src="avatars/nening-v2-face.png" alt=""></span><span>${m.read()}</span></div>`;
  box.hidden = false; box.dataset.open = key;
  try { box.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
}
function initHealthDashboard() {
  renderHealthDashboard();
  const status = document.getElementById('status');
  if (status) status.addEventListener('click', e => {
    const el = e.target.closest('.focus-card[data-metric], .calm-row[data-metric]');
    if (el) renderMetricDetail(el.dataset.metric);
  });
}

// [ENGINE] 原型用瀏覽器內建語音；正式版換中文（台灣）/英文語音接點
function cname() {
  try {
    // 使用者沒自己取過名字時，一律現查當下語言的預設名——不能用開頁那一刻存下來的。
    // 2026-08-01：companionDisplayName 是在載入時就定住的，那一刻語言檔往往還沒讀完，
    // 於是英文／西班牙文使用者會看到中文的「寧寧」夾在句子中間
    // （例：「Your family says they'll visit this weekend. 寧寧 saved the message for you.」）。
    // 自己取過名字的人不受影響——那是他選的字，不該被語言蓋掉。
    if (!companionNameTouched) {
      const live = String((CompanionProfile.templateFor(currentAvatarId) || {}).defaultName || '').trim();
      if (live) return live;
    }
    return (companionDisplayName || muneaT('companion.nening.name', '寧寧')).trim() || muneaT('companion.nening.name', '寧寧');
  } catch (e) { return muneaT('companion.nening.name', '寧寧'); }
}
function hint(text) {
  // 聊聊以外不出聲（只出文字提示，禁止在此接語音）（2026-07-03 Edward 拍板）：只顯示提示
  toast(text);
}
function speakChat(text) {
  // 寧寧只用她本人的聲音（真語音 playB64）。沒有真聲音時，絕不用系統的機械聲代打——
  // 改用一則輕量文字提示，不破壞「是寧寧在講話」的感覺。
  toast(text);
}

// 今天一起完成：打勾 → 寧寧鼓勵（不是賺幣，是被看見）
const CHEERS = {
  pill: () => muneaT('home.cheer.pill', '藥吃了，你真棒，我幫你記到存摺裡，家人也看得到。'),
  visit: () => muneaT('home.cheer.visit', '回診辛苦了，醫生說的我幫你記著，回家歇一下。'),
  event: () => muneaT('home.cheer.event', '這個約赴完了吧？跟喜歡的人吃頓飯最好了，回來跟我說說。'),
  walk: () => muneaT('home.cheer.walk', '出去走走最好了，回來記得喝口水。'),
  chat: () => muneaT('home.cheer.chat', '謝謝你跟我說這些，我都記下來了。'),
  mood: () => muneaT('home.cheer.mood', '今天的心情記好了，謝謝你願意照顧自己的感受。'),
};
function refreshMoodTask() {
  const item = document.querySelector('.task-item[data-task="mood"]');
  if (!item) return;
  const done = !!(window.MM && typeof window.MM.hasSelfReportToday === 'function' && window.MM.hasSelfReportToday());
  item.classList.toggle('done', done);
  const sub = document.getElementById('moodTaskSub');
  const chip = document.getElementById('moodTaskChip');
  if (sub) sub.textContent = done
    ? muneaT('home.taskMoodDone', '今天的心情已記錄')
    : muneaT('home.taskMoodBody', '記錄今天的心情');
  if (chip) chip.textContent = done
    ? muneaT('home.taskDone', '完成')
    : muneaT('home.taskAnytime', '隨時');
  refreshTaskProgress();
}
window.__muneaMoodRecorded = function () { refreshMoodTask(); };
window.__muneaPostMood = function (body) { return brainPost('/wellbeing/log', body || {}); };
window.__muneaPullMood = function (body) { return brainPost('/wellbeing/recent', body || { limit: 400 }); };
function refreshTaskProgress() {
  const items = $$('#taskCard .task-item').filter(i => i.style.display !== 'none');
  const done = items.filter(i => i.classList.contains('done')).length;
  const tp = document.querySelector('.task-progress');
  if (tp) tp.classList.toggle('full', done === items.length && items.length > 0);
  if (done === items.length && items.length && !window.__celebrated) {
    window.__celebrated = true;
    setTimeout(() => toast(muneaT('home.allTasksDoneToast', '今天{count}件都完成了，我跟家人說一聲', { count: items.length })), 250);
    if (typeof pushFamilyFeed === 'function') pushFamilyFeed('<b>' + myFeedName() + '</b>今天把該做的都完成了，給他一個讚');
  }
  const pillTask = document.querySelector('.task-item[data-task="pill"]');
  const pv = $('#statPillVal');
  const pdone = pillTask && pillTask.classList.contains('done');
  const medSummary = window.MuneaMedication ? window.MuneaMedication.daySummary(pillDateKey(), loadMeds()) : null;
  const medTaken = medSummary ? medSummary.taken : (pdone ? 3 : 2);
  const medExpected = medSummary ? medSummary.expected : 3;
  if (pv && pillTask) pv.innerHTML = medTaken + '<small>/' + medExpected + '</small>';
  const dots = document.querySelectorAll('#pillDots i');
  if (dots.length) dots.forEach((d2, i2) => d2.classList.toggle('f', i2 < medTaken));
  const hint = $('#statPillHint');
  if (hint) { const remaining = Math.max(0, medExpected - medTaken); hint.textContent = remaining ? muneaT('medication.remainingCount', '剩 {count} 次', { count: remaining }) : muneaT('medication.allTaken', '都吃了'); hint.className = 'st-trend ' + (remaining ? 'warn' : 'ok'); }
  const prog = $('.task-progress');
  if (!prog) return;
  const label = prog.childNodes[prog.childNodes.length - 1];
  if (label) label.textContent = ` ${done} / ${items.length}`;
  const bar = prog.querySelector('.bar i');
  if (bar) bar.style.width = items.length ? `${Math.round(done / items.length * 100)}%` : '0%';
}

let _uncheckArm = null;
function toggleTask(item) {
  if (item.dataset.task === 'pill' && window.MuneaMedication) {
    if (item.classList.contains('done')) {
      // 防手抖：完成整天用藥後，第二次確認才取消最後一筆。
      if (_uncheckArm === item) {
        _uncheckArm = null;
        window.MuneaMedication.undoLast(loadMeds(), 'home-undo');
        toast(muneaT('medication.undoLastDose', '好，已取消最後一筆服藥紀錄。'));
      } else {
        _uncheckArm = item;
        toast(muneaT('medication.allDoneUndoHint', "今天的藥已完成，再按一次才會取消最後一筆。"));
        setTimeout(() => { if (_uncheckArm === item) _uncheckArm = null; }, 3000);
      }
      return;
    }
    window.MuneaMedication.markNext(loadMeds(), 'home');
    return;
  }
  // 看診任務：點開＝就診摘要，不是打勾（M1 PR-4c）。長輩按小勾勾很難按；
  // 「看完醫生了」要順手把口袋問題標記問過，那在摘要頁底部用大按鈕做。
  if (item.dataset.task === 'visit') {
    if (typeof openVisitSummary === 'function') openVisitSummary('daily-task');
    return;
  }
  if (item.dataset.task === 'mood') {
    showView('status');
    try { if (window.MM && typeof window.MM.renderMood === 'function') window.MM.renderMood('today'); } catch (e) {}
    setTimeout(() => {
      const card = document.getElementById('moodCheckinCard');
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
    return;
  }
  if (item.classList.contains('done')) {
    // 防手抖：取消「已完成」要按兩次（第一次只提示、3 秒內再按才真的取消）
    if (_uncheckArm === item) {
      _uncheckArm = null;
      item.classList.remove('done');
      refreshTaskProgress();
      toast(muneaT('medication.cancelDoseToast', '好，先取消這筆，等等再完成也可以。'));
    } else {
      _uncheckArm = item;
      toast(muneaT('home.taskDoneUndoHint', "這件已經完成了，再按一次才會取消。"));
      setTimeout(() => { if (_uncheckArm === item) _uncheckArm = null; }, 3000);
    }
    return;
  }
  item.classList.add('done');
  refreshTaskProgress();
  hint(CHEERS[item.dataset.task] ? CHEERS[item.dataset.task]() : muneaT('home.taskCheerDefault', '做得很好。'));
}

// 心情圖譜 v2（六類）；之後接 /wellbeing/trend 真資料
const MOODS = {
  happy:  { label: () => muneaT('mood.happy', '開心'), bg: '#FBE7D2', fg: '#C25716', face: 'M9 10h.01M15 10h.01M8 14s1.5 2.5 4 2.5 4-2.5 4-2.5' },
  glad:   { label: () => muneaT('mood.glad', '愉快'), bg: '#F6ECD4', fg: '#9A6E14', face: 'M9 10h.01M15 10h.01M8.5 14.5s1.2 1.8 3.5 1.8 3.5-1.8 3.5-1.8' },
  calm:   { label: () => muneaT('mood.steady', '平穩'), bg: '#E8F2EE', fg: '#1E7169', face: 'M9 10h.01M15 10h.01M9 15h6' },
  tired:  { label: () => muneaT('mood.tired', '疲累'), bg: '#EEEFEA', fg: '#5F6A61', face: 'M9 10h.01M15 10h.01M9.5 15.5h5' },
  down:   { label: () => muneaT('mood.low', '低落'), bg: '#E4EBF3', fg: '#3F5F80', face: 'M9 10h.01M15 10h.01M8.5 15.5s1.2-1.8 3.5-1.8 3.5 1.8 3.5 1.8' },
  upset:  { label: () => muneaT('mood.upset', '煩躁'), bg: '#ECE1F0', fg: '#6E4488', face: 'M8.5 9.5l2 1M15.5 9.5l-2 1M8.5 15.5s1.2-1.5 3.5-1.5 3.5 1.5 3.5 1.5' },
  // 家人要看得到他點的完整六種，不是被歸納成三四類（Edward 2026-08-01）。
  // 「焦慮」以前根本沒有位置、被 || 'calm' 掃進「平穩」——他明明點了焦慮，家人看到一切安好。
  // 「生氣」以前併進「煩躁」——被惹毛跟悶著氣不是同一件事，想關心他的家人需要分得出來。
  anxious: { label: () => muneaT('mood.anxious', '焦慮'), bg: '#FAECD8', fg: '#985C15', face: 'M8.6 9.1l2 .9M15.4 9.1l-2 .9M9 11h.01M15 11h.01M9.2 15.6q1.4-1.2 2.8 0t2.8 0' },
  angry:  { label: () => muneaT('mood.angry', '生氣'), bg: '#F7DEDB', fg: '#B0392D', face: 'M8.4 8.9l2.2 1.2M15.6 8.9l-2.2 1.2M9.2 11.4h.01M14.8 11.4h.01M8.8 16.4c1.7-1.9 4.7-1.9 6.4 0' },
};
const MOOD_WEEK_DEMO = [
  { d: '五', mood: 'happy', chats: [{ m: 'happy', t: () => muneaT('demo.mood.fri', '聊到孫子回來，笑聲不斷') }] },
  { d: '六', mood: 'glad',  chats: [{ m: 'glad', t: () => muneaT('demo.mood.sat', '天氣好，去公園走了一圈回來心情不錯') }] },
  { d: '日', mood: 'calm',  chats: [{ m: 'calm', t: () => muneaT('demo.mood.sun', '平常的一天，聊了午餐吃什麼') }] },
  { d: '一', mood: 'down',  chats: [{ m: 'down', t: () => muneaT('demo.mood.mon', '翻到老伴的照片，聊著聊著有點想念') }] },
  { d: '二', mood: 'tired', chats: [{ m: 'tired', t: () => muneaT('demo.mood.tue', '昨晚沒睡好，講話比較沒力氣') }] },
  { d: '三', mood: 'glad',  chats: [{ m: 'glad', t: () => muneaT('demo.mood.wed', '韓劇大結局，聊得很起勁') }] },
  { d: '今天', mood: 'happy', mixed: true, chats: [
    { m: 'upset', t: () => muneaT('demo.mood.todayAm', '早上：推銷電話一直來，有點火氣，陪她抱怨了一會兒') },
    { m: 'happy', t: () => muneaT('demo.mood.todayPm', '傍晚：小寶來電話說畢業了，笑得合不攏嘴') } ] },
];
let MOOD_WEEK = MOOD_WEEK_DEMO;
// 心情詞 → 家人頁的粗標籤（Edward 2026-08-01 修）
//
// 這張表以前只認「聊聊觀察」用的六個詞（開心／愉快／平穩／疲累／低落／煩躁），但使用者
// 自己在情緒球點的是另一組（開心／愉悅／平靜／低落／焦慮／生氣）——雲端原字送回來，
// 這裡對不上就一律 || 'calm'。結果他點愉悅、焦慮、生氣，家人頁全都顯示「平穩」。
//
// 現在兩套詞都收。**焦慮與生氣一定要分開**：焦慮是「他不安」、煩躁是「他被惹毛」，
// 對想關心他的家人來說是完全不同的訊號，不能混成一格。
const MOOD_ZH2KEY = {
  '開心': 'happy',
  '愉快': 'glad', '愉悅': 'glad',
  '平穩': 'calm', '平靜': 'calm',
  '疲累': 'tired',
  '低落': 'down',
  '焦慮': 'anxious', '緊張': 'anxious',
  '生氣': 'angry', '憤怒': 'angry',
  '煩躁': 'upset',
};
async function loadMoodWeekReal() {
  try {
    const r = await fetch(brainURL('/wellbeing/trend'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ days: 7 }) });
    if (!r.ok) return null;
    const d = await r.json();
    const daily = d.daily || [];
    if (!daily.length) return null;
    const wd = ['日', '一', '二', '三', '四', '五', '六'];
    const now = new Date();
    const todayIso = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    try { cacheMyMoodToday(daily, todayIso); } catch (e) {}
    return daily.map(x => ({
      d: x.date === todayIso ? '今天' : wd[new Date(x.date + 'T00:00').getDay()],
      mood: MOOD_ZH2KEY[x.mood] || 'calm',
      mixed: !!x.mixed,
      chats: (x.signals || []).map(s => ({ m: MOOD_ZH2KEY[s.mood] || 'calm', t: s.oneLine || '' })).filter(c => c.t),
    })).filter(x => x.chats.length);
  } catch (e) { return null; }
}
// 7/16 心情真串接：把「今天的粗心情標籤」存本機＋（變了就）補推一次家庭帳本。
// 為什麼只有粗標籤：心情觀察細節（聊了什麼、每句觀察）留在本人手機與本人帳，家人只看得到「開心／平穩／疲累」這種詞——隱私線在這裡。
function cacheMyMoodToday(daily, todayIso) {
  const today = (daily || []).find(x => x && x.date === todayIso);
  if (!today || !today.mood) return;
  const record = { label: today.mood, key: MOOD_ZH2KEY[today.mood] || 'calm', date: todayIso };
  let prev = null;
  try { prev = JSON.parse(localStorage.getItem('munea.myMoodToday') || 'null'); } catch (e) {}
  try { localStorage.setItem('munea.myMoodToday', JSON.stringify(record)); } catch (e) {}
  if (!isLoggedIn()) return;
  if (!prev || prev.key !== record.key || prev.date !== record.date) {
    let log = {};
    try { log = JSON.parse(localStorage.getItem('munea.healthLog') || '{}') || {}; } catch (e) {}
    pushOwnHealthLog(log);   // 沒接健康裝置也照推：帳本按人合併、家人至少看得到心情
  }
}
// 一個 session 只跟引擎拿一次心情週報（狀態頁心情卡與家庭心情同步共用同一份）
function fetchMoodWeekOnce() {
  if (!window.__moodRealPromise) window.__moodRealPromise = loadMoodWeekReal();
  return window.__moodRealPromise;
}
// 開機閒時抓一次：家人頁的心情同步不必等使用者自己點進狀態頁
setTimeout(() => { try { if (isLoggedIn()) fetchMoodWeekOnce(); } catch (e) {} }, 3000);
function moodFaceSvg(key, size) {
  const m = MOODS[key] || MOODS.calm;
  return '<svg class="ic" viewBox="0 0 24 24" style="color:' + m.fg + ';width:' + size + 'px;height:' + size + 'px"><circle cx="12" cy="12" r="9"/><path d="' + m.face + '"/></svg>';
}
function renderMoodWeek() {
  const wrap = $('#moodWeek');
  if (!wrap) return;
  // 真的還沒有紀錄時，不可以拿示範資料充數（Edward 2026-08-01 拍板）。
  // 那組示範寫著「聊到孫子回來，笑聲不斷」「翻到老伴的照片，聊著聊著有點想念」——
  // 剛裝好 App 的人打開家人頁就會看到這一週，子女會以為是真的。
  // 最後那句對伴侶還健在、或剛失去伴侶的人，傷的不只是準確度。
  // 標準跟健康數據一致：讀不到就說讀不到，不假裝有。
  if (MOOD_WEEK === MOOD_WEEK_DEMO) {
    wrap.innerHTML = '<div class="mood-week-empty">'
      + muneaEscapeHtml(muneaT(
        'mood.weekAccumulating',
        '還沒有足夠的紀錄。多聊幾次、或在下面點個心情，這裡就會長出你自己的一週。',
      ))
      + '</div>';
    return;
  }
  wrap.innerHTML = MOOD_WEEK.map((day, i) => {
    const m = MOODS[day.mood];
    const today = day.d === '今天';
    return '<button class="md' + (today ? ' today' : '') + '" data-i="' + i + '">' +
      '<span class="mcirc" style="background:' + m.bg + '">' + moodFaceSvg(day.mood, 22) +
      (day.mixed ? '<span class="mixdot"></span>' : '') + '</span>' +
      '<span class="mday">' + moodDayShort(day.d) + '</span></button>';
  }).join('');
  wrap.querySelectorAll('.md').forEach(b => b.addEventListener('click', () => showMoodDay(+b.dataset.i)));
  showMoodDay(MOOD_WEEK.length - 1);
  fetchMoodWeekOnce().then(real => {
    if (real && real.length >= 3 && MOOD_WEEK !== real) { MOOD_WEEK = real; renderMoodWeek(); }
  });
}
const MOOD_WEEKDAY_KEYS = { '一': 'mood.weekdayShortMon', '二': 'mood.weekdayShortTue', '三': 'mood.weekdayShortWed', '四': 'mood.weekdayShortThu', '五': 'mood.weekdayShortFri', '六': 'mood.weekdayShortSat', '日': 'mood.weekdayShortSun' };
function moodDayShort(d) {
  if (d === '今天') return muneaT('common.today', '今天');
  return MOOD_WEEKDAY_KEYS[d] ? muneaT(MOOD_WEEKDAY_KEYS[d], d) : d;
}
function moodDayLabel(d) {
  if (d === '今天') return muneaT('common.today', '今天');
  return MOOD_WEEKDAY_KEYS[d] ? muneaT('mood.weekdayLabel', '週{day}', { day: muneaT(MOOD_WEEKDAY_KEYS[d], d) }) : d;
}
function showMoodDay(i) {
  const day = MOOD_WEEK[i];
  const box = $('#moodDayDetail');
  if (!box || !day) return;
  box.innerHTML = '<div class="dd-date">' + muneaT('mood.dayChatsCount', '{day} · 聊了 {count} 次', { day: moodDayLabel(day.d), count: day.chats.length }) + '</div>' +
    day.chats.map(c => '<div class="dd-row">' + moodFaceSvg(c.m, 19) + '<span>' + (typeof c.t === 'function' ? c.t() : c.t) + '</span></div>').join('');
}
const MOOD_DAY_LINES = {
  happy: () => muneaT('mood.dayHappy', '那天聊得很開心，聲音都亮亮的'),
  glad: () => muneaT('mood.dayGlad', '心情不錯，話匣子開著'),
  calm: () => muneaT('mood.dayCalm', '平平穩穩的一天'),
  tired: () => muneaT('mood.dayTired', '有點累，講話比較小聲'),
  down: () => muneaT('mood.dayDown', '悶悶的，多陪了一會兒'),
  upset: () => muneaT('mood.dayUpset', '有點火氣，抱怨完就好多了'),
};
function renderMoodMonth() {
  const wrap = $('#moodMonth');
  if (!wrap || wrap.childElementCount) return;
  const seq = ['calm','glad','happy','calm','tired','glad','calm','down','calm','glad','happy','glad','calm','calm','tired','glad','calm','happy','glad','calm','down','tired','glad','calm','happy','glad','calm','happy'];
  const now = new Date();
  const daysInM = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const todayD = now.getDate();
  let html = '';
  for (let i = 0; i < daysInM; i++) {
    const day = i + 1;
    if (day > todayD) { html += '<span class="mm-cell future"></span>'; continue; }
    const k = seq[i % seq.length];
    html += '<button class="mm-cell" data-k="' + k + '" data-d="' + day + '" style="background:' + MOODS[k].bg + ';color:' + MOODS[k].fg + '">' + day + '</button>';
  }
  wrap.innerHTML = html + '<div class="mm-note">' + muneaT('mood.mapUpTo', '記到今天（{date}）為止', { date: (now.getMonth() + 1) + '/' + todayD }) + '</div>';
  wrap.addEventListener('click', e => {
    const c = e.target.closest('.mm-cell');
    if (!c) return;
    wrap.querySelectorAll('.mm-cell').forEach(x => x.classList.remove('on'));
    c.classList.add('on');
    const box = $('#moodDayDetail');
    if (box) box.innerHTML = '<div class="dd-date">' + (now.getMonth() + 1) + '/' + c.dataset.d + ' · ' + MOODS[c.dataset.k].label() + '</div>' +
      '<div class="dd-row">' + moodFaceSvg(c.dataset.k, 19) + '<span>' + (MOOD_DAY_LINES[c.dataset.k] ? MOOD_DAY_LINES[c.dataset.k]() : '') + '</span></div>';
    $('#moodDayDetail').style.display = '';
  });
}

const _hscrollUpdaters = [];
function refreshHscrollHints() { _hscrollUpdaters.forEach(u => u()); }
function setupHscrollHints() {
  $$('.hscroll-wrap').forEach(w => {
    const sc = w.querySelector('.fam-switch, .avatar-pick');
    if (!sc) return;
    const update = () => {
      if (!sc.clientWidth) return; // 分頁隱藏中不判定
      const atEnd = sc.scrollLeft + sc.clientWidth >= sc.scrollWidth - 8;
      w.classList.toggle('at-end', atEnd);
    };
    sc.addEventListener('scroll', update, { passive: true });
    _hscrollUpdaters.push(update);
    update();
  });
  window.addEventListener('resize', refreshHscrollHints);
}

async function connectCall() {
  // 真的要撥號才要求登入（Edward 2026-07-30：訪客能進聊聊頁看，點「開始通話」才跳登入）。
  // 守門放在這裡＝所有撥號入口的共同關卡（通話鈕／同意跨境後接著撥／選完話題後接著撥），
  // 少一條路都不會漏。免費 5 分鐘綁帳號的原則不變，只是把關卡從門口移到這一刻。
  if (!requireLogin(muneaT(
    'auth.chatSignInRequired',
    '請先使用 Google 或 Apple 登入才能使用聊聊；免費帳號會收到一次性 5 點，約 5 分鐘',
  ), 'chat')) return;
  if (callPreflightPending || callDialing || callConnected) return;
  setCallPreflightPending(true);
  // 2026-08-01（Edward 真機：「按下去會 lag 一陣子才轉撥通中，會以為當機」）：
  // 畫面的「撥通中」原本要等帳號確認／點數／向總機叫號整趟跑完（那幾支各 0.7-1.2 秒）
  // 才切——手指按下去到畫面有反應中間空白一大段。改成**先把畫面切過去、再去跑那些事**；
  // 任何一條失敗路徑會經過 setCallPreflightPending(false)，那裡負責把畫面切回待機。
  try {
    const _chatEl0 = document.getElementById('chat');
    if (_chatEl0 && _chatEl0.dataset.state !== 'connecting') _chatEl0.dataset.state = 'connecting';
    setLocalizedCallHint('connecting', true);
  } catch (e) {}
  hideBusyCard();   // 上一輪的「全滿」卡若還留著，重撥就收掉
  if (typeof exitTextFallbackChat === 'function') exitTextFallbackChat();   // 若正在「先用文字聊」，重新真的撥號前先收掉面板，避免兩層畫面疊在一起（2026-07-24 P0）
  // Give immediate, cancellable feedback before any optional network work.
  const developmentDirectCall = usesDevelopmentDirectCall();
  try {
    if (VoiceCallDiagnostics) VoiceCallDiagnostics.start({
      appVersion: window.MuneaVersion && window.MuneaVersion.current,
      routeMode: developmentDirectCall ? 'development_direct' : 'gateway',
      gatewayEndpoint: CallControl.url(),
      voiceEndpoint: getLiveVoiceUrl(),
      avatarEndpoint: getAvatarUrl(),
      faceEngine: faceEngine(),
    });
  } catch (e) {}
  // 撥通中＝保持角色的待機動畫（Edward 2026-07-09 二次拍板：不定格照片、也不動照片）。
  // 硬規則：聲音＋會動的臉「兩邊都真的就緒」才一起開場——寧可讓用戶等，也不要開場後像當機。
  // 同線聲音的 iPhone 解鎖（2026-07-11）：iPhone 不准「沒經過使用者手指」的聲音自動播——
  // 同線那軌之前一直被擋、每通都退回本地播放。趁「開始通話」這根手指先讓 faceAud 播一下取得許可。
  try {
    Avatar._callT0 = Date.now(); Avatar._diagTrail = [];   // 黑盒子每通歸零
    Avatar._diagNote('按下開始通話');
    _fhWarmArt();        // 立繪再保險解碼一次（進頁時沒跑到也補得上）
    _fhPreParentVid();   // 播放器先進臉框：接通時不再搬 DOM＝不重建圖層、不黑一格（第一通黑閃修正）
    if (faceSameLineOn()) {
      const _fv = document.getElementById('faceVid');
      if (_fv) {
        // 趁「這根手指」餵一段無聲的真聲音給影像播放器並播——iPhone 才會把「出聲許可」記在它身上；
        // 之前只對「還沒裝聲音的空播放器」喊 play 不算數（真串流一秒後到、手指許可已過期又被擋）＝延遲根因之一。
        try {
          const AC = window.AudioContext || window.webkitAudioContext;
          Avatar._primeCtx = Avatar._primeCtx || new AC();
          try { if (Avatar._primeCtx.state === 'suspended') Avatar._primeCtx.resume(); } catch (e2) {}
          const dst = Avatar._primeCtx.createMediaStreamDestination();
          const g = Avatar._primeCtx.createGain(); g.gain.value = 0;
          const osc = Avatar._primeCtx.createOscillator(); osc.connect(g); g.connect(dst); osc.start();
          _fv.srcObject = dst.stream; _fv.muted = false;   // 無聲音軌、不影響待機影片（待機片在另一層）
          const _p2 = _fv.play();
          if (_p2 && _p2.then) _p2.then(() => Avatar._diagNote('解鎖影像播放器:成功')).catch((er) => Avatar._diagNote(muneaT('avatar.forceUnlockBlocked', '解鎖:被擋({reason})', { reason: (er && er.name) || '' }), true));
        } catch (e3) { try { _fv.muted = false; const _p3 = _fv.play(); if (_p3 && _p3.catch) _p3.catch(() => {}); } catch (e4) {} Avatar._diagNote('解鎖:改用簡易法'); }
      }
      const _fa = document.getElementById('faceAud');
      if (_fa) { _fa.muted = false; const _p = _fa.play(); if (_p && _p.catch) _p.catch(() => {}); }
    }
  } catch (e) {}
  // Keep the iOS user gesture alive before the queue/network wait starts.
  voiceCallMark('microphone_requested', 'pass');
  if (!LiveVoice.prime()) {
    setCallPreflightPending(false);
    voiceCallFail('microphone_requested', LiveVoice._micUnavailableReason || 'microphone_prime_failed');
    voiceCallEnd('failed', LiveVoice._micUnavailableReason || 'microphone_prime_failed');
    const micHttpsOnly = LiveVoice._micUnavailableReason === 'https_required';
    setLocalizedCallHint('unavailable');
    showCallStatusCard(micHttpsOnly ? 'microphoneHttps' : 'microphonePermission');
    return;
  }
  // 前置並行（2026-07-29 接通提速）：家人傳話準備、帳號確認、點數同步原本一條龍
  // 等完才向總機叫號——行動網路一趟來回幾百毫秒、串起來破秒。改成同時跑，語意不變：
  // 傳話仍最多等 1.2 秒（從這裡就開始計時、跟其他前置重疊）、帳號沒好照樣擋在叫號前、
  // 點數不足照樣不佔席位。
  const _relayReady = developmentDirectCall ? null : Promise.race([
    LiveVoice.prepareRelay().catch(() => {}),
    new Promise(resolve => setTimeout(resolve, 1200)),
  ]);
  if (typeof FaceIdle !== 'undefined' && !FaceIdle.active) FaceIdle.start();   // 進頁已在播就延續、不重啟（免重播招呼）
  if (developmentDirectCall) {
    setCallDialing(true);
    setLocalizedCallHint('developerConnecting', true);
  } else {
    // 點數是否足夠這件事只在後端靜默判斷，畫面維持一般撥號觀感，不對用戶顯示「查點數」字樣（Edward 2026-07-20拍板）。
    setLocalizedCallHint('connecting', true);
    try {
      // A verified Auth session is not enough for Call Control: its durable
      // lease RPC also requires the account_members/person graph. Await the
      // idempotent bootstrap so a fresh login cannot race the first call.
      const _preflightT0 = performance.now();
      let creditState = null;
      // 帳號確認與點數同步並行（各自一趟網路來回，疊起來只花較慢那趟的時間）。
      // 跨月或年繳方案可能在這次通話前進入新點數週期；點數照樣在叫號前同步完。
      const [accountReady] = await Promise.all([
        syncAccountBootstrap('create', { reason: 'call_preflight' }),
        (async () => { try { creditState = await refreshServerCredits(); } catch (e0) {} })(),
      ]);
      if (!accountReady || !accountReady.ok) throw new Error('account_not_ready');
      const rawAvailableCredits = creditState && creditState.walletSummary && creditState.walletSummary.total;
      const availableCredits = Number(rawAvailableCredits);
      if (rawAvailableCredits !== null && rawAvailableCredits !== undefined && rawAvailableCredits !== '' && Number.isFinite(availableCredits)) {
        voiceCallMark('credits_checked', availableCredits > 0 ? 'pass' : 'fail', { remaining: Math.max(0, availableCredits) });
        // 開發者 Gateway 模式（真登入、非直連）：仍照查、照記錄，但 0 點不擋——Edward 講了幾百遍卡在這裡測不了聊聊。
        // 正式用戶（非開發者旁路）完全不受影響，0 點依然照擋。
        if (availableCredits <= 0 && !isGatewayDeveloperProfile()) throw new Error('insufficient_credits');
      }
      // 用戶可能在前置檢查途中就按了取消／離開（排隊可取消上線後，取消會把 preflight 收掉）——不再往下向總機叫號
      if (!callPreflightPending && !callDialing && !callConnected) return;
      // 撥號中就是撥號中：不把「安排通話／安排席位」這種後台調度字眼推到畫面上，
      // 按鈕與字幕一路維持「連線中…」直到真的進入撥號（Edward 2026-07-20 拍板）。
      // 例外＝真的滿載在排隊（Edward 2026-07-22 拍板 B 案）：排隊卡明講第幾位，這不是後台字眼、是誠實狀態。
      setCallPreflightPending(true);
      // 傳話準備若還沒好，補等到 1.2 秒上限為止（多半已在上面並行期間完成＝零等待）
      if (_relayReady) { try { await _relayReady; } catch (e0) {} }
      voiceCallMark('preflight_parallel', 'pass', { ms: Math.round(performance.now() - _preflightT0) });
      voiceCallMark('gateway_requested', 'pass', { endpoint: CallControl.url() });
      const lease = await CallControl.acquire(typeof currentChar === 'string' ? currentChar : 'default');
      if (!lease || !lease.voice || !lease.voice.url || !lease.worker || !lease.worker.url) {
        throw new Error('paired_service_unavailable');
      }
      setCallDialing(true);
      voiceCallMark('gateway_assigned', 'pass', {
        gatewayCallId: lease.call_id || '',
        voiceEndpoint: lease.voice.url,
        avatarEndpoint: lease.worker.url,
      });
    } catch (e) {
      const reason = String(e && e.message || e);
      // 用戶自己取消排隊／撥號：取消當下畫面與席位都已收好（completeChatSession → release），這裡靜靜退場即可
      if (reason === 'call_cancelled') { setCallPreflightPending(false); setCallDialing(false); return; }
      const authRequired = reason.indexOf('authentication_required') >= 0;
      voiceCallFail('gateway_assigned', reason, { endpoint: CallControl.url() });
      voiceCallEnd('failed', reason);
      try { await CallControl.release(reason); } catch (e2) {}
      LiveVoice.stop(); setCallPreflightPending(false); setCallDialing(false); stopCallTimer();
      setLocalizedCallHint('unavailable');
      // 無聲失敗全部接上看得見的卡（2026-07-24 Edward 拍板 P0）：#chatCaption 被藏起來，光靠上面那句字幕使用者實際上看不到，
      // 每種失敗都要有標題講原因＋一句怎麼辦＋一顆按鈕；點數不足已有專屬彈窗（__muneaShowCallCreditBlocked），不重複打擾。
      const accountNotReady = reason.indexOf('account_not_ready') >= 0;
      const queueFull = reason.indexOf('queue_full') >= 0;
      const insufficientCredits = reason.indexOf('insufficient_credits') >= 0;
      const controlNotConfigured = reason.indexOf('call_control_not_configured') >= 0;
      if (queueFull) {
        showBusyCard('full');   // 連排隊的位子都滿了：明講忙線、請稍後再試＋「先用文字聊」出口（Edward 7/22 B 案／7/24 P0 加出口）
      } else if (authRequired) {
        showCallStatusCard('authExpired');
      } else if (accountNotReady) {
        showCallStatusCard('accountPreparing');
      } else if (controlNotConfigured) {
        showCallStatusCard('serviceUpdating');
      } else if (!insufficientCredits) {
        showCallStatusCard('serviceBusy');
      }
      if (authRequired) setTimeout(() => { try { openAuthSheet(); } catch (e2) {} }, 0);
      if (insufficientCredits) setTimeout(__muneaShowCallCreditBlocked, 0);
      try { trackProductEvent('call_control_rejected', { reason }); } catch (e2) {}
      return;
    }
  }
  let _connectedOnce = false;
  const markConnected = () => { if (_connectedOnce) return; _connectedOnce = true; setCallToggle(true); startCallTimer(); };
  // 每通電話都從一張乾淨的字幕開始（同 enterChat：只切顯示／隱藏會把上一通的字帶進來）。
  // 拿掉之後由 setCaption 重建；字幕開關關著時 setCaption 本來就不會建，所以原本
  // 「關字幕就隱藏」的行為不變。
  const box = document.querySelector('.face-caption-box');
  if (box) box.remove();
  // 真即時語音（Gemini 3.1 Live）：麥克風即時串流、寧寧真聲音即時回、可打斷
  if (getLiveVoiceUrl()) {
    chatOpened = true;
    activeChatSessionId = makeSessionId('voice');
    activeChatStartedAt = Date.now();
    activeChatTurnCount = 0;
    voiceCallMark('app_session_created', 'pass', { sessionId: activeChatSessionId });
    setFaceState('idle');
    // 新引擎首通冷開機較久（喚醒優化交先鋒車道）——誠實預告、不讓人以為當機（Edward 2026-07-11「等20秒」）
    setLocalizedCallHint(faceEngine() === 'flashhead' && !Avatar.warm ? 'firstWarmup' : 'connecting', true);
    trackProductEvent('voice_session_started', { locale: muneaLocale(), mode: 'live' });
    const chatEl = document.getElementById('chat');
    if (chatEl) chatEl.dataset.state = 'connecting';
    FaceWave.start();   // 撥通中就先把波紋畫出來（靜止的一排小點）＝接通了畫面不是空的（Edward 8/10）

    // ===== 兩邊都就緒才開場（Edward 2026-07-09 二次拍板）=====
    let _voiceReady = false, _faceReady = false, _started = false, _activationInFlight = false;
    const noFace = !getAvatarUrl();          // 沒接雲端臉的角色（或關閉）＝不必等臉
    if (noFace) _faceReady = true;
    const beginConversation = async () => {
      if (_started || _activationInFlight || !_voiceReady || !_faceReady) return;
      if (!callDialing && !callConnected) { clearTimeout(_gateTimeout); return; }   // 已取消/掛斷 → 別誤開場
      _activationInFlight = true;
      try {
        voiceCallMark('gateway_activation_wait', 'pass');
        setLocalizedCallHint(developmentDirectCall ? 'developerReady' : 'connecting', true);
        if (!developmentDirectCall) await CallControl.waitUntilActive(15000);
      } catch (e) {
        voiceCallFail('gateway_activation', e);
        _activationInFlight = false;
        clearTimeout(_gateTimeout);
        try { LiveVoice.stop(); } catch (e2) {}
        try { FaceWave.stop(); } catch (e2) {}
        try { completeChatSession(String(e && e.message || e)); } catch (e2) {}
        chatOpened = false; setCallDialing(false); stopCallTimer();
        const ce = document.getElementById('chat'); if (ce) ce.dataset.state = 'idle';
        setFaceState('idle'); setLocalizedCallHint('unavailable');
        showCallStatusCard('activationPending');
        try { FaceIdle.start(); } catch (e2) {}
        return;
      }
      if (!callDialing && !callConnected) { clearTimeout(_gateTimeout); return; }
      setLocalizedCallHint('openingWarmup', true);
      voiceCallMark('opening_audio_warmup', 'pass');
      const openingAudio = noFace
        ? { mode: 'no_avatar', verified: true, receiverAttached: false }
        : await LiveVoice.prepareOpeningAudioPath(600);
      // Silent warmup is advisory: some Avatar workers do not emit RTP for
      // zero PCM. A connected receiver continues on the same-line route and
      // real opening audio is checked by the watchdog; no receiver uses local
      // playback immediately. Neither case should tear down a healthy call.
      voiceCallMark('opening_audio_ready', 'pass', openingAudio);
      await new Promise(resolve => setTimeout(resolve, 250));
      _activationInFlight = false;
      if (!callDialing && !callConnected) { clearTimeout(_gateTimeout); return; }
      _started = true;
      clearTimeout(_gateTimeout);
      try { localStorage.setItem('munea.callCount', String((parseInt(localStorage.getItem('munea.callCount') || '0', 10) || 0) + 1)); } catch (e) {}   // 聊過幾通＋1 → 下通開場更像老朋友（熟識度）
      try {
        if (!LiveVoice._openingRecorded && LiveVoice._openingDayKey) {
          localStorage.setItem('munea.dailyCallOpening', JSON.stringify({ day: LiveVoice._openingDayKey, count: (LiveVoice._openingDayCall || 0) + 1 }));
          LiveVoice._openingRecorded = true;
        }
      } catch (e) {}
      markConnected();                       // 1 秒獨立暖機完成，現在才切成真正接通並開始計時
      voiceCallMark('call_connected', 'pass');
      if (!noFace) Avatar.showLiveFrame();   // 第一個有效影格確認後才切換，撥號中不露出黑色視訊層
      try { FaceIdle.stop(); } catch (e) {}
      // greet() 只在「有家人託她轉達」時才真的請她開口；其餘一律等使用者先說。
      LiveVoice.greet();
      // 麥克風已經在 ready 事件開好了（見 'ready' 分支）。這裡再補一次是保險：
      // 萬一 ready 早於 markConnected、中間狀態被別的路徑動過，接通當下一定是開的。
      LiveVoice._setMicOpen(true);
      LiveVoice._openMicAfterGreet = false;
      try { if (window.MuneaAvSyncMeter && typeof Avatar !== 'undefined' && Avatar.on) MuneaAvSyncMeter.start(); } catch (e) {}   // 接了會動的臉才量延遲（左下角讀數 · Edward 2026-07-10）
      // 省點提醒（Edward 2026-07-10）：通話開著卻一直沒人講話 → 寧寧兩段式溫柔提醒、再久自動掛斷、不浪費點數。
      // 時鐘只算「真沉默」（使用者＋AI 都沒講）；使用者一開口整個歸零。11 秒一階。
      const _autoEndCall = () => {
        setLocalizedCallHint('idleEnded');
        try { LiveVoice.stop(); } catch (e) {} try { FaceWave.stop(); } catch (e) {}
        try { completeChatSession('idle_timeout'); } catch (e) {}
        chatOpened = false; setCallToggle(false); stopCallTimer();
        const ce = document.getElementById('chat'); if (ce) ce.dataset.state = 'idle';
        setFaceState('idle'); if (window.__muneaStopListen) window.__muneaStopListen();
        try { FaceIdle.start(); } catch (e) {}
      };
      let _idleLast = Date.now(), _idleStage = 0;
      const _idleGapMs = 30000;   // Edward 2026-07-10 拍板：第一次提醒 30 秒、第二次再過 30 秒（自動收線再 30 秒）
      const _idleMon = setInterval(() => {
        if (!callConnected && !callDialing) { clearInterval(_idleMon); return; }      // 通話結束 → 自我終止
        if (LiveVoice.micLevel > 0.08) { _idleLast = Date.now(); _idleStage = 0; return; }   // 使用者在講 → 全歸零
        if (speechActive()) { _idleLast = Date.now(); return; }   // AI 在講（單一真相 speechActive：本地喇叭或臉那條線都認）→ 時鐘後推、階段保留
        if (Date.now() - _idleLast < _idleGapMs) return;                               // 還沒到 30 秒真沉默
        // Edward 2026-07-11 拍板：提醒做不好就拿掉、不要再吵——兩段提醒全停（nudge 不再呼叫），
        // 只留第三段「沉默 90 秒安靜收線」。要復原提醒＝把下兩行換回 LiveVoice.nudge(1)/nudge(2)。
        if (_idleStage === 0) { _idleStage = 1; _idleLast = Date.now(); }
        else if (_idleStage === 1) {
          _idleStage = 2; _idleLast = Date.now();
          // 2026-08-01（Edward 真機：「不講話怎麼自己就斷了」）：兩段語音提醒 7/11 已拿掉，
          // 於是 90 秒沉默的自動收線變成「毫無預警忽然斷掉」＝很像當機。這裡補一句
          // **畫面上的**預告（不出聲，維持 7/11「不要再吵」的決定），最後 30 秒才收線。
          try { setLocalizedCallHint('idleWarning'); } catch (e) {}
          try { trackProductEvent('voice_idle_warning_shown', { afterMs: _idleGapMs * 2 }); } catch (e) {}
        }
        // 2026-08-08 Edward 拍板：「現在只要不講話就會自動掐斷通話，拿掉這個機制」。
        // 改成「你先說她才回」之後，接通後的安靜變成常態——使用者可能只是在想要講什麼，
        // 卻被當成離開而收線；被系統掛掉的感覺跟當機沒兩樣。
        // 現在沉默只留畫面上的提示（上面那段），**不再自動掛斷**。
        // 代價講明：使用者忘記掛斷就會一直計費，靠的是他自己按結束。
        // 要復原＝把下面這行換回 `clearInterval(_idleMon); _autoEndCall();`
        else { _idleLast = Date.now(); }                                               // 沉默不再收線，時鐘往後推、繼續等他
      }, 1500);
    };
    const tryStart = () => { beginConversation().catch(() => {}); };
    window.__muneaOnFaceReady = () => { _faceReady = true; tryStart(); };
    // 準備逾時絕不「假裝就緒」硬開場。舊規則 25 秒後強制放行，正是顯卡未好就撥通、首句變形的來源。
    const _gateTimeout = setTimeout(() => {
      if (_started) return;
      voiceCallFail('readiness_gate', 'readiness_timeout', { voiceReady: _voiceReady, faceReady: _faceReady });
      try { LiveVoice.stop(); } catch (e) {}
      chatOpened = false; setCallDialing(false); stopCallTimer();
      const ce = document.getElementById('chat'); if (ce) ce.dataset.state = 'idle';
      setFaceState('idle'); setLocalizedCallHint('unavailable');
      showCallStatusCard('readinessPending');
      try { completeChatSession('readiness_timeout'); } catch (e) {}
      try { FaceIdle.start(); } catch (e) {}
      try { trackProductEvent('voice_readiness_timeout', { voiceReady: _voiceReady, faceReady: _faceReady }); } catch (e) {}
    }, 30000);

    LiveVoice.onReady = () => { _voiceReady = true; tryStart(); };   // 語音伺服器接上腦＝語音就緒
    LiveVoice.onConnecting = () => { if (chatEl) chatEl.dataset.state = 'connecting'; setLocalizedCallHint('connecting', true); };
    // 開場後才顯示狀態（撥通中維持待機動畫、不搶戲）
    const onListen = () => { if (!_started) return; if (chatEl) chatEl.dataset.state = 'listening'; setFaceState('listening'); setLocalizedCallHint('ready'); FaceWave.start(); };
    // 她講話時波紋不跟著跳（Edward 8/10）——波紋只代表「我聽到你」；她在說話有嘴形＋聲音就夠了。
    const onSpeak = () => { if (!_started) return; if (chatEl) chatEl.dataset.state = 'speaking'; setFaceState('speaking'); setLocalizedCallHint('speaking'); FaceWave.start(); avatarRuntime.startLiveViseme(() => LiveVoice.playLevel); };
    LiveVoice.onCaption = (t) => setCaption(t);   // 字幕開啟時，寧寧說的話逐字上字幕
    // 斷線自動接回：掉了就自動重連；多次失敗則收整通，不退成純語音。
    let _reconnects = 0;
    const onDrop = () => {
      if (!callConnected && !callDialing) return;         // 使用者已掛斷/取消 → 不重連
      if (_reconnects++ > 6) {                            // Voice＋Avatar 是同一項服務；任一邊斷線就收整通
        try { LiveVoice.stop(); } catch (e) {}
        try { completeChatSession('reconnect_failed'); } catch (e) {}
        chatOpened = false; setCallDialing(false); setCallToggle(false); stopCallTimer();
        if (chatEl) chatEl.dataset.state = 'idle';
        setFaceState('idle'); setLocalizedCallHint('unavailable');
        showCallStatusCard('disconnected');
        try { FaceIdle.start(); } catch (e) {}
        return;
      }
      setLocalizedCallHint('connecting', true);
      setTimeout(() => {
        if (!callConnected && !callDialing) return;
        const resume = CallControl.active ? CallControl.refreshToken() : Promise.resolve();
        resume.then(() => LiveVoice.start(onListen, onSpeak, onDrop)).catch(() => onDrop());
      }, 500);
    };
    LiveVoice.start(onListen, onSpeak, onDrop).then(ok => {
      if (!ok && callDialing) voiceCallFail('voice_start', 'voice_start_failed');
    }).catch(error => voiceCallFail('voice_start', error));
    Avatar.start().then(ok => {
      if (ok || Avatar._lastError !== 'capacity_full') return;
      try { LiveVoice.stop(); } catch (e) {}
      chatOpened = false; setCallDialing(false); stopCallTimer();
      if (chatEl) chatEl.dataset.state = 'idle';
      setFaceState('idle'); setLocalizedCallHint('unavailable');
      showBusyCard('full');   // 影像席位全滿跟排隊全滿是同一類「都滿了」，一併給「先用文字聊」出口（2026-07-24 P0）
      try { completeChatSession('avatar_capacity_full'); } catch (e) {}
      try { trackProductEvent('avatar_capacity_full', { mode: 'voice_avatar_required' }); } catch (e) {}
      try { FaceIdle.start(); } catch (e) {}
    }).catch(() => {});   // 影像滿載不退純語音；下一版接 Gateway 後顯示排隊位置
    return;
  }
  setCaption(
    muneaT('voice.call.connectedCaption', ''),
    muneaT('voice.call.listeningPrompt', ''),
  );
  markConnected();   // 簡單陪聊模式（無雲端語音）＝立即可講
  openVoiceSession();
  setTimeout(() => { if (window.__muneaStartListen) window.__muneaStartListen(); }, 400);
}

let legalRoutingManifestsPromise = null;
function isLocalI18nDraftPreview() {
  const config = window.MUNEA_DEV_CONFIG || {};
  const localOrigin = ['localhost', '127.0.0.1', ''].includes(window.location.hostname)
    || window.location.protocol === 'file:';
  const queryLocale = new URLSearchParams(window.location.search).get('lang');
  const requestedLocale = config.i18nPreviewLocale || queryLocale;
  return localOrigin
    && config.enabled === true
    && ['zh-TW', 'en', 'ja', 'es'].includes(requestedLocale)
    && requestedLocale === muneaLocale();
}
function trustedLegalRegion() {
  const region = latestTrustedLocaleContext && latestTrustedLocaleContext.legalRegion;
  return /^[A-Z]{2}$/.test(String(region || '').trim().toUpperCase())
    ? String(region).trim().toUpperCase()
    : null;
}
async function fetchJsonDocument(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Unable to load ${path}: HTTP ${response.status}`);
  return response.json();
}
function legalRoutingManifests() {
  if (!legalRoutingManifestsPromise) {
    legalRoutingManifestsPromise = Promise.all([
      fetchJsonDocument('src/i18n/catalog-manifest.json'),
      fetchJsonDocument('legal/manifest.json'),
    ]).then(([catalogManifest, legalManifest]) => ({ catalogManifest, legalManifest }))
      .catch(error => {
        legalRoutingManifestsPromise = null;
        throw error;
      });
  }
  return legalRoutingManifestsPromise;
}
async function resolveInAppLegalPage(kind) {
  const routing = window.MuneaLegalRouting;
  if (!routing || typeof routing.resolveLegalPage !== 'function') {
    throw new Error('Legal routing is unavailable');
  }
  const manifests = await legalRoutingManifests();
  return routing.resolveLegalPage({
    kind,
    ...manifests,
    locale: muneaLocale(),
    legalRegion: trustedLegalRegion(),
    allowDraft: isLocalI18nDraftPreview(),
  });
}
function setReaderStatus(body, text) {
  const paragraph = document.createElement('p');
  paragraph.textContent = text;
  body.replaceChildren(paragraph);
}
async function openInAppReader(kind, options) {
  const reader = $('#readerPage');
  const body = $('#readerBody');
  if (!reader || !body) return;
  const titleKey = kind === 'terms' ? 'reader.termsTitle' : 'reader.privacyTitle';
  const titleFallback = kind === 'terms' ? muneaT('auth.termsLinkTerms', '使用條款') : muneaT('auth.termsLinkPrivacy', '隱私權政策');
  $('#readerTitle').textContent = muneaT(titleKey, titleFallback);
  reader.dataset.returnToConsent = options && options.returnToConsent ? '1' : '';
  setReaderStatus(body, muneaT('reader.loading', '內容載入中…'));
  reader.classList.add('show');
  reader.setAttribute('aria-hidden', 'false');
  try {
    const route = await resolveInAppLegalPage(kind);
    const response = await fetch(route.path);
    if (!response.ok) throw new Error(`Unable to load legal page: HTTP ${response.status}`);
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    const secs = [...doc.querySelectorAll('.privacy-section')];
    if (!secs.length) throw new Error('Legal page has no readable sections');
    body.innerHTML = secs.map(s2 => '<h4>' + (s2.querySelector('h2')?.textContent || '') + '</h4>' +
      [...s2.querySelectorAll('p, ul')].map(x => x.outerHTML.replace(/<h2.*?<\/h2>/, '')).join('')).join('');
    body.querySelectorAll('a').forEach(a => { const b2 = document.createElement('strong'); b2.textContent = a.textContent; a.replaceWith(b2); });
  } catch (e) {
    setReaderStatus(body, muneaT('reader.loadError', '無法載入內容，請稍後再試。'));
  }
  const scroll = body.closest('.reader-scroll');
  if (scroll) scroll.scrollTop = 0;
}

function closeInAppReader() {
  const reader = $('#readerPage');
  if (!reader) return;
  const returnToConsent = reader.dataset.returnToConsent === '1';
  reader.dataset.returnToConsent = '';
  reader.classList.remove('show');
  reader.setAttribute('aria-hidden', 'true');
  if (returnToConsent) {
    const sheet = $('#consentSheet');
    if (sheet) sheet.classList.add('show');
  }
}

function applyTaskAccessibilityLabels() {
  document.querySelectorAll('#taskCard svg').forEach(s2 => s2.setAttribute('aria-hidden', 'true'));
  document.querySelectorAll('#taskCard .task-check').forEach(s2 => {
    s2.setAttribute('aria-label', muneaT('accessibility.markComplete', '標示完成'));
  });
}

function setupCriticalConsentControls() {
  const sheet = $('#consentSheet');
  if (!sheet || sheet.dataset.controlsBound === '1') return;
  sheet.dataset.controlsBound = '1';

  const close = sheet.querySelector('.mx-close');
  if (close) close.addEventListener('click', e => {
    e.stopPropagation();
    sheet.classList.remove('show');
  });
  const agree = $('#consentAgree');
  if (agree) agree.addEventListener('click', () => {
    try { localStorage.setItem('munea.consent.crossborder', new Date().toISOString()); } catch (e) {}
    try { trackProductEvent('crossborder_consent_given', {}); } catch (e) {}
    sheet.classList.remove('show');
    connectCall();
  });
  const detail = $('#consentDetail');
  if (detail) detail.addEventListener('click', e => {
    e.preventDefault();
    sheet.classList.remove('show');
    openInAppReader('privacy', { returnToConsent: true });
  });
  const readerBack = $('#readerBack');
  if (readerBack && readerBack.dataset.controlsBound !== '1') {
    readerBack.dataset.controlsBound = '1';
    readerBack.addEventListener('click', closeInAppReader);
  }
}
document.addEventListener('DOMContentLoaded', setupCriticalConsentControls);

function init() {
  if (new URLSearchParams(location.search).get('debug')) document.body.classList.add('debug');
  // 體驗捷徑：網址帶 ?voiceUrl= / ?avatarUrl= → 寫進本機設定後生效（一鍵體驗 bat 用）
  try {
    const _q = new URLSearchParams(location.search);
    if (_q.get('voiceUrl') !== null) localStorage.setItem('munea.liveVoiceUrl', _q.get('voiceUrl'));
    if (_q.get('avatarUrl') !== null) localStorage.setItem('munea.avatarUrl', _q.get('avatarUrl'));
    if (_q.get('brainUrl') !== null) localStorage.setItem('munea.brainUrl', _q.get('brainUrl'));
    if (_q.get('faceEngine') !== null) localStorage.setItem('munea.faceEngine', _q.get('faceEngine'));   // 換臉引擎捷徑：?faceEngine=flashhead / ditto（空字串=回預設）
    // 視覺檢查台（機器人測試員的眼睛）：?callmock=1 ＝ 直接擺出「通話中」畫面（全身合成+live 狀態），
    // 拍照模式瀏覽器拍圖驗「滿版/無紗/無框」——不連線、不出聲、純畫面。
    if (_q.get('callmock') === '1' || _q.get('photomock') === '1') setTimeout(() => { try {
      document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
      const _c = document.getElementById('chat'); _c.classList.add('active'); _c.dataset.state = 'speaking';
      if (_q.get('callmock') === '1') {   // callmock=活臉層；photomock=純底圖照片層（看有沒有上下漸層紗）
        const _f = document.getElementById('fhFrame'); if (_f) _f.hidden = false;
        document.querySelector('#chat .face-bg').classList.add('livevid');
      }
    } catch (e) {} }, 600);
  } catch (e) {}
  // 內頁真版印章：通話畫面角落顯示網頁內容真版本（防 iOS 外殼標籤新、內頁舊）。
  // 2026-07-18 Edward 拍板 A：只有開發包／我們自己在瀏覽器測時顯示，正式包一律藏——
  // 這是給打包驗版用的除錯標籤，長輩看到只會困惑（正式包＝沒有 MUNEA_DEV_CONFIG）。
  try {
    const _vs = document.getElementById('webVerStamp');
    if (_vs && window.MuneaVersion) {
      const _showStamp = (typeof isDeveloperBypassAllowed === 'function' && isDeveloperBypassAllowed())
        || (typeof isPackagedApp === 'function' && !isPackagedApp());
      _vs.textContent = _showStamp
        ? muneaT('version.webBuild', 'Web v{version}', { version: MuneaVersion.current })
        : '';
    }
  } catch (e) {}
  window.addEventListener('munea:medication-change', handleMedicationChange);
  const __pullPromise = Promise.resolve(syncPullAll());
  const __medicationPromise = __pullPromise.then(configureMedicationService);
  refreshServerPlanEntitlement();
  refreshServerCredits();
  if (_familySyncTimer) clearInterval(_familySyncTimer);
  _familySyncTimer = setInterval(() => { try { syncPullAll(); } catch (e) {} }, 120000);   // 家人動態每 2 分鐘拉一次（傳話/告警跨裝置到達）
  if (!_familyVisibilityBound) {
    _familyVisibilityBound = true;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return;
      syncPullAll({ minIntervalMs: 30000 });
      // 回到前景時也重新確認會員身分與點數（2026-07-30 Edward 抓到）。
      // 原本只有「完全關掉 App 再開」「換帳號」「點進管理方案」這三種時機才問伺服器，
      // 所以後台改了方案、手機切回來卻還是舊身分——顯示的是本機記著的值，它根本沒問過。
      // 30 秒節流，避免切來切去一直打。
      const now = Date.now();
      if (now - _lastPlanRecheckAt >= 30000) {
        _lastPlanRecheckAt = now;
        try { void refreshServerPlanEntitlement(); } catch (e) {}
        try { void refreshServerCredits(); } catch (e) {}
      }
    });
  }
  applyTaskAccessibilityLabels();
  syncCompanionUI();
  setupHscrollHints();
  renderPoints();
  updateMedCount();
  renderVisitTask();
  if (window.MuneaHealth) window.MuneaHealth.boot(); // 之前連過 Apple 健康就靜默帶回今天步數
  renderCareCarousel();
  if ($('#careBody')) $('#careBody').addEventListener('click', e => {
    const rm = e.target.closest('[data-remove]');
    if (rm) { removeFamilyFeedItem(+rm.dataset.remove); return; }
    const rp = e.target.closest('[data-report]');
    if (rp) { reportFamilyFeedItem(+rp.dataset.report); return; }
    const b = e.target.closest('.care-btn');
    if (!b) return;
    // 個人資料那則不換頁，開的是同一張 #profileModal（一般模式），跟設定頁的「個人資料」入口共用同一顆
    if (b.dataset.go === 'profile') { fillPersonProfile(); $('#profileModal').classList.add('show'); return; }
    showView(b.dataset.go === 'status' ? 'status' : 'family');
  });
  if (location.hash.slice(1) === 'pick') {
    const sheet = $('#companionSheet');
    const mask = sheet && sheet.closest('.modal-mask');
    if (mask) { showView('settings'); mask.classList.add('show'); }
  }
  // 關閉聊聊（X）＝有通話先掛斷結算，再回首頁；沒通話就直接回
  if ($('#chatExit')) $('#chatExit').addEventListener('click', () => {
    if (callConnected || callDialing || callPreflightPending) {   // 排隊／前置中離開也要真取消，不留幽靈佔位
      const wasConnected = callConnected;
      LiveVoice.stop(); completeChatSession(wasConnected ? 'user_ended' : 'user_cancelled'); chatOpened = false; setCallToggle(false); if (window.__muneaStopListen) window.__muneaStopListen();
      if (wasConnected) {
        try { const n = +(localStorage.getItem('munea.stat.chatsCompleted') || 0) + 1; localStorage.setItem('munea.stat.chatsCompleted', String(n)); } catch (e2) {}
        setTimeout(() => window.__muneaMaybeAskReview('chat_completed'), 800);   // 自己掛斷＝好好聊完 → 開心時刻
      }
    }
    if (typeof exitTextFallbackChat === 'function') exitTextFallbackChat();   // 離開時順手收掉「先用文字聊」面板，下次進來是乾淨的通話畫面
    FaceWave.stop();
    showView('home');
  });
  // iOS WebView 在音訊路由／系統面板切換時可能短暫 hidden。舊版立刻 click 掛斷，會把
  // 短暫切換誤當成使用者離開。改成穩定背景 5 秒才收線；回前景就取消。
  let _hangupOnLeaveT = null;
  const _cancelHangupOnLeave = () => { clearTimeout(_hangupOnLeaveT); _hangupOnLeaveT = null; };
  const _hangupOnLeave = (source = 'visibility_hidden') => {
    _cancelHangupOnLeave();
    if (!(callConnected || callDialing || callPreflightPending)) return;
    _hangupOnLeaveT = setTimeout(() => {
      _hangupOnLeaveT = null;
      if (document.visibilityState !== 'hidden') return;
      try { trackProductEvent('voice_background_release', { source, hiddenMs: 5000 }); } catch (e) {}
      try { if ((callConnected || callDialing || callPreflightPending) && $('#callToggle')) $('#callToggle').click(); } catch (e) {}
    }, 5000);
  };
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') _hangupOnLeave('visibility_hidden');
    else { _cancelHangupOnLeave(); try { LiveVoice._resumeAudio(); } catch (e) {} }
  });
  window.addEventListener('pagehide', () => _hangupOnLeave('pagehide'));
  // 忙線／失敗卡按鈕：排隊＝取消排隊（走通話鍵同一條取消線）；登入失效＝重新登入；其餘＝知道了、收卡
  if ($('#busyCardBtn')) $('#busyCardBtn').addEventListener('click', () => {
    const card = $('#busyCard'); const action = card && card.dataset.action;
    hideBusyCard();
    if (action === 'cancel' && !callConnected && (callDialing || callPreflightPending)) { try { $('#callToggle').click(); } catch (e) {} }
    else if (action === 'reopen-auth') { setTimeout(() => { try { openAuthSheet(); } catch (e2) {} }, 0); }
  });
  // 全滿出口（2026-07-24 P0）：不用乾等 GPU 席位，先切去既有 /chat 文字管線聊
  if ($('#busyCardAlt')) $('#busyCardAlt').addEventListener('click', () => {
    hideBusyCard();
    if (typeof startTextFallbackChat === 'function') startTextFallbackChat();
  });
  if ($('#callToggle')) $('#callToggle').addEventListener('click', () => {
    // 撥通中（含排隊／前置連線）再按一次＝取消撥號、回到待機
    if ((callDialing || callPreflightPending) && !callConnected) {
      LiveVoice.stop(); FaceWave.stop(); completeChatSession('user_cancelled'); chatOpened = false;
      setCallToggle(false); stopCallTimer();
      const chatEl = document.getElementById('chat'); if (chatEl) chatEl.dataset.state = 'idle';
      setFaceState('idle'); if (window.__muneaStopListen) window.__muneaStopListen();
      FaceIdle.start();
      return;
    }
    // 訪客按「開始通話」＝立刻跳登入，不要先問跨境同意／聊天話題再回頭要他登入（那順序很莫名）。
    // connectCall 開頭也有同一道關卡兜底，這裡是為了把提示提早到第一次點擊。
    if (!callConnected && !isLoggedIn()) {
      requireLogin(muneaT(
        'auth.chatSignInRequired',
        '請先使用 Google 或 Apple 登入才能使用聊聊；免費帳號會收到一次性 5 點，約 5 分鐘',
      ), 'chat');
      return;
    }
    if (!callConnected && !localStorage.getItem('munea.consent.crossborder')) { $('#consentSheet').classList.add('show'); return; }
    // 第一次開聊前輕問一次「想聊什麼話題」（可跳過、之後在設定隨時改；只問這一次）
    if (!callConnected && !localStorage.getItem('munea.interestsAsked') && !loadInterests().length && window.__muneaOpenInterests) { window.__muneaOpenInterests(true); return; }
    if (!callConnected) { connectCall(); }
    else { LiveVoice.stop(); FaceWave.stop(); completeChatSession('user_ended'); chatOpened = false; setCallToggle(false); if (window.__muneaStopListen) window.__muneaStopListen(); FaceIdle.start(); }
  });
  if ($('#captionToggle')) $('#captionToggle').addEventListener('click', () => {
    captionsOn = !captionsOn;
    try { localStorage.setItem('munea.captions', captionsOn ? '1' : '0'); } catch (e) {}
    applyCaptionState();
    toast(captionsOn
      ? muneaT('voice.caption.enabled', '字幕已開啟')
      : muneaT('voice.caption.disabled', '字幕已關閉'));
  });
  applyCaptionState();
  localizeChatControls();
  localizeMedicationSurfaces();
  enableSheetDrag();               // 所有彈窗支援下拉關閉手勢
  refreshTaskProgress();
  restoreFamilyFeed();
  applyDeveloperBypass();
  setupAuthControls();
  setupAiProviderConsentControls();
  if (window.MuneaAuth && typeof window.MuneaAuth.init === 'function') {
    const authInit = window.MuneaAuth.init();
    if (authInit && typeof authInit.then === 'function') authInit.then(updateAuthUI).catch(updateAuthUI);
  }
  window.addEventListener('munea:auth-state', e => {
    const detail = e.detail || {};
    updateAuthUI();
    if (detail.status === 'signed-in') {
      closeAuthSheet();
      syncAccountBootstrap('create', { reason: 'auth_signed_in', force: true })
        .then(result => { if (result && result.ok) refreshServerCredits(); return syncPersonProfileCloud(); })
        .then(() => { maybeShowFirstRunProfilePrompt(); renderFreeMemberBadge(); })
        .catch(() => {});
    } else {
      POINTS.serverRemaining = null;
      renderPoints();
    }
    if (detail.status === 'signed-in') {
      try { if (window.MuneaHealth && typeof window.MuneaHealth.refresh === 'function') window.MuneaHealth.refresh(); } catch (e) {}
    }
    configureMedicationService();
  });
  loadCompanionProfileFromBackend().finally(() => {
    if (storageGet(ONBOARDING_COMPLETED_KEY) === 'true' || storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'pending-auth') {
      syncAccountBootstrap('create', { reason: 'app_init' });
    }
  });
  avatarRuntime.setState('idle');
  $('#tabBar').addEventListener('click', e => { const b = e.target.closest('.tab-btn'); if (b) showView(b.dataset.view); });
  renderAiDiagnostics();
  if ($('#aiDevRefresh')) $('#aiDevRefresh').addEventListener('click', () => refreshAiDiagnostics());

  // 首頁「跟寧寧聊聊」＝ 進全屏臉「待命」；使用者自己按「開始通話」才啟動、才開始扣點（Edward 7/7：不自動通話）
  if ($('#startCall')) $('#startCall').addEventListener('click', () => {
    // 訪客直接進聊聊頁（Edward 2026-07-30），登入關卡留到頁內按「開始通話」那一刻。
    // 已登入的人維持原本的點數／方案把關——先擋在首頁，免得進去了才發現沒點數可撥。
    if (isLoggedIn()) {
      if (window.MMPLAN && window.MMPLAN.isFree()) { if (window.MMPLAN.chatRemainSec() <= 0) { window.MMPLAN.upsell('chat-daily'); return; } }
      else if (typeof ptsLeft === 'function' && ptsLeft() <= 0) { __muneaShowPointsPopup(); return; }
    }
    showView('chat');
  });
  // （提醒改為彈窗版；埋點併入 B1 排程處理器）

  // 連接裝置（狀態頁資料條 / 設定裝置區 → 串接三方裝置引導）
  if ($('#srcStrip')) $('#srcStrip').addEventListener('click', () => { window.__connectFrom = 'status'; showView('connect'); });
  if ($('#setDevices')) $('#setDevices').addEventListener('click', () => { window.__connectFrom = 'settings'; showView('connect'); });
  if ($('#companionRow')) $('#companionRow').addEventListener('click', () => $('#companionSheet').classList.add('show'));
  if ($('#companionCloseBtn')) $('#companionCloseBtn').addEventListener('click', () => $('#companionSheet').classList.remove('show'));
  if ($('#quizCloseX')) $('#quizCloseX').addEventListener('click', () => $('#quizModal').classList.remove('show'));
  if ($('#companionSheet')) $('#companionSheet').addEventListener('click', e => { if (e.target === $('#companionSheet')) $('#companionSheet').classList.remove('show'); });
  const RT_DEF = { b: '07:30', l: '12:00', d: '18:00', s: '22:00' };
  function loadRoutine() { try { return Object.assign({}, RT_DEF, JSON.parse(localStorage.getItem('munea.routine') || '{}')); } catch (e) { return Object.assign({}, RT_DEF); } }
  function saveRoutine(rt) { try { localStorage.setItem('munea.routine', JSON.stringify(rt)); } catch (e) {} syncPush('routine', rt); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  function shiftTime(t, mins) {
    let [h, m] = t.split(':').map(Number);
    let total = (h * 60 + m + mins + 1440) % 1440;
    return String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
  }
  let _pfPendingAvatar = '';
  const PF_DEF = { name: '', nick: '', birth: '', city: '', country: '', updatedAt: '' };   // 7/9 正式化：不再預設示範身分（陳秀英/阿嬤）——空欄位＋提示字自己填；updatedAt 給雲端合併判斷「較新者勝」用（2026-07-24）
  function loadPersonProfile() { try { return Object.assign({}, PF_DEF, JSON.parse(localStorage.getItem('munea.personProfile') || '{}')); } catch (e) { return Object.assign({}, PF_DEF); } }
  // 所在地：不叫長輩填表——聊天講過一次她就記起來（2026-07-31 Edward 拍板）。
  // 這裡只做兩件事：把她記得的顯示出來、讓他改得掉（個資法：用戶有權查看與更正）。
  // 各國行政區清單沒有消失，只是換了用途——從「給用戶挑」變成引擎那側
  // 「聽到的地名對回哪個縣市」的對照（世田谷区→東京都才報得出天氣）。
  function fillPfLocation(city) {
    const box = $('#pfCityFree');
    if (box) box.value = (city || '').trim();
    const hint = $('#pfLocationHint');
    if (hint) {
      hint.textContent = (city || '').trim()
        ? muneaT('profile.locationEditHint', '打錯或搬家了，在這裡改就好')
        : muneaT('profile.locationNotYet', '還沒聊到——聊天時說一次就好，她會記起來');
    }
  }
  function pfLocationValue() { return (($('#pfCityFree') && $('#pfCityFree').value) || '').trim(); }
  function pfCountryValue() { return (loadPersonProfile().country || '').toUpperCase(); }
  // 舊資料相容：以前存的是「台北市大安區」這種合成字串，拆回縣市＋區給雲端欄位用。
  // 拆不出來也沒關係——整串原文照樣送上去，引擎那側自己會對照。
  function parsePfCity(city) {
    const text = (city || '').trim();
    const book = (window.MUNEA_REGIONS && window.MUNEA_REGIONS.TW) || null;
    if (!text || !book) return { county: '', district: text };
    for (const county of Object.keys(book.regions)) {
      if (text.indexOf(county) === 0) {
        return { county, district: text.slice(county.length).replace(/^[,\s]+/, '') };
      }
    }
    return { county: '', district: text };
  }

  function fillPersonProfile() {
    const p = loadPersonProfile();
    if ($('#pfName')) $('#pfName').value = p.name;
    if ($('#pfNick')) $('#pfNick').value = p.nick;
    const ys = $('#pfBirthY'), ms = $('#pfBirthM');
    if (ys && !ys.options.length) {
      const nowY = new Date().getFullYear();
      let yh = '';
      for (let y = nowY - 5; y >= 1920; y--) yh += '<option value="' + y + '">' + muneaT('profile.yearOption', '{year} 年', { year: y }) + '</option>';
      ys.innerHTML = yh;
      let mh = '';
      for (let m = 1; m <= 12; m++) mh += '<option value="' + m + '">' + muneaT('profile.monthOption', '{month} 月', { month: m }) + '</option>';
      ms.innerHTML = mh;
    }
    const mt = String(p.birth || '').match(/(19|20)(\d{2}).*?(\d{1,2})/);
    if (ys) ys.value = mt ? mt[1] + mt[2] : '1954';
    if (ms) ms.value = mt ? String(+mt[3]) : '3';
    fillPfLocation(p.city);
    _pfPendingAvatar = p.avatar || '';
    if (typeof renderPfAvatar === 'function') renderPfAvatar(p.avatar, p.nick);
  }
  // 個人資料上雲同步（開帳與個人資料重整 2026-07-24 拍板）：本機 schema（birth="YYYY 年 M 月"字串、
  // city=縣市＋區合併字串）跟 Brain /person-profile 的結構化欄位（birthYear/birthMonth/county/district）
  // 互轉，換裝置登入同帳號資料都在；照片不上雲（沿用需求單拍板）。
  function personProfileToCloudPayload(p) {
    const my = p || loadPersonProfile();
    const ym = String(my.birth || '').match(/(\d{4}).*?(\d{1,2})/);
    const loc = parsePfCity(my.city || '');
    return {
      name: my.name || '',
      nick: my.nick || '',
      birthYear: ym ? parseInt(ym[1], 10) : null,
      birthMonth: ym ? parseInt(ym[2], 10) : null,
      county: loc.county || '',
      district: loc.district || '',
      country: (my.country || '').toUpperCase() || '',
      updatedAt: my.updatedAt || '',
    };
  }
  function cloudProfileToLocal(cloud, existing) {
    const base = existing || loadPersonProfile();
    const cloudCountry = (cloud.country || base.country || '').toUpperCase();
    // 中日地名直接相連、西英中間空白（跟 pfLocationValue 同一條規矩）
    const cityJoin = (cloudCountry === 'JP' || cloudCountry === 'TW' || !cloudCountry) ? '' : ' ';
    const city = cloud.county ? (cloud.county + (cloud.district ? cityJoin + cloud.district : '')) : base.city;
    const birth = cloud.birthYear ? (cloud.birthYear + ' 年 ' + (cloud.birthMonth || 1) + ' 月') : base.birth;
    return Object.assign({}, base, {
      name: cloud.name || base.name,
      nick: cloud.nick || base.nick,
      birth: birth,
      city: city,
      country: cloudCountry || base.country || '',
      updatedAt: cloud.updatedAt || base.updatedAt,
    });
  }
  function pushPersonProfileToCloud(p) {
    if (isStaticPreview() || usesDevelopmentDirectCall() || !isLoggedIn()) return Promise.resolve(null);
    return brainPost('/person-profile', { action: 'save', profile: personProfileToCloudPayload(p) }).catch(() => null);
  }
  let _personProfileCloudSyncPromise = null;
  // 開機／登入後跑一次：雲端有較新資料就合併回本機（換裝置場景）；
  // 本機比雲端新（或雲端根本沒資料）就把本機資料補上雲（既有用戶/離線先存的場景）。
  function syncPersonProfileCloud() {
    if (isStaticPreview() || usesDevelopmentDirectCall() || !isLoggedIn()) return Promise.resolve(null);
    if (_personProfileCloudSyncPromise) return _personProfileCloudSyncPromise;
    _personProfileCloudSyncPromise = (async () => {
      try {
        const resp = await brainPost('/person-profile', { action: 'load' });
        const cloud = resp && resp.ok && resp.profile ? resp.profile : null;
        const local = loadPersonProfile();
        const localAt = local.updatedAt ? (Date.parse(local.updatedAt) || 0) : 0;
        const cloudAt = cloud && cloud.updatedAt ? (Date.parse(cloud.updatedAt) || 0) : 0;
        const cloudHasData = !!(cloud && (cloud.nick || cloud.name || cloud.county || cloud.birthYear));
        const localHasData = personProfileHasData(local);
        if (cloudHasData && cloudAt >= localAt) {
          const merged = cloudProfileToLocal(cloud, local);
          try { localStorage.setItem('munea.personProfile', JSON.stringify(merged)); } catch (e) {}
          if (typeof applyUserAvatar === 'function') applyUserAvatar();
          return merged;
        }
        if (localHasData && (!cloudHasData || localAt > cloudAt)) {
          if (!local.updatedAt) {
            local.updatedAt = new Date().toISOString();
            try { localStorage.setItem('munea.personProfile', JSON.stringify(local)); } catch (e) {}
          }
          await pushPersonProfileToCloud(local);
          return local;
        }
        return local;
      } catch (e) {
        return null;
      }
    })();
    return _personProfileCloudSyncPromise.finally(() => { _personProfileCloudSyncPromise = null; });
  }
  // 首登一次性彈個人資料卡（Edward 2026-07-24 拍板）：關掉首登視覺（banner＋跳過鈕），
  // 回到「一般模式」（設定頁點『個人資料』進來時用的就是這個乾淨版）。
  function closeProfileFirstRunUi() {
    const banner = $('#pfFirstRunBanner'); if (banner) banner.hidden = true;
    const disclosure = $('#pfFirstRunDisclosure'); if (disclosure) disclosure.hidden = true;
    const skip = $('#pfSkipBtn'); if (skip) skip.hidden = true;
    const modal = $('#profileModal'); if (modal) modal.classList.remove('pf-first-run');
  }
  function openProfileModalFirstRun() {
    fillPersonProfile();
    // 名稱預填：Google/Apple 帳號帶的名字（使用者還沒填過個人資料時，這是唯一能預填的來源）。
    try {
      const st = authState();
      const nameInput = $('#pfName');
      if (nameInput && !nameInput.value && st && st.name) nameInput.value = String(st.name).trim().slice(0, 12);
    } catch (e) {}
    const banner = $('#pfFirstRunBanner');
    if (banner) {
      banner.textContent = muneaT('profile.firstRunBanner', '填了這些，{companion}會用你習慣的稱呼、合你的節奏跟你說話，也能報你那邊的天氣。', { companion: cname() });
      banner.hidden = false;
    }
    // 沙利曼 Gate 5：資料在按「存好」當下就上傳，告知必須早於上傳（放在存好鈕正上方），
    // 不能只靠聊聊前的同意卡把關——那時個人資料早就已經存過雲了。
    const disclosure = $('#pfFirstRunDisclosure'); if (disclosure) disclosure.hidden = false;
    const skip = $('#pfSkipBtn'); if (skip) skip.hidden = false;
    const modal = $('#profileModal');
    if (modal) { modal.classList.add('pf-first-run'); modal.classList.add('show'); }
    storageSet(PERSON_PROFILE_PROMPT_KEY, 'true');
    try { trackProductEvent('person_profile_first_prompt_shown', {}); } catch (e) {}
  }
  // 登入成功＋帳號 bootstrap＋雲端個人資料合併都跑完才判斷要不要彈：
  // 已問過＝不管；還沒問過但（本機或剛從雲端合併回來的）資料已經有內容＝視同舊用戶問過，靜靜補記旗標、不彈；
  // 真的全空白才是「首登真新用戶」，這時才彈。
  function maybeShowFirstRunProfilePrompt() {
    if (!isLoggedIn()) return;
    if (storageGet(PERSON_PROFILE_PROMPT_KEY) === 'true') { syncProfileNudge(); return; }
    if (personProfileHasData(loadPersonProfile())) {
      storageSet(PERSON_PROFILE_PROMPT_KEY, 'true');
      syncProfileNudge();
      return;
    }
    openProfileModalFirstRun();
  }
  if ($('#pfSaveBtn')) $('#pfSaveBtn').addEventListener('click', () => {
    const p = {
      name: ($('#pfName').value || '').trim() || PF_DEF.name,
      nick: ($('#pfNick').value || '').trim() || PF_DEF.nick,
      birth: ($('#pfBirthY') && $('#pfBirthY').value ? $('#pfBirthY').value + ' 年 ' + $('#pfBirthM').value + ' 月' : PF_DEF.birth),
      city: pfLocationValue() || PF_DEF.city,
      country: pfCountryValue(),
      avatar: _pfPendingAvatar,
      updatedAt: new Date().toISOString(),
    };
    try { localStorage.setItem('munea.personProfile', JSON.stringify(p)); } catch (e) {}
    if (typeof applyUserAvatar === 'function') applyUserAvatar();
    pushPersonProfileToCloud(p);
    closeProfileFirstRunUi();
    storageSet(PERSON_PROFILE_PROMPT_KEY, 'true');
    syncProfileNudge();
    $('#profileModal').classList.remove('show');
    toast(p.name ? muneaT('profile.savedWithName', '存好了，{name}，資料我記著。', { name: p.name }) : muneaT('profile.savedToast', '存好了，資料我記著。'));
  });
  if ($('#pfSkipBtn')) $('#pfSkipBtn').addEventListener('click', () => {
    closeProfileFirstRunUi();
    storageSet(PERSON_PROFILE_PROMPT_KEY, 'true');
    $('#profileModal').classList.remove('show');
    syncProfileNudge();
    try { trackProductEvent('person_profile_first_prompt_skipped', {}); } catch (e) {}
  });
  // 2026-07-28：獨立小卡的「點卡片」與「關閉 X」兩顆事件隨小卡一起退役——
  // 提醒改由「幫你留意」輪播的 .care-btn[data-go=profile] 接手（見上方 #careBody 的處理）。
  if ($('#profileRow')) $('#profileRow').addEventListener('click', () => { fillPersonProfile(); $('#profileModal').classList.add('show'); });
  if ($('#profileClose')) $('#profileClose').addEventListener('click', () => $('#profileModal').classList.remove('show'));
  if ($('#profileModal')) $('#profileModal').addEventListener('click', e => { if (e.target === $('#profileModal')) $('#profileModal').classList.remove('show'); });
  function renderPfAvatar(av, nick) {
    const box = $('#pfAvatar'); if (!box) return;
    box.style.backgroundImage = av ? 'url(' + av + ')' : '';
    box.classList.toggle('has-photo', !!av);
    if ($('#pfAvatarClear')) $('#pfAvatarClear').hidden = !av;
  }
  function resizeAvatar(file, cb, onErr) {
    if (!looksLikeImage(file)) { if (onErr) onErr(); return; }
    const r = new FileReader();
    r.onerror = () => { if (onErr) onErr(); };
    r.onload = () => { const img = new Image(); img.onload = () => { try { const max = 320; let w = img.width, h = img.height; const sc = Math.min(max / w, max / h, 1); const cv = document.createElement('canvas'); cv.width = Math.max(1, Math.round(w * sc)); cv.height = Math.max(1, Math.round(h * sc)); cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height); cb(canvasToJpeg(cv)); } catch (e) { if (onErr) onErr(); } }; img.onerror = () => { if (onErr) onErr(); }; img.src = r.result; };
    r.readAsDataURL(file);
  }
  function applyUserAvatar() {
    let av = ''; try { av = (JSON.parse(localStorage.getItem('munea.personProfile') || '{}')).avatar || ''; } catch (e) {}
    // 還沒上傳照片就用帳號的頭像（Google／Apple 登入時就帶回來了 · Edward 2026-07-30）——
    // 剛登入的人不必先去填個人資料才有臉。自己上傳過的永遠優先。
    if (!av) {
      try {
        const st = authState();
        const meta = (st && st.user && st.user.user_metadata) || {};
        if (st && st.status === 'signed-in') av = st.avatarUrl || meta.avatar_url || meta.picture || meta.photo_url || '';
      } catch (e) {}
    }
    document.querySelectorAll('.init-ava.p-ama').forEach(el => {
      if (av) { el.style.backgroundImage = 'url(' + av + ')'; el.style.backgroundSize = 'cover'; el.style.backgroundPosition = 'center'; el.style.color = 'transparent'; }
      else { el.style.backgroundImage = ''; el.style.color = ''; }
    });
    renderAuthAvatar(authState(), isLoggedIn());
  }
  window.__muneaApplyUserAvatar = applyUserAvatar;
  if ($('#pfAvatarBtn')) $('#pfAvatarBtn').addEventListener('click', () => { if ($('#pfAvatarFile')) $('#pfAvatarFile').click(); });
  if ($('#pfAvatarFile')) $('#pfAvatarFile').addEventListener('change', e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (!f) return; const box = $('#pfAvatar'); if (box) box.classList.add('processing'); resizeAvatar(f, dataUrl => { if (box) box.classList.remove('processing'); _pfPendingAvatar = dataUrl; renderPfAvatar(dataUrl); }, () => { if (box) box.classList.remove('processing'); toast(muneaT('profile.photoUnreadable', "這張照片讀不到，換一張相簿裡的照片試試")); }); });
  if ($('#pfAvatarClear')) $('#pfAvatarClear').addEventListener('click', () => { _pfPendingAvatar = ''; renderPfAvatar('', ($('#pfNick') && $('#pfNick').value) || '我'); });
  applyUserAvatar();
  // 全家健康圈
  // Edward 2026-07-31 拍板：免費也能有 1 位家人（本人＋1＝2）。
  // 原本免費＝只有自己，等於免費版根本沒有家庭圈——那個分頁打開永遠是空的，
  // 使用者體驗不到價值就不會想升級。付費牆本來就在點數（免費只有一次 5 分鐘），不在人數。
  // 2 人＝一對夫妻／一對親子夠體驗，三代同堂或多個子女輪流照顧就得升 Plus，分界剛好。
  const CIRCLE_LIMITS = { free: 2, plus: 4, pro: 12 };                       // 含本人：免費 2、Plus 4、Pro 12
  const circlePlanLabel = plan => plan === 'free' ? muneaT('subscription.planFree', '免費') : plan === 'pro' ? 'Pro' : 'Plus';
  const PLAN_POINTS = { free: 0, plus: 100, pro: 200 };                       // 每月贈點（2026-07-17 Edward 拍板：每分鐘 6 元錨）
  function circlePlan() { try { return localStorage.getItem('munea.plan') || 'free'; } catch (e) { return 'free'; } }
  // 全家健康圈：就是一個家庭、大家平等（不分發起人/付款人/照護對象）；本人只標「本人」、其他人可移除
  // 7/9 正式化：不再預設示範四人家庭——圈子從「只有本人」開始，家人用邀請碼真的加進來
  // 剛登入、還沒填個人資料的人也要有像樣的身分（Edward 2026-07-30）：
  // 取名順序＝個人資料的名稱／稱呼 → 帳號帶回來的真名（Google／Apple 登入時就給了）→ 「我」。
  // 刻意不用 email 前綴當名字（authDisplayName 會退到那步）——「edwardt0303」不是人願意被叫的稱呼，
  // 印在家庭名單上更怪。填了個人資料就永遠以個人資料為準。
  function selfAccountName() {
    try {
      const st = authState();
      if (st && st.status === 'signed-in' && st.name) return String(st.name).trim();
    } catch (e) {}
    return '';
  }
  function circleSelfMember() {
    let nm = '';
    try { const p = JSON.parse(localStorage.getItem('munea.personProfile') || '{}'); nm = (p.name || p.nick || '').trim(); } catch (e) {}
    if (!nm) nm = selfAccountName();
    const ini = (nm || muneaT('common.meInitial', '我'))[0] || muneaT('common.meInitial', '我');
    return { name: nm || muneaT('common.meInitial', '我'), init: ini, tint: 'p-ama', self: true };
  }
  // 本人那筆的稱呼與頭像一律以「個人資料」為準（Edward 2026-07-30 在名單上看到英文「Primary user」）。
  // 為什麼要覆寫：雲端同步回來的家庭圈成員，後端對本人的預設名是英文 "Primary user"
  //（engine/server.py 與 supabase_adapter.py 的 displayName 兜底值），會蓋掉使用者自己填的稱呼，
  // 連頭像首字母都跟著變成「P」。本人是誰只有他自己說得準，不該讓後端的兜底值改寫。
  // tint 也一起釘回 p-ama——照片是靠 applyUserAvatar() 找 .init-ava.p-ama 套上去的，換了色就套不到。
  function loadCircle() {
    let arr = [];
    try { const v = JSON.parse(localStorage.getItem('munea.circleMembers')); if (Array.isArray(v)) arr = v; } catch (e) {}
    if (!arr.length) return [circleSelfMember()];
    const me = circleSelfMember();
    // 每個畫面都經過這裡，所以配色放在這一關——不管名單是雲端來的、舊版存的、
    // 還是根本沒帶顏色，拿到手的一定是「八個真的存在的色號、同一家人不撞色」。
    return muneaAssignTints(arr.map(m => (m && m.self) ? Object.assign({}, m, { name: me.name, init: me.init, tint: me.tint }) : m));
  }
  function saveCircle(a2) {
    try { localStorage.setItem('munea.circleMembers', JSON.stringify(a2)); } catch (e) {}
    syncPush('circle', a2.map(m => ({ name: m.name, personId: m.personId, relationship: m.relationship, init: m.init, tint: m.tint })));   // 本人標記不上雲；personId 保留給指定收件人的傳話
  }
  window.__muneaAfterCircleSync = function () { try { renderFamRoster(); renderFcRoster(); updateSafetyCount(); } catch (e) {} };
  function renderFcRoster() {
    const box = $('#fcRoster'); if (!box) return;
    const members = loadCircle(); const plan = circlePlan(); const limit = CIRCLE_LIMITS[plan] || 4;
    const cnt = $('#fcCount'); if (cnt) cnt.textContent = members.length + '/' + limit + ' · ' + circlePlanLabel(plan);
    box.innerHTML = members.map(m => {
      const action = m.self
        ? `<span class="fc-you">${muneaT('familyCircle.you', '本人')}</span>`
        : `<button type="button" class="fc-remove" data-name="${m.name}">${muneaT('familyCircle.remove', '移除')}</button>`;
      return '<div class="rl"><span class="init-ava ' + muneaSafeTint(m.tint, m.name) + '">' + m.init + '</span><b>' + m.name + '</b>' + action + '</div>';
    }).join('');
    if (typeof window.__muneaApplyUserAvatar === 'function') window.__muneaApplyUserAvatar();
    // 「退出這個健康圈」只在圈裡真的還有別人時才給（Edward 2026-07-30）：
    // 圈裡只剩自己一個人的時候，沒有圈可以退——按下去只會把自己從自己的名單移除，
    // 對使用者來說就是「按了沒事發生」。這種按鍵擺在那裡只會讓人以為壞掉。
    const leave = $('#fcLeaveBtn');
    if (leave) leave.hidden = members.filter(m => !m.self).length === 0;
    const inv = $('#fcInviteBtn');
    if (inv) {
      const full = members.length >= limit;
      inv.textContent = full
        ? muneaT('familyCircle.limitReached', '{plan} 已達上限 · 升級可加更多', {
          plan: circlePlanLabel(plan),
        })
        : muneaT('familyCircle.invite', '邀請家人加入');
      inv.dataset.full = full ? '1' : '';
    }
    const note = $('#invLimitNote');
    if (note) note.textContent = muneaT(
      'invite.planLimit',
      '目前 {plan} 方案 · 家庭健康圈最多 {limit} 人',
      { plan: circlePlanLabel(plan), limit },
    );
  }
  // 移除家人：點一下「移除」→變紅「確定移除」、再點才移（App 內確認、不用系統醜彈窗）
  if ($('#fcRoster')) $('#fcRoster').addEventListener('click', e => {
    const rm = e.target.closest('.fc-remove'); if (!rm) return;
    if (rm.dataset.arm !== '1') {
      rm.dataset.arm = '1';
      rm.classList.add('arm');
      rm.textContent = muneaT('familyCircle.confirmRemove', '確定移除');
      setTimeout(() => {
        rm.dataset.arm = '';
        rm.classList.remove('arm');
        rm.textContent = muneaT('familyCircle.remove', '移除');
      }, 3000);
      return;
    }
    saveCircle(loadCircle().filter(m => m.name !== rm.dataset.name));
    renderFcRoster(); renderFamRoster(); updateSafetyCount();   // 家人頁與緊急聯絡人跟著同步（單一名單）
    toast(muneaT('familyCircle.removedToast', '已把 {name} 移出全家健康圈。', { name: rm.dataset.name }));
  });
  // 免費也能加入別人的圈（Edward 2026-07-31）：不開這道，免費 A 邀請免費 B 時 B 會被擋在門外，
  // 邀請發得出去卻沒人接得到＝整件事失效。人數由圈主的方案決定，伺服器端另有 circle_full 把關。
  if ($('#fcJoinBtn')) $('#fcJoinBtn').addEventListener('click', () => { if (!requireLoginForFamily(muneaT('familyCircle.joinLoginPrompt', '要加入家人的健康圈，先登入一下（換手機也找得回來）'))) return; $('#famCircleModal').classList.remove('show'); if ($('#joinCircleModal')) $('#joinCircleModal').classList.add('show'); });
  if ($('#joinCircleClose')) $('#joinCircleClose').addEventListener('click', () => $('#joinCircleModal').classList.remove('show'));
  if ($('#joinCircleModal')) $('#joinCircleModal').addEventListener('click', e => { if (e.target === $('#joinCircleModal')) $('#joinCircleModal').classList.remove('show'); });
  if ($('#joinCircleBtn')) $('#joinCircleBtn').addEventListener('click', async () => {
    if (!requireLoginForFamily(muneaT('familyCircle.loginToJoin', '要加入家人的健康圈，先登入一下'))) return;   // 雙保險：訪客不能入別人的圈
    // 2026-07-31：免費也能加入別人的圈（見上方 #fcJoinBtn 的說明）。人數上限由圈主的方案決定，
    // 伺服器端 accept 那關會用邀請碼帶的 maxMembers 擋 circle_full，這裡不重複判斷。
    const code = ($('#joinCodeInput').value || '').trim();
    if (!code || code.replace(/\D/g, '').length < 4) { toast(muneaT('familyCircle.invitePlaceholderHint', "把家人給你的邀請碼打進去（例：MUNEA-284753）")); return; }
    const btn = $('#joinCircleBtn');
    if (typeof setBtnBusy === 'function') setBtnBusy(btn, muneaT('familyCircle.joining', '加入中'));
    try {
      const p = loadPersonProfile();
      // Use the common API helper so the verified bearer token is sent.  A
      // join code proves an invitation, never the caller's identity.
      const j = await brainPost('/family/invitations', { action: 'accept', shortCode: code, inviteeName: p.nick || p.name || '' });
      if (j && j.ok && j.invitation && j.invitation.familyGroupId) {
        try { localStorage.setItem('munea.familyGroupId', j.invitation.familyGroupId); } catch (e) {}
        // 把自己掛進這家的圈名單（雲端），對方裝置拉回來就看得到你
        await syncPullAll();
        const mem = loadCircle();
        const meName = p.nick || p.name || muneaT('common.meInitial', '我');
        if (!mem.some(m => m.name === meName)) { mem.push({ name: meName, init: meName[0], tint: 'p-bao', self: true }); saveCircle(mem); }
        renderFamRoster(); renderFcRoster();
        $('#joinCircleModal').classList.remove('show'); $('#joinCodeInput').value = '';
        toast(muneaT('familyCircle.joinedToast', "加入了！你們現在在同一個全家健康圈，動態會互相看得到。"));
      } else if (j && j.error === 'invitation_expired') {
        toast(muneaT('familyCircle.inviteExpiredToast', "這組邀請碼過期了，請家人重新產一組給你。"));
      } else if (j && j.error === 'circle_full') {
        toast(muneaT('familyCircle.circleFullToast', "這個全家健康圈人數已滿，請家人升級方案後再邀請你。"));
      } else {
        toast(muneaT('familyCircle.inviteCodeNotFound', '找不到這組邀請碼，跟家人核對一下數字。'));
      }
    } catch (e) {
      toast(muneaT('common.cloudRetryToast', '現在連不上雲端，等網路好一點再試一次。'));
    }
    if (typeof clearBtnBusy === 'function') clearBtnBusy(btn); else if (btn) btn.textContent = muneaT('familyCircle.joinCircleButton', '加入全家健康圈');
  });
  if ($('#fcLeaveBtn')) $('#fcLeaveBtn').addEventListener('click', () => {
    const b = $('#fcLeaveBtn');
    if (b.dataset.arm !== '1') { b.dataset.arm = '1'; b.classList.add('arm'); b.textContent = muneaT('familyCircle.leaveConfirm', '再按一次確認退出'); setTimeout(() => { b.dataset.arm = ''; b.classList.remove('arm'); b.textContent = muneaT('familyCircle.leaveAction', '退出這個健康圈'); }, 4000); return; }
    b.dataset.arm = ''; b.classList.remove('arm'); b.textContent = muneaT('familyCircle.leaveAction', '退出這個健康圈');
    $('#famCircleModal').classList.remove('show');
    toast(muneaT('familyCircle.leftToast', '已退出這個健康圈。想再回來，請家人重新邀請你。'));
  });
  if ($('#famCircleRow')) $('#famCircleRow').addEventListener('click', () => { renderFcRoster(); $('#famCircleModal').classList.add('show'); });
  // 移除家人／封鎖入口也放在家人頁顯眼處（不用鑽進設定才找得到，Edward 7/9 UGC 審核要求）——開的是同一個管理視窗
  if ($('#famManageBtn')) $('#famManageBtn').addEventListener('click', () => { renderFcRoster(); $('#famCircleModal').classList.add('show'); });
  if ($('#famCircleClose')) $('#famCircleClose').addEventListener('click', () => $('#famCircleModal').classList.remove('show'));
  if ($('#famCircleModal')) $('#famCircleModal').addEventListener('click', e => { if (e.target === $('#famCircleModal')) $('#famCircleModal').classList.remove('show'); });
  // 免費也能邀請（Edward 2026-07-31）：不再一律擋，改成只有「圈滿了」才擋——
  // 免費上限 2（本人＋1 位），滿了照樣提示升級，所以升級動機沒有被拿掉，只是往後移了一位。
  if ($('#fcInviteBtn')) $('#fcInviteBtn').addEventListener('click', e => { if (!requireLoginForFamily(muneaT('familyCircle.loginToInvite', '要邀請家人連上你，先登入一下（這樣家人才連得到你）'))) return; if (e.currentTarget.dataset.full) { toast(muneaT('familyCircle.fullUpgradeToast', '全家健康圈滿了，升級方案可以邀請更多家人。')); return; } $('#famCircleModal').classList.remove('show'); if ($('#inviteFamModal')) { fillInvCode(true); $('#inviteFamModal').classList.add('show'); } });
  // 邀請碼：跟雲端拿真的（6 位數、72 小時內有效、綁自己的家庭編號）；連不上雲端就先給本機碼並提示
  async function ensureCloudInvite() {
    // 已有 48 小時內拿到的雲端碼就沿用（雲端碼 72 小時有效，留 24 小時緩衝）
    try {
      const at = +(localStorage.getItem('munea.inviteCodeAt') || 0);
      const cached = localStorage.getItem('munea.inviteCode') || '';
      if (/^MUNEA-\d{6}$/.test(cached) && Date.now() - at < 172800000) return { code: cached, error: null };
    } catch (e) {}
    try {
      // Plan, circle id, owner and member limit are derived on the server.
      // Do not send client-controlled authority fields with an invite request.
      const j = await brainPost('/family/invitations', { action: 'create' });
      if (j && j.ok && j.invitation && j.invitation.shortCode) {
        const code = 'MUNEA-' + j.invitation.shortCode;
        try { localStorage.setItem('munea.inviteCode', code); localStorage.setItem('munea.inviteCodeAt', String(Date.now())); } catch (e) {}
        return { code, error: null };
      }
      // 雲端有回但拒絕：把理由帶回去，畫面照理由講人話（不再混成一句）
      if (j && j.error) return { code: null, error: String(j.error) };
    } catch (e) {}
    return { code: null, error: 'network' };   // 連不上雲端
  }
  // 雲端拒絕理由 → 給用戶看的人話（2026-07-17 Edward 指示：說法要照理由講、不能一句混）
  const INVITE_FAIL_TEXT = {
    auth_required: () => muneaT('familyCircle.failAuth', '先登入帳號，才能邀請家人。'),
    family_cloud_identity_required: () => muneaT('familyCircle.failAuth', '先登入帳號，才能邀請家人。'),
    family_owner_required: () => muneaT('familyCircle.failOwner', '只有家庭健康圈的圈主能建立邀請碼。'),
    family_plan_required: () => muneaT('familyCircle.failPlan', '邀請家人是付費方案的功能，升級後就能建立邀請碼。'),
    network: () => muneaT('familyCircle.failNetwork', '網路不通，請檢查連線後再試一次。'),
  };
  function fillInvCode(withCloud) {
    const el = $('#invCode'); if (!el) return;
    const note = $('#invTempNote');
    // There is no offline invitation mode: a locally generated code cannot
    // carry verified identity, entitlement or membership provisioning.
    el.textContent = withCloud ? muneaT('common.creating', '建立中…') : '—';
    if (note) note.style.display = 'none';
    if (!withCloud) return;
    ensureCloudInvite().then(r => {
      if (r.code) { el.textContent = r.code; if (note) note.style.display = 'none'; return; }  // 拿到正式碼＝乾淨顯示
      el.textContent = '—';
      if (r.error === 'family_plan_required' && window.MMPLAN && typeof window.MMPLAN.upsell === 'function') {
        // 跟入口那道門同一套：方案不夠就直接帶去看升級方案，不留人在死畫面
        const mask = $('#inviteFamModal'); if (mask) mask.classList.remove('show');
        window.MMPLAN.upsell('family-invite');
        return;
      }
      // INVITE_FAIL_TEXT 的每個值都是「函式」（四語化後改成用時才取翻譯），這裡少了呼叫的括號，
      // 等於把整段程式碼當文字塞進畫面——Edward 2026-07-31 在邀請視窗上看到
      // "() => muneaT('familyCircle.failNetwork', '網路不通…')" 印在那裡。
      // 加上 () 才會拿到真正的句子；再加型別判斷，之後若有人把某個值改回純字串也不會再壞一次。
      if (note) {
        const pick = INVITE_FAIL_TEXT[r.error] || INVITE_FAIL_TEXT.network;
        note.textContent = typeof pick === 'function' ? pick() : String(pick);
        note.style.display = '';
      }
    });
  }
  if ($('#inviteFamModal')) $('#inviteFamModal').addEventListener('click', e => { if (e.target === $('#inviteFamModal')) $('#inviteFamModal').classList.remove('show'); });
  if ($('#inviteCloseX')) $('#inviteCloseX').addEventListener('click', () => $('#inviteFamModal').classList.remove('show'));
  function shownInvCode() {
    const code = ((($('#invCode') || {}).textContent) || '').trim();
    return /^MUNEA-\d{6}$/.test(code) ? code : '';
  }
  if ($('#invShareBtn')) $('#invShareBtn').addEventListener('click', () => {
    if (!shownInvCode()) { toast(muneaT('familyCircle.inviteCodeNotReady', '邀請碼還沒建立好，先看畫面上寫的原因處理一下。')); return; }
    const text = muneaT('familyCircle.shareText', '我在用「沐寧 Munea」，AI 健康管家陪全家顧健康。我的家庭圈邀請碼是 {code}，在沐寧的「家人 → 加入全家健康圈」輸入，我們就連上了！', { code: shownInvCode() });
    if (navigator.share) { navigator.share({ text }).catch(() => {}); }
    else { location.href = 'sms:?&body=' + encodeURIComponent(text); }
  });
  if ($('#invCopyBtn')) $('#invCopyBtn').addEventListener('click', () => {
    const code = shownInvCode();
    if (!code) { toast(muneaT('familyCircle.inviteCodeNotReady', '邀請碼還沒建立好，先看畫面上寫的原因處理一下。')); return; }
    (navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(code) : Promise.reject()).then(
      () => toast(muneaT('familyCircle.inviteCopiedToast', "邀請碼複製好了，貼給家人")),
      () => toast(muneaT('familyCircle.yourCodeToast', '你的邀請碼：{code}', { code }))
    );
  });
  fillInvCode(false);
  if ($('#connectBack')) $('#connectBack').addEventListener('click', () => showView(window.__connectFrom || 'status'));
  $$('#connect .cn-btn').forEach(b => b.addEventListener('click', async () => {
    // Apple 健康：在 App 裡就真的去要 iPhone 授權；網頁預覽則走原本示範切換
    if (b.id === 'cnHealthBtn' && window.MuneaHealth && window.MuneaHealth.available()) {
      setBtnBusy(b, muneaT('health.connecting', '連接中'));
      const r = await window.MuneaHealth.connect();
      if (r && r.ok) {
        clearBtnBusy(b);
        trackProductEvent('health_connected', { empty: !!r.empty, needsHealthApp: !!r.needsHealthApp });
        // 按鍵長什麼樣、下一步該做什麼，統一交給 health.js 依狀態決定（整頁只有這一顆鍵）。
        // 這裡只負責講一句人話，不要在這邊自己改按鍵文字，否則兩邊會打架。
        if (typeof window.MuneaHealth.renderConnectionState === 'function') {
          window.MuneaHealth.renderConnectionState();
        }
        // 一項都沒讀到就不要承諾會幫她留意——蘋果不會告訴我們是沒授權還是本來就沒紀錄，
        // 所以只講現況跟怎麼打開，不亂猜原因
        hint(r.empty
          ? (r.needsHealthApp
            ? muneaT('health.hintAskedOnce', '這個授權視窗只會跳一次，之後要改都在「健康」App 裡。按上面那顆鍵我帶你過去。')
            : muneaT('health.hintEmpty', '連上了，但我還讀不到資料。按上面那顆鍵去「健康」App 把項目打開就好。'))
          : muneaT('health.hintConnected', '好，連上 Apple 健康了，步數和身體數據我會自動幫你留意。'));
      } else {
        clearBtnBusy(b, b.dataset.label || muneaT('health.connect', '連接'));
        hint(r && r.reason === 'unavailable' ? muneaT('health.noDeviceData', '這台裝置沒有健康資料可讀。') : muneaT('health.connectRetryHint', '沒有連上，晚點在「連接裝置」再試一次也可以。'));
      }
      return;
    }
    const on = b.classList.toggle('done');
    b.textContent = on ? ('✓ ' + muneaT('health.connectedShort', '已連接')) : (b.dataset.label || muneaT('health.connect', '連接'));
    if (on) { hint(muneaT('health.connectedToast', "好，連上了，之後健康資料我會自動留意。")); try { localStorage.setItem('munea.devicesOn', '1'); } catch (e2) {} }
  }));

  // 今天一起完成（任務打勾）
  $('#taskCard').addEventListener('click', e => { const it = e.target.closest('.task-item'); if (it) toggleTask(it); });

  // 家人互動回應（親情循環）
  const reactRow = $('#reactRow');
  if (reactRow) reactRow.addEventListener('click', e => {
    const b = e.target.closest('.react-btn');
    if (!b || b.classList.contains('sent')) return;
    reactRow.querySelectorAll('.react-btn.sent').forEach(x => x.classList.remove('sent'));
    b.classList.add('sent');
    hint(muneaT('familyCircle.relaySentHint', '送出去了，會在家人動態幫你帶到。', { companion: cname() }));
    const who = document.getElementById('ptName')?.textContent || '家人';
    pushFamilyFeed(`<b>你</b>給${who}${b.dataset.react || '送上心意'}，${cname()}會在下次聊天時帶到`);
  });

  // 全家健康圈：切換成員看健康（7/9 正式化：示範看板已拆、一律吃真同步數據）
  // 家人真數據（7/9 Edward「數據真同步」）：從家人水管拉回的 munea.famVitals 依名字對人
  function famVitalsFor(name) {
    try {
      const all = JSON.parse(localStorage.getItem('munea.famVitals') || '{}');
      let best = null;
      for (const pid in all) {
        const v = all[pid];
        if (!v || typeof v !== 'object') continue;
        if ((v.name && v.name === name) || (v.nick && v.nick === name)) {
          if (!best || (v.updatedAt || 0) > (best.updatedAt || 0)) best = v;
        }
      }
      return best;
    } catch (e) { return null; }
  }
  // 家人「心情」標籤（7/16 Edward 拆混淆）：只認他自己裝置同步上來的當天／昨天粗標籤；
  // 沒有＝整顆不顯示——不再擺一顆人人相同的「平穩」，跟右邊的平安燈徹底分工
  function famMoodFor(rv) {
    const m = rv && rv.mood;
    if (!m || !m.key || !MOODS[m.key]) return null;
    const y = new Date(); y.setDate(y.getDate() - 1);
    const yesterIso = y.getFullYear() + '-' + String(y.getMonth() + 1).padStart(2, '0') + '-' + String(y.getDate()).padStart(2, '0');
    if (m.date !== _todayISO() && m.date !== yesterIso) return null;
    const moodKey = {
      happy: 'mood.happy',
      glad: 'mood.pleasant',
      calm: 'mood.calm',
      tired: 'mood.tired',
      down: 'mood.low',
      anxious: 'mood.anxious',
      angry: 'mood.angry',
      upset: 'mood.upset',
    }[m.key];
    return { key: m.key, label: muneaT(moodKey, MOODS[m.key].label()) };
  }
  // 真數據 → 顯示格式（門檻白話跟狀態頁同一套規則）
  function vitalsToDisplay(v) {
    if (!v) return null;
    const sys = +v.bpSys || 0, dia = +v.bpDia || 0, hr = +v.hr || 0, spo2 = +v.spo2 || 0, sleep = +v.sleepHours || 0, steps = +v.steps || 0;
    const d = { bp: null, hr: null, spo2: null, sleep: null, steps: null, med: null, day: v.day || '' };
    if (sys && dia) {
      const hi = sys >= 140 || dia >= 90, lo = sys < 90;
      d.bp = { n: String(Math.round(sys)), u: '/' + Math.round(dia) + ' mmHg', chip: hi ? muneaT('health.high', '偏高') : lo ? muneaT('health.low', '偏低') : muneaT('health.stable', '穩定'), warn: (hi || lo) ? 1 : 0, sub: hi ? muneaT('health.bpHighHint', '比平常高一點，多留意') : lo ? muneaT('health.bpLowHint', '偏低一些，起身動作放慢') : muneaT('health.bpNormalHint', '正常範圍內') };
    }
    if (hr) {
      const odd = hr < 50 || hr > 100;
      d.hr = { n: String(Math.round(hr)), chip: odd ? muneaT('health.attention', '注意') : muneaT('health.normal', '正常'), warn: odd ? 1 : 0, sub: muneaT('health.restingHrHint', '靜息心率') };
    }
    if (spo2) d.spo2 = String(Math.round(spo2));
    if (sleep) d.sleep = String(Math.round(sleep * 10) / 10);
    if (steps) d.steps = Math.round(steps).toLocaleString();
    return (d.bp || d.hr || d.spo2 || d.sleep || d.steps) ? d : null;
  }
  function renderPersonStats(p) {
    const grid = $('#personGrid');
    if (!grid) return;
    const d = vitalsToDisplay(famVitalsFor(p));   // 只認真數據；沒有＝老實說還沒有
    if (!d) { grid.innerHTML = '<div class="card" style="padding:16px;margin-bottom:16px;font-size:14.5px;color:var(--muted);text-align:center;line-height:1.7">' + muneaT('health.famEmptyHint', '等{name}連上沐寧，健康數據就會出現在這裡', { name: p || muneaT('familyCircle.memberFallback', '家人') }) + '</div>'; return; }
    if (!d.bp) d.bp = { n: '—', u: '', chip: muneaT('health.notProvided', '未提供'), warn: 0, sub: muneaT('health.noBpFromDevice', '他的裝置還沒帶到血壓') };
    if (!d.hr) d.hr = { n: '—', chip: muneaT('health.notProvided', '未提供'), warn: 0, sub: muneaT('health.noHrFromDevice', '他的裝置還沒帶到心率') };
    if (!d.spo2) d.spo2 = '—';
    if (!d.sleep) d.sleep = '—';
    if (!d.steps) d.steps = '—';
    // 標籤配色照狀態頁規範：警示=珊瑚、血壓正常=薄荷綠、心率正常=淡珊瑚（7/9 Edward 對齊設計規範）
    const chip = (t, warn, tone) => { const coral = warn || tone === 'coral'; return '<span class="chip" style="flex-shrink:0;background:' + (coral ? 'var(--coral-soft)' : 'var(--mint)') + ';color:' + (coral ? 'var(--ink)' : 'var(--teal-dd)') + '">' + t + '</span>'; };
    const medCard = d.med
      ? '<div class="card" style="padding:14px 15px;margin-bottom:11px"><div class="row" style="justify-content:space-between;gap:10px">' +
        '<div class="row" style="gap:11px;min-width:0"><span style="flex:0 0 38px;width:38px;height:38px;border-radius:12px;background:' + (d.med.warn ? 'var(--coral)' : 'var(--teal)') + ';display:grid;place-items:center;color:#fff"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M10.5 20.5 20 11a4.95 4.95 0 1 0-7-7l-9.5 9.5a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/></svg></span>' +
        '<div style="min-width:0"><div style="font-weight:700;font-size:14.5px">' + muneaT('health.medStatusTitle', '用藥狀態') + '</div><div style="font-size:14px;color:var(--muted);margin-top:1px">' + d.med.sub + '</div></div></div>' + chip(d.med.chip, d.med.warn) + '</div></div>'
      : '';
    grid.innerHTML = medCard +
      '<div class="row" style="gap:11px;margin-bottom:11px;align-items:stretch">' +
        '<div class="card" style="padding:15px;flex:1">' +
          '<div class="row" style="justify-content:space-between;margin-bottom:12px"><span style="width:32px;height:32px;border-radius:10px;background:var(--teal);display:grid;place-items:center;color:#fff"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg></span>' + chip(d.bp.chip, d.bp.warn) + '</div>' +
          '<div style="font-size:14px;color:var(--muted);margin-bottom:3px">' + muneaT('health.bloodPressure', '血壓') + '</div>' +
          '<div><span class="mnum" style="font-size:26px;color:var(--teal-dd)">' + d.bp.n + '</span><span style="font-size:14px;color:var(--muted)">' + d.bp.u + '</span></div>' +
          '<div style="font-size:14px;color:var(--muted);margin-top:6px">' + d.bp.sub + '</div></div>' +
        '<div class="card" style="padding:15px;flex:1">' +
          '<div class="row" style="justify-content:space-between;margin-bottom:12px"><span style="width:32px;height:32px;border-radius:10px;background:var(--coral);display:grid;place-items:center;color:#fff"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.8 8.6c0-3.2-2.5-5.4-5.3-5.4-1.6 0-2.9.7-3.5 1.9-.6-1.2-1.9-1.9-3.5-1.9-2.8 0-5.3 2.2-5.3 5.4C3.2 14 12 20 12 20s8.8-6 8.8-11.4Z"/></svg></span>' + chip(d.hr.chip, d.hr.warn, 'coral') + '</div>' +
          '<div style="font-size:14px;color:var(--muted);margin-bottom:3px">' + muneaT('health.heartRate', '心率') + '</div>' +
          '<div><span class="mnum" style="font-size:26px;color:var(--ink)">' + d.hr.n + '</span><span style="font-size:14px;color:var(--muted)"> bpm</span></div>' +
          '<div style="font-size:14px;color:var(--muted);margin-top:6px">' + d.hr.sub + '</div></div>' +
      '</div>' +
      '<div class="card" style="display:flex;align-items:stretch;padding:0;overflow:hidden;margin-bottom:16px">' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--teal)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11Z"/></svg><span style="font-size:14px;color:var(--muted)">' + muneaT('health.bloodOxygen', '血氧') + '</span></div><div><span class="mnum" style="font-size:21px;color:var(--teal-dd)">' + d.spo2 + '</span><span style="font-size:14px;color:var(--muted)"> %</span></div></div>' +
        '<div style="width:1px;background:var(--line);margin:12px 0"></div>' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#C79A3B" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg><span style="font-size:14px;color:var(--muted)">' + muneaT('health.lastNightSleep', '昨晚睡眠') + '</span></div><div><span class="mnum" style="font-size:21px;color:#8A6410">' + d.sleep + '</span><span style="font-size:14px;color:var(--muted)"> ' + muneaT('health.unit.hourNarrow', '時') + '</span></div></div>' +
        '<div style="width:1px;background:var(--line);margin:12px 0"></div>' +
        '<div style="flex:1;padding:13px 14px"><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--teal-dd)" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 16v-2.4c0-2.1-1-3.1-1-5.6 0-2.7 1.5-6 4.5-6C9.4 2 10 3.8 10 5.5c0 3.1-2 5.7-2 8.7V16a2 2 0 1 1-4 0Z"/><path d="M20 20v-2.4c0-2.1 1-3.1 1-5.6 0-2.7-1.5-6-4.5-6C14.6 6 14 7.8 14 9.5c0 3.1 2 5.7 2 8.7V20a2 2 0 1 0 4 0Z"/></svg><span style="font-size:14px;color:var(--muted)">' + muneaT('health.activityAmount', '運動量') + '</span></div><div><span class="mnum" style="font-size:21px;color:var(--teal-dd)">' + d.steps + '</span><span style="font-size:14px;color:var(--muted)"> ' + muneaT('health.unit.steps', '步') + '</span></div></div>' +
      '</div>';
  }
  function renderPersonMood(p) {
    // 7/16 心情真串接：家庭帳本帶回來的「當天粗心情標籤」可以顯示；聊天觀察細節仍留在本人手機、這裡誠實不編
    const mood = famMoodFor(famVitalsFor(p));
    if ($('#mcTitle')) $('#mcTitle').textContent = mood ? muneaT('mood.todayLooks', '今天心情看起來「{label}」', { label: mood.label }) : muneaT('mood.noObservation', '還沒有觀察');
    // 有心情時不再多一句說明（Edward 2026-08-01）：上面那行「今天心情看起來『焦慮』」
    // 本身就講完了，底下再解釋一次「這是從聊天觀察到的、聊什麼留在他手機」只是變長。
    // 沒有心情的空狀態仍要留一句——不然畫面空白，看的人不知道是壞了還是還沒開始用。
    if ($('#mcSub')) $('#mcSub').textContent = mood
      ? ''
      : muneaT('mood.familyObsEmpty', '等{name}開始用沐寧聊天，觀察會出現在這裡', { name: p || muneaT('familyCircle.memberFallback', '家人') });
    if ($('#mcObs')) $('#mcObs').innerHTML = '';
    if ($('#mcTopics')) $('#mcTopics').innerHTML = '';
  }

  // 家人頁名單跟「設定 → 全家健康圈」吃同一份資料（兩本帳合一）：圈裡移除了人，這裡自動跟著消失
  // （7/9 拆示範：稱謂/狀態不再寫死——狀態從真數據推、稱謂一律「家人」）
  let FAM_ORDER = [];   // 本人資料在「狀態」頁，家人頁不重複顯示；實際名單由 renderFamRoster 重算
  let currentPerson = '';
  function famInit(m) { return m.init || (m.name || '')[0] || ''; }
  function renderFamRoster() {
    const mem = loadCircle().filter(m => !m.self);
    FAM_ORDER = mem.map(m => m.name);
    const fs = $('#famSwitch');
    if (fs) {
      const allBtn = fs.querySelector('[data-person="all"]');
      const invBtn = fs.querySelector('[data-person="invite"]');
      fs.innerHTML = (allBtn ? allBtn.outerHTML : '') + mem.map(m =>
        '<button class="fam-switch-item" data-person="' + m.name + '" data-rel="家人" data-init="' + famInit(m) + '" data-tint="' + muneaSafeTint(m.tint, m.name) + '"><span class="fs-av"><span class="init-ava ' + muneaSafeTint(m.tint, m.name) + '">' + famInit(m) + '</span></span><span class="fs-name">' + m.name + '</span></button>'
      ).join('') + (invBtn ? invBtn.outerHTML : '');
    }
    const hl = $('#healthList');
    if (hl) hl.innerHTML = mem.length ? mem.map(m => {
      // 7/16 標籤分工重整（Edward「兩個標籤會混淆」）：
      // 左＝心情（臉＋詞、來自他自己的沐寧聊天觀察、當天才顯示、沒有就不擺）
      // 右＝平安燈（有同步數據且都在留意範圍→安好；有超標→需留意；還沒連→未連）
      const rv = famVitalsFor(m.name);
      const d = rv ? vitalsToDisplay(rv) : null;
      const warn = !!(d && ((d.bp && d.bp.warn) || (d.hr && d.hr.warn) || (rv && +rv.spo2 && +rv.spo2 < 90)));
      const mood = famMoodFor(rv);
      const st = rv
        ? (
          warn
            ? { cls: 'watch', label: muneaT('family.status.needsAttention', '需留意') }
            : { cls: 'ok', label: muneaT('family.status.okay', '安好') }
        )
        : { cls: 'off', label: muneaT('family.status.notConnected', '未連') };
      const pill = mood ? '<em class="mood-pill ' + mood.key + '">' + moodFaceSvg(mood.key, 13) + mood.label + '</em>' : '';
      let familyDay = rv && rv.day ? String(rv.day) : '';
      if (familyDay === '今天') familyDay = muneaT('common.today', '今天');
      else if (familyDay === '昨天') familyDay = muneaT('common.yesterday', '昨天');
      if (!familyDay) familyDay = muneaT('common.recently', '近日');
      const txt = rv
        ? muneaT('family.status.updatedAt', '數據更新於 {day}', { day: familyDay })
        : muneaT('family.status.waiting', '等他加入連上，就看得到狀態');
      return '<div class="health-row" data-person="' + m.name + '" data-rel="家人" data-init="' + famInit(m) + '" data-tint="' + muneaSafeTint(m.tint, m.name) + '">' +
        '<span class="hr-av"><span class="init-ava ' + muneaSafeTint(m.tint, m.name) + '">' + famInit(m) + '</span></span>' +
        '<div class="hr-info"><div class="hr-name">' + m.name + '</div><div class="hr-state">' + pill + txt + '</div></div>' +
        '<div class="hr-status ' + st.cls + '"><span class="hr-dot"></span><span class="hr-slabel">' + st.label + '</span></div></div>';
    }).join('') : '<div class="fam-empty">' + muneaT('familyCircle.emptyRosterTitle', '圈裡還沒有家人') + '<br>' + muneaT('familyCircle.emptyRosterBody', '點上面「邀請」把家人拉進來，就看得到大家的狀態') + '</div>';
    // 空的時候讓掉白卡外觀，改用跟上面「還沒有進行中的活動」同一套虛線框（Edward 2026-07-29）
    if (hl) hl.classList.toggle('is-empty', !mem.length);
    if (currentPerson && !FAM_ORDER.includes(currentPerson)) { currentPerson = FAM_ORDER[0] || ''; if ($('#viewPerson') && $('#viewPerson').classList.contains('active')) showFamAll(); }
    renderFamDots();
  }
  function famItemOf(name) {
    return [...document.querySelectorAll('.fam-switch-item')].find(x => x.dataset.person === name);
  }
  function renderFamDots() {
    const box = $('#famDots');
    if (!box) return;
    box.innerHTML = FAM_ORDER.map(n => '<i class="' + (n === currentPerson ? 'on' : '') + '"></i>').join('');
  }
  function switchPerson(delta) {
    const idx = FAM_ORDER.indexOf(currentPerson);
    const next = FAM_ORDER[idx + delta];
    if (!next) return; // 到邊了
    const b = famItemOf(next);
    if (!b) return;
    const v = $('#viewPerson');
    if (v) { v.classList.remove('slide-l', 'slide-r'); void v.offsetWidth; v.classList.add(delta > 0 ? 'slide-l' : 'slide-r'); }
    showFamPerson(next, b.dataset.rel, b.dataset.init, b.dataset.tint);
    b.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
  }

  function showFamPerson(p, rel, init, tint) {
    currentPerson = p;
    renderFamDots();
    const v = $('#viewPerson');
    const wasActive = v && v.classList.contains('active');
    $('#viewAll').classList.remove('active');
    if (v) v.classList.add('active');
    if ($('#ptName')) $('#ptName').textContent = p;   // 名字只在這裡出現一次（不再放稱謂副標、不放說明文字）
    renderPersonStats(p);
    renderPersonMood(p);   // 心情監測每個人都有（Edward 7/9）
    renderFamTrends();     // 活動量/睡眠/心情圖表跟著換人（跟狀態頁同款圖）
    if ($('#moodToday')) $('#moodToday').style.display = '';
    const pa = $('#ptAv');
    if (pa) { pa.textContent = init || (p || '')[0] || ''; pa.className = 'init-ava init-ava-lg ' + (tint || ''); }
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === p));
    // 左右切換鍵：到邊就變淡（美華在最左、小寶在最右）
    const idx = FAM_ORDER.indexOf(p);
    if ($('#ptPrev')) $('#ptPrev').disabled = idx <= 0;
    if ($('#ptNext')) $('#ptNext').disabled = idx < 0 || idx >= FAM_ORDER.length - 1;
    // 從全家頁進來＝整頁置頂（第一眼就看到這是誰）；左右換人保持原捲動位置（治晃動 · Edward 7/9）
    if (!wasActive) { const sc = $('#family'); if (sc) sc.scrollTop = 0; }
  }
  function showFamAll() {
    $('#viewPerson').classList.remove('active');
    $('#viewAll').classList.add('active');
    $$('.fam-switch-item').forEach(b => b.classList.toggle('active', b.dataset.person === 'all'));
  }
  const vp = $('#viewPerson');
  if (vp) {
    let sx = 0, sy = 0, tracking = false;
    vp.addEventListener('touchstart', e => { sx = e.touches[0].clientX; sy = e.touches[0].clientY; tracking = true; }, { passive: true });
    vp.addEventListener('touchend', e => {
      if (!tracking) return; tracking = false;
      const dx = e.changedTouches[0].clientX - sx, dy = e.changedTouches[0].clientY - sy;
      if (Math.abs(dx) > 56 && Math.abs(dx) > Math.abs(dy) * 2) switchPerson(dx < 0 ? 1 : -1);
    }, { passive: true });
    let mx = null;
    vp.addEventListener('mousedown', e => { mx = e.clientX; });
    vp.addEventListener('mouseup', e => {
      if (mx === null) return;
      const dx = e.clientX - mx; mx = null;
      if (Math.abs(dx) > 56) switchPerson(dx < 0 ? 1 : -1);
    });
  }
  if ($('#personBack')) $('#personBack').addEventListener('click', showFamAll);
  // 左右切換鍵＝跟左右滑同一件事（看得到的入口 · Edward 7/9）
  if ($('#ptPrev')) $('#ptPrev').addEventListener('click', () => switchPerson(-1));
  if ($('#ptNext')) $('#ptNext').addEventListener('click', () => switchPerson(1));
  if ($('#moodTrendBtn')) $('#moodTrendBtn').addEventListener('click', () => {
    $('#viewPerson').classList.remove('active');
    $('#viewMood').classList.add('active');
    const n = $('#ptName') ? $('#ptName').textContent : muneaT('familyCircle.memberFallback', '家人');
    if ($('#moodTitle')) $('#moodTitle').textContent = muneaT('mood.personTitle', '{name}的心情', { name: n });
    renderMoodWeek();
    const lg = $('#moodLegend');
    if (lg && !lg.childElementCount) lg.innerHTML = Object.keys(MOODS).map(k =>
      '<span><i style="background:' + MOODS[k].bg + '">' + moodFaceSvg(k, 14) + '</i>' + MOODS[k].label() + '</span>').join('');
  });
  if ($('#moodBack')) $('#moodBack').addEventListener('click', () => {
    $('#viewMood').classList.remove('active');
    $('#viewPerson').classList.add('active');
  });
  if ($('#moodRange')) $('#moodRange').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    $('#moodRange').querySelectorAll('button').forEach(x => x.classList.toggle('active', x === b));
    const month = b.dataset.r === 'month';
    $('#moodWeek').style.display = month ? 'none' : '';
    if (!month) $('#moodDayDetail').style.display = '';
    $('#moodMonth').style.display = month ? '' : 'none';
    if (month) renderMoodMonth();
  });
  const setReminders = $('#medEntrySettings');
  if (setReminders) setReminders.addEventListener('click', () => {
    const mask = $('#medMgrModal');
    if (mask) { renderMedList(); mask.classList.add('show'); }
  });
  if ($('#medMgrClose')) $('#medMgrClose').addEventListener('click', () => $('#medMgrModal').classList.remove('show'));
  if ($('#medMgrModal')) $('#medMgrModal').addEventListener('click', e => { if (e.target === $('#medMgrModal')) $('#medMgrModal').classList.remove('show'); });
  const chipToggle = (boxId, single) => {
    const box = $(boxId);
    if (!box) return;
    box.addEventListener('click', e => {
      const b = e.target.closest('.mchip');
      if (!b) return;
      if (single) box.querySelectorAll('.mchip').forEach(x => x.classList.remove('on'));
      b.classList.toggle('on');
    });
  };
  chipToggle('#medTimeChips', false);
  chipToggle('#medDayChips', true);
  if ($('#medSlots')) $('#medSlots').addEventListener('click', e => {
    const thumb = e.target.closest('.ms-thumb');
    if (thumb) { const _m = loadMeds().find(x => x.name === thumb.dataset.name); if (_m && _m.photo) showMedPhoto(_m.photo, _m.name); return; }
    const tb = e.target.closest('.ms-tbtn');
    if (tb) {
      const rt = loadRoutine();
      rt[tb.dataset.k] = shiftTime(rt[tb.dataset.k], +tb.dataset.m);
      saveRoutine(rt);
      renderMedSlots();
      return;
    }
    const del = e.target.closest('.ms-del');
    if (del) {
      let meds = loadMeds();
      let changedMed = null, archivedMed = null;
      meds = meds.map(m => {
        if (m.name !== del.dataset.name) return m;
        const rest = String(m.time).split('、').map(x => x.trim()).filter(x => x && x !== del.dataset.slot);
        if (rest.length) {
          changedMed = Object.assign({}, m, { time: rest.join('、') });
          return changedMed;
        }
        archivedMed = m;
        return null;
      }).filter(Boolean);
      try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e2) {}
      if (changedMed) syncMedicationReminder(changedMed);
      if (archivedMed) archiveRoutineReminder(archivedMed.id || stableReminderId('med_', [archivedMed.name, archivedMed.time, archivedMed.days, archivedMed.by].join('|')));
      updateMedCount();
      renderMedSlots();
      toast(muneaT(
        'medicationManager.removedToast',
        '已移除，這個時段不再提醒這種藥。',
      ));
    }
  });
  if ($('#medSlots')) $('#medSlots').addEventListener('change', e => {
    const ti = e.target.closest('input.ms-time');
    if (ti && ti.value) {
      const rt = loadRoutine();
      rt[ti.dataset.k] = shiftTime(ti.value, -(+ti.dataset.off || 0));
      saveRoutine(rt);
      renderMedSlots();
      updateMedCount();
    }
  });
  let _medPendingPhoto = '';
  if ($('#medPhotoBtn')) $('#medPhotoBtn').addEventListener('click', () => { if ($('#medPhotoFile')) $('#medPhotoFile').click(); });
  if ($('#medPhotoFile')) $('#medPhotoFile').addEventListener('change', e => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (!f) return; const box = $('#medPhotoBox'); if (box) box.classList.add('processing'); resizeSquare(f, url => { if (box) box.classList.remove('processing'); _medPendingPhoto = url; if (box) { box.style.backgroundImage = 'url(' + url + ')'; box.classList.add('has'); } }, () => { if (box) box.classList.remove('processing'); toast(muneaT('medicationManager.photoReadError', '這張照片讀不到，請換一張相簿裡的照片。')); }); });
  if ($('#medAddBtn')) $('#medAddBtn').addEventListener('click', () => {
    const name = $('#medName').value.trim();
    const times = [...document.querySelectorAll('#medTimeChips .mchip.on')].map(b => b.dataset.t);
    const days = document.querySelector('#medDayChips .mchip.on')?.dataset.d || '長期';
    if (!name) {
      toast(muneaT(
        'medicationManager.nameRequired',
        '請先填寫藥名（照藥袋抄即可）。',
      ));
      return;
    }
    if (!times.length) {
      toast(muneaT(
        'medicationManager.scheduleRequired',
        '請選擇服藥時間，可以多選。',
      ));
      return;
    }
    const meds = loadMeds();
    const med = { name, time: times.join('、'), days, by: '本人', photo: _medPendingPhoto };
    ensureMedReminderId(med);
    meds.push(med);
    try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
    syncMedicationReminder(med);
    $('#medName').value = '';
    _medPendingPhoto = ''; { const _b = $('#medPhotoBox'); if (_b) { _b.style.backgroundImage = ''; _b.classList.remove('has'); } }
    document.querySelectorAll('#medTimeChips .mchip.on').forEach(x => x.classList.remove('on'));
    renderMedList();
    updateMedCount();
    toast(muneaT(
      'medicationManager.addedToast',
      '{companion}會在{slots}提醒你服用「{name}」，時間依照你的作息。',
      {
        companion: cname(),
        slots: localizedMedicationSlotList(times),
        name,
      },
    ));
  });
  if ($('#medEntryStatus')) $('#medEntryStatus').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  if ($('#medTileBtn')) $('#medTileBtn').addEventListener('click', () => { renderMedList(); $('#medMgrModal').classList.add('show'); });
  initHealthDashboard();
  
  if ($('#topUpBtn')) $('#topUpBtn').addEventListener('click', () => {
    $('#topUpModal').classList.add('show');
    void refreshLocalizedStoreProducts();
  });
  if ($('#topUpClose')) $('#topUpClose').addEventListener('click', () => $('#topUpModal').classList.remove('show'));
  if ($('#topUpModal')) $('#topUpModal').addEventListener('click', e => {
    if (e.target === $('#topUpModal')) { $('#topUpModal').classList.remove('show'); return; }
    const card = e.target.closest('.tu-card');
    if (card) {
      document.querySelectorAll('#topUpModal .tu-card').forEach(x => x.classList.remove('on'));
      card.classList.add('on');
      renderCreditPurchaseButtons();
    }
  });
  if ($('#tuBuyBtn')) $('#tuBuyBtn').addEventListener('click', async () => {
    const selCard = document.querySelector('#topUpModal .tu-card.on');
    const p = selCard ? +selCard.dataset.p : 0;
    if (!p) { toast(muneaT('purchase.selectPack', 'Choose a credit pack')); return; }
    // App 裡走真蘋果付款；點數入帳由 __muneaApplyPurchase 統一做
    if (window.MuneaStore && window.MuneaStore.available()) {
      const authNow = window.MuneaAuth && typeof window.MuneaAuth.state === 'function' ? window.MuneaAuth.state() : {};
      if (!authNow.authUserId) {
        toast(muneaT('purchase.signInRequiredBody', 'Sign in to buy, restore, and use credits across your devices.'), 4200);
        if (typeof openAuthSheet === 'function') openAuthSheet();
        return;
      }
      const b = $('#tuBuyBtn');
      const purchaseFlow = muneaPurchaseFlow();
      setBtnBusy(b, purchaseFlow
        ? purchaseFlow.connectingMessage()
        : muneaT('purchase.connectingStore', 'Connecting to the App Store…'));
      const r = await window.MuneaStore.purchase(window.MuneaStore.ptsId(p));
      clearBtnBusy(b);
      if (r.ok) $('#topUpModal').classList.remove('show');
      else if (r.reason !== 'cancelled') toast(planPurchaseFailMessage(r.reason), 5200);
      return;
    }
    try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + p)); } catch (e2) {}
    pushWallet();
    renderPoints();
    $('#topUpModal').classList.remove('show');
    toast(muneaT('purchase.success', '{credits} credits were added to your account.', {
      credits: new Intl.NumberFormat(muneaLocale()).format(p),
    }));
  });
  // ===== 訂閱頁：比較表 + 月/年繳切換 + 訂閱鈕（金額為暫定、待 Edward 拍板）=====
  // 年繳＝月費 ×12 打 8 折（省 20%）；金額暫定、待 Edward 拍板
  const SUB_PRICE = { plus: { month: 599, year: 5750 }, pro: { month: 1199, year: 11500 } };
  const PT_PRICE = { 100: 790, 300: 2190, 600: 4190, 1000: 6490 };            // 加購一律貴過訂閱 6 元/分（訂閱含功能價值、點數是純加分鐘）
  let _subPlan = 'pro', _subCyc = 'month', _planPick = null;
  let _storeProductsPromise = null;
  let _storeProductsState = 'idle';
  function hasNativeStore() {
    return !!(window.MuneaStore && window.MuneaStore.available());
  }
  // 拿不到蘋果價格時的退路。台幣金額只對台灣使用者成立——
  // 對西班牙／美國／日本的使用者顯示「1199 TWD」是錯的價格加錯的幣別
  // （Edward 2026-08-01 在西班牙文版看到）。真機幾乎都拿得到蘋果的當地價，
  // 但網路一慢就會走到這裡，蘋果審查若看到會當成誤導定價。
  // 所以：只有中文版才退回台幣，其他語言一律顯示破折號——不知道就不要編一個。
  function fallbackTwdPrice(amount) {
    if (muneaLocale() !== 'zh-TW') return '—';
    return new Intl.NumberFormat(muneaLocale(), {
      currency: 'TWD',
      currencyDisplay: 'code',
      maximumFractionDigits: 0,
      style: 'currency',
    }).format(Number(amount) || 0);
  }
  function storeProduct(productId) {
    return window.MuneaStore && typeof window.MuneaStore.product === 'function'
      ? window.MuneaStore.product(productId)
      : null;
  }
  function subscriptionProduct(plan, cyc) {
    if (!(window.MuneaStore && typeof window.MuneaStore.subId === 'function')) return null;
    return storeProduct(window.MuneaStore.subId(plan, cyc));
  }
  function creditProduct(credits) {
    if (!(window.MuneaStore && typeof window.MuneaStore.ptsId === 'function')) return null;
    return storeProduct(window.MuneaStore.ptsId(credits));
  }
  function fmtPrice(plan, cyc) {
    const product = subscriptionProduct(plan, cyc);
    return product && product.displayPrice
      ? product.displayPrice
      : fallbackTwdPrice(SUB_PRICE[plan][cyc]);
  }
  function fmtCreditPrice(credits) {
    const product = creditProduct(credits);
    return product && product.displayPrice
      ? product.displayPrice
      : fallbackTwdPrice(PT_PRICE[credits]);
  }
  function localizedPurchaseButton(credits) {
    const rendererCopy = muneaRendererCopy();
    const values = {
      credits,
      price: fmtCreditPrice(credits),
    };
    return rendererCopy
      ? rendererCopy.purchaseButton(values)
      : muneaT('purchase.buyCredits', 'Buy {credits} credits · {price}', values);
  }
  function renderCreditPurchaseButtons() {
    $$('.tu-card').forEach((card) => {
      const credits = Number(card.dataset.p || 0);
      const price = card.querySelector('.tu-price');
      if (!price) return;
      price.textContent = hasNativeStore()
        && (_storeProductsState === 'idle'
          || _storeProductsState === 'loading'
          || _storeProductsState === 'unavailable'
          || !creditProduct(credits))
        ? '—'
        : fmtCreditPrice(credits);
    });
    [
      ['#topUpModal .tu-card.on', '#tuBuyBtn'],
      ['#subPoints .tu-card.on', '#tuBuyBtn2'],
    ].forEach(([cardSelector, buttonSelector]) => {
      const card = document.querySelector(cardSelector);
      const button = $(buttonSelector);
      if (!button) return;
      const credits = card ? Number(card.dataset.p || 0) : 0;
      if (hasNativeStore() && (_storeProductsState === 'idle' || _storeProductsState === 'loading')) {
        button.textContent = muneaT('purchase.loadingProducts', 'Loading products…');
        button.disabled = true;
        return;
      }
      if (hasNativeStore() && (_storeProductsState === 'unavailable' || !creditProduct(credits))) {
        button.textContent = muneaT('purchase.storeUnavailable', 'The App Store is unavailable right now. Please try again later.');
        button.disabled = true;
        return;
      }
      button.textContent = credits
        ? localizedPurchaseButton(credits)
        : muneaT('purchase.selectPack', 'Choose a credit pack');
      button.disabled = !credits;
    });
  }
  async function refreshLocalizedStoreProducts() {
    if (!hasNativeStore() || typeof window.MuneaStore.getProducts !== 'function') {
      _storeProductsState = 'preview';
      renderSubUI();
      renderCreditPurchaseButtons();
      return;
    }
    if (_storeProductsPromise) return _storeProductsPromise;
    _storeProductsState = 'loading';
    renderSubUI();
    renderCreditPurchaseButtons();
    _storeProductsPromise = window.MuneaStore.getProducts()
      .then((result) => {
        _storeProductsState = result && result.ok ? 'ready' : 'unavailable';
        return result;
      })
      .catch(() => {
        _storeProductsState = 'unavailable';
        return { ok: false, reason: 'store_products_unavailable' };
      })
      .finally(() => {
        _storeProductsPromise = null;
        renderSubUI();
        renderCreditPurchaseButtons();
      });
    return _storeProductsPromise;
  }
  function renderSubUI() {
    localizePurchasePlanContent();
    const cur = circlePlan();
    [['plus', 'Plus'], ['pro', 'Pro']].forEach(([pl, Cap]) => {
      const priceEl = $('#price' + Cap);
      if (priceEl) {
        const period = document.createElement('small');
        period.textContent = muneaT(
          _subCyc === 'year' ? 'subscription.perYearShort' : 'subscription.perMonthShort',
          _subCyc === 'year' ? '/year' : '/month',
        );
        priceEl.replaceChildren(document.createTextNode(fmtPrice(pl, _subCyc)), period);
      }
      const saveEl = $('#save' + Cap);
      if (saveEl) {
        if (_subCyc === 'year') {
          saveEl.textContent = muneaT('subscription.savePercent', 'Save {percent}%', { percent: 20 });
          saveEl.style.display = '';
        }
        else saveEl.style.display = 'none';
      }
    });
    document.querySelectorAll('.ppk').forEach(c => { c.classList.toggle('sel', c.dataset.t === _subPlan); c.classList.toggle('is-cur', c.dataset.t === cur); });
    const cta = $('#subCta');
    if (cta) {
      const rendererCopy = muneaRendererCopy();
      if (hasNativeStore() && (_storeProductsState === 'idle' || _storeProductsState === 'loading')) {
        cta.textContent = muneaT('purchase.loadingProducts', 'Loading products…');
        cta.disabled = true;
      } else if (hasNativeStore() && (_storeProductsState === 'unavailable' || !subscriptionProduct(_subPlan, _subCyc))) {
        cta.textContent = muneaT('purchase.storeUnavailable', 'The App Store is unavailable right now. Please try again later.');
        cta.disabled = true;
      } else {
        const ctaValues = {
          currentPlan: cur,
          price: fmtPrice(_subPlan, _subCyc),
          selectedPlan: _subPlan,
        };
        cta.textContent = rendererCopy
          ? rendererCopy.subscriptionCta(ctaValues)
          : (_subPlan === cur
            ? muneaT('subscription.currentPlanCta', 'You are currently on {plan}', {
              plan: muneaT(`subscription.plan${_subPlan === 'pro' ? 'Pro' : 'Plus'}`, circlePlanLabel(_subPlan)),
            })
            : muneaT(
              PLAN_POINTS[_subPlan] > PLAN_POINTS[cur] ? 'subscription.upgradeTo' : 'subscription.changeTo',
              PLAN_POINTS[_subPlan] > PLAN_POINTS[cur]
                ? 'Upgrade to {plan} · {price}'
                : 'Switch to {plan} · {price}',
              {
                plan: muneaT(`subscription.plan${_subPlan === 'pro' ? 'Pro' : 'Plus'}`, circlePlanLabel(_subPlan)),
                price: ctaValues.price,
              },
            ));
        cta.disabled = _subPlan === cur;
      }
    }
    renderCreditPurchaseButtons();
    // 免費不能買點數（Edward 7/17 拍板 Ⓐ）：點數是會員的東西，免費走一次性 5 分鐘體驗、不吃點數。
    // 只剩一個分頁的切換器像壞掉 → 整個收起來，免費只看得到訂閱方案。訂閱後才長出來。
    const seg = $('#subSeg');
    if (seg) seg.style.display = cur === 'free' ? 'none' : '';
    const unlock = $('#pointsUnlockNotice');
    if (unlock) unlock.style.display = cur === 'free' ? '' : 'none';
    if (cur === 'free') showSubPane('plans');
    // 確認欄開著就跟著重畫，畫面寫的跟等下要扣的永遠一致
    if (typeof syncPlanConfirm === 'function') syncPlanConfirm();
  }
  // 切換「訂閱方案 / 點數購買」：唯一入口，免費被上面擋住不會走到 points
  function showSubPane(pane) {
    document.querySelectorAll('.sseg-btn').forEach((x, i) => {
      const on = x.dataset.pane === pane;
      x.classList.toggle('on', on);
      if (on) { const th = $('#ssegThumb'); if (th) th.style.transform = 'translateX(' + (i * 100) + '%)'; }
    });
    if ($('#subPlans')) $('#subPlans').style.display = pane === 'plans' ? '' : 'none';
    if ($('#subPoints')) $('#subPoints').style.display = pane === 'points' ? '' : 'none';
  }
  // 手上真的還剩多少點＝伺服器錢包（ptsLeft 優先用 /credits/balance 回來的餘額）。
  // 不可以用 localStorage 的「歷史累計買過」（POINTS.bought）：那個數字只增不減，
  // 而且後台發的點從來不會寫進本機。
  function creditsInHand() { return Math.max(0, Math.round(ptsLeft())); }
  // 點數列（餘額＋說明句）：餘額一變就要重畫。
  // 兩個入口都走這裡——換方案（renderPlanState）與伺服器餘額回來（renderPoints）。
  // 舊寫法只在 renderPlanState 算一次，而 /credits/balance 回來只呼叫 renderPoints：
  // 開機時那兩支並行，餘額後到就沒人重算顯示，畫面會停在「手上沒有點數」的樣子。
  function renderCreditRow() {
    const card = document.querySelector('.plan-card');
    if (!card) return;
    const plan = circlePlan();
    const isFree = plan === 'free';
    const monthly = Object.prototype.hasOwnProperty.call(PLAN_POINTS, plan) ? PLAN_POINTS[plan] : PLAN_POINTS.plus;
    // 免費方案不吃點數（走一次性 5 分鐘體驗）＝一律不能買點數。
    // 但「訂閱過→買過點→退訂掉回免費」的人、以及後台手動發過點的人，手上真的還有點：
    // 那些點看得到、留著、訂閱回來就能用（Edward 7/17 拍板「手上還有點數的話一定看得到餘額」）。
    const inHand = isFree ? creditsInHand() : 0;
    const lbl = card.querySelector('.pts-label');
    const used = card.querySelector('.pts-used');
    const bar = card.querySelector('.pts-bar');
    const note = card.querySelector('.pts-note');
    // 免費沒有月贈點 → 餘額只在「手上真的還有點」時露出來，且不顯示「每月送／已用」與進度條
    if (lbl) lbl.style.display = (!isFree || inHand > 0) ? '' : 'none';
    if (used) used.style.display = isFree ? 'none' : '';
    if (bar) bar.style.display = isFree ? 'none' : '';
    if (!note) return;
    const rendererCopy = muneaRendererCopy();
    const localized = rendererCopy
      ? rendererCopy.planSummary({
        minutes: monthly,
        monthlyCredits: monthly,
        plan,
        remainingCredits: inHand,
      })
      : null;
    note.textContent = localized
      ? localized.note
      : (!isFree
        ? muneaT(
          'subscription.monthlyCreditsNote',
          '{credits} credits provide about {minutes} minutes of conversation. Add more when they run out to keep talking.',
          { credits: monthly, minutes: monthly },
        )
        : (inHand > 0
          ? muneaT(
            'subscription.freeCreditsLeft',
            'Your unused {credits} credits will remain available. Subscribe to Plus or Pro to use them for conversations.',
            { credits: inHand },
          )
          : muneaT(
            'subscription.freePlanNote',
            'You are on the Free plan. Link an account for one 5-minute conversation. Plus and Pro add credit-based conversations, longer history, and family invitations.',
          )));
  }
  // renderPoints 在頂層 scope、方案額度表（PLAN_POINTS）在這層，所以掛出去給它呼叫
  window.__muneaRenderCreditRow = renderCreditRow;
  function renderPlanState() {
    const plan = circlePlan();
    const label = circlePlanLabel(plan);
    const pts = Object.prototype.hasOwnProperty.call(PLAN_POINTS, plan) ? PLAN_POINTS[plan] : PLAN_POINTS.plus;
    const rendererCopy = muneaRendererCopy();
    const localizedPlan = rendererCopy
      ? rendererCopy.planSummary({
        minutes: pts,
        monthlyCredits: pts,
        plan,
        remainingCredits: creditsInHand(),
      })
      : null;
    const sn = $('#setPlanName'); if (sn) sn.textContent = localizedPlan
      ? localizedPlan.name
      : muneaT('settings.planName', '{plan} plan', { plan: label });
    // 帳號卡右上角唯一的身份標籤（開發測試帳號會蓋成 TEST）
    renderMemBadge(plan);
    const sg = $('#setPlanGrant'); if (sg) sg.textContent = pts;
    // 換方案後本機記著的「已用」可能比新方案的月額度還大 → 夾到額度上限。
    // 舊寫法在這裡填 Math.round(pts * 0.3)，那是憑空生出來的假數字（畫面會寫「每月送 100 · 已用 30」，
    // 誰都沒用過那 30 點）。真相在伺服器，本機只負責不要顯示超過額度的數。
    if (POINTS.total !== pts) { POINTS.total = pts; if (POINTS.used > pts) POINTS.used = pts; }
    if (typeof renderPoints === 'function') renderPoints();
    const _isFreeP = plan === 'free';
    renderCreditRow();   // 餘額與說明句統一在這支算（renderPoints 也會呼叫它）
    const _tBtn = $('#topUpBtn'); if (_tBtn) _tBtn.style.display = _isFreeP ? 'none' : '';
    const _mBtn = $('#managePlanBtn'); if (_mBtn) _mBtn.textContent = localizedPlan
      ? localizedPlan.manageLabel
      : muneaT(_isFreeP ? 'settings.upgradePlan' : 'settings.managePlan', _isFreeP ? 'Upgrade plan' : 'Manage plan');
    renderSubUI();
  }
  window.__muneaRenderPlanState = renderPlanState;
  // 分段 tab（訂閱方案 / 點數購買）
  document.querySelectorAll('.sseg-btn').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.pane === 'points' && circlePlan() === 'free') return;   // 雙保險：免費點不到點數購買
    showSubPane(b.dataset.pane);
  }));
  // 月/年繳
  document.querySelectorAll('.scyc-btn').forEach((b, i) => b.addEventListener('click', () => {
    document.querySelectorAll('.scyc-btn').forEach(x => x.classList.toggle('on', x === b));
    const th = $('#scycThumb'); if (th) th.style.transform = 'translateX(' + (i * 100) + '%)';
    _subCyc = b.dataset.cyc; renderSubUI();
  }));
  // 選方案欄
  document.querySelectorAll('.ppk').forEach(c => c.addEventListener('click', () => { _subPlan = c.dataset.t; renderSubUI(); }));
  // ===== 確認欄：畫面寫什麼＝就扣什麼（唯一真相＝_subPlan／_subCyc）=====
  // 舊寫法在開欄當下把方案抄進 _planPick 就不再更新：欄開著時改選方案或月/年繳，
  // 欄位文字與實際扣款會對不上（選 Plus 卻扣 Pro、寫月費卻扣年費）。一律重畫、不留舊值。
  function planConfirmHtml(plan, cyc) {
    const rendererCopy = muneaRendererCopy();
    const values = {
      credits: PLAN_POINTS[plan],
      members: CIRCLE_LIMITS[plan],
      plan,
      price: fmtPrice(plan, cyc),
    };
    const localized = rendererCopy
      ? rendererCopy.planConfirmation(values)
      : {
        action: muneaT('subscription.confirmAction', 'Confirm with Apple'),
        body: muneaT(
          'subscription.confirmBody',
          'Apple will process your payment. The subscription renews automatically and can be managed in the App Store.',
        ),
        cancel: muneaT('subscription.cancel', 'Cancel'),
        facts: muneaT(
          'subscription.confirmFacts',
          '{credits} credits each month · Up to {members} care circle members',
          values,
        ),
        title: muneaT(
          'subscription.confirmTitle',
          'Confirm {plan} · {price}',
          {
            plan: muneaT(`subscription.plan${plan === 'pro' ? 'Pro' : 'Plus'}`, circlePlanLabel(plan)),
            price: values.price,
          },
        ),
      };
    const yes = $('#planYes'); if (yes) yes.textContent = localized.action;
    const no = $('#planNo'); if (no) no.textContent = localized.cancel;
    return muneaEscapeHtml(localized.title)
      + '<br>' + muneaEscapeHtml(localized.facts)
      + '<br><small>' + muneaEscapeHtml(localized.body) + '</small>';
  }
  function planConfirmOpen() { const b = $('#planConfirm'); return !!b && b.style.display !== 'none'; }
  // 付款失敗要講「為什麼」，不要全部混成一句（同邀請碼 105 號的教訓）
  function planPurchaseFailMessage(reason) {
    const purchaseFlow = muneaPurchaseFlow();
    return purchaseFlow
      ? purchaseFlow.failureMessage(reason)
      : muneaT('purchase.failed', 'The purchase could not be completed. Please try again later.');
  }
  function showPlanConfirm() {
    const bar = $('#planConfirm'); if (!bar) return;
    _planPick = _subPlan;
    $('#planConfirmText').innerHTML = planConfirmHtml(_subPlan, _subCyc);
    bar.style.display = '';
    // 欄是釘在畫面下方的，內容要墊高，最底下的條款連結與按鈕才不會被蓋住（蘋果要求條款看得到）
    const body = document.querySelector('#planModal .sub-body');
    if (body) body.style.paddingBottom = (bar.offsetHeight + 18) + 'px';
  }
  function hidePlanConfirm() {
    _planPick = null;
    const bar = $('#planConfirm'); if (bar) bar.style.display = 'none';
    const body = document.querySelector('#planModal .sub-body');
    if (body) body.style.paddingBottom = '';
  }
  // 欄開著時改選方案／月年繳 → 跟著重畫；選回目前方案就收起來（沒東西好確認）
  function syncPlanConfirm() {
    if (!planConfirmOpen()) return;
    if (_subPlan === circlePlan()) { hidePlanConfirm(); return; }
    showPlanConfirm();
  }
  // 訂閱鈕
  if ($('#subCta')) $('#subCta').addEventListener('click', () => {
    const cur = circlePlan();
    if (_subPlan === cur) {
      toast(muneaT('subscription.currentPlanCta', 'You are currently on {plan}', {
        plan: muneaT(`subscription.plan${_subPlan === 'pro' ? 'Pro' : 'Plus'}`, circlePlanLabel(_subPlan)),
      }));
      return;
    }
    showPlanConfirm();
  });
  if ($('#planYes')) $('#planYes').addEventListener('click', async () => {
    if (!_planPick) return;
    // App 裡走真蘋果付款（StoreKit）；網頁預覽維持示範切換
    if (window.MuneaStore && window.MuneaStore.available()) {
      // 未登入不先開蘋果付款——付完款才發現綁不了帳號，是 2026-07-22 Guideline 2.1(b) 退件級的體驗
      const authNow = window.MuneaAuth && typeof window.MuneaAuth.state === 'function' ? window.MuneaAuth.state() : {};
      if (!authNow.authUserId) {
        hidePlanConfirm();
        toast(muneaT('purchase.signInRequiredBody', 'Sign in to buy, restore, and use credits across your devices.'), 4200);
        if (typeof openAuthSheet === 'function') openAuthSheet();
        return;
      }
      const pid = window.MuneaStore.subId(_planPick, _subCyc);
      const b = $('#planYes');
      const purchaseFlow = muneaPurchaseFlow();
      setBtnBusy(b, purchaseFlow
        ? purchaseFlow.connectingMessage()
        : muneaT('purchase.connectingStore', 'Connecting to the App Store…'));
      const r = await window.MuneaStore.purchase(pid);
      clearBtnBusy(b, muneaT('subscription.confirmAction', 'Confirm with Apple'));
      if (r.ok) { hidePlanConfirm(); } // 生效與提示由 __muneaApplyPurchase 統一做
      else if (r.reason === 'cancelled') toast(muneaT('purchase.cancelled', 'Purchase cancelled. You were not charged.'));
      else if (r.reason === 'pending') {
        toast(muneaT('purchase.pending', 'Apple is processing this purchase. Your balance will update automatically.'));
        hidePlanConfirm();
      }
      else toast(planPurchaseFailMessage(r.reason), 4200);
      return;
    }
    const picked = _planPick;
    try { localStorage.setItem('munea.plan', picked); localStorage.removeItem('munea.planNext'); } catch (e2) {}
    hidePlanConfirm();
    renderPlanState();
    if (typeof renderFcRoster === 'function') { try { renderFcRoster(); } catch (e3) {} }
    toast(subscriptionSuccessMessage(picked), 4200);
  });
  if ($('#planNo')) $('#planNo').addEventListener('click', () => hidePlanConfirm());
  if ($('#planCancelBtn')) $('#planCancelBtn').addEventListener('click', async () => {
    const b = $('#planCancelBtn');
    if (window.MuneaStore && window.MuneaStore.available() && typeof window.MuneaStore.manageSubscriptions === 'function') {
      setBtnBusy(b, muneaT('purchase.manageSubscription', 'Manage subscription'));
      const result = await window.MuneaStore.manageSubscriptions();
      clearBtnBusy(b, muneaT('purchase.manageSubscription', 'Manage subscription'));
      if (!result.ok) {
        toast(muneaT(
          'purchase.manageSubscriptionUnavailable',
          'Subscription management could not be opened. Use Settings → Apple Account → Subscriptions on your iPhone.',
        ));
      }
      return;
    }
    toast(muneaT(
      'purchase.manageSubscriptionInstructions',
      'Use Settings → Apple Account → Subscriptions on your iPhone to manage or cancel.',
    ));
  });
  if ($('#managePlanBtn')) $('#managePlanBtn').addEventListener('click', () => {
    hidePlanConfirm();       // 每次進來都從乾淨狀態開始，不留上次挑到一半的確認欄
    renderSubUI();
    $('#planModal').classList.add('show');
    void refreshLocalizedStoreProducts();
    void refreshServerPlanEntitlement();
  });
  if ($('#planClose')) $('#planClose').addEventListener('click', () => {
    hidePlanConfirm();       // 關頁面＝放棄這次變更，別讓它下次開頁還掛在那
    $('#planModal').classList.remove('show');
  });
  // 恢復購買（蘋果硬規定）：原生付款層在（真機）→ 交給它；不在（網頁預覽）→ 誠實說明
  // 真機直接走 MuneaStore.restore；每筆交易仍須先經伺服器驗證才套用權益。
  if ($('#restoreBtn')) $('#restoreBtn').addEventListener('click', async () => {
    const b = $('#restoreBtn');
    if (!(window.MuneaStore && window.MuneaStore.available() && typeof window.MuneaStore.restore === 'function')) {
      toast(muneaT('purchase.restoreInAppOnly', 'Restore Purchases is available in the iPhone app.'));
      return;
    }
    const purchaseFlow = muneaPurchaseFlow();
    setBtnBusy(b, purchaseFlow
      ? purchaseFlow.restoringMessage()
      : muneaT('purchase.restoring', 'Restoring purchases…'));
    const result = await window.MuneaStore.restore();
    clearBtnBusy(b, muneaT('purchase.restore', 'Restore purchases'));
    toast(
      purchaseFlow
        ? purchaseFlow.restoreMessage(result)
        : result.ok
          ? muneaT('purchase.restoreSuccess', 'Your purchases were restored and access is being updated.')
          : result.reason === 'none'
            ? muneaT('purchase.restoreNone', 'No active subscription was found to restore.')
            : planPurchaseFailMessage(result.reason),
      result.reason === 'apple_account_token_mismatch' ? 5200 : 4200,
    );
  });
  if ($('#legalTermsLink')) $('#legalTermsLink').addEventListener('click', e => { e.preventDefault(); openInAppReader('terms'); });
  if ($('#legalPrivacyLink')) $('#legalPrivacyLink').addEventListener('click', e => { e.preventDefault(); openInAppReader('privacy'); });
  // 點數購買
  if ($('#subPoints')) $('#subPoints').addEventListener('click', e => {
    const card = e.target.closest('.tu-card'); if (!card) return;
    $('#subPoints').querySelectorAll('.tu-card').forEach(x => x.classList.remove('on')); card.classList.add('on');
    renderCreditPurchaseButtons();
  });
  if ($('#tuBuyBtn2')) $('#tuBuyBtn2').addEventListener('click', async () => {
    const sel = document.querySelector('#subPoints .tu-card.on');
    const p = sel ? +sel.dataset.p : 0;
    if (!p) { toast(muneaT('purchase.selectPack', 'Choose a credit pack')); return; }
    if (window.MuneaStore && window.MuneaStore.available()) {
      const authNow = window.MuneaAuth && typeof window.MuneaAuth.state === 'function' ? window.MuneaAuth.state() : {};
      if (!authNow.authUserId) {
        toast(muneaT('purchase.signInRequiredBody', 'Sign in to buy, restore, and use credits across your devices.'), 4200);
        if (typeof openAuthSheet === 'function') openAuthSheet();
        return;
      }
      const b = $('#tuBuyBtn2');
      const purchaseFlow = muneaPurchaseFlow();
      setBtnBusy(b, purchaseFlow
        ? purchaseFlow.connectingMessage()
        : muneaT('purchase.connectingStore', 'Connecting to the App Store…'));
      const r = await window.MuneaStore.purchase(window.MuneaStore.ptsId(p));
      clearBtnBusy(b);
      if (!r.ok && r.reason !== 'cancelled') toast(planPurchaseFailMessage(r.reason), 5200);
      return;
    }
    try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + p)); } catch (e2) {}
    pushWallet(); renderPoints();
    toast(muneaT('purchase.success', '{credits} credits were added to your account.', {
      credits: new Intl.NumberFormat(muneaLocale()).format(p),
    }));
  });
  renderPlanState();
  // 蘋果內購（StoreKit）購買成功 → 前端生效的唯一入口。
  // Mac 原生端付款成功（含沙盒測試）就呼叫這支，傳 App Store Connect 的產品 ID（見金流步驟單第 4 步表）。
  // 回傳 true=已生效、false=不認得的產品 ID。示範按鈕之後換真金流時，也一律改走這支。
  window.__muneaApplyPurchase = function (productId, purchase) {
    const pid = String(productId || '');
    const SUB_PID = {
      'net.munea.app.plus.monthly': 'plus', 'net.munea.app.plus.yearly': 'plus',
      'net.munea.app.pro.monthly': 'pro', 'net.munea.app.pro.yearly': 'pro'
    };
    const PT_PID = { 'net.munea.app.points.200': 100, 'net.munea.app.points.500': 300, 'net.munea.app.points.1000': 600, 'net.munea.app.points.1800': 1000 };
    if (SUB_PID[pid]) {
      try { localStorage.setItem('munea.plan', SUB_PID[pid]); localStorage.removeItem('munea.planNext'); } catch (e) {}
      trackProductEvent('subscription_purchased', { productId: pid, plan: SUB_PID[pid] });
      renderSubscriptionEndDate(purchase && purchase.billing && purchase.billing.subscription);
      renderPlanState();
      if (typeof renderFcRoster === 'function') { try { renderFcRoster(); } catch (e2) {} }
      void refreshServerPlanEntitlement();
      toast(subscriptionSuccessMessage(SUB_PID[pid], purchase && purchase.billing && purchase.billing.subscription), 4200);
      return true;
    }
    if (PT_PID[pid]) {
      try { localStorage.setItem('munea.ptsBought', String((POINTS.bought || 0) + PT_PID[pid])); } catch (e3) {}
      trackProductEvent('points_purchased', { productId: pid, points: PT_PID[pid] });
      pushWallet(); renderPoints();
      toast(muneaT('purchase.success', '{credits} credits were added to your account.', {
        credits: new Intl.NumberFormat(muneaLocale()).format(PT_PID[pid]),
      }));
      return true;
    }
    return false;
  };
  const famSwitch = $('#famSwitch');
  if (famSwitch) famSwitch.addEventListener('click', e => {
    const b = e.target.closest('.fam-switch-item'); if (!b) return;
    const p = b.dataset.person;
    if (p === 'all') showFamAll();
    else if (p === 'invite') {
      // 家人頁的邀請入口跟設定頁同一套規則：2026-07-31 起免費也能邀，只有圈滿了才擋
      if (loadCircle().length >= (CIRCLE_LIMITS[circlePlan()] || 4)) { toast(muneaT('familyCircle.fullUpgradeToast', '全家健康圈滿了，升級方案可以邀請更多家人。')); return; }
      if ($('#inviteFamModal')) { fillInvCode(true); $('#inviteFamModal').classList.add('show'); }
    }
    else showFamPerson(p, b.dataset.rel, b.dataset.init, b.dataset.tint);
  });
  const healthList = $('#healthList');
  if (healthList) healthList.addEventListener('click', e => {
    const r = e.target.closest('.health-row'); if (!r) return;
    showFamPerson(r.dataset.person, r.dataset.rel, r.dataset.init, r.dataset.tint);
  });
  renderFamRoster();   // 開頁就以家庭圈名單為準重建家人頁（兩本帳合一）
  // 狀態頁底部「接上 Apple 健康」卡 → 點了直接進「連接裝置」頁（Edward 7/9：綠字連結要真的能走）
  if ($('#stConnectCard')) $('#stConnectCard').addEventListener('click', () => { window.__connectFrom = 'status'; showView('connect'); });
  // ===== 家人頁圖表：跟狀態頁同一款長相（柱狀＋目標虛線），活動量/睡眠/心情 週月直接切 =====
  function famBarsHTML(labels, values, goal, colorFn, hiIdx) {
    const max = Math.max(goal, Math.max.apply(null, values)) * 1.15;
    const goalPct = Math.min(96, Math.round((goal / max) * 100));
    const bars = values.map((v, i) => {
      const h = Math.max(6, Math.round((v / max) * 100));
      const isHi = i === hiIdx;
      return '<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:6px;position:relative;z-index:1">' +
        '<div style="width:100%;max-width:24px;height:' + h + '%;border-radius:7px 7px 3px 3px;background:' + colorFn(v) + '"></div>' +
        '<div style="font-size:14px;color:' + (isHi ? 'var(--teal-dd)' : 'var(--muted)') + ';font-weight:' + (isHi ? '900' : '700') + '">' + labels[i] + '</div></div>';
    }).join('');
    return '<div style="position:relative;display:flex;align-items:flex-end;gap:8px;height:96px">' +
      '<div style="position:absolute;left:0;right:0;bottom:' + goalPct + '%;border-top:1.5px dashed rgba(90,105,99,.4)"></div>' + bars + '</div>';
  }
  // 家人示範數據（正式版＝那位家人自己的沐寧經雲端同步；頁面上方已標「示範資料」）
  const FAM_WD = [muneaT('mood.weekdayShortMon', '一'), muneaT('mood.weekdayShortTue', '二'), muneaT('mood.weekdayShortWed', '三'), muneaT('mood.weekdayShortThu', '四'), muneaT('mood.weekdayShortFri', '五'), muneaT('mood.weekdayShortSat', '六'), muneaT('mood.weekdayShortSun', '日')];
  const FAM_WL = [1, 2, 3, 4].map(n => muneaT('mood.weekN', '第{n}週', { n }));
  // 7/9 正式化：家人趨勢改吃真同步的 35 天日記帳（沒有資料＝誠實空狀態）
  function famTrendFor(p) {
    const v = famVitalsFor(p);
    const log = v && v.log && typeof v.log === 'object' ? v.log : null;
    if (!log) return null;
    const days = Object.keys(log).sort();
    if (!days.length) return null;
    const pick = (arr, field) => arr.map(k => +((log[k] || {})[field]) || 0);
    const w = days.slice(-7);
    const stepsW = pick(w, 'steps'), sleepW = pick(w, 'sleepHours');
    // 月＝最近 28 天切 4 週取均（不足老實少幾根）
    const m = days.slice(-28);
    const chunk = (arr) => { const out = []; for (let i = 0; i < arr.length; i += 7) { const seg = arr.slice(i, i + 7).filter(Boolean); out.push(seg.length ? Math.round(seg.reduce((a, b) => a + b, 0) / seg.length) : 0); } return out; };
    const stepsM = chunk(pick(m, 'steps'));
    const sleepM = chunk(pick(m, 'sleepHours')).map(x => Math.round(x * 10) / 10);
    const wd = w.map(k => FAM_WD[(new Date(k + 'T12:00:00').getDay() + 6) % 7] || '');
    if (!stepsW.some(Boolean) && !sleepW.some(Boolean)) return null;
    return { stepsW, sleepW, stepsM, sleepM, wd };
  }
  const FAM_STEP_GOAL = 7000, FAM_SLEEP_GOAL = 7.5;
  function famAvg(a, dec) { let s = 0; a.forEach(v => s += v); const m = s / a.length; return dec ? +m.toFixed(dec) : Math.round(m); }
  function famEmptyChart(box, note, name) {
    if (box) box.innerHTML = '<div style="padding:16px 2px;font-size:14.5px;color:var(--muted);text-align:center;line-height:1.7">' + muneaT('health.famEmptyData', '等{name}連上沐寧，這裡就會長出他的真數據', { name }) + '</div>';
    if (note) note.textContent = '';
  }
  let _famActRange = 'week', _famSleepRange = 'week', _famMoodRange = 'week';
  function renderFamAct() {
    const box = $('#famActChart'), note = $('#trendNote');
    const t = famTrendFor(currentPerson);
    if (!t || !(_famActRange === 'week' ? t.stepsW : t.stepsM).some(Boolean)) return famEmptyChart(box, note, currentPerson || muneaT('familyCircle.memberFallback', '家人'));
    const wk = _famActRange === 'week';
    const vals = wk ? t.stepsW : t.stepsM;
    if (box) box.innerHTML = famBarsHTML(wk ? t.wd : FAM_WL.slice(0, vals.length), vals, FAM_STEP_GOAL, v => v >= FAM_STEP_GOAL ? 'var(--teal)' : 'var(--gold)', vals.length - 1);
    if (note) note.innerHTML = muneaT('health.famStepsNote', '日均 {avgBold} · 達標 {met}/{total}{unit}{trailing}', { avgBold: '<b>' + famAvg(vals).toLocaleString() + ' ' + muneaT('health.unit.steps', '步') + '</b>', met: vals.filter(v => v >= FAM_STEP_GOAL).length, total: vals.length, unit: ' ' + (wk ? muneaT('health.famStepsUnitDays', '天') : muneaT('health.famStepsUnitWeeks', '週')), trailing: vals.length < (wk ? 7 : 4) ? ' · ' + muneaT('health.famAccumulating', '累積中') : '' });
  }
  function renderFamSleep() {
    const box = $('#famSleepChart'), note = $('#famSleepNote');
    const t = famTrendFor(currentPerson);
    if (!t || !(_famSleepRange === 'week' ? t.sleepW : t.sleepM).some(Boolean)) return famEmptyChart(box, note, currentPerson || muneaT('familyCircle.memberFallback', '家人'));
    const wk = _famSleepRange === 'week';
    const vals = wk ? t.sleepW : t.sleepM;
    if (box) box.innerHTML = famBarsHTML(wk ? t.wd : FAM_WL.slice(0, vals.length), vals, FAM_SLEEP_GOAL, v => v >= 7.5 ? 'var(--teal)' : (v >= 6.5 ? 'var(--gold)' : 'var(--coral)'), vals.length - 1);
    if (note) note.innerHTML = muneaT('health.famSleepNote', '平均 {avgBold}{quality}', { avgBold: '<b>' + famAvg(vals.filter(Boolean), 1) + ' ' + muneaT('health.unit.hoursShort', '小時') + '</b>', quality: ' · ' + (famAvg(vals.filter(Boolean), 1) >= 7 ? muneaT('health.famSleepSteady', '睡得穩') : muneaT('health.famSleepShort', '睡得偏少，多留意')) });
  }
  // 心情週/月：色點跟狀態頁情緒球同一套顏色
  const FAM_MOOD_COLS = ['#F4B63A', '#2FB7A8', '#236C66', '#6D7F91', '#D98A32', '#E95B4F'];
  const FAM_MOOD_NAME = [
    () => muneaT('mood.happy', '開心'),
    () => muneaT('mood.pleasant', '愉悅'),
    () => muneaT('mood.calm', '平靜'),
    () => muneaT('mood.low', '低落'),
    () => muneaT('mood.anxious', '焦慮'),
    () => muneaT('mood.angry', '生氣'),
  ];
  function renderFamMoodRange() {
    const box = $('#mcRangeBody'), note = $('#mcRangeNote');
    const seq = null;   // 7/9 正式化：心情軌跡只認真資料；跨裝置心情水管還沒接、一律誠實空狀態
    if (!seq) { if (box) box.innerHTML = ''; if (note) note.textContent = muneaT('mood.familyTrailEmpty', '等{name}開始用沐寧聊天，這裡會長出他的心情軌跡。', { name: currentPerson || muneaT('familyCircle.memberFallback', '家人') }); return; }
    if (_famMoodRange === 'week') {
      if (box) box.innerHTML = '<div class="mood-mini">' + seq.map((mi, i) =>
        '<div class="mm-day"><div class="mm-dot" style="background:' + FAM_MOOD_COLS[mi] + '"></div><div class="mm-lab">' + FAM_WD[i] + '</div></div>').join('') + '</div>';
      const cnt = {}; seq.forEach(x => cnt[x] = (cnt[x] || 0) + 1);
      const main = (FAM_MOOD_NAME[+Object.keys(cnt).sort((a, b) => cnt[a] - cnt[b]).pop()] || (() => ''))();
      if (note) note.innerHTML = muneaT('mood.weekMostly', '過去 7 天多在{moodBold}；顏色跟狀態頁的情緒球同一套。', { moodBold: '<b>' + main + '</b>' });
    } else {
      const cells = Array.from({ length: 30 }, (_, i) => seq[i % seq.length]);
      if (box) box.innerHTML = '<div class="mood-grid">' + cells.map(mi => '<i style="background:' + FAM_MOOD_COLS[mi] + '"></i>').join('') + '</div>';
      if (note) note.innerHTML = muneaT('mood.monthMapNote', '過去 30 天的心情地圖；一格一天、顏色跟情緒球同一套。');
    }
  }
  function renderFamTrends() { renderFamAct(); renderFamSleep(); renderFamMoodRange(); }
  function bindFamTabs(id, setter) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      el.querySelectorAll('button').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      setter(b.dataset.range || b.dataset.r);
    });
  }
  bindFamTabs('#trendTabs', r => { _famActRange = r; renderFamAct(); });
  bindFamTabs('#sleepTabs', r => { _famSleepRange = r; renderFamSleep(); });
  bindFamTabs('#mcRangeTabs', r => { _famMoodRange = r; renderFamMoodRange(); });

  // ── 就診摘要 ──────────────────────────────────────────
  // 入口有三個：今天的看診任務卡、設定頁、以及就診推播。
  // 2026-07-29 改成全螢幕子頁後，關閉走 nav-back，不再有遮罩可以點掉。
  if ($('#reportClose')) $('#reportClose').addEventListener('click', closeVisitSummary);

  // 期間切換：診間現場也能切（醫生問「這狀況多久了」→ 當場切到 60 天給他看）
  if ($('#rptPeriodTabs')) $('#rptPeriodTabs').addEventListener('click', async e => {
    const b = e.target.closest('.seg-btn');
    if (!b) return;
    const days = parseInt(b.dataset.days, 10);
    if (!days || days === _rptPeriod) return;
    _rptPeriod = days;
    setVisitSummaryPeriod(days);          // 也更新預設值，下次打開就是這個
    syncVisitSummaryTabs();
    try { trackProductEvent('visit_summary_period_changed', { periodDays: days }); } catch (e2) {}
    await loadVisitSummaryInto(days);
  });

  // 匯出：按一下就好（Edward 2026-07-29：「不需要顯示一堆提醒或流程，
  // 直接轉為 PDF 然後跳出 App 分享的系統預設窗」）。
  // 原本要先答一個 confirm、再選 1/2/3 的 prompt 選單，兩關才拿得到檔案，
  // 而且那兩個都是瀏覽器的原生醜視窗。現在：PDF → 系統分享面板，其餘交給 iOS。
  //
  // 為什麼還留退路：window.print() 在 iOS 的 WKWebView **完全無效**，所以
  // App 內一定要走原生外掛；瀏覽器開的時候沒有外掛，退回系統分享純文字。
  if ($('#rptExportBtn')) $('#rptExportBtn').addEventListener('click', async () => {
    const btn = $('#rptExportBtn');
    if (btn.dataset.busy === '1') return;      // 連按兩下不要跑兩份
    btn.dataset.busy = '1';
    const hasNativePdf = !!(muneaExportPlugin() && typeof muneaExportPlugin().sharePdf === 'function');
    try { trackProductEvent('visit_summary_exported', { periodDays: _rptPeriod, path: hasNativePdf ? 'pdf' : 'text' }); } catch (e) {}
    try {
      if (hasNativePdf) {
        const r = await exportVisitSummaryPdf(_rptLastSummary);
        if (!r.ok) toast(muneaT('visit.pdfFailed', 'PDF 這次沒做出來，請再試一次'));
        return;
      }
      // 沒有原生外掛（瀏覽器）：退回系統分享純文字，仍然是「按一下就跳系統視窗」
      const text = visitSummaryAsText(_rptLastSummary);
      if (navigator.share) { await navigator.share({ text }).catch(() => {}); return; }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        toast(muneaT('visit.copied', '摘要複製好了'));
        return;
      }
      toast(muneaT('visit.exportUnsupported', '這台裝置沒辦法匯出，晚點在手機上試'));
    } finally {
      btn.dataset.busy = '';
    }
  });

  // 發起挑戰面板
  const chalModal = $('#chalModal');
  const closeChal = () => chalModal && chalModal.classList.remove('show');
  // 「找誰一起」吃全家健康圈真名單（排除本人）、開窗時重畫；圈空時給邀請引導——不再用寫死的示範四人（7/15 修）
  function chalEsc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function renderInviteList() {
    const box = $('#inviteList'); if (!box) return;
    const mem = loadCircle().filter(m => !m.self);
    if (!mem.length) {
      box.innerHTML = '<div class="iv-empty">' + muneaT('familyCircle.emptyInvitePick', '圈裡還沒有家人。先到家人頁「邀請家人加入」，之後就能在這裡找他們一起。') + '</div>';
      return;
    }
    box.innerHTML = mem.map(m =>
      '<button type="button" class="iv on" data-name="' + chalEsc(m.name) + '"><span class="iv-ava"><span class="init-ava ' + chalEsc(muneaSafeTint(m.tint, m.name)) + '">' + chalEsc(famInit(m)) + '</span></span>' + chalEsc(m.name) + '</button>'
    ).join('');
  }
  if ($('#newChalBtn')) $('#newChalBtn').addEventListener('click', () => {
    if (!chalModal) return;
    renderInviteList();
    const cur = document.querySelector('.chal-type.active');
    applyChalKind(cur ? (cur.dataset.kind || 'walk') : 'walk');
    recalcWalk(true);   // 名單重畫後人數會變，目標步數建議跟著重算
    // 預填日期：運動=今天開始、問答=後天截止、揪一攤=這週六、抽獎=今天（時間欄各有預設）
    try {
      const t0 = new Date();
      const sat = new Date(t0); sat.setDate(sat.getDate() + (((6 - sat.getDay() + 7) % 7) || 7));
      const due = new Date(t0); due.setDate(due.getDate() + 2);
      const w7 = new Date(t0); w7.setDate(w7.getDate() + 7);
      if ($('#walkDue') && !$('#walkDue').value) { $('#walkDue').value = isoOf(w7); if (typeof syncWalkDays === 'function') syncWalkDays(); }
      if ($('#quizDue') && !$('#quizDue').value) $('#quizDue').value = isoOf(due);
      if ($('#voteDue') && !$('#voteDue').value) $('#voteDue').value = isoOf(due);
      if ($('#evDate') && !$('#evDate').value) $('#evDate').value = isoOf(sat);
      if ($('#drawDate') && !$('#drawDate').value) $('#drawDate').value = isoOf(t0);
    } catch (e) {}
    chalModal.classList.add('show');
  });
  const WD_KEYS = ['mood.weekdayShortSun', 'mood.weekdayShortMon', 'mood.weekdayShortTue', 'mood.weekdayShortWed', 'mood.weekdayShortThu', 'mood.weekdayShortFri', 'mood.weekdayShortSat'];
  const WD_ZH = ['日', '一', '二', '三', '四', '五', '六'];
  function fmtDay(d) {
    if (!(muneaLocale() || 'zh-TW').startsWith('zh')) {
      return new Intl.DateTimeFormat(muneaLocale(), { month: 'numeric', day: 'numeric', weekday: 'short' }).format(d);
    }
    return (d.getMonth() + 1) + '/' + d.getDate() + '（' + muneaT('mood.weekdayLabel', '週{day}', { day: muneaT(WD_KEYS[d.getDay()], WD_ZH[d.getDay()]) }) + '）';
  }
  function isoOf(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  // 就診日期（Edward 2026-08-01：原本只給未來 14 天，兩個月後的回診記不進來）。
  // 用手機自己的年月日行事曆——四個語系的月份、星期、排列順序都由系統給，
  // 不必為了日期硬刻四套文字。今天／明天留成快捷，長輩最常用的還是一點就好。
  function visitPickedISO() {
    const input = $('#visitDate');
    return (input && input.value) || '';
  }
  function visitDateLabel(d) {
    // 中文的排法會擠成「2026年8月2日週日」——星期直接黏在日期後面。
    // 日文自己會加括號、英文西文本來就有逗號，所以只在缺分隔的語系補一個空格。
    const parts = new Intl.DateTimeFormat(muneaLocale(), {
      year: 'numeric', month: 'long', day: 'numeric', weekday: 'short',
    }).formatToParts(d);
    // 判斷「要不要補空格」不能看前一段是不是分隔符號——中文的「日」本身就是分隔符號，
    // 看類型會誤判成不用補（第一版就錯在這裡）。改看前一段的最後一個字：
    // 已經是空白或左括號（日文的「(土)」）就不補，其餘才補。
    return parts.map((part, i) => {
      const prev = parts[i - 1];
      const tail = prev ? prev.value.slice(-1) : '';
      const alreadySeparated = !prev || /[\s([（]/.test(tail);
      return (part.type === 'weekday' && !alreadySeparated ? ' ' : '') + part.value;
    }).join('').trim();
  }
  function syncVisitDateField() {
    const input = $('#visitDate');
    const text = $('#visitDateText');
    if (!input || !text) return;
    const iso = input.value;
    const d = iso ? new Date(iso + 'T00:00') : null;
    text.textContent = (d && !Number.isNaN(d.getTime()))
      ? visitDateLabel(d)
      : muneaT('appointment.pickDate', '選日期');
  }
  function visitLeadMinutes() {
    const on = document.querySelector('#visitLeadChips .mchip.on');
    const raw = on ? Number(on.dataset.m) : NaN;
    return Number.isFinite(raw) ? raw : VISIT_LEAD_DEFAULT;
  }
  function wireVisitLeadChips() {
    const box = $('#visitLeadChips');
    if (!box || box.dataset.wired) return;
    box.dataset.wired = '1';
    box.addEventListener('click', (e) => {
      const chip = e.target.closest('.mchip');
      if (!chip) return;
      box.querySelectorAll('.mchip').forEach(x => x.classList.remove('on'));
      chip.classList.add('on');
    });
  }
  function resetVisitLead() {
    const box = $('#visitLeadChips');
    if (!box) return;
    box.querySelectorAll('.mchip').forEach(x =>
      x.classList.toggle('on', Number(x.dataset.m) === VISIT_LEAD_DEFAULT));
  }
  function resetVisitDate() {
    const input = $('#visitDate');
    if (!input) return;
    const now = new Date();
    input.min = isoOf(now);              // 提醒不能設在過去
    input.value = isoOf(now);
    syncVisitDateField();
  }
  function wireVisitDateField() {
    const input = $('#visitDate');
    if (!input || input.dataset.wired) return;
    input.dataset.wired = '1';
    input.addEventListener('change', syncVisitDateField);
    input.addEventListener('input', syncVisitDateField);
    input.min = isoOf(new Date());
  }
  function loadActs() { try { return JSON.parse(localStorage.getItem('munea.activities')) || []; } catch (e) { return []; } }
  function saveActs(a) { try { localStorage.setItem('munea.activities', JSON.stringify(a)); } catch (e) {} syncPush('activities', a); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  // 聊聊 AI 記行程（7/16 Edward「約吃飯被設成看診」）：約會/聚餐/出遊走揪一攤這本帳，
  // 同步與「活動前 30 分提醒」都沿用現成水管（saveActs 內建）；看診/用藥帳本完全不碰
  window.__muneaAddPersonalEvent = async function (a) {
    const rawTitle = String((a && a.title) || '').trim();
    const title = (rawTitle && muneaIsCleanSpeechText(rawTitle)) ? rawTitle : muneaT('event.familyTitle', '和家人的約');
    const dateISO = String((a && a.dateISO) || '').trim();
    const time = String((a && a.time) || '').trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateISO) || !/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return { ok: false, error: 'invalid_date_or_time' };
    const when = new Date(dateISO + 'T' + time + ':00');
    if (Number.isNaN(when.getTime()) || when.getTime() < Date.now() - 60000) return { ok: false, error: 'event_time_in_past' };
    const rawPlace = String((a && a.place) || '').trim();
    const act = {
      id: Date.now(), kind: 'event', names: [], owner: myFeedName(),
      title, place: (rawPlace && muneaIsCleanSpeechText(rawPlace)) ? rawPlace : '',
      dateISO, time, dateLabel: fmtDay(when) + ' ' + _clock12(time),
    };
    const acts = loadActs(); acts.push(act); saveActs(acts);
    try { renderActCard(act); } catch (e) {}
    try { if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks(); } catch (e) {}
    try { trackProductEvent('activity_created', { kind: 'event', source: 'voice-ai' }); } catch (e) {}
    return { ok: true, title, label: act.dateLabel };
  };
  // 家庭圈另外四種活動也要能用講的開（Edward 2026-08-01：所有家庭圈活動）。
  // 揪一攤走上面的 __muneaAddPersonalEvent（已驗過的路、不動）；這裡負責
  // 一起運動／機智問答／投票／抽獎。缺什麼就回什麼錯誤代碼，讓寧寧照著問，
  // 不要默默用預設值把活動發出去——發出去全家人都看得到，改起來很尷尬。
  window.__muneaAddFamilyActivity = async function (a) {
    a = a || {};
    const kind = String(a.kind || '').trim().toLowerCase();
    if (!['walk', 'quiz', 'vote', 'draw'].includes(kind)) return { ok: false, error: 'unsupported_activity_kind' };
    const dateISO = String(a.dateISO || '').trim();
    const time = /^([01]\d|2[0-3]):[0-5]\d$/.test(String(a.time || '')) ? String(a.time) : '20:00';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateISO)) return { ok: false, error: 'invalid_date' };
    const day = new Date(dateISO + 'T00:00');
    if (Number.isNaN(day.getTime())) return { ok: false, error: 'invalid_date' };
    const when = new Date(dateISO + 'T' + time + ':00');
    if (when.getTime() < Date.now() - 60000) return { ok: false, error: 'activity_time_in_past' };
    // 字數上限：中日文一個字塞得下的資訊量，拉丁字母要用兩倍的字元寫。
    // 共用 24 會把英文的獎品名切掉（「A walk with your grandkid」→「grandki」，
    // 2026-08-01 截圖看見）。
    const nameCap = (muneaLocale() === 'en' || muneaLocale() === 'es') ? 48 : 24;
    const clean = (v) => {
      const raw = String(v || '').trim().slice(0, nameCap);
      return (raw && muneaIsCleanSpeechText(raw)) ? raw : '';
    };
    const act = { id: Date.now(), kind, names: [], owner: myFeedName() };
    const dueLabel = muneaT('activity.dueAt', '{when} 截止', { when: fmtDay(day) + ' ' + _clock12(time) });
    if (kind === 'walk') {
      const today = new Date();
      const day0 = new Date(today.getFullYear(), today.getMonth(), today.getDate());
      act.startISO = isoOf(today);
      act.days = Math.max(1, Math.round((day - day0) / 86400000));
      act.dateISO = dateISO; act.dueTime = time; act.dueLabel = dueLabel;
      // 步數目標：跟畫面上自己開的一樣、預設三萬步。
      // 少了這個，卡片會印出「大家一起走 非數值 步」（2026-08-01 截圖才看見——
      // 文字測試只看回傳 ok，看不到卡片上寫什麼）。
      const goalRaw = Number(a.stepGoal);
      act.goal = (Number.isFinite(goalRaw) && goalRaw >= 1000 && goalRaw <= 200000)
        ? Math.round(goalRaw / 1000) * 1000
        : 30000;
      act.title = muneaT('activity.exercise', '一起運動');
    } else if (kind === 'quiz') {
      const n = Number(a.questionCount);
      act.q = (Number.isFinite(n) && n >= 5 && n <= 20) ? Math.round(n) : 10;
      act.title = muneaT('activity.quiz', '機智問答');
      act.dueISO = dateISO; act.dueTime = time; act.dueLabel = dueLabel;
    } else if (kind === 'vote') {
      const question = clean(a.title);
      if (!question) return { ok: false, error: 'vote_question_required' };
      const opts = (Array.isArray(a.options) ? a.options : []).map(clean).filter(Boolean).slice(0, 3);
      if (opts.length < 2) return { ok: false, error: 'vote_needs_two_options' };
      act.title = question; act.opts = opts; act.votes = {};
      act.dueISO = dateISO; act.dueTime = time; act.dateISO = dateISO; act.dueLabel = dueLabel;
    } else {
      const prizes = (Array.isArray(a.prizes) ? a.prizes : []).map(clean).filter(Boolean).slice(0, 3);
      if (!prizes.length) return { ok: false, error: 'draw_prize_required' };
      act.prizes = prizes.map(name => ({ name, n: 1 }));
      act.prize = prizes[0];        // 舊欄位留著：通知、記錄簿、家人動態都還在讀它
      act.dateISO = dateISO; act.dueTime = time;   // 小標籤要印時間，靠這格
      act.when = fmtDay(day) + ' ' + _clock12(time);
      act.title = muneaT('activity.luckyDrawTitle', '幸運抽獎');
    }
    const acts = loadActs(); acts.push(act); saveActs(acts);
    try { renderActCard(act); } catch (e) {}
    try { if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks(); } catch (e) {}
    try { trackProductEvent('activity_created', { kind: kind, source: 'voice-ai' }); } catch (e) {}
    return { ok: true, kind, title: act.title, label: act.dueLabel || act.when || '' };
  };
  const FAM_AVA = { '阿嬤': [() => muneaT('demo.family.gmInit', '嬤'), 'p-ama'], '美華': [() => muneaT('demo.family.d1Init', '華'), 'p-mei'], '志明': [() => muneaT('demo.family.s1Init', '明'), 'p-zhi'], '小寶': [() => muneaT('demo.family.g1Init', '寶'), 'p-bao'], '你': [() => muneaT('common.meInitial', '我'), 'p-me'] };
  function buildRankList(act) {
    const rows = Object.entries(act.answers).sort((x, y) => y[1] - x[1]);
    return '<div class="rank-list">' + rows.map((r2, i3) => {
      const av = FAM_AVA[r2[0]] || [r2[0][0], 'p-me'];
      const avInit = typeof av[0] === 'function' ? av[0]() : av[0];
      const noCls = i3 === 0 ? 'n1' : i3 === 1 ? 'n2' : i3 === 2 ? 'n3' : '';
      return '<div class="rank-row"><span class="rank-no ' + noCls + '">' + (i3 + 1) + '</span>' +
        '<span class="rank-av"><span class="init-ava ' + av[1] + '">' + avInit + '</span></span>' +
        '<b>' + actDisplayName(r2[0]) + '</b><span class="rank-score">' + muneaT('activity.rankCorrectCount', '答對 {count} 題', { count: r2[1] }) + '</span></div>';
    }).join('') + '</div><div class="qc-life">' + muneaT('activity.rankRetention', '排名保留一天，明天自動收進記錄簿') + '</div>';
  }
  // 揪一攤：我要去／我沒空 ＋ 名單（Edward 7/9：補完整互動）
  function renderEventBody(act, box) {
    const my = act.rsvp && act.rsvp['你'];
    const going = Object.entries(act.rsvp || {}).filter(([, v]) => v === 'go').map(([n]) => n);
    const no = Object.entries(act.rsvp || {}).filter(([, v]) => v === 'no').map(([n]) => n);
    // 活動時間過了就鎖住（時間點以前才能選、之後只看結果）— Edward 7/9
    let locked = false;
    try { if (act.dateISO) { const dt = new Date(act.dateISO + 'T' + (act.time || '23:59')); if (!isNaN(dt) && dt < new Date()) locked = true; } } catch (e) {}
    box.innerHTML =
      '<div class="ad-note"><b>' + act.title + '</b>' + (act.place ? ' · ' + act.place : '') + (act.dateLabel ? '<br>' + act.dateLabel : '') + '</div>' +
      '<div class="rsvp-btns"><button type="button" class="rsvp-btn go' + (my === 'go' ? ' on' : '') + '" data-r="go"' + (locked ? ' disabled' : '') + '>' + muneaT('activity.rsvpGo', '我要去') + '</button>' +
      '<button type="button" class="rsvp-btn no' + (my === 'no' ? ' on' : '') + '" data-r="no"' + (locked ? ' disabled' : '') + '>' + muneaT('activity.rsvpNo', '我沒空') + '</button></div>' +
      '<div class="qc-num">' + (going.length ? muneaT('activity.rsvpGoing', '要去的：{names}', { names: going.map(actDisplayName).join(muneaListSeparator()) }) : muneaT('activity.rsvpNoneYet', '還沒有人回「要去」')) + (no.length ? '　·　' + muneaT('activity.rsvpBusy', '沒空：{names}', { names: no.map(actDisplayName).join(muneaListSeparator()) }) : '') +
      '；' + (locked ? muneaT('activity.rsvpLocked', '活動時間到了，不能再改。') : (my ? muneaT('activity.rsvpTailMine', '想改隨時再點另一個就好；其他家人打開 App 也會看到。', { companion: cname() }) : muneaT('activity.rsvpTailAsk', '點一下回覆；其他家人打開 App 也會看到。', { companion: cname() }))) + '</div>';
    if (!locked) box.querySelector('.rsvp-btns').addEventListener('click', e => {
      const b = e.target.closest('.rsvp-btn'); if (!b || b.disabled) return;
      act.rsvp = act.rsvp || {}; act.rsvp['你'] = b.dataset.r;
      const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) t.rsvp = act.rsvp; saveActs(acts);
      renderEventBody(act, box);
      toast(b.dataset.r === 'go' ? muneaT('activity.rsvpGoToast', '好，記下你要去了') : muneaT('activity.rsvpSkipToast', '好，記下你這次沒空'));
    });
  }
  // 一起運動：進度條 ＋ 每人步數（你的自動吃 Apple 健康、其他人吃帶回的數據）
  // 一起運動的名次（Edward 2026-08-01「這裡可以做個排名」）。
  // 兩條規矩：① 平手就同名次、下一位跳號（走一樣多不該有人被排後面）
  //          ② 0 步的人不給名次——沒資料不等於走最少，排他第 8 名是替他認了沒發生的事。
  function walkRanked(names, steps) {
    const rows = names.map(n => ({ name: n, steps: Math.max(0, +steps[n] || 0) }));
    rows.sort((a, b) => b.steps - a.steps);
    let rank = 0, seen = 0, prev = null;
    rows.forEach(r => {
      if (r.steps <= 0) { r.rank = 0; return; }
      seen += 1;
      if (r.steps !== prev) { rank = seen; prev = r.steps; }
      r.rank = rank;
    });
    return rows;
  }
  // 某個人在這場活動裡真正走了多少（Edward 2026-08-01）
  //
  // 以前直接抓「今天的總步數」——早上十點發起，那八千步是活動開始前走的，
  // 卻整份灌進大家一起完成的目標裡，數字一開始就是假的。
  //
  // 現在：發起當天只算超出基準線的部分，之後每天算整天。跨天的資料從
  // 雲端的每日紀錄拿；拿不到就只認今天的增量，寧可少算也不要憑空多加。
  // 舊活動沒有 baseline，維持原本算法——進行中的活動數字不該一夜之間變小。
  function walkStepsFor(act, name) {
    let latest = 0, log = null;
    try {
      if (name === '你') {
        const h = JSON.parse(localStorage.getItem('munea.health.last') || 'null');
        if (h && h.s && typeof h.s.steps === 'number') latest = h.s.steps;
        const hist = JSON.parse(localStorage.getItem('munea.health.history') || 'null');
        if (hist && typeof hist === 'object') log = hist;
      } else {
        const v = famVitalsFor(name);
        if (v && v.steps) latest = +v.steps;
        if (v && v.log && typeof v.log === 'object') log = v.log;
      }
    } catch (e) {}
    latest = Math.max(0, +latest || 0);
    if (!act.baseline || !act.startISO) return latest || +((act._steps || {})[name]) || 0;   // 舊活動：照舊
    const base = Math.max(0, +act.baseline[name] || 0);
    const start = act.startISO;
    const today = isoOf(new Date());
    if (!log) {
      // 只拿得到最新的數字：唯一能誠實計算的就是「今天比基準多走的」
      return today === start ? Math.max(0, latest - base) : Math.max(0, latest - base);
    }
    let sum = 0;
    const d = new Date(start + 'T00:00');
    const end = new Date(today + 'T00:00');
    for (let guard = 0; d <= end && guard < 400; guard += 1, d.setDate(d.getDate() + 1)) {
      const key = isoOf(d);
      const day = log[key];
      const s = Math.max(0, +((day && (day.steps !== undefined ? day.steps : day.s)) || (key === today ? latest : 0)) || 0);
      sum += (key === start) ? Math.max(0, s - base) : s;
    }
    return sum;
  }
  function renderWalkBody(act, box) {
    const goal = +act.goal || 30000;
    const parts = actParts(act);
    const steps = {};
    parts.forEach(n => { steps[n] = walkStepsFor(act, n); });
    const sum = parts.reduce((s, n) => s + (+steps[n] || 0), 0);
    const pct = Math.min(100, goal ? Math.round(sum / goal * 100) : 0);
    const gap = Math.max(0, goal - sum);
    box.innerHTML =
      '<div class="walk-bar"><i style="width:' + pct + '%"></i></div>' +
      '<div class="walk-sum">' + (gap > 0 ? muneaT('activity.walkSumGap', '{sumBold} / {goal} 步 · 還差 {gap} 步', { sumBold: '<b>' + sum.toLocaleString() + '</b>', goal: goal.toLocaleString(), gap: gap.toLocaleString() }) : muneaT('activity.walkSumMet', '{sumBold} / {goal} 步 · 達標了！', { sumBold: '<b>' + sum.toLocaleString() + '</b>', goal: goal.toLocaleString() })) + '</div>' +
      '<div class="walk-people">' + (function (tints) { return walkRanked(parts, steps).map(r => {
        const avInit = avaPartsFor(r.name)[0];
        const avTint = tints[r.name] || avaTintFor(r.name);
        // 名次徽章只給真的有步數的人。0 步不是「最後一名」——可能只是手機還沒同步，
        // 標成第 8 名等於替使用者認了一件他沒做的事（Edward 2026-08-01「不要假設用戶做了什麼」）。
        const badge = r.rank
          ? '<span class="walk-rank' + (r.rank <= 3 ? ' r' + r.rank : '') + '">' + r.rank + '</span>'
          : '<span class="walk-rank none">·</span>';
        const val = r.steps > 0
          ? r.steps.toLocaleString() + ' ' + muneaT('health.unit.steps', '步')
          : muneaT('activity.walkNoSteps', '還沒有資料');
        // 佔比用「全家已經走的」當分母，不是用目標。8,260 步佔目標只有 4.9%（看了只會洩氣），
        // 佔全家是 21%——七個人加起來剛好一整份，看的是「我也出了一份力」。
        const share = sum > 0 ? Math.round(r.steps / sum * 100) : 0;
        return '<div class="walk-p' + (r.rank === 1 ? ' lead' : '') + (r.steps > 0 ? '' : ' quiet') + '">' +
          '<i class="wp-bar" style="width:' + share + '%"></i>' + badge +
          '<span class="init-ava ' + avTint + '">' + muneaEscapeHtml(avInit) + '</span><b>' + muneaEscapeHtml(actDisplayName(r.name)) + '</b>' +
          (r.steps > 0 ? '<span class="wp-pct">' + share + '%</span>' : '') +
          '<span>' + val + '</span></div>';
      }).join(''); })(avaTintMap(parts)) + '</div>' +
      '<div class="qc-num">' + muneaT('activity.walkAutoNote', '你的步數自動從 Apple 健康帶入；家人的步數同步過來就會一起算，{due}結算。', { due: act.dueLabel || muneaT('activity.daysChip', '{days} 天內', { days: act.days }) }) + '</div>';
  }
  // 家庭記錄簿（Edward 2026-08-01）
  //
  // 以前這頁是三張寫死在畫面上的範例卡，沒有任何程式在讀真的活動——而活動到期時
  // announceActEnd() 說「收進家庭記錄簿」、saveActs() 卻把它從清單刪掉，資料就沒了。
  // App 對使用者說了一件沒發生的事。現在到期的活動真的存進這本簿子。
  const FAMILY_BOOK_KEY = 'munea.familyBook';
  const FAMILY_BOOK_MAX = 30;          // 留最近 30 筆就夠翻，不必無限長
  function loadFamilyBook() {
    try { const a = JSON.parse(localStorage.getItem(FAMILY_BOOK_KEY) || '[]'); return Array.isArray(a) ? a : []; }
    catch (e) { return []; }
  }
  function recordInFamilyBook(a, resultText, people) {
    try {
      const book = loadFamilyBook();
      if (book.some(x => x && String(x.id) === String(a.id))) return;   // 同一場只記一次
      book.unshift({
        id: a.id,
        kind: a.kind || 'custom',
        title: String(a.title || '').slice(0, 40),
        endedAt: Date.now(),
        result: String(resultText || '').slice(0, 60),
        people: (people || []).filter(Boolean).slice(0, 6).map(n => String(n).slice(0, 8)),
      });
      localStorage.setItem(FAMILY_BOOK_KEY, JSON.stringify(book.slice(0, FAMILY_BOOK_MAX)));
      syncPush('familyBook', book.slice(0, FAMILY_BOOK_MAX));
    } catch (e) {}
  }
  // 活動結束時，依種類公布結果進記錄簿（不再只是「結束了」）
  function announceActEnd(a) {
    try {
      if (a.kind === 'quiz' && a.answers && Object.keys(a.answers).length) {
        const top = Object.entries(a.answers).sort((x, y) => y[1] - x[1])[0];
        pushFamilyFeed('「' + a.title + '」結算了——<b>' + top[0] + '</b> 答對最多（' + top[1] + ' 題），收進<b>家庭記錄簿</b>');
        recordInFamilyBook(a, muneaT('book.quizWinner', '{name} 答對最多（{n} 題）', { name: top[0], n: top[1] }), Object.keys(a.answers));
      } else if (a.kind === 'vote' && a.votes && Object.keys(a.votes).length) {
        const tally = {}; Object.values(a.votes).forEach(o => tally[o] = (tally[o] || 0) + 1);
        const win = Object.entries(tally).sort((x, y) => y[1] - x[1])[0];
        pushFamilyFeed('「' + a.title + '」投票結束——<b>' + win[0] + '</b> 最多票，收進<b>家庭記錄簿</b>');
        recordInFamilyBook(a, muneaT('book.voteWinner', '{name} 最多票', { name: win[0] }), Object.keys(a.votes));
      } else if (a.kind === 'draw' && a.picks && Object.keys(a.picks).length) {
        // 新玩法：大家早就各自抽完了，到期只是把結果收攏進記錄簿，不再重抽一次
        const got = Object.keys(a.picks).filter(n => a.picks[n]);
        if (got.length) {
          a.winners = got.map(n => ({ prize: a.picks[n], name: n }));
          a.winner = got[0];
          pushFamilyFeed(muneaT('feed.drawWinnersMulti', '開獎了——{list}！', {
            list: got.map(n => '<b>' + muneaEscapeHtml(n) + '</b> ' + muneaEscapeHtml(a.picks[n])).join(muneaListSeparator()),
          }));
          recordInFamilyBook(a, got.map(n => muneaT('book.drawWinnerItem', '{prize} {name}', { prize: a.picks[n], name: n })).join(muneaListSeparator()), Object.keys(a.picks));
        } else {
          pushFamilyFeed(muneaT('feed.drawNobody', '「{prize}」結束了，這次沒有人抽', { prize: a.prize || a.title }));
          recordInFamilyBook(a, muneaT('book.drawNobody', '沒有人抽'), []);
        }
      } else if (a.kind === 'draw' && !a.winner && a.tickets && Object.keys(a.tickets).length) {
        // 卡片上寫著「8/3 20:00 開獎」，時間到就真的要開（Edward 2026-08-01）。
        // 以前到期只會說一句「結束了」，抽獎等於沒有結果——那是對使用者說了一件沒發生的事。
        // 只從抽過的人裡開：沒抽的人本來就沒參加。
        const pool = Object.keys(a.tickets);
        const results = drawWinnersFrom(a.tickets, actPrizes(a));
        if (!results.length) return;
        a.winners = results;
        a.winner = results[0].name;
        if (results.length > 1) {
          pushFamilyFeed(muneaT('feed.drawWinnersMulti', '開獎了——{list}！', {
            list: results.map(w => muneaEscapeHtml(w.prize) + ' <b>' + muneaEscapeHtml(w.name) + '</b>').join(muneaListSeparator()),
          }));
          recordInFamilyBook(a, results.map(w => muneaT('book.drawWinnerItem', '{prize} {name}', { prize: w.prize, name: w.name })).join(muneaListSeparator()), pool);
        } else {
          const no = String(a.tickets[results[0].name]).padStart(2, '0');
          pushFamilyFeed(muneaT('feed.drawWinner', '「{prize}」開獎了——{name} 抽中（{no} 號）！', { prize: results[0].prize || a.title, name: '<b>' + muneaEscapeHtml(results[0].name) + '</b>', no }));
          recordInFamilyBook(a, muneaT('book.drawWinner', '{name} 抽中（{no} 號）', { name: results[0].name, no }), pool);
        }
      } else if (a.kind === 'draw' && !a.winner) {
        // 一個人都沒抽：誠實說沒開成，不要硬抽一個沒參加的人出來
        pushFamilyFeed(muneaT('feed.drawNobody', '「{prize}」結束了，這次沒有人抽', { prize: a.prize || a.title }));
        recordInFamilyBook(a, muneaT('book.drawNobody', '沒有人抽'), []);
      } else if (a.kind === 'event' && a.rsvp) {
        const going = Object.entries(a.rsvp).filter(([, v]) => v === 'go').map(([n]) => n);
        pushFamilyFeed('「' + a.title + '」結束了' + (going.length ? '（' + going.join('、') + ' 有去）' : '') + '，收進<b>家庭記錄簿</b>');
        recordInFamilyBook(a, going.length ? muneaT('book.eventWent', '{names} 有去', { names: going.join(muneaListSeparator()) }) : muneaT('book.eventEnded', '結束了'), going);
      } else {
        pushFamilyFeed('「' + a.title + '」結束了，收進<b>家庭記錄簿</b>');
        recordInFamilyBook(a, muneaT('book.eventEnded', '結束了'), a.names || []);
      }
    } catch (e) { pushFamilyFeed('「' + (a.title || '活動') + '」結束了，收進<b>家庭記錄簿</b>'); }
  }
  // 空狀態 #actEmpty＝唯一插入錨點（示範卡 7/15 拆掉後，頁上可能一張卡都沒有）
  function updateActEmpty() {
    const empty = document.getElementById('actEmpty');
    if (!empty) return;
    const pad = empty.closest('.pad');
    empty.style.display = pad && pad.querySelector('.quest-card') ? 'none' : '';
  }
  function renderActCard(act) {
    const empty = document.getElementById('actEmpty');
    if (!empty) return;
    if (actHidden(act)) return;   // 我自己收起來的，不畫；活動本身還在，別人照樣看得到
    const card = document.createElement('div');
    card.className = 'quest-card pending';
    let chip, goal, note;
    if (act.status === 'done') {
      chip = muneaT('activity.endedChip', '已結束');
      if (act.kind === 'quiz' && act.answers && Object.keys(act.answers).length) {
        act._rankHtml = buildRankList(act);
        goal = '';
        note = '';
      } else {
        goal = act.kind === 'quiz' ? muneaT('activity.quizScoreGoal', '你答對 {score} / {total} 題', { score: act.score, total: act.q || 5 }) : muneaT('activity.endedGoal', '{title} 結束了', { title: act.title });
        note = muneaT('activity.endedNote', '等大家都看過就收進記錄簿 · 最多留 3 天', { companion: cname() });
      }
    } else if (act.kind === 'walk') {
      // 鍵不可以寫成三元運算式——搬遷掃描器只認得寫死的鍵，看不到就把中文當成沒綁
      chip = act.days === 1
        ? muneaT('activity.daysChipOne', '{days} 天內', { days: act.days })
        : muneaT('activity.daysChip', '{days} 天內', { days: act.days });
      goal = muneaT('activity.walkGoal', '大家一起走 {steps} 步', { steps: (+act.goal).toLocaleString() });
      note = muneaT('activity.walkNote', '家人打開 App 就會看到；開始後每個人走多少都看得到', { companion: cname() });
      // 外層也要看得到進度跟自己走了多少——不然要點進去才知道（跟抽獎同一個道理）
      try {
        const wParts = actParts(act);
        const wSum = wParts.reduce((s, n) => s + walkStepsFor(act, n), 0);
        const wMine = walkStepsFor(act, '你');
        const wPct = act.goal ? Math.min(100, Math.round(wSum / +act.goal * 100)) : 0;
        note = muneaT('activity.walkCardProgress', '已經走了 {sum} 步（{pct}%）· 你走了 {mine} 步', {
          sum: wSum.toLocaleString(), pct: wPct, mine: wMine.toLocaleString(),
        });
        act._stateTag = wMine > 0
          ? { cls: 'got', text: muneaT('activity.walkStateMine', '你走了 {mine} 步', { mine: wMine.toLocaleString() }) }
          : { cls: 'todo', text: muneaT('activity.walkStateZero', '你還沒開始走') };
      } catch (e) {}
    } else if (act.kind === 'quiz') {
      chip = act.q === 1
        ? muneaT('activity.questionsChipOne', '{count} 題', { count: act.q })
        : muneaT('activity.questionsChip', '{count} 題', { count: act.q });
      if (act.myDone && act.answers && act.answers['你'] !== undefined) {
        goal = muneaT('activity.quizScoreGoal', '你答對 {score} / {total} 題', { score: act.answers['你'], total: act.q });
        note = muneaT('activity.quizWaitNote', '等 {names} 作答完看排名', { names: act.names.join(muneaListSeparator()), companion: cname() });
      } else {
        goal = muneaT('activity.quizReadyGoal', '你的 {count} 題準備好了', { count: act.q });
        note = muneaT('activity.quizReadyNote', '點這張卡先作答；其他人打開 App 也能玩，都答完看排名', { companion: cname() });
      }
    } else if (act.kind === 'vote') {
      // 這張卡也一樣是空的（跟抽獎同一個毛病）：選項、誰領先、我投了沒，
      // 全都要點進去才知道。外層就該答完這三件事。
      const voters = act.names.length + 1;
      chip = voters === 1
        ? muneaT('activity.peopleChipOne', '{count} 人', { count: voters })
        : muneaT('activity.peopleChip', '{count} 人', { count: voters });
      goal = (act.opts || []).join(muneaListSeparator());
      const vVotes = act.votes || {};
      const vCount = Object.keys(vVotes).length;
      const vMine = vVotes['你'];
      const vTally = {};
      Object.values(vVotes).forEach(o => { vTally[o] = (vTally[o] || 0) + 1; });
      const vTop = Object.entries(vTally).sort((a, b) => b[1] - a[1])[0];
      // 平手就不說誰領先——宣布一個其實沒領先的選項是錯的
      const vTied = vTop && Object.values(vTally).filter(n => n === vTop[1]).length > 1;
      note = vCount
        ? (vTop && !vTied
          ? muneaT('activity.voteCardLeading', '{n} 個人投了 · 「{opt}」{count} 票領先', { n: vCount, opt: vTop[0], count: vTop[1] })
          : muneaT('activity.voteCardTied', '{n} 個人投了 · 目前平手', { n: vCount }))
        : muneaT('activity.voteCardEmpty', '還沒有人投');
      act._stateTag = vMine
        ? { cls: 'got', text: muneaT('activity.voteStateMine', '你投了 {opt}', { opt: vMine }) }
        : { cls: 'todo', text: muneaT('activity.voteStateTodo', '還沒投') };
    } else if (act.kind === 'draw') {
      // 以前這張卡只有一行標題跟時間，中間整片空白（Edward 2026-08-01 一眼看出來）。
      // 抽獎最該讓人看到的是「有什麼獎」跟「我抽了沒」——前者決定他想不想點進去，
      // 後者是他每次打開 App 最想確認的一件事。
      chip = (actLegacyDraw(act) ? muneaT('activity.drawChip', '{when}開獎', { when: chipWhen(act) }) : muneaT('activity.drawChipDue', '{when}截止', { when: chipWhen(act) }));
      const dPrizes = actPrizes(act);
      goal = dPrizes.map(p => p.name).join(muneaListSeparator());
      const dPicks = act.picks || {};
      const dPicked = Object.keys(dPicks).length;
      const total = (act.names || []).length + 1;
      note = actLegacyDraw(act)
        ? muneaT('activity.drawCardPeople', '{total} 個人有機會', { total })
        : (dPicked
          ? muneaT('activity.drawCardProgress', '{total} 個人有機會，已經抽了 {n} 個', { total, n: dPicked })
          : muneaT('activity.drawCardPeople', '{total} 個人有機會', { total }));
      // 「我抽了沒」是他每次打開 App 最想確認的一件事，要能一眼看到、不必點進去
      if (!actLegacyDraw(act)) {
        const mine = dPicks['你'];
        const soldOut = !prizeSeatsLeft(act);
        act._stateTag = mine
          ? { cls: 'got', text: muneaT('activity.drawStateGot', '你抽到 {prize}', { prize: mine }) }
          : (mine === '' ? { cls: 'miss', text: muneaT('activity.drawStateMiss', '這次沒抽到') }
            : (soldOut ? { cls: 'over', text: muneaT('activity.drawStateSoldOut', '獎都被抽完了') }
              : { cls: 'todo', text: muneaT('activity.drawStateTodo', '還沒抽') }));
      }
    } else {
      chip = act.dateLabel || act.dueLabel || muneaT('activity.inProgress', '進行中');
      goal = muneaT('activity.eventGoal', '{title}，誰能到？', { title: (act.title || muneaT('activity.defaultEventTitle', '家庭活動')) + (act.place ? ' · ' + act.place : '') });
      note = muneaT('activity.eventNote', '家人打開 App 就會看到，回「去 / 沒空」；過了那天卡片會自動收進記錄簿', { companion: cname() });
    }
    const rwLine = act.rewards && act.rewards.some(Boolean)
      ? '<div class="qc-prize"><span class="qp-ico">🏅</span><div class="qp-txt">' + act.rewards.map((r, i2) => r ? muneaT('activity.prizeRankItem', '第 {rank} 名 {prize}', { rank: i2 + 1, prize: r }) : '').filter(Boolean).join(muneaListSeparator()) + '<small>' + muneaT('activity.prizeGiver', '獎品提供：{owner}', { owner: act.owner || muneaT('common.you', '你') }) + '</small></div></div>'
      : '';
    if (act._rankHtml) {
      card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><path d="M8 21h8M12 17v4M17 5H7v5a5 5 0 0 0 10 0V5z"/><path d="M17 6h3a1 1 0 0 1 1 1c0 2-1.5 3.5-3.5 3.8M7 6H4a1 1 0 0 0-1 1c0 2 1.5 3.5 3.5 3.8"/></svg>' + muneaT('activity.rankKicker', '機智問答 · 排名出來了') + '<span class="qc-days">' + muneaT('activity.questionsChip', '{count} 題', { count: act.q || 5 }) + '</span></div>' + act._rankHtml + rwLine;
      delete act._rankHtml;
    } else {
      card.innerHTML = '<div class="qc-kicker"><svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>' +
        actKindName(act) +
        '<span class="qc-days">' + chip + '</span></div>' +
        (goal ? '<div class="qc-goal">' + goal + '</div>' : '') +
        (act._stateTag ? '<div class="qc-state ' + act._stateTag.cls + '">' + muneaEscapeHtml(act._stateTag.text) + '</div>' : '') +
        (note ? '<div class="qc-num">' + note + '</div>' : '') + rwLine;
      delete act._stateTag;
    }
    // 點整張卡片＝打開完整活動詳情頁（投票／作答／開獎／管理／刪除都在裡面）
    card.style.cursor = 'pointer';
    card.dataset.actId = act.id;
    card.addEventListener('click', () => openActDetail(act, card));
    empty.parentNode.insertBefore(card, empty.nextSibling);   // 貼著錨點插＝新卡永遠在最上面（跟舊行為一致）
    updateActEmpty();
  }
  function actParts(act) { return ['你'].concat(act.names || []); }
  function actDisplayName(n) { return n === '你' ? muneaT('activity.selfName', '你') : n; }
  // 「不看這個活動」＝只從我的畫面收起來（Edward 2026-08-01）。
  //
  // 為什麼要分兩種：刪除是把活動從雲端拿掉，全家的都會不見、救不回來——那是發起人的權利。
  // 但參加的人也需要能整理自己的畫面（一場跟他無關的聚會一直卡在那裡）。
  // 所以發起人看到「刪除這個活動」、其他人看到「不看這個活動」，各做各的事。
  //
  // 這份清單刻意只存在這台手機、不同步：它是「我的畫面偏好」，不是活動資料。
  // 而且活動最多存在幾天就自動收進記錄簿，換手機重新出現的機會很小，
  // 不值得為它多開一條同步的水管（多一條就多一個會壞的地方）。
  const HIDDEN_ACTS_KEY = 'munea.hiddenActs';
  function loadHiddenActs() {
    try { const a = JSON.parse(localStorage.getItem(HIDDEN_ACTS_KEY) || '[]'); return Array.isArray(a) ? a.map(String) : []; }
    catch (e) { return []; }
  }
  function actHidden(act) {
    if (!act || act.id == null) return false;
    return loadHiddenActs().indexOf(String(act.id)) >= 0;
  }
  function hideAct(id) {
    try {
      const list = loadHiddenActs();
      if (list.indexOf(String(id)) < 0) list.push(String(id));
      localStorage.setItem(HIDDEN_ACTS_KEY, JSON.stringify(list.slice(-60)));
    } catch (e) {}
  }
  // 活動收掉之後，隱藏清單裡那筆就沒意義了——順手清掉，免得這份清單一直長
  function pruneHiddenActs(currentActs) {
    try {
      const alive = new Set((currentActs || []).map(a => String(a && a.id)));
      const kept = loadHiddenActs().filter(id => alive.has(id));
      localStorage.setItem(HIDDEN_ACTS_KEY, JSON.stringify(kept));
    } catch (e) {}
  }
  // 這場活動是不是我發起的（Edward 2026-08-01：開獎是主人的事，不能誰打開誰就按）。
  // 舊活動沒記發起人，這種一律當「是我的」——不然使用者昨天開的抽獎今天突然按不動，
  // 那是把一個沒壞的東西弄壞。新建的活動從現在起都有記。
  function actIsMine(act) {
    if (!act || !act.ownerId) return true;
    try { return String(act.ownerId) === String(muneaCloudPersonId()); } catch (e) { return true; }
  }
  // 圈裡每個人給一個固定顏色（Edward 2026-08-01）
  //
  // 兩個 bug 一次修：
  // ① FAM_AVA 的第一格是「函式」（要呼叫才拿得到字），這裡漏了那一步，於是把函式的原始碼
  //    當成名字印出來——畫面上第一顆頭像顯示「common…」，那是程式內部的東西漏到使用者眼前。
  //    同一份資料在別處（buildRankList、walk-p）都有判斷，只有這裡漏掉。
  // ② FAM_AVA 只認得三個示範名字，其他人一律退回同一個綠——整排頭像長得一模一樣，
  //    分不出誰是誰。改成用名字算出固定顏色：同一個人每次都同色，不同人盡量不同色。
  // 七色輪替。兩個顏色刻意不放進來：
  //   p-me  是「本人」專用，借給家人會讓兩個人看起來是同一個；
  //   p-mei (#3AA8A0) 跟 p-me (#2E8A83) 都是薄荷綠、並排時分不出來（Edward 的截圖裡
  //         「我」和「舅舅」就長得一樣），所以家人只用剩下這七個彼此有對比的顏色。
  const AVA_TINTS = ['p-ama', 'p-zhi', 'p-bao', 'p-lin', 'p-hai', 'p-ye', 'p-mo'];
  function avaTintFor(name) {
    const key = String(name || '');
    let sum = 0;
    for (let i = 0; i < key.length; i += 1) sum = (sum * 31 + key.charCodeAt(i)) % 9973;
    return AVA_TINTS[sum % AVA_TINTS.length];
  }
  function avaPartsFor(name) {
    const known = FAM_AVA[name];
    if (known) return [typeof known[0] === 'function' ? known[0]() : known[0], known[1]];
    return [String(name || '').trim().slice(0, 1) || '·', avaTintFor(name)];
  }
  // 抽獎的開獎時間：舊資料或跨版本同步回來的可能沒有這欄，缺了就退回截止標籤／「稍後」，
  // 不要讓畫面印出 undefined（2026-08-01 逐一掃五種活動詳情頁時抓到）
  // 卡片最上面那一行只寫「這是什麼活動」（Edward 2026-08-01：標題只寫是什麼活動）。
  //
  // 原本寫的是「種類 · 標題」，另外還有一種寫「邀請已送出 · 標題」。兩個毛病：
  //   ① 標題在下面那行大字已經寫了一次（抽獎最明顯：上面「抽獎 · 孫子陪散步一次」、
  //      下面又一個「孫子陪散步一次」），同一句話印兩次
  //   ② 種類＋標題太長，中文折成兩行、英文更慘（「A walk with your grandki」被切掉）
  // 「邀請已送出」也拿掉——它沒告訴人這是什麼活動，而且下面本來就有狀態標籤
  //  （還沒抽／還沒投／你還沒開始走）。
  function actKindName(act) {
    switch (act && act.kind) {
      case 'walk': return muneaT('activity.exercise', '一起運動');
      case 'quiz': return muneaT('activity.quiz', '機智問答');
      case 'vote': return muneaT('activity.vote', '投票');
      case 'draw': return muneaT('activity.draw', '抽獎');
      default: return muneaT('activity.event', '揪一攤');
    }
  }
  function drawWhen(act) {
    return (act && (act.when || act.dueLabel || act.dateLabel)) || muneaT('activity.drawWhenUnknown', '稍後');
  }
  // 卡片右上角那顆小標籤塞不下「日期＋星期＋時間＋截止」——中文英文西班牙文
  // 都會折成兩行（2026-08-01 Edward 指出）。小標籤只留日期和時間，
  // 星期在點進去的詳情頁看得到。
  // 舊卡片可能沒有 dateISO（只存了組好的字串），那就照舊用長的、至少不會空白。
  function chipWhen(act) {
    const iso = String((act && (act.dueISO || act.dateISO)) || '');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) return drawWhen(act);
    const day = new Date(iso + 'T00:00');
    if (Number.isNaN(day.getTime())) return drawWhen(act);
    const short = new Intl.DateTimeFormat(muneaLocale(), { month: 'numeric', day: 'numeric' }).format(day);
    const time = String((act && (act.dueTime || act.time)) || '');
    return time ? short + ' ' + _clock12(time) : short;
  }
  // 獎項與得主（Edward 2026-08-01 加了多獎項）。
  // 這兩個函式同時讀得懂新舊兩種資料：舊的抽獎只有一個 prize 字串、一個 winner 名字，
  // 換版之後那些卡片還在使用者手機裡，不能因為讀不到新欄位就變成空白。
  // 換版前開著的抽獎才有「集中開獎」這件事；新的是各自抽、時間到只是截止
  function actLegacyDraw(act) { return !!(act && act.tickets) && !(act && act.picks); }
  function actPrizes(act) {
    const list = (act && Array.isArray(act.prizes) ? act.prizes : [])
      .map(p => ({
        tier: String((p && p.tier) || '').trim(),
        name: String((p && p.name) || '').trim(),
        count: Math.max(1, +((p && p.count) || 1)),
      }))
      .filter(p => p.name);
    if (list.length) return list;
    const single = String((act && act.prize) || '').trim();
    return single ? [{ tier: '', name: single, count: 1 }] : [];
  }
  function actWinners(act) {
    if (act && Array.isArray(act.winners) && act.winners.length) {
      return act.winners.filter(w => w && w.name).map(w => ({ prize: String(w.prize || ''), name: String(w.name) }));
    }
    if (act && act.winner) return [{ prize: String(act.prize || ''), name: String(act.winner) }];
    return [];
  }
  function prizeSeats(act) {
    return actPrizes(act).reduce((s, p) => s + p.count, 0);
  }
  // 還剩幾個名額沒被抽走（0 ＝ 獎都發完了）
  function prizeSeatsLeft(act) {
    const taken = Object.values((act && act.picks) || {}).filter(Boolean).length;
    return Math.max(0, prizeSeats(act) - taken);
  }
  // 開獎：把抽過票的人洗牌，再照獎項順序一個一個發下去。
  // 兩條規矩：① 一個人只中一個獎（洗完就照順序取，不會重複）
  //          ② 人比獎少就發到沒人為止——不硬湊，也不把沒抽的人拉進來充數。
  function drawWinnersFrom(tickets, prizes) {
    const pool = Object.keys(tickets || {});
    for (let i = pool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = pool[i]; pool[i] = pool[j]; pool[j] = t;
    }
    const out = [];
    let i = 0;
    (prizes || []).forEach(p => {
      for (let k = 0; k < p.count && i < pool.length; k += 1) out.push({ prize: p.name, name: pool[i++] });
    });
    return out;
  }
  // 名字算出來的顏色會撞（七個人可能只分到五色，整排看起來像同一個人）。
  // 同一份名單裡撞到就往後借下一個沒用過的顏色——排在一起的人一定看得出是不同人。
  // 抽成一份對照表，是因為同一份名單會在好幾個地方畫（一排小頭像、運動名次、投票的人），
  // 各畫各的就會出現「頭像那排是綠的、名次那排變紫的」——同一個人在同一頁換了顏色。
  function avaTintMap(names) {
    const used = new Set();
    const map = {};
    (names || []).forEach(n => {
      const [, preferred] = avaPartsFor(n);
      let tint = preferred;
      if (used.has(tint)) {
        const free = AVA_TINTS.find(t => !used.has(t));
        if (free) tint = free;
      }
      used.add(tint);
      map[n] = tint;
    });
    return map;
  }
  function avatarsHtml(names) {
    const tints = avaTintMap(names);
    return (names || []).map(n => {
      const [init] = avaPartsFor(n);
      return '<span class="init-ava ' + (tints[n] || avaTintFor(n)) + '">' + muneaEscapeHtml(init) + '</span>';
    }).join('');
  }
  // 完整活動詳情頁：看完整資訊＋參與者，並在裡面投票／作答／開獎／刪除（Edward 7/7 拍板「做完整詳情頁」）
  function openActDetail(act, card) {
    const sheet = $('#actDetailModal'), body = $('#actDetailBody');
    if (!sheet || !body) return;
    const done = act.status === 'done';
    const chip = done ? muneaT('activity.endedChip', '已結束')
      : act.kind === 'walk' ? muneaT('activity.walkChipActive', '進行中 · {due}', { due: act.dueLabel || muneaT('activity.daysChip', '{days} 天內', { days: act.days }) })
      : act.kind === 'quiz' ? (muneaT('activity.questionsChip', '{count} 題', { count: act.q }) + (act.dueLabel ? ' · ' + act.dueLabel : ''))
      : act.kind === 'draw' ? (actLegacyDraw(act) ? muneaT('activity.drawChip', '{when}開獎', { when: drawWhen(act) }) : muneaT('activity.drawChipDue', '{when}截止', { when: drawWhen(act) }))
      : act.kind === 'event' ? (act.dateLabel || muneaT('activity.inProgress', '進行中'))
      : act.kind === 'vote' ? (act.dueLabel || muneaT('activity.inProgress', '進行中')) : muneaT('activity.inProgress', '進行中');
    const kindName = act.kind === 'walk' ? muneaT('activity.exercise', '一起運動') : act.kind === 'quiz' ? muneaT('activity.quiz', '機智問答') : act.kind === 'vote' ? muneaT('activity.vote', '投票') : act.kind === 'draw' ? muneaT('activity.draw', '抽獎') : muneaT('activity.event', '揪一攤');
    // 抽獎的標題＝獎品名（「一頓火鍋」比「幸運抽獎」好認）。但分了等級之後
    // 拿第一個獎當標題會變成「大獎」——那是獎項不是這場抽獎，改回通用標題。
    const title = act.kind === 'draw'
      ? (actPrizes(act).length > 1 ? (act.title || muneaT('activity.defaultDrawTitle', '家庭抽獎')) : (act.prize || act.title))
      : (act.title || kindName);
    body.innerHTML =
      '<div class="ad-kind">' + kindName + '</div>' +
      '<div class="ad-title">' + title + '</div>' +
      '<div><span class="ad-chip">' + chip + '</span></div>' +
      '<div class="ad-sec"><div class="ad-lbl">' + muneaT('activity.participantsLabel', '一起的人（{count} 人）', { count: actParts(act).length }) + '</div><div class="ad-avs">' + avatarsHtml(actParts(act)) + '</div></div>' +
      '<div class="ad-interact"></div>';
    const box = body.querySelector('.ad-interact');
    if (act.kind === 'vote') { renderVoteBody(act, box); }
    else if (act.kind === 'draw') { renderDrawBody(act, box); }
    else if (act.kind === 'quiz') {
      if (act.myDone && act.answers && act.answers['你'] !== undefined) { box.innerHTML = '<div class="ad-note">' + muneaT('activity.quizWaitDetail', '你答對 {score} / {total} 題，等 {names} 答完看排名。', { score: act.answers['你'], total: act.q, names: (act.names || []).join(muneaListSeparator()) }) + '</div>'; }
      else {
        box.innerHTML = '<div class="ad-note">' + muneaT('activity.quizReadyDetail', '你的 {count} 題準備好了，點下面開始作答；其他人打開 App 也能玩，都答完看排名。', { count: act.q, companion: cname() }) + '</div>';
        const qb = document.createElement('button'); qb.className = 'modal-btn'; qb.style.marginTop = '14px'; qb.textContent = muneaT('activity.quizStart', '開始作答');
        qb.addEventListener('click', () => { sheet.classList.remove('show'); startQuiz(act, card || document.querySelector('[data-act-id="' + act.id + '"]')); });
        box.appendChild(qb);
      }
    }
    else if (act.kind === 'walk') { renderWalkBody(act, box); }
    else if (act.kind === 'event') { renderEventBody(act, box); }
    if (act.rewards && act.rewards.some(Boolean)) {
      box.insertAdjacentHTML('beforeend', '<div class="ad-sec"><div class="ad-lbl">' + muneaT('activity.rewardsLabel', '小獎勵') + '</div><div class="ad-rewards">' + act.rewards.map((r, i) => r ? '<div>' + muneaT('activity.rewardRankItem', '第 {rank} 名 · {prize}', { rank: i + 1, prize: r }) + '</div>' : '').filter(Boolean).join('') + '</div></div>');
    }
    // 刪除是把活動從雲端拿掉、全家的都會不見——那是發起人的事。
    // 參加的人給「不看這個活動」：只收起自己的畫面，別人照樣看得到（Edward 2026-08-01）。
    const mine = actIsMine(act);
    const del = document.createElement('button');
    del.className = mine ? 'ad-del' : 'ad-del ad-hide'; del.type = 'button';
    const idleLabel = () => mine ? muneaT('activity.deleteButton', '刪除這個活動') : muneaT('activity.hideButton', '不看這個活動');
    const armLabel = () => mine ? muneaT('activity.deleteConfirm', '確定刪除？再點一下') : muneaT('activity.hideConfirm', '從我的畫面收起來？再點一下');
    const ICON = mine
      ? '<svg class="ic" viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v5M14 11v5"/></svg>'
      : '<svg class="ic" viewBox="0 0 24 24"><path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.4 5.2A9.5 9.5 0 0 1 12 5c5 0 9 4.5 9 7a11 11 0 0 1-2.4 3.5M6.5 6.9C4 8.4 3 10.7 3 12c0 2.5 4 7 9 7a9.6 9.6 0 0 0 3.4-.6"/></svg>';
    del.innerHTML = ICON + '<span>' + idleLabel() + '</span>';
    del.addEventListener('click', () => {
      if (del.dataset.arm !== '1') { del.dataset.arm = '1'; del.classList.add('arm'); del.querySelector('span').textContent = armLabel(); setTimeout(() => { del.dataset.arm = ''; del.classList.remove('arm'); const s = del.querySelector('span'); if (s) s.textContent = idleLabel(); }, 3200); return; }
      if (mine) {
        const acts = loadActs().filter(a => a.id !== act.id); saveActs(acts);
      } else {
        hideAct(act.id);   // 資料一動都不動，只記「我不看」
      }
      const c = card || document.querySelector('[data-act-id="' + act.id + '"]'); if (c) c.remove();
      updateActEmpty();
      sheet.classList.remove('show');
      toast(mine ? muneaT('activity.deletedToast', '活動刪除了') : muneaT('activity.hiddenToast', '收起來了，家人那邊還在'));
    });
    body.appendChild(del);
    if (typeof window.__muneaApplyUserAvatar === 'function') window.__muneaApplyUserAvatar();   // 有上傳帳號照片的（本人）→ 圓形頭像帶照片
    if (!sheet.dataset.wired) { sheet.dataset.wired = '1'; sheet.addEventListener('click', e => { if (e.target === sheet) sheet.classList.remove('show'); }); }
    sheet.classList.add('show');
  }
  function renderVoteBody(act, card) {
    const my = act.votes && act.votes['你'];
    const total = Object.keys(act.votes || {}).length;
    const wrap = document.createElement('div');
    wrap.className = 'vote-body';
    // 每個選項一個色標（Edward 2026-08-01「有點單調，設計有趣或活潑一點」）。
    // 投完票後右邊放投票人的頭像而不是只有「3 票」——看得到是媽媽跟姊姊選了這個，
    // 才像一家人在決定事情；票數本身留著給人數多時看。
    const VOTE_TINTS = ['v-teal', 'v-coral', 'v-gold', 'v-sage', 'v-plum'];
    const LETTERS = 'ABCDEFGH';
    const counts = act.opts.map(o => Object.values(act.votes || {}).filter(v => v === o).length);
    const topN = Math.max.apply(null, counts.concat([0]));
    // 還開著嗎——截止時間過了就只能看，不能再改
    const voteOpen = (() => {
      try {
        const iso = act.dueISO || act.dateISO;
        if (!iso) return true;
        const end = new Date(iso + 'T' + (act.dueTime || '23:59') + ':00');
        return Number.isNaN(end.getTime()) ? true : Date.now() < end.getTime();
      } catch (e) { return true; }
    })();
    // 跟上面那排小頭像共用同一份配色，同一個人在同一頁不會換顏色
    const voteTints = avaTintMap(actParts(act).concat(Object.keys(act.votes || {})));
    wrap.innerHTML = act.opts.map((o, i) => {
      const n = counts[i];
      const pct = total ? Math.round(n / total * 100) : 0;
      const voters = Object.keys(act.votes || {}).filter(k => act.votes[k] === o);
      const faces = voters.slice(0, 4).map(v => {
        const ini = avaPartsFor(v)[0];
        const tint = voteTints[v] || avaTintFor(v);
        return '<span class="init-ava ' + tint + '" title="' + muneaEscapeHtml(actDisplayName(v)) + '">' + muneaEscapeHtml(ini) + '</span>';
      }).join('') + (voters.length > 4 ? '<span class="vo-more">+' + (voters.length - 4) + '</span>' : '');
      return '<button type="button" class="vote-opt ' + VOTE_TINTS[i % VOTE_TINTS.length] +
        (my === o ? ' mine' : '') + (my ? ' voted' : '') + (my && n > 0 && n === topN ? ' lead' : '') + '" data-o="' + o + '">' +
        '<i style="width:' + (my ? pct : 0) + '%"></i>' +
        '<span class="vo-no">' + LETTERS[i % LETTERS.length] + '</span>' +
        '<span class="vo-txt">' + muneaEscapeHtml(o) + '</span>' +
        (my && voters.length ? '<span class="vo-faces">' + faces + '</span>' : '') +
        (my ? '<span class="vo-n">' + muneaT('activity.voteCount', '{count} 票', { count: n }) + '</span>' : '') +
        (my === o ? '<span class="vo-check">✓</span>' : '') + '</button>';
    }).join('') + '<div class="qc-num">' + (my
      ? (voteOpen
        ? muneaT('activity.voteChangeNote', '想改隨時再點另一個，{when}截止', { when: act.dueLabel || drawWhen(act) })
        : muneaT('activity.voteClosedNote', '投票結束了，這是最後的結果'))
      : (voteOpen
        ? muneaT('activity.votePickNote', '點一個選項投下你的票')
        : muneaT('activity.voteClosedMissed', '投票結束了，這次你沒趕上'))) + '</div>';
    // 截止前可以改主意（Edward 2026-08-01「在截止日前用戶都能夠反悔選別的選項」）。
    // 以前投完就鎖死——家裡討論到一半改變想法是常有的事，鎖住只會逼他找人幫忙改資料。
    if (voteOpen) wrap.addEventListener('click', e => {
      const b = e.target.closest('.vote-opt');
      if (!b) return;
      const picked = b.dataset.o;
      if (my === picked) return;   // 點自己已經投的那個＝沒事發生，不要洗成「又投了一次」
      act.votes = act.votes || {}; act.votes['你'] = picked;
      const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) t.votes = act.votes; saveActs(acts);
      wrap.remove(); renderVoteBody(act, card);
      toast(my
        ? muneaT('activity.voteChangedToast', '改成「{opt}」了', { opt: picked })
        : muneaT('activity.votedToast', '投好了，等其他人的票'));
    });
    card.appendChild(wrap);
  }
  function renderDrawBody(act, card) {
    // 開獎儀式（Edward 7/9）：按「現在開獎」→ 名字輪盤轉快轉慢 → 定格 → 彩帶＋中獎卡（獎品＋找誰領）
    const wrap = document.createElement('div');
    wrap.className = 'draw-body';
    const all = ['你'].concat(act.names || []);
    const AWARD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:26px;height:26px"><circle cx="12" cy="8" r="6"/><path d="M15.5 13 17 22l-5-3-5 3 1.5-9"/></svg>';
    const GIFT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13M5 12v9h14v-9"/><path d="M7.5 8a2.5 2.5 0 1 1 0-5C10 3 12 5.5 12 8c0-2.5 2-5 4.5-5a2.5 2.5 0 1 1 0 5"/></svg>';
    // 抽獎鍵的圖示＝一張票（兩側內凹＋中間撕線）。刻意不用禮物盒——禮物盒留給開獎那一刻，
    // 兩個地方用同一個圖，「抽」跟「開」就分不出來了。
    const TICKET = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" style="width:100%;height:100%"><path d="M4 8.5V7a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v1.5a2.2 2.2 0 0 0 0 4.4V17a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-4.1a2.2 2.2 0 0 0 0-4.4z"/><path d="M13.5 6.6v1.6M13.5 11.2v1.6M13.5 15.8v1.6"/></svg>';
    function winCardHtml(pop) {
      // 「找誰領」要看我是不是出獎的那個人——以前拿 owner 的名字去跟「你」比對，
      // 結果發起人自己看到的是「獎品請找我領」（那就是他本人）。改用身分判斷。
      const iAmGiver = actIsMine(act);
      const giver = muneaSafeDisplayText(act.owner, '');
      const list = actWinners(act);
      const iWon = list.some(w => w.name === '你');
      const claim = iWon
        ? muneaT('activity.claimSelf', '獎品就是你的了，跟家人說一聲')
        : (iAmGiver
          ? muneaT('activity.claimYouGiveAll', '獎品由你提供，記得拿給中獎的家人')
          : (giver
            ? muneaT('activity.claimFromGiver', '獎品請找{giver}領', { giver })
            : muneaT('activity.claimFromHost', '獎品請找發起的人領')));
      // 兩種樣子：只有一個獎照舊放大顯示；有分等級就列成一張榜，自己中的那行標出來
      if (list.length > 1) {
        return '<div class="draw-stage"><div class="draw-confetti"></div><div class="draw-win-card multi' + (pop ? '' : ' nopop') + '">' +
          '<span class="dw-ico">' + AWARD + '</span>' +
          '<div class="dw-title">' + muneaT('activity.winnersTitle', '開獎結果') + '</div>' +
          '<div class="dw-list">' + list.map(w =>
            '<div class="dw-item' + (w.name === '你' ? ' me' : '') + '">' +
            '<span class="dw-prize-name">' + muneaEscapeHtml(w.prize) + '</span>' +
            '<b>' + muneaEscapeHtml(actDisplayName(w.name)) + '</b></div>').join('') + '</div>' +
          '<div class="dw-claim">' + claim + (iWon ? muneaT('activity.winnerFollowupSelf', '；記錄收進家庭記錄簿。') : muneaT('activity.winnerFollowupOther', '；記錄收進家庭記錄簿。')) + '</div>' +
          '</div></div>';
      }
      const only = list[0] || { name: act.winner, prize: act.prize };
      return '<div class="draw-stage"><div class="draw-confetti"></div><div class="draw-win-card' + (pop ? '' : ' nopop') + '">' +
        '<span class="dw-ico">' + AWARD + '</span>' +
        '<div class="dw-name">' + muneaT('activity.winnerLine', '{winner} 抽中了', { winner: actDisplayName(only.name) }) + '</div>' +
        '<div class="dw-prize">「' + muneaEscapeHtml(only.prize || act.prize || '') + '」</div>' +
        '<div class="dw-claim">' + claim + (iWon ? muneaT('activity.winnerFollowupSelf', '；記錄收進家庭記錄簿。') : muneaT('activity.winnerFollowupOther', '；記錄收進家庭記錄簿。')) + '</div>' +
        '</div></div>';
    }
    function throwConfetti() {
      const conf = wrap.querySelector('.draw-confetti');
      if (!conf) return;
      const colors = ['#E0B354', '#F4A261', '#3AA8A0', '#D9EFE8'];   // 暖金/Logo橘/療癒綠/薄荷（自家色盤）
      for (let k = 0; k < 26; k++) {
        const p = document.createElement('i');
        p.style.left = (4 + Math.random() * 92) + '%';
        p.style.background = colors[k % colors.length];
        p.style.animationDelay = (Math.random() * 0.5).toFixed(2) + 's';
        conf.appendChild(p);
      }
    }
    // 抽獎流程（Edward 2026-08-01 兩次修正後定案）
    //
    // 一開始是發起人按一下、系統直接公布得主，其他人全程沒有動作——那不叫抽獎。
    // 中間我改成每人抽一個號碼、時間到再開獎，Edward 指出號碼是多餘的：
    // 「抽獎不用抽號碼吧？而是直接顯示用戶設定的獎項」——他說得對，
    // 使用者設定的是獎項（大獎／二獎／安慰獎），抽到的就該是獎項本身。
    //
    // 現在：點下去當場翻出你抽到什麼，先搶先有；獎發完了就誠實說沒抽到。
    // 「等待」留給最後——等大家都抽完，才知道全家誰中了什麼。
    const picks = act.picks || {};
    const legacyTicketRound = !!act.tickets && !act.picks;   // 換版前就開著的舊抽獎，維持原本的玩法
    const myPick = picks['你'];
    const pickedNames = Object.keys(picks);
    const waiting = all.filter(n => !(n in picks));
    // 每個獎項還剩幾個名額
    function prizeLeft() {
      const taken = {};
      Object.values(picks).forEach(p => { if (p) taken[p] = (taken[p] || 0) + 1; });
      return actPrizes(act).map(p => ({ tier: p.tier, name: p.name, count: p.count, left: Math.max(0, p.count - (taken[p.name] || 0)) }));
    }
    // 抽一個：把還有名額的獎項攤成一個池子隨機挑。全發完就回空字串＝這次沒抽到，
    // 不硬塞一個已經沒名額的獎給他（那等於騙人）。
    function pickPrizeNow() {
      const pool = [];
      prizeLeft().forEach(p => { for (let i = 0; i < p.left; i += 1) pool.push(p.name); });
      if (!pool.length) return '';
      return pool[Math.floor(Math.random() * pool.length)];
    }
    function savePicks() {
      const acts = loadActs(); const t = acts.find(a => a.id === act.id);
      if (t) { t.picks = act.picks; saveActs(acts); }
    }
    const pad = (n) => String(n).padStart(2, '0');
    function saveTickets() {
      const acts = loadActs(); const t = acts.find(a => a.id === act.id);
      if (t) { t.tickets = act.tickets; saveActs(acts); }
    }
    const tickets = act.tickets || {};
    const myTicket = tickets['你'];
    const drawnLine = () => '<div class="qc-num">' + (waiting.length
      ? muneaT('activity.drawWaitingOn', '已經抽了 {n} 個人；還沒抽的：{names}', { n: pickedNames.length, names: waiting.map(actDisplayName).join(muneaListSeparator()) })
      : muneaT('activity.drawEveryoneDone', '{n} 個人都抽完了', { n: pickedNames.length })) + '</div>';
    // 開獎：只從抽過的人裡面開。動畫沿用原本的輪盤，轉的是號碼＋名字。
    function revealWinner() {
      const pool = Object.keys(act.tickets || {});
      if (!pool.length) return;
      const results = drawWinnersFrom(act.tickets, actPrizes(act));
      if (!results.length) return;
      const winner = results[0].name;   // 輪盤定格在第一個獎的得主，接著才攤開整張榜
      act.winners = results;
      act.winner = winner;              // 舊欄位留著：通知與記錄簿還在讀
      const acts = loadActs(); const t = acts.find(a => a.id === act.id); if (t) { t.winner = winner; t.winners = results; t.tickets = act.tickets; } saveActs(acts);
      wrap.innerHTML = '<div class="draw-stage"><div class="ds-gift">' + GIFT + '</div><div class="draw-roll"><span class="dr-name">…</span><small>' + muneaT('activity.drawRolling', '看看是誰…') + '</small></div></div>';
      const nameEl = wrap.querySelector('.dr-name');
      let i = 0, delay = 70;
      const spin = () => {
        const n = pool[i % pool.length];
        nameEl.textContent = pad(act.tickets[n]) + ' ' + actDisplayName(n); i++;
        if (delay < 330) { delay *= 1.14; setTimeout(spin, delay); }
        else {
          nameEl.textContent = pad(act.tickets[winner]) + ' ' + actDisplayName(winner);
          setTimeout(() => {
            wrap.innerHTML = winCardHtml(true);
            throwConfetti();
            pushFamilyFeed(results.length > 1
              ? muneaT('feed.drawWinnersMulti', '開獎了——{list}！', {
                list: results.map(w => muneaEscapeHtml(w.prize) + ' <b>' + muneaEscapeHtml(w.name) + '</b>').join(muneaListSeparator()),
              })
              : muneaT('feed.drawWinner', '「{prize}」開獎了——{name} 抽中（{no} 號）！', { prize: results[0].prize || act.prize, name: '<b>' + muneaEscapeHtml(winner) + '</b>', no: pad(act.tickets[winner]) }));
          }, 620);
        }
      };
      spin();
    }
    // 獎項板一律顯示（Edward 2026-08-01「抽獎畫面應該要顯示獎項」）。
    // 就算只有一個獎也畫——使用者要先看得到自己在抽什麼，才知道值不值得按下去。
    // 抽到一半的時候順便標「還剩幾個」，先搶先有這件事要看得見。
    const prizeRows = prizeLeft();
    const anyPicked = pickedNames.length > 0;
    const prizeBoard = prizeRows.length
      ? '<div class="prize-board">' + prizeRows.map(p =>
        '<div class="pb-row' + (p.left ? '' : ' gone') + '">' +
        (p.tier ? '<span class="pb-tier">' + muneaEscapeHtml(p.tier) + '</span>' : '') +
        '<span class="pb-name">' + muneaEscapeHtml(p.name) + '</span>' +
        '<span class="pb-count">' + (anyPicked && !legacyTicketRound
          ? (p.left
            ? muneaT('activity.prizeLeftCount', '還剩 {n} 個', { n: p.left })
            : muneaT('activity.prizeGone', '已經抽走'))
          : muneaT('activity.prizeCountOption', '{n} 位', { n: p.count })) + '</span></div>').join('') +
      '</div>'
      : '';
    // 抽到的獎項對應的等級（顯示「大獎 · 一頓火鍋」用）
    function tierOf(prizeName) {
      const hit = actPrizes(act).find(p => p.name === prizeName);
      return (hit && hit.tier) || '';
    }
    // 誰抽到什麼（Edward 2026-08-01「owner 或家人點開能看到誰抽到什麼嗎？」）
    // 本來只有自己抽完才看得到——但這是一家人一起玩的東西，還沒抽的人、
    // 發起人想看進度，都該看得到。所以只要有人抽過就列出來。
    function pickListHtml() {
      const others = pickedNames.filter(n => n !== '你');
      if (!others.length) return '';
      return '<div class="pick-list">' + others.map(n =>
        '<div class="pk-row"><span class="pk-name">' + muneaEscapeHtml(actDisplayName(n)) + '</span>' +
        '<span class="pk-got' + (picks[n] ? '' : ' miss') + '">' + (picks[n] ? muneaEscapeHtml(picks[n]) : muneaT('activity.drawMissShort', '沒抽到')) + '</span></div>').join('') +
        '</div>';
    }
    // 中了什麼獎的下面接一句「找誰領」（Edward 2026-08-01）
    function claimLine() {
      if (actIsMine(act)) return muneaT('activity.claimYouGiveSelf', '獎品是你自己出的，記得留著');
      const giver = muneaSafeDisplayText(act.owner, '');
      return giver
        ? muneaT('activity.claimFromGiver', '獎品請找{giver}領', { giver })
        : muneaT('activity.claimFromHost', '獎品請找發起的人領');
    }
    if (act.winner) {
      wrap.innerHTML = winCardHtml(false);
    } else if (legacyTicketRound) {
      // 換版前就開著的抽獎：那些人已經拿了號碼，維持原本「等發起人開獎」的玩法，
      // 不要讓他們的卡片一夜之間變成另一個遊戲。
      wrap.innerHTML = prizeBoard + (myTicket === undefined
        ? '<div class="qc-num">' + muneaT('activity.drawLegacyWait', '這場抽獎用的是舊的玩法，{when}由發起的人開獎', { when: drawWhen(act) }) + '</div>'
        : '<div class="draw-mine"><span class="dm-no">' + pad(myTicket) + '</span><div class="dm-txt"><b>' +
          muneaT('activity.drawMyTicket', '你抽到 {no} 號', { no: pad(myTicket) }) + '</b><small>' +
          muneaT('activity.drawMyTicketSub', '{when}開獎，中了會告訴你', { when: drawWhen(act) }) + '</small></div></div>') +
        (actIsMine(act)
          ? '<button type="button" class="draw-now">' + muneaT('activity.drawNowButton', '現在開獎') + '</button>'
          : '<div class="draw-wait">' + (muneaSafeDisplayText(act.owner, '')
            ? muneaT('activity.drawWaitOwner', '等{owner}開獎', { owner: muneaSafeDisplayText(act.owner, '') })
            : muneaT('activity.drawWaitHost', '等發起的人開獎')) + '</div>');
      const now = wrap.querySelector('.draw-now');
      if (now) now.addEventListener('click', () => revealWinner());
    } else if (myPick === undefined && !prizeSeatsLeft(act)) {
      // 獎已經被抽光了：先講清楚，不要讓他滿懷期待按下去才落空
      wrap.innerHTML = prizeBoard +
        '<div class="draw-got miss"><div class="dg-txt"><b>' + muneaT('activity.drawSoldOutTitle', '獎都被抽完了') + '</b>' +
        '<small>' + muneaT('activity.drawSoldOutSub', '這場來晚了一步，下次早點來') + '</small></div></div>' +
        drawnLine() + pickListHtml();
    } else if (myPick === undefined) {
      // 還沒抽：這是每個人自己的動作，不分發起人或參加者
      wrap.innerHTML = prizeBoard + '<div class="qc-num">' + muneaT('activity.drawPickHint2', '點一下就知道自己抽到什麼，{when}截止', { when: drawWhen(act) }) + '</div>' +
        '<button type="button" class="draw-pick"><span class="dp-card">' + TICKET + '</span><span>' + muneaT('activity.drawPickButton', '抽獎') + '</span></button>' +
        (pickedNames.length ? drawnLine() + pickListHtml() : '');
      wrap.querySelector('.draw-pick').addEventListener('click', () => {
        const got = pickPrizeNow();
        act.picks = Object.assign({}, act.picks || {}, { 你: got });
        savePicks();
        // 翻牌：獎項名快速跳動後定格在自己抽到的那個
        const names = actPrizes(act).map(p => p.name);
        // 這一層要自己帶彩帶的容器——throwConfetti() 是往 .draw-confetti 裡塞紙片的，
        // 少了它抽中就完全沒有彩帶（改成當場開獎之後漏掉的，2026-08-01 抓到）
        wrap.innerHTML = '<div class="draw-stage"><div class="draw-confetti"></div><div class="ds-gift">' + GIFT + '</div><div class="draw-roll"><span class="dr-name dr-prize">…</span><small>' + muneaT('activity.drawPicking2', '看看抽到什麼…') + '</small></div></div>';
        const el = wrap.querySelector('.dr-prize');
        let i = 0, delay = 65;
        const flip = () => {
          el.textContent = names[i % names.length] || ''; i += 1;
          if (delay < 310) { delay *= 1.15; setTimeout(flip, delay); }
          else {
            el.textContent = got || muneaT('activity.drawMissShort', '沒抽到');
            el.classList.add('locked');   // 定格「咚」一下，讓結果落地有重量
            // 下面那句還停在「看看抽到什麼…」——都抽到了還在問，要一起換掉
            const capEl = wrap.querySelector('.draw-roll small');
            if (capEl) capEl.textContent = got
              ? muneaT('activity.drawLockedGot', '恭喜！是你的了')
              : muneaT('activity.drawLockedMiss', '這次沒中，下次再來');
            if (got) {
              throwConfetti();
              // 抽中的那一刻要停得住（Edward 2026-08-01「太快切換了，至少停 4.6 秒」）：
              // 中了獎的人想看清楚自己抽到什麼，畫面一秒就跳走等於沒讓他享受到。
              // 中段再灑一次彩帶，這 4.6 秒才不是靜止的。
              setTimeout(() => { try { throwConfetti(); } catch (e) {} }, 1700);
              setTimeout(() => { renderDrawBody(act, card); wrap.remove(); }, 4600);
            } else {
              // 沒抽到就不要讓他盯著看——短一點過去比較體貼
              setTimeout(() => { renderDrawBody(act, card); wrap.remove(); }, 1900);
            }
          }
        };
        flip();
      });
    } else {
      // 抽完了：直接看到自己抽到什麼；中了就接一句找誰領
      wrap.innerHTML = prizeBoard +
        (myPick
          ? '<div class="draw-got"><span class="dg-ico">' + AWARD + '</span><div class="dg-txt">' +
            (tierOf(myPick) ? '<span class="dg-tier">' + muneaEscapeHtml(tierOf(myPick)) + '</span>' : '') + '<b>' +
            muneaT('activity.drawIGot', '你抽到「{prize}」', { prize: muneaEscapeHtml(myPick) }) + '</b><small>' + claimLine() + '</small></div></div>'
          : '<div class="draw-got miss"><div class="dg-txt"><b>' + muneaT('activity.drawIMissed', '這次沒抽到') + '</b><small>' +
            muneaT('activity.drawIMissedSub', '獎項被抽完了，下次再一起玩') + '</small></div></div>') +
        drawnLine() +
        pickListHtml();
    }
    card.appendChild(wrap);
  }
  if ($('#startChalBtn')) $('#startChalBtn').addEventListener('click', () => {
    const type = document.querySelector('.chal-type.active');
    const kind = type ? (type.dataset.kind || 'walk') : 'walk';
    const ons = $$('#inviteList .iv.on');
    const names = ons.map(x => x.dataset.name).filter(Boolean);
    if (!names.length) { toast(loadCircle().some(m => !m.self) ? muneaT('activity.pickFamilyFirst', '先選至少一位家人一起') : muneaT('activity.noFamilyYet', '圈裡還沒有家人，先到家人頁邀請家人加入')); return; }
    // 記下發起人（Edward 2026-08-01「開獎應該是發起人的事」）。
    //   ownerId 才是判斷依據——名字會改、也可能兩個家人同名；顯示才用 owner。
    const act = { id: Date.now(), kind, names, owner: myFeedName(), ownerId: muneaCloudPersonId() };
    if (kind === 'walk') {
      act.goal = +(($('#walkGoal') && $('#walkGoal').value) || 30000);
      act.title = muneaT('activity.exercise', '一起運動');
      // 挑戰截止（跟其他活動同款日期＋時間）：今天開始、到期自動結算 — Edward 7/9
      const wd0 = ($('#walkDue') && $('#walkDue').value) ? new Date($('#walkDue').value + 'T00:00') : null;
      if (!wd0 || isNaN(wd0)) { toast(muneaT('activity.pickChallengeDeadline', "先選挑戰截止的日期")); return; }
      const wt = ($('#walkDueTime') && $('#walkDueTime').value) || '20:00';
      const start = new Date();
      act.startISO = isoOf(start);
      // 發起當下，每個人「今天已經走了多少」——之後只算超出這條線的部分
      // （Edward 2026-08-01：「發起時才正式開始記錄，而不是已經累積今天的步數直接灌進來」）。
      // 早上十點發起，那八千步是活動開始前走的，不該算進大家一起完成的目標裡。
      act.baseline = {};
      names.concat(['你']).forEach(n => {
        let s = 0;
        try {
          if (n === '你') { const h = JSON.parse(localStorage.getItem('munea.health.last') || 'null'); if (h && h.s && typeof h.s.steps === 'number') s = h.s.steps; }
          else { const v = famVitalsFor(n); if (v && v.steps) s = +v.steps; }
        } catch (e) {}
        act.baseline[n] = Math.max(0, s || 0);
      });
      const day0 = new Date(start.getFullYear(), start.getMonth(), start.getDate());
      act.days = Math.max(1, Math.round((wd0 - day0) / 86400000));
      act.dateISO = isoOf(wd0);
      act.dueTime = wt;
      act.dueLabel = muneaT('activity.dueAt', '{when} 截止', { when: fmtDay(wd0) + ' ' + _clock12(wt) });
    } else if (kind === 'quiz') {
      act.q = +(($('#quizN') && $('#quizN').value) || 10);
      act.title = muneaT('activity.quiz', '機智問答');
      const qd = ($('#quizDue') && $('#quizDue').value) ? new Date($('#quizDue').value + 'T00:00') : null;
      const qt = ($('#quizDueTime') && $('#quizDueTime').value) || '20:00';
      if (qd && !isNaN(qd)) { act.dueISO = isoOf(qd); act.dueTime = qt; act.dueLabel = muneaT('activity.dueAt', '{when} 截止', { when: fmtDay(qd) + ' ' + _clock12(qt) }); }
    } else if (kind === 'vote') {
      act.title = (($('#voteQ') && $('#voteQ').value.trim()) || muneaT('activity.defaultVoteTitle', '家庭投票'));
      act.opts = ['#vo1', '#vo2', '#vo3'].map(x => ($(x) && $(x).value.trim()) || '').filter(Boolean);
      if (act.opts.length < 2) { toast(muneaT('activity.voteNeedsTwoOptions', "投票至少要兩個選項")); return; }
      // 投票要有截止（到期自動公布結果、收進記錄簿）— Edward 7/9
      const vd0 = ($('#voteDue') && $('#voteDue').value) ? new Date($('#voteDue').value + 'T00:00') : null;
      if (!vd0 || isNaN(vd0)) { toast(muneaT('activity.pickVoteDeadline', "先選投票截止的日期")); return; }
      const vt = ($('#voteDueTime') && $('#voteDueTime').value) || '20:00';
      act.dueISO = isoOf(vd0); act.dueTime = vt; act.dateISO = act.dueISO;
      act.dueLabel = muneaT('activity.dueAt', '{when} 截止', { when: fmtDay(vd0) + ' ' + _clock12(vt) });
      act.votes = {};
      ['#voteQ', '#vo1', '#vo2', '#vo3'].forEach(x => { if ($(x)) $(x).value = ''; });
    } else if (kind === 'draw') {
      const prizeRows = readPrizeRows();
      if (!prizeRows.length) { toast(muneaT('activity.fillPrizeFirst', "先填獎品，抽起來才有趣")); return; }
      // 名額比人多＝一定發不完。先擋一次講清楚，不然他等到截止才發現獎沒送出去。
      const seats = prizeRows.reduce((s, p) => s + p.count, 0);
      const joiners = names.length + 1;
      if (seats > joiners && $('#startChalBtn').dataset.seatWarn !== '1') {
        $('#startChalBtn').dataset.seatWarn = '1';
        setTimeout(() => { if ($('#startChalBtn')) $('#startChalBtn').dataset.seatWarn = ''; }, 6000);
        toast(muneaT('activity.prizeMoreThanPeople', '獎有 {seats} 個、人只有 {people} 位，會發不完。要這樣就再按一次送出', { seats, people: joiners }));
        return;
      }
      act.prizes = prizeRows;
      act.prize = prizeRows[0].name;   // 舊欄位留著：通知、記錄簿、家人動態都還在讀它
      const dd0 = ($('#drawDate') && $('#drawDate').value) ? new Date($('#drawDate').value + 'T00:00') : new Date();
      const dd = isNaN(dd0) ? new Date() : dd0;
      const dtv = ($('#drawTime') && $('#drawTime').value) || '20:00';
      // 截止時間不能設到過去——設了就是建好立刻過期，卡片隔天早上直接消失
      const dueAt = new Date(isoOf(dd) + 'T' + dtv + ':00');
      if (!Number.isNaN(dueAt.getTime()) && dueAt.getTime() < Date.now()) {
        toast(muneaT('activity.drawDueInPast', '截止時間已經過了，改一個晚一點的'));
        return;
      }
      act.dateISO = isoOf(dd);
      act.dueTime = dtv;   // 小標籤要印時間，靠這格
      act.when = fmtDay(dd) + ' ' + _clock12(dtv);
      act.title = muneaT('activity.luckyDrawTitle', '幸運抽獎');
      resetPrizeRows();
    } else {
      const ed0 = ($('#evDate') && $('#evDate').value) ? new Date($('#evDate').value + 'T00:00') : null;
      if (!ed0 || isNaN(ed0)) { toast(muneaT('activity.pickEventDate', "先選聚會的日期")); return; }
      const etv = ($('#evTime') && $('#evTime').value) || '18:00';
      act.dateISO = isoOf(ed0);
      act.time = etv;   // 原始時間：給「活動前 30 分提醒」＋「時間過了鎖 RSVP」用
      act.dateLabel = fmtDay(ed0) + ' ' + _clock12(etv);
      act.title = (($('#eventName') && $('#eventName').value.trim()) || muneaT('notification.familyDefaultTitle', '家庭聚會'));
      act.place = (($('#eventPlace') && $('#eventPlace').value.trim()) || '');
    }
    const rw = ['#rw1', '#rw2', '#rw3'].map(x => ($(x) && $(x).value.trim()) || '');
    if (rw.some(Boolean)) act.rewards = rw;
    ['#rw1', '#rw2', '#rw3'].forEach(x => { if ($(x)) $(x).value = ''; });
    const acts = loadActs(); acts.push(act); saveActs(acts);
    trackProductEvent('activity_created', { kind: kind });
    closeChal();
    renderActCard(act);
    hint(kind === 'event' ? muneaT('activity.launchedEventHint', '好，發出去了，誰能到、誰沒空，回覆齊了告訴你。', { companion: cname() }) : kind === 'vote' ? muneaT('activity.launchedVoteHint', '好，問題送出去了，誰投了什麼馬上看得到。', { companion: cname() }) : kind === 'draw' ? muneaT('activity.launchedDrawHint', '好，抽獎發出去了，{when}開獎！', { companion: cname(), when: act.when || '' }) : muneaT('activity.launchedInviteHint', '好，邀請發出去了，等大家答應就開始。', { companion: cname() }));
  });
  // 一張活動卡是不是「到期該收」（含自己發起的、含問答/投票、含沒設日期的殭屍卡）— Edward 7/9 修卡死
  // 這個活動「哪天算結束」（揪一攤=活動日、問答/投票=截止、運動=截止、抽獎=開獎日）
  function actEndISO(a) {
    if (a.kind === 'quiz' || a.kind === 'vote') return a.dueISO || a.dateISO;
    return a.dateISO || a.dueISO;
  }
  // 到期規則（Edward 7/9）：揪一攤=活動當天過後、隔天 0:00 收；問答/運動=結束後多留一天看成績；殭屍卡放 3 天一律清
  function actExpired(a) {
    if (!a) return false;
    const today = isoOf(new Date());
    const created = a.id ? isoOf(new Date(a.id)) : today;
    const endBase = (a.status === 'done' ? a.doneISO : actEndISO(a)) || created;
    const grace = (a.kind === 'quiz' || a.kind === 'walk') ? 1 : 0;   // 問答/運動：結束後多留一天
    const g = new Date(endBase + 'T00:00'); g.setDate(g.getDate() + grace);
    const removeAfter = isoOf(g);   // 這天(含)之前留著、隔天 0:00 收
    const d3 = new Date(); d3.setDate(d3.getDate() - 3);
    if (removeAfter < today) return true;
    if (created < isoOf(d3)) return true;   // 保險：殭屍卡放超過 3 天一律清
    return false;
  }
  // 開 App 時整理牆面：到期的收進記錄簿、其餘重畫
  function restoreActsBoot() {
    const acts = loadActs();
    const keep = [];
    acts.forEach(a => {
      if (actExpired(a)) {
        announceActEnd(a);
      } else { keep.push(a); renderActCard(a); }
    });
    if (keep.length !== acts.length) saveActs(keep);
    pruneHiddenActs(keep);   // 收掉的活動不必再記「我不看」
    updateActEmpty();
  }
  // 進家人頁時再掃一次：不用重開 App，到期卡當場收掉＋公布結果
  function sweepActsOnView() {
    const acts = loadActs();
    const expired = acts.filter(a => actExpired(a));
    if (!expired.length) return;
    expired.forEach(a => { announceActEnd(a); const c = document.querySelector('[data-act-id="' + a.id + '"]'); if (c) c.remove(); });
    saveActs(acts.filter(a => !actExpired(a)));
    updateActEmpty();
  }
  window.__muneaSweepActs = sweepActsOnView;
  Promise.resolve(__pullPromise).finally(() => restoreActsBoot());   // syncPullAll 可能不回 Promise（頁面隱藏啟動等）；不包住整個 init 會從這裡斷頭（7/15 修）
  if (chalModal) chalModal.addEventListener('click', e => { if (e.target === chalModal) closeChal(); });
  // 邀請勾選 → 依人數+能力動態算目標
  const inviteList = $('#inviteList');
  function paintRange(el) {
    if (!el) return;
    const p = (el.value - el.min) / (el.max - el.min) * 100;
    el.style.setProperty('--fill', p.toFixed(1) + '%');
  }
  function updateWalkLabels() {
    paintRange($('#walkGoal')); paintRange($('#walkDays')); paintRange($('#quizN'));
    const g = +($('#walkGoal') ? $('#walkGoal').value : 30000);
    if ($('#walkGoalVal')) $('#walkGoalVal').textContent = muneaT(
      'legacyUi.activityGoalValue',
      '{steps} steps',
      { steps: new Intl.NumberFormat(muneaLocale()).format(g) },
    );
    const n = $$('#inviteList .iv.on').length || 1;
    const d = +($('#walkDays') ? $('#walkDays').value : 7);
    if ($('#walkDaysVal')) $('#walkDaysVal').textContent = muneaT(
      'legacyUi.activityDaysValue',
      '{days} days',
      { days: new Intl.NumberFormat(muneaLocale()).format(d) },
    );
    const per = Math.max(100, Math.round(g / (n * d) / 100) * 100);
    if ($('#goalHint')) $('#goalHint').textContent = muneaT(
      'legacyUi.activityGoalHint',
      '{people} people over {days} days · About {steps} steps per person each day',
      {
        people: new Intl.NumberFormat(muneaLocale()).format(n),
        days: new Intl.NumberFormat(muneaLocale()).format(d),
        steps: new Intl.NumberFormat(muneaLocale()).format(per),
      },
    );
  }
  window.__muneaUpdateWalkLabels = updateWalkLabels;
  function recalcWalk(reset) {
    const slider = $('#walkGoal');
    if (!slider) return;
    const n = $$('#inviteList .iv.on').length || 1;
    const d = +($('#walkDays') ? $('#walkDays').value : 7);
    const suggest = Math.round(n * d * 4000 / 1000) * 1000;
    slider.min = Math.max(2000, Math.round(n * d * 1500 / 1000) * 1000);
    slider.max = Math.max(suggest * 2, n * d * 8000);
    slider.step = 1000;
    if (reset || +slider.value < +slider.min || +slider.value > +slider.max) slider.value = suggest;
    updateWalkLabels();
  }
  if (inviteList) inviteList.addEventListener('click', e => { const it = e.target.closest('.iv'); if (it) { it.classList.toggle('on'); recalcWalk(true); } });
  // 挑戰類型選擇
  function applyChalKind(kind) {
    if ($('#walkFields')) $('#walkFields').style.display = kind === 'walk' ? '' : 'none';
    if ($('#quizFields')) $('#quizFields').style.display = kind === 'quiz' ? '' : 'none';
    if ($('#eventFields')) $('#eventFields').style.display = kind === 'event' ? '' : 'none';
    if ($('#voteFields')) $('#voteFields').style.display = kind === 'vote' ? '' : 'none';
    if ($('#drawFields')) $('#drawFields').style.display = kind === 'draw' ? '' : 'none';
    if ($('#rewardFields')) $('#rewardFields').style.display = (kind === 'walk' || kind === 'quiz') ? '' : 'none';
  }
  // 抽獎的獎項清單（Edward 2026-08-01「大獎、二獎、安慰獎，可以設數量」）
  // 預設只有一行、跟以前一樣簡單；點「再加一個獎項」才長出第二行，最多四個
  //（大獎／二獎／三獎／安慰獎剛好），再多對長輩就難填了。
  const PRIZE_MAX_ROWS = 4;
  const PRIZE_MAX_COUNT = 5;
  function fillPrizeCount(sel, value) {
    if (!sel || sel.dataset.filled === '1') return;
    sel.innerHTML = '';
    for (let n = 1; n <= PRIZE_MAX_COUNT; n += 1) {
      const o = document.createElement('option');
      o.value = String(n);
      o.textContent = muneaT('activity.prizeCountOption', '{n} 位', { n });
      sel.appendChild(o);
    }
    sel.value = String(value || 1);
    sel.dataset.filled = '1';
  }
  // 等級是系統給的、跟著行數走（Edward 2026-08-01：「大獎那些是預設，用戶應該填的是獎項內容」）。
  // 只有一行時不標等級——只有一個獎，沒有「大」可以對比。
  function prizeTierFor(i, total) {
    if (total <= 1) return '';
    return [
      muneaT('activity.tier1', '大獎'),
      muneaT('activity.tier2', '二獎'),
      muneaT('activity.tier3', '三獎'),
      muneaT('activity.tier4', '安慰獎'),
    ][i] || muneaT('activity.tierN', '第 {n} 獎', { n: i + 1 });
  }
  function refreshPrizeRows() {
    const list = $('#drawPrizeList');
    const add = $('#drawPrizeAdd');
    if (!list) return;
    const rows = [].slice.call(list.querySelectorAll('.prize-row'));
    rows.forEach((row, i) => {
      fillPrizeCount(row.querySelector('.pz-count'), 1);
      const tier = row.querySelector('.pz-tier');
      if (tier) { tier.textContent = prizeTierFor(i, rows.length); tier.style.display = rows.length > 1 ? '' : 'none'; }
      const name = row.querySelector('.pz-name');
      if (name && i > 0) name.placeholder = muneaT('activity.prizeMorePlaceholder', '例：一杯手搖、洗碗一次');
      let del = row.querySelector('.pz-del');
      if (i === 0) { if (del) del.remove(); return; }   // 第一行是必填的主獎，不給移除
      if (!del) {
        del = document.createElement('button');
        del.type = 'button'; del.className = 'pz-del';
        del.setAttribute('aria-label', muneaT('activity.prizeRemoveAria', '移除這個獎項'));
        del.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        del.addEventListener('click', () => { row.remove(); refreshPrizeRows(); });
        row.appendChild(del);
      }
    });
    if (add) add.style.display = rows.length >= PRIZE_MAX_ROWS ? 'none' : '';
  }
  function addPrizeRow() {
    const list = $('#drawPrizeList');
    if (!list || list.querySelectorAll('.prize-row').length >= PRIZE_MAX_ROWS) return;
    const row = document.createElement('div');
    row.className = 'prize-row';
    row.innerHTML = '<span class="pz-tier"></span><input class="chal-input pz-name" maxlength="14" /><select class="pz-count" aria-label="' +
      muneaEscapeHtml(muneaT('activity.prizeCountAria', '幾位')) + '"></select>';
    list.appendChild(row);
    refreshPrizeRows();
    const el = row.querySelector('.pz-name'); if (el) el.focus();
  }
  function readPrizeRows() {
    const list = $('#drawPrizeList');
    if (!list) return [];
    const rows = [].slice.call(list.querySelectorAll('.prize-row'));
    const filled = rows.map(row => ({
      name: ((row.querySelector('.pz-name') || {}).value || '').trim(),
      count: Math.max(1, Math.min(PRIZE_MAX_COUNT, +((row.querySelector('.pz-count') || {}).value || 1))),
    })).filter(p => p.name);
    // 等級照最後真的填了幾個重算：中間留空的那行不算，等級才不會跳號
    return filled.map((p, i) => Object.assign({ tier: prizeTierFor(i, filled.length) }, p));
  }
  function resetPrizeRows() {
    const list = $('#drawPrizeList');
    if (!list) return;
    [].slice.call(list.querySelectorAll('.prize-row')).forEach((row, i) => {
      if (i > 0) { row.remove(); return; }
      const name = row.querySelector('.pz-name'); if (name) name.value = '';
      const cnt = row.querySelector('.pz-count'); if (cnt) cnt.value = '1';
    });
    refreshPrizeRows();
  }
  if ($('#drawPrizeAdd')) $('#drawPrizeAdd').addEventListener('click', addPrizeRow);
  refreshPrizeRows();
  document.addEventListener('munea:locale-ready', () => {
    // 換語言時「1 位／2 位」要跟著換，下拉是程式生的、翻譯層掃不到
    const list = $('#drawPrizeList');
    if (!list) return;
    [].slice.call(list.querySelectorAll('.pz-count')).forEach(sel => {
      const keep = sel.value; sel.dataset.filled = ''; fillPrizeCount(sel, keep);
    });
    refreshPrizeRows();
  });
  $$('.chal-type').forEach(b => b.addEventListener('click', () => {
    $$('.chal-type').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    applyChalKind(b.dataset.kind || 'walk');
  }));
  applyChalKind('walk');
  recalcWalk(true);
  // 拉桿連動
  if ($('#walkGoal')) $('#walkGoal').addEventListener('input', () => updateWalkLabels());
  if ($('#walkDays')) $('#walkDays').addEventListener('input', () => recalcWalk(true));
  // 挑戰截止一改 → 換算天數（給目標步數建議用）
  function syncWalkDays() {
    const el = $('#walkDue');
    if (!el || !el.value) return;
    const due = new Date(el.value + 'T00:00');
    if (isNaN(due)) return;
    const t = new Date();
    const day0 = new Date(t.getFullYear(), t.getMonth(), t.getDate());
    const d = Math.min(30, Math.max(1, Math.round((due - day0) / 86400000)));
    if ($('#walkDays')) $('#walkDays').value = d;
    recalcWalk(true);
  }
  if ($('#walkDue')) $('#walkDue').addEventListener('change', syncWalkDays);
  if ($('#quizN')) $('#quizN').addEventListener('input', () => {
    paintRange($('#quizN'));
    if ($('#quizNVal')) $('#quizNVal').textContent = muneaT('activity.questionsChip', '{count} 題', { count: $('#quizN').value });
  });
  // 狀態頁三檔切換（今天/本週/本月）
  const statusSeg = $('#statusSeg');
  if (statusSeg) {
    const sviews = { today: $('#statusToday'), week: $('#statusWeek'), month: $('#statusMonth') };
    const stitles = { today: muneaT('status.todayTitle', '今天的狀態'), week: muneaT('status.weekTitle', '這週的狀態'), month: muneaT('status.monthTitle', '這個月的狀態') };
    statusSeg.addEventListener('click', e => {
      const b = e.target.closest('.seg-btn');
      if (!b) return;
      statusSeg.querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('on', x === b));
      Object.entries(sviews).forEach(([k, el]) => { if (el) el.style.display = k === b.dataset.v ? '' : 'none'; });
      if ($('#statusTitle')) $('#statusTitle').textContent = stitles[b.dataset.v];
    });
  }
  // 看診可記多筆、每筆有標題（看什麼診）＋日期＋時間
  function loadVisits() {
    let arr = null; try { arr = JSON.parse(localStorage.getItem('munea.visits') || 'null'); } catch (e) {}
    if (!Array.isArray(arr)) {
      let old = null; try { old = JSON.parse(localStorage.getItem('munea.visit') || 'null'); } catch (e2) {}
      arr = (old && (old.dateISO || old.label)) ? [{ id: 1, title: old.title || '回診', dateISO: old.dateISO || '', time: old.time || '', label: old.label || '' }] : [];
    }
    return arr.filter(v => v && v.dateISO).sort((a, b) => (a.dateISO + (a.time || '')).localeCompare(b.dateISO + (b.time || '')));
  }
  function saveVisits(arr) { try { localStorage.setItem('munea.visits', JSON.stringify(arr)); } catch (e) {} syncPush('visits', arr); if (window.MuneaNotify) window.MuneaNotify.sync(); }
  function nextVisit() { const today = isoOf(new Date()); const arr = loadVisits(); return arr.filter(v => v.dateISO >= today)[0] || arr[0] || null; }
  function fmtVisitTime(tv) {  // "14:30" → "下午 2:30"
    const p = String(tv || '09:00').split(':'); const hh = +p[0] || 9, mm = +p[1] || 0;
    const ap = hh < 12 ? muneaT('common.am', '上午') : muneaT('common.pm', '下午'); const h12 = ((hh + 11) % 12) + 1;
    return ap + ' ' + h12 + ':' + String(mm).padStart(2, '0');
  }
  function renderVisitRow() {
    const v = nextVisit();
    const lb = $('#visitLabel');
    if (lb) lb.textContent = v ? _visitDayShort(v) : '';
    // 看診有增減時，同步首頁「今天一起完成」的回診任務（只在當天顯示）
    if (window.__muneaRenderDailyTasks) window.__muneaRenderDailyTasks();
  }
  window.__muneaRefreshVisitRow = renderVisitRow;
  function renderVisitList() {
    const box = $('#visitList'); if (!box) return;
    const arr = loadVisits();
    // 每一筆都能直接看那次的摘要（Edward 2026-07-29：跟就診提醒連動）
    box.innerHTML = arr.length ? ('<div class="field-label">' + muneaT('appointment.scheduled', '已排的就診') + '</div>' + arr.map(v =>
      '<div class="visit-item"><div class="vi-info"><b>' + muneaSafeDisplayText(v.title, muneaT('visit.defaultTitle', '回診')) + '</b><span>' + (v.label || '') + '</span></div>'
      + '<button type="button" class="vi-sum" data-id="' + v.id + '">' + muneaT('visit.openSummary', '看摘要') + '</button>'
      + '<button type="button" class="vi-del" data-id="' + v.id + '">' + muneaT('common.delete', '刪除') + '</button></div>').join('')) : '';   // 看診管理清單標題守門（Edward 2026-07-15 事故）
  }
  if ($('#visitList')) $('#visitList').addEventListener('click', e => {
    const sum = e.target.closest('.vi-sum');
    if (sum) {
      $('#visitModal').classList.remove('show');
      if (typeof openVisitSummary === 'function') openVisitSummary('visit-list');
      return;
    }
    const b = e.target.closest('.vi-del'); if (!b) return;
    const currentVisits = loadVisits();
    const removed = currentVisits.find(v => String(v.id) === String(b.dataset.id));
    saveVisits(currentVisits.filter(v => String(v.id) !== String(b.dataset.id)));
    if (removed) archiveRoutineReminder(removed.id);
    renderVisitList(); renderVisitRow();
  });
  if ($('#visitEntry')) $('#visitEntry').addEventListener('click', () => {
    wireVisitDateField();
    wireVisitLeadChips();
    resetVisitDate();
    resetVisitLead();
    if ($('#visitTitle')) $('#visitTitle').value = '';
    if ($('#visitTime')) $('#visitTime').value = '09:00';
    renderVisitList();
    $('#visitModal').classList.add('show');
  });
  if ($('#visitClose')) $('#visitClose').addEventListener('click', () => $('#visitModal').classList.remove('show'));
  if ($('#visitModal')) $('#visitModal').addEventListener('click', e => { if (e.target === $('#visitModal')) $('#visitModal').classList.remove('show'); });
  if ($('#visitSaveBtn')) $('#visitSaveBtn').addEventListener('click', () => {
    const pickedISO = visitPickedISO();
    if (!pickedISO) { toast(muneaT('visit.pickDayFirst', '先選一天')); return; }
    const title = ((($('#visitTitle') && $('#visitTitle').value) || '').trim()) || muneaT('visit.defaultTitle', '回診');
    const tv = ($('#visitTime') && $('#visitTime').value) || '09:00';
    const d = new Date(pickedISO + 'T00:00');
    const label = fmtDay(d) + ' ' + fmtVisitTime(tv);
    const visit = { id: Date.now(), title, dateISO: pickedISO, time: tv, label, remindBefore: visitLeadMinutes() };
    const arr = loadVisits(); arr.push(visit);
    saveVisits(arr);
    syncVisitReminder(visit);
    renderVisitList(); renderVisitRow();
    if ($('#visitTitle')) $('#visitTitle').value = '';
    resetVisitDate();
    resetVisitLead();
    toast(muneaT('visit.savedToast', '好，「{title}」{label}記下了，{companion}會{lead}提醒你',
      { title, label, companion: cname(), lead: visitLeadSpoken(visit.remindBefore) }));
  });
  renderVisitRow();
  refreshRoutineRemindersFromBackend();
  const FONT_STEPS = [
    ['std', () => muneaT('font.standard', '標準'), ''],
    ['lg', () => muneaT('font.large', '大'), '1.07'],
    ['xl', () => muneaT('font.extraLarge', '特大'), '1.14'],
  ];
  function applyFontScale() {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    const step = FONT_STEPS.find(x => x[0] === cur) || FONT_STEPS[0];
    // .reader-page 也要跟著放大。2026-07-29 就診摘要從 .modal 改成子頁後，
    // 它就掉出這個選擇器＝使用者選了「特大」卻完全沒變大——而這一頁正是最需要
    // 放大的一頁（長輩在診間拿著唸給醫生聽）。順帶把通知中心、條款那幾個子頁
    // 一起納入，它們本來也一直沒被縮放到。
    document.querySelectorAll('.screen .pad, .modal, .reader-page').forEach(el => { el.style.zoom = step[2]; });
    const row = $('#fontNow');
    if (row) row.textContent = step[1]() + ' ›';
  }
  window.__muneaApplyFontScale = applyFontScale;
  function markFontOpt() {
    const cur = localStorage.getItem('munea.fontScale') || 'std';
    document.querySelectorAll('.font-opt').forEach(o => o.classList.toggle('on', o.dataset.f === cur));
  }
  if ($('#fontRow')) $('#fontRow').addEventListener('click', () => { markFontOpt(); $('#fontModal').classList.add('show'); });
  if ($('#fontClose')) $('#fontClose').addEventListener('click', () => $('#fontModal').classList.remove('show'));
  if ($('#fontModal')) $('#fontModal').addEventListener('click', e => {
    if (e.target === $('#fontModal')) { $('#fontModal').classList.remove('show'); return; }
    const o = e.target.closest('.font-opt');
    if (!o) return;
    try { localStorage.setItem('munea.fontScale', o.dataset.f); } catch (e2) {}
    applyFontScale();
    markFontOpt();
    const nm = ((FONT_STEPS.find(x => x[0] === o.dataset.f) || FONT_STEPS[0])[1])();
    toast(muneaT('font.changedToast', '好，改成「{name}」了', { name: nm }));
  });
  applyFontScale();
  // 條款／隱私閱讀器由最早期控制綁定，避免其他初始化失敗時連返回都不能操作。
  // 安全通知：選 1~3 位家庭圈家人當緊急聯絡人，健康數據危險異常時通知他們確認
  // 名單直接吃「設定 → 全家健康圈」同一份資料（單一真相）；圈裡移除了人，這裡自動跟著消失
  function safetyMembers() { return loadCircle().filter(m => !m.self); }
  function loadSafety() {
    try {
      const raw = JSON.parse(localStorage.getItem('munea.safetyContacts')) || [];
      const valid = new Set(safetyMembers().map(m => m.name));
      const sel = raw.filter(n => valid.has(n));
      if (sel.length !== raw.length) localStorage.setItem('munea.safetyContacts', JSON.stringify(sel));
      return sel;
    } catch (e) { return []; }
  }
  function updateSafetyCount() { const el = $('#safetyCount'); if (el) { const sel = loadSafety(); el.textContent = sel.length ? sel.join('、') : ''; } }
  function renderSafety() {
    const picks = $('#safetyPicks'); if (!picks) return;
    const sel = loadSafety();
    const mem = safetyMembers();
    picks.innerHTML = mem.length ? mem.map(m =>
      '<button type="button" class="safety-pick' + (sel.includes(m.name) ? ' on' : '') + '" data-name="' + m.name + '">' +
      '<span class="init-ava ' + muneaSafeTint(m.tint, m.name) + '">' + (m.init || (m.name || '')[0] || '') + '</span><span class="sp-name">' + m.name + '</span>' +
      '<span class="sp-check"><svg class="ic" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg></span></button>').join('')
      : '<p class="modal-sub" style="margin:4px 0 0">' + muneaT('familyCircle.emptyContactPick', '圈裡還沒有家人。先到「家人」頁邀請家人加入，就能選緊急聯絡人。') + '</p>';
    updateSafetyCount();
  }
  if ($('#safetyPicks')) $('#safetyPicks').addEventListener('click', e => {
    const b = e.target.closest('.safety-pick'); if (!b) return;
    let sel = loadSafety(); const name = b.dataset.name;
    if (sel.includes(name)) sel = sel.filter(n => n !== name);
    else { if (sel.length >= 3) { toast(muneaT('safety.maxContactsToast', '最多選 3 位緊急聯絡人')); return; } sel.push(name); }
    try { localStorage.setItem('munea.safetyContacts', JSON.stringify(sel)); } catch (e2) {}
    b.classList.toggle('on', sel.includes(name));
    updateSafetyCount();
  });
  if ($('#safetyRow')) $('#safetyRow').addEventListener('click', () => { renderSafety(); $('#safetyModal').classList.add('show'); });
  if ($('#safetySave')) $('#safetySave').addEventListener('click', () => {
    $('#safetyModal').classList.remove('show');
    const sel = loadSafety();
    toast(sel.length ? muneaT('safety.contactsSavedToast', '名單記好了：{names}。異常時我會第一時間讓家人知道。', { names: sel.join(muneaListSeparator()) }) : muneaT('safety.contactsNoneToast', '還沒選聯絡人，等你想好再設定就好'));
  });
  if ($('#safetyModal')) $('#safetyModal').addEventListener('click', e => { if (e.target === $('#safetyModal')) $('#safetyModal').classList.remove('show'); });
  updateSafetyCount();
  // 想聊的話題：設定入口＋第一次開聊前輕問一次（可跳過、只問一次）
  let _intSel = loadInterests();
  let _intFromCall = false;
  function renderInterestPicks() {
    const box = $('#interestPicks');
    if (box) box.innerHTML = INTEREST_TOPICS.map(t => '<button type="button" class="topic-chip' + (_intSel.includes(t) ? ' on' : '') + '" data-t="' + t + '">' + interestTopicLabel(t) + '</button>').join('');
    const now = $('#interestsNow');
    if (now) now.innerHTML = _intSel.length ? ('<b>' + muneaT('interests.pickedCount', '已挑 {count} 個', { count: _intSel.length }) + '</b> ›') : '›';
  }
  window.__muneaOpenInterests = function (fromCall) {
    _intSel = loadInterests(); _intFromCall = !!fromCall;
    renderInterestPicks();
    const skip = $('#interestsSkip'); if (skip) skip.style.display = fromCall ? '' : 'none';
    $('#interestsModal').classList.add('show');
  };
  function closeInterests(startAfter) {
    $('#interestsModal').classList.remove('show');
    try { localStorage.setItem('munea.interestsAsked', '1'); } catch (e2) {}
    const goCall = startAfter && _intFromCall;
    _intFromCall = false;
    if (goCall) connectCall();
  }
  if ($('#interestPicks')) $('#interestPicks').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    const t = b.dataset.t;
    if (_intSel.includes(t)) _intSel = _intSel.filter(x => x !== t);
    else { if (_intSel.length >= 5) { toast(muneaT('interests.maxFiveHint', "挑 5 個以內就好，聊得才深")); return; } _intSel.push(t); }
    b.classList.toggle('on', _intSel.includes(t));
  });
  if ($('#interestsRow')) $('#interestsRow').addEventListener('click', () => window.__muneaOpenInterests(false));
  // ===== 意見與建議（回報問題/功能建議/稱讚/NPS）→ 引擎收件箱＋Slack 叮一聲 =====
  let _fbType = 'bug', _fbNps = null;
  function renderNps() {
    // 拉桿 Bar 條打分（Edward 7/9：不要 11 顆按鈕）：拉或點都行、上方大字即時顯示
    const s = $('#npsSlider'); if (!s || s.dataset.built) return; s.dataset.built = '1';
    const WORDS = [
      muneaT('feedback.npsVeryUnlikely', 'Very unlikely'),
      muneaT('feedback.npsUnlikely', 'Unlikely'),
      muneaT('feedback.npsUnlikely', 'Unlikely'),
      muneaT('feedback.npsNeutral', 'Neutral'),
      muneaT('feedback.npsNeutral', 'Neutral'),
      muneaT('feedback.npsNeutral', 'Neutral'),
      muneaT('feedback.npsSomewhatLikely', 'Somewhat likely'),
      muneaT('feedback.npsLikely', 'Likely'),
      muneaT('feedback.npsLikely', 'Likely'),
      muneaT('feedback.npsVeryLikely', 'Very likely'),
      muneaT('feedback.npsVeryLikely', 'Very likely'),
    ];
    const paint = () => {
      const v = +s.value;
      s.style.setProperty('--fill', (v * 10) + '%');
      if ($('#npsVal')) $('#npsVal').textContent = String(v);
      if ($('#npsWord')) $('#npsWord').textContent = WORDS[v] || '';
    };
    const pick = () => { _fbNps = +s.value; paint(); };
    s.addEventListener('input', pick);
    s.addEventListener('change', pick);
  }
  function fbApplyType() {
    if ($('#fbCatWrap')) $('#fbCatWrap').style.display = _fbType === 'bug' ? '' : 'none';
    if ($('#fbNpsWrap')) $('#fbNpsWrap').style.display = _fbType === 'nps' ? '' : 'none';
    const lbl = $('#fbTextLabel'), txt = $('#fbText');
    const feedbackCopy = {
      bug: ['feedback.promptBug', 'What happened? Details help us fix it faster.', 'feedback.placeholderBug', 'For example: The conversation went silent halfway through.'],
      idea: ['feedback.promptIdea', 'What would you like Munea to add?', 'feedback.placeholderIdea', 'For example: Help me record blood sugar or support another language.'],
      praise: ['feedback.promptPraise', 'What did you appreciate?', 'feedback.placeholderPraise', 'For example: My companion remembered an important family event.'],
      nps: ['feedback.promptNps', 'Why did you choose this score? (Optional)', 'feedback.placeholderNps', 'Tell us what shaped your score.'],
    }[_fbType];
    if (lbl) lbl.textContent = muneaT(feedbackCopy[0], feedbackCopy[1]);
    if (txt) txt.placeholder = muneaT(feedbackCopy[2], feedbackCopy[3]);
    renderNps();
  }
  // 意見回饋附圖（7/9 Edward：文字說不清時附截圖）：選圖→縮到最長邊 1200px、壓成 JPEG→data URL 預覽
  let _fbImage = null;
  function fbClearPhoto() {
    _fbImage = null;
    const inp = $('#fbPhotoInput'); if (inp) inp.value = '';
    const pv = $('#fbPhotoPreview'); if (pv) pv.style.display = 'none';
    const add = $('#fbPhotoAdd'); if (add) add.style.display = '';
  }
  if ($('#fbPhotoAdd')) $('#fbPhotoAdd').addEventListener('click', () => $('#fbPhotoInput') && $('#fbPhotoInput').click());
  if ($('#fbPhotoRemove')) $('#fbPhotoRemove').addEventListener('click', fbClearPhoto);
  if ($('#fbPhotoInput')) $('#fbPhotoInput').addEventListener('change', e => {
    const file = e.target.files && e.target.files[0]; if (!file) return;
    const rd = new FileReader();
    rd.onload = () => {
      const img = new Image();
      img.onload = () => {
        const max = 1200, scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const cv = document.createElement('canvas'); cv.width = w; cv.height = h;
        cv.getContext('2d').drawImage(img, 0, 0, w, h);
        _fbImage = cv.toDataURL('image/jpeg', 0.7);   // 壓過通常 <150KB
        const el = $('#fbPhotoImg'); if (el) el.src = _fbImage;
        const pv = $('#fbPhotoPreview'); if (pv) pv.style.display = '';
        const add = $('#fbPhotoAdd'); if (add) add.style.display = 'none';
      };
      img.onerror = () => toast(muneaT('feedback.photoUnreadable', '這張圖讀不了，換一張試試'));
      img.src = rd.result;
    };
    rd.readAsDataURL(file);
  });
  if ($('#feedbackRow')) $('#feedbackRow').addEventListener('click', () => { fbApplyType(); fbClearPhoto(); $('#feedbackModal').classList.add('show'); });
  if ($('#fbTypes')) $('#fbTypes').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    _fbType = b.dataset.t;
    $('#fbTypes').querySelectorAll('.topic-chip').forEach(x => x.classList.toggle('on', x === b));
    fbApplyType();
  });
  if ($('#fbCats')) $('#fbCats').addEventListener('click', e => {
    const b = e.target.closest('.topic-chip'); if (!b) return;
    $('#fbCats').querySelectorAll('.topic-chip').forEach(x => x.classList.toggle('on', x === b));
  });
  if ($('#fbSend')) $('#fbSend').addEventListener('click', async () => {
    const text = ($('#fbText') && $('#fbText').value.trim()) || '';
    if (_fbType === 'nps' && _fbNps === null) { toast(muneaT('feedback.pickScoreFirst', "先拉一下分數條，選個 0～10 的分數")); return; }
    if (_fbType !== 'nps' && !text) { toast(muneaT('feedback.needText', '說一句就好，我們想聽')); return; }
    const cat = _fbType === 'bug' ? ((document.querySelector('#fbCats .topic-chip.on') || { dataset: {} }).dataset.c || '其他') : '';
    const body = { type: _fbType, category: cat, text: text, score: _fbNps, appVersion: (window.MuneaVersion && window.MuneaVersion.current) || '', plan: (window.MMPLAN && window.MMPLAN.get()) || '' };
    if (_fbImage) body.image = _fbImage;   // 選填附圖（已壓縮）
    brainPost('/feedback', body);
    trackProductEvent('feedback_submitted', { type: _fbType, category: cat, score: _fbNps, hasImage: !!_fbImage });
    $('#feedbackModal').classList.remove('show');
    if ($('#fbText')) $('#fbText').value = ''; _fbNps = null; fbClearPhoto(); const r = $('#npsRow'); if (r) r.querySelectorAll('.nps-btn').forEach(x => x.classList.remove('on'));
    toast(_fbType === 'praise' ? muneaT('feedback.thanksPraise', '收到了，{companion}會很開心！', { companion: cname() }) : muneaT('feedback.thanksGeneric', '收到了，謝謝你——我們會認真看'));
  });

  // ===== App Store 評分彈窗：只在開心時刻、每版最多一次、負面情境絕不跳 =====
  // 原生視窗＝ StorePlugin.requestReview（ios/App/App/StorePlugin.swift），下面這行把它接成 __muneaRequestReview。
  // 網頁預覽沒有原生外掛 → 接不上，時機閘會自己跳過（見下方 native_unavailable 那道）。
  if (window.MuneaStore && typeof window.MuneaStore.requestReview === 'function' && window.MuneaStore.available()) {
    window.__muneaRequestReview = function () { return window.MuneaStore.requestReview(); };
  }
  // 問過就不再問——這是一輩子一次的章，不是「每版一次」。
  // 2026-08-10 Edward：「評分那個彈窗不要一直跳！用戶不想填跳過了就不要再出現。」
  // 舊版蓋的章是 munea.reviewAsked.<版號>，所以每出一版就重新問一次；他測版本測得勤，
  // 感覺就是一直跳。而且蘋果那個視窗**不會回報使用者按了什麼**——我們無從分辨
  // 「給了五顆星」還是「滑掉不想理」，那就一律當成不想再被打擾。
  const REVIEW_ASKED_KEY = 'munea.reviewAsked.forever';
  function reviewAlreadyAsked() {
    try {
      if (localStorage.getItem(REVIEW_ASKED_KEY)) return true;
      // 已經被舊規矩問過的人，不要因為換了新規矩又被問一次。
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.indexOf('munea.reviewAsked.') === 0) {
          localStorage.setItem(REVIEW_ASKED_KEY, '1');
          return true;
        }
      }
    } catch (e) {}
    return false;
  }
  window.__muneaMaybeAskReview = function (moment) {
    try {
      if (reviewAlreadyAsked()) return;                                          // 一輩子最多一次
      if (localStorage.getItem('munea.reviewCoolOff') === '1') return;            // 負面情境冷卻（斷線/錯誤後設）
      const chats = +(localStorage.getItem('munea.stat.chatsCompleted') || 0);
      const okMoment = (moment === 'chat_completed' && chats >= 3) || moment === 'activity_done';
      if (!okMoment) return;
      // 原生沒接上就直接退場、不蓋「問過了」的章——否則補好原生也叫不動已裝機的人（2026-07-29 修）
      if (typeof window.__muneaRequestReview !== 'function') {
        trackProductEvent('review_prompt_skipped', { moment: moment, reason: 'native_unavailable' });
        return;
      }
      localStorage.setItem(REVIEW_ASKED_KEY, '1');
      trackProductEvent('review_prompt_shown', { moment: moment });
      window.__muneaRequestReview();
    } catch (e) {}
  };
  if ($('#interestsSave')) $('#interestsSave').addEventListener('click', () => {
    saveInterests(_intSel);
    trackProductEvent('interests_saved', { count: _intSel.length });
    renderInterestPicks();
    toast(_intSel.length ? muneaT('interests.savedToast', '記下了，這些話題我會多幫你留意新鮮事') : muneaT('interests.skippedToast', '好，不挑也行，想聊什麼直接說'));
    closeInterests(true);
  });
  if ($('#interestsSkip')) $('#interestsSkip').addEventListener('click', () => closeInterests(true));
  if ($('#interestsModal')) $('#interestsModal').addEventListener('click', e => { if (e.target === $('#interestsModal')) closeInterests(false); });
  renderInterestPicks();
  // 彈窗通用 X（右上角）：掛 .mx-close 的按鈕一律關掉自己所在的視窗（7/8 Edward 巡檢後補齊）
  document.querySelectorAll('.mx-close').forEach(b => b.addEventListener('click', e => {
    e.stopPropagation();
    const mk = b.closest('.modal-mask');
    if (mk) mk.classList.remove('show');
  }));
  if ($('#termsRow')) $('#termsRow').addEventListener('click', () => openInAppReader('terms'));
  if ($('#privacyPolicyRow')) $('#privacyPolicyRow').addEventListener('click', () => openInAppReader('privacy'));
  if ($('#versionRow')) $('#versionRow').addEventListener('click', openVersionSheet);
  if ($('#verClose')) $('#verClose').addEventListener('click', () => $('#versionSheet').classList.remove('show'));
  applyAppVersion();
  // 設定頁「就診摘要」：點了就打開，外層不顯示天數（Edward 2026-07-28）。
  // 天數在摘要裡面用 7／14／30／60 四顆膠囊選——外層再標一次是重複資訊。
  if ($('#visitSummaryRow')) $('#visitSummaryRow').addEventListener('click', () => {
    if (typeof openVisitSummary === 'function') openVisitSummary('settings');
  });
  if ($('#privacyRow')) $('#privacyRow').addEventListener('click', () => $('#dataModal').classList.add('show'));
  if ($('#dataClose')) $('#dataClose').addEventListener('click', () => $('#dataModal').classList.remove('show'));
  if ($('#dataModal')) $('#dataModal').addEventListener('click', e => { if (e.target === $('#dataModal')) $('#dataModal').classList.remove('show'); });
  if ($('#dataExportBtn')) $('#dataExportBtn').addEventListener('click', async () => {
    const b = $('#dataExportBtn');
    if (authState().status !== 'signed-in') { toast(muneaT('profile.exportLoginFirst', "請先登入，才能安全匯出只屬於你的資料")); return; }
    setBtnBusy(b, muneaT('profile.exportPreparing', '正在整理資料'));
    const result = await brainPost('/privacy-export', { action: 'request' });
    clearBtnBusy(b, muneaT('report.exportButton', '匯出一份給我'));
    if (!(result && result.ok && result.status === 'completed' && result.exportPackage)) {
      toast(muneaT('profile.exportFailedToast', "資料副本沒有建立，請確認登入與網路後再試一次"));
      return;
    }
    const filename = result.filename || 'munea-personal-data.json';
    const json = JSON.stringify(result.exportPackage, null, 2);
    const file = new File([json], filename, { type: 'application/json' });
    try {
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({ title: muneaT('profile.exportShareTitle', '沐寧個人資料副本'), files: [file] });
      } else {
        const url = URL.createObjectURL(file);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 30000);
      }
      toast(muneaT('profile.exportReadyToast', '資料副本已建立，只包含你本人與你的帳務資料'));
    } catch (e) {
      if (e && e.name !== 'AbortError') toast(muneaT('profile.exportShareIncomplete', "資料已建立，但分享視窗沒有完成；可以再按一次"));
    }
  });
  if ($('#dataDeleteBtn')) $('#dataDeleteBtn').addEventListener('click', () => {
    const b = $('#dataDeleteBtn');
    const signedIn = authState().status === 'signed-in';
    if (b.dataset.arm !== '1') {
      b.dataset.arm = '1';
      b.textContent = signedIn ? muneaT('data.confirmDeleteAccount', '再按一次：永久刪除帳號與資料') : muneaT('data.confirmDeleteLocal', '再按一次：清除這台裝置的資料');
      setTimeout(() => { b.dataset.arm = ''; b.textContent = muneaT('data.delete', '刪除我的資料'); }, 6000);
      return;
    }
    b.dataset.arm = ''; b.textContent = muneaT('data.delete', '刪除我的資料');
    (async () => {
      b.disabled = true;
      b.textContent = signedIn ? muneaT('data.deletingAccount', '正在永久刪除') : muneaT('data.clearingLocal', '正在清除');
      let deletion = null;
      if (signedIn) {
        deletion = await brainPost('/account-deletion', { action: 'request', reason: 'user_requested_in_app' });
        if (!(deletion && deletion.ok && deletion.accountDeleted)) {
          b.disabled = false;
          b.textContent = muneaT('data.delete', '刪除我的資料');
          toast(muneaT('profile.deleteFailedToast', "帳號與雲端資料尚未刪除，請確認網路後再試一次"));
          return;
        }
        if (typeof signOutAuth === 'function') { try { await signOutAuth(); } catch (e) {} }
      }
      try {
        const ks = [];
        for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k && k.indexOf('munea.') === 0) ks.push(k); }
        ks.forEach(k => localStorage.removeItem(k));
      } catch (e) {}
      $('#dataModal').classList.remove('show');
      if (!signedIn) toast(muneaT('profile.localDataCleared', "這台裝置上的沐寧資料已清除"));
      else if (deletion.authUserDeleted) toast(muneaT('profile.accountDeletedToast', "帳號與雲端資料已永久刪除；Apple 訂閱需另行取消"));
      else toast(muneaT('profile.cloudDeletedToast', "雲端資料已刪除，登入帳號移除正在完成；Apple 訂閱需另行取消"));
      setTimeout(() => { location.reload(); }, 1200);
    })();
  });
  const authTermsLink = document.querySelector('.auth-terms a');
  if (authTermsLink) authTermsLink.addEventListener('click', e => { e.preventDefault(); closeAuthSheet(); openLegal('terms'); });
  if ($('#historyEntry')) $('#historyEntry').addEventListener('click', () => { rcInit(); $('#historyModal').classList.add('show'); });
  if ($('#histSeg')) $('#histSeg').addEventListener('click', e => {
    const b = e.target.closest('.seg-btn');
    if (!b) return;
    $('#histSeg').querySelectorAll('.seg-btn').forEach(x => x.classList.toggle('on', x === b));
    $('#histMonths').style.display = b.dataset.v === 'months' ? '' : 'none';
    $('#histRange').style.display = b.dataset.v === 'range' ? '' : 'none';
  });
  // 自選日期範圍（一年內）
  let rcYear = 0, rcMonth = 0, rcStart = null, rcEnd = null;
  function rcInit() {
    const now = new Date();
    rcYear = now.getFullYear(); rcMonth = now.getMonth();
    rcStart = null; rcEnd = null;
    if ($('#rcResult')) { $('#rcResult').style.display = 'none'; }
    if ($('#rcHint')) $('#rcHint').textContent = muneaT('visit.rangePickHint', '點開始那天，再點結束那天');
    renderRangeCal();
  }
  function renderRangeCal() {
    const grid = $('#rcGrid');
    if (!grid) return;
    if ($('#rcTitle')) $('#rcTitle').textContent = (muneaLocale() || 'zh-TW').startsWith('zh')
      ? muneaT('history.monthTitle', '{year} 年 {month} 月', { year: rcYear, month: rcMonth + 1 })
      : new Intl.DateTimeFormat(muneaLocale(), { year: 'numeric', month: 'long' }).format(new Date(rcYear, rcMonth, 1));
    const startPad = (new Date(rcYear, rcMonth, 1).getDay() + 6) % 7;
    const daysInM = new Date(rcYear, rcMonth + 1, 0).getDate();
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const minDate = new Date(today); minDate.setFullYear(minDate.getFullYear() - 1);
    let html = '';
    for (let i = 0; i < startPad; i++) html += '<span class="rc-cell pad"></span>';
    for (let d = 1; d <= daysInM; d++) {
      const dt = new Date(rcYear, rcMonth, d);
      const iso = isoOf(dt);
      let cls = 'rc-cell';
      if (dt > today || dt < minDate) cls += ' off';
      if (rcStart && iso === rcStart) cls += ' sel';
      if (rcEnd && iso === rcEnd) cls += ' sel';
      if (rcStart && rcEnd && iso > rcStart && iso < rcEnd) cls += ' in';
      html += '<span class="' + cls + '" data-iso="' + iso + '">' + d + '</span>';
    }
    grid.innerHTML = html;
  }
  function rcShowResult() {
    const a = new Date(rcStart + 'T00:00'), b2 = new Date(rcEnd + 'T00:00');
    const days = Math.round((b2 - a) / 86400000) + 1;
    const med = Math.max(1, Math.round(days * 0.86));
    const act = Math.max(1, Math.round(days * 0.55));
    const box = $('#rcResult');
    box.innerHTML = '<div class="rpt-row"><span class="rpt-k">' + muneaT('report.periodLabel', '期間') + '</span><div><b>' + muneaT('report.periodRange', '{from} 到 {to}', { from: fmtDay(a), to: fmtDay(b2) }) + '</b><span>' + muneaT('report.periodDaysDemo', '共 {days} 天（示範數據）', { days }) + '</span></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">' + muneaT('report.kMed', '用藥') + '</span><div><b>' + muneaT('report.medOnTime', '準時 {met} / {days} 天', { met: med, days }) + '</b></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">' + muneaT('report.kActivity', '活動') + '</span><div><b>' + muneaT('report.actMet', '達標 {days} 天', { days: act }) + '</b></div></div>' +
      '<div class="rpt-row"><span class="rpt-k">' + muneaT('report.kSleep', '睡眠') + '</span><div><b>' + muneaT('report.sleepAvgDemo', '平均 7.2 小時') + '</b></div></div>';
    box.style.display = '';
    if ($('#rcHint')) $('#rcHint').textContent = muneaT('report.pickAnotherStart', '要看別段，再點一次新的開始日');
  }
  if ($('#rcGrid')) $('#rcGrid').addEventListener('click', e => {
    const cell = e.target.closest('.rc-cell');
    if (!cell || cell.classList.contains('off') || cell.classList.contains('pad')) return;
    const iso = cell.dataset.iso;
    if (!rcStart || (rcStart && rcEnd)) { rcStart = iso; rcEnd = null; if ($('#rcResult')) $('#rcResult').style.display = 'none'; if ($('#rcHint')) $('#rcHint').textContent = muneaT('report.pickEndDay', '再點結束那天'); }
    else if (iso < rcStart) { rcStart = iso; if ($('#rcHint')) $('#rcHint').textContent = muneaT('report.pickEndDay', '再點結束那天'); }
    else { rcEnd = iso; rcShowResult(); }
    renderRangeCal();
  });
  if ($('#rcPrev')) $('#rcPrev').addEventListener('click', () => {
    const min = new Date(); min.setFullYear(min.getFullYear() - 1);
    if (new Date(rcYear, rcMonth - 1, 28) < min) { toast(muneaT('report.retentionLimitToast', '紀錄保存一年，再往前就沒有了')); return; }
    rcMonth--; if (rcMonth < 0) { rcMonth = 11; rcYear--; }
    renderRangeCal();
  });
  if ($('#rcNext')) $('#rcNext').addEventListener('click', () => {
    const now = new Date();
    if (rcYear === now.getFullYear() && rcMonth === now.getMonth()) { toast(muneaT('report.alreadyThisMonth', "已經是這個月了")); return; }
    rcMonth++; if (rcMonth > 11) { rcMonth = 0; rcYear++; }
    renderRangeCal();
  });
  if ($('#historyClose')) $('#historyClose').addEventListener('click', () => $('#historyModal').classList.remove('show'));
  if ($('#historyModal')) $('#historyModal').addEventListener('click', e => {
    if (e.target === $('#historyModal')) { $('#historyModal').classList.remove('show'); return; }
    const row = e.target.closest('.hist-row');
    if (row) toast(row.classList.contains('dim') ? muneaT('demo.history.demoRowToast', '正式版點開就是當月整理，示範先看 6 月這行') : muneaT('demo.history.juneReadyToast', '6 月整理好了，完整月報之後接引擎'));
  });

  // B1 提醒排程：app 開著就到點響（打包後升級推播）
  const SLOT_MIN = { '早餐後': ['b', 30], '午餐後': ['l', 30], '晚餐後': ['d', 30], '睡前': ['s', -30] };
  function slotDueMinutes(slot) {
    const m = SLOT_MIN[slot];
    if (!m) return null;
    const rt = loadRoutine();
    const [h2, mi] = (rt[m[0]] || '08:00').split(':').map(Number);
    return h2 * 60 + mi + m[1];
  }
  function todayKey() { const n = new Date(); return 'munea.medDone.' + isoOf(n); }
  let medSnoozeUntil = 0, medShowing = null;
  function fireMedReminder(med) {
    medShowing = med;
    renderMedicationReminderCopy(med);
    $('#medRemindModal').classList.add('show');
    // A6：寧寧親口說（App 開著時；打包後升級推播）
    try { if (typeof speakChat === 'function') speakChat(medicationReminderSpeech(med)); } catch (e) {}
  }
  function checkDueMeds() {
    if (Date.now() < medSnoozeUntil || medShowing) return;
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    let done = {};
    try { done = JSON.parse(localStorage.getItem(todayKey())) || {}; } catch (e) {}
    for (const med of loadMeds()) {
      for (const slot of String(med.time).split('、')) {
        const due = slotDueMinutes(slot.trim());
        if (due === null) continue;
        const key = slot.trim() + '|' + med.name;
        if (!done[key] && nowMin >= due && nowMin <= due + 20) { fireMedReminder({ ...med, time: slot.trim(), key }); return; }
      }
    }
  }
  window.__fireMedNow = () => { const m = loadMeds()[0]; if (m) fireMedReminder({ ...m, time: String(m.time).split('、')[0], key: 'test|' + m.name }); };
  if ($('#medTaken')) $('#medTaken').addEventListener('click', () => {
    if (medShowing) {
      if (window.MuneaMedication) {
        const dose = window.MuneaMedication.findDose(loadMeds(), medShowing.key, pillDateKey());
        if (dose) window.MuneaMedication.setStatus(dose, 'taken', 'notification');
      } else {
        let done = {};
        try { done = JSON.parse(localStorage.getItem(todayKey())) || {}; } catch (e) {}
        done[medShowing.key] = true;
        try { localStorage.setItem(todayKey(), JSON.stringify(done)); } catch (e) {}
        pushFamilyFeed(muneaT(
          'medicationReminder.familyFeedTaken',
          '{person}的{slot}藥已服用，{companion}已記錄。',
          {
            person: '<b>' + muneaEscapeHtml(myFeedName()) + '</b>',
            slot: localizedMedicationSlot(medShowing.time),
            companion: cname(),
          },
        ));
        trackProductEvent('routine_reminder_completed', { reminderType: 'medication' });
      }
    }
    medShowing = null;
    $('#medRemindModal').classList.remove('show');
    toast(muneaT('medicationReminder.takenToast', '已記錄為服用。'));
    renderPillTask();
  });
  if ($('#medSnooze')) $('#medSnooze').addEventListener('click', () => {
    medSnoozeUntil = Date.now() + 10 * 60 * 1000;
    medShowing = null;
    $('#medRemindModal').classList.remove('show');
    toast(muneaT(
      'medicationReminder.snoozedToast',
      '好，{minutes} 分鐘後再提醒你。',
      { minutes: new Intl.NumberFormat(muneaLocale()).format(10) },
    ));
  });
  setInterval(checkDueMeds, 30000);
  setTimeout(checkDueMeds, 1500);
  // 回診前一天：開 app 提醒一次
  (function visitEve() {
    const arr = (typeof loadVisits === 'function') ? loadVisits() : [];
    const t = new Date(); t.setDate(t.getDate() + 1); const tIso = isoOf(t);
    const v = arr.find(x => x && x.dateISO === tIso);
    if (!v || sessionStorage.getItem('visitEveShown')) return;
    sessionStorage.setItem('visitEveShown', '1');
    let _when = ((String(v.label || '').split('）')[1]) || '').trim();
    if (!_when && v.time && typeof fmtVisitTime === 'function') _when = fmtVisitTime(v.time);
    setTimeout(() => toast(_when ? muneaT('visit.tomorrowAtToast', '明天{when} 回診，回診摘要我準備好了', { when: String(_when).trim() }) : muneaT('visit.tomorrowToast', '明天回診，回診摘要我準備好了')), 1200);
  })();

  // 機智問答（示範題庫；正式版由寧寧出題、語音作答）
  const QUIZ_BANK = [
    { q: muneaT('quiz.q1', '一般建議大人每天走多少步，比較有活力？'), opts: [muneaT('quiz.q1o1', '500 步'), muneaT('quiz.q1o2', '2,000 步'), muneaT('quiz.q1o3', '7,000 步左右'), muneaT('quiz.q1o4', '50,000 步')], a: 2 },
    { q: muneaT('quiz.q2', '下面哪一個是台灣的傳統節日？'), opts: [muneaT('quiz.q2o1', '感恩節'), muneaT('quiz.q2o2', '端午節'), muneaT('quiz.q2o3', '萬聖節'), muneaT('quiz.q2o4', '復活節')], a: 1 },
    { q: muneaT('quiz.q3', '睡前做哪件事，通常比較好睡？'), opts: [muneaT('quiz.q3o1', '喝濃茶'), muneaT('quiz.q3o2', '滑手機'), muneaT('quiz.q3o3', '聽輕音樂'), muneaT('quiz.q3o4', '吃宵夜')], a: 2 },
    { q: muneaT('quiz.q4', '「一暝大一寸」說的是誰？'), opts: [muneaT('quiz.q4o1', '小嬰兒'), muneaT('quiz.q4o2', '大樹'), muneaT('quiz.q4o3', '月亮'), muneaT('quiz.q4o4', '麵團')], a: 0 },
    { q: muneaT('quiz.q5', '夏天出門，哪件事最重要？'), opts: [muneaT('quiz.q5o1', '多喝水'), muneaT('quiz.q5o2', '穿厚外套'), muneaT('quiz.q5o3', '戴毛帽'), muneaT('quiz.q5o4', '正中午曬太陽')], a: 0 },
    { q: muneaT('quiz.q6', '台灣哪個節日要吃湯圓？'), opts: [muneaT('quiz.q6o1', '冬至'), muneaT('quiz.q6o2', '端午節'), muneaT('quiz.q6o3', '中秋節'), muneaT('quiz.q6o4', '清明節')], a: 0 },
    { q: muneaT('quiz.q7', '晚上走路，穿什麼顏色比較安全？'), opts: [muneaT('quiz.q7o1', '亮色或反光'), muneaT('quiz.q7o2', '全黑'), muneaT('quiz.q7o3', '深藍'), muneaT('quiz.q7o4', '深咖啡')], a: 0 },
    { q: muneaT('quiz.q8', '「呷緊弄破碗」是什麼意思？'), opts: [muneaT('quiz.q8o1', '欲速則不達'), muneaT('quiz.q8o2', '吃飯要快'), muneaT('quiz.q8o3', '碗要買厚的'), muneaT('quiz.q8o4', '肚子餓了')], a: 0 },
    { q: muneaT('quiz.q9', '綠燈行，紅燈要怎樣？'), opts: [muneaT('quiz.q9o1', '停'), muneaT('quiz.q9o2', '衝'), muneaT('quiz.q9o3', '倒退'), muneaT('quiz.q9o4', '按喇叭')], a: 0 },
    { q: muneaT('quiz.q10', '台灣夏天最有名的水果是？'), opts: [muneaT('quiz.q10o1', '芒果'), muneaT('quiz.q10o2', '蘋果'), muneaT('quiz.q10o3', '水梨'), muneaT('quiz.q10o4', '柿子')], a: 0 },
    { q: muneaT('quiz.q11', '喝茶說的「回甘」是指？'), opts: [muneaT('quiz.q11o1', '喝完嘴裡回甜'), muneaT('quiz.q11o2', '茶很苦'), muneaT('quiz.q11o3', '茶涼了'), muneaT('quiz.q11o4', '要再泡一次')], a: 0 },
    { q: muneaT('quiz.q12', '中秋節大家常一起做什麼？'), opts: [muneaT('quiz.q12o1', '烤肉賞月'), muneaT('quiz.q12o2', '包粽子'), muneaT('quiz.q12o3', '掃墓'), muneaT('quiz.q12o4', '提燈籠')], a: 0 },
    { q: muneaT('quiz.q13', '台語「呷飽未」是什麼意思？'), opts: [muneaT('quiz.q13o1', '吃飽了嗎'), muneaT('quiz.q13o2', '睡飽了嗎'), muneaT('quiz.q13o3', '要出門嗎'), muneaT('quiz.q13o4', '天氣好嗎')], a: 0 },
    { q: muneaT('quiz.q14', '散步選什麼時段比較舒服？'), opts: [muneaT('quiz.q14o1', '清晨或傍晚'), muneaT('quiz.q14o2', '正中午'), muneaT('quiz.q14o3', '半夜'), muneaT('quiz.q14o4', '颱風天')], a: 0 },
    { q: muneaT('quiz.q15', '睡前喝哪一種，比較不好睡？'), opts: [muneaT('quiz.q15o1', '濃咖啡'), muneaT('quiz.q15o2', '溫開水'), muneaT('quiz.q15o3', '溫牛奶'), muneaT('quiz.q15o4', '無咖啡因花茶')], a: 0 },
    { q: muneaT('quiz.q16', '元宵節會做什麼？'), opts: [muneaT('quiz.q16o1', '提燈籠吃元宵'), muneaT('quiz.q16o2', '烤肉'), muneaT('quiz.q16o3', '立蛋'), muneaT('quiz.q16o4', '吃月餅')], a: 0 },
    { q: muneaT('quiz.q17', '「家和萬事」下一個字是？'), opts: [muneaT('quiz.q17o1', '興'), muneaT('quiz.q17o2', '好'), muneaT('quiz.q17o3', '成'), muneaT('quiz.q17o4', '樂')], a: 0 },
    { q: muneaT('quiz.q18', '適度曬太陽，身體會自己做出什麼？'), opts: [muneaT('quiz.q18o1', '維生素 D'), muneaT('quiz.q18o2', '維生素 C'), muneaT('quiz.q18o3', '鐵'), muneaT('quiz.q18o4', '鈣片')], a: 0 },
    { q: muneaT('quiz.q19', '過馬路前，先做哪件事？'), opts: [muneaT('quiz.q19o1', '左右看清楚'), muneaT('quiz.q19o2', '看手機'), muneaT('quiz.q19o3', '快跑'), muneaT('quiz.q19o4', '閉眼睛')], a: 0 },
  ];
  let quizState = null;

  // 寧寧當場出題（Edward 2026-08-01 拍板 B 案）
  //
  // 上面那份 QUIZ_BANK 是 19 題示範題庫，四國各自改寫過，但玩幾次就重複了。
  // 改成建立活動時跟雲端要一份新的：會配合他的語言、興趣與所在地，每次都不一樣。
  //
  // 拿不到就用內建題庫，玩得起來最重要——所以這裡任何一步失敗都只是「安靜退回」，
  // 不擋住他開始玩、也不跳錯誤訊息嚇他。雲端那邊出的題只要有一題不合格就整份不給，
  // 所以這裡收到的不是「好題目」就是「沒題目」，不必再挑一次。
  async function fetchQuizQuestions(count) {
    try {
      let interests = [], place = '';
      try { interests = (typeof loadInterests === 'function' ? loadInterests() : []) || []; } catch (e) {}
      try {
        const pp = JSON.parse(localStorage.getItem('munea.personProfile') || '{}');
        place = String(pp.city || '').trim();
      } catch (e) {}
      const r = await brainPost('/quiz-questions', { count: count, interests: interests, place: place });
      if (!r || !r.ok || !Array.isArray(r.questions) || !r.questions.length) return null;
      // 雲端已經逐題驗過，這裡只做最後一道形狀檢查——萬一舊版雲端回了別的東西，
      // 寧可用內建題庫，也不要讓畫面印出怪東西。
      const ok = r.questions.every(x => x
        && typeof x.q === 'string' && x.q.trim()
        && Array.isArray(x.opts) && x.opts.length === 4 && x.opts.every(o => typeof o === 'string' && o.trim())
        && Number.isInteger(x.a) && x.a >= 0 && x.a < 4);
      return ok ? r.questions.map(x => ({ q: x.q.trim(), opts: x.opts.map(o => o.trim()), a: x.a })) : null;
    } catch (e) { return null; }
  }

  async function startQuiz(act, card) {
    const want = Math.min(act.q || 5, 12);
    // 同一場活動只跟雲端要一次題：他關掉再點開，題目要跟剛剛一樣，不然一場活動兩套題。
    // 只掛在記憶體裡的活動物件上、不寫進手機儲存——題目沒必要佔空間、也不必同步給家人，
    // 而且每次作答本來就從第一題重新開始，不存也不會弄丟進度。
    if (!Array.isArray(act._questions) || !act._questions.length) {
      const fresh = await fetchQuizQuestions(want);
      if (fresh && fresh.length >= want) act._questions = fresh.slice(0, want);
    }
    const bank = (Array.isArray(act._questions) && act._questions.length) ? act._questions : QUIZ_BANK;
    quizState = { act, card, i: 0, score: 0, n: Math.min(want, bank.length), bank: bank };
    renderQuizStep();
    $('#quizModal').classList.add('show');
  }
  function renderQuizStep() {
    const st = quizState;
    if (!st) return;
    const item = (st.bank || QUIZ_BANK)[st.i];
    $('#quizProgress').textContent = muneaT('activity.quizProgress', '第 {current} 題／共 {total} 題', { current: st.i + 1, total: st.n });
    $('#quizQ').textContent = item.q;
    const order = item.opts.map((_, k) => k).sort((a2, b2) => ((a2 * 7 + st.i * 3) % 4) - ((b2 * 7 + st.i * 3) % 4));
    st.map = order;
    $('#quizOpts').innerHTML = order.map(k => '<button type="button" class="quiz-opt" data-k="' + k + '">' + item.opts[k] + '</button>').join('');
  }
  function finishQuiz() {
    const st = quizState;
    $('#quizProgress').textContent = muneaT('activity.quizDone', '完成！');
    $('#quizQ').textContent = '';
    $('#quizOpts').innerHTML = '<div class="quiz-score">' + muneaT('activity.quizScoreLine', '答對 {score} / {total} 題', { score: st.score, total: st.n }) + '</div>' +
      '<p class="modal-sub" style="text-align:center">' + muneaT('activity.quizAskOthers', '{names} 打開 App 也能玩，都答完就看排名', { companion: cname(), names: st.act.names.join(muneaListSeparator()) }) + '</p>' +
      '<button class="modal-btn quiz-close-btn" type="button">' + muneaT('common.ok', '好') + '</button>';
    const closeBtn = $('#quizOpts .quiz-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', () => $('#quizModal').classList.remove('show'));
    const note = st.card && st.card.querySelector('.qc-num');
    if (note) note.textContent = muneaT('activity.quizWaitOthers', '你答對 {score}/{total}，等 {names} 作答完看排名', { score: st.score, total: st.n, names: st.act.names.join(muneaListSeparator()) });
    const acts2 = loadActs();
    const rec = acts2.find(a => a.id === st.act.id);
    if (rec) {
      rec.answers = rec.answers || {};
      rec.answers['你'] = st.score;
      rec.myDone = true;
      const everyone = [...(rec.names || [])];
      if (everyone.every(n => rec.answers[n] !== undefined)) { rec.status = 'done'; rec.doneISO = isoOf(new Date()); }
      rec.score = st.score;
      saveActs(acts2);
    }
    pushFamilyFeed('<b>你</b>完成了機智問答，答對 ' + st.score + '/' + st.n + ' 題，等大家玩完看排名');
  }
  if ($('#quizOpts')) $('#quizOpts').addEventListener('click', e => {
    const btn = e.target.closest('.quiz-opt');
    if (!btn || !quizState) return;
    const item = (quizState.bank || QUIZ_BANK)[quizState.i];
    const k = +btn.dataset.k;
    [...$('#quizOpts').children].forEach(b2 => {
      if (+b2.dataset.k === item.a) b2.classList.add('good');
      else if (b2 === btn) b2.classList.add('bad');
      b2.disabled = true;
    });
    if (k === item.a) quizState.score++;
    setTimeout(() => { quizState.i++; if (quizState.i >= quizState.n) finishQuiz(); else renderQuizStep(); }, 700);
  });
  if ($('#quizModal')) $('#quizModal').addEventListener('click', e => { if (e.target === $('#quizModal')) $('#quizModal').classList.remove('show'); });

  // 家庭記錄簿
  // 有真的活動記錄就畫真的、把「範例」整組收起來；一場都還沒辦過才留範例讓人知道這頁長什麼樣
  function renderFamilyBook() {
    const box = $('#bookTimeline');
    const tag = $('#bookSampleTag');
    const note = $('#bookSampleNote');
    if (!box) return;
    const book = loadFamilyBook();
    const demo = $('#bookDemoEntries');
    if (!book.length) {
      if (tag) tag.hidden = false;
      if (note) note.hidden = false;
      if (demo) demo.hidden = false;
      const real = $('#bookRealEntries');
      if (real) real.innerHTML = '';
      return;
    }
    if (tag) tag.hidden = true;
    if (note) note.hidden = true;
    if (demo) demo.hidden = true;
    const real = $('#bookRealEntries');
    if (!real) return;
    const icon = '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="8" r="6"/><path d="M8.2 13.5 7 22l5-3 5 3-1.2-8.5"/></svg>';
    real.innerHTML = book.map(item => {
      const when = new Date(item.endedAt || Date.now());
      const day = (when.getMonth() + 1) + '/' + when.getDate();
      // 頭像要照範例卡那層包裝（.be-members > .be-mem > .init-ava）——少包一層 .be-mem，
      // 那排頭像就會被擠成直的一條（Edward 2026-08-01 一眼看出來）
      const faces = (item.people || []).map(n => {
        const av = FAM_AVA[n] || [(n || '')[0] || '', 'p-me'];
        const init = typeof av[0] === 'function' ? av[0]() : av[0];
        return '<span class="be-mem"><span class="init-ava ' + av[1] + '">'
          + muneaEscapeHtml(init) + '</span></span>';
      }).join('');
      return '<div class="book-entry">'
        + '<div class="be-head"><div class="be-title"><span class="be-medal">' + icon + '</span>'
        + muneaEscapeHtml(item.title || muneaT('activity.defaultTitle', '活動')) + '</div>'
        + '<span class="be-date">' + day + '</span></div>'
        + '<div class="be-foot"><span class="be-result">'
        + muneaEscapeHtml(item.result || '') + '</span>'
        + (faces ? '<div class="be-members">' + faces + '</div>' : '') + '</div>'
        + '</div>';
    }).join('');
  }
  function openBook() {
    showView('family');
    $$('#family .fam-view').forEach(v => v.classList.remove('active'));
    $('#viewBook').classList.add('active');
    try { renderFamilyBook(); } catch (e) {}
  }
  if ($('#bookBtn')) $('#bookBtn').addEventListener('click', openBook);
  const peekCard = document.querySelector('.fam-peek');
  if (peekCard) { peekCard.style.cursor = 'pointer'; peekCard.addEventListener('click', openBook); }
  if ($('#bookBack')) $('#bookBack').addEventListener('click', () => { $('#viewBook').classList.remove('active'); $('#viewAll').classList.add('active'); });

  // 聊聊：日常語音陪聊 · [ENGINE] 正式版換中文（台灣）/英文即時語音 + 反射腦
  const SR2 = window.SpeechRecognition || window.webkitSpeechRecognition;
  let chatRec = null, chatOn = false;
  const CHAT_RULES = [
    [/(藥.*(怎麼吃|幾顆|[0-9一二兩三四五]顆|停|加量|減量|可以吃|能不能吃))|劑量|(可以吃.*藥)/, '藥怎麼吃、吃幾顆，我不能幫你決定，這要聽醫生或藥師的喔。要不要我幫你記下來，回診時問醫生？'],
    [/痛|痠|不舒服|頭暈/, '聽到你不太舒服，我有點擔心。先坐下歇會兒，需要的話我幫你通知家人。'],
    [/累|睡不|失眠/, '辛苦了，累了就休息、不要硬撐，我在這裡陪你。'],
    [/孫|想.*他|想.*她|寂寞|一個人/, '想家人了是吧？要不要我提醒他們今晚打給你？'],
    [/吃|飯|餓|藥/, '好，吃飯吃藥都別忘了，到時間我會叫你。'],
    [/天氣|冷|熱|下雨/, '記得隨天氣加減衣服，別著涼了。'],
    [/謝|你真好|感謝/, '不用謝，陪著你是我最想做的事。'],
  ];
  function chatReply(t) { for (const [re, r] of CHAT_RULES) if (re.test(t.toLowerCase())) return r; return muneaT('chat.defaultListening', '我聽見了，你慢慢說，我都在。'); }
  // 中文時間／日期解析（聊聊自動建提醒用 · Edward 7/7）
  function zhDigit(s) {
    if (s == null) return NaN;
    s = String(s).replace('兩', '二');
    if (/^\d+$/.test(s)) return +s;
    const M = { 零: 0, 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
    if (s in M) return M[s];
    let m = s.match(/^十([一二三四五六七八九])?$/); if (m) return 10 + (m[1] ? M[m[1]] : 0);
    m = s.match(/^([二三四五六七八九])十([一二三四五六七八九])?$/); if (m) return M[m[1]] * 10 + (m[2] ? M[m[2]] : 0);
    return NaN;
  }
  function parseZhClock(t) { // → 'HH:MM' 或 null
    const m = t.match(/(凌晨|清晨|早晨|早上|上午|中午|下午|傍晚|晚上|晚間|夜裡|半夜)?\s*([0-9一二兩三四五六七八九十]{1,3})\s*[點点時](半|[0-9一二兩三四五六七八九十]{1,3})?\s*分?/);
    if (!m) return null;
    let h = zhDigit(m[2]); if (isNaN(h)) return null;
    let mi = 0;
    if (m[3]) { if (m[3] === '半') mi = 30; else { const mm = zhDigit(m[3]); if (!isNaN(mm)) mi = mm; } }
    const p = m[1] || '';
    if (/(下午|傍晚|晚上|晚間|夜裡)/.test(p) && h < 12) h += 12;
    if (/中午/.test(p)) { if (h < 12) h = 12; }
    if (/(凌晨|半夜)/.test(p) && h === 12) h = 0;
    if (/(清晨|早晨|早上|上午)/.test(p) && h === 12) h = 0;
    if (h > 23) h = h % 24;
    return String(h).padStart(2, '0') + ':' + String(mi).padStart(2, '0');
  }
  function clockToSegment(hhmm) { const h = +String(hhmm).split(':')[0]; return h < 10 ? '早餐後' : h < 14 ? '午餐後' : h < 19 ? '晚餐後' : '睡前'; }
  function parseZhDate(t) { // → Date 或 null
    const now = new Date(); const base = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (/大後天/.test(t)) { base.setDate(base.getDate() + 3); return base; }
    if (/後天/.test(t)) { base.setDate(base.getDate() + 2); return base; }
    if (/明天|明日/.test(t)) { base.setDate(base.getDate() + 1); return base; }
    if (/今天|今日|等一下|待會/.test(t)) return base;
    const wm = t.match(/(這|本|下|下個|下一)?\s*(週|周|星期|禮拜|拜)\s*([一二三四五六日天末])/);
    if (wm) {
      const map = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 日: 0, 天: 0, 末: 6 };
      const target = map[wm[3]]; const d = new Date(base); let add = (target - d.getDay() + 7) % 7;
      if (add === 0) add = 7; if (/(下|下個|下一)/.test(wm[1] || '')) add += 7;
      d.setDate(d.getDate() + add); return d;
    }
    const dm = t.match(/(\d{1,2})\s*[\/月]\s*(\d{1,2})/);
    if (dm) { let d = new Date(now.getFullYear(), +dm[1] - 1, +dm[2]); if (d < base) d = new Date(now.getFullYear() + 1, +dm[1] - 1, +dm[2]); return d; }
    return null;
  }
  let _pendingFamilyRelayDraft = null;
  function parseChatIntent(t) {
    // 聊聊代辦：講一句、寧寧直接把 app 設定做好（原型版；真腦版走同一批動作）
    // 問點數：用真錢包數字回答、順帶安心話（不推銷）
    if (/(還剩幾點|剩幾點|剩多少點|點數還有|點數剩|我有幾點)/.test(t)) {
      const left = POINTS.total - POINTS.used + POINTS.bought;
      return left > 0
        ? '我看了一下，你還有 ' + left + ' 點，語音陪聊大概還能聊 ' + left + ' 分鐘。放心，就算用完，基本陪伴也不會斷。'
        : '點數用完了喔——補一些點數就能繼續跟我聊，設定裡就能加值。';
    }
    // 傳話：①「提醒／告訴 某人 …」直接算 ②「跟 某人」必須真的接「說」才算（防「有跟誰約好」這種閒聊誤觸發）
    // 7/9 正式化：名單改吃真的全家健康圈成員（不再寫死示範名）；圈外仍有通用中文名比對兜底
    let KNOWN_FAM = [];
    try { KNOWN_FAM = (typeof loadCircle === 'function' ? loadCircle() : []).map(m => m.name).filter(Boolean); } catch (e) {}
    let relay0 = null;
    for (const nm of KNOWN_FAM) {
      relay0 = t.match(new RegExp('(提醒|告訴)\\s*(' + nm + ')(說|，|要|來)?\\s*(.{2,30})')) || t.match(new RegExp('(跟)\\s*(' + nm + ')(說)\\s*(.{2,30})'));
      if (relay0) break;
    }
    if (!relay0) relay0 = t.match(/(提醒|告訴)\s*([一-龥]{2,3})(說|，|要|來)?\s*(.{2,30})/) || t.match(/(跟)\s*([一-龥]{2,3})(說)\s*(.{2,30})/);
    const relayBadWho = /[我你妳他她誰哪]/;
    if (relay0 && !relayBadWho.test(relay0[2])) {
      let who = relay0[2].replace(/[要說來]$/, '');
      if (who.length < 2) who = relay0[2];
      const _msg = relay0[4].replace(/^[要說來，]/, '').replace(/[。！]$/, '');
      // 傳話會印在對方首頁最顯眼的位置，聽錯就是別人替你出糗、而他無從核對 → push 前先擋（Edward 2026-07-14）
      if (!muneaIsCleanSpeechText(_msg)) return '我剛剛沒聽清楚要帶的話，你再跟我說一次要跟' + who + '說什麼？';
      _pendingFamilyRelayDraft = { recipientName: who, message: _msg };
      return '我確認一下：你要我跟' + who + '說「' + _msg + '」，對嗎？';
    }
    // ===== 用藥提醒：聽到「幫我記得／提醒我…吃藥」→ 直接建好 =====
    const medTrig = /(提醒|記得|記錄|紀錄|幫我記|幫我排|安排|叫我)/.test(t);
    const medSig = /(吃藥|用藥|服藥)/.test(t) || (/(吃|服)\s*(「)?[一-龥A-Za-z0-9]{2,6}(」)?/.test(t) && /(藥|錠|膠囊|膜衣錠|優|血壓|糖|膽固醇|降|鈣|鐵|甲狀腺|抗凝)/.test(t));
    if (medTrig && medSig) {
      let name = (t.match(/(吃|服)\s*(「)?([一-龥A-Za-z0-9]{2,6}藥)/) || [])[3]
              || (t.match(/(吃|服)\s*(「)?([一-龥A-Za-z0-9]{2,4})/) || [])[3] || '';
      if (/^(的|一下|一顆|東西|飯|完)$/.test(name) || /(提醒|記得|時候|每天|天天|早上|中午|下午|晚上|睡前|點|要|了)/.test(name)) name = '';
      const clock = parseZhClock(t);
      const seg = (t.match(/(早餐後|午餐後|晚餐後|睡前)/) || [])[1] || (clock ? clockToSegment(clock) : '早餐後');
      const daysM = t.match(/(\d{1,3})\s*[天日]/);
      const days = daysM ? (daysM[1] + ' 天') : '長期';
      const meds = loadMeds();
      const med = { name: name || '藥', time: seg, days, by: '本人' };
      ensureMedReminderId(med);
      meds.push(med);
      try { localStorage.setItem('munea.meds', JSON.stringify(meds)); syncPush('meds', meds); } catch (e) {}
      syncMedicationReminder(med);
      updateMedCount();
      if (window.__medRefresh) { try { window.__medRefresh(); } catch (e3) {} }
      const whenSay = clock ? (clock + '（' + seg + '）') : seg;
      return '好，我幫你記下來了：' + (name ? '「' + name + '」' : '你的藥') + '，' + whenSay + '提醒你吃'
        + (days !== '長期' ? ('，連續 ' + days) : '') + '。到時間我會叫你，也會記下你有沒有吃。想改隨時跟我說。';
    }
    // ===== 回診提醒：聽到「記得我…回診」→ 抓日期＋時間建好 =====
    if (/(回診|看診|門診|複診|回院|要看醫生|去看醫生)/.test(t) && /(提醒|記得|記錄|紀錄|幫我記|排|安排|預約|要去|約|去)/.test(t)) {
      const d = parseZhDate(t);
      const clock = parseZhClock(t);
      if (d) {
        const wd = '日一二三四五六'[d.getDay()];
        const iso2 = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
        const timeStr = clock ? (' ' + clock) : (/(下午)/.test(t) ? ' 下午' : /(晚上|傍晚)/.test(t) ? ' 晚上' : /(上午|早上|早)/.test(t) ? ' 上午' : '');
        const label = (d.getMonth() + 1) + '/' + d.getDate() + '（週' + wd + '）' + timeStr;
        const visit = { id: Date.now(), title: '回診', dateISO: iso2, time: clock || '', label };
        try { localStorage.setItem('munea.visit', JSON.stringify({ dateISO: iso2, label })); } catch (e) {} syncPush('visit', { dateISO: iso2, label });
        try {
          const visits = JSON.parse(localStorage.getItem('munea.visits') || '[]') || [];
          visits.push(visit);
          localStorage.setItem('munea.visits', JSON.stringify(visits));
        } catch (e3) {}
        syncVisitReminder(visit);
        if (typeof renderVisitRow === 'function') try { renderVisitRow(); } catch (e2) {}
        return '記好了，' + label + '回診。我前一天會提醒你，回診要問醫生的、要帶的東西，也會先幫你準備好。';
      }
      return '好，跟我說是哪一天回診就好（像是「明天下午三點」「下週三」或「7 月 10 日」），我馬上幫你設。';
    }
    return null;
  }
  window.__chatTest = t => { const r = parseChatIntent(t); return r || chatReply(t); };
  window.__chatSay = t => chatHandle(t);
  async function chatHandle(t) {
    if (_pendingFamilyRelayDraft && /^(對|是|好|可以|沒錯|正確|嗯)/.test(String(t || '').trim())) {
      const draft = _pendingFamilyRelayDraft;
      _pendingFamilyRelayDraft = null;
      const sent = await createFamilyRelay(draft.recipientName, draft.message);
      speakChat(sent.ok
        ? ('好，' + draft.recipientName + '下次打開聊聊時，我會先說「' + draft.message + '」。')
        : '這句話目前還沒送出去，請先確認家庭圈成員名稱，再跟我說一次。');
      return;
    }
    if (_pendingFamilyRelayDraft && /^(不|不是|取消|不要)/.test(String(t || '').trim())) {
      _pendingFamilyRelayDraft = null;
      speakChat('好，我先不傳。');
      return;
    }
    const acted = parseChatIntent(t);
    if (acted) { speakChat(acted); return; }
    setLocalizedRuntimeHint('heard');
    chatHistory.push({ role: 'user', text: t });
    activeChatTurnCount += 1;
    // [S2S] 思考態：不顯示文字稿，只讓臉與狀態提示表達「她在想」
    setTimeout(() => { setFaceState('thinking'); setLocalizedRuntimeHint('thinking'); }, 380);
    const r = await voiceProvider.sendText({ history: chatHistory, char: currentChar });
    if (r && r.reply) {                              // 真腦回話＋真聲音
      if (_brainDegraded) {
        _brainDegraded = false;
        setLocalizedRuntimeCaption('recovered');
        trackProductEvent('voice_brain_recovered', { turnCount: activeChatTurnCount });
      }
      setLocalizedCallHint('speaking');
      chatHistory.push({ role: 'model', text: r.reply });
      if (r.audio) playB64(r.audio); else speakChat(r.reply);
      faceSpeak(r.reply);
      trackProductEvent('voice_turn_completed', {
        turnCount: activeChatTurnCount,
        replyAudio: !!r.audio,
        fallbackUsed: false,
      });
      postTurnReview();
    } else {                                          // 沒真腦 → 退回規則版（純靜態 demo 也能動）
      if (!_brainDegraded) {
        _brainDegraded = true;
        setLocalizedRuntimeCaption('degraded');
      }
      const rr = chatReply(t);
      setLocalizedCallHint('speaking');
      chatHistory.push({ role: 'model', text: rr });
      speakChat(rr);
      faceSpeak(rr);
      trackProductEvent('voice_session_fallback_used', {
        turnCount: activeChatTurnCount,
        fallback: 'local-rule-reply',
      });
      postTurnReview();
    }
  }
  // 全滿出口「先用文字聊」的送出／面板事件綁定（函式本體移到頂層 scope，見 showCallStatusCard 附近——
  // connectCall() 是頂層函式，需要在真的要撥號前呼叫 exitTextFallbackChat() 收面板，兩邊都要拿得到）。
  window.__muneaSendTextFallback = sendTextFallbackMessage;   // 供 Chrome MCP／自動測試直接觸發送出
  if ($('#textChatSend')) $('#textChatSend').addEventListener('click', sendTextFallbackMessage);
  if ($('#textChatInput')) $('#textChatInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendTextFallbackMessage(); }
  });
  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  }
  async function sendVoiceNote(blob, durationMs) {
    if (!blob || !blob.size) {
      setLocalizedRuntimeHint('didNotHear');
      setFaceState('idle');
      return;
    }
    setLocalizedRuntimeHint('thinking');
    const audio = await blobToDataUrl(blob);
    const r = await voiceProvider.sendVoiceNote({ char: currentChar, audio, mime: blob.type || 'audio/webm', durationMs });
    if (r && r.ok) {
      trackProductEvent('voice_note_uploaded', {
        durationMs,
        bytes: r.bytes || 0,
        mime: blob.type || 'audio/webm',
      });
      setLocalizedCallHint('speaking');
    } else {
      trackProductEvent('voice_session_fallback_used', {
        fallback: 'voice-note-upload-failed',
        durationMs,
      });
      setLocalizedCallHint('unavailable');
      const s = prompt(muneaT(
        'voice.runtime.textFallbackPrompt',
        '我先用文字接住你，想跟{companion}說什麼？',
        { companion: companionDisplayName },
      ));
      if (s) chatHandle(s);
    }
    setFaceState('idle');
  }
  const chatMic = $('#chatMic');
  let mediaRec = null, mediaChunks = [], mediaStartedAt = 0;
  async function startVoiceCapture() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      const s = prompt(muneaT(
        'voice.runtime.deviceTextFallbackPrompt',
        '這個裝置暫時無法使用語音，我們先用文字。想跟{companion}說什麼？',
        { companion: companionDisplayName },
      ));
      if (s) chatHandle(s);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaChunks = [];
      mediaStartedAt = Date.now();
      mediaRec = new MediaRecorder(stream);
      mediaRec.ondataavailable = e => { if (e.data && e.data.size) mediaChunks.push(e.data); };
      mediaRec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        chatOn = false;
        chatMic.classList.remove('recording');
        const blob = new Blob(mediaChunks, { type: mediaRec.mimeType || 'audio/webm' });
        await sendVoiceNote(blob, Date.now() - mediaStartedAt);
      };
      mediaRec.start();
      chatOn = true;
      chatMic.classList.add('recording');
      setFaceState('listening');
      setLocalizedRuntimeHint('recordingTapWhenDone');
    } catch (e) {
      setLocalizedRuntimeHint('microphonePermission');
      const s = prompt(muneaT(
        'voice.runtime.microphoneTextFallbackPrompt',
        '想跟{companion}說什麼？',
        { companion: companionDisplayName },
      ));
      if (s) chatHandle(s);
    }
  }
  let micMuted = false;
  function startListening() {
    if (!SR2 || chatOn || micMuted || !callConnected) return;
    chatRec = new SR2(); chatRec.lang = muneaLocale(); chatRec.interimResults = false;
    chatRec.onstart = () => { chatOn = true; chatMic && chatMic.classList.add('recording'); setFaceState('listening'); setLocalizedCallHint('ready'); };
    chatRec.onresult = e => chatHandle(e.results[0][0].transcript);
    chatRec.onend = () => {
      chatOn = false;
      chatMic && chatMic.classList.remove('recording');
      if (callConnected && !micMuted) { setTimeout(() => startListening(), 300); }
      else if ($('#chat') && $('#chat').dataset.state === 'listening') setFaceState('idle');
    };
    chatRec.onerror = chatRec.onend;
    try { chatRec.start(); } catch (e) {}
  }
  window.__muneaStartListen = startListening;
  window.__muneaStopListen = () => { micMuted = false; try { chatRec && chatRec.stop(); } catch (e) {} };
  if (chatMic) chatMic.addEventListener('click', async () => {
    // 真即時語音模式（LiveVoice/Gemini）：麥克風鈕＝純靜音開關，絕不碰舊的打字/錄音備援（Edward 2026-07-10：不該有藍色狀態變打字）
    if (getLiveVoiceUrl() && typeof LiveVoice !== 'undefined' && LiveVoice.on) {
      micMuted = !micMuted;
      chatMic.classList.toggle('off', micMuted);
      try { LiveVoice.micOpen = !micMuted; } catch (e) {}   // 靜音＝停收音；開啟＝恢復（半雙工仍套用：她說話時本就靜音）
      setLocalizedRuntimeHint(micMuted ? 'microphoneMutedHint' : 'listening');
      return;
    }
    if (!SR2) {
      if (chatOn && mediaRec) { mediaRec.stop(); return; }
      await startVoiceCapture();
      return;
    }
    if (!callConnected) { // 還沒接通：按一下講一句（舊行為保底）
      if (chatOn) { chatRec && chatRec.stop(); return; }
      startListening();
      return;
    }
    // 通話中：麥克風＝靜音開關
    micMuted = !micMuted;
    chatMic.classList.toggle('off', micMuted);
    if (micMuted) { try { chatRec && chatRec.stop(); } catch (e) {} setLocalizedRuntimeHint('microphoneMuted'); }
    else { setLocalizedCallHint('ready'); startListening(); }
  });

  // 陪伴角色：使用者命名與模板分離
  const companionNameInput = $('#companionNameInput');
  if (companionNameInput) {
    companionNameInput.addEventListener('input', e => setCompanionName(e.target.value, { skipBackend: true }));
    companionNameInput.addEventListener('blur', () => {
      if (!companionDisplayName.trim()) companionDisplayName = templateFor().defaultName;
      companionNameTouched = companionDisplayName.trim().length > 0;
      saveCompanionProfileToBackend();
      persistCompanionProfile();
      syncCompanionUI();
      saveCompanionProfileToBackend();
      syncAccountBootstrap('create', { reason: 'companion_name_updated' });
      toast(muneaT('companion.renamedToast', '名字改好了：以後叫「{name}」', { name: companionDisplayName.trim() }));
    });
  }
  const avatarPick = $('#avatarPick');
  if (avatarPick) avatarPick.addEventListener('click', e => {
    const o = e.target.closest('.avo:not(.soon)'); if (!o) return;
    const wasOn = o.classList.contains('on');
    setCompanionTemplate(o.dataset.ava);
    if (!wasOn) {
      const label = o.querySelector('.avl b');
      toast(muneaT('companion.switchedToast', '已換成 {name}', { name: label ? label.textContent : muneaT('companion.newDefault', '新的陪伴') }));
    }
  });

  if ('speechSynthesis' in window) speechSynthesis.onvoiceschanged = () => {};
}
document.addEventListener('DOMContentLoaded', init);
function refreshLocalizedDynamicUi() {
  if (document.readyState === 'loading') return;
  try { if (window.MuneaI18n) window.MuneaI18n.apply(); } catch (e) {}
  try { localizeLegacyStaticCopy(); } catch (e) {}
  try {
    const consentNote = $('#consentNote');
    if (consentNote) {
      // 急難號碼跟安全區走、不跟語言走：安全區接線前，中文＝台灣現行（119/1925 粗體），
      // 其他語言用區域安全政策的「聯絡當地緊急服務」通用句、不輸出台灣號碼。
      const zhSafety = (muneaLocale() || 'zh-TW').startsWith('zh');
      consentNote.innerHTML = muneaT('consent.custody', '資料由沐寧（Munea）保管，只在你使用期間保存；隨時可查詢、更正或要求刪除。沐寧是陪伴、不是緊急服務。')
        + (zhSafety ? '' : ' ')
        + muneaT('consent.emergency', '遇到急難請撥 {emergency}，想找人說說話可撥 {talkline}。', {
          emergency: zhSafety ? '<b>119</b>' : '',
          talkline: zhSafety ? '<b>1925</b>' : '',
        });
    }
  } catch (e) {}
  try {
    const cnameSpan = '<span class="cname">' + muneaT('companion.nening.name', '寧寧') + '</span>';
    const sf1 = $('#sfStep1Text');
    if (sf1) sf1.innerHTML = muneaT('legacyUi.safetyStep1', '異常發生，{companion}先關心你一句、確認你還好嗎', { companion: cnameSpan });
    const mcSubEl = $('#mcSub');
    if (mcSubEl && !mcSubEl.textContent.trim()) mcSubEl.innerHTML = muneaT('demo.family.chatSubSample', '今天聊了 2 次 · 有一小段有點火氣', { companion: cnameSpan });
    const cnNoData = $('#cnNoDataText');
    if (cnNoData) cnNoData.innerHTML = '<b>' + muneaT('legacyUi.connectNoDataTitle', '沒有這些也沒關係。') + '</b>' + muneaT('legacyUi.connectNoDataBody', '{companion}也能從每天聊天陪你留意生活狀態，健康數據是加分，陪伴和提醒不受影響。', { companion: cnameSpan });
    const rptFootEl = $('#rptFoot');
    if (rptFootEl) rptFootEl.innerHTML = muneaT('report.footerLine', '{companion}整理 · 家屬提供的紀錄，非醫療診斷', { companion: cnameSpan });
    const cnIntro = $('#cnHealthIntro');
    if (cnIntro) cnIntro.innerHTML = muneaT('settings.connectIntro', '連上 {appleHealth}，每次開啟沐寧時會同步步數、心跳、睡眠等資料；同步到需要留意的變化時會提醒你。這不是即時或醫療級監測。', { appleHealth: '<b>' + muneaT('settings.appleHealth', 'Apple 健康') + '</b>' });
    const interestsHint = $('#interestsPickHint');
    if (interestsHint) interestsHint.innerHTML = muneaT('interests.pickHint', '挑幾個有興趣的（最多 5 個），{companion}會幫你留意這些話題的新鮮事，聊起來更對味。之後隨時可以回來改。', { companion: cnameSpan });
  } catch (e) {}
  try { renderCareCarousel(); } catch (e) {}
  try { syncCompanionUI(); } catch (e) {}
  try { renderHomeGreeting(); } catch (e) {}
  try { refreshMoodTask(); } catch (e) {}
  try { updateMedCount(); } catch (e) {}
  try { renderDailyTasks(); } catch (e) {}
  try {
    const walk = document.querySelector('.task-item[data-task="walk"]');
    if (walk && walk.dataset.steps !== undefined) {
      renderWalkProgress(Number(walk.dataset.steps));
    }
  } catch (e) {}
  try { renderStatusCharts(true); } catch (e) {}
  try { if (window.__muneaAfterCircleSync) window.__muneaAfterCircleSync(); } catch (e) {}
  try { if (window.__muneaUpdateWalkLabels) window.__muneaUpdateWalkLabels(); } catch (e) {}
  try { applyAppVersion(); } catch (e) {}
  try { if (window.__muneaApplyFontScale) window.__muneaApplyFontScale(); } catch (e) {}
  try { if (window.__muneaRenderPlanState) window.__muneaRenderPlanState(); } catch (e) {}
  try { renderPointsPopupCopy(); } catch (e) {}
  try { updateAuthUI(); } catch (e) {}
  try { localizeAuthTerms(); } catch (e) {}
  try { applyTaskAccessibilityLabels(); } catch (e) {}
  try { localizeChatControls(); } catch (e) {}
  try { localizeMedicationSurfaces(); } catch (e) {}
  try { localizeCanonicalLegacyPanels(); } catch (e) {}
}
window.addEventListener('munea:locale-ready', refreshLocalizedDynamicUi);
window.addEventListener('munea:locale-change', () => {
  refreshLocalizedDynamicUi();
  voiceProvider.close();
  if (storageGet(ACCOUNT_BOOTSTRAP_KEY) === 'true') syncAccountBootstrap('update', { force: true, reason: 'locale_updated' });
});
// 撥號前暖機第一階段的兩個時機：開機（讓開機要緊的請求先跑、延後 2.5 秒）＋回前景
try { setTimeout(() => preDialConnWarm('boot'), 2500); } catch (e) {}
try {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') preDialConnWarm('resume');
  });
} catch (e) {}

/* ═══════════════════════════════════════════════════════════════════════════
   啟動頁與開場三頁（Edward 2026-08-10 拍板）
   需求單：docs/開場與啟動頁-需求單-2026-08-10.md

   啟動頁在 index.html 裡「預設就是顯示的」——不能等這支檔案跑完才蓋上去，
   不然使用者會先看到首頁閃一下。這裡只負責決定什麼時候收掉。
   保險絲寫在 index.html 的 inline script：萬一這段出錯，幾秒後也會自己收掉，App 不會被鎖死。

   ⚠ 刻意不重用 ONBOARDING_COMPLETED_KEY：那個記號是舊迎賓精靈留下的，
   現在還被拿來決定要不要跑帳號初始化（app_init 那段）。把它的意思改掉會動到通話路徑，
   所以開場三頁自己用一個新記號。
   ═══════════════════════════════════════════════════════════════════════════ */
const ONBOARDING_INTRO_SEEN_KEY = 'munea.onboardingIntroSeen.v1';
const ONBOARDING_INTRO_PAGES = 3;

function onboardingIntroSeen() {
  return storageGet(ONBOARDING_INTRO_SEEN_KEY) === 'true';
}

function openOnboardingIntro() {
  const root = $('#onboarding');
  const track = $('#onbTrack');
  const nextBtn = $('#onbNext');
  const startBtn = $('#onbStart');
  const dots = $('#onbDots');
  if (!root || !track || !nextBtn || !startBtn || !dots) return;
  root.hidden = false;
  let index = 0;

  // 兩顆按鈕輪流出現、不是一顆按鈕換字——句子留在畫面檔各自綁鍵，這裡只決定誰顯示
  function syncControls() {
    Array.prototype.forEach.call(dots.children, (dot, i) => dot.classList.toggle('on', i === index));
    const last = index === ONBOARDING_INTRO_PAGES - 1;
    nextBtn.hidden = last;
    startBtn.hidden = !last;
  }

  track.addEventListener('scroll', () => {
    const width = track.clientWidth || 1;
    const moved = Math.round(track.scrollLeft / width);
    if (moved !== index && moved >= 0 && moved < ONBOARDING_INTRO_PAGES) {
      index = moved;
      syncControls();
    }
  }, { passive: true });

  nextBtn.addEventListener('click', () => {
    if (index >= ONBOARDING_INTRO_PAGES - 1) return;
    track.scrollTo({ left: (index + 1) * track.clientWidth, behavior: 'smooth' });
  });

  startBtn.addEventListener('click', () => {
    // 三頁全部看完才算看過；中途關掉的話下次重看，不然有人會漏掉整段介紹
    storageSet(ONBOARDING_INTRO_SEEN_KEY, 'true');
    root.hidden = true;
  });

  syncControls();
}

function runBootSplash() {
  const splash = $('#bootSplash');
  if (!splash || splash.hidden) return;
  const needIntro = !onboardingIntroSeen();
  // 第一次要接開場三頁，播久一點；平常只要蓋住載入那一兩秒就好
  const hold = needIntro ? 2400 : 1600;
  window.setTimeout(() => {
    // 開場頁要在啟動頁「開始淡出之前」就鋪好。
    // 原本是等淡出跑完 500ms 才顯示——那半秒底下露出來的是 App 首頁，
    // 使用者看到的就是「啟動頁 → 閃一下首頁 → 開場頁」（Edward 2026-08-10 真機回報）。
    // 配套：.boot-splash 的層級要比 .onb 高一階，否則排在後面的開場頁會直接蓋掉
    // 還在淡出的啟動頁，動畫等於沒播。
    if (needIntro) openOnboardingIntro();
    splash.classList.add('is-leaving');
    window.setTimeout(() => {
      splash.hidden = true;
    }, 500);
  }, hold);
}

document.addEventListener('DOMContentLoaded', runBootSplash);
