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
        sh("sh -c 'echo " + b64 + " | base64 -d >> " + OUT_DIR + "/result.txt'");
    }

    /**
     * 在 App 的 WebView 跑一段 JS（函式本體，要 return、可以 await），回傳 JSON 字串；失敗回 "ERR:..."。
     * 走 debug 包裡的 net.munea.app.debug.EVAL 廣播（只有 shell 叫得動）。App 要在執行中。
     */
    String evalJs(String jsBody, int timeoutSec) {
        String b64 = Base64.encodeToString(jsBody.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
        String out = sh("am broadcast -n " + PKG + "/net.munea.app.debugbridge.DebugEvalReceiver"
                + " -a net.munea.app.debug.EVAL --es js64 " + b64 + " --ei timeout " + timeoutSec);
\s\s\s\s\s\s\s\sMatcher\sm\s=\sPattern.compile("data=\"(.*)\"\s*$",\sPattern.DOTALL\s|\sPattern.MULTILINE).matcher(out);
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
\s\s\s\s\s\s\s\sreturn\sout.isEmpty()\s?\s""\s:\sout.split("\s+")[0];
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
}
