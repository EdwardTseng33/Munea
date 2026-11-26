package net.munea.app.remindertest;

import static org.junit.Assert.assertTrue;

import androidx.test.ext.junit.runners.AndroidJUnit4;

import org.junit.FixMethodOrder;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.MethodSorters;

import java.util.ArrayList;
import java.util.List;

/**
 * 補助案 B2 剩下三個流程，真機版：1 登入 → 2 聊聊通話 → 3 家人圈。依檔名順序跑（共用同一個 App 登入狀態）。
 * 帳密不寫死、不進 GitHub：從 gcloud --environment-variables qaEmail=...,qaPassword=... 傳進
 * （InstrumentationRegistry.getArguments()），測試只用不印（記錄裡信箱只留前兩字）。
 * 參數：qaEmail、qaPassword；fakeSession=1（只給模擬器驗畫面流程：用本機假證，不碰任何帳密）；
 *      callSeconds（接通後講多久才掛，預設 40）；inviteOnModel（機型名含這串才產生邀請碼，預設 Pixel 8；空白＝都不產生）。
 * 機房手機沒有人講話：只驗「接通＋AI 有出聲＋有字幕」，不驗對話內容。
 */
@RunWith(AndroidJUnit4.class)
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class LoginChatFamilyTest {
    private static QaKit kit;
    private static boolean appReady = false;
    private static boolean loggedIn = false;
    private final List<String> failures = new ArrayList<>();

    private static QaKit kit() {
        if (kit == null) kit = new QaKit();
        return kit;
    }

    private void step(String name, boolean ok, String detail) {
        kit().log((ok ? "PASS " : "FAIL ") + name + " | " + detail);
        if (!ok) failures.add(name);
    }

    private void finish() {
        assertTrue("沒過的步驟：" + failures, failures.isEmpty());
    }

    /** 點底部分頁（view = home／status／chat／family／settings）。 */
    private void tab(String view) {
        kit().evalJs("var b=document.querySelector('.tab-btn[data-view=" + view + "]'); if(b) b.click(); return !!b", 10);
    }

    @Test
    public void test1_login() {
        QaKit k = kit();
        boolean fake = "1".equals(k.args("fakeSession", "0"));
        String email = k.args("qaEmail", "");
        String password = k.args("qaPassword", "");
        k.log("DEVICE " + k.sh("getprop ro.product.manufacturer").trim() + " " + k.sh("getprop ro.product.model").trim()
                + " Android " + k.sh("getprop ro.build.version.release").trim() + " fakeSession=" + fake);
        if (!fake && (email.isEmpty() || password.isEmpty())) {
            step("取得測試帳密參數", false, "缺 qaEmail／qaPassword（用 --environment-variables 傳入）；不繼續");
            finish();
            return;
        }
        appReady = k.prepareApp();
        step("App 起來、跳過開場介紹", appReady, "");
        if (!appReady) { finish(); return; }
        k.shot("L00-launch");

        String devOn = "window.MUNEA_DEV_CONFIG=Object.assign({},window.MUNEA_DEV_CONFIG||{},{enabled:true,analyticsExcluded:true});";
        String signIn;
        if (fake) {
            signIn = k.evalJs(devOn + "var r=await MuneaAuth.signInAsDeveloper(); return {ok:!!r.ok, fake:true, status:MuneaAuth.state().status};", 30);
        } else {
            signIn = k.evalJs(devOn
                    + "var r=await MuneaAuth.signInWithTestAccount({email:" + QaKit.jsQuote(email) + ",password:" + QaKit.jsQuote(password) + "});"
                    + "var s=MuneaAuth.state(); var tok=(r&&r.session&&r.session.access_token)||'';"
                    + "return {ok:!!r.ok, errCode:(r.error&&r.error.code)||null, status:s.status, provider:s.provider, hasUserId:!!s.userId,"
                    + " devLocalToken: tok.indexOf('dev-local')===0, developerSession: !!(r.session&&r.session.developer), tokenLooksReal: tok.split('.').length===3};", 60);
        }
        k.log("LOGIN-RESULT " + signIn);
        boolean ok = signIn.contains("\"ok\":true") && signIn.contains("\"status\":\"signed-in\"");
        if (!fake) ok = ok && signIn.contains("\"devLocalToken\":false") && signIn.contains("\"developerSession\":false") && signIn.contains("\"tokenLooksReal\":true");
        step("登入（正式 Supabase 密碼登入，拿到真 session，不是 dev-local 假證）", ok, fake ? "假證模式" : "細節在 LOGIN-RESULT");
        loggedIn = ok;
        if (!ok) { k.shot("L01-login-failed"); finish(); return; }

        QaKit.sleep(4000);
        k.shot("L01-after-login");
        String home = k.evalJs("var s=document.querySelector('.screen.active'); var g=document.querySelector('.tab-btn.active');"
                + "return {screen:s?s.id:null, tab:(g&&g.dataset)?g.dataset.view:null, tabBarVisible: !!document.querySelector('.tab-btn')};", 15);
        step("登入後進到 App 首頁", home.contains("\"screen\":\"home\"") || home.contains("\"tab\":\"home\""), home);

        tab("settings");
        QaKit.sleep(2500);
        k.shot("L02-settings");
        String acct = k.evalJs("var st=MuneaAuth.state(); var n=document.getElementById('setPlanName'); var p=document.getElementById('ptsLeft'); var em=st.email||'';"
                + "return {name:st.name||null, emailMasked:em.slice(0,2)+'***'+em.slice(em.indexOf('@')), plan:n?(n.textContent||'').trim():null, pointsLeft:p?(p.textContent||'').trim():null};", 15);
        k.log("ACCOUNT " + acct);
        step("設定頁顯示帳號與方案", acct.contains("\"plan\":\"") && !acct.contains("\"plan\":\"\""), acct);
        tab("home");
        finish();
    }

    private static final String POLL_JS = "var d=window.MuneaVoiceDiagnostics&&MuneaVoiceDiagnostics.current();"
            + "if(!d){var h=window.MuneaVoiceDiagnostics&&MuneaVoiceDiagnostics.history&&MuneaVoiceDiagnostics.history(); d=(h&&h.length)?h[h.length-1]:null;}"
            + "var cs=document.getElementById('consentSheet'), im=document.getElementById('interestsModal'), lb=document.getElementById('callToggleLabel');"
            + "return {consent:!!cs&&cs.classList.contains('show'), topics:!!im&&im.classList.contains('show'), outcome:d?d.outcome:null,"
            + " failed:d?d.firstFailedStage:null, last:d?d.lastSuccessfulStage:null, label:lb?(lb.textContent||'').trim():null,"
            + " stages:d?d.stages.map(function(s){return s.stage+':'+s.status+'@'+s.elapsedMs}):[]};";

    @Test
    public void test2_chat() {
        QaKit k = kit();
        if (!appReady || !loggedIn) {
            step("聊聊（需先登入成功）", false, "登入沒成功，這段不跑");
            finish();
            return;
        }
        int callSeconds = k.argsInt("callSeconds", 40);
        tab("chat");
        QaKit.sleep(2500);
        k.shot("C00-chat-tab");
        k.evalJs("var b=document.getElementById('callToggle'); if(b) b.click(); return !!b", 10);
        long t0 = System.currentTimeMillis();
        String state = "";
        boolean connected = false, audio = false, caption = false, sawConsent = false, sawTopics = false;
        while (System.currentTimeMillis() - t0 < 150000) {
            k.allowPermissionDialog();
            state = k.evalJs(POLL_JS, 15);
            if (state.contains("\"consent\":true")) {
                sawConsent = true;
                QaKit.sleep(2500);
                k.shot("C01-consent-sheet");
                k.evalJs("var b=document.getElementById('consentAgree'); if(b) b.click(); return !!b", 10);
                t0 = System.currentTimeMillis();
                continue;
            }
            if (state.contains("\"topics\":true")) {
                sawTopics = true;
                QaKit.sleep(2500);
                k.shot("C02-topics-sheet");
                k.evalJs("var b=document.getElementById('interestsSave'); if(b) b.click(); return !!b", 10);
                t0 = System.currentTimeMillis();
                continue;
            }
            connected = state.contains("call_connected:pass");
            audio = state.contains("voice_first_audio:pass");
            caption = state.contains("assistant_first_caption:pass");
            if (connected && audio) break;
            if (state.contains("\"outcome\":\"failed\"") || state.contains("\"outcome\":\"abandoned\"")) break;
            QaKit.sleep(2000);
        }
        k.log("CALL-STATE " + state);
        k.log("CALL-SHEETS consent=" + sawConsent + " topics=" + sawTopics);
        k.shot("C03-after-dial");
        step("撥號鏈接通（call_connected）", connected, state.length() > 600 ? state.substring(0, 600) : state);
        step("寧寧開口（voice_first_audio，AI 有出聲）", audio, "assistantCaption=" + caption);
        if (connected) {
            QaKit.sleep(callSeconds * 1000L);
            String mid = k.evalJs(POLL_JS, 15);
            k.shot("C04-call-" + callSeconds + "s");
            k.log("CALL-AFTER-" + callSeconds + "s " + mid);
            step("通話持續 " + callSeconds + " 秒沒掉線", !mid.contains("\"outcome\":\"failed\"") && !mid.contains("\"outcome\":\"abandoned\""), "");
            step("有字幕（assistant_first_caption）", mid.contains("assistant_first_caption:pass"), "");
        }
        // 掛斷：沒在通話中時點這顆會變成「撥號」，所以只在通話還在進行時才點
        k.evalJs("var b=document.getElementById('callToggle'); var live=!!b&&(b.classList.contains('end')||b.classList.contains('dialing')); if(live) b.click(); return live", 10);
        QaKit.sleep(4000);
        String end = k.evalJs(POLL_JS, 15);
        k.shot("C05-after-hangup");
        k.log("CALL-ENDED " + end);
        finish();
    }

    @Test
    public void test3_family() {
        QaKit k = kit();
        if (!appReady || !loggedIn) {
            step("家人圈（需先登入成功）", false, "登入沒成功，這段不跑");
            finish();
            return;
        }
        tab("family");
        QaKit.sleep(4000);
        k.shot("F00-family-tab");
        String fam = k.evalJs("var s=document.querySelector('.screen.active'); var items=document.querySelectorAll('.fam-switch-item');"
                + "return {screen:s?s.id:null, people:items.length};", 15);
        step("家人頁打得開", fam.contains("\"screen\":\"family\""), fam);

        tab("settings");
        QaKit.sleep(1500);
        String opened = k.evalJs("var r=document.getElementById('famCircleRow'); if(!r) return false; r.click(); await new Promise(function(x){setTimeout(x,3000)});"
                + "var m=document.getElementById('famCircleModal'); return !!m&&m.classList.contains('show');", 20);
        k.shot("F01-family-circle");
        step("全家健康圈視窗打得開", "true".equals(opened), opened);

        String only = k.args("inviteOnModel", "Pixel 8");
        String model = k.sh("getprop ro.product.model").trim();
        if (!only.isEmpty() && model.contains(only)) {
            String inv = k.evalJs("var b=document.getElementById('fcInviteBtn'); if(!b) return {clicked:false}; b.click();"
                    + "var code=''; for(var i=0;i<30;i++){await new Promise(function(x){setTimeout(x,1000)}); var c=document.getElementById('invCode'); code=c?(c.textContent||'').trim():''; if(code.indexOf('MUNEA-')===0) break;}"
                    + "var n=document.getElementById('invTempNote');"
                    + "return {clicked:true, gotCode: code.indexOf('MUNEA-')===0 && code.length===12, note:(n&&n.style.display!=='none')?(n.textContent||'').trim():null};", 60);
            k.shot("F02-invite-code");
            k.log("INVITE " + inv + " (code itself not logged; invite expires in 72h, the App has no revoke)");
            step("產生邀請碼（只在 " + only + " 做一次）", inv.contains("\"gotCode\":true"), inv);
        } else {
            k.log("SKIP 產生邀請碼：本機型 " + model + " 不是 inviteOnModel=" + only);
        }
        k.log("NOTE 另一人加入要第二個帳號，這次沒做");
        finish();
    }
}
