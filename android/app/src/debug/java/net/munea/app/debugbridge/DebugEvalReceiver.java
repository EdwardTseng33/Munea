package net.munea.app.debugbridge;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.webkit.ValueCallback;
import android.webkit.WebView;

import java.nio.charset.StandardCharsets;

/**
 * adb shell am broadcast -a net.munea.app.debug.EVAL --es js64 BASE64 [--ei timeout 60]
 * js64 是 JS 函式本體（要 return 值、可以 await）。結果 JSON 字串放在廣播的 data 裡（am 會印出來）。
 * 只進 debug 包；呼叫端要持有 DUMP 權限（shell）。
 */
public class DebugEvalReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        final PendingResult result = goAsync();
        final Handler main = new Handler(Looper.getMainLooper());
        String js64 = intent.getStringExtra("js64");
        final int timeoutSec = intent.getIntExtra("timeout", 60);
        if (js64 == null) { result.setResultData("ERR:no js64"); result.finish(); return; }
        final String body = new String(Base64.decode(js64, Base64.DEFAULT), StandardCharsets.UTF_8);
        main.post(new Runnable() {
            @Override public void run() {
                final WebView wv = DebugBridgeProvider.webView();
                if (wv == null) { result.setResultData("ERR:no webview"); result.finish(); return; }
                String start = "(function(){window.__dbgR=undefined;(async function(){try{var v=await (async function(){" + body
                        + "\n})();window.__dbgR=JSON.stringify(v===undefined?null:v);}catch(e){window.__dbgR='ERR:'+e;}})();return 1;})()";
                wv.evaluateJavascript(start, null);
                poll(wv, main, result, System.currentTimeMillis() + timeoutSec * 1000L);
            }
        });
    }

    private void poll(final WebView wv, final Handler main, final PendingResult result, final long deadline) {
        wv.evaluateJavascript("window.__dbgR===undefined?'__pending__':window.__dbgR", new ValueCallback<String>() {
            @Override public void onReceiveValue(String value) {
                if (value != null && !value.equals("\"__pending__\"")) {
                    result.setResultData(value);
                    result.finish();
                } else if (System.currentTimeMillis() > deadline) {
                    result.setResultData("ERR:timeout");
                    result.finish();
                } else {
                    main.postDelayed(new Runnable() { @Override public void run() { poll(wv, main, result, deadline); } }, 300);
                }
            }
        });
    }
}
