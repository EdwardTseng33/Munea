package net.munea.app.remindertest;

import static org.junit.Assert.assertTrue;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.BySelector;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.Until;

import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 補助案 B2「提醒」流程，真機版：
 * 開 App → 跳過開場介紹 → App 說明卡「好，開通知」→ 系統視窗「允許」→ 排一則約 2.5 分鐘後的用藥提醒
 * → 回桌面、結束 App 行程（不是強制停止）→ 等通知出現 → 拉下通知列 → 點通知 → 確認開到用藥頁。
 * 每一步照實記錄，某步沒過不會硬讓它過；後面還能做的照做。重開機在 Test Lab 做不到，不測。
 * 不登入、不讀任何帳密。
 */
@RunWith(AndroidJUnit4.class)
public class ReminderFlowTest {
    private final QaKit kit = new QaKit();
    private final List<String> failures = new ArrayList<>();

    private void step(String name, boolean ok, String detail) {
        kit.log((ok ? "PASS " : "FAIL ") + name + " | " + detail);
        if (!ok) failures.add(name);
    }

    private void finish() {
        assertTrue("沒過的步驟：" + failures, failures.isEmpty());
    }

    private static int parseInt(String s) {
        try { return Integer.parseInt(s.trim()); } catch (Exception e) { return 0; }
    }

    private static long extractLong(String json, String key) {
        Matcher m = Pattern.compile("\"" + key + "\"\\s*:\\s*(\\d+)").matcher(json);
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    private static String schedJs(int aheadSec) {
        return "var now=new Date(); var target=new Date(now.getTime()+" + aheadSec + "*1000); target.setSeconds(0,0);"
            + "if(target.getTime()-now.getTime()<90000) target.setMinutes(target.getMinutes()+1);"
            + "var meal=new Date(target.getTime()-30*60000);"
            + "function hhmm(d){return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')}"
            + "localStorage.setItem('munea.meds',JSON.stringify([{id:'qa-med',name:'QA 測試藥',time:'早餐後'}]));"
            + "localStorage.setItem('munea.routine',JSON.stringify(Object.assign(JSON.parse(localStorage.getItem('munea.routine')||'{}'),{b:hhmm(meal)})));"
            + "MuneaNotify.sync(); await new Promise(function(r){setTimeout(r,4000)});"
            + "var p=await Capacitor.Plugins.LocalNotifications.getPending();"
            + "var ours=(p.notifications||[]).filter(function(n){return n.extra&&n.extra.source==='munea.local'});"
            + "var t=ours.map(function(n){return new Date(n.schedule.at).getTime()}).sort(function(a,b){return a-b});"
            + "return {targetEpoch:Math.round(target.getTime()/1000), pendingCount:ours.length, earliest:t.length?new Date(t[0]).toString():null};";
    }

    @Test
    public void reminderFiresWhenAppIsClosedAndOpensMedicationPage() throws Exception {
        int aheadSec = kit.argsInt("scheduleAheadSeconds", 150);
        int maxWaitSec = kit.argsInt("maxWaitAfterTargetSeconds", 300);
        kit.log("DEVICE " + kit.sh("getprop ro.product.manufacturer").trim() + " " + kit.sh("getprop ro.product.model").trim()
                + " Android " + kit.sh("getprop ro.build.version.release").trim() + " (API " + kit.sh("getprop ro.build.version.sdk").trim()
                + ") locale=" + kit.sh("getprop persist.sys.locale").trim() + "/" + kit.sh("getprop ro.product.locale").trim());

        // 1. 開 App
        kit.device.wakeUp();
        // 一開始就鎖成直向（真機實測 Test Lab 手機會是橫的，導覽頁標題被切）
        kit.device.setOrientationNatural();
        kit.device.freezeRotation();
        kit.log("SCREEN " + kit.device.getDisplayWidth() + "x" + kit.device.getDisplayHeight() + " rotation=" + kit.device.getDisplayRotation());
        kit.device.pressHome();
        kit.sh("monkey -p " + QaKit.PKG + " -c android.intent.category.LAUNCHER 1");
        boolean front = kit.device.wait(Until.hasObject(By.pkg(QaKit.PKG).depth(0)), 40000);
        boolean bridge = front && kit.waitBridge(60);
        kit.shot("00-launch");
        String state = bridge ? kit.evalJs("return ({platform: Capacitor.getPlatform(), available: MuneaNotify.available(), permission: await Capacitor.Plugins.LocalNotifications.checkPermissions()})", 15) : "front=" + front;
        step("App 起來、提醒橋接上", bridge, state);
        if (!bridge) { finish(); return; }

        // 2. 跳過開場介紹（真人是看完介紹才會遇到說明卡）。
        // 真機慢：啟動頁約 2.4 秒後才把開場三頁鋪出來，太早設旗標會被蓋回去。
        // 做法：等啟動頁收掉 → 設旗標＋直接按「開始」＋關掉 → 隔 3 秒再確認一次；多次嘗試仍在就立刻 FAIL。
        boolean introGone = false;
        String introState = "";
        long introEnd = System.currentTimeMillis() + 40000;
        while (System.currentTimeMillis() < introEnd) {
            String sp = kit.evalJs("var sp=document.getElementById('bootSplash'); return !sp || sp.hidden", 10);
            if ("true".equals(sp)) break;
            QaKit.sleep(1000);
        }
        for (int attempt = 1; attempt <= 3 && !introGone; attempt++) {
            kit.evalJs("localStorage.setItem('munea.onboardingIntroSeen.v1','true'); var s=document.getElementById('onbStart'); if(s) s.click(); var i=document.getElementById('onboarding'); if(i) i.hidden=true; return true", 10);
            QaKit.sleep(3000);
            introState = kit.evalJs("var o=document.getElementById('onboarding'); return {introVisible: !!o && !o.hidden, seen: localStorage.getItem('munea.onboardingIntroSeen.v1')}", 10);
            introGone = introState.contains("\"introVisible\":false");
        }
        kit.shot("01-home");
        step("跳過開場介紹", introGone, introState);
        if (!introGone) { finish(); return; }
        kit.shot("01-home");

        // 3. App 說明卡
        String card = kit.evalJs("localStorage.removeItem('munea.notification.askInContext.medication'); MuneaNotify.askInContext('medication'); await new Promise(function(r){setTimeout(r,1500)}); return !!document.querySelector('#pushAskModal.show')", 15);
        kit.shot("02-ask-card");
        UiObject2 accept = kit.device.wait(Until.findObject(By.text(Pattern.compile("^(好，開通知|Yes, turn on|はい、オンにする|Sí, activar)$"))), 6000);
        boolean accepted;
        if (accept != null) { accept.click(); accepted = true; }
        else accepted = "true".equals(kit.evalJs("var b=document.getElementById('pushAskAccept'); if(!b) return false; b.click(); return true", 10));
        step("App 說明卡出現並按「好，開通知」", ("true".equals(card) && accepted) || state.contains("granted\"}"), "card=" + card + " clickedByUiAutomator=" + (accept != null));

        // 4. 系統通知權限視窗（各牌 resource-id／文字不同，兩種都比對；Android 13 以下沒有這個視窗）
        QaKit.sleep(2500);
        kit.shot("03-system-permission");
        BySelector allowRes = By.res(Pattern.compile(".*:id/(permission_allow_button|permission_allow_foreground_only_button|permission_allow_one_time_button|btn_allow.*)"));
        BySelector allowTxt = By.text(Pattern.compile("(?i)^(Allow|允許|允许|許可|许可|허용|許可する|Permitir|Erlauben|Autoriser)$"));
        UiObject2 allow = kit.device.wait(Until.findObject(allowRes), 8000);
        if (allow == null) allow = kit.device.findObject(allowTxt);
        boolean sdk33 = parseInt(kit.sh("getprop ro.build.version.sdk")) >= 33;
        boolean preGranted = state.contains("\"display\":\"granted\"");
        boolean allowed = false;
        String how = "none";
        if (allow != null) { how = "res=" + allow.getResourceName() + " text=" + allow.getText(); allow.click(); allowed = true; }
        step("Android 系統問通知權限並點「允許」", allowed || !sdk33 || preGranted, preGranted ? "Test Lab 預設已把通知權限給了，不會跳系統視窗（走已授權分支）" : (sdk33 ? how : "Android 13 以下沒有這個視窗"));
        QaKit.sleep(3000);
        String perm = kit.evalJs("return ({permission: await MuneaNotify.permissionStatus(), settings: JSON.parse(localStorage.getItem('munea.notification.settings.v1')||'null')})", 15);
        step("權限結果", perm.contains("\"granted\":true") && perm.contains("\"pushEnabled\":true"), perm);
        kit.shot("04-after-permission");

        // 5. 排提醒：早餐後的藥，早餐時間調成「目標時間 - 30 分」，走 notify.js 平常的排程
        String sched = kit.evalJs(schedJs(aheadSec), 40);
        long target = extractLong(sched, "targetEpoch");
        int pending = (int) extractLong(sched, "pendingCount");
        step("排程：展開成未來 14 天", target > 0 && pending >= 10, sched);
        if (target <= 0 || pending == 0) {
            kit.shot("05-schedule-EMPTY");
            kit.log("HINT 排程是空的，不等了：notificationSettings=" + kit.evalJs("return localStorage.getItem('munea.notification.settings.v1')", 10)
                    + " onboardingVisible=" + kit.evalJs("var o=document.getElementById('onboarding'); return !!o && !o.hidden", 10));
            finish();
            return;
        }

        // 6. 回桌面、結束 App 行程（等同滑掉／被系統回收；不用 force-stop，那會連鬧鐘一起清）
        kit.device.pressHome();
        QaKit.sleep(2000);
        kit.sh("am kill " + QaKit.PKG);
        QaKit.sleep(3000);
        String pid = kit.pidOfApp();
        String killedBy = "am kill";
        if (!pid.isEmpty()) {
            kit.sh("run-as " + QaKit.PKG + " kill -9 " + pid);
            killedBy = "run-as kill -9";
            QaKit.sleep(3000);
            pid = kit.pidOfApp();
        }
        step("關掉 App 行程（不是強制停止）", pid.isEmpty(), pid.isEmpty() ? "pidof 查不到 App（" + killedBy + "）" : "仍在跑 pid=" + pid);
        kit.shot("05-home-app-closed");

        // 7. 等通知出現
        long seen = -1;
        long deadline = target + maxWaitSec;
        while (target > 0) {
            String dump = kit.sh("dumpsys notification --noredact");
            if (dump.contains("pkg=" + QaKit.PKG) && dump.contains("munea-reminders")) { seen = kit.deviceNowSec(); break; }
            if (kit.deviceNowSec() >= deadline) break;
            QaKit.sleep(5000);
        }
        if (seen < 0) {
            kit.shot("06-notification-NOTFOUND");
            kit.log("HINT 省電白名單：" + kit.sh("dumpsys deviceidle whitelist").replace('\n', ' ').trim());
            kit.log("HINT 待機分類：" + kit.sh("am get-standby-bucket " + QaKit.PKG).trim());
            kit.log("HINT 鬧鐘裡有沐寧：" + kit.sh("dumpsys alarm").contains(QaKit.PKG));
            step("App 關著，提醒時間到→通知跳出", false, "預定時間後 " + maxWaitSec + " 秒內沒看到通知");
            finish();
            return;
        }
        step("App 關著，提醒時間到→通知跳出", true, "比預定晚 " + (seen - target) + " 秒（每 5 秒查一次）");

        // 8. 拉下通知列、點通知
        kit.device.openNotification();
        QaKit.sleep(2500);
        kit.shot("07-notification-shade");
        UiObject2 note = kit.device.wait(Until.findObject(By.text(Pattern.compile("(?s).*(沐寧提醒|Munea reminder|Munea).*"))), 8000);
        step("通知列找得到「沐寧提醒」", note != null, note != null ? note.getText() : "找不到文字");
        if (note == null) { finish(); return; }
        note.click();
        boolean opened = kit.device.wait(Until.hasObject(By.pkg(QaKit.PKG).depth(0)), 20000);
        boolean bridge2 = opened && kit.waitBridge(40);
        QaKit.sleep(2500);
        kit.shot("08-opened-from-notification");
        String view = bridge2 ? kit.evalJs("var a=document.querySelector('.tab-btn.active'); var s=document.querySelector('.screen.active'); return {activeTab: a&&a.dataset?a.dataset.view:null, activeScreen: s?s.id:null}", 15) : "WebView 接不上";
        step("點通知→打開 App、直接到用藥頁（status）", view.contains("\"status\""), view);

        finish();
    }
}
