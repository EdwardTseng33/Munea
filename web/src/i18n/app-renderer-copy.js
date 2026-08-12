(function (root, factory) {
  'use strict';

  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MuneaAppRendererCopy = Object.freeze({ ...api });
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const PLAN_RANK = Object.freeze({ free: 0, plus: 1, pro: 2 });
  const PLAN_KEYS = Object.freeze({
    free: 'subscription.planFree',
    plus: 'subscription.planPlus',
    pro: 'subscription.planPro',
  });
  const CALL_HINT_KEYS = Object.freeze({
    connected: 'voice.call.connected',
    connecting: 'voice.connecting',
    developerConnecting: 'voice.call.developerConnecting',
    developerReady: 'voice.call.developerReady',
    fallback: 'voice.fallback',
    firstWarmup: 'voice.call.firstWarmup',
    idleEnded: 'voice.call.idleEnded',
    openingWarmup: 'voice.call.openingWarmup',
    ready: 'voice.ready',
    speaking: 'voice.call.speaking',
    unavailable: 'voice.call.unavailable',
  });
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
  const VOICE_RUNTIME_CAPTION_KEYS = Object.freeze({
    degraded: Object.freeze({
      body: VOICE_RUNTIME_KEYS.degradedBody,
      title: VOICE_RUNTIME_KEYS.degradedTitle,
    }),
    recovered: Object.freeze({
      body: VOICE_RUNTIME_KEYS.recoveredBody,
      title: VOICE_RUNTIME_KEYS.recoveredTitle,
    }),
  });
  const CALL_STATUS_KEYS = Object.freeze({
    accountPreparing: Object.freeze({
      title: 'voice.call.accountPreparingTitle',
      note: 'voice.call.accountPreparingNote',
    }),
    activationPending: Object.freeze({
      title: 'voice.call.activationPendingTitle',
      note: 'voice.call.retryLater',
    }),
    authExpired: Object.freeze({
      title: 'voice.call.authExpiredTitle',
      note: 'voice.call.authExpiredNote',
      button: 'auth.signInAgain',
      action: 'reopen-auth',
    }),
    disconnected: Object.freeze({
      title: 'voice.call.disconnectedTitle',
      note: 'voice.call.disconnectedNote',
    }),
    microphoneHttps: Object.freeze({
      title: 'voice.call.microphoneHttpsTitle',
      note: 'voice.call.microphoneHttpsNote',
    }),
    microphonePermission: Object.freeze({
      title: 'voice.call.microphonePermissionTitle',
      note: 'voice.call.microphonePermissionNote',
    }),
    readinessPending: Object.freeze({
      title: 'voice.call.readinessPendingTitle',
      note: 'voice.call.readinessPendingNote',
    }),
    serviceBusy: Object.freeze({
      title: 'voice.call.unavailable',
      note: 'voice.call.serviceBusyNote',
    }),
    serviceUpdating: Object.freeze({
      title: 'voice.call.serviceUpdatingTitle',
      note: 'voice.call.serviceUpdatingNote',
    }),
    unavailable: Object.freeze({
      title: 'voice.call.unavailable',
      note: 'voice.call.retryLater',
    }),
  });
  const AUTH_MESSAGE_KEYS = Object.freeze({
    cancelled: 'auth.cancelled',
    inProgress: 'auth.inProgress',
    unavailable: 'auth.unavailable',
  });

  function positiveInteger(value, fallback = 1) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? Math.ceil(number) : fallback;
  }

  function planId(value) {
    const normalized = String(value || '').toLowerCase();
    return Object.prototype.hasOwnProperty.call(PLAN_KEYS, normalized) ? normalized : 'plus';
  }

  function createAppRendererCopy(options) {
    const config = options || {};
    if (typeof config.t !== 'function') {
      throw new TypeError('App renderer copy requires an i18n translator');
    }
    const t = config.t;

    function planLabel(value) {
      return t(PLAN_KEYS[planId(value)]);
    }

    function queueEta({ etaSeconds, preparing }) {
      const seconds = Number(etaSeconds);
      if (Number.isFinite(seconds) && seconds > 0 && seconds < 90) {
        return t(
          preparing
            ? 'voice.queue.etaPreparingSoon'
            : 'voice.queue.etaWaitingSoon',
        );
      }
      if (Number.isFinite(seconds) && seconds >= 90 && seconds <= 600) {
        return t(
          preparing
            ? 'voice.queue.etaPreparingMinutes'
            : 'voice.queue.etaWaitingMinutes',
          { minutes: Math.ceil(seconds / 60) },
        );
      }
      return t(
        preparing
          ? 'voice.queue.etaPreparingUnknown'
          : 'voice.queue.etaWaitingUnknown',
      );
    }

    function queueCard(input) {
      const value = input || {};
      const companion = String(value.companion || '').trim();
      if (value.mode === 'full') {
        return Object.freeze({
          action: 'dismiss',
          button: t('common.okay'),
          note: t('voice.queue.fullBody', { companion }),
          position: '',
          showTextFallback: true,
          title: t('voice.queue.fullTitle'),
        });
      }
      const position = positiveInteger(value.position);
      const preparing = position <= 1;
      const eta = queueEta({ etaSeconds: value.etaSeconds, preparing });
      return Object.freeze({
        action: 'cancel',
        button: t('voice.queue.cancel'),
        note: t('voice.queue.note', { eta }),
        position: preparing ? '' : t('voice.queue.position', { count: position }),
        showTextFallback: false,
        title: t(
          preparing
            ? 'voice.queue.preparingWithCompanion'
            : 'voice.queue.busyWithCompanion',
          { companion },
        ),
      });
    }

    function callHint(state) {
      return t(CALL_HINT_KEYS[state] || CALL_HINT_KEYS.unavailable);
    }

    function voiceRuntimeText(state) {
      return t(VOICE_RUNTIME_KEYS[state] || VOICE_RUNTIME_KEYS.reconnecting);
    }

    function voiceRuntimeCaption(state) {
      const keys = VOICE_RUNTIME_CAPTION_KEYS[state] || VOICE_RUNTIME_CAPTION_KEYS.degraded;
      return Object.freeze({
        body: t(keys.body),
        title: t(keys.title),
      });
    }

    function callStatus(state) {
      const keys = CALL_STATUS_KEYS[state] || CALL_STATUS_KEYS.unavailable;
      return Object.freeze({
        action: keys.action || 'dismiss',
        button: t(keys.button || 'common.okay'),
        note: t(keys.note),
        title: t(keys.title),
      });
    }

    function authMessage(state) {
      if (!state || state === 'idle') return '';
      return t(AUTH_MESSAGE_KEYS[state] || AUTH_MESSAGE_KEYS.unavailable);
    }

    function purchaseButton(input) {
      const value = input || {};
      if (value.state === 'loading') return t('purchase.loadingProducts');
      if (value.state === 'unavailable') return t('purchase.storeUnavailable');
      return t('purchase.buyCredits', {
        credits: positiveInteger(value.credits),
        price: String(value.price || '').trim(),
      });
    }

    function planName(value) {
      return t('settings.planName', { plan: planLabel(value) });
    }

    function subscriptionCta(input) {
      const value = input || {};
      const currentPlan = planId(value.currentPlan);
      const selectedPlan = planId(value.selectedPlan);
      const selectedLabel = planLabel(selectedPlan);
      if (currentPlan === selectedPlan) {
        return t('subscription.currentPlanCta', { plan: selectedLabel });
      }
      return t(
        PLAN_RANK[selectedPlan] > PLAN_RANK[currentPlan]
          ? 'subscription.upgradeTo'
          : 'subscription.changeTo',
        {
          plan: selectedLabel,
          price: String(value.price || '').trim(),
        },
      );
    }

    function planConfirmation(input) {
      const value = input || {};
      const label = planLabel(value.plan);
      const price = String(value.price || '').trim();
      return Object.freeze({
        action: t('subscription.confirmAction'),
        body: t('subscription.confirmBody'),
        cancel: t('subscription.cancel'),
        facts: t('subscription.confirmFacts', {
          credits: positiveInteger(value.credits),
          members: positiveInteger(value.members),
        }),
        title: t('subscription.confirmTitle', { plan: label, price }),
      });
    }

    function planSummary(input) {
      const value = input || {};
      const plan = planId(value.plan);
      // 免費方案的說明句要講「手上還剩多少點」（伺服器錢包），不是「歷史買過多少點」。
      // 舊參數 purchasedCredits 讀的是本機累計購買數，只增不減：餘額 193 卻寫「還有 500 點沒用完」。
      // 舊名留著相容，但新呼叫端一律傳 remainingCredits。
      const remainingCredits = Math.max(0, Number(
        value.remainingCredits === undefined ? value.purchasedCredits : value.remainingCredits,
      ) || 0);
      let noteKey = 'subscription.monthlyCreditsNote';
      let noteValues = {
        credits: positiveInteger(value.monthlyCredits),
        minutes: positiveInteger(value.minutes || value.monthlyCredits),
      };
      if (plan === 'free' && remainingCredits > 0) {
        noteKey = 'subscription.freeCreditsLeft';
        noteValues = { credits: remainingCredits };
      } else if (plan === 'free') {
        noteKey = 'subscription.freePlanNote';
        noteValues = {};
      }
      return Object.freeze({
        manageLabel: t(plan === 'free' ? 'settings.upgradePlan' : 'settings.managePlan'),
        name: planName(plan),
        note: t(noteKey, noteValues),
      });
    }

    function profilePrompt() {
      return Object.freeze({
        action: t('home.profilePromptAction'),
        body: t('home.profilePromptBody'),
        title: t('home.profilePromptTitle'),
      });
    }

    function careLabels() {
      return Object.freeze({
        acknowledge: t('home.care.acknowledge'),
        open: t('home.care.open'),
        remove: t('home.care.remove'),
        report: t('home.care.report'),
      });
    }

    function familyRelay(input) {
      const value = input || {};
      const from = String(value.from || '').trim();
      return Object.freeze({
        body: String(value.body || '').trim() || t('home.care.demoRelay', {
          companion: String(value.companion || '').trim(),
        }),
        title: from
          ? t('home.care.familyRelayFrom', { name: from })
          : t('home.care.familyRelayTitle'),
      });
    }

    function walkActivity(input) {
      const value = input || {};
      const owner = String(value.owner || '').trim() || t('home.care.familyFallback');
      const gap = Math.max(0, Number(value.gap) || 0);
      return Object.freeze({
        body: gap > 0
          ? t('home.care.walkGap', { count: Math.ceil(gap) })
          : t('home.care.walkComplete'),
        title: t('home.care.walkTitle', { name: owner }),
      });
    }

    function familyActivity(input) {
      const value = input || {};
      const owner = String(value.owner || '').trim() || t('home.care.familyFallback');
      const title = String(value.title || '').trim() || t('home.care.activityFallback');
      return Object.freeze({
        body: t('home.care.activityProgress', { title }),
        title: t('home.care.activityTitle', { name: owner }),
      });
    }

    function upcomingVisit(input) {
      const value = input || {};
      const title = String(value.title || '').trim() || t('home.care.visitFallback');
      return Object.freeze({
        body: t('home.care.visitNote', {
          companion: String(value.companion || '').trim(),
          date: String(value.date || '').trim(),
        }),
        title: t('home.care.visitSoon', { title }),
      });
    }

    return Object.freeze({
      authMessage,
      callHint,
      callStatus,
      careLabels,
      familyActivity,
      familyRelay,
      planConfirmation,
      planLabel,
      planName,
      planSummary,
      profilePrompt,
      purchaseButton,
      queueCard,
      subscriptionCta,
      upcomingVisit,
      voiceRuntimeCaption,
      voiceRuntimeText,
      walkActivity,
    });
  }

  return Object.freeze({
    createAppRendererCopy,
  });
}));
