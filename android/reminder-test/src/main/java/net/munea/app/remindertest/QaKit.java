package net.munea.app.remindertest;

import android.os.Bundle;
import android.util.Base64;
import android.util.Log;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONTokener;

import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 雲端真機測試的共用小工具：shell、截圖、結果記錄、在 App 網頁殼執行 JS 並取回結果、取測試參數。
 * 之後的登入／聊聊／家人圈測試直接重用這支。測試包裡不寫死任何帳密，參數一律從
 * `gcloud firebase test android run --environment-variables key=value` 傳進來（args("key")）。
 */
final class QaKit {
    static final String PKG = "net.munea.app";
    static final String OUT_DIR = "/sdcard/screenshots"; // Test Lab 會把這個資料夾帶回（另外也用 --directories-to-pull 指定）
    private static final String TAG = "MuneaQa";

    final UiDevice device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation());
    private final Bundle args = InstrumentationRegistry.getArguments();

    QaKit() {
        sh("mkdir -p " + OUT_DIR);
    }

    /** 測試參數（沒給回 fallback）。 */
    String args(String key, String fallback) {
        String v = args.getString(key);
        return v == null || v.isEmpty() ? fallback : v;
    }

    int argsInt(String key, int fallback) {
        try { return Integer.parseInt(args(key, String.valueOf(fallback))); } catch (NumberFormatException e) { return fallback; }
    }

    String sh(String cmd) {
        try { return device.executeShellCommand(cmd); } catch (Exception e) { return "ERR:" + e; }
    }

    long deviceNowSec() {
        try { return Long.parseLong(sh("date +%s").trim()); } catch (Exception e) { return System.currentTimeMillis() / 1000; }
    }

    void shot(String name) {
        sh("screencap -p " + OUT_DIR + "/" + name + ".png");
    }

    /** 記一行到 logcat 與 /sdcard/screenshots/result.txt（Test Lab 會帶回）。 */
    void log(String line) {
        Log.i(TAG, line);
        String stamped = new SimpleDateFormat("HH:mm:ss", Locale.US).format(new Date()) + " " + line;
        String b64 = Base64.encodeToString((stamped + "\n").getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        sh("echo " + b64 + " | base64 -d >> " + OUT_DIR + "/result.txt");
    }

    /**
     * 在 App 的 WebView 跑一段 JS（函式本體，要 return、可以 await），回傳 JSON 字串；失敗回 "ERR:..."。
     * 走 debug 包裡的 net.munea.app.debug.EVAL 廣播（只有 shell 叫得動）。App 要在執行中。
     */
    String evalJs(String jsBody, int timeoutSec) {
        String b64 = Base64.encodeToString(jsBody.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        String out = sh("am broadcast -n " + PKG + "/net.munea.app.debugbridge.DebugEvalReceiver"
                + " -a net.munea.app.debug.EVAL --es js64 " + b64 + " --ei timeout " + timeoutSec);
        Matcher m = Pattern.compile("data=\"(.*)\"\\s*$", Pattern.DOTALL | Pattern.MULTILINE).matcher(out);
        if (!m.find()) return "ERR:no-data " + out.replace('\n', ' ');
        String raw = m.group(1);
        try {
            Object v = new JSONTokener(raw).nextValue();
            return String.valueOf(v);
        } catch (Exception e) {
            return raw;
        }
    }

    String pidOfApp() {
        String out = sh("pidof " + PKG).trim();
        return out.isEmpty() ? "" : out.split("\\s+")[0];
    }

    /** 等 App 的網頁殼起來、提醒橋接在（最多 sec 秒）。 */
    boolean waitBridge(int sec) {
        long end = System.currentTimeMillis() + sec * 1000L;
        while (System.currentTimeMillis() < end) {
            String r = evalJs("return !!(window.MuneaNotify && window.MuneaAndroidNotify)", 10);
            if ("true".equals(r)) return true;
            sleep(2000);
        }
        return false;
    }

    static void sleep(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
    }

    // ---- 登入／聊聊／家人圈測試共用 ----

    /** 把字串變成 JS 字串常值（全部非英數字元用 unicode 跳脫，帳密裡有引號也安全）。 */
    static String jsQuote(String s) {
        String bs = String.valueOf((char) 92);
        StringBuilder sb = new StringBuilder("'");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) sb.append(c);
            else sb.append(bs).append(String.format("u%04x", (int) c));
        }
        return sb.append("'").toString();
    }

    /** 記錄用：只留前兩個字與網域，不印完整信箱。 */
    static String maskEmail(String email) {
        if (email == null) return "";
        int at = email.indexOf('@');
        if (at < 1) return "***";
        return email.substring(0, Math.min(2, at)) + "***" + email.substring(at);
    }

    /** 開 App、等網頁殼、跳過開場介紹（真機慢，等啟動頁收掉）。成功回 true。 */
    boolean prepareApp() {
        try {
            device.wakeUp();
            device.setOrientationNatural();
            device.freezeRotation();
        } catch (Exception e) { log("WARN 鎖直向失敗 " + e); }
        sh("monkey -p " + PKG + " -c android.intent.category.LAUNCHER 1");
        boolean front = device.wait(androidx.test.uiautomator.Until.hasObject(androidx.test.uiautomator.By.pkg(PKG).depth(0)), 40000);
        if (!front || !waitBridge(60)) { log("FAIL App 沒起來 front=" + front); return false; }
        long end = System.currentTimeMillis() + 40000;
        while (System.currentTimeMillis() < end) {
            if ("true".equals(evalJs("var sp=document.getElementById('bootSplash'); return !sp || sp.hidden", 10))) break;
            sleep(1000);
        }
        for (int i = 0; i < 3; i++) {
            evalJs("localStorage.setItem('munea.onboardingIntroSeen.v1','true'); var s=document.getElementById('onbStart'); if(s) s.click(); var o=document.getElementById('onboarding'); if(o) o.hidden=true; return true", 10);
            sleep(3000);
            if (evalJs("var o=document.getElementById('onboarding'); return !!o && !o.hidden", 10).equals("false")) return true;
        }
        log("FAIL 開場介紹跳不掉");
        return false;
    }

    /** 若有系統權限視窗（麥克風、通知）就點允許；有點到回 true。 */
    boolean allowPermissionDialog() {
        androidx.test.uiautomator.UiObject2 allow = device.findObject(androidx.test.uiautomator.By.res(java.util.regex.Pattern.compile(".*:id/(permission_allow_button|permission_allow_foreground_only_button|permission_allow_one_time_button)")));
        if (allow == null) allow = device.findObject(androidx.test.uiautomator.By.text(java.util.regex.Pattern.compile("(?i)^(While using the app|Allow|允許|仅在使用时允许|使用中のみ許可|許可)$")));
        if (allow == null) return false;
        log("PERM-DIALOG 點 " + allow.getText());
        allow.click();
        return true;
    }
}
